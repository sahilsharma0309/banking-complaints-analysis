"""
Stage 7 -- Tableau handoff.

Creates four PostgreSQL views so Tableau connects to clean, pre-shaped data
rather than to raw tables, then exports the same shapes to dashboard/ as CSV
and (if tableauhyperapi is available) as a .hyper extract.

PRIMARY PATH  Tableau -> PostgreSQL live connection -> cfpb.v_* views
BACKUP PATH   Tableau -> dashboard/*.csv  or  dashboard/banking_complaints.hyper

WHY VIEWS
---------
A view means Tableau never contains business logic. The 500-complaint floor, the
trend-window bound, the resolved-only denominator and the FDIC join all live in
SQL where they are versioned and reviewable. If the definition of "risk" changes
the view changes and every worksheet follows -- nobody has to remember which
Tableau calculated field encoded the rule.

Build steps for the dashboard itself: dashboard/TABLEAU_BUILD_GUIDE.md
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text as sa_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASH = PROJECT_ROOT / "dashboard"
load_dotenv(PROJECT_ROOT / ".env")
SCHEMA = "cfpb"

VIEWS: dict[str, str] = {}

VIEWS["v_company_summary"] = f"""
-- One row per company. Drives the ranking bars and the resolution scatter.
-- Companies below the 500-complaint floor are EXCLUDED here (not merely
-- unscored) because every measure on this view is a rate, and rates on tiny
-- denominators are noise that would dominate any sort.
CREATE OR REPLACE VIEW {SCHEMA}.v_company_summary AS
SELECT
    r.company,
    r.total_complaints,
    r.resolved_complaints,
    r.products_touched,
    r.states_touched,
    r.first_complaint,
    r.last_complaint,
    -- resolution quality
    r.monetary_relief_rate,
    r.any_relief_rate,
    r.pct_no_relief,
    r.explanation_only_rate,
    r.untimely_rate,
    r.disputes_facts_rate,
    r.avg_days_to_company,
    r.median_days_to_company,
    r.p90_days_to_company,
    -- vulnerable populations
    r.pct_servicemember,
    r.pct_older_american,
    -- size adjustment (NULL for non-banks by design)
    r.matched                       AS is_fdic_matched,
    r.fdic_name,
    r.total_assets_b,
    r.n_charters,
    r.complaints_per_1b_assets,
    -- scores
    r.conduct_risk_score,
    r.exposure_risk_score,
    r.risk_tier,
    -- Why a company has no size-adjusted figure, in plain language. Put this on
    -- the tooltip so a viewer seeing a blank bar learns it is structural, not a
    -- data gap.
    CASE
        WHEN r.matched THEN 'FDIC-insured depository'
        WHEN r.match_method = 'known_non_bank'    THEN 'Non-bank: no FDIC charter'
        WHEN r.match_method = 'ncua_credit_union' THEN 'Credit union: NCUA-insured, not in FDIC data'
        WHEN r.match_method = 'inactive_charter'  THEN 'Charter no longer active (merged/acquired)'
        ELSE 'No confident FDIC match'
    END                             AS fdic_status,
    -- Rank over ALL scored companies. Informational only -- it answers "how big
    -- a complaint generator is this overall", including non-banks.
    RANK() OVER (ORDER BY r.total_complaints DESC)          AS overall_volume_rank,

    -- THE HEADLINE CONTRAST. Both ranks are computed over the SAME population
    -- (FDIC-matched depositories only, via the PARTITION on matched), because
    -- subtracting ranks drawn from different populations is meaningless.
    --
    -- The first version ranked volume over all 112 scored companies but the
    -- size-adjusted rate over only the 28 matched ones, then subtracted them.
    -- That inflated every gap: SoFi read as 32 -> 3 (a "+29 move") when the
    -- honest comparison within the matched cohort is 18 -> 3 (+15). The symptom
    -- was a rank_gap range of -23..98 where the true range is -23..18.
    CASE WHEN r.matched AND r.complaints_per_1b_assets IS NOT NULL
         THEN RANK() OVER (PARTITION BY (r.matched AND r.complaints_per_1b_assets IS NOT NULL)
                           ORDER BY r.total_complaints DESC)
    END                                                     AS volume_rank,
    CASE WHEN r.matched AND r.complaints_per_1b_assets IS NOT NULL
         THEN RANK() OVER (PARTITION BY (r.matched AND r.complaints_per_1b_assets IS NOT NULL)
                           ORDER BY r.complaints_per_1b_assets DESC)
    END                                                     AS size_adjusted_rank,
    CASE WHEN r.matched AND r.complaints_per_1b_assets IS NOT NULL
         THEN RANK() OVER (PARTITION BY (r.matched AND r.complaints_per_1b_assets IS NOT NULL)
                           ORDER BY r.total_complaints DESC)
            - RANK() OVER (PARTITION BY (r.matched AND r.complaints_per_1b_assets IS NOT NULL)
                           ORDER BY r.complaints_per_1b_assets DESC)
    END                                                     AS rank_gap
FROM {SCHEMA}.company_risk_profile r
WHERE r.total_complaints >= 500;
"""

VIEWS["v_complaints_enriched"] = f"""
-- Complaint-level fact view with company attributes joined on. This is the
-- filter/detail source for the dashboard.
-- Bounded to in_trend_window: the extract ends 2026-01-01, so 2026 is a
-- one-day stub that would render as a collapse in any date-axis chart.
CREATE OR REPLACE VIEW {SCHEMA}.v_complaints_enriched AS
SELECT
    c.complaint_id,
    c.date_received,
    c.year,
    c.month,
    c.year_month,
    c.product,
    c.product_short,
    c.sub_product,
    c.issue,
    c.sub_issue,
    c.company,
    c.state,
    c.state_type,
    c.zip3,
    c.submitted_via,
    c.company_response,
    c.company_public_response,
    c.timely,
    c.tags,
    c.is_servicemember,
    c.is_older_american,
    c.has_narrative,
    c.days_to_company,
    c.is_resolved,
    c.got_monetary_relief,
    c.got_any_relief,
    c.is_untimely,
    c.closed_explanation_only,
    -- company attributes for cross-filtering without a second data source
    e.matched            AS is_fdic_matched,
    e.fdic_name,
    e.total_assets_b,
    r.conduct_risk_score,
    r.exposure_risk_score,
    r.risk_tier
FROM {SCHEMA}.complaints c
LEFT JOIN {SCHEMA}.company_enriched     e ON e.company = c.company
LEFT JOIN {SCHEMA}.company_risk_profile r ON r.company = c.company
WHERE c.in_trend_window;
"""

VIEWS["v_monthly_trend"] = f"""
-- Pre-aggregated monthly series by product. Small and fast: use this for the
-- trend line rather than making Tableau aggregate 624k rows on every redraw.
CREATE OR REPLACE VIEW {SCHEMA}.v_monthly_trend AS
WITH m AS (
    SELECT
        year_month,
        MIN(date_received)                          AS month_start,
        product,
        product_short,
        count(*)                                    AS complaints,
        count(*) FILTER (WHERE is_resolved)         AS resolved,
        count(*) FILTER (WHERE got_monetary_relief) AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)         AS untimely
    FROM {SCHEMA}.complaints
    WHERE in_trend_window
    GROUP BY year_month, product, product_short
)
SELECT
    m.*,
    ROUND(100.0 * monetary_relief / NULLIF(resolved, 0), 2) AS monetary_relief_rate,
    ROUND(100.0 * untimely        / NULLIF(resolved, 0), 2) AS untimely_rate,
    LAG(complaints) OVER (PARTITION BY product ORDER BY year_month) AS prev_month,
    ROUND(100.0 * (complaints - LAG(complaints) OVER (PARTITION BY product ORDER BY year_month))
          / NULLIF(LAG(complaints) OVER (PARTITION BY product ORDER BY year_month), 0), 2)
                                                            AS mom_pct_change,
    ROUND(AVG(complaints) OVER (PARTITION BY product ORDER BY year_month
                                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
                                                            AS moving_avg_3m
FROM m;
"""

VIEWS["v_state_summary"] = f"""
-- One row per US state (50 + DC) for the map. Territories and military
-- APO/FPO codes are excluded: AA/AE/AP are postal routing codes, not places,
-- and would plot as phantom geography.
CREATE OR REPLACE VIEW {SCHEMA}.v_state_summary AS
WITH t AS (
    SELECT
        state,
        count(*)                                    AS complaints,
        count(*) FILTER (WHERE is_resolved)         AS resolved,
        count(*) FILTER (WHERE got_monetary_relief) AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)         AS untimely,
        count(DISTINCT company)                     AS companies,
        ROUND(AVG(days_to_company) FILTER (WHERE NOT dq_long_routing_lag), 2)
                                                    AS avg_days_to_company
    FROM {SCHEMA}.complaints
    WHERE in_trend_window AND state_type = 'state'
    GROUP BY state
),
top_issue AS (
    SELECT state, issue, ROW_NUMBER() OVER (PARTITION BY state ORDER BY count(*) DESC) rn
    FROM {SCHEMA}.complaints
    WHERE in_trend_window AND state_type = 'state'
    GROUP BY state, issue
),
top_product AS (
    SELECT state, product_short, ROW_NUMBER() OVER (PARTITION BY state ORDER BY count(*) DESC) rn
    FROM {SCHEMA}.complaints
    WHERE in_trend_window AND state_type = 'state'
    GROUP BY state, product_short
)
SELECT
    t.state,
    t.complaints,
    t.companies,
    ROUND(100.0 * t.complaints / SUM(t.complaints) OVER (), 3) AS pct_of_national,
    ROUND(100.0 * t.monetary_relief / NULLIF(t.resolved, 0), 2) AS monetary_relief_rate,
    ROUND(100.0 * t.untimely        / NULLIF(t.resolved, 0), 2) AS untimely_rate,
    t.avg_days_to_company,
    ti.issue          AS top_issue,
    tp.product_short  AS top_product
FROM t
JOIN top_issue   ti ON ti.state = t.state AND ti.rn = 1
JOIN top_product tp ON tp.state = t.state AND tp.rn = 1;
"""

EXPORTS = {
    "company_summary":     f"SELECT * FROM {SCHEMA}.v_company_summary ORDER BY total_complaints DESC",
    "monthly_trend":       f"SELECT * FROM {SCHEMA}.v_monthly_trend ORDER BY product, year_month",
    "state_summary":       f"SELECT * FROM {SCHEMA}.v_state_summary ORDER BY complaints DESC",
    "top_issues_by_product": f"""
        SELECT product_short, issue, count(*) AS complaints,
               count(*) FILTER (WHERE got_monetary_relief) AS monetary_relief,
               ROUND(100.0*count(*) FILTER (WHERE got_monetary_relief)
                     / NULLIF(count(*) FILTER (WHERE is_resolved),0),2) AS relief_rate
        FROM {SCHEMA}.complaints WHERE in_trend_window
        GROUP BY product_short, issue HAVING count(*) >= 50
        ORDER BY product_short, complaints DESC""",
}


def banner(m: str) -> None:
    print(f"\n{'=' * 74}\n{m}\n{'=' * 74}", flush=True)


def log(m: str) -> None:
    print(f"  {m}", flush=True)


def main() -> None:
    DASH.mkdir(parents=True, exist_ok=True)
    eng = create_engine(
        f"postgresql+psycopg2://{os.getenv('PGUSER','postgres')}:"
        f"{quote_plus(os.getenv('PGPASSWORD',''))}@{os.getenv('PGHOST','localhost')}:"
        f"{os.getenv('PGPORT','5432')}/{os.getenv('PGDATABASE','banking_complaints')}")

    banner("STAGE 7 -- CREATING POSTGRESQL VIEWS FOR TABLEAU")
    with eng.begin() as c:
        for name, ddl in VIEWS.items():
            c.execute(sa_text(f"DROP VIEW IF EXISTS {SCHEMA}.{name} CASCADE"))
            c.execute(sa_text(ddl))
            n = c.execute(sa_text(f"SELECT count(*) FROM {SCHEMA}.{name}")).scalar()
            log(f"{SCHEMA}.{name:<24} {n:>9,} rows")

    banner("EXPORTING CSV BACKUPS TO dashboard/")
    frames: dict[str, pd.DataFrame] = {}
    with eng.connect() as c:
        for name, q in EXPORTS.items():
            df = pd.read_sql(sa_text(q), c)
            frames[name] = df
            path = DASH / f"{name}.csv"
            df.to_csv(path, index=False)
            log(f"{path.name:<28} {len(df):>7,} rows  {path.stat().st_size/1024:>7.0f} KB")

    banner("TABLEAU .hyper EXTRACT")
    # Date columns arrive from psycopg2 as Python date objects, which pandas
    # holds as dtype=object -> the extract writer would type them as TEXT and
    # Tableau would render a string axis instead of a real date axis (no
    # continuous months, no date filter). Declared explicitly instead.
    DATE_COLUMNS = {
        "monthly_trend": ["month_start"],
        "company_summary": ["first_complaint", "last_complaint"],
    }
    try:
        from tableauhyperapi import (Connection, HyperProcess, SqlType, TableDefinition,
                                     TableName, Telemetry, Inserter, CreateMode)

        hyper_path = DASH / "banking_complaints.hyper"

        def sql_type(dtype):
            k = dtype.kind
            if k in "i":
                return SqlType.big_int()
            if k in "fu":
                return SqlType.double()
            if k == "b":
                return SqlType.bool()
            if k == "M":
                return SqlType.date()
            return SqlType.text()

        with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
            with Connection(hp.endpoint, str(hyper_path),
                            CreateMode.CREATE_AND_REPLACE) as conn:
                conn.catalog.create_schema("Extract")
                for name, df in frames.items():
                    d = df.copy()
                    date_cols = DATE_COLUMNS.get(name, [])
                    for col in date_cols:
                        if col in d.columns:
                            d[col] = pd.to_datetime(d[col], errors="coerce").dt.date
                    for col in d.columns:
                        if col in date_cols:
                            continue
                        if d[col].dtype.kind == "O":
                            d[col] = d[col].astype(str).replace({"nan": None, "None": None})
                    tdef = TableDefinition(
                        TableName("Extract", name),
                        [TableDefinition.Column(
                            c, SqlType.date() if c in date_cols else sql_type(d[c].dtype))
                         for c in d.columns])
                    conn.catalog.create_table(tdef)
                    with Inserter(conn, tdef) as ins:
                        ins.add_rows(d.where(pd.notna(d), None).values.tolist())
                        ins.execute()
                    log(f"Extract.{name:<26} {len(d):>7,} rows")
        log(f"wrote {hyper_path.name} ({hyper_path.stat().st_size/1e6:.1f} MB)")
    except ImportError:
        log("tableauhyperapi not installed -- skipping .hyper (CSV backup is sufficient)")
    except Exception as exc:  # noqa: BLE001
        log(f"! .hyper generation failed: {type(exc).__name__}: {str(exc)[:120]}")
        log("  CSV backups above are unaffected.")

    banner("CONNECTION DETAILS FOR TABLEAU")
    print(f"  Server   : {os.getenv('PGHOST','localhost')}")
    print(f"  Port     : {os.getenv('PGPORT','5432')}")
    print(f"  Database : {os.getenv('PGDATABASE','banking_complaints')}")
    print(f"  Schema   : {SCHEMA}")
    print(f"  Username : {os.getenv('PGUSER','postgres')}")
    print("  Password : (the PGPASSWORD value in your .env)")
    print("\n  Views to drag onto the canvas:")
    for v in VIEWS:
        print(f"    {v}")
    print("\n  Build steps: dashboard/TABLEAU_BUILD_GUIDE.md")
    eng.dispose()
    print("\nSTAGE 7 COMPLETE")


if __name__ == "__main__":
    main()
