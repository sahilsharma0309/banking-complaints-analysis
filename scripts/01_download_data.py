"""
Stage 1 — Data acquisition from the CFPB Consumer Complaint Database.

WHAT THIS DOES
--------------
Pulls a filtered subset of the CFPB Consumer Complaint Database via the public
search API (no key required) and writes it to `data/raw/`.

WHY A FILTERED SUBSET, NOT THE BULK DOWNLOAD
--------------------------------------------
The full bulk export is a 5-6 GB zip. We do not need it. Two filters cut it to
something a laptop can hold while making the analysis *more* valid, not less:

1. DATE WINDOW: 2023-01-01 .. 2026-01-01 (inclusive both ends).

2. PRODUCT SCOPE: banking and lending products only -- see PRODUCT_SCOPE below.
   The date window alone contains ~9.48M complaints, but ~8.23M of those (87%)
   are *credit reporting* complaints filed against Equifax, Experian and
   TransUnion. Those three are consumer reporting agencies, not FDIC-insured
   depository institutions, so:
     - they have no total-assets denominator, which is what the project's
       headline metric (complaints per $1B of assets) is built on; and
     - at 87% of all rows they would dominate every product, issue and trend
       chart, burying the banks the analysis is actually about.
   Debt collection (508k) and money transfer/crypto (115k) are excluded for the
   same reason: they are overwhelmingly third-party collection agencies and
   non-bank fintechs.
   Net: 9,478,443 rows -> ~624,727 rows, and every remaining row is a product a
   bank or lender actually sells.

3. NARRATIVE SPLIT: the free-text `complaint_what_happened` field is present on
   ~62% of rows and averages ~900 bytes, which alone accounts for ~77% of the
   payload. It is written to its OWN file keyed by complaint_id rather than
   being dropped, so the core quantitative pipeline (Stages 2-8) stays lean and
   fast while an optional text-analysis stage remains possible without a
   re-download.

OUTPUTS
-------
  data/raw/complaints.csv            lean analytical table (no narrative text)
  data/raw/complaint_narratives.csv  complaint_id -> narrative, non-empty only
  data/sample_1000.csv               first 1,000 lean rows, committed to git

PAGINATION
----------
The API caps the `frm` offset parameter (it is silently ignored past the first
page -- verified empirically), so deep pagination must use the Elasticsearch
`search_after` cursor. The cursor is the previous page's last hit `sort` array
joined with an underscore: "<epoch_millis>_<complaint_id>".

The run is checkpointed after every page, so an interrupted download resumes
where it stopped instead of starting over.

USAGE
-----
    python scripts/01_download_data.py                # full pull (resumes)
    python scripts/01_download_data.py --limit 20000  # quick smoke test
    python scripts/01_download_data.py --restart      # ignore checkpoint
    python scripts/01_download_data.py --bulk-fallback
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Paths & configuration
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_DIR = PROJECT_ROOT / "data"

COMPLAINTS_CSV = RAW_DIR / "complaints.csv"
NARRATIVES_CSV = RAW_DIR / "complaint_narratives.csv"
SAMPLE_CSV = DATA_DIR / "sample_1000.csv"
CHECKPOINT = RAW_DIR / ".download_checkpoint.json"
MANIFEST = RAW_DIR / "download_manifest.json"

load_dotenv(PROJECT_ROOT / ".env")

API_BASE = (
    "https://www.consumerfinance.gov/data-research/consumer-complaints/"
    "search/api/v1/"
)
BULK_ZIP_URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"

DATE_FROM = os.getenv("CFPB_DATE_FROM", "2023-01-01")
DATE_TO = os.getenv("CFPB_DATE_TO", "2026-01-01")

# Banking & lending products only. See module docstring for the rationale.
# These strings must match the CFPB `product` values byte-for-byte. Two pairs
# are legacy/current labels for the same thing; the CFPB renamed them mid-stream
# and both appear in the 2023-2026 window. Stage 2 collapses them.
PRODUCT_SCOPE = [
    "Checking or savings account",
    "Credit card",
    "Credit card or prepaid card",          # legacy label, merged in Stage 2
    "Prepaid card",
    "Mortgage",
    "Vehicle loan or lease",
    "Student loan",
    "Payday loan, title loan, personal loan, or advance loan",
    "Payday loan, title loan, or personal loan",  # legacy label
    "Debt or credit management",
]

PAGE_SIZE = 5_000
NARRATIVE_FIELD = "complaint_what_happened"

# Explicit column order so the CSV is byte-stable across runs (reproducibility).
LEAN_COLUMNS = [
    "complaint_id",
    "date_received",
    "date_sent_to_company",
    "product",
    "sub_product",
    "issue",
    "sub_issue",
    "company",
    "state",
    "zip_code",
    "tags",
    "submitted_via",
    "company_public_response",
    "company_response",
    "timely",
    "has_narrative",
]
NARRATIVE_COLUMNS = ["complaint_id", NARRATIVE_FIELD]

MAX_RETRIES = 6
BACKOFF_BASE = 2.0
REQUEST_TIMEOUT = 180
POLITE_DELAY = 0.4  # seconds between successful pages


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "banking-complaints-analysis/1.0 "
                "(portfolio data-analysis project; contact via GitHub)"
            ),
            "Accept": "application/json",
        }
    )
    return s


def fetch_page(session: requests.Session, cursor: str | None) -> dict:
    """GET one page, retrying with exponential backoff + jitter.

    Retries on connection errors, timeouts, 429 and 5xx. A 4xx other than 429
    is a bug in our request, not a transient fault, so it fails loudly.
    """
    # GOTCHA, verified empirically: do NOT send `format=json`. Passing an
    # explicit `format` routes the request to the CFPB *export* endpoint, which
    # caps the total result set at 100,000 and rejects our 624,727-row filter
    # with HTTP 400 ("Result set of 624727 exceeds the export limit of 100000").
    # Omitting `format` uses the normal search endpoint, which returns JSON by
    # default and has no depth limit when paginating with search_after.
    params = {
        "date_received_min": DATE_FROM,
        "date_received_max": DATE_TO,
        "product": PRODUCT_SCOPE,
        "size": PAGE_SIZE,
        "sort": "created_date_desc",
        "no_aggs": "true",  # skip aggregation computation -> much faster
    }
    if cursor:
        params["search_after"] = cursor

    last_err: Exception | str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(API_BASE, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
            else:
                raise RuntimeError(
                    f"Non-retryable HTTP {resp.status_code} from CFPB API: "
                    f"{resp.text[:300]}"
                )
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_err = exc

        if attempt == MAX_RETRIES:
            break
        sleep_for = BACKOFF_BASE ** attempt + random.uniform(0, 1.5)
        log(f"    retry {attempt}/{MAX_RETRIES - 1} after {last_err} "
            f"-- sleeping {sleep_for:.1f}s")
        time.sleep(sleep_for)

    raise RuntimeError(f"Gave up after {MAX_RETRIES} attempts. Last error: {last_err}")


def total_expected(session: requests.Session) -> int:
    """Ask the API how many rows the filter matches, for progress reporting."""
    params = {
        "date_received_min": DATE_FROM,
        "date_received_max": DATE_TO,
        "product": PRODUCT_SCOPE,
        "size": 1,
        "no_aggs": "true",
    }
    resp = session.get(API_BASE, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return int(resp.json()["hits"]["total"]["value"])


def load_checkpoint() -> dict | None:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("! checkpoint file corrupt -- ignoring it and starting fresh")
    return None


def save_checkpoint(cursor: str | None, rows: int, narratives: int, pages: int) -> None:
    CHECKPOINT.write_text(
        json.dumps(
            {
                "cursor": cursor,
                "rows_written": rows,
                "narratives_written": narratives,
                "pages_done": pages,
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "product_scope": PRODUCT_SCOPE,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def existing_ids() -> set[str]:
    """Reload already-written complaint_ids so a resumed run cannot duplicate."""
    if not COMPLAINTS_CSV.exists():
        return set()
    ids: set[str] = set()
    with COMPLAINTS_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ids.add(row["complaint_id"])
    return ids


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------- #
# Main API pull
# --------------------------------------------------------------------------- #
def download_via_api(row_limit: int | None, restart: bool) -> tuple[int, int]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = build_session()

    if restart:
        for p in (COMPLAINTS_CSV, NARRATIVES_CSV, CHECKPOINT):
            p.unlink(missing_ok=True)
        log("--restart: cleared previous output and checkpoint")

    ckpt = load_checkpoint()
    resuming = ckpt is not None and COMPLAINTS_CSV.exists()

    if resuming:
        # Guard: a checkpoint from a different filter would silently mix scopes.
        if ckpt.get("product_scope") != PRODUCT_SCOPE or \
           ckpt.get("date_from") != DATE_FROM or ckpt.get("date_to") != DATE_TO:
            log("! checkpoint was written under a DIFFERENT filter "
                "(date range or product scope changed).")
            log("! refusing to resume -- re-run with --restart to rebuild cleanly.")
            sys.exit(1)
        cursor = ckpt["cursor"]
        rows = ckpt["rows_written"]
        narratives = ckpt["narratives_written"]
        pages = ckpt["pages_done"]
        log(f"resuming from checkpoint: {rows:,} rows over {pages} pages already saved")
        log("  reloading existing complaint_ids for duplicate protection...")
        seen = existing_ids()
        log(f"  {len(seen):,} ids loaded")
    else:
        cursor, rows, narratives, pages = None, 0, 0, 0
        seen = set()

    expected = total_expected(session)
    target = min(expected, row_limit) if row_limit else expected
    log(f"CFPB API filter matches {expected:,} complaints")
    log(f"date window : {DATE_FROM} .. {DATE_TO} (inclusive)")
    log(f"products    : {len(PRODUCT_SCOPE)} banking/lending categories")
    log(f"target      : {target:,} rows  |  page size {PAGE_SIZE:,}")
    log("-" * 68)

    mode = "a" if resuming else "w"
    started = time.time()
    duplicates = 0

    with COMPLAINTS_CSV.open(mode, encoding="utf-8", newline="") as f_main, \
         NARRATIVES_CSV.open(mode, encoding="utf-8", newline="") as f_narr:

        w_main = csv.DictWriter(f_main, fieldnames=LEAN_COLUMNS, extrasaction="ignore")
        w_narr = csv.DictWriter(f_narr, fieldnames=NARRATIVE_COLUMNS, extrasaction="ignore")
        if not resuming:
            w_main.writeheader()
            w_narr.writeheader()

        while True:
            if row_limit and rows >= row_limit:
                log(f"reached --limit {row_limit:,} -- stopping early")
                break

            payload = fetch_page(session, cursor)
            hits = payload.get("hits", {}).get("hits", [])
            if not hits:
                log("API returned an empty page -- end of result set")
                break

            page_new = 0
            for hit in hits:
                src = hit.get("_source", {})
                cid = src.get("complaint_id")
                if cid is None or cid in seen:
                    duplicates += 1
                    continue
                seen.add(cid)

                narrative = (src.get(NARRATIVE_FIELD) or "").strip()
                if narrative:
                    w_narr.writerow({"complaint_id": cid, NARRATIVE_FIELD: narrative})
                    narratives += 1

                w_main.writerow(src)
                page_new += 1

                if row_limit and rows + page_new >= row_limit:
                    break

            rows += page_new
            pages += 1
            cursor = "_".join(str(v) for v in hits[-1]["sort"])

            f_main.flush()
            f_narr.flush()
            save_checkpoint(cursor, rows, narratives, pages)

            elapsed = time.time() - started
            pct = 100 * rows / target if target else 0
            rate = rows / elapsed if elapsed > 0 else 0
            eta = (target - rows) / rate if rate > 0 else 0
            log(f"page {pages:>3}  |  {rows:>7,} / {target:,} rows ({pct:5.1f}%)  "
                f"|  {narratives:>7,} narratives  |  {rate:6.0f} rows/s  "
                f"|  ETA {eta/60:5.1f} min")

            if len(hits) < PAGE_SIZE:
                log("short page returned -- end of result set")
                break

            time.sleep(POLITE_DELAY)

    if duplicates:
        log(f"note: skipped {duplicates:,} duplicate complaint_id(s) returned by the API")

    CHECKPOINT.unlink(missing_ok=True)
    return rows, narratives


# --------------------------------------------------------------------------- #
# Bulk-zip fallback
# --------------------------------------------------------------------------- #
def download_via_bulk_zip() -> tuple[int, int]:
    """Last resort if the API is unavailable.

    Streams the ~5-6 GB zip to disk, filters it in pandas chunks so peak memory
    stays low, writes the same two outputs, then DELETES the big files.
    """
    import pandas as pd

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / "_bulk_complaints.csv.zip"

    log("FALLBACK: downloading CFPB bulk zip (this is 5-6 GB and will be deleted after)")
    with requests.get(BULK_ZIP_URL, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with zip_path.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 22):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {human(done)} / {human(total)} "
                          f"({100*done/total:.1f}%)", end="", flush=True)
        print()

    log("extracting and filtering in chunks...")
    with zipfile.ZipFile(zip_path) as zf:
        inner = zf.namelist()[0]
        rows = narratives = 0
        first = True
        with zf.open(inner) as fh:
            reader = pd.read_csv(fh, chunksize=200_000, low_memory=False)
            for i, chunk in enumerate(reader, 1):
                chunk.columns = [c.strip().lower().replace(" ", "_").replace("-", "_")
                                 for c in chunk.columns]
                # Bulk export uses slightly different names than the API.
                chunk = chunk.rename(columns={
                    "consumer_complaint_narrative": NARRATIVE_FIELD,
                    "timely_response?": "timely",
                    "submitted_via": "submitted_via",
                })
                chunk["date_received"] = pd.to_datetime(
                    chunk["date_received"], errors="coerce")
                mask = (
                    chunk["date_received"].between(DATE_FROM, DATE_TO)
                    & chunk["product"].isin(PRODUCT_SCOPE)
                )
                sub = chunk.loc[mask].copy()
                if sub.empty:
                    continue

                narr = sub.loc[
                    sub[NARRATIVE_FIELD].notna() & (sub[NARRATIVE_FIELD].str.strip() != ""),
                    ["complaint_id", NARRATIVE_FIELD],
                ]
                for col in LEAN_COLUMNS:
                    if col not in sub.columns:
                        sub[col] = pd.NA

                sub[LEAN_COLUMNS].to_csv(
                    COMPLAINTS_CSV, mode="w" if first else "a",
                    header=first, index=False)
                narr.to_csv(
                    NARRATIVES_CSV, mode="w" if first else "a",
                    header=first, index=False)
                first = False
                rows += len(sub)
                narratives += len(narr)
                log(f"  chunk {i}: kept {len(sub):,} (running total {rows:,})")

    log("deleting the bulk zip to reclaim disk space")
    zip_path.unlink(missing_ok=True)
    return rows, narratives


# --------------------------------------------------------------------------- #
# Post-processing
# --------------------------------------------------------------------------- #
def write_sample_and_manifest(rows: int, narratives: int, source: str) -> None:
    import pandas as pd

    log("writing data/sample_1000.csv (committed to git so reviewers see the schema)")
    sample = pd.read_csv(COMPLAINTS_CSV, nrows=1000, dtype=str)
    sample.to_csv(SAMPLE_CSV, index=False)

    df_head = pd.read_csv(COMPLAINTS_CSV, nrows=50_000, dtype=str)
    manifest = {
        "source": source,
        "api_base": API_BASE,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "product_scope": PRODUCT_SCOPE,
        "rows_complaints": rows,
        "rows_narratives": narratives,
        "columns_complaints": LEAN_COLUMNS,
        "columns_narratives": NARRATIVE_COLUMNS,
        "bytes_complaints": COMPLAINTS_CSV.stat().st_size,
        "bytes_narratives": NARRATIVES_CSV.stat().st_size if NARRATIVES_CSV.exists() else 0,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print()
    print("=" * 72)
    print("STAGE 1 COMPLETE -- CFPB extract written")
    print("=" * 72)
    print(f"  source                 : {source}")
    print(f"  date window            : {DATE_FROM} .. {DATE_TO} (inclusive)")
    print(f"  product scope          : {len(PRODUCT_SCOPE)} banking/lending categories")
    print()
    print(f"  complaints.csv         : {rows:,} rows  "
          f"({human(COMPLAINTS_CSV.stat().st_size)})")
    print(f"  complaint_narratives   : {narratives:,} rows  "
          f"({human(NARRATIVES_CSV.stat().st_size)})"
          f"  [{100*narratives/rows:.1f}% of complaints have narrative text]")
    print(f"  sample_1000.csv        : 1,000 rows  ({human(SAMPLE_CSV.stat().st_size)})")
    print()
    print(f"  columns ({len(LEAN_COLUMNS)}):")
    for c in LEAN_COLUMNS:
        nn = df_head[c].notna().sum()
        pct = 100 * nn / len(df_head)
        print(f"    {c:<26s} {pct:5.1f}% populated (in first 50k rows)")
    print()
    print(f"  manifest               : {MANIFEST.relative_to(PROJECT_ROOT)}")
    print("=" * 72)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after roughly N rows (smoke testing)")
    ap.add_argument("--restart", action="store_true",
                    help="discard any checkpoint and re-download from scratch")
    ap.add_argument("--bulk-fallback", action="store_true",
                    help="skip the API and use the 5-6 GB bulk zip instead")
    args = ap.parse_args()

    free = shutil.disk_usage(PROJECT_ROOT).free
    log(f"free disk on project drive: {human(free)}")

    if args.bulk_fallback:
        rows, narratives = download_via_bulk_zip()
        source = "CFPB bulk zip (fallback path)"
    else:
        try:
            rows, narratives = download_via_api(args.limit, args.restart)
            source = "CFPB search API v1 (search_after pagination)"
        except Exception as exc:  # noqa: BLE001 - we want the fallback hint
            log(f"! API pull failed: {exc}")
            log("! re-run with --bulk-fallback to use the bulk zip instead.")
            raise

    if rows == 0:
        log("! no rows written -- check the filters")
        sys.exit(1)

    write_sample_and_manifest(rows, narratives, source)


if __name__ == "__main__":
    main()
