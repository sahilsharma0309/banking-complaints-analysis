"""
Stage 4 -- Load into PostgreSQL and run the SQL analysis.

Reads   data/processed/*.csv  (Stage 2 + Stage 3 outputs)
        .env                  (connection details, gitignored)
Creates database + `cfpb` schema, typed tables, indexes
Runs    sql/*.sql and exports each result to data/processed/query_*.csv

WHY COPY AND NOT to_sql / INSERT
--------------------------------
624,708 rows through row-by-row INSERT (or pandas .to_sql, which batches
INSERTs) takes minutes and floods the WAL. PostgreSQL's COPY streams the CSV
straight into the table in a single statement. psycopg2 exposes it as
copy_expert, so the file never has to be parsed in Python at all.

TYPES ARE DECLARED, NOT INFERRED
--------------------------------
Everything as TEXT would work and would be wrong: date arithmetic, BETWEEN
filters, AVG() and boolean predicates all need real types, and Tableau reads the
column types to decide what is a measure and what is a dimension.

One column needs care: `zip3` is TEXT, never numeric. 46,528 rows have a
leading-zero prefix (`007` = Puerto Rico, `010` = Massachusetts). Reading it as a
number silently turns `007` into `7` and destroys the join to any ZIP reference
data. The CSV itself is fine -- the damage happens on read, so every read here
forces string dtype.

USAGE
-----
    python scripts/04_load_postgres.py              # create, load, index, export
    python scripts/04_load_postgres.py --export-only  # re-run queries only
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from urllib.parse import quote_plus

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql as psql
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROC = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"

load_dotenv(PROJECT_ROOT / ".env")

PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PGDATABASE = os.getenv("PGDATABASE", "banking_complaints")
SCHEMA = "cfpb"

COMPLAINTS_DDL = f"""
CREATE TABLE {SCHEMA}.complaints (
    complaint_id             BIGINT PRIMARY KEY,
    date_received            DATE        NOT NULL,
    date_received_ts         TIMESTAMPTZ NOT NULL,
    date_sent_to_company     DATE,
    year                     SMALLINT    NOT NULL,
    month                    SMALLINT    NOT NULL,
    year_month               CHAR(7)     NOT NULL,
    days_to_company          NUMERIC(10,3),
    product                  TEXT        NOT NULL,
    product_short            TEXT        NOT NULL,
    product_raw              TEXT        NOT NULL,
    sub_product              TEXT,
    issue                    TEXT,
    sub_issue                TEXT,
    company                  TEXT        NOT NULL,
    company_raw              TEXT        NOT NULL,
    company_key              TEXT        NOT NULL,
    state                    TEXT        NOT NULL,
    state_type               TEXT        NOT NULL,
    zip_code                 TEXT,
    zip3                     TEXT,          -- TEXT: leading zeros are real
    tags                     TEXT,
    is_servicemember         BOOLEAN     NOT NULL,
    is_older_american        BOOLEAN     NOT NULL,
    submitted_via            TEXT,
    company_response         TEXT,
    company_public_response  TEXT,
    timely                   TEXT,
    has_narrative            BOOLEAN     NOT NULL,
    is_resolved              BOOLEAN     NOT NULL,
    got_monetary_relief      BOOLEAN     NOT NULL,
    got_any_relief           BOOLEAN     NOT NULL,
    closed_explanation_only  BOOLEAN     NOT NULL,
    is_untimely              BOOLEAN     NOT NULL,
    company_disputes_facts   BOOLEAN     NOT NULL,
    dq_state_missing         BOOLEAN     NOT NULL,
    dq_zip_masked            BOOLEAN     NOT NULL,
    dq_sub_issue_missing     BOOLEAN     NOT NULL,
    dq_response_in_progress  BOOLEAN     NOT NULL,
    dq_long_routing_lag      BOOLEAN     NOT NULL,
    dq_partial_period        BOOLEAN     NOT NULL,
    dq_legacy_product_label  BOOLEAN     NOT NULL,
    in_trend_window          BOOLEAN     NOT NULL
);
"""

COMPANY_ENRICHED_DDL = f"""
CREATE TABLE {SCHEMA}.company_enriched (
    company                     TEXT PRIMARY KEY,
    total_complaints            INTEGER NOT NULL,
    complaints_in_trend_window  INTEGER NOT NULL,
    avg_days_to_company         NUMERIC(10,3),
    resolved_complaints         INTEGER,
    monetary_relief_n           INTEGER,
    untimely_n                  INTEGER,
    monetary_relief_rate        NUMERIC(8,3),
    untimely_rate               NUMERIC(8,3),
    matched                     BOOLEAN,
    fdic_name                   TEXT,
    group_key                   TEXT,
    total_assets_b              NUMERIC(14,3),
    n_charters                  SMALLINT,
    match_score                 NUMERIC(5,1),
    match_method                TEXT,
    complaints_per_1b_assets    NUMERIC(14,3)
);
"""

FDIC_HC_DDL = f"""
CREATE TABLE {SCHEMA}.fdic_holding_companies (
    group_key                 TEXT PRIMARY KEY,
    group_name                TEXT NOT NULL,
    total_assets_k            NUMERIC(20,2),
    n_charters                SMALLINT,
    largest_charter           TEXT,
    largest_charter_assets_k  NUMERIC(20,2),
    primary_cert              TEXT,
    state                     TEXT,
    has_holding_company       BOOLEAN,
    total_assets_b            NUMERIC(14,3),
    assets_understated_pct    NUMERIC(8,2)
);
"""

COMPANY_MAP_DDL = f"""
CREATE TABLE {SCHEMA}.company_name_map (
    company_raw       TEXT NOT NULL,
    company_clean     TEXT NOT NULL,
    company_key       TEXT NOT NULL,
    n_complaints      INTEGER NOT NULL,
    required_collapse BOOLEAN NOT NULL
);
"""

INDEXES = [
    f"CREATE INDEX idx_complaints_company    ON {SCHEMA}.complaints (company)",
    f"CREATE INDEX idx_complaints_product    ON {SCHEMA}.complaints (product)",
    f"CREATE INDEX idx_complaints_state      ON {SCHEMA}.complaints (state)",
    f"CREATE INDEX idx_complaints_date       ON {SCHEMA}.complaints (date_received)",
    f"CREATE INDEX idx_complaints_year_month ON {SCHEMA}.complaints (year_month)",
    f"CREATE INDEX idx_complaints_company_key ON {SCHEMA}.complaints (company_key)",
    # Composite: nearly every rate query filters is_resolved then groups by
    # company, and most bound to the trend window.
    f"""CREATE INDEX idx_complaints_rate_cover ON {SCHEMA}.complaints
        (company, is_resolved, in_trend_window)""",
    f"""CREATE INDEX idx_complaints_product_month ON {SCHEMA}.complaints
        (product, year_month)""",
    f"CREATE INDEX idx_company_enriched_matched ON {SCHEMA}.company_enriched (matched)",
]

TABLES = [
    ("complaints", COMPLAINTS_DDL, PROC / "complaints_clean.csv"),
    ("company_enriched", COMPANY_ENRICHED_DDL, PROC / "company_enriched.csv"),
    ("fdic_holding_companies", FDIC_HC_DDL, PROC / "fdic_holding_companies.csv"),
    ("company_name_map", COMPANY_MAP_DDL, PROC / "company_name_map.csv"),
]


def log(m: str) -> None:
    print(f"  {m}", flush=True)


def banner(m: str) -> None:
    print(f"\n{'=' * 74}\n{m}\n{'=' * 74}", flush=True)


def connect(dbname: str, autocommit: bool = False):
    conn = psycopg2.connect(host=PGHOST, port=PGPORT, user=PGUSER,
                            password=PGPASSWORD, dbname=dbname)
    conn.autocommit = autocommit
    return conn


def ensure_database() -> None:
    # NOTE: no `with connect(...)` here. psycopg2's connection context manager
    # wraps the block in a transaction, and CREATE DATABASE cannot run inside
    # one ("CREATE DATABASE cannot run inside a transaction block"). The
    # connection is managed manually so autocommit genuinely applies.
    conn = connect("postgres", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PGDATABASE,))
            if cur.fetchone():
                log(f"database '{PGDATABASE}' already exists")
            else:
                cur.execute(psql.SQL("CREATE DATABASE {}").format(
                    psql.Identifier(PGDATABASE)))
                log(f"created database '{PGDATABASE}'")
    finally:
        conn.close()


def load_table(conn, name: str, ddl: str, csv_path: Path) -> int:
    if not csv_path.exists():
        sys.exit(f"missing {csv_path} -- run the earlier stages first")

    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{name} CASCADE")
        cur.execute(ddl)

        # Column order must match the CSV header exactly.
        header = pd.read_csv(csv_path, nrows=0).columns.tolist()
        cols = ", ".join(f'"{c}"' for c in header)
        copy_sql = (f"COPY {SCHEMA}.{name} ({cols}) FROM STDIN "
                    f"WITH (FORMAT csv, HEADER true, NULL '')")

        t0 = time.time()
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            cur.copy_expert(copy_sql, fh)
        cur.execute(f"SELECT count(*) FROM {SCHEMA}.{name}")
        n = cur.fetchone()[0]
    conn.commit()
    mb = csv_path.stat().st_size / 1e6
    dt = time.time() - t0
    log(f"{name:<24} {n:>9,} rows  {mb:>7.1f} MB  in {dt:5.1f}s "
        f"({n/dt:,.0f} rows/s)")
    return n


def run_sql_exports() -> bool:
    """Run every sql/*.sql and export its result. Returns False if any failed."""
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        log("no .sql files found in sql/ -- nothing to export")
        return True

    # pandas warns (correctly) that it only supports SQLAlchemy connectables,
    # so the exports go through an engine rather than the raw psycopg2 handle.
    engine = create_engine(
        f"postgresql+psycopg2://{quote_plus(PGUSER)}:{quote_plus(PGPASSWORD)}"
        f"@{PGHOST}:{PGPORT}/{PGDATABASE}")

    all_ok = True
    for f in files:
        text = f.read_text(encoding="utf-8")
        # First line comment is the business question; show it for context.
        first = next((ln for ln in text.splitlines() if ln.strip().startswith("--")), "")
        t0 = time.time()
        try:
            with engine.connect() as ec:
                df = pd.read_sql_query(sa_text(text), ec)
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            msg = str(exc).strip().splitlines()
            detail = next((ln for ln in msg if ln.strip() and "BUSINESS" not in ln),
                          msg[0] if msg else "")
            print(f"  ! {f.name} FAILED: {detail[:150]}")
            continue
        out = PROC / f"query_{f.stem}.csv"
        df.to_csv(out, index=False)
        log(f"{f.name:<38} {len(df):>7,} rows -> {out.name}  ({time.time()-t0:.1f}s)")
        if first:
            print(f"      {first.lstrip('- ').strip()[:90]}")
    engine.dispose()
    return all_ok


def main() -> None:
    export_only = "--export-only" in sys.argv

    if not PGPASSWORD:
        sys.exit("PGPASSWORD is empty in .env -- set it and re-run")

    banner("STAGE 4 -- POSTGRESQL LOAD")
    log(f"target: postgresql://{PGUSER}@{PGHOST}:{PGPORT}/{PGDATABASE} "
        f"(schema '{SCHEMA}')")
    ensure_database()

    conn = connect(PGDATABASE)
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    conn.commit()

    if not export_only:
        banner("BULK LOAD (COPY)")
        total = 0
        for name, ddl, path in TABLES:
            total += load_table(conn, name, ddl, path)
        log(f"total rows loaded: {total:,}")

        banner("INDEXES")
        with conn.cursor() as cur:
            for stmt in INDEXES:
                t0 = time.time()
                cur.execute(stmt)
                idx = stmt.split()[2]
                log(f"{idx:<34} {time.time()-t0:5.1f}s")
            cur.execute(f"ANALYZE {SCHEMA}.complaints")
            cur.execute(f"ANALYZE {SCHEMA}.company_enriched")
        conn.commit()
        log("ANALYZE complete (planner statistics refreshed)")

        banner("INTEGRITY CHECKS")
        checks = [
            ("row count == 624,708",
             f"SELECT count(*) = 624708 FROM {SCHEMA}.complaints"),
            ("complaint_id unique",
             f"""SELECT count(*) = count(DISTINCT complaint_id)
                 FROM {SCHEMA}.complaints"""),
            ("zip3 kept leading zeros",
             f"""SELECT count(*) > 40000 FROM {SCHEMA}.complaints
                 WHERE zip3 LIKE '0%'"""),
            ("dates are real DATE type",
             f"""SELECT data_type = 'date' FROM information_schema.columns
                 WHERE table_schema = '{SCHEMA}' AND table_name = 'complaints'
                   AND column_name = 'date_received'"""),
            ("booleans are real BOOLEAN type",
             f"""SELECT data_type = 'boolean' FROM information_schema.columns
                 WHERE table_schema = '{SCHEMA}' AND table_name = 'complaints'
                   AND column_name = 'got_monetary_relief'"""),
            ("no complaint dated outside the window",
             f"""SELECT count(*) = 0 FROM {SCHEMA}.complaints
                 WHERE date_received < DATE '2023-01-01'
                    OR date_received > DATE '2026-01-01'"""),
            ("every company in complaints exists in company_enriched",
             f"""SELECT count(*) = 0 FROM (
                   SELECT DISTINCT c.company FROM {SCHEMA}.complaints c
                   LEFT JOIN {SCHEMA}.company_enriched e USING (company)
                   WHERE e.company IS NULL) t"""),
        ]
        ok = True
        with conn.cursor() as cur:
            for label, q in checks:
                cur.execute(q)
                passed = bool(cur.fetchone()[0])
                ok &= passed
                print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        if not ok:
            sys.exit("integrity checks failed -- not proceeding to exports")

    banner("RUNNING sql/ QUERIES AND EXPORTING")
    exports_ok = run_sql_exports()

    banner("DONE")
    with conn.cursor() as cur:
        # c.relname must be qualified: pg_class and pg_stat_user_tables both
        # expose a relname column.
        cur.execute(f"""
            SELECT c.relname,
                   s.n_live_tup,
                   pg_size_pretty(pg_total_relation_size(c.oid))
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = '{SCHEMA}' AND c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC""")
        print(f"  {'table':<26}{'rows':>12}  size")
        for rel, rows, size in cur.fetchall():
            print(f"  {rel:<26}{rows:>12,}  {size}")
    conn.close()
    if not exports_ok:
        sys.exit("\nSTAGE 4 INCOMPLETE -- one or more sql/ queries failed above")
    print("\nSTAGE 4 COMPLETE")


if __name__ == "__main__":
    main()
