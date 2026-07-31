"""
Stage 6 -- Feature engineering: the company-level risk profile that feeds Tableau.

Reads   PostgreSQL cfpb.complaints + cfpb.company_enriched
Writes  cfpb.company_risk_profile          (table, for Tableau + Stage 7 views)
        data/processed/company_risk_profile.csv
        reports/risk_score_methodology.md  (generated)

WHY TWO SCORES AND NOT ONE
--------------------------
The obvious design is a single composite. It would be wrong here, for a reason
worth stating plainly:

`complaints_per_1b_assets` divides by total assets, which proxies *balance sheet
size*, not *customer count*. A monoline card issuer serves millions of customers
on a small balance sheet; a universal bank holds mortgages and commercial loans
that add assets without adding retail customers. So card issuers score high on
that measure partly by business model rather than by conduct. Worse, the measure
is undefined for the ~50% of complaint volume belonging to non-banks -- credit
bureaus, NCUA credit unions, loan servicers, fintechs -- which would silently
drop half the market out of any single composite.

So this stage produces:

  conduct_risk_score     0-100. Resolution behaviour ONLY -- how a company
                         handles the complaints it receives. Defined for EVERY
                         company with enough volume, bank or not. Immune to the
                         business-model distortion. This is the defensible one
                         for statements about conduct.

  exposure_risk_score    0-100. Adds size-adjusted complaint frequency. Only
                         defined for FDIC-matched depositories. Answers "how
                         much consumer friction per dollar of balance sheet".

Both are percentile-based, so a score of 80 means "worse than 80% of peers" --
directly interpretable, and robust to the heavy skew in these rates that would
distort a min-max or z-score normalisation.

MINIMUM VOLUME
--------------
Only companies with >= MIN_COMPLAINTS receive a score. A 0% relief rate on 3
complaints is noise; ranking on it would fill the top of the table with
companies nobody has heard of. Companies below the floor are retained in the
output with NULL scores so nothing disappears silently.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text as sa_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROC = PROJECT_ROOT / "data" / "processed"
OUT_CSV = PROC / "company_risk_profile.csv"
METHOD_MD = PROJECT_ROOT / "reports" / "risk_score_methodology.md"

load_dotenv(PROJECT_ROOT / ".env")
SCHEMA = "cfpb"
MIN_COMPLAINTS = 500

# ---- score weights --------------------------------------------------------
# Chosen to reflect what a compliance team actually cares about, and stated
# explicitly so a reader can disagree with the weighting rather than having to
# reverse-engineer it.
#
# `explanation_only_rate` was DROPPED from the score after checking it against
# `pct_no_relief`: they correlate at Spearman rho = 0.954 and differ by a mean
# of 1.0 percentage points. That is the same construct measured twice -- closing
# with an explanation IS giving no relief -- and together they were carrying 55%
# of the weight, so the score was largely one variable wearing two hats. It is
# still reported as an output column, just not double-counted in the score.
# Every remaining pairwise correlation is <= 0.33.
CONDUCT_WEIGHTS = {
    "pct_no_relief":        0.40,   # company gave the consumer nothing at all
    "untimely_rate":        0.35,   # missed the response deadline -- hard failure
    "disputes_facts_rate":  0.15,   # formally contests the consumer's account
    "avg_days_to_company":  0.10,   # slow routing -- weakest signal, least weight
}
EXPOSURE_WEIGHTS = {
    "conduct_risk_score":       0.60,
    "complaints_per_1b_assets": 0.40,
}


def banner(m: str) -> None:
    print(f"\n{'=' * 74}\n{m}\n{'=' * 74}", flush=True)


def log(m: str) -> None:
    print(f"  {m}", flush=True)


def engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('PGUSER','postgres')}:"
        f"{quote_plus(os.getenv('PGPASSWORD',''))}@{os.getenv('PGHOST','localhost')}:"
        f"{os.getenv('PGPORT','5432')}/{os.getenv('PGDATABASE','banking_complaints')}")


FEATURE_SQL = f"""
WITH base AS (
    SELECT * FROM {SCHEMA}.complaints WHERE in_trend_window
),
resolved AS (
    SELECT * FROM base WHERE is_resolved
)
SELECT
    b.company,
    count(*)                                                AS total_complaints,
    count(DISTINCT b.product)                               AS products_touched,
    count(DISTINCT b.state) FILTER (WHERE b.state_type='state') AS states_touched,
    min(b.date_received)                                    AS first_complaint,
    max(b.date_received)                                    AS last_complaint,
    count(*) FILTER (WHERE b.is_servicemember)              AS servicemember_complaints,
    count(*) FILTER (WHERE b.is_older_american)             AS older_american_complaints,
    count(*) FILTER (WHERE b.has_narrative)                 AS with_narrative,
    -- Routing speed. Long-lag outliers excluded so a handful of extreme values
    -- cannot drag a company's mean.
    ROUND(AVG(b.days_to_company) FILTER (WHERE NOT b.dq_long_routing_lag), 3)
                                                            AS avg_days_to_company,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.days_to_company)::numeric, 3)
                                                            AS median_days_to_company,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY b.days_to_company)::numeric, 3)
                                                            AS p90_days_to_company
FROM base b
GROUP BY b.company
"""

OUTCOME_SQL = f"""
SELECT
    company,
    count(*)                                            AS resolved_complaints,
    count(*) FILTER (WHERE got_monetary_relief)         AS monetary_relief_n,
    count(*) FILTER (WHERE got_any_relief)              AS any_relief_n,
    count(*) FILTER (WHERE closed_explanation_only)     AS explanation_only_n,
    count(*) FILTER (WHERE is_untimely)                 AS untimely_n,
    count(*) FILTER (WHERE company_disputes_facts)      AS disputes_facts_n
FROM {SCHEMA}.complaints
WHERE in_trend_window AND is_resolved
GROUP BY company
"""


def pct_rank(s: pd.Series, higher_is_worse: bool = True) -> pd.Series:
    """Percentile rank scaled 0-100. 80 = worse than 80% of scored peers."""
    r = s.rank(pct=True, na_option="keep")
    if not higher_is_worse:
        r = 1 - r
    return (100 * r).round(2)


def main() -> None:
    eng = engine()
    banner("STAGE 6 -- COMPANY RISK PROFILE")

    with eng.connect() as c:
        feats = pd.read_sql(sa_text(FEATURE_SQL), c)
        outcomes = pd.read_sql(sa_text(OUTCOME_SQL), c)
        enriched = pd.read_sql(
            sa_text(f"SELECT company, matched, fdic_name, total_assets_b, "
                    f"n_charters, match_method FROM {SCHEMA}.company_enriched"), c)

    df = feats.merge(outcomes, on="company", how="left").merge(
        enriched, on="company", how="left")
    log(f"companies: {len(df):,}")

    # ---- rates -----------------------------------------------------------
    rc = df["resolved_complaints"].replace(0, pd.NA)
    df["monetary_relief_rate"] = (100 * df.monetary_relief_n / rc).round(3)
    df["any_relief_rate"] = (100 * df.any_relief_n / rc).round(3)
    df["pct_no_relief"] = (100 - df["any_relief_rate"]).round(3)
    df["explanation_only_rate"] = (100 * df.explanation_only_n / rc).round(3)
    df["untimely_rate"] = (100 * df.untimely_n / rc).round(3)
    df["disputes_facts_rate"] = (100 * df.disputes_facts_n / rc).round(3)
    df["pct_servicemember"] = (100 * df.servicemember_complaints
                               / df.total_complaints).round(3)
    df["pct_older_american"] = (100 * df.older_american_complaints
                                / df.total_complaints).round(3)
    df["complaints_per_1b_assets"] = (
        df.total_complaints / df.total_assets_b).round(3)
    df.loc[~df["matched"].fillna(False), "complaints_per_1b_assets"] = pd.NA

    # ---- scoring cohort --------------------------------------------------
    scored = df["total_complaints"] >= MIN_COMPLAINTS
    log(f"companies meeting the {MIN_COMPLAINTS}-complaint floor: {scored.sum():,} "
        f"({100*df.loc[scored,'total_complaints'].sum()/df.total_complaints.sum():.1f}% "
        f"of complaint volume)")

    banner("CONDUCT RISK SCORE (all companies, bank or not)")
    comps = {}
    for col, w in CONDUCT_WEIGHTS.items():
        pr = pd.Series(pd.NA, index=df.index, dtype="Float64")
        pr.loc[scored] = pct_rank(df.loc[scored, col], higher_is_worse=True)
        comps[col] = pr
        df[f"pctile_{col}"] = pr
        log(f"{col:<24} weight {w:>5.0%}  "
            f"median={df.loc[scored, col].median():8.3f}  "
            f"p90={df.loc[scored, col].quantile(.9):8.3f}")

    conduct = sum(comps[c] * w for c, w in CONDUCT_WEIGHTS.items())
    df["conduct_risk_score"] = conduct.astype("Float64").round(2)

    banner("EXPOSURE RISK SCORE (FDIC-matched depositories only)")
    matched_scored = scored & df["matched"].fillna(False) & \
        df["complaints_per_1b_assets"].notna()
    log(f"eligible: {matched_scored.sum():,} companies")

    pr_size = pd.Series(pd.NA, index=df.index, dtype="Float64")
    pr_size.loc[matched_scored] = pct_rank(
        df.loc[matched_scored, "complaints_per_1b_assets"], higher_is_worse=True)
    df["pctile_complaints_per_1b_assets"] = pr_size

    # Conduct percentile is re-ranked within the matched cohort so both
    # components are on the same peer basis.
    pr_conduct_matched = pd.Series(pd.NA, index=df.index, dtype="Float64")
    pr_conduct_matched.loc[matched_scored] = pct_rank(
        df.loc[matched_scored, "conduct_risk_score"], higher_is_worse=True)

    df["exposure_risk_score"] = (
        pr_conduct_matched * EXPOSURE_WEIGHTS["conduct_risk_score"]
        + pr_size * EXPOSURE_WEIGHTS["complaints_per_1b_assets"]
    ).astype("Float64").round(2)

    df["risk_tier"] = pd.NA
    df.loc[scored, "risk_tier"] = pd.cut(
        df.loc[scored, "conduct_risk_score"].astype(float),
        bins=[-0.01, 25, 50, 75, 90, 100.01],
        labels=["Low", "Moderate", "Elevated", "High", "Severe"]).astype(str)

    # Sort AFTER scoring, and re-derive the masks from the sorted frame -- a
    # boolean Series built on the pre-sort index misaligns on reindex.
    df = df.sort_values("total_complaints", ascending=False).reset_index(drop=True)
    scored = df["total_complaints"] >= MIN_COMPLAINTS
    matched_scored = scored & df["matched"].fillna(False) & \
        df["complaints_per_1b_assets"].notna()
    df.to_csv(OUT_CSV, index=False)
    log(f"wrote {OUT_CSV.name}: {len(df):,} rows x {df.shape[1]} cols")

    # ---- load into Postgres ---------------------------------------------
    with eng.begin() as c:
        c.execute(sa_text(f"DROP TABLE IF EXISTS {SCHEMA}.company_risk_profile CASCADE"))
    df.to_sql("company_risk_profile", eng, schema=SCHEMA, index=False,
              if_exists="replace", chunksize=1000)
    with eng.begin() as c:
        c.execute(sa_text(f"""CREATE INDEX idx_risk_profile_conduct
                              ON {SCHEMA}.company_risk_profile (conduct_risk_score DESC)"""))
        c.execute(sa_text(f"""CREATE INDEX idx_risk_profile_company
                              ON {SCHEMA}.company_risk_profile (company)"""))
    log(f"loaded {SCHEMA}.company_risk_profile into PostgreSQL")

    # ---- report ----------------------------------------------------------
    banner("HIGHEST CONDUCT RISK (>= 500 complaints)")
    top = df[scored].nlargest(15, "conduct_risk_score")
    print(f"  {'score':>6} {'tier':<9} {'complaints':>11} {'no relief':>10} "
          f"{'untimely':>9}  company")
    for r in top.itertuples():
        print(f"  {r.conduct_risk_score:>6.1f} {str(r.risk_tier):<9} "
              f"{r.total_complaints:>11,} {r.pct_no_relief:>9.1f}% "
              f"{r.untimely_rate:>8.1f}%  {str(r.company)[:38]}")

    banner("HIGHEST EXPOSURE RISK (FDIC-matched depositories)")
    tope = df[matched_scored].nlargest(15, "exposure_risk_score")
    print(f"  {'score':>6} {'conduct':>8} {'per $1B':>9} {'assets$B':>10}  company")
    for r in tope.itertuples():
        print(f"  {r.exposure_risk_score:>6.1f} {r.conduct_risk_score:>8.1f} "
              f"{r.complaints_per_1b_assets:>9.1f} {r.total_assets_b:>10,.0f}  "
              f"{str(r.company)[:38]}")

    banner("RISK TIER DISTRIBUTION")
    for tier, n in df.loc[scored, "risk_tier"].value_counts().items():
        vol = df.loc[scored & (df.risk_tier == tier), "total_complaints"].sum()
        print(f"  {str(tier):<10} {n:>4} companies  {vol:>9,} complaints")

    # ---- methodology doc -------------------------------------------------
    cw = "\n".join(f"| `{k}` | {v:.0%} | {d} |" for (k, v), d in zip(
        CONDUCT_WEIGHTS.items(), [
            "Share of resolved complaints where the consumer received **nothing** — no monetary and no non-monetary relief. The most direct measure of whether complaining achieved anything.",
            "Share where the company missed the CFPB response deadline. A hard, unambiguous process failure entirely within the company's control.",
            "Share where the company formally disputes the consumer's account of events. An adversarial-posture signal, and near-independent of the others (ρ ≤ 0.16).",
            "Mean days to route the complaint to the company. Weakest signal — partly CFPB-side — so it carries the least weight.",
        ]))
    ew = "\n".join(f"| `{k}` | {v:.0%} |" for k, v in EXPOSURE_WEIGHTS.items())
    tiers = "\n".join(
        f"| {t} | {n} | {df.loc[scored & (df.risk_tier == t), 'total_complaints'].sum():,} |"
        for t, n in df.loc[scored, "risk_tier"].value_counts().items())

    METHOD_MD.write_text(f"""# Risk score methodology — Stage 6

*Generated by `scripts/06_feature_engineering.py` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.*

## Why there are two scores, not one

A single composite would be misleading here.

`complaints_per_1b_assets` divides by **balance-sheet size**, which is not the
same as **customer count**. A monoline credit-card issuer serves millions of
customers on a small balance sheet; a universal bank holds mortgages and
commercial loans that add assets without adding retail customers. Card issuers
therefore score high on that measure partly by *business model*, not by conduct.

It is also **undefined for roughly half of all complaint volume** — credit
bureaus, NCUA credit unions, loan servicers and fintechs have no FDIC assets. A
single composite would quietly drop half the market.

| Score | Range | Defined for | Measures |
|---|---|---|---|
| `conduct_risk_score` | 0–100 | **Every** company ≥ {MIN_COMPLAINTS} complaints ({scored.sum():,}) | How a company *handles* complaints. Immune to the business-model distortion. **Use this for conduct claims.** |
| `exposure_risk_score` | 0–100 | FDIC-matched depositories ({matched_scored.sum():,}) | Adds complaint frequency per $1B of assets. |

## Conduct risk score

Each component is converted to a **percentile rank within the scored cohort**,
then weighted. A score of 80 means *worse than 80% of peers*.

Percentiles rather than min–max or z-scores because every one of these rates is
heavily right-skewed — a single company at 100% untimely would compress every
other company into the bottom of a min–max scale.

| Component | Weight | What it captures |
|---|---:|---|
{cw}

**A component was removed after checking it.** The first version also included
`explanation_only_rate` at 20%. Measured against `pct_no_relief` it correlates
at **Spearman ρ = 0.954** and differs by a mean of **1.0 percentage points** —
closing with an explanation *is* giving no relief. Together the two carried 55%
of the weight, meaning the score was largely one variable counted twice. It is
still reported as an output column, just not double-counted. All remaining
pairwise correlations are ≤ 0.33.

## Exposure risk score

| Component | Weight |
|---|---:|
{ew}

The conduct component is **re-ranked within the matched cohort** so both inputs
share the same peer basis rather than mixing a whole-market percentile with a
depositories-only one.

## Minimum volume floor

Only companies with **≥ {MIN_COMPLAINTS} complaints** are scored
({scored.sum():,} companies, {100*df.loc[scored,'total_complaints'].sum()/df.total_complaints.sum():.1f}%
of all complaint volume). A 0% relief rate on 3 complaints is noise, and without
a floor the top of the table fills with companies whose rates are arithmetic
accidents. Companies below the floor are **kept in the output with NULL scores**
so nothing disappears silently.

## Risk tiers

| Tier | Companies | Complaints |
|---|---:|---:|
{tiers}

## Honest limitations

1. **Weights are a judgement, not a derivation.** They encode what a compliance
   team typically prioritises. They are stated here so a reader can disagree with
   the weighting rather than reverse-engineer it. The underlying rates are all
   in the output, so any reader can re-weight.
2. **Percentile scores are relative, not absolute.** A "Low" tier company is
   better than its peers, not necessarily good.
3. **Complaint counts reflect propensity to complain**, which varies by product
   and demographics, not only by how badly a company behaves.
4. **Jan-2025 contains a mass-filing event** (see `notebooks/eda.ipynb` §7).
   Affected companies' volumes are inflated; the size-adjusted ranking was
   verified stable without it, but the raw counts still include it.
""", encoding="utf-8")
    log(f"wrote {METHOD_MD.relative_to(PROJECT_ROOT)}")
    eng.dispose()
    print("\nSTAGE 6 COMPLETE")


if __name__ == "__main__":
    main()
