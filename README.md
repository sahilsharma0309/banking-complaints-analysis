# US Banking Consumer Complaints — Risk & Resolution Analysis

End-to-end analytics project on the **CFPB Consumer Complaint Database**: Python
ingestion → pandas cleaning → external enrichment → PostgreSQL warehouse → SQL
analysis → statistical testing → Tableau dashboard.

> **Status:** in progress — built stage by stage. See [Project stages](#project-stages).

---

## Problem statement

Complaint *volume* is a misleading risk signal. The biggest banks naturally
generate the most complaints because they have the most customers. The question
that actually matters to a risk or compliance team is what's left after you
control for size.

**Primary business question**

> Which US financial companies and products generate the most consumer risk, and
> — after adjusting for company size — which companies actually resolve
> complaints *worst* (lowest monetary-relief rate / highest untimely-response
> rate)?

Supporting questions:

1. How has complaint volume trended by product since 2023, and which products are accelerating?
2. Which companies look safe on raw volume but are outliers once normalised per $1B of assets?
3. Is complaint outcome (monetary relief vs. no relief) statistically independent of the company handling it?
4. Which issues and states concentrate the most risk?

## Data

| Source | What it gives us | Link |
|---|---|---|
| CFPB Consumer Complaint Database | Complaint-level records: date, product, issue, company, state, company response, timeliness, disputes | [API docs](https://cfpb.github.io/api/ccdb/) · [Search UI](https://www.consumerfinance.gov/data-research/consumer-complaints/) |
| FDIC BankFind Suite API | Insured institution total assets — the denominator for size-adjusted risk | [banks.data.fdic.gov](https://banks.data.fdic.gov/docs/) |
| FRED (optional) | Unemployment rate, CPI — macro context for complaint volume | [fred.stlouisfed.org](https://fred.stlouisfed.org/) |

**Scope:** complaints received **2023-01-01 → 2026-01-01**, pulled via the CFPB
API (not the 5–6 GB bulk download). Raw data is never committed; a 1,000-row
sample lives at [`data/sample_1000.csv`](data/sample_1000.csv) so you can see the
schema without downloading anything.

## Methodology

1. **Acquisition** — paginated API pull using the `search_after` cursor, with retry/backoff.
2. **Cleaning** — date parsing, company-name canonicalisation via an auditable mapping table, explicit dedupe key, per-column missing-value decisions, data-quality flags. Every non-obvious decision is logged in [`reports/cleaning_log.md`](reports/cleaning_log.md).
3. **Enrichment** — fuzzy-match CFPB company names to FDIC institutions (`rapidfuzz`) to attach total assets; match rate and unmatched handling reported honestly.
4. **Warehouse** — typed PostgreSQL tables, bulk-loaded via `COPY`, indexed on company / product / state / date.
5. **Analysis** — SQL with CTEs and window functions (`RANK`, `LAG`), one file per business question in [`sql/`](sql/).
6. **Statistics** — chi-square test of independence on complaint outcome; time-series and correlation analysis.
7. **Presentation** — Tableau connected directly to Postgres views.

### Key cleaning decisions

_Populated in Stage 2 — see [`reports/cleaning_log.md`](reports/cleaning_log.md) for the full log._

### Headline metric

**Size-adjusted risk = complaints per $1B of total assets.** Documented with its
caveats (notably: the FDIC denominator only covers insured depository
institutions, so non-bank lenders and credit bureaus are excluded from this
ranking rather than silently mis-ranked).

## Key findings

_Populated in Stage 8 — see [`reports/insights.md`](reports/insights.md)._

## Dashboard

_Tableau Public link: TBD (Stage 7)._

Build instructions: [`dashboard/TABLEAU_BUILD_GUIDE.md`](dashboard/TABLEAU_BUILD_GUIDE.md)

## How to run

### Prerequisites

- Windows, **Python 3.11** (see note below), PostgreSQL 14+ running locally
- Tableau Desktop (optional — for the dashboard only)

> **Why Python 3.11 and not 3.14?** `pandas`, `scipy`, `psycopg2-binary` and
> `tableauhyperapi` all ship mature prebuilt wheels for 3.11. On 3.14 several of
> them have to compile from source or have no wheel at all, which turns a
> one-command setup into a toolchain problem. Pinning the interpreter is part of
> making this reproducible.

### Setup

```powershell
git clone https://github.com/sahilsharma0309/banking-complaints-analysis.git
cd banking-complaints-analysis

py -3.11 -m venv venv
venv\Scripts\pip install --upgrade pip
venv\Scripts\pip install -r requirements.txt

Copy-Item .env.example .env
# then edit .env and set PGPASSWORD (and PGDATABASE/PGUSER if yours differ)
```

### Pipeline

Scripts are numbered and idempotent — run them in order:

```powershell
venv\Scripts\python scripts\01_download_data.py    # CFPB API -> data/raw/
venv\Scripts\python scripts\02_clean.py            # -> data/processed/complaints_clean.csv
venv\Scripts\python scripts\03_enrich.py           # FDIC assets join
venv\Scripts\python scripts\04_load_postgres.py    # typed tables + indexes + views
```

Then open [`notebooks/eda.ipynb`](notebooks/eda.ipynb) for the exploratory and
statistical analysis, and follow
[`dashboard/TABLEAU_BUILD_GUIDE.md`](dashboard/TABLEAU_BUILD_GUIDE.md) to build
the dashboard.

## Repository layout

```
banking-complaints-project/
├── data/
│   ├── raw/              # CFPB API output — gitignored, never modified
│   ├── processed/        # cleaned + enriched outputs — gitignored
│   └── sample_1000.csv   # committed: 1,000 rows so reviewers see the schema
├── scripts/              # numbered, re-runnable pipeline steps
├── sql/                  # one .sql file per business question
├── notebooks/            # eda.ipynb — trends, chi-square, correlations
├── dashboard/            # Tableau build guide + CSV/hyper backups
├── reports/              # cleaning_log.md, insights.md, figures/
├── requirements.txt
└── .env.example          # copy to .env (gitignored) and fill in
```

## Project stages

| Stage | Deliverable | Status |
|---|---|---|
| 0 | Scaffold, repo, venv, config | ✅ |
| 1 | CFPB API acquisition | ⬜ |
| 2 | Cleaning & wrangling | ⬜ |
| 3 | FDIC / FRED enrichment | ⬜ |
| 4 | PostgreSQL load + SQL analysis | ⬜ |
| 5 | EDA + statistical tests | ⬜ |
| 6 | Feature engineering + risk score | ⬜ |
| 7 | Tableau handoff | ⬜ |
| 8 | Business report | ⬜ |
| 9 | README polish + resume bullets | ⬜ |

## Resume bullets

_Drafted in Stage 9._

---

**Author:** Sahil Vashisth · Data source: [CFPB](https://www.consumerfinance.gov/data-research/consumer-complaints/) (public domain)
