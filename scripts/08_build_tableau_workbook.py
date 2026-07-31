"""
Stage 7b -- Generate a ready-built Tableau workbook.

Writes dashboard/banking_complaints_dashboard.twb: four worksheets plus an
assembled dashboard, already wired to dashboard/banking_complaints.hyper.

Open it in Tableau and everything renders. No manual chart building, no
relationship dialogs, no shelf dragging.

WHY THIS EXISTS
---------------
A .twb is plain XML. Everything the build guide asks you to do by hand -- put
Company on Rows, AVG(Complaints Per 1B Assets) on Columns, Rank Gap on Colour,
filter to FDIC-matched, sort descending, take the top 15 -- is a few lines of
markup. Generating it removes ~60 minutes of clicking and, more importantly,
makes the dashboard reproducible: re-run this script and you get the identical
workbook, rather than whatever you remembered to click that day.

The hand-build path in dashboard/TABLEAU_BUILD_GUIDE.md still stands, and is
worth doing once to understand what the XML encodes.

IMPORTANT -- each table needs its OWN datasource
------------------------------------------------
`company_summary` (one row per company) and `monthly_trend` (one row per
product-month) share no column, so they cannot be related. Dropping both onto a
single canvas makes Tableau demand a relationship it cannot form. This script
therefore emits one independent federated datasource per table, which is the
correct model for unrelated tables.

USAGE
-----
    python scripts/07_tableau_handoff.py        # first: build the .hyper
    python scripts/08_build_tableau_workbook.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASH = PROJECT_ROOT / "dashboard"
HYPER = DASH / "banking_complaints.hyper"
OUT = DASH / "banking_complaints_dashboard.twb"

# Tableau needs a forward-slash absolute path.
HYPER_PATH = str(HYPER.resolve()).replace("\\", "/")

TABLES = ["company_summary", "monthly_trend", "state_summary", "top_issues_by_product"]

# pandas dtype kind -> (Tableau datatype, default role, default type)
DTYPE_MAP = {
    "i": ("integer", "measure", "quantitative"),
    "f": ("real", "measure", "quantitative"),
    "b": ("boolean", "dimension", "nominal"),
    "M": ("date", "dimension", "ordinal"),
    "O": ("string", "dimension", "nominal"),
}
DATE_COLUMNS = {"monthly_trend": ["month_start"],
                "company_summary": ["first_complaint", "last_complaint"]}
# Numeric columns that are really identifiers/ranks, not things to sum.
FORCE_DIMENSION = {"year_month", "state", "company", "product", "product_short",
                   "issue", "risk_tier", "fdic_status", "fdic_name"}


def caption(col: str) -> str:
    """Tableau's own field-name prettifier: snake_case -> Title Case."""
    return " ".join(w.capitalize() if not w.isupper() else w for w in col.split("_"))


def a(v) -> str:
    return quoteattr(str(v))


class DS:
    """One federated datasource bound to a single table inside the .hyper."""

    def __init__(self, table: str, df: pd.DataFrame, idx: int):
        self.table = table
        self.df = df
        self.name = f"federated.{table}_ds{idx}"
        self.conn = f"hyper.{table}_conn{idx}"
        self.caption = f"{table}"
        self.cols: dict[str, tuple[str, str, str]] = {}
        dates = DATE_COLUMNS.get(table, [])
        for c in df.columns:
            if c in dates:
                self.cols[c] = ("date", "dimension", "ordinal")
                continue
            kind = df[c].dtype.kind
            dt, role, typ = DTYPE_MAP.get(kind, ("string", "dimension", "nominal"))
            if c in FORCE_DIMENSION:
                role, typ = "dimension", "nominal"
            self.cols[c] = (dt, role, typ)

    def ref(self, instance: str) -> str:
        """Fully-qualified field reference.

        `instance` already carries its own brackets (inst() returns
        '[avg:col:qk]'), so this must NOT add another pair -- doing so emits
        '[ds].[[avg:col:qk]]', which Tableau silently fails to resolve and the
        sheet opens blank.
        """
        assert instance.startswith("[") and instance.endswith("]"), instance
        return f"[{self.name}].{instance}"

    def xml(self) -> str:
        parts = [
            f"    <datasource caption={a(self.caption)} inline='true' "
            f"name={a(self.name)} version='18.1'>",
            "      <connection class='federated'>",
            "        <named-connections>",
            f"          <named-connection caption='banking_complaints' name={a(self.conn)}>",
            f"            <connection authentication='auth-none' author-locale='en_US' "
            f"class='hyper' dbname={a(HYPER_PATH)} default-settings='yes' server='' "
            f"sslmode='' username='tableau_internal_user' />",
            "          </named-connection>",
            "        </named-connections>",
            f"        <relation connection={a(self.conn)} name={a(self.table)} "
            f"table={a(f'[Extract].[{self.table}]')} type='table' />",
            "      </connection>",
        ]
        for c, (dt, role, typ) in self.cols.items():
            semantic = ""
            if self.table == "state_summary" and c == "state":
                semantic = " semantic-role='[State].[Name]'"
            parts.append(
                f"      <column caption={a(caption(c))} datatype={a(dt)} "
                f"name={a(f'[{c}]')} role={a(role)} type={a(typ)}{semantic} />")
        parts.append("    </datasource>")
        return "\n".join(parts)


def inst(col: str, deriv: str, kind: str) -> str:
    """Build a Tableau column-instance name, e.g. [avg:total_complaints:qk]."""
    prefix = {"None": "none", "Sum": "sum", "Avg": "avg",
              "Month-Trunc": "tmn", "Year-Trunc": "tyr"}[deriv]
    return f"[{prefix}:{col}:{kind}]"


def dep_block(ds: DS, cols: list[str], instances: list[tuple[str, str, str]]) -> str:
    """<datasource-dependencies>: declare every column and instance a sheet uses."""
    out = [f"          <datasource-dependencies datasource={a(ds.name)}>"]
    for c in sorted(set(cols)):
        dt, role, typ = ds.cols[c]
        semantic = ""
        if ds.table == "state_summary" and c == "state":
            semantic = " semantic-role='[State].[Name]'"
        out.append(f"            <column caption={a(caption(c))} datatype={a(dt)} "
                   f"name={a(f'[{c}]')} role={a(role)} type={a(typ)}{semantic} />")
    for col, deriv, kind in instances:
        typ = "quantitative" if kind == "qk" else "nominal"
        if deriv in ("Month-Trunc", "Year-Trunc"):
            typ = "quantitative"
        out.append(f"            <column-instance column={a(f'[{col}]')} "
                   f"derivation={a(deriv)} name={a(inst(col, deriv, kind))} "
                   f"pivot='key' type={a(typ)} />")
    out.append("          </datasource-dependencies>")
    return "\n".join(out)


def worksheet(name: str, ds: DS, *, rows: str, cols: str, mark: str,
              used_cols: list[str], instances: list[tuple[str, str, str]],
              encodings: list[str] = (), filters: str = "",
              slices: list[str] = (), extra_style: str = "",
              sort: str = "") -> str:
    return f"""    <worksheet name={a(name)}>
      <table>
        <view>
          <datasources>
            <datasource caption={a(ds.caption)} name={a(ds.name)} />
          </datasources>
{dep_block(ds, used_cols, instances)}
{filters}{sort}          <slices>
{chr(10).join(f'            <column>{escape(s)}</column>' for s in slices)}
          </slices>
        </view>
        <style>
{extra_style}        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class={a(mark)} />
            <encodings>
{chr(10).join(encodings)}
            </encodings>
          </pane>
        </panes>
        <rows>{escape(rows)}</rows>
        <cols>{escape(cols)}</cols>
      </table>
    </worksheet>"""


def main() -> None:
    if not HYPER.exists():
        sys.exit(f"missing {HYPER}\n  run: python scripts/07_tableau_handoff.py "
                 f"(close Tableau first if it has the file open)")

    frames, dss = {}, {}
    for i, t in enumerate(TABLES, start=1):
        csv = DASH / f"{t}.csv"
        if not csv.exists():
            sys.exit(f"missing {csv} -- run scripts/07_tableau_handoff.py first")
        df = pd.read_csv(csv)
        for c in DATE_COLUMNS.get(t, []):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        frames[t], dss[t] = df, DS(t, df, i)
        print(f"  {t:<24} {len(df):>6,} rows, {len(df.columns)} cols")

    cs, mt, ss = dss["company_summary"], dss["monthly_trend"], dss["state_summary"]

    # ---------------- Sheet 1: size-adjusted risk ---------------------------
    top_n = 15
    matched = frames["company_summary"]
    matched = matched[matched.is_fdic_matched.astype(str).str.lower().isin(["true", "1"])]
    members = "\n".join(
        f"                  <groupfilter function='member' "
        f"level='[none:company:nk]' member={a(chr(34) + str(c) + chr(34))} />"
        for c in sorted(matched.company.dropna().unique()))

    s1_filters = f"""          <filter class='categorical' column={a(cs.ref('[none:company:nk]'))}>
            <groupfilter count='{top_n}' end='top' function='end' units='records' user:ui-marker='end' user:ui-top-by-field='true'>
              <groupfilter direction='DESC' expression='MAX([complaints_per_1b_assets])' function='order' user:ui-marker='order'>
                <groupfilter function='union' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate'>
{members}
                </groupfilter>
              </groupfilter>
            </groupfilter>
          </filter>
          <filter class='quantitative' column={a(cs.ref('[none:complaints_per_1b_assets:qk]'))} included-values='non-null' />
          <filter class='categorical' column={a(cs.ref('[none:is_fdic_matched:nk]'))}>
            <groupfilter function='member' level='[none:is_fdic_matched:nk]' member='true' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />
          </filter>
"""
    s1_sort = (f"          <natural-sort column={a(cs.ref('[none:company:nk]'))} "
               f"direction='DESC' />\n")
    s1_style = (f"          <style-rule element='mark'>\n"
                f"            <encoding attr='color' center='0.0' "
                f"field={a(cs.ref('[none:rank_gap:qk]'))} "
                f"palette='red_blue_diverging_10_0' reverse='true' type='interpolated' />\n"
                f"          </style-rule>\n")
    sheet1 = worksheet(
        "1. Size-Adjusted Risk", cs,
        rows=cs.ref("[none:company:nk]"),
        cols=cs.ref("[avg:complaints_per_1b_assets:qk]"),
        mark="Bar",
        used_cols=["company", "complaints_per_1b_assets", "is_fdic_matched",
                   "rank_gap", "total_complaints", "total_assets_b",
                   "volume_rank", "size_adjusted_rank", "monetary_relief_rate",
                   "untimely_rate", "fdic_status"],
        instances=[("company", "None", "nk"),
                   ("complaints_per_1b_assets", "None", "qk"),
                   ("complaints_per_1b_assets", "Avg", "qk"),
                   ("is_fdic_matched", "None", "nk"),
                   ("rank_gap", "None", "qk")],
        encodings=[f"              <color column={a(cs.ref('[none:rank_gap:qk]'))} />",
                   f"              <text column={a(cs.ref('[avg:complaints_per_1b_assets:qk]'))} />"],
        filters=s1_filters, sort=s1_sort, extra_style=s1_style,
        slices=[cs.ref("[none:is_fdic_matched:nk]"),
                cs.ref("[none:complaints_per_1b_assets:qk]"),
                cs.ref("[none:company:nk]")])

    # ---------------- Sheet 2: monthly trend --------------------------------
    sheet2 = worksheet(
        "2. Monthly Trend", mt,
        rows=mt.ref("[sum:complaints:qk]"),
        cols=mt.ref("[tmn:month_start:qk]"),
        mark="Line",
        used_cols=["month_start", "complaints", "product_short", "product",
                   "monetary_relief_rate", "untimely_rate"],
        instances=[("month_start", "Month-Trunc", "qk"),
                   ("complaints", "Sum", "qk"),
                   ("product_short", "None", "nk")],
        encodings=[f"              <color column={a(mt.ref('[none:product_short:nk]'))} />"],
        slices=[mt.ref("[none:product_short:nk]")])

    # ---------------- Sheet 3: resolution scatter ---------------------------
    sheet3 = worksheet(
        "3. Resolution Quality", cs,
        rows=cs.ref("[avg:untimely_rate:qk]"),
        cols=cs.ref("[avg:monetary_relief_rate:qk]"),
        mark="Circle",
        used_cols=["company", "monetary_relief_rate", "untimely_rate",
                   "total_complaints", "risk_tier", "pct_no_relief",
                   "conduct_risk_score", "resolved_complaints"],
        instances=[("monetary_relief_rate", "Avg", "qk"),
                   ("untimely_rate", "Avg", "qk"),
                   ("total_complaints", "Sum", "qk"),
                   ("company", "None", "nk"),
                   ("risk_tier", "None", "nk")],
        encodings=[f"              <color column={a(cs.ref('[none:risk_tier:nk]'))} />",
                   f"              <size column={a(cs.ref('[sum:total_complaints:qk]'))} />",
                   f"              <lod column={a(cs.ref('[none:company:nk]'))} />"],
        slices=[cs.ref("[none:company:nk]"), cs.ref("[none:risk_tier:nk]")])

    # ---------------- Sheet 4: state map ------------------------------------
    sheet4 = worksheet(
        "4. By State", ss,
        rows="[federated.state_summary_ds3].[none:Latitude (generated):qk]",
        cols="[federated.state_summary_ds3].[none:Longitude (generated):qk]",
        mark="Map",
        used_cols=["state", "complaints", "monetary_relief_rate", "untimely_rate",
                   "top_issue", "top_product", "companies"],
        instances=[("state", "None", "nk"), ("complaints", "Sum", "qk")],
        encodings=[f"              <color column={a(ss.ref('[sum:complaints:qk]'))} />",
                   f"              <lod column={a(ss.ref('[none:state:nk]'))} />"],
        slices=[ss.ref("[none:state:nk]")])

    # ---------------- Dashboard --------------------------------------------
    def zone(sheet, x, y, w, h):
        return (f"          <zone h='{h}' id='{abs(hash(sheet)) % 900 + 20}' "
                f"name={a(sheet)} w='{w}' x='{x}' y='{y}' />")

    dashboard = f"""    <dashboard name='Dashboard'>
      <style />
      <size maxheight='900' maxwidth='1600' minheight='900' minwidth='1600' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          <zone h='8000' id='2' param='vert' type-v2='title' w='100000' x='0' y='0' />
          <zone h='46000' id='3' type-v2='layout-flow' w='100000' x='0' y='8000'>
{zone('1. Size-Adjusted Risk', 0, 8000, 50000, 46000)}
{zone('2. Monthly Trend', 50000, 8000, 50000, 46000)}
          </zone>
          <zone h='46000' id='6' type-v2='layout-flow' w='100000' x='0' y='54000'>
{zone('3. Resolution Quality', 0, 54000, 50000, 46000)}
{zone('4. By State', 50000, 54000, 50000, 46000)}
          </zone>
        </zone>
      </zones>
    </dashboard>"""

    sheets = [sheet1, sheet2, sheet3, sheet4]
    ds_xml = "\n".join(d.xml() for d in dss.values())

    twb = f"""<?xml version='1.0' encoding='utf-8' ?>

<!-- Generated by scripts/08_build_tableau_workbook.py -->
<workbook original-version='18.1' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{ds_xml}
  </datasources>
  <worksheets>
{chr(10).join(sheets)}
  </worksheets>
  <dashboards>
{dashboard}
  </dashboards>
  <windows source-height='30'>
{chr(10).join(f"    <window class='worksheet' name={a(s)} />" for s in ['1. Size-Adjusted Risk', '2. Monthly Trend', '3. Resolution Quality', '4. By State'])}
    <window class='dashboard' maximized='true' name='Dashboard'>
      <viewpoints>
{chr(10).join(f"        <viewpoint name={a(s)} />" for s in ['1. Size-Adjusted Risk', '2. Monthly Trend', '3. Resolution Quality', '4. By State'])}
      </viewpoints>
    </window>
  </windows>
</workbook>
"""

    OUT.write_text(twb, encoding="utf-8")

    # Fail loudly rather than shipping a file Tableau will reject.
    import xml.etree.ElementTree as ET
    try:
        ET.parse(OUT)
    except ET.ParseError as exc:
        sys.exit(f"generated XML is malformed: {exc}")

    print(f"\n  wrote {OUT.name}  ({OUT.stat().st_size/1024:.0f} KB)")
    print(f"  XML validates. Points at {HYPER_PATH}")
    print("\n  Open it:  dashboard\\banking_complaints_dashboard.twb")
    print("  Sheets: 1. Size-Adjusted Risk | 2. Monthly Trend | "
          "3. Resolution Quality | 4. By State | Dashboard")


if __name__ == "__main__":
    main()
