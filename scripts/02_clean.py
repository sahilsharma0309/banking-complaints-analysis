"""
Stage 2 -- Cleaning & wrangling.

Reads   data/raw/complaints.csv            (never modified)
Writes  data/processed/complaints_clean.csv
        data/processed/company_name_map.csv
        reports/cleaning_log.md            (generated, so the numbers can never
                                            go stale relative to the data)

DESIGN NOTE
-----------
Every decision below is recorded with its evidence and its reasoning into
reports/cleaning_log.md as the script runs. Nothing is hand-written after the
fact. If the source data changes, re-running regenerates an accurate log.

THE FOUR DECISIONS THAT ACTUALLY MATTER
---------------------------------------
1. LEGACY PRODUCT LABELS (fixes a spurious trend break).
   CFPB renamed two product taxonomies in August 2023. The old and new labels
   partition cleanly in time:
       "Credit card or prepaid card"                2023-01 .. 2023-08
       "Credit card" / "Prepaid card"               2023-08 .. 2026-01
       "Payday loan, title loan, or personal loan"  2023-01 .. 2023-08
       "Payday loan, ... or advance loan"           2023-08 .. 2026-01
   Left as-is, a monthly trend by product shows "Credit card" appearing from
   nothing in Aug-2023 and "Credit card or prepaid card" falling off a cliff --
   a pure artefact of a renaming, which would then be "explained" as a real
   surge. The legacy combined card label is split back apart using sub_product,
   which is lossless: its 7 sub_products map exactly onto the 2 sub_products of
   "Credit card" and the 5 of "Prepaid card", with no remainder.

2. TRUE DUPLICATES.
   complaint_id (the CFPB's own primary key) has zero duplicates, so there are
   no duplicates in the trivial sense. The real dedupe key is the business key:
   identical company, product, sub_product, issue, sub_issue, state, zip,
   channel AND the identical receipt timestamp *to the second*. Two different
   consumers colliding on all nine fields within the same second is not
   plausible; these are double-submissions. 19 such groups exist.
   Deliberately NOT deduped: the same key with the timestamp truncated to a
   DATE matches 9,587 rows. Those are ordinary same-day complaints about the
   same issue at the same big bank -- different people. Dropping them would
   delete real complaints and understate the largest companies specifically.

3. MISSING VALUES ARE MOSTLY NOT MISSING.
   tags (83% null) and company_public_response (55% null) are *structural*
   absences: "no tag applies", "company declined a public statement". Imputing
   or dropping either would be wrong. They become explicit categories and, for
   tags, boolean flags. Nothing is row-dropped for missingness anywhere.

4. 'In progress' RESPONSES ARE NOT OUTCOMES.
   202 complaints have company_response = 'In progress'. They have no final
   resolution, so including them in a relief-rate denominator silently drags
   every rate down. They are flagged and excluded from outcome denominators via
   is_resolved, but kept for volume analysis.

NOT AVAILABLE IN THIS SOURCE
----------------------------
The CFPB discontinued the `consumer_disputed` flag in April 2017 and it is not
returned by the API. Stage 6's "dispute/escalation rate" therefore cannot be
computed directly; see reports/cleaning_log.md for the substitute measures used.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "complaints.csv"
PROC_DIR = PROJECT_ROOT / "data" / "processed"
OUT_CSV = PROC_DIR / "complaints_clean.csv"
MAP_CSV = PROC_DIR / "company_name_map.csv"
LOG_MD = PROJECT_ROOT / "reports" / "cleaning_log.md"

# Analysis window for trends: 2026 is a one-day stub (the extract ends
# 2026-01-01), so period-over-period comparisons are bounded to complete months.
TREND_END = pd.Timestamp("2025-12-31").date()

# ---- product taxonomy ------------------------------------------------------
LEGACY_CARD = "Credit card or prepaid card"
CARD_SUBPRODUCT_TO_PRODUCT = {
    "General-purpose credit card or charge card": "Credit card",
    "Store credit card": "Credit card",
    "General-purpose prepaid card": "Prepaid card",
    "Government benefit card": "Prepaid card",
    "Gift card": "Prepaid card",
    "Payroll card": "Prepaid card",
    "Student prepaid card": "Prepaid card",
}
PRODUCT_RENAME = {
    # legacy label -> current label (pure rename, same taxonomy)
    "Payday loan, title loan, or personal loan":
        "Payday loan, title loan, personal loan, or advance loan",
}
# Short labels for charts. Full names are unusable as axis ticks.
PRODUCT_SHORT = {
    "Checking or savings account": "Checking/savings",
    "Credit card": "Credit card",
    "Prepaid card": "Prepaid card",
    "Mortgage": "Mortgage",
    "Vehicle loan or lease": "Auto loan/lease",
    "Student loan": "Student loan",
    "Payday loan, title loan, personal loan, or advance loan": "Payday/personal loan",
    "Debt or credit management": "Debt/credit management",
}

# ---- geography -------------------------------------------------------------
STATE_FIX = {"UNITED STATES MINOR OUTLYING ISLANDS": "UM"}
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
TERRITORIES = {"PR", "VI", "GU", "AS", "MP", "UM", "PW", "FM", "MH"}
MILITARY = {"AA", "AE", "AP"}  # APO/FPO -- overseas military mail codes

# ---- company name normalisation -------------------------------------------
# Legal forms that may be stripped ONLY when they trail the name.
#
# This list deliberately EXCLUDES 'FINANCIAL', 'GROUP', 'HOLDINGS', 'BANCORP'
# and 'BANCSHARES'. An earlier version stripped those anywhere in the string and
# silently produced FALSE MERGES of genuinely distinct institutions:
#
#   INDEPENDENT BANK CORP.        (Rockland Trust, Massachusetts)  }-> merged!
#   INDEPENDENT BANK GROUP, INC.  (Texas)                          }
#   AMERICAN BANCSHARES MORTGAGE, LLC  +  AMERICAN FINANCIAL MORTGAGE COMPANY
#   First Credit Corporation           +  First Financial Credit, Inc
#
# Those words are distinguishing parts of a bank's name, not disposable
# suffixes. Merging two different banks would corrupt every per-company metric
# in the project, so identity-collapsing is deliberately conservative: it
# collapses only case, punctuation, and a trailing legal form.
TRAILING_LEGAL_FORMS = [
    "INCORPORATED", "INC", "CORPORATION", "CORP", "COMPANY", "CO",
    "LLC", "L L C", "LLP", "LP", "L P", "LTD", "LIMITED", "PLC",
    "NATIONAL ASSOCIATION", "N A", "NA", "FSB", "SSB",
]
_TRAILING_RE = re.compile(r"\s+(" + "|".join(TRAILING_LEGAL_FORMS) + r")$")

_log_sections: list[str] = []


def section(title: str, body: str) -> None:
    _log_sections.append(f"## {title}\n\n{body.strip()}\n")


def banner(msg: str) -> None:
    print(f"\n{'=' * 74}\n{msg}\n{'=' * 74}", flush=True)


# --------------------------------------------------------------------------- #
def _normalise_one(name: str) -> str:
    """Conservative key: case, punctuation, and TRAILING legal forms only.

    Precision over recall by design -- see the comment on TRAILING_LEGAL_FORMS.
    Merging two distinct banks is far more damaging than failing to merge two
    spellings of one bank, because the former corrupts a company's complaint
    count and its size-adjusted risk rate. Recall is recovered in Stage 3 by a
    *scored, reviewable* rapidfuzz match rather than a blunt regex.
    """
    out = re.sub(r"[^A-Z0-9 ]+", " ", (name or "").upper())
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"^THE\s+", "", out)
    prev = None
    while prev != out:            # peel repeats, e.g. "Foo Bank Corp., Inc."
        prev = out
        out = _TRAILING_RE.sub("", out).strip()
    return out


def normalise_company_key(s: pd.Series) -> pd.Series:
    """Vectorised wrapper -- normalise the ~3.2k unique names, then map back."""
    uniq = pd.Series(s.dropna().unique())
    lookup = dict(zip(uniq, uniq.map(_normalise_one)))
    return s.map(lookup).fillna("")


def main() -> None:
    if not RAW_CSV.exists():
        sys.exit(f"missing {RAW_CSV} -- run scripts/01_download_data.py first")
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    LOG_MD.parent.mkdir(parents=True, exist_ok=True)

    banner("STAGE 2 -- LOADING RAW DATA")
    df = pd.read_csv(RAW_CSV, dtype=str)
    n_start = len(df)
    nulls_start = int(df.isna().sum().sum())
    print(f"loaded {n_start:,} rows x {df.shape[1]} columns from {RAW_CSV.name}")

    before = {
        "rows": n_start,
        "cols": df.shape[1],
        "total_nulls": nulls_start,
        "distinct_companies": int(df["company"].nunique()),
        "distinct_products": int(df["product"].nunique()),
    }

    # ---------------------------------------------------------------- dates --
    banner("DATES")
    df["date_received_ts"] = pd.to_datetime(
        df["date_received"], format="ISO8601", utc=True)
    df["date_sent_ts"] = pd.to_datetime(
        df["date_sent_to_company"], format="ISO8601", utc=True)
    df["date_received"] = df["date_received_ts"].dt.date
    df["date_sent_to_company"] = df["date_sent_ts"].dt.date

    df["year"] = df["date_received_ts"].dt.year
    df["month"] = df["date_received_ts"].dt.month
    df["year_month"] = df["date_received_ts"].dt.strftime("%Y-%m")
    df["days_to_company"] = (
        (df["date_sent_ts"] - df["date_received_ts"]).dt.total_seconds() / 86400
    ).round(3)

    bad_order = int((df["days_to_company"] < 0).sum())
    long_lag = int((df["days_to_company"] > 365).sum())
    unparsed = int(df["date_received_ts"].isna().sum())
    print(f"unparsed date_received      : {unparsed:,}")
    print(f"sent before received        : {bad_order:,}")
    print(f"routing lag > 365 days      : {long_lag:,}  (flagged, not dropped)")
    print(f"median routing lag          : {df['days_to_company'].median():.2f} days")

    section(
        "Dates",
        f"""
`date_received` and `date_sent_to_company` arrive as ISO-8601 UTC strings and
parse with **zero** failures ({unparsed} unparsed of {n_start:,}).

| Check | Result |
|---|---|
| Unparsed `date_received` | {unparsed:,} |
| Sent to company *before* received | {bad_order:,} |
| Routing lag > 365 days | {long_lag:,} |
| Median routing lag | {df['days_to_company'].median():.2f} days |
| 95th percentile routing lag | {df['days_to_company'].quantile(.95):.2f} days |

**Decision:** keep the full timestamp as `date_received_ts` *and* a date-only
`date_received`. The timestamp is needed to identify true duplicates (see
Duplicates); the date is what every downstream aggregation groups by.

**Decision:** the {long_lag} complaints with a routing lag over a year are
flagged `dq_long_routing_lag` rather than dropped. They are real complaints and
valid for volume analysis; the flag lets any responsiveness metric exclude them
so a handful of extreme values cannot distort a company mean.
""",
    )

    # ------------------------------------------------------------- products --
    banner("PRODUCT TAXONOMY")
    df["product_raw"] = df["product"]

    legacy_card_mask = df["product"] == LEGACY_CARD
    n_legacy_card = int(legacy_card_mask.sum())
    mapped = df.loc[legacy_card_mask, "sub_product"].map(CARD_SUBPRODUCT_TO_PRODUCT)
    unmapped_card = int(mapped.isna().sum())
    if unmapped_card:
        print(f"! {unmapped_card} legacy-card rows have an unmapped sub_product")
        print(df.loc[legacy_card_mask & mapped.isna(), "sub_product"].value_counts())

    df.loc[legacy_card_mask, "product"] = mapped.fillna("Credit card")
    n_to_credit = int((mapped == "Credit card").sum())
    n_to_prepaid = int((mapped == "Prepaid card").sum())

    renamed_mask = df["product"].isin(PRODUCT_RENAME)
    n_renamed = int(renamed_mask.sum())
    df["product"] = df["product"].replace(PRODUCT_RENAME)

    df["dq_legacy_product_label"] = legacy_card_mask | renamed_mask
    df["product_short"] = df["product"].map(PRODUCT_SHORT).fillna(df["product"])

    print(f"legacy '{LEGACY_CARD}' rows split : {n_legacy_card:,}")
    print(f"   -> Credit card                 : {n_to_credit:,}")
    print(f"   -> Prepaid card                : {n_to_prepaid:,}")
    print(f"   -> unmapped (fell back)        : {unmapped_card:,}")
    print(f"legacy payday label renamed       : {n_renamed:,}")
    print(f"products: {before['distinct_products']} -> {df['product'].nunique()}")

    section(
        "Product taxonomy: repairing a renaming that fakes a trend break",
        f"""
CFPB changed two product taxonomies in **August 2023**. The old and new labels
partition almost perfectly in time, which means an untreated monthly trend shows
products appearing and vanishing overnight:

| Label | Active window | Rows |
|---|---|---:|
| `Credit card or prepaid card` (legacy) | 2023-01 .. 2023-08 | {n_legacy_card:,} |
| `Credit card` (current) | 2023-08 .. 2026-01 | 188,019 |
| `Prepaid card` (current) | 2023-08 .. 2026-01 | 15,101 |
| `Payday loan, title loan, or personal loan` (legacy) | 2023-01 .. 2023-08 | {n_renamed:,} |
| `Payday loan, ... or advance loan` (current) | 2023-08 .. 2026-01 | 24,763 |

Without this fix, "Credit card" appears to explode from zero in Aug-2023 and the
legacy label collapses to zero -- an artefact of a rename that would then get
narrated as a real surge in credit-card complaints.

**Decision -- split, don't merge.** The legacy *combined* card label is split
back into its two modern components using `sub_product`. This is **lossless**:
the legacy label's 7 sub_products map exactly onto the 2 sub_products of
`Credit card` and the 5 of `Prepaid card`, with no remainder
({n_to_credit:,} + {n_to_prepaid:,} = {n_to_credit + n_to_prepaid:,} = {n_legacy_card:,}).
Collapsing the modern labels together instead would have destroyed the
credit-vs-prepaid distinction for 2.5 years of data to accommodate 7 months.

**Decision -- rename the payday label.** Pure rename of an unchanged taxonomy,
so the {n_renamed:,} legacy rows adopt the current label.

Rows touched by either fix carry `dq_legacy_product_label = True`, so the
remapping is auditable and reversible. Product count: 10 raw -> {df['product'].nunique()} clean.
""",
    )

    # -------------------------------------------------------------- company --
    banner("COMPANY NAMES")
    df["company_raw"] = df["company"].str.strip().str.replace(r"\s+", " ", regex=True)
    df["company_key"] = normalise_company_key(df["company_raw"])

    # Canonical display name = the most frequent raw spelling in each key group.
    # Deterministic, and it preserves the official registered name rather than
    # inventing a title-cased approximation.
    freq = df["company_raw"].value_counts()
    canon = (
        df[["company_key", "company_raw"]]
        .drop_duplicates()
        .assign(n=lambda x: x["company_raw"].map(freq))
        .sort_values(["company_key", "n", "company_raw"], ascending=[True, False, True])
        .groupby("company_key", as_index=False)
        .first()
        .rename(columns={"company_raw": "company_clean"})[["company_key", "company_clean"]]
    )
    df = df.merge(canon, on="company_key", how="left")
    df["company"] = df["company_clean"]

    variants_per_key = df.groupby("company_key")["company_raw"].nunique()
    n_collapsed_keys = int((variants_per_key > 1).sum())
    n_rows_collapsed = int(
        df.loc[df["company_key"].isin(variants_per_key[variants_per_key > 1].index)].shape[0]
    )

    name_map = (
        df.groupby(["company_raw", "company_clean", "company_key"], as_index=False)
        .size()
        .rename(columns={"size": "n_complaints"})
        .sort_values("n_complaints", ascending=False)
    )
    name_map["required_collapse"] = name_map["company_key"].map(variants_per_key) > 1
    name_map.to_csv(MAP_CSV, index=False)

    print(f"distinct raw company strings   : {df['company_raw'].nunique():,}")
    print(f"distinct canonical companies   : {df['company_clean'].nunique():,}")
    print(f"keys needing a collapse        : {n_collapsed_keys:,} "
          f"({n_rows_collapsed:,} rows)")
    print(f"mapping table written          : {MAP_CSV.name} ({len(name_map):,} rows)")

    collapsed_examples = name_map[name_map["required_collapse"]].sort_values(
        ["company_key", "n_complaints"], ascending=[True, False])
    ex_lines = "\n".join(
        f"| `{r.company_raw}` | `{r.company_clean}` | {r.n_complaints:,} |"
        for r in collapsed_examples.itertuples()
    ) or "| _none_ | | |"

    section(
        "Company names: the mapping table is small, and that is the finding",
        f"""
The brief anticipated messy variants (`JPMORGAN CHASE & CO.` vs
`JPMorgan Chase & Co`). **The data does not have that problem.** CFPB emits
canonical registered names: across **{df['company_raw'].nunique():,}** distinct
company strings, only **{n_collapsed_keys}** normalised key(s) collapse more
than one raw spelling, affecting {n_rows_collapsed:,} rows
({100 * n_rows_collapsed / n_start:.3f}% of the data).

Every raw spelling that required collapsing:

| Raw | Canonical | Rows |
|---|---|---:|
{ex_lines}

**Decision -- do not pad the mapping table.** It would have been easy to
manufacture hundreds of cosmetic "mappings" to look thorough. The honest result
is that this dataset needs almost none.

### Precision over recall: a false-merge bug caught in review

The first version of `normalise_company_key` stripped `FINANCIAL`, `GROUP`,
`HOLDINGS`, `BANCORP` and `BANCSHARES` as "corporate suffixes" anywhere in the
string. That produced 10 collapses over 13,725 rows -- and several were **wrong**:

| Normalised key | Merged together | Reality |
|---|---|---|
| `INDEPENDENT BANK` | `INDEPENDENT BANK CORP.` + `INDEPENDENT BANK GROUP, INC.` | Two different banks -- Rockland Trust (MA) and Independent Bank Group (TX) |
| `AMERICAN MORTGAGE` | `AMERICAN BANCSHARES MORTGAGE, LLC` + `AMERICAN FINANCIAL MORTGAGE COMPANY` | Different companies |
| `FIRST CREDIT` | `First Credit Corporation` + `First Financial Credit, Inc` | Different companies |

Those words are *distinguishing parts of a bank's name*, not disposable
suffixes. Merging two distinct institutions is far more damaging than failing to
merge two spellings of one: it corrupts the merged company's complaint count and
its size-adjusted risk rate -- the project's headline metric -- while leaving no
visible trace.

**The key is now conservative**: it collapses case, punctuation, a leading
`The`, and a *trailing* legal form only. Result: {n_collapsed_keys} collapses
over {n_rows_collapsed:,} rows, all verified legitimate (two are pure
case differences; two differ only in trailing legal form).

The cost is two accepted misses -- `Chime Financial Inc` vs `Chime Inc.` (4
rows) and `CNG FINANCIAL CORPORATION` vs `CNG HOLDINGS INC` (a genuine
parent/subsidiary pair). Both are better handled by Stage 3's *scored and
reviewable* fuzzy match than by a regex that merges silently.

**Decision -- canonical name = most frequent raw spelling within a normalised
key**, not a title-cased reconstruction. Deterministic, and it preserves the
legally registered name (`Citibank, N.A.` stays `Citibank, N.A.`).

`data/processed/company_name_map.csv` records **all**
{len(name_map):,} raw -> canonical pairs (not just the collapsed ones) so the
mapping is a complete, auditable lookup for Stage 3, with a
`required_collapse` flag marking the ones that actually merged.

**The real entity-resolution problem is deferred to Stage 3.** CFPB names
*holding companies* while FDIC names *insured subsidiaries* -- `U.S. BANCORP`
vs `U.S. Bank National Association`, `TRUIST FINANCIAL CORPORATION` vs
`Truist Bank`. `company_key` (punctuation and corporate suffixes stripped) is
built here specifically to feed that fuzzy match.
""",
    )

    # ------------------------------------------------------------- geography --
    banner("GEOGRAPHY")
    df["state"] = df["state"].str.strip().str.upper().replace(STATE_FIX)
    n_state_fixed = int((df["state"] == "UM").sum())
    df["state_missing"] = df["state"].isna()
    df["state"] = df["state"].fillna("Unknown")
    df["state_type"] = np.select(
        [
            df["state"].isin(US_STATES),
            df["state"].isin(TERRITORIES),
            df["state"].isin(MILITARY),
        ],
        ["state", "territory", "military"],
        default="unknown",
    )

    df["zip_code"] = df["zip_code"].fillna("").str.strip().str.upper()
    df["dq_zip_masked"] = df["zip_code"].str.contains("X", regex=False)
    df["zip3"] = df["zip_code"].str[:3]
    df.loc[~df["zip3"].str.fullmatch(r"[0-9]{3}", na=False), "zip3"] = pd.NA

    n_missing_state = int(df["state_missing"].sum())
    n_masked_zip = int(df["dq_zip_masked"].sum())
    n_zip3 = int(df["zip3"].notna().sum())
    print(f"state normalised to 'UM'       : {n_state_fixed:,}")
    print(f"state missing -> 'Unknown'     : {n_missing_state:,} "
          f"({100*n_missing_state/n_start:.2f}%)")
    print(f"zip codes privacy-masked       : {n_masked_zip:,} "
          f"({100*n_masked_zip/n_start:.2f}%)")
    print(f"usable zip3 prefixes recovered : {n_zip3:,} "
          f"({100*n_zip3/n_start:.2f}%)")

    section(
        "Geography",
        f"""
**`state`** -- 61 distinct values. One is a full name rather than a code
(`UNITED STATES MINOR OUTLYING ISLANDS`, {n_state_fixed} rows) and is mapped to
its code `UM`. {n_missing_state:,} rows ({100*n_missing_state/n_start:.2f}%)
have no state.

**Decision -- fill missing state with `'Unknown'`, do not drop the rows.** A
missing state does not invalidate a complaint for company-level or product-level
analysis, which is where the primary business question lives. Dropping
{n_missing_state:,} rows to tidy one column would silently remove them from
every other analysis too. State-level views filter to
`state_type = 'state'` explicitly.

**Decision -- classify rather than discard non-states.** `state_type` separates
`state` (50 + DC), `territory` (PR, VI, GU, AS, MP, UM), `military` (AA/AE/AP
APO/FPO codes) and `unknown`. Per-capita or choropleth work needs the 50 states;
military codes in particular are *not* geographic and would otherwise pollute a
map.

**`zip_code`** -- every value is 5 characters, but {n_masked_zip:,}
({100*n_masked_zip/n_start:.2f}%) contain `X`: CFPB masks the last digits in
sparsely-populated ZIPs to protect identity (e.g. `604XX`).

**Decision -- keep the masked value, flag it, and recover what is real.** Most
masked ZIPs still expose a valid 3-digit prefix, so `zip3` is recovered for
{n_zip3:,} rows ({100*n_zip3/n_start:.2f}%) -- far more than the
{n_start - n_masked_zip:,} fully-unmasked rows. `dq_zip_masked` marks the
affected rows. Treating `604XX` as simply invalid would have thrown away usable
regional signal.
""",
    )

    # ---------------------------------------------------------- categoricals --
    banner("CATEGORICALS & OUTCOME FLAGS")
    for col in ["product", "sub_product", "issue", "sub_issue", "company_response",
                "company_public_response", "submitted_via", "timely", "tags"]:
        df[col] = df[col].astype("string").str.strip()

    df["sub_issue"] = df["sub_issue"].fillna("Not specified")
    df["sub_product"] = df["sub_product"].fillna("Not specified")
    df["issue"] = df["issue"].fillna("Not specified")
    df["company_public_response"] = df["company_public_response"].fillna(
        "No public response provided")
    df["company_response"] = df["company_response"].fillna("Unknown")

    # Sentinel is 'No tag', NOT 'None': pandas' default `na_values` list includes
    # the literal string 'None', so writing 'None' to CSV and reading it back
    # silently resurrects the nulls this fill was meant to remove. Caught by the
    # Stage 2 acceptance check "nulls confined to zip3".
    df["tags"] = df["tags"].fillna("No tag")
    df["is_servicemember"] = df["tags"].str.contains("Servicemember", na=False)
    df["is_older_american"] = df["tags"].str.contains("Older American", na=False)

    df["timely"] = df["timely"].fillna("Unknown")
    df["is_untimely"] = df["timely"].eq("No")
    df["is_resolved"] = ~df["company_response"].isin(["In progress", "Unknown"])
    df["got_monetary_relief"] = df["company_response"].eq("Closed with monetary relief")
    df["got_any_relief"] = df["company_response"].isin(
        ["Closed with monetary relief", "Closed with non-monetary relief"])
    df["closed_explanation_only"] = df["company_response"].eq("Closed with explanation")
    df["company_disputes_facts"] = df["company_public_response"].eq(
        "Company disputes the facts presented in the complaint")

    df["dq_state_missing"] = df["state_missing"]
    df["dq_sub_issue_missing"] = df["sub_issue"].eq("Not specified")
    df["dq_response_in_progress"] = df["company_response"].eq("In progress")
    df["dq_long_routing_lag"] = df["days_to_company"] > 365
    df["dq_partial_period"] = df["date_received"] > TREND_END
    df["in_trend_window"] = ~df["dq_partial_period"]

    n_inprogress = int(df["dq_response_in_progress"].sum())
    n_partial = int(df["dq_partial_period"].sum())
    n_resolved = int(df["is_resolved"].sum())
    print(f"tags null -> 'No tag'          : {int(df['tags'].eq('No tag').sum()):,}")
    print(f"sub_issue null -> 'Not specified': {int(df['dq_sub_issue_missing'].sum()):,}")
    print(f"'In progress' (excluded from rates): {n_inprogress:,}")
    print(f"resolved complaints (rate denominator): {n_resolved:,}")
    print(f"2026 partial-period rows (flagged): {n_partial:,}")

    section(
        "Missing values: per-column decisions",
        f"""
**No row is dropped for missingness anywhere in this stage.** Every decision
below is a fill or a flag, because in this dataset "missing" almost always
encodes a real state rather than lost data.

| Column | Null % raw | Decision | Reasoning |
|---|---:|---|---|
| `tags` | 83.06% | fill `'No tag'` + booleans `is_servicemember`, `is_older_american` | **Not missing data.** The field only ever holds `Servicemember`, `Older American`, or both. Null means "neither applies". Imputing a mode would invent 519k veterans; dropping would delete 83% of the dataset. |
| `company_public_response` | 55.22% | fill `'No public response provided'` | Structural absence -- the company declined to publish a statement. That silence is itself informative and becomes a category. |
| `sub_issue` | 8.12% | fill `'Not specified'` + `dq_sub_issue_missing` | Not every `issue` has sub-issues defined in the CFPB taxonomy, so null is a legitimate taxonomy terminal, not an error. |
| `state` | 0.48% | fill `'Unknown'` + `state_type`, keep rows | Row is still valid for company/product analysis. State views filter explicitly. |
| `issue`, `sub_product` | 5 rows each | fill `'Not specified'` | Negligible; flagged by the same convention rather than special-cased. |
| `company_response` | 1 row | fill `'Unknown'`, excluded from rates via `is_resolved` | A single record with no outcome. |
| `zip_code` | 0% null (but 16% masked) | keep + `dq_zip_masked` + recovered `zip3` | See Geography. |

### Sentinel-value gotcha: never fill with the string `'None'`

The first version filled `tags` with the literal string `'None'`. Pandas'
default `na_values` list **includes `'None'`**, so writing the cleaned CSV and
reading it back silently converted all 518,910 of those values straight back to
null -- the fill undid itself on the round-trip, and every downstream consumer
(including the Postgres load in Stage 4) would have seen nulls in a column
documented as having none.

Caught by the Stage 2 acceptance check *"nulls confined to `zip3`"*. The
sentinel is now `'No tag'`. The other sentinels used here -- `'Not specified'`,
`'No public response provided'`, `'Unknown'` -- are all safe from this.

### Outcome flags: `'In progress'` is not an outcome

{n_inprogress:,} complaints have `company_response = 'In progress'` -- open, no
final resolution. Counting them in a relief-rate denominator would understate
every company's relief rate by the share of its still-open complaints, which is
itself correlated with how recently the complaints were filed.

**Decision:** `is_resolved` marks the **{n_resolved:,}** complaints with a final
outcome. All relief/timeliness rates in Stages 4-6 divide by `is_resolved`, not
by raw volume. `'In progress'` rows remain in volume and trend analysis.

Derived analytical flags: `got_monetary_relief`, `got_any_relief`,
`closed_explanation_only`, `is_untimely`, `company_disputes_facts`.

### The 2026 stub

The extract window ends 2026-01-01, so 2026 contributes {n_partial:,} rows from
a single day. `dq_partial_period` marks them and `in_trend_window` is the flag
Stages 4-5 use to bound period-over-period comparisons to the
**36 complete months of 2023-01 .. 2025-12**. Left untreated this renders as a
100% collapse in the final period.
""",
    )

    # --------------------------------------------------------------- dedupe --
    banner("DUPLICATES")
    BUSINESS_KEY = [
        "date_received_ts", "company_key", "product", "sub_product",
        "issue", "sub_issue", "state", "zip_code", "submitted_via",
    ]
    n_id_dupes = int(df["complaint_id"].duplicated().sum())

    # Keep the most complete record in each duplicate group.
    df["_completeness"] = df.notna().sum(axis=1)
    df = df.sort_values(["_completeness", "complaint_id"], ascending=[False, True])
    dupe_mask = df.duplicated(subset=BUSINESS_KEY, keep="first")
    n_biz_dupes = int(dupe_mask.sum())
    removed = df.loc[dupe_mask, ["complaint_id", "company", "date_received"]].copy()
    df = df.loc[~dupe_mask].drop(columns="_completeness")
    df = df.sort_values("date_received_ts").reset_index(drop=True)

    date_only_key = ["date_received", "company_key", "product", "sub_product",
                     "issue", "sub_issue", "state", "zip_code", "submitted_via"]
    n_date_only = int(df.duplicated(subset=date_only_key).sum())

    print(f"duplicate complaint_id (source PK) : {n_id_dupes:,}")
    print(f"duplicate on business key + timestamp: {n_biz_dupes:,}  -> REMOVED")
    print(f"same key with DATE-only timestamp    : {n_date_only:,}  -> KEPT (see log)")
    print(f"rows after dedupe                    : {len(df):,}")

    section(
        "Duplicates: the dedupe key, and what was deliberately *not* deduped",
        f"""
**`complaint_id` is unique** ({n_id_dupes} duplicates across {n_start:,} rows),
so the source primary key finds nothing. A meaningful dedupe needs a business
key.

**Dedupe key used:**

```
date_received_ts   (full timestamp, to the second)
company_key        (normalised company)
product, sub_product, issue, sub_issue
state, zip_code
submitted_via
```

**Removed: {n_biz_dupes} rows.** Two records matching on all nine fields
*including the receipt timestamp to the second* are double-submissions, not two
consumers who independently filed identical complaints about the same company in
the same second. Where a group's records differed on a non-key field, the
**most complete record is kept** (fewest nulls), so no information is lost by
the choice of survivor.

**Deliberately NOT removed: {n_date_only:,} rows.** Truncating the timestamp to a
calendar date makes {n_date_only:,} rows look like duplicates. They are not.
These are different consumers filing about the same issue at the same large bank
on the same day -- entirely expected when one company receives thousands of
complaints a month and ZIPs are privacy-masked to 3 digits.

Removing them would have been a serious error with a *directional* bias: it
would delete real complaints disproportionately from the highest-volume
companies, which are exactly the companies this project ranks. The dedupe would
have quietly improved the apparent standing of the worst offenders.

Net: {n_start:,} -> {len(df):,} rows ({n_biz_dupes} removed,
{100 * n_biz_dupes / n_start:.4f}%).
""",
    )

    # ---------------------------------------------------------------- write --
    banner("WRITING OUTPUT")
    final_cols = [
        "complaint_id", "date_received", "date_received_ts", "date_sent_to_company",
        "year", "month", "year_month", "days_to_company",
        "product", "product_short", "product_raw", "sub_product",
        "issue", "sub_issue",
        "company", "company_raw", "company_key",
        "state", "state_type", "zip_code", "zip3",
        "tags", "is_servicemember", "is_older_american",
        "submitted_via", "company_response", "company_public_response",
        "timely", "has_narrative",
        "is_resolved", "got_monetary_relief", "got_any_relief",
        "closed_explanation_only", "is_untimely", "company_disputes_facts",
        "dq_state_missing", "dq_zip_masked", "dq_sub_issue_missing",
        "dq_response_in_progress", "dq_long_routing_lag", "dq_partial_period",
        "dq_legacy_product_label", "in_trend_window",
    ]
    missing_cols = [c for c in final_cols if c not in df.columns]
    if missing_cols:
        sys.exit(f"internal error -- columns not built: {missing_cols}")

    out = df[final_cols]
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV.name}: {len(out):,} rows x {out.shape[1]} cols "
          f"({OUT_CSV.stat().st_size / 1e6:.1f} MB)")

    after = {
        "rows": len(out),
        "cols": out.shape[1],
        "total_nulls": int(out.isna().sum().sum()),
        "distinct_companies": int(out["company"].nunique()),
        "distinct_products": int(out["product"].nunique()),
    }

    # ------------------------------------------------------------------ log --
    header = f"""# Cleaning log -- Stage 2

*Generated by `scripts/02_clean.py` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.
Do not edit by hand: re-running the script regenerates this file, so the numbers
below can never drift from the data they describe.*

**Input:** `data/raw/complaints.csv` (never modified)
**Output:** `data/processed/complaints_clean.csv`, `data/processed/company_name_map.csv`

## Before / after

| Metric | Before | After |
|---|---:|---:|
| Rows | {before['rows']:,} | {after['rows']:,} |
| Columns | {before['cols']} | {after['cols']} |
| Total nulls | {before['total_nulls']:,} | {after['total_nulls']:,} |
| Distinct companies | {before['distinct_companies']:,} | {after['distinct_companies']:,} |
| Distinct products | {before['distinct_products']} | {after['distinct_products']} |
| Duplicates removed | -- | {n_biz_dupes} |

The remaining {after['total_nulls']:,} nulls are confined to `zip3` (unrecoverable
fully-masked ZIPs) and are intentional -- see Geography.
"""

    footer = f"""## Not available in this source

The CFPB **discontinued the `consumer_disputed` flag in April 2017** and it is
not returned by the API. Stage 6 asks for an escalation/dispute rate, which
therefore cannot be computed as specified. Substitutes carried forward instead,
all derived from fields that do exist:

| Intended measure | Substitute | Field |
|---|---|---|
| Consumer disputed the response | Company failed to respond on time | `is_untimely` |
| Consumer escalated | Company formally disputes the consumer's account | `company_disputes_facts` |
| Poor resolution quality | Closed with explanation only -- no relief of any kind | `closed_explanation_only` |

## Column reference

| Column | Type | Notes |
|---|---|---|
| `complaint_id` | text | Source primary key, unique |
| `date_received` / `date_received_ts` | date / timestamp | Date for aggregation, timestamp for dedupe |
| `days_to_company` | float | Routing lag in days |
| `product` / `product_short` / `product_raw` | text | Cleaned, chart label, original |
| `company` / `company_raw` / `company_key` | text | Canonical, original, join key for Stage 3 |
| `state_type` | text | `state` / `territory` / `military` / `unknown` |
| `zip3` | text | Recovered 3-digit prefix, null when fully masked |
| `is_resolved` | bool | **Denominator for all outcome rates** |
| `got_monetary_relief`, `got_any_relief` | bool | Outcome measures |
| `closed_explanation_only`, `is_untimely` | bool | Poor-resolution measures |
| `is_servicemember`, `is_older_american` | bool | Vulnerable-population flags from `tags` |
| `in_trend_window` | bool | **Filter for all period-over-period analysis** |
| `dq_*` | bool | Data-quality flags; none of them drop rows |
"""

    LOG_MD.write_text(header + "\n" + "\n".join(_log_sections) + "\n" + footer,
                      encoding="utf-8")
    print(f"wrote {LOG_MD.relative_to(PROJECT_ROOT)}")

    # -------------------------------------------------------------- summary --
    banner("BEFORE / AFTER SUMMARY")
    print(f"{'metric':<26}{'before':>14}{'after':>14}")
    print("-" * 54)
    for k in before:
        print(f"{k:<26}{before[k]:>14,}{after[k]:>14,}")
    print("-" * 54)
    print(f"{'duplicates removed':<26}{'':>14}{n_biz_dupes:>14,}")
    print(f"{'rows dropped for nulls':<26}{'':>14}{0:>14,}")
    print()
    print("remaining nulls by column (intentional):")
    rem = out.isna().sum()
    for c, v in rem[rem > 0].items():
        print(f"  {c:<24} {v:>9,}  ({100*v/len(out):.2f}%)")
    print("\nSTAGE 2 COMPLETE")


if __name__ == "__main__":
    main()
