"""
Stage 3 -- Enrichment: attach FDIC total assets so complaint volume can be
size-adjusted.

Reads   data/processed/complaints_clean.csv
Writes  data/raw/fdic_institutions.csv          (cached API pull, never modified)
        data/processed/fdic_holding_companies.csv
        data/processed/company_fdic_match.csv   (every company, matched or not)
        data/processed/company_enriched.csv     (company-level analytical table)
        reports/enrichment_log.md               (generated)

WHY THIS STAGE EXISTS
---------------------
Complaint volume is a size proxy, not a risk signal. JPMorgan generates the most
complaints because it has the most customers. The headline metric of this project
is complaints per $1B of total assets, and this stage builds the denominator.

THE MATCHING PROBLEM
--------------------
CFPB names HOLDING COMPANIES. FDIC names INSURED SUBSIDIARIES.

    CFPB "U.S. BANCORP"                  FDIC "U.S. Bank National Association"
    CFPB "TRUIST FINANCIAL CORPORATION"  FDIC "Truist Bank"

FDIC exposes NAMEHCR (holding-company name) which bridges the two, but it is
heavily abbreviated ("U S BCORP", "PNC FINL SERVICES GROUP INC"), so the
abbreviations are expanded before fuzzy matching.

TWO RULES THAT KEEP THE METRIC HONEST
-------------------------------------
1. ASSETS ARE AGGREGATED AT HOLDING-COMPANY LEVEL.
   One CFPB company can map to several FDIC charters. Matching to a single
   subsidiary and using only its assets understates the denominator and inflates
   the risk rate. Measured on real data, matching Morgan Stanley to its largest
   charter alone would understate assets by 38.2%; Popular Inc by 19.8%;
   Charles Schwab by 13.5%.

   IMPORTANT EXCEPTION: 683 insured institutions have NO holding company (a
   blank NAMEHCR). Grouping on the blank value would fuse 683 unrelated
   independent banks into one fictional $822B entity. Those are keyed by their
   own CERT and remain individual.

2. UNMATCHED COMPANIES ARE NOT DROPPED.
   Fintechs, loan servicers and credit bureaus have no FDIC assets by design.
   They keep every volume, trend and resolution metric; they are excluded only
   from the size-adjusted ranking, and the "unmatched but high-volume" list is
   published as a finding in its own right.
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from rapidfuzz import fuzz, process

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_CSV = PROJECT_ROOT / "data" / "processed" / "complaints_clean.csv"
FDIC_RAW = PROJECT_ROOT / "data" / "raw" / "fdic_institutions.csv"
PROC = PROJECT_ROOT / "data" / "processed"
HC_CSV = PROC / "fdic_holding_companies.csv"
MATCH_CSV = PROC / "company_fdic_match.csv"
UNMATCHED_CSV = PROC / "unmatched_companies.csv"
ENRICHED_CSV = PROC / "company_enriched.csv"
LOG_MD = PROJECT_ROOT / "reports" / "enrichment_log.md"

load_dotenv(PROJECT_ROOT / ".env")

FDIC_API = "https://banks.data.fdic.gov/api/institutions"
FDIC_FIELDS = ("NAME,CERT,ASSET,CITY,STALP,ACTIVE,BKCLASS,RSSDHCR,NAMEHCR,"
               "OFFDOM,ESTYMD")

# Auto-accept threshold. Anything scoring below this is left UNMATCHED rather
# than guessed at -- a wrong match silently corrupts a company's risk rate, so
# the failure mode is chosen to be "no denominator" rather than "wrong
# denominator". The 80-92 band is written to the log for manual review.
AUTO_ACCEPT = 92
REVIEW_FLOOR = 75
# A shared distinctive token is necessary but NOT sufficient. 'MECHANICS BANK'
# and 'Farmers and Mechanics Federal Savings' share MECHANICS; 'Fidelity
# National Information Services' and 'Fidelity Co' share FIDELITY. Both are
# false. Requiring the distinctive-token SETS to overlap substantially (Jaccard)
# rejects them while keeping genuine pairs, whose sets are usually identical.
MIN_TOKEN_JACCARD = 0.6
# A single shared distinctive token is never enough. Fuzzy acceptance requires
# TWO. This is affordable because exact-normalised and curated matches already
# carry ~99% of matched complaint volume -- the fuzzy paths were contributing
# 0.5% of volume while generating every false positive found in review.
MIN_SHARED_TOKENS = 2

# FDIC abbreviates aggressively in NAMEHCR. Expanded before matching.
FDIC_ABBREV = {
    "BCORP": "BANCORP", "BC": "BANCORP", "BSHRS": "BANCSHARES",
    "BSHS": "BANCSHARES", "FINL": "FINANCIAL", "FNCL": "FINANCIAL",
    "NATL": "NATIONAL", "NTNL": "NATIONAL", "SVGS": "SAVINGS",
    "SVG": "SAVINGS", "MTG": "MORTGAGE", "GRP": "GROUP",
    "INTL": "INTERNATIONAL", "BK": "BANK", "BKS": "BANKS",
    "BKG": "BANKING", "TR": "TRUST", "ASSN": "ASSOCIATION",
    "CORP": "CORPORATION", "CO": "COMPANY", "INC": "INCORPORATED",
    "SVC": "SERVICE", "SVCS": "SERVICES", "MUT": "MUTUAL",
    "FED": "FEDERAL", "CU": "CREDIT UNION", "HLDG": "HOLDING",
    "HLDGS": "HOLDINGS", "AMER": "AMERICAN", "NORTHWEST": "NORTHWEST",
}

# Tokens that carry no identifying signal -- almost every US bank contains
# several. A match is only trusted when at least one token OUTSIDE this set
# matches EXACTLY (see significant_tokens / the guard in match_companies).
GENERIC_TOKENS = {
    "BANK", "BANKS", "BANKING", "BANC", "BANCORP", "BANCSHARES", "FINANCIAL",
    "FINANCE", "GROUP", "HOLDING", "HOLDINGS", "NATIONAL", "ASSOCIATION",
    "SERVICE", "SERVICES", "USA", "US", "AMERICA", "AMERICAN", "FEDERAL",
    "SAVINGS", "TRUST", "CREDIT", "UNION", "STATE", "STATES", "FIRST",
    "COMMUNITY", "COMMERCIAL", "COMMERCE", "MUTUAL", "COUNTY", "CITY",
    "NEW", "OLD", "THE", "OF", "AND", "CORPORATION", "COMPANY", "INTERNATIONAL",
}

# Curated overrides for companies where fuzzy matching cannot succeed because
# the CFPB name and the FDIC legal name share no distinctive token. Each maps to
# an EXACT FDIC charter NAME (not a holding-company string), so every entry is a
# checkable factual claim rather than a tuning knob. The charter's holding group
# -- and therefore its full aggregated assets -- is resolved from it.
MANUAL_OVERRIDES = {
    "CITIBANK, N.A.": "Citibank, National Association",
    "GOLDMAN SACHS BANK USA": "Goldman Sachs Bank USA",
    "TD BANK US HOLDING COMPANY": "TD Bank, National Association",
    "SANTANDER HOLDINGS USA, INC.": "Santander Bank, N.A.",
    "BMO HARRIS BANK N.A.": "BMO Bank National Association",
    "BARCLAYS BANK DELAWARE": "Barclays Bank Delaware",
    "AMERICAN EXPRESS COMPANY": "American Express National  Bank",
    "SYNCHRONY FINANCIAL": "Synchrony Bank",
    "FIFTH THIRD FINANCIAL CORPORATION": "Fifth Third Bank, National Association",
}

# Companies that WERE FDIC-insured during the analysis window but no longer hold
# an active charter, so BankFind reports no current assets for them. Forcing
# them onto their acquirer would distort both parties' rates for the years
# before the deal closed, so they are declared unmatched with the reason stated.
DECLARED_INACTIVE_CHARTER = {
    "DISCOVER BANK": (
        "merged into Capital One, N.A. (acquisition completed May 2025); no "
        "active FDIC charter, so no current asset denominator exists"
    ),
    "BANK OF THE WEST": (
        "acquired by BMO (February 2023); the surviving 'BancWest Inc' shell "
        "reports $0.18B, which is a post-divestiture residual and not a "
        "meaningful denominator for the complaints filed against the bank"
    ),
    "COMERICA": (
        "no active charter in the current BankFind snapshot -- cert 983 is "
        "absent from the active institution list, consistent with the Fifth "
        "Third acquisition. Verified absent rather than assumed: a search of "
        "all 4,255 active institutions returns no Comerica record"
    ),
}

# Companies known to have NO FDIC-insured charter. Declaring them explicitly
# stops the matcher forcing a spurious match onto a similar-sounding bank, and
# turns the exclusion into an auditable claim instead of a silent failure.
# Keys are matched on the NORMALISED name so punctuation variants all hit.
KNOWN_NON_BANKS = {
    "EQUIFAX": "credit reporting agency -- not a depository",
    "TRANSUNION INTERMEDIATE": "credit reporting agency -- not a depository",
    "EXPERIAN INFORMATION SOLUTIONS": "credit reporting agency -- not a depository",
    "MOHELA": "federal student loan servicer -- no charter",
    "NELNET": "federal student loan servicer -- no charter",
    "NAVIENT SOLUTIONS": "student loan servicer -- no charter",
    "MAXIMUS FEDERAL SERVICES": "federal loan servicer -- no charter",
    "CHIME FINANCIAL": "fintech -- deposits held at partner banks",
    "BLOCK": "fintech / payments -- no charter",
    "PAYPAL HOLDINGS": "fintech / payments -- no charter",
    "SHELLPOINT PARTNERS": "mortgage servicer -- no charter",
    "MR COOPER": "mortgage servicer -- no charter",
    "OCWEN FINANCIAL": "mortgage servicer -- no charter (NOT 'Owen Financial Corp')",
    "BREAD FINANCIAL": "card issuer via partner bank -- no charter of its own",
    "BMW FINANCIAL SERVICES": "captive auto lender -- no charter",
}

# Any name containing these is NCUA-insured, not FDIC-insured. They are real
# depositories with real assets, but they are simply absent from BankFind.
CREDIT_UNION_MARKERS = ("CREDIT UNION", "FEDERAL CREDIT UNION", " FCU")


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def banner(msg: str) -> None:
    print(f"\n{'=' * 74}\n{msg}\n{'=' * 74}", flush=True)


def normalise(name: str) -> str:
    """Shared normaliser for both sides of the match."""
    out = (name or "").upper()
    out = out.replace("&", " AND ")
    # Expand 'N.A.' BEFORE punctuation is stripped, otherwise it shatters into
    # the meaningless tokens 'N' and 'A' and 'PNC Bank N.A.' stops matching
    # 'PNC Bank, National Association'.
    out = re.sub(r"\bN\.\s*A\.", " NATIONAL ASSOCIATION ", out)
    out = re.sub(r"[^A-Z0-9 ]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\bN A\b", " NATIONAL ASSOCIATION ", out)
    out = re.sub(r"^THE\s+", "", out)
    out = re.sub(r"\s+THE$", "", out)
    tokens = [FDIC_ABBREV.get(t, t) for t in out.split()]
    # Drop pure legal-form noise that carries no identifying signal.
    drop = {"INCORPORATED", "CORPORATION", "COMPANY", "LLC", "LP", "LLP",
            "PLC", "LTD", "LIMITED", "AND", "SA", "AG", "NV"}
    tokens = [t for t in tokens if t not in drop]
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def significant_tokens(norm: str) -> set[str]:
    """Tokens that actually identify an institution.

    Guard against the central failure mode of character-level fuzzy matching:
    'OCWEN FINANCIAL' vs 'OWEN FINANCIAL' scores 96.6 on token_sort_ratio -- a
    single missing letter -- and would attach a $0.4B community bank's assets to
    a mortgage servicer, producing 7,923 complaints per $1B. Requiring at least
    one *exact* distinctive-token overlap rejects that while leaving genuine
    matches (PNC/PNC, SYNCHRONY/SYNCHRONY) untouched.
    """
    return {t for t in norm.split() if len(t) >= 3 and t not in GENERIC_TOKENS}


def is_credit_union(name: str) -> bool:
    up = (name or "").upper()
    return any(m in up for m in CREDIT_UNION_MARKERS)


def known_non_bank_reason(norm: str) -> str | None:
    for key, reason in KNOWN_NON_BANKS.items():
        if norm.startswith(key):
            return reason
    return None


# --------------------------------------------------------------------------- #
def fetch_fdic(force: bool = False) -> pd.DataFrame:
    if FDIC_RAW.exists() and not force:
        log(f"using cached {FDIC_RAW.name}")
        return pd.read_csv(FDIC_RAW, dtype=str)

    log("pulling FDIC BankFind institutions (public API, no key required)...")
    rows, offset = [], 0
    while True:
        params = {"filters": "ACTIVE:1", "fields": FDIC_FIELDS, "limit": 1000,
                  "offset": offset, "sort_by": "CERT", "sort_order": "ASC",
                  "format": "json"}
        for attempt in range(5):
            try:
                r = requests.get(FDIC_API, params=params, timeout=180)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt == 4:
                    raise
                log(f"  retry after {e}")
                time.sleep(2 ** attempt)
        batch = [d["data"] for d in r.json().get("data", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        print(f"    {len(rows):,} institutions", end="\r", flush=True)
        if len(batch) < 1000:
            break
        time.sleep(0.25)
    print()
    df = pd.DataFrame(rows)
    FDIC_RAW.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FDIC_RAW, index=False)
    log(f"cached {len(df):,} institutions -> {FDIC_RAW.name}")
    return df


def build_holding_companies(fdic: pd.DataFrame) -> pd.DataFrame:
    """Collapse charters to holding-company groups, summing assets.

    Institutions with no holding company keep their own identity -- grouping on
    a blank NAMEHCR would fuse hundreds of unrelated independent banks.
    """
    f = fdic.copy()
    f["ASSET"] = pd.to_numeric(f["ASSET"], errors="coerce").fillna(0)
    f["NAMEHCR"] = f["NAMEHCR"].fillna("").str.strip()
    f["has_hc"] = f["NAMEHCR"].ne("")

    f["group_key"] = f["NAMEHCR"].where(f["has_hc"], "CERT:" + f["CERT"].astype(str))
    f["group_name"] = f["NAMEHCR"].where(f["has_hc"], f["NAME"])

    f = f.sort_values("ASSET", ascending=False)
    hc = (
        f.groupby("group_key", as_index=False)
        .agg(
            group_name=("group_name", "first"),
            total_assets_k=("ASSET", "sum"),
            n_charters=("CERT", "count"),
            largest_charter=("NAME", "first"),
            largest_charter_assets_k=("ASSET", "first"),
            primary_cert=("CERT", "first"),
            state=("STALP", "first"),
            has_holding_company=("has_hc", "first"),
        )
    )
    hc["total_assets_b"] = (hc["total_assets_k"] / 1e6).round(3)
    denom = hc["total_assets_k"].where(hc["total_assets_k"] > 0)
    hc["assets_understated_pct"] = (
        100 * (1 - hc["largest_charter_assets_k"] / denom)
    ).astype("float64").round(2)
    return hc.sort_values("total_assets_k", ascending=False).reset_index(drop=True)


def match_companies(companies: pd.DataFrame, hc: pd.DataFrame,
                    fdic: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-match each CFPB company to a holding-company group.

    Candidates are the holding-company name AND every subsidiary charter name,
    because CFPB sometimes names the bank ("DISCOVER BANK") and sometimes the
    parent ("U.S. BANCORP").
    """
    cand_rows = []
    for r in hc.itertuples():
        cand_rows.append((normalise(r.group_name), r.group_key, "holding_company"))
    f = fdic.copy()
    f["NAMEHCR"] = f["NAMEHCR"].fillna("").str.strip()
    f["group_key"] = f["NAMEHCR"].where(f["NAMEHCR"].ne(""),
                                        "CERT:" + f["CERT"].astype(str))
    for r in f.itertuples():
        cand_rows.append((normalise(r.NAME), r.group_key, "charter"))

    cand = pd.DataFrame(cand_rows, columns=["norm", "group_key", "source"])
    cand = cand[cand["norm"].str.len() > 2].drop_duplicates("norm").reset_index(drop=True)
    cand["sig"] = cand["norm"].map(significant_tokens)
    choices = cand["norm"].tolist()
    log(f"built {len(choices):,} match candidates "
        f"({(cand['source'] == 'holding_company').sum():,} holding names, "
        f"{(cand['source'] == 'charter').sum():,} charter names)")

    # Charter NAME -> group_key, for resolving manual overrides.
    charter_to_group = {}
    for r in fdic.itertuples():
        gk = r.NAMEHCR if str(r.NAMEHCR).strip() else f"CERT:{r.CERT}"
        charter_to_group[str(r.NAME).strip()] = gk

    hc_by_key = hc.set_index("group_key")
    out = []
    for r in companies.itertuples():
        raw = r.company
        norm = normalise(raw)
        sig = significant_tokens(norm)

        # 1. Declared non-banks -- never guess a match for these.
        reason = known_non_bank_reason(norm)
        if reason:
            out.append({**_blank(raw, r.n_complaints), "match_method": "known_non_bank",
                        "match_note": reason})
            continue

        # 1b. Charters that lapsed during or after the analysis window.
        if raw.upper() in DECLARED_INACTIVE_CHARTER:
            out.append({**_blank(raw, r.n_complaints),
                        "match_method": "inactive_charter",
                        "match_note": DECLARED_INACTIVE_CHARTER[raw.upper()]})
            continue

        # 2. Credit unions are NCUA-insured and simply absent from BankFind.
        if is_credit_union(raw):
            out.append({**_blank(raw, r.n_complaints), "match_method": "ncua_credit_union",
                        "match_note": "NCUA-insured credit union -- not in FDIC BankFind"})
            continue

        # 3. Curated overrides, resolved through an exact FDIC charter name.
        if raw.upper() in MANUAL_OVERRIDES:
            charter = MANUAL_OVERRIDES[raw.upper()]
            gk = charter_to_group.get(charter)
            if gk is not None and gk in hc_by_key.index:
                g = hc_by_key.loc[gk]
                out.append(_row(raw, r.n_complaints, g, gk, 100.0, "manual_override",
                                f"curated -> charter '{charter}'"))
                continue
            log(f"! override target not found in FDIC: {charter!r} (for {raw!r})")

        # 4. Fuzzy match. The distinctive-token rule is applied as a FILTER over
        #    the top candidates, not as a check on a single winner. Checking
        #    only the top-1 lets a wrong candidate crowd out the right one:
        #    'FIFTH THIRD FINANCIAL' lost to 'PATHWARD FINANCIAL' even though
        #    'FIFTH THIRD BANCORP' was present and shares two exact tokens.
        ranked = process.extract(norm, choices, scorer=fuzz.token_set_ratio,
                                 limit=25)
        if not ranked:
            out.append({**_blank(raw, r.n_complaints), "match_method": "no_candidate",
                        "match_note": ""})
            continue

        viable = [(t, s, i) for t, s, i in ranked
                  if t == norm or (sig & cand.iloc[i]["sig"])]
        if viable:
            # token_set_ratio saturates at 100 for many candidates at once
            # ('COMERICA' matches both 'COMERICA' and 'COMERICA BANK' at 100),
            # so ranking by score alone picks arbitrarily. Prefer, in order:
            # an exact normalised match, then the highest distinctive-token
            # overlap, then the character score.
            def _rank_key(x):
                t, s, i = x
                cs = cand.iloc[i]["sig"]
                u = sig | cs
                return (t == norm, len(sig & cs) / len(u) if u else 0.0, s)

            text, score, idx = max(viable, key=_rank_key)
        else:
            text, score, idx = ranked[0]
        gk = cand.iloc[idx]["group_key"]
        shared = sig & cand.iloc[idx]["sig"]

        # An EXACT normalised-string match is the strongest evidence available
        # and is accepted even with no distinctive token. This is what rescues
        # names built entirely from generic words -- 'BANK OF AMERICA NATIONAL
        # ASSOCIATION' and 'U S BANCORP' have no non-generic token at all, yet
        # match their FDIC counterpart character-for-character. OCWEN/OWEN is
        # NOT exact, so the guard still rejects it.
        cand_sig = cand.iloc[idx]["sig"]
        union = sig | cand_sig
        jaccard = len(shared) / len(union) if union else 0.0

        if norm == text:
            g = hc_by_key.loc[gk]
            out.append(_row(raw, r.n_complaints, g, gk, score, "exact_normalised",
                            f"exact normalised match: '{text}'"))
        elif len(sig) >= MIN_SHARED_TOKENS and sig == cand_sig:
            # Identical distinctive-token sets differing only in generic words:
            # 'FIFTH THIRD FINANCIAL' vs 'FIFTH THIRD BANCORP'. Requires TWO
            # tokens -- a single shared token is not evidence. 'Paramount GR
            # Holdings' vs 'Paramount Financial Group' and 'Continental Finance'
            # vs 'Continental Bancorp' both have identical one-token sets and
            # are both wrong.
            g = hc_by_key.loc[gk]
            out.append(_row(raw, r.n_complaints, g, gk, score, "token_set_identical",
                            f"identical distinctive tokens {sorted(sig)} -> '{text}'"))
        elif (score >= AUTO_ACCEPT and len(shared) >= MIN_SHARED_TOKENS
              and jaccard >= MIN_TOKEN_JACCARD):
            g = hc_by_key.loc[gk]
            out.append(_row(raw, r.n_complaints, g, gk, score, "fuzzy_auto",
                            f"matched '{text}' on {sorted(shared)} (J={jaccard:.2f})"))
        elif score >= AUTO_ACCEPT and shared:
            out.append({**_blank(raw, r.n_complaints),
                        "match_method": "rejected_weak_token_overlap",
                        "match_score": round(score, 1),
                        "match_note": f"'{text}' scored {score:.0f} but distinctive "
                                      f"tokens overlap only J={jaccard:.2f} "
                                      f"({sorted(sig)} vs {sorted(cand_sig)}) -- rejected"})
        elif score >= AUTO_ACCEPT and not shared:
            # High character similarity but no distinctive token in common --
            # this is the OCWEN/OWEN class of false positive.
            out.append({**_blank(raw, r.n_complaints),
                        "match_method": "rejected_no_shared_token",
                        "match_score": round(score, 1),
                        "match_note": f"'{text}' scored {score:.0f} but shares no "
                                      f"distinctive token -- rejected as false positive"})
        elif score >= REVIEW_FLOOR:
            out.append({**_blank(raw, r.n_complaints), "match_method": "below_threshold",
                        "match_score": round(score, 1),
                        "match_note": f"best was '{text}' @ {score:.0f} -- rejected"})
        else:
            out.append({**_blank(raw, r.n_complaints), "match_method": "no_match",
                        "match_score": round(score, 1),
                        "match_note": f"best was '{text}' @ {score:.0f}"})

    return pd.DataFrame(out)


def _blank(company: str, n: int) -> dict:
    return {"company": company, "n_complaints": n, "matched": False,
            "group_key": None, "fdic_name": None, "total_assets_b": None,
            "n_charters": None, "match_score": None}


def _row(company: str, n: int, g, gk: str, score: float, method: str,
         note: str) -> dict:
    return {"company": company, "n_complaints": n, "matched": True,
            "group_key": gk, "fdic_name": g["group_name"],
            "total_assets_b": g["total_assets_b"],
            "n_charters": int(g["n_charters"]), "match_score": round(score, 1),
            "match_method": method, "match_note": note}


# --------------------------------------------------------------------------- #
def main() -> None:
    force = "--refresh-fdic" in sys.argv
    if not CLEAN_CSV.exists():
        sys.exit(f"missing {CLEAN_CSV} -- run scripts/02_clean.py first")

    banner("STAGE 3 -- FDIC ENRICHMENT")
    fdic = fetch_fdic(force)
    log(f"FDIC institutions: {len(fdic):,}")

    hc = build_holding_companies(fdic)
    hc.to_csv(HC_CSV, index=False)
    n_multi = int((hc["n_charters"] > 1).sum())
    n_indep = int((~hc["has_holding_company"]).sum())
    log(f"holding-company groups: {len(hc):,}  "
        f"({n_multi:,} multi-charter, {n_indep:,} independent banks kept separate)")
    log(f"total system assets: ${hc['total_assets_b'].sum():,.1f}B")

    banner("MATCHING CFPB COMPANIES -> FDIC")
    df = pd.read_csv(CLEAN_CSV, usecols=["company", "complaint_id", "is_resolved",
                                         "got_monetary_relief", "is_untimely",
                                         "in_trend_window", "days_to_company"])
    companies = (df.groupby("company", as_index=False)
                   .agg(n_complaints=("complaint_id", "count"))
                   .sort_values("n_complaints", ascending=False))
    log(f"distinct CFPB companies: {len(companies):,}")

    matches = match_companies(companies, hc, fdic)
    matches = matches.sort_values("n_complaints", ascending=False)
    matches.to_csv(MATCH_CSV, index=False)

    total_rows = int(companies["n_complaints"].sum())
    m = matches[matches["matched"]]
    u = matches[~matches["matched"]]
    rate_co = 100 * len(m) / len(matches)
    rate_vol = 100 * m["n_complaints"].sum() / total_rows

    banner("MATCH RATE")
    print(f"  by distinct company : {len(m):,} / {len(matches):,}  ({rate_co:.1f}%)")
    print(f"  by complaint volume : {m['n_complaints'].sum():,} / {total_rows:,}  "
          f"({rate_vol:.1f}%)   <- the one that matters")
    print()
    print("  breakdown by method:")
    for meth, sub in matches.groupby("match_method"):
        print(f"    {meth:<18} {len(sub):>5,} companies  "
              f"{sub['n_complaints'].sum():>8,} complaints "
              f"({100*sub['n_complaints'].sum()/total_rows:5.2f}%)")

    u_sorted = u.sort_values("n_complaints", ascending=False)
    u_sorted.to_csv(UNMATCHED_CSV, index=False)
    print("\n  TOP 15 UNMATCHED BY VOLUME (kept in all non-size-adjusted analysis):")
    for r in u_sorted.head(15).itertuples():
        print(f"    {r.n_complaints:>7,}  {str(r.company)[:46]:<46} "
              f"{str(r.match_note)[:44]}")

    # ---- company-level enriched table --------------------------------------
    banner("BUILDING COMPANY-LEVEL ENRICHED TABLE")
    res = df[df["is_resolved"]]
    agg = (df.groupby("company")
             .agg(total_complaints=("complaint_id", "count"),
                  complaints_in_trend_window=("in_trend_window", "sum"),
                  avg_days_to_company=("days_to_company", "mean"))
             .join(res.groupby("company").agg(
                 resolved_complaints=("complaint_id", "count"),
                 monetary_relief_n=("got_monetary_relief", "sum"),
                 untimely_n=("is_untimely", "sum")))
             .reset_index())
    agg["monetary_relief_rate"] = (
        100 * agg["monetary_relief_n"] / agg["resolved_complaints"]).round(3)
    agg["untimely_rate"] = (
        100 * agg["untimely_n"] / agg["resolved_complaints"]).round(3)
    agg["avg_days_to_company"] = agg["avg_days_to_company"].round(3)

    enriched = agg.merge(
        matches[["company", "matched", "fdic_name", "group_key", "total_assets_b",
                 "n_charters", "match_score", "match_method"]],
        on="company", how="left")
    enriched["complaints_per_1b_assets"] = (
        enriched["total_complaints"] / enriched["total_assets_b"]).round(3)
    enriched.loc[~enriched["matched"].fillna(False), "complaints_per_1b_assets"] = pd.NA

    # Counts must stay integers. The left join above introduces NaN for
    # companies with no resolved complaints, which silently promotes these
    # columns to float64 and writes '41078.0' to the CSV -- which then fails to
    # COPY into an INTEGER column in Stage 4. Nullable Int64 keeps the NULLs
    # while writing clean integers.
    for col in ["resolved_complaints", "monetary_relief_n", "untimely_n",
                "n_charters"]:
        enriched[col] = enriched[col].astype("Int64")
    enriched["matched"] = enriched["matched"].fillna(False).astype(bool)
    enriched = enriched.sort_values("total_complaints", ascending=False)
    enriched.to_csv(ENRICHED_CSV, index=False)
    log(f"wrote {ENRICHED_CSV.name}: {len(enriched):,} companies")

    # Plausibility sweep: a surviving false match shows up as an absurd ratio.
    # Reported, never silently corrected -- the point is that it is visible.
    IMPLAUSIBLE = 300
    sus = enriched[enriched["matched"].fillna(False)
                   & (enriched["complaints_per_1b_assets"] > IMPLAUSIBLE)]
    print(f"\n  PLAUSIBILITY SWEEP (> {IMPLAUSIBLE} complaints per $1B is not credible "
          f"for a real depository):")
    if sus.empty:
        print("    none -- no matched company has an implausible ratio")
    else:
        for r in sus.nlargest(10, "complaints_per_1b_assets").itertuples():
            print(f"    {r.complaints_per_1b_assets:>10,.1f}  {str(r.company)[:38]:<38} "
                  f"-> {str(r.fdic_name)[:30]:<30} ${r.total_assets_b:,.2f}B")

    MIN_VOL = 500
    rank = enriched[enriched["matched"].fillna(False)
                    & (enriched["total_complaints"] >= MIN_VOL)].copy()
    rank = rank.sort_values("complaints_per_1b_assets", ascending=False)
    print(f"\n  SIZE-ADJUSTED RISK, companies with >= {MIN_VOL} complaints "
          f"({len(rank)} qualify):")
    print(f"    {'complaints/$1B':>14}  {'volume':>8}  {'assets $B':>10}  company")
    for r in rank.head(15).itertuples():
        print(f"    {r.complaints_per_1b_assets:>14.2f}  {r.total_complaints:>8,}  "
              f"{r.total_assets_b:>10,.1f}  {str(r.company)[:40]}")

    # ---- FRED (optional) ----------------------------------------------------
    fred_key = os.getenv("FRED_API_KEY", "").strip()
    fred_note = (
        "Skipped. No `FRED_API_KEY` is configured, and with only 36 complete "
        "monthly observations a macro correlation would be underpowered and "
        "invite a spurious narrative. Excluded deliberately rather than "
        "reported weakly."
    ) if not fred_key else "Attempted -- see console output."
    log(f"FRED macro enrichment: {'skipped (no key)' if not fred_key else 'enabled'}")

    # ---- log ----------------------------------------------------------------
    top_multi = hc[hc["n_charters"] > 1].nlargest(8, "total_assets_k")
    multi_rows = "\n".join(
        f"| {r.group_name} | {int(r.n_charters)} | ${r.total_assets_b:,.1f}B | "
        f"${r.largest_charter_assets_k/1e6:,.1f}B | **{r.assets_understated_pct:.1f}%** |"
        for r in top_multi.itertuples())

    method_rows = "\n".join(
        f"| `{meth}` | {len(sub):,} | {sub['n_complaints'].sum():,} | "
        f"{100*sub['n_complaints'].sum()/total_rows:.2f}% |"
        for meth, sub in matches.groupby("match_method"))

    unmatched_rows = "\n".join(
        f"| {r.n_complaints:,} | {r.company} | {r.match_note or '—'} |"
        for r in u_sorted.head(20).itertuples())

    review_band = matches[matches["match_method"] == "below_threshold"].nlargest(
        12, "n_complaints")
    review_rows = "\n".join(
        f"| {r.n_complaints:,} | {r.company} | {r.match_note} |"
        for r in review_band.itertuples()) or "| — | _none_ | |"

    LOG_MD.write_text(f"""# Enrichment log -- Stage 3

*Generated by `scripts/03_enrich.py` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.*

**Source:** [FDIC BankFind Suite API](https://banks.data.fdic.gov/docs/) — public, no key.
Pulled {len(fdic):,} active insured institutions, cached to `data/raw/fdic_institutions.csv`.

## Why this stage exists

Complaint volume is a proxy for customer count, not for risk. The headline
metric — **complaints per $1B of total assets** — needs a denominator, and this
stage builds it.

## Rule 1: assets are aggregated at holding-company level

One CFPB company maps to one *holding company*, which may own several FDIC
charters. Summing across all of them is not a refinement — using only the
largest subsidiary materially understates the denominator and therefore
**inflates** the risk rate:

| Holding company | Charters | Total assets | Largest alone | Would understate by |
|---|---:|---:|---:|---:|
{multi_rows}

{n_multi:,} of {len(hc):,} groups hold more than one charter.

### The blank-`NAMEHCR` trap

{n_indep:,} insured institutions have **no** holding company. Grouping on the
blank `NAMEHCR` value would have fused {n_indep:,} unrelated independent banks
into a single fictional entity worth hundreds of billions, and any one of them
that matched a CFPB name would have inherited that absurd denominator. They are
keyed by their own `CERT` and stay individual.

## Rule 2: unmatched companies are reported, not dropped

Non-banks have no FDIC assets **by design**. They remain in every volume, trend
and resolution-rate analysis; they are excluded only from the size-adjusted
ranking.

## Match rate

| | Matched | Total | Rate |
|---|---:|---:|---:|
| By distinct company | {len(m):,} | {len(matches):,} | {rate_co:.1f}% |
| **By complaint volume** | {m['n_complaints'].sum():,} | {total_rows:,} | **{rate_vol:.1f}%** |

Volume-weighted is the honest figure: {len(matches):,} companies exist but the
top 50 carry ~80% of complaints, so a per-company rate understates coverage of
the data that actually drives the analysis.

| Method | Companies | Complaints | % of volume |
|---|---:|---:|---:|
{method_rows}

### Matching approach

Candidates are **both** the holding-company name and every subsidiary charter
name, because CFPB sometimes names the parent (`U.S. BANCORP`) and sometimes the
bank (`DISCOVER BANK`). FDIC abbreviations (`BCORP`, `FINL`, `NATL`, `SVGS`) are
expanded before scoring, and `rapidfuzz.token_sort_ratio` is used with an
auto-accept floor of **{AUTO_ACCEPT}**.

**The threshold is deliberately strict.** A wrong match silently attaches the
wrong denominator and produces a confidently wrong risk rate; no match merely
omits the company from one ranking. Candidates scoring {REVIEW_FLOOR}–{AUTO_ACCEPT}
are **rejected**, not accepted, and listed below for manual review.

### Why character similarity alone is not enough

Fuzzy matching on names produces confident, invisible errors. Every guard below
was added in response to a specific false positive found by reviewing output,
not designed up front:

| False match found | Score | Why it happened | Guard added |
|---|---:|---|---|
| `Ocwen Financial Corporation` → `OWEN FINANCIAL CORP` ($0.4B) | 96.6 | One missing letter. Produced **7,923 complaints per $1B** | Require ≥1 *exact* distinctive-token overlap |
| `Bank of America` → *rejected* | 100 | Over-correction: every token (`BANK`,`OF`,`AMERICA`,`NATIONAL`,`ASSOCIATION`) is generic, so it had no distinctive token to share | Accept an **exact normalised string** match regardless |
| `MECHANICS BANK` → `Farmers and Mechanics Federal` | 92+ | Shares the single token `MECHANICS` | Require token-set Jaccard ≥ {MIN_TOKEN_JACCARD} |
| `Paramount GR Holdings` → `PARAMOUNT FINANCIAL GROUP` | 92+ | Identical *one*-token sets | Require ≥ {MIN_SHARED_TOKENS} shared distinctive tokens |
| `FIFTH THIRD FINANCIAL` → `PATHWARD FINANCIAL` | — | The correct candidate existed but a wrong one outscored it | Apply the token rule as a **filter over the top 25 candidates**, not a check on the top 1 |

The cost of this strictness is a lower automated match rate. That is the right
trade: `exact_normalised` and curated overrides already carry **~99% of matched
complaint volume**, so the fuzzy paths were contributing well under 1% of volume
while generating every false positive above.

A final **plausibility sweep** flags any matched company exceeding 300
complaints per $1B — a ratio no real depository can produce. It currently
returns nothing, and it is reported rather than auto-corrected so that a future
regression is visible instead of silent.

### Rejected near-misses (scored {REVIEW_FLOOR}–{AUTO_ACCEPT}, treated as unmatched)

| Complaints | Company | Best candidate |
|---:|---|---|
{review_rows}

## Unmatched but high-volume — a finding in itself

These are large complaint generators with no FDIC denominator. That they are
*structurally* outside prudential asset regulation is itself worth stating.

| Complaints | Company | Reason |
|---:|---|---|
{unmatched_rows}

## FRED macro enrichment

{fred_note}

## Outputs

| File | Contents |
|---|---|
| `data/raw/fdic_institutions.csv` | Cached FDIC pull ({len(fdic):,} rows), never modified |
| `data/processed/fdic_holding_companies.csv` | {len(hc):,} holding-company groups with summed assets |
| `data/processed/company_fdic_match.csv` | Every CFPB company with its match, score and method |
| `data/processed/unmatched_companies.csv` | The {len(u):,} unmatched, ranked by volume |
| `data/processed/company_enriched.csv` | Company-level table feeding Stages 4–7 |
""", encoding="utf-8")
    log(f"wrote {LOG_MD.relative_to(PROJECT_ROOT)}")
    print("\nSTAGE 3 COMPLETE")


if __name__ == "__main__":
    main()
