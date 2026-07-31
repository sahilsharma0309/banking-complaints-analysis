"""
Generate the Hinglish project handbook PDF (interview preparation document).

Builds rich HTML, embeds the Stage 5 figures as base64, then renders to PDF via
headless Chrome. Output: reports/PROJECT_HANDBOOK.pdf

    python scripts/09_build_project_pdf.py
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "reports" / "figures"
OUT_HTML = ROOT / "reports" / "_handbook.html"
OUT_PDF = ROOT / "reports" / "PROJECT_HANDBOOK.pdf"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def img(name: str) -> str:
    p = FIGS / name
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" />'


CSS = """
@page { size: A4; margin: 14mm 13mm 16mm 13mm; }
@page:first { margin: 0; }
* { box-sizing: border-box; }
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:#1a2233;
     font-size:10.2pt;line-height:1.62;margin:0;}
h1,h2,h3,h4{line-height:1.25;margin:0 0 .45em;}
p{margin:0 0 .7em;}
code{font-family:Consolas,'Courier New',monospace;background:#eef2f9;color:#1e3a8a;
     padding:1px 5px;border-radius:4px;font-size:.88em;}
a{color:#2563eb;text-decoration:none;}

/* ---------- cover ---------- */
.cover{height:297mm;background:linear-gradient(150deg,#0f172a 0%,#1e3a8a 45%,#4c1d95 100%);
       color:#fff;padding:26mm 20mm;position:relative;page-break-after:always;}
.cover .kicker{font-size:11pt;letter-spacing:.32em;text-transform:uppercase;
       color:#a5b4fc;font-weight:600;margin-bottom:14mm;}
.cover h1{font-size:33pt;font-weight:800;letter-spacing:-.5pt;margin-bottom:6mm;}
.cover .sub{font-size:14pt;color:#c7d2fe;font-weight:400;margin-bottom:16mm;line-height:1.5;}
.cover .rule{width:52mm;height:5px;background:linear-gradient(90deg,#fbbf24,#f472b6);
       border-radius:3px;margin-bottom:12mm;}
.statgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:5mm;margin-bottom:12mm;}
.stat{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.20);
      border-radius:9px;padding:5mm;}
.stat .n{font-size:19pt;font-weight:800;color:#fde68a;display:block;line-height:1.1;}
.stat .l{font-size:8.4pt;color:#c7d2fe;margin-top:2mm;display:block;}
.cover .foot{position:absolute;bottom:22mm;left:20mm;right:20mm;font-size:9.5pt;
      color:#a5b4fc;border-top:1px solid rgba(255,255,255,.22);padding-top:5mm;}
.chips span{display:inline-block;background:rgba(255,255,255,.14);border-radius:20px;
      padding:2mm 4mm;font-size:8.6pt;margin:0 2mm 2mm 0;color:#e0e7ff;}

/* ---------- structure ---------- */
.section{page-break-before:always;}
.sechead{border-left:7px solid #4f46e5;padding:1mm 0 1mm 5mm;margin-bottom:6mm;}
.sechead .num{font-size:8.6pt;letter-spacing:.22em;color:#7c3aed;font-weight:700;
      text-transform:uppercase;}
.sechead h2{font-size:20pt;font-weight:800;color:#0f172a;margin:1mm 0 0;}
h3{font-size:13pt;color:#1e3a8a;margin-top:7mm;border-bottom:2px solid #e0e7ff;
   padding-bottom:1.5mm;}
h4{font-size:10.8pt;color:#4338ca;margin-top:5mm;}

/* ---------- boxes ---------- */
.box{border-radius:9px;padding:4mm 5mm;margin:4mm 0;page-break-inside:avoid;}
.box .t{font-weight:800;font-size:9.6pt;letter-spacing:.05em;margin-bottom:2mm;
        text-transform:uppercase;}
.say{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border-left:5px solid #059669;}
.say .t{color:#047857;}
.bug{background:linear-gradient(135deg,#fef2f2,#fee2e2);border-left:5px solid #dc2626;}
.bug .t{color:#b91c1c;}
.why{background:linear-gradient(135deg,#fffbeb,#fef3c7);border-left:5px solid #d97706;}
.why .t{color:#b45309;}
.info{background:linear-gradient(135deg,#eff6ff,#dbeafe);border-left:5px solid #2563eb;}
.info .t{color:#1d4ed8;}
.tip{background:linear-gradient(135deg,#faf5ff,#f3e8ff);border-left:5px solid #7c3aed;}
.tip .t{color:#6d28d9;}

/* ---------- tables ---------- */
table{width:100%;border-collapse:collapse;margin:3.5mm 0;font-size:9pt;
      page-break-inside:avoid;}
th{background:#1e3a8a;color:#fff;text-align:left;padding:2.2mm 3mm;font-weight:600;
   font-size:8.6pt;}
td{padding:2mm 3mm;border-bottom:1px solid #e2e8f0;vertical-align:top;}
tr:nth-child(even) td{background:#f8fafc;}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;}
.hi{background:#fef3c7 !important;font-weight:700;}

/* ---------- code ---------- */
pre{background:#0f172a;color:#e2e8f0;padding:4mm;border-radius:8px;font-size:8.1pt;
    line-height:1.5;overflow:hidden;white-space:pre-wrap;margin:3mm 0;
    font-family:Consolas,'Courier New',monospace;page-break-inside:avoid;
    border-left:4px solid #6366f1;}
pre .c{color:#7dd3fc;}
pre .k{color:#f472b6;}
pre .s{color:#86efac;}
pre .m{color:#64748b;font-style:italic;}

/* ---------- misc ---------- */
img{max-width:100%;border:1px solid #cbd5e1;border-radius:7px;margin:3mm 0;}
.two{display:grid;grid-template-columns:1fr 1fr;gap:4mm;}
.pill{display:inline-block;background:#4f46e5;color:#fff;border-radius:20px;
      padding:1mm 3.5mm;font-size:8pt;font-weight:700;}
.toc{background:#f8fafc;border:1px solid #e2e8f0;border-radius:9px;padding:5mm 6mm;}
.toc div{padding:1.4mm 0;border-bottom:1px dotted #cbd5e1;font-size:9.6pt;}
.toc b{color:#4f46e5;display:inline-block;width:14mm;}
.big{font-size:15pt;font-weight:800;color:#4f46e5;}
ul,ol{margin:0 0 .7em;padding-left:5mm;}
li{margin-bottom:1.6mm;}
.qa{border:1px solid #e0e7ff;border-radius:9px;margin:4mm 0;overflow:hidden;
    page-break-inside:avoid;}
.qa .q{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:3mm 4mm;
       font-weight:700;font-size:10pt;}
.qa .ans{padding:3.5mm 4mm;background:#fff;}
.flow{display:flex;gap:2mm;margin:4mm 0;flex-wrap:wrap;}
.flow div{flex:1;min-width:26mm;background:linear-gradient(135deg,#eef2ff,#e0e7ff);
   border:1px solid #c7d2fe;border-radius:7px;padding:3mm 2mm;text-align:center;font-size:8.2pt;}
.flow div b{display:block;color:#4338ca;font-size:9pt;margin-bottom:1mm;}
"""


def stage_block(num, title, what, why, how, code, result, say):
    code_html = f"<pre>{code}</pre>" if code else ""
    return f"""
<h3><span class="pill">STAGE {num}</span> &nbsp;{title}</h3>
<h4>Kya kiya?</h4>{what}
<div class="box why"><div class="t">Kyun kiya — ye decision important tha</div>{why}</div>
<h4>Kaise kiya — technical detail</h4>{how}
{code_html}
<h4>Result</h4>{result}
<div class="box say"><div class="t">Interview mein aise bolna</div>{say}</div>
"""


# NOTE: these are built OUTSIDE the big f-string below. Their arguments contain
# backslashes (\\n inside the code samples), and Python 3.11 forbids a backslash
# inside an f-string expression -- inlining the calls raises
# "SyntaxError: f-string expression part cannot include a backslash".
STAGE_0 = stage_block(
    0, "Project setup, Git, environment",
    "<p>Folder structure banaya, existing GitHub repo se connect kiya, Python virtual environment "
    "banaya, <code>.gitignore</code> configure kiya, aur <code>.env</code> se secrets alag kiye.</p>",
    "<p>Sabse important cheez: repo pehle se exist karta tha aur usme ek commit tha. Agar main "
    "<code>git init</code> karke naya history banata toh <b>duplicate/conflicting history</b> ban "
    "jaati. Isliye maine <code>fetch</code> karke existing <code>origin/main</code> ko track kiya — "
    "purani history preserve rahi.</p>"
    "<p>Doosra: <code>.gitignore</code> mein raw data block kiya. 176 MB ka complaints.csv aur "
    "405 MB ka narratives file kabhi GitHub pe nahi gaya. Sirf ek 1,000-row sample commit kiya "
    "taaki reviewer schema dekh sake.</p>",
    "<p>Python 3.11 pe venv banaya (3.14 default tha, lekin uspe libraries ke wheels nahi the). "
    "111 packages install kiye aur <code>requirements-lock.txt</code> generate kiya — matlab exact "
    "versions record kiye taaki koi aur bhi bilkul same environment bana sake.</p>",
    "<span class='m'>Verify kiya ki gitignore sach mein kaam kar raha hai:</span>\n"
    "$ git add --dry-run data/raw/complaints.csv\n"
    "  <span class='s'>The following paths are ignored by .gitignore   BLOCKED</span>\n\n"
    "$ git add --dry-run data/sample_1000.csv\n"
    "  <span class='s'>add 'data/sample_1000.csv'                      ALLOWED</span>",
    "<p>Clean repo, reproducible environment, aur secrets safe. Poore project mein ek baar bhi "
    "password ya raw data GitHub pe nahi gaya — maine end mein <code>git log -p --all</code> se "
    "verify bhi kiya.</p>",
    "<p>\"Maine environment ko reproducible banane pe focus kiya. Interpreter version pin kiya, "
    "lock file banayi, aur gitignore ko sirf likha nahi — <b>test kiya</b>. Maine actually try kiya "
    "ki raw data commit ho paata hai ya nahi, aur confirm kiya ki block ho raha hai. Ye habit "
    "isliye important hai kyunki agar data ya password ek baar Git history mein chala gaya toh use "
    "hatana bahut painful hota hai.\"</p>")

STAGE_1 = stage_block(
    1, "Data acquisition — CFPB API se 6.24 lakh rows",
    "<p>CFPB ke public API se filtered data pull kiya. Full bulk download 5–6 GB ka hai — wo "
    "deliberately avoid kiya. Pagination, retry logic, aur checkpoint system banaya.</p>",
    "<p>Yahan project ka sabse bada <b>scope decision</b> aaya. Date range mein <b>94,78,443</b> "
    "complaints the. Lekin unme se <b>82,30,677 (87%)</b> credit reporting ke the — Equifax, "
    "Experian, TransUnion ke against.</p>"
    "<p>Ye credit bureaus <b>banks nahi hain</b>. Inke paas FDIC assets nahi hote. Matlab inka "
    "size-adjusted metric calculate hi nahi ho sakta. Aur 87% hone ki wajah se ye har chart, har "
    "product breakdown, har trend ko dabaa dete.</p>"
    "<p>Isliye maine sirf <b>banking &amp; lending products</b> rakhe — 10 categories jo koi bank "
    "ya lender actually bechta hai. Result: 94 lakh se 6.24 lakh rows.</p>",
    "<p><b>Pagination:</b> API ka <code>frm</code> offset parameter page 1 ke baad silently ignore "
    "ho jaata hai. Isliye Elasticsearch ka <code>search_after</code> cursor use karna pada — "
    "previous page ke last record ka sort value next request mein bhejte hain.</p>"
    "<p><b>Retry:</b> Exponential backoff with jitter — fail hone pe 2, 4, 8, 16 seconds wait, "
    "plus random jitter taaki saare retries ek saath na ho.</p>"
    "<p><b>Checkpoint:</b> Har page ke baad cursor file mein save karta hoon. Agar download beech "
    "mein ruk jaye toh dobara chalane pe wahin se resume hota hai, zero se nahi.</p>"
    "<p><b>Narrative split:</b> Complaint ka free-text 70% payload tha. Usko alag file mein "
    "<code>complaint_id</code> ke saath rakha — main table lean rahi (176 MB vs 580 MB).</p>",
    "<span class='m'># search_after cursor — previous page ke sort values se banta hai</span>\n"
    "<span class='k'>if</span> cursor:\n"
    "    params[<span class='s'>\"search_after\"</span>] = cursor\n\n"
    "<span class='m'># Response se next cursor nikalna</span>\n"
    "cursor = <span class='s'>\"_\"</span>.join(<span class='k'>str</span>(v) "
    "<span class='k'>for</span> v <span class='k'>in</span> hits[-<span class='c'>1</span>]"
    "[<span class='s'>\"sort\"</span>])\n\n"
    "<span class='m'># Exponential backoff + jitter</span>\n"
    "sleep_for = BACKOFF_BASE ** attempt + random.uniform(<span class='c'>0</span>, "
    "<span class='c'>1.5</span>)",
    "<p><b>6,24,727 rows</b> — API ke reported total se bilkul exact match. 13/13 acceptance checks "
    "pass: zero duplicate IDs, zero unparsed dates, har product ka count scope table se match.</p>",
    "<p>\"Sabse important decision scope ka tha. 94 lakh rows available the, lekin 87% credit "
    "reporting complaints the jo credit bureaus ke against hain — wo banks hain hi nahi. Agar main "
    "unhe rakhta toh mera headline metric — complaints per $1B assets — un companies ke liye "
    "calculate hi nahi ho paata, aur wo baaki sab data ko dabaa dete. Isliye maine banking products "
    "pe scope kiya. Ye analysis ko kamzor nahi, <b>zyada valid</b> banata hai — aur maine ye README "
    "mein clearly document kiya hai ki kya exclude kiya aur kyun.\"</p>"
    "<p>\"Technically, do cheezein interesting thi. Ek — API ka <code>frm</code> offset page 1 ke "
    "baad kaam nahi karta, toh <code>search_after</code> cursor use karna pada. Do — "
    "<code>format=json</code> bhejne se API export endpoint pe chala jaata hai jiski 1 lakh rows ki "
    "limit hai. Wo parameter hatate hi problem solve ho gayi. Ye dono maine documentation se nahi, "
    "<b>experiment karke</b> discover kiye.\"</p>")

STAGE_4 = stage_block(
    4, "Typed warehouse, bulk load, indexes, 6 analysis queries",
    "<p>Database banaya, typed tables define kiye, COPY se bulk load kiya, 9 indexes banaye, "
    "integrity checks chalaye, aur 6 SQL analysis files likhi.</p>",
    "<p><b>Types declare kiye, infer nahi kiye.</b> Sab kuch TEXT rakhna kaam kar jaata lekin galat "
    "hota — date arithmetic, BETWEEN filters, AVG(), boolean predicates sabko real types chahiye. "
    "Aur Tableau column types dekh ke decide karta hai ki kya measure hai aur kya dimension.</p>",
    "<p><b>COPY vs INSERT:</b> 6.24 lakh rows row-by-row INSERT se minutes lagte. PostgreSQL ka "
    "COPY command poori CSV ko ek hi statement mein stream kar deta hai. psycopg2 mein "
    "<code>copy_expert</code> se ye expose hota hai — file Python mein parse hoti hi nahi.</p>"
    "<p><b>Indexes:</b> company, product, state, date pe single-column, plus do composite indexes jo "
    "actual query shapes se match karte hain: <code>(company, is_resolved, in_trend_window)</code> "
    "aur <code>(product, year_month)</code>.</p>",
    "<span class='m'># Fast bulk load — 36,700 rows/second</span>\n"
    "copy_sql = <span class='s'>f\"COPY {SCHEMA}.{name} ({cols}) FROM STDIN \"</span>\n"
    "           <span class='s'>f\"WITH (FORMAT csv, HEADER true, NULL '')\"</span>\n\n"
    "<span class='k'>with</span> csv_path.open(<span class='s'>\"r\"</span>, "
    "encoding=<span class='s'>\"utf-8\"</span>) <span class='k'>as</span> fh:\n"
    "    cur.copy_expert(copy_sql, fh)   <span class='m'># file Python mein parse hi nahi hoti</span>",
    "<p><b>6,34,961 rows load hue 17 seconds mein — 36,700 rows/second.</b> 7/7 integrity checks "
    "pass: row count, unique IDs, zip3 leading zeros, DATE/BOOLEAN types (information_schema se "
    "verify), date bounds, referential coverage.</p>",
    "<p>\"Load ke liye maine <code>copy_expert</code> use kiya, pandas ka <code>to_sql</code> nahi. "
    "<code>to_sql</code> batched INSERTs karta hai jo 6 lakh rows ke liye minutes leta hai aur WAL "
    "flood karta hai. COPY ne 17 second mein kar diya — 36,700 rows per second.\"</p>"
    "<p>\"Ek subtle cheez jo maine catch ki: <code>zip3</code> column ko TEXT rakha, numeric nahi. "
    "46,528 rows mein leading zero hai — jaise 007 Puerto Rico ka hai. Numeric padho toh 007 ban "
    "jaata hai 7, aur koi bhi ZIP reference data se join toot jaata hai. CSV theek tha — damage "
    "read pe hota hai. Isliye har read mein dtype force kiya aur ek integrity check likha jo verify "
    "karta hai ki leading zeros bache hain.\"</p>")

HTML = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Project Handbook</title><style>{CSS}</style></head><body>

<!-- ================= COVER ================= -->
<div class="cover">
  <div class="kicker">Data Analyst Portfolio Project</div>
  <h1>US Banking Consumer<br>Complaints Analysis</h1>
  <div class="rule"></div>
  <div class="sub">Risk &amp; Resolution Analysis<br>
    <span style="font-size:11pt;opacity:.85">Complete Project Handbook — Interview Preparation Guide</span></div>

  <div class="statgrid">
    <div class="stat"><span class="n">6,24,708</span><span class="l">Complaints analyze kiye</span></div>
    <div class="stat"><span class="n">3,193</span><span class="l">Companies</span></div>
    <div class="stat"><span class="n">36</span><span class="l">Months ka data</span></div>
    <div class="stat"><span class="n">4,255</span><span class="l">FDIC banks matched</span></div>
    <div class="stat"><span class="n">10</span><span class="l">Pipeline stages</span></div>
    <div class="stat"><span class="n">18+</span><span class="l">Bugs pakde &amp; fix kiye</span></div>
  </div>

  <div class="chips">
    <span>Python 3.11</span><span>pandas</span><span>PostgreSQL 18</span><span>SQL Windows</span>
    <span>rapidfuzz</span><span>SciPy</span><span>Tableau</span><span>Git</span><span>REST APIs</span>
  </div>

  <div class="foot">
    <b>Sahil Vashisth</b> &nbsp;·&nbsp; github.com/sahilsharma0309/banking-complaints-analysis<br>
    Data source: CFPB Consumer Complaint Database + FDIC BankFind Suite API (dono public)
  </div>
</div>

<!-- ================= TOC ================= -->
<div class="section">
  <div class="sechead"><div class="num">Contents</div><h2>Is document mein kya hai</h2></div>
  <p>Ye handbook aapke poore project ka <b>A se Z</b> record hai — kya banaya, kaise banaya, kyun
  waise banaya, aur <b>interview mein har cheez ke baare mein kya bolna hai</b>. Har section mein
  ek hara box hai <span style="color:#059669;font-weight:700">"Interview mein aise bolna"</span> —
  wo aapki script hai.</p>

  <div class="toc">
    <div><b>1</b> Project ek nazar mein — problem, solution, impact</div>
    <div><b>2</b> Business problem — asli sawal kya tha</div>
    <div><b>3</b> Architecture &amp; tech stack — pipeline ka flow</div>
    <div><b>4</b> Stage 0 — Project setup aur Git</div>
    <div><b>5</b> Stage 1 — Data acquisition (CFPB API se 6.24 lakh rows)</div>
    <div><b>6</b> Stage 2 — Data cleaning (sabse important stage)</div>
    <div><b>7</b> Stage 3 — Enrichment (FDIC fuzzy matching)</div>
    <div><b>8</b> Stage 4 — PostgreSQL + SQL analysis</div>
    <div><b>9</b> Stage 5 — Statistics (chi-square + effect size)</div>
    <div><b>10</b> Stage 6 — Feature engineering &amp; risk score</div>
    <div><b>11</b> Stage 7 — Tableau dashboard</div>
    <div><b>12</b> Stage 8 &amp; 9 — Business report aur documentation</div>
    <div><b>13</b> Bugs jo maine pakde — <i>ye aapka biggest differentiator hai</i></div>
    <div><b>14</b> Final results — 4 business insights</div>
    <div><b>15</b> Interview Q&amp;A — 20 sawal aur unke jawab</div>
    <div><b>16</b> Resume bullets aur closing</div>
  </div>

  <div class="box tip"><div class="t">Ise kaise use karein</div>
  <p><b>Interview se 2 din pehle:</b> Section 1, 2, 13, 14, 15 padho — yahi 80% sawaal cover karte hain.<br>
  <b>Interview se 1 ghanta pehle:</b> Sirf hare boxes (Interview mein aise bolna) padh lo.<br>
  <b>Technical round ke liye:</b> Section 4–12 mein code aur decisions detail mein hain.</p></div>
</div>

<!-- ================= 1. OVERVIEW ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 1</div><h2>Project ek nazar mein</h2></div>

  <h3>Ek line mein project kya hai</h3>
  <p class="big">"Maine 6.24 lakh US banking complaints analyze karke ye prove kiya ki complaint
  <i>volume</i> se risk measure karna galat hai — aur size-adjust karne pe industry ki ranking
  poori tarah badal jaati hai."</p>

  <h3>Problem — jo galat ho raha tha</h3>
  <p>Har koi banks ko complaint <b>count</b> se judge karta hai. News headlines bhi yahi bolte hain —
  "Bank X ko sabse zyada complaints mile". Lekin ye <b>fundamentally misleading</b> hai, kyunki bada
  bank hone ki wajah se hi zyada customers hote hain, aur zyada customers ka matlab zyada complaints.</p>

  <p>Ye bilkul aisa hai jaise kehna: "Mumbai mein sabse zyada crime hote hain, isliye Mumbai sabse
  khatarnak city hai" — bina population dekhe. Sahi metric hai <b>crime per lakh population</b>.
  Waise hi banking mein sahi metric hai <b>complaints per $1B of assets</b>.</p>

  <h3>Solution — maine kya banaya</h3>
  <p>Ek complete end-to-end data pipeline: CFPB API se data pull kiya → pandas se clean kiya →
  FDIC ke bank asset data se enrich kiya (fuzzy matching se) → PostgreSQL mein load kiya →
  SQL window functions se analyze kiya → statistics se validate kiya → Tableau dashboard banaya.</p>

  <h3>Impact — kya nikla</h3>
  <table>
    <tr><th>Company</th><th class="n">Volume rank</th><th class="n">Size-adjusted rank</th><th>Kya matlab</th></tr>
    <tr class="hi"><td><b>Synchrony Financial</b></td><td class="n">7</td><td class="n">1</td><td>Volume pe normal, per dollar pe <b>desh mein sabse kharab</b></td></tr>
    <tr><td>Barclays Bank Delaware</td><td class="n">13</td><td class="n">2</td><td>11 position upar</td></tr>
    <tr><td>SoFi Technologies</td><td class="n">18</td><td class="n">3</td><td>15 position upar</td></tr>
    <tr class="hi"><td><b>JPMorgan Chase</b></td><td class="n">2</td><td class="n">25 (of 28)</td><td>Volume pe 2nd worst dikhta hai, actually <b>best mein se ek</b></td></tr>
  </table>

  <div class="box info"><div class="t">Sabse powerful line jo aap bol sakte ho</div>
  <p>"Wells Fargo aur JPMorgan ko dekhiye — dono ko lagbhag same complaints mile, 41,051 aur 40,391.
  Volume chart pe ye twins lagte hain. Lekin JPMorgan ke paas <b>2.2 guna zyada assets</b> hain.
  Matlab per dollar Wells Fargo <b>2.2 guna zyada consumer friction</b> generate karta hai.
  Same data, bilkul ulta conclusion."</p></div>

  <h3>Numbers jo yaad rakhne hain</h3>
  <table>
    <tr><th>Metric</th><th class="n">Value</th><th>Context</th></tr>
    <tr><td>Total complaints analyzed</td><td class="n">6,24,708</td><td>94 lakh mein se filter karke</td></tr>
    <tr><td>Companies</td><td class="n">3,193</td><td>112 ko score kiya (500+ complaints)</td></tr>
    <tr><td>Time period</td><td class="n">36 months</td><td>Jan 2023 – Dec 2025</td></tr>
    <tr><td>National monetary relief rate</td><td class="n">9.93%</td><td>Baseline for comparison</td></tr>
    <tr><td>National untimely rate</td><td class="n">2.32%</td><td>Baseline</td></tr>
    <tr><td>Postgres load speed</td><td class="n">36,700 rows/sec</td><td>COPY use karke</td></tr>
    <tr><td>FDIC match rate</td><td class="n">50.0%</td><td>Volume-weighted</td></tr>
    <tr><td>Worst company (size-adj)</td><td class="n">147.8 / $1B</td><td>Synchrony — peer avg se 4.6×</td></tr>
  </table>
</div>

<!-- ================= 2. BUSINESS PROBLEM ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 2</div><h2>Business problem — asli sawal kya tha</h2></div>

  <h3>Primary question</h3>
  <div class="box info"><div class="t">Ye poora project isi ek sawal ka jawab hai</div>
  <p style="font-size:11pt"><i>"Kaun si US financial companies sabse zyada consumer risk generate
  karti hain — aur company ke <b>size ko adjust karne ke baad</b>, kaun complaints ko sabse
  <b>kharab handle</b> karti hai (sabse kam monetary relief / sabse zyada late response)?"</i></p></div>

  <h3>Ye sawal kyun matter karta hai — 3 audiences</h3>
  <table>
    <tr><th>Kaun</th><th>Unke liye kyun useful</th></tr>
    <tr><td><b>Regulators (CFPB, OCC)</b></td><td>Kis bank ki supervision badhani chahiye. Volume dekhoge toh hamesha bade banks hi dikhenge — chhote lekin risky banks chhoot jayenge.</td></tr>
    <tr><td><b>Bank ki risk/compliance team</b></td><td>Apne peers ke against kahan khade hain. Agar aapka relief rate industry se bahut kam hai toh wo regulatory question ban sakta hai.</td></tr>
    <tr><td><b>Consumers</b></td><td>Kis bank mein complaint karne se actually kuch hota hai. Relief rate 0% se 38.5% tak varies karta hai — 38 guna farak!</td></tr>
  </table>

  <h3>Supporting questions</h3>
  <ol>
    <li>2023 se products ke hisaab se complaint volume kaise badla, aur kaun se products accelerate kar rahe hain?</li>
    <li>Kaun si companies raw volume pe theek lagti hain lekin size-adjust karne pe outlier ban jaati hain?</li>
    <li>Kya complaint ka outcome (relief mila ya nahi) company se <b>statistically independent</b> hai?</li>
    <li>Kaun se issues aur states mein risk sabse zyada concentrated hai?</li>
  </ol>

  <div class="box say"><div class="t">Interview mein aise bolna</div>
  <p>"Project ka core insight ye hai ki <b>volume ek size proxy hai, risk signal nahi</b>.
  Maine CFPB ka data liya, usko FDIC ke bank asset data se join kiya, aur complaints per $1B assets
  nikala. Isse ranking poori badal gayi. Jo companies volume chart pe invisible thi, wo top pe
  aa gayi. Aur maine ye sirf claim nahi kiya — chi-square test se statistically prove bhi kiya
  ki outcome company pe product se 1.8 guna zyada depend karta hai."</p></div>
</div>

<!-- ================= 3. ARCHITECTURE ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 3</div><h2>Architecture &amp; tech stack</h2></div>

  <h3>Pipeline ka flow</h3>
  <div class="flow">
    <div><b>1. EXTRACT</b>CFPB REST API<br>search_after pagination</div>
    <div><b>2. CLEAN</b>pandas<br>43 columns banaye</div>
    <div><b>3. ENRICH</b>FDIC API<br>rapidfuzz matching</div>
    <div><b>4. LOAD</b>PostgreSQL<br>COPY + indexes</div>
    <div><b>5. ANALYZE</b>SQL windows<br>+ SciPy stats</div>
    <div><b>6. VISUALIZE</b>Tableau<br>live connection</div>
  </div>

  <h3>Har tool kyun choose kiya</h3>
  <table>
    <tr><th>Tool</th><th>Kis liye</th><th>Kyun yahi (interview mein ye poochha jaata hai)</th></tr>
    <tr><td><b>Python 3.11</b></td><td>Poora pipeline</td><td>3.14 default tha machine pe, lekin pandas/scipy/psycopg2 ke stable wheels 3.11 pe hain. 3.14 pe source se compile karna padta. <b>Reproducibility ke liye interpreter pin karna zaroori hai.</b></td></tr>
    <tr><td><b>pandas</b></td><td>Cleaning, transformation</td><td>6 lakh rows ke liye perfect — memory mein aa jaata hai, aur vectorized operations fast hain.</td></tr>
    <tr><td><b>PostgreSQL</b></td><td>Warehouse + analysis</td><td>Window functions (RANK, LAG), CTEs, proper types, indexes. Tableau ka native connector bhi hai.</td></tr>
    <tr><td><b>rapidfuzz</b></td><td>Entity matching</td><td>C++ mein likha hai, fuzzywuzzy se 10-100× fast. 3,193 × 6,726 comparisons chahiye the.</td></tr>
    <tr><td><b>SciPy</b></td><td>Chi-square test</td><td>Statistical validation — claim ko sirf number se nahi, test se back karna.</td></tr>
    <tr><td><b>Tableau</b></td><td>Dashboard</td><td>Industry standard for BI. Live Postgres connection.</td></tr>
    <tr><td><b>Git/GitHub</b></td><td>Version control</td><td>Har stage ka alag commit — reviewer decision history dekh sakta hai.</td></tr>
  </table>

  <h3>Repository structure</h3>
<pre><span class="m">banking-complaints-project/</span>
├── data/
│   ├── raw/              <span class="m"># CFPB output — gitignored, KABHI modify nahi kiya</span>
│   ├── processed/        <span class="m"># cleaned outputs — gitignored</span>
│   └── sample_1000.csv   <span class="m"># sirf ye commit kiya, taaki schema dikhe</span>
├── scripts/              <span class="m"># 01 se 09 tak numbered, re-runnable</span>
├── sql/                  <span class="m"># 6 files, har ek ek business question</span>
├── notebooks/eda.ipynb   <span class="m"># statistics</span>
├── dashboard/            <span class="m"># Tableau guide + generated .twb</span>
└── reports/              <span class="m"># cleaning_log, insights, figures</span></pre>

  <div class="box why"><div class="t">Design principle jo poore project mein follow kiya</div>
  <p><b>Har log file script se GENERATE hoti hai, haath se nahi likhi.</b> Matlab
  <code>cleaning_log.md</code> mein jo numbers hain, wo <code>02_clean.py</code> chalane pe
  automatically likhe jaate hain. Isse ye kabhi purane nahi ho sakte. Agar data badla toh
  script dobara chalao, numbers apne aap update ho jayenge.</p>
  <p>Ye interview mein bahut strong point hai — <i>"maine documentation ko code ka output banaya,
  manual step nahi"</i>.</p></div>
</div>

<!-- ================= STAGE 0-1 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 4–5</div><h2>Stage 0 &amp; 1 — Setup aur Data Acquisition</h2></div>

{STAGE_0}

{STAGE_1}
</div>

<!-- ================= STAGE 2 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 6</div><h2>Stage 2 — Data Cleaning (sabse important stage)</h2></div>

  <p>Ye stage sabse zyada showcase karne layak hai, kyunki yahan maine ek <b>aisi cheez pakdi jo
  analysis ko poori tarah galat kar deti</b>.</p>

  <h3>Problem #1 — Product rename ne fake trend bana diya</h3>
  <p>CFPB ne August 2023 mein apni product taxonomy badal di. Purane label band kar diye, naye
  shuru kar diye. Data mein ye aisa dikhta hai:</p>

  <table>
    <tr><th>Month</th><th class="n">"Credit card" (raw)</th><th class="n">"Credit card or prepaid card" (raw)</th><th class="n">Fix ke baad</th></tr>
    <tr><td>2023-06</td><td class="n" style="color:#dc2626"><b>0</b></td><td class="n">4,650</td><td class="n">4,296</td></tr>
    <tr><td>2023-07</td><td class="n" style="color:#dc2626"><b>0</b></td><td class="n">5,252</td><td class="n">4,891</td></tr>
    <tr><td>2023-08</td><td class="n">1,215</td><td class="n">4,532</td><td class="n">5,435</td></tr>
    <tr><td>2023-09</td><td class="n">4,918</td><td class="n" style="color:#dc2626"><b>0</b></td><td class="n">4,918</td></tr>
  </table>

  <div class="box bug"><div class="t">Agar ye fix nahi karte toh kya hota</div>
  <p>Chart pe dikhta ki "Credit card complaints 0 se 4,918 ho gaye 3 mahine mein". Koi bhi analyst
  likh deta: <b>"Credit card complaints surged 300% in Q3 2023"</b>. Ye poori tarah galat hota —
  ye sirf label change tha, real surge nahi. Aur ye galti bilkul invisible hoti, kyunki chart
  perfectly normal dikhta.</p></div>

  <h4>Maine kaise fix kiya</h4>
  <p>Purane label <code>"Credit card or prepaid card"</code> ko <code>sub_product</code> ke basis
  pe wapas do naye labels mein <b>split</b> kiya. Ye <b>lossless</b> tha:</p>
  <ul>
    <li>32,541 rows → "Credit card" (general-purpose + store credit card)</li>
    <li>2,769 rows → "Prepaid card" (prepaid + gift + payroll + govt benefit)</li>
    <li><b>Total 35,310 — bilkul exact, ek bhi row bachi nahi</b></li>
  </ul>
  <p>Result: August boundary pe max month-over-month swing 100%+ se girkar <b>11.1%</b> ho gaya.</p>

  <h3>Problem #2 — Company names merge ho rahe the (mera apna bug)</h3>
  <div class="box bug"><div class="t">Maine apne hi code mein ye bug pakda</div>
  <p>Pehle version mein maine company name normalize karne ke liye <code>FINANCIAL</code>,
  <code>GROUP</code>, <code>BANCSHARES</code> jaise words strip kar diye the — soch ke ki ye "noise"
  hain. Result:</p>
  <table style="margin-top:2mm">
    <tr><th>Merge ho gaya</th><th>Reality</th></tr>
    <tr><td><code>INDEPENDENT BANK CORP.</code> + <code>INDEPENDENT BANK GROUP, INC.</code></td><td><b>Do bilkul alag banks!</b> Ek Massachusetts ka (Rockland Trust), doosra Texas ka</td></tr>
    <tr><td><code>AMERICAN BANCSHARES MORTGAGE</code> + <code>AMERICAN FINANCIAL MORTGAGE</code></td><td>Alag companies</td></tr>
  </table>
  <p style="margin-top:2mm">Do alag banks ko merge karna matlab dono ka complaint count aur risk
  rate <b>corrupt</b> — aur koi symptom bhi nahi dikhta.</p></div>

  <h4>Fix — precision over recall</h4>
  <p>Ab sirf case, punctuation, aur <b>trailing</b> legal form (Inc, LLC, Corp) strip karta hoon.
  Beech ke words nahi chhedta. Result: 10 merges se ghatkar 4 merges, aur chaaron manually verify kiye.</p>

  <div class="box why"><div class="t">Ye trade-off kyun sahi hai</div>
  <p>Do alag banks ko merge karna (false positive) bahut zyada nuksaan karta hai bajaye ek hi bank
  ki do spellings ko merge na kar paane ke (false negative). Kyunki pehla case data ko silently
  corrupt karta hai, doosra case sirf ek company ranking se bahar rakhta hai.</p></div>

  <h3>Baaki cleaning decisions</h3>
  <table>
    <tr><th>Column</th><th class="n">Null %</th><th>Decision</th><th>Reasoning</th></tr>
    <tr><td><code>tags</code></td><td class="n">83%</td><td>Fill 'No tag'</td><td><b>Ye missing data hai hi nahi.</b> Field mein sirf 'Servicemember' ya 'Older American' aata hai. Null ka matlab "koi bhi nahi". Mode se impute karte toh 5 lakh fake veterans ban jaate!</td></tr>
    <tr><td><code>company_public_response</code></td><td class="n">55%</td><td>Fill 'No public response'</td><td>Company ne jaan-boojh ke public statement nahi di. Ye silence khud ek information hai.</td></tr>
    <tr><td><code>sub_issue</code></td><td class="n">8%</td><td>Fill 'Not specified'</td><td>CFPB taxonomy mein har issue ke sub-issues nahi hote. Null legitimate hai.</td></tr>
    <tr><td><code>state</code></td><td class="n">0.5%</td><td>Fill 'Unknown', row rakhi</td><td>State missing hone se complaint invalid nahi ho jaati. Company analysis ke liye wo row abhi bhi valid hai.</td></tr>
  </table>

  <p class="big" style="font-size:12pt">Missing values ki wajah se <b>0 rows drop ki</b>.</p>

  <h3>Duplicates — kya hataya aur kya jaan-boojh ke nahi hataya</h3>
  <table>
    <tr><th>Test</th><th class="n">Matches</th><th>Action</th><th>Kyun</th></tr>
    <tr><td><code>complaint_id</code> (source PK)</td><td class="n">0</td><td>—</td><td>Source ki apni key unique hai</td></tr>
    <tr><td>Business key + <b>exact timestamp</b></td><td class="n">19</td><td style="color:#059669"><b>HATAYE</b></td><td>Same company, same issue, same ZIP, <b>same second</b> — ye double submission hai</td></tr>
    <tr><td>Business key + <b>sirf date</b></td><td class="n">9,568</td><td style="color:#dc2626"><b>NAHI HATAYE</b></td><td>Ye alag log hain jo same din same bank ke against complaint kar rahe hain — bilkul normal</td></tr>
  </table>

  <div class="box why"><div class="t">Ye doosra wala decision bahut important hai</div>
  <p>Agar main 9,568 rows hata deta toh ye <b>directional bias</b> create karta — sabse zyada
  complaints wali companies se sabse zyada rows delete hoti. Matlab jo companies sabse kharab hain,
  unki ranking automatically improve ho jaati. Dedup karke maine unhe bacha diya hota!</p></div>

  <div class="box say"><div class="t">Interview mein aise bolna</div>
  <p>"Cleaning stage mein maine ek aisi cheez pakdi jo poore analysis ko galat kar deti. CFPB ne
  August 2023 mein product taxonomy rename ki thi. Raw data mein 'Credit card' complaints June aur
  July mein zero dikhte hain, phir September mein 4,918. Koi bhi ise dekh ke likh deta ki credit
  card complaints mein 300% surge aaya — jabki wo sirf ek rename tha."</p>
  <p>"Maine purane label ko sub-product ke basis pe wapas split kiya, aur ye lossless tha —
  32,541 plus 2,769 exactly 35,310 ban gaya. Iske baad month-over-month swing 11% pe aa gaya."</p>
  <p>"Doosri cheez jo main highlight karunga wo ye hai ki maine <b>apne hi code mein bug pakda</b>.
  Mera pehla name-normalizer 'Independent Bank Corp' aur 'Independent Bank Group' ko merge kar raha
  tha — ye Massachusetts aur Texas ke do alag banks hain. Maine output review kiya, galti pakdi,
  aur logic ko conservative bana diya. Data cleaning mein <b>precision zyada important hai recall se</b>,
  kyunki galat merge silently data corrupt karta hai."</p></div>
</div>

<!-- ================= STAGE 3 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 7</div><h2>Stage 3 — Enrichment (FDIC fuzzy matching)</h2></div>

  <p>Ye project ka <b>differentiator</b> stage hai. Yahan external data laake wo metric banaya jo
  poore analysis ka base hai.</p>

  <h3>Matching problem</h3>
  <div class="box info"><div class="t">Core challenge</div>
  <p>CFPB <b>holding company</b> ka naam deta hai. FDIC <b>insured subsidiary</b> ka naam rakhta hai.
  Ye do alag naam hote hain:</p>
  <table style="margin-top:2mm">
    <tr><th>CFPB kehta hai</th><th>FDIC mein hai</th></tr>
    <tr><td><code>U.S. BANCORP</code></td><td><code>U.S. Bank National Association</code></td></tr>
    <tr><td><code>TRUIST FINANCIAL CORPORATION</code></td><td><code>Truist Bank</code></td></tr>
    <tr><td><code>SYNCHRONY FINANCIAL</code></td><td><code>Synchrony Bank</code></td></tr>
  </table></div>

  <h3>Do rules jo metric ko sahi rakhte hain</h3>

  <h4>Rule 1 — Assets holding company level pe jodo</h4>
  <p>Ek CFPB company ke neeche kai FDIC charters ho sakte hain. Agar sirf sabse bade subsidiary ke
  assets use karo toh denominator kam ho jaata hai aur risk rate <b>artificially badh jaata hai</b>:</p>
  <table>
    <tr><th>Holding company</th><th class="n">Charters</th><th class="n">Total assets</th><th class="n">Sirf sabse bada</th><th class="n">Kitna kam dikhta</th></tr>
    <tr class="hi"><td>Morgan Stanley</td><td class="n">2</td><td class="n">$632.7B</td><td class="n">$391.3B</td><td class="n"><b>38.2%</b></td></tr>
    <tr><td>Popular Inc</td><td class="n">2</td><td class="n">$75.6B</td><td class="n">$60.6B</td><td class="n">19.8%</td></tr>
    <tr><td>Charles Schwab</td><td class="n">3</td><td class="n">$280.8B</td><td class="n">$242.9B</td><td class="n">13.5%</td></tr>
  </table>

  <div class="box bug"><div class="t">Ek trap jo maine time pe pakda</div>
  <p><b>683 institutions ke paas koi holding company hai hi nahi</b> — unka <code>NAMEHCR</code>
  field blank hai. Agar main blank value pe group by karta toh <b>683 alag-alag independent banks
  ek hi fake $822 billion ki entity ban jaate</b>! Aur jo bhi company usse match hoti, use wo
  absurd denominator mil jaata.</p>
  <p>Fix: aise institutions ko unke apne <code>CERT</code> number se key kiya — har ek alag rehta hai.</p></div>

  <h4>Rule 2 — Unmatched companies ko drop mat karo</h4>
  <p>50% complaint volume aisi entities ka hai jinke FDIC assets hain hi nahi — <b>by design</b>:</p>
  <table>
    <tr><th>Type</th><th class="n">Complaints</th><th>Example</th></tr>
    <tr><td>Credit bureaus</td><td class="n">~57,000</td><td>Equifax, TransUnion, Experian</td></tr>
    <tr><td>Credit unions (NCUA-insured)</td><td class="n">~26,000</td><td>Navy Federal</td></tr>
    <tr><td>Loan servicers</td><td class="n">~50,000</td><td>MOHELA, Nelnet, Navient</td></tr>
    <tr><td>Fintechs</td><td class="n">~30,000</td><td>Chime, Block, SoFi ka non-bank part</td></tr>
  </table>
  <p>Ye sab <b>volume, trend, aur resolution analysis mein rehte hain</b>. Sirf size-adjusted
  ranking se bahar hain. Aur maine "unmatched but high-volume" ki alag list publish ki — kyunki
  <i>ye khud ek finding hai</i> ki itna bada hissa prudential regulation ke bahar hai.</p>

  <h3>Fuzzy matching — har guard ek real bug se aaya</h3>
  <p>Ye section interview mein sabse zyada impress karta hai, kyunki ye dikhata hai ki maine
  output <b>review</b> kiya, blindly trust nahi kiya.</p>

  <table>
    <tr><th>Jo galat match mila</th><th class="n">Score</th><th>Kyun hua</th><th>Guard jo add kiya</th></tr>
    <tr class="hi"><td><code>Ocwen Financial</code> → <code>OWEN FINANCIAL CORP</code></td><td class="n">96.6</td><td><b>Ek letter ka farak!</b> Ocwen ek mortgage servicer hai, Owen ek $0.4B ka chhota bank. Result: <b>7,923 complaints per $1B</b> — bilkul bakwas number</td><td>Kam se kam 1 distinctive token exactly match hona chahiye</td></tr>
    <tr><td><code>Bank of America</code> → reject ho gaya</td><td class="n">100</td><td>Over-correction! Iske saare tokens (BANK, OF, AMERICA, NATIONAL, ASSOCIATION) generic hain, toh koi distinctive token tha hi nahi</td><td>Exact normalized string match ko hamesha accept karo</td></tr>
    <tr><td><code>MECHANICS BANK</code> → <code>Farmers and Mechanics Federal</code></td><td class="n">92+</td><td>Sirf ek token 'MECHANICS' share ho raha tha</td><td>Token-set Jaccard ≥ 0.6</td></tr>
    <tr><td><code>Paramount GR Holdings</code> → <code>PARAMOUNT FINANCIAL GROUP</code></td><td class="n">92+</td><td>Dono ka distinctive token set identical tha — lekin sirf <b>ek</b> token</td><td>Kam se kam <b>2</b> shared tokens chahiye</td></tr>
    <tr><td><code>FIFTH THIRD FINANCIAL</code> → <code>PATHWARD FINANCIAL</code></td><td class="n">—</td><td>Sahi candidate list mein tha, lekin galat wale ne zyada score kar liya</td><td>Token rule ko <b>top-25 candidates pe filter</b> ki tarah lagao, sirf top-1 pe check nahi</td></tr>
  </table>

  <div class="box why"><div class="t">Strictness ka cost affordable kyun tha</div>
  <p>Maine data dekha: <code>exact_normalised</code> aur curated overrides milke <b>99% matched
  volume</b> carry karte hain. Fuzzy paths sirf 1% volume de rahe the — <b>lekin saare false
  positives wahi se aa rahe the</b>. Toh strict banana lagbhag free tha.</p></div>

  <h4>Final safety net</h4>
  <p>Ek <b>plausibility sweep</b> banaya: agar kisi matched company ka ratio 300 complaints per $1B
  se zyada hai toh flag karo — koi real bank itna generate nahi kar sakta. Abhi ye khaali return
  karta hai. Aur main isko <b>report</b> karta hoon, auto-correct nahi — taaki future mein koi
  regression aaye toh dikhe, chhupe nahi.</p>

  <div class="box say"><div class="t">Interview mein aise bolna</div>
  <p>"Enrichment mein maine CFPB companies ko FDIC ke 4,255 institutions se match kiya rapidfuzz se.
  Challenge ye tha ki CFPB holding company ka naam deta hai aur FDIC subsidiary ka."</p>
  <p>"Sabse important baat — <b>maine har guard ko design karke nahi, output review karke add kiya</b>.
  Mera pehla matcher 'Ocwen Financial' ko 'Owen Financial Corp' se match kar raha tha — ek letter ka
  farak, 96.6 score. Ocwen mortgage servicer hai, Owen $0.4 billion ka chhota bank. Isse 7,923
  complaints per billion ka number aa raha tha, jo obviously galat hai."</p>
  <p>"Maine fix kiya toh over-correction ho gaya — Bank of America reject hone laga, kyunki uske
  naam mein koi distinctive word hi nahi hai. Toh doosra rule add karna pada. Total 5 aise guards
  bane, har ek kisi real false positive ki response mein."</p>
  <p>"Aur maine ek plausibility check chhoda hai jo 300 per billion se zyada ratio ko flag karta
  hai. Abhi wo khaali hai, lekin agar future mein koi regression aayi toh turant dikh jayegi.
  <b>Main auto-correct nahi karta — report karta hoon</b>, kyunki silent fix se problem chhup jaati hai."</p></div>
</div>

<!-- ================= STAGE 4 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 8</div><h2>Stage 4 — PostgreSQL + SQL Analysis</h2></div>

{STAGE_4}

  <h3>SQL files — har ek ek business question</h3>
  <table>
    <tr><th>File</th><th>Question</th><th>Technique</th></tr>
    <tr><td><code>01_company_complaint_ranking</code></td><td>Kaun si companies sabse zyada complaints generate karti hain?</td><td>RANK(), DENSE_RANK(), NTILE(), running cumulative share</td></tr>
    <tr><td><code>02_monthly_trend_by_product</code></td><td>Month-over-month trend kya hai?</td><td>LAG(1), LAG(12) for YoY, LEAD(), 3-month moving average</td></tr>
    <tr><td><code>03_resolution_rates</code></td><td>Kaun complaints sabse kharab resolve karta hai?</td><td>FILTER aggregates, PERCENT_RANK(), peer median CTE</td></tr>
    <tr class="hi"><td><code>04_size_adjusted_risk</code></td><td><b>HEADLINE</b> — size adjust karke kaun riskiest hai?</td><td>FDIC join, dual RANK(), rank gap calculation</td></tr>
    <tr><td><code>05_top_issues_by_product</code></td><td>Har product mein top issues kya hain?</td><td>ROW_NUMBER() PARTITION BY</td></tr>
    <tr><td><code>06_top_issues_by_state</code></td><td>Geographic distribution kya hai?</td><td>ROW_NUMBER() PARTITION BY, vs-national comparison</td></tr>
  </table>

  <div class="box tip"><div class="t">SQL ka wo hissa jo interviewer ko dikhana chahiye</div>
  <p>Query 04 mein maine <b>rank gap</b> nikala — volume rank minus size-adjusted rank. Ye number
  hi asli finding hai. Positive gap ka matlab: company volume pe safe dikhti hai lekin actually
  nahi hai. Ye ek single column mein poora insight capture kar leta hai.</p>
  <pre><span class="k">CASE WHEN</span> volume_rank - size_adjusted_rank &gt;= <span class="c">5</span>
     <span class="k">THEN</span> <span class="s">'UNDERSTATED by volume'</span>
     <span class="k">WHEN</span> volume_rank - size_adjusted_rank &lt;= -<span class="c">5</span>
     <span class="k">THEN</span> <span class="s">'overstated by volume'</span>
     <span class="k">ELSE</span> <span class="s">'consistent'</span>
<span class="k">END</span> <span class="k">AS</span> volume_vs_size_verdict</pre></div>
</div>

<!-- ================= STAGE 5 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 9</div><h2>Stage 5 — Statistics (chi-square + effect size)</h2></div>

  <h3>Sabse important statistical concept jo is project mein hai</h3>
  <div class="box why"><div class="t">Ye baat interview mein aapko alag dikhayegi</div>
  <p>Jab sample size 6 lakh ho, toh <b>p-value bekaar ho jaata hai</b>. Chi-square test kisi bhi
  association pe p &lt; 0.001 de dega — chahe wo association kitni bhi choti ho. Matlab
  "statistically significant" hona guaranteed hai, aur isliye wo koi information nahi deta.</p>
  <p>Isliye maine har test ke saath <b>Cramér's V</b> report kiya — ye <b>effect size</b> hai, jo
  batata hai association kitni <i>strong</i> hai, sirf ye nahi ki exist karti hai ya nahi.</p></div>

  <h3>Test results</h3>
  <table>
    <tr><th>Test</th><th class="n">Chi-square</th><th class="n">df</th><th class="n">p-value</th><th class="n">Cramér's V</th><th>Interpretation</th></tr>
    <tr><td>Outcome × Product</td><td class="n">21,575</td><td class="n">7</td><td class="n">&lt; 1e-300</td><td class="n">0.186</td><td>Weak</td></tr>
    <tr class="hi"><td>Outcome × <b>Company</b></td><td class="n">65,031</td><td class="n">111</td><td class="n">&lt; 1e-300</td><td class="n"><b>0.341</b></td><td><b>Strong</b></td></tr>
  </table>

  <p class="big">Company ka association product se <b>1.8 guna strong</b> hai.</p>
  <p>Matlab: <b>aap kis company ke against complaint kar rahe ho, ye zyada matter karta hai bajaye
  iske ki aap kis cheez ke baare mein complaint kar rahe ho.</b></p>

  <h3>Standardized residuals — kaun se cells result drive kar rahe hain</h3>
  <p>Chi-square ek single number deta hai poore table ke liye. Lekin ye nahi batata ki <i>kahan</i>
  problem hai. Standardized residuals se pata chalta hai — ±2 se bahar wale cells hi asli kaam kar
  rahe hain:</p>
  <table>
    <tr><th>Product</th><th class="n">Residual</th><th>Matlab</th></tr>
    <tr><td>Mortgage</td><td class="n" style="color:#dc2626">−66.2</td><td>Expected se bahut kam relief milta hai</td></tr>
    <tr><td>Student loan</td><td class="n" style="color:#dc2626">−62.4</td><td>Expected se bahut kam relief</td></tr>
    <tr><td>Auto loan</td><td class="n" style="color:#dc2626">−51.7</td><td>Expected se kam relief</td></tr>
    <tr><td>Credit card</td><td class="n" style="color:#059669">+53.7</td><td>Expected se zyada relief</td></tr>
    <tr><td>Prepaid card</td><td class="n" style="color:#059669">+50.7</td><td>Expected se zyada relief</td></tr>
  </table>

  {img("fig_03_chisquare_residuals_product.png")}

  <h3>Anomaly jo maine chart dekh ke pakdi</h3>
  {img("fig_01_monthly_trend_overall.png")}

  <div class="box bug"><div class="t">January 2025 — 36,342 complaints (normal 18,000)</div>
  <p>Trend chart banate hi ek spike dikha jo turant wapas normal ho gaya. Spike jo revert ho jaye
  wo aam taur pe organic demand nahi hoti. Maine investigate kiya:</p>
  <ul>
    <li><b>18,441 extra complaints</b></li>
    <li><b>67% sirf do companies se</b> — Navy Federal (484 → 7,725, <b>16 guna</b>) aur Capital One (840 → 5,876)</li>
    <li>15–18 January pe concentrated, 17 tarikh ko akele 4,978</li>
    <li>Dominant issue: overdraft/NSF fees</li>
  </ul>
  <p>Ye ek <b>coordinated filing campaign</b> hai — aam taur pe kisi enforcement action ke baad
  hoti hai. Service quality kharab hone ka signal nahi hai.</p></div>

  <h4>Maine kya kiya — aur kyun delete nahi kiya</h4>
  <p>Complaints <b>real</b> hain, isliye maine unhe delete nahi kiya. Balki flag kiya, aur ek
  <b>sensitivity check</b> chalaya: mahine ko hata ke ranking dobara calculate ki.</p>
  <p class="big" style="color:#059669">Result: 28 mein se 28 companies ka rank same raha.</p>
  <p>Matlab ranking is event se robust hai — aur ab ye <b>proven</b> hai, assumed nahi.</p>

  <div class="box say"><div class="t">Interview mein aise bolna</div>
  <p>"Statistics mein maine ek cheez pe dhyan diya jo bahut log miss karte hain. Mera sample 6 lakh
  ka hai — is size pe chi-square har association pe p less than 0.001 dega. Significance guaranteed
  hai, isliye wo useless hai. Isliye maine <b>Cramér's V</b> report kiya, jo effect size batata hai."</p>
  <p>"Result ye tha ki company ka effect 0.34 tha aur product ka 0.19 — matlab company 1.8 guna
  zyada matter karta hai. Ye ek business-relevant statement hai: aap kis bank ko complaint karte ho
  ye zyada important hai bajaye iske ki complaint kis baare mein hai."</p>
  <p>"Aur maine trend chart banate waqt ek anomaly pakdi — January 2025 mein spike tha jo turant
  revert ho gaya. Investigate kiya toh pata chala 67% spike sirf do companies se aa raha tha, 4 din
  mein concentrated, overdraft issues pe. Ye coordinated filing campaign thi. Maine data delete
  nahi kiya kyunki complaints real hain — balki flag kiya aur sensitivity check chalaya. 28 mein se
  28 companies ka rank same raha, toh ranking robust hai. <b>Maine assume nahi kiya, verify kiya</b>."</p></div>
</div>

<!-- ================= STAGE 6-7 ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 10–11</div><h2>Stage 6 &amp; 7 — Risk Score aur Tableau</h2></div>

  <h3>Stage 6 — Do scores banaye, ek nahi</h3>
  <div class="box why"><div class="t">Ek single composite score kyun galat hota</div>
  <p><b>Reason 1:</b> <code>complaints_per_1b_assets</code> balance sheet size se divide karta hai,
  customer count se nahi. Ek credit card company lakhs customers serve karti hai chhote balance
  sheet pe; ek universal bank ke paas mortgages aur commercial loans hote hain jo assets badhate
  hain bina retail customers badhaye. Toh card issuers <b>business model ki wajah se</b> upar aate
  hain, conduct ki wajah se nahi.</p>
  <p><b>Reason 2:</b> Ye metric 50% complaint volume ke liye <b>undefined</b> hai (non-banks).
  Single composite chupchap aadha market drop kar deta.</p></div>

  <table>
    <tr><th>Score</th><th>Kiske liye</th><th>Kya measure karta hai</th></tr>
    <tr><td><code>conduct_risk_score</code></td><td><b>Har</b> company (112)</td><td>Sirf resolution behaviour. Business model se distort nahi hota. <b>Conduct claims ke liye yahi use karna</b></td></tr>
    <tr><td><code>exposure_risk_score</code></td><td>FDIC-matched (28)</td><td>Isme complaint frequency per $1B bhi add hoti hai</td></tr>
  </table>

  <h4>Score formula — percentile based</h4>
  <table>
    <tr><th>Component</th><th class="n">Weight</th><th>Kya capture karta hai</th></tr>
    <tr><td><code>pct_no_relief</code></td><td class="n">40%</td><td>Consumer ko kuch bhi nahi mila — na paisa, na non-monetary relief</td></tr>
    <tr><td><code>untimely_rate</code></td><td class="n">35%</td><td>Deadline miss ki — hard failure, poori tarah company ke control mein</td></tr>
    <tr><td><code>disputes_facts_rate</code></td><td class="n">15%</td><td>Company consumer ki baat ko formally challenge karti hai</td></tr>
    <tr><td><code>avg_days_to_company</code></td><td class="n">10%</td><td>Routing speed — weakest signal, isliye kam weight</td></tr>
  </table>

  <div class="box bug"><div class="t">Ek component maine test karke HATA diya</div>
  <p>Pehle version mein <code>explanation_only_rate</code> bhi tha 20% weight pe. Maine check kiya
  toh wo <code>pct_no_relief</code> se <b>Spearman ρ = 0.954</b> pe correlate kar raha tha, aur
  average sirf <b>1.0 percentage point</b> ka farak tha.</p>
  <p>Matlab ye <b>ek hi cheez do baar count ho rahi thi</b> — explanation ke saath close karna hi
  toh no relief dena hai. Dono milke 55% weight le rahe the, aur <code>untimely_rate</code> ko
  dabaa rahe the.</p>
  <p>Hataane ke baad ranking sahi hui: "Servicer under contract with Federal Student Aid" — jo 100%
  no relief <b>aur</b> 100% untimely hai — top pe aaya, jo bilkul sahi hai.</p></div>

  <h3>Stage 7 — Tableau handoff</h3>
  <p>4 PostgreSQL views banaye taaki Tableau clean, pre-shaped data padhe:</p>
  <table>
    <tr><th>View</th><th class="n">Rows</th><th>Kis chart ke liye</th></tr>
    <tr><td><code>v_company_summary</code></td><td class="n">112</td><td>Size-adjusted ranking + resolution scatter</td></tr>
    <tr><td><code>v_monthly_trend</code></td><td class="n">281</td><td>Trend line (pre-aggregated, fast)</td></tr>
    <tr><td><code>v_state_summary</code></td><td class="n">51</td><td>Map / state chart</td></tr>
    <tr><td><code>v_complaints_enriched</code></td><td class="n">6,24,195</td><td>Detail aur free-form filtering</td></tr>
  </table>

  <div class="box why"><div class="t">Views kyun banaye, Tableau calculated fields kyun nahi</div>
  <p>View ka matlab hai ki <b>business logic Tableau mein nahi rehta</b>. 500-complaint floor,
  resolved-only denominator, trend window bound, FDIC join — sab SQL mein hain jahan wo versioned
  aur reviewable hain. Agar "risk" ki definition badalti hai toh view badlo, saare worksheets
  automatically follow karenge. Kisi ko yaad nahi rakhna padega ki kaun se calculated field mein
  rule chhupa tha.</p></div>

  <h4>Bonus — poora Tableau workbook code se generate kiya</h4>
  <p><code>.twb</code> file plain XML hoti hai. Toh maine ek script likhi jo poora workbook generate
  karti hai — 4 worksheets, dashboard, sab pre-built. File open karo, sab ready.</p>
  <p>Isme 4 round debugging lagi kyunki Tableau ka XML schema bahut strict hai. Jo errors mile:</p>
  <table>
    <tr><th>Error</th><th>Fix</th></tr>
    <tr><td><code>missing required attribute 'source-build'</code></td><td>Workbook tag mein build version add ki</td></tr>
    <tr><td><code>missing elements in content model ...aggregation)</code></td><td>Har <code>&lt;view&gt;</code> ka aakhri child <code>&lt;aggregation&gt;</code> hona chahiye</td></tr>
    <tr><td><code>value 'Map' not in enumeration</code></td><td>Mark class 'Map' valid nahi hai — Bar use kiya</td></tr>
    <tr class="hi"><td><code>no declaration found for element 'natural-sort'</code></td><td><b>Tableau khud ye element likhta hai apni saved files mein, lekin apna hi loader use reject karta hai!</b> Computed <code>&lt;sort&gt;</code> use kiya</td></tr>
  </table>

  <div class="box say"><div class="t">Interview mein aise bolna (Stage 6 &amp; 7)</div>
  <p>"Risk score mein maine ek deliberate design choice ki — <b>do scores banaye, ek nahi</b>.
  Kyunki size-adjusted metric business model se biased hai: card companies chhote balance sheet pe
  lakhs customers serve karti hain, toh wo automatically upar aati hain. Aur wo metric 50% volume ke
  liye defined hi nahi hai. Isliye ek pure conduct score banaya jo sabke liye valid hai."</p>
  <p>"Score banate waqt maine components ko <b>test kiya</b>, assume nahi kiya. Do components
  0.954 pe correlate kar rahe the — matlab ek hi cheez do baar count ho rahi thi, 55% weight pe.
  Ek hata diya aur rebalance kiya. Iske baad worst performer sahi jagah aaya."</p>
  <p>"Tableau ke liye maine views banaye taaki business logic SQL mein rahe, workbook mein nahi.
  Aur ek step aage jaake maine poora Tableau workbook <b>code se generate</b> kiya — .twb XML hi
  toh hai. Isse dashboard reproducible ban gaya: script chalao, wahi workbook milega, bajaye iske
  ki jo us din click kiya tha."</p></div>
</div>

<!-- ================= BUGS ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 13</div><h2>Bugs jo maine pakde — aapka biggest differentiator</h2></div>

  <div class="box tip"><div class="t">Ye section kyun sabse important hai</div>
  <p>Har candidate keh sakta hai "maine pipeline banaya". Bahut kam log ye keh sakte hain
  <b>"maine apne hi kaam mein ye galtiyan pakdi aur fix ki"</b>. Ye seniority ka sabse strong
  signal hai — kyunki iska matlab hai ki aapne output <b>verify</b> kiya, blindly trust nahi kiya.</p>
  <p>Agar interviewer poochhe "sabse mushkil part kya tha?" — <b>yahan se answer do</b>.</p></div>

  <h3>Category A — Data bugs (analysis galat kar dete)</h3>
  <table>
    <tr><th>#</th><th>Bug</th><th>Impact agar na pakadte</th></tr>
    <tr class="hi"><td>1</td><td><b>Product taxonomy rename</b> — Aug 2023 mein CFPB ne labels badle</td><td>"Credit card complaints 300% surge" — bilkul jhoota claim, aur chart normal dikhta</td></tr>
    <tr class="hi"><td>2</td><td><b>Ocwen → Owen false match</b> — ek letter ka farak, 96.6 score</td><td>7,923 complaints/$1B — nonsense number top pe dikhta</td></tr>
    <tr><td>3</td><td><b>Independent Bank Corp + Group merge</b> — do alag banks</td><td>Dono ka count aur risk rate corrupt, bina kisi symptom ke</td></tr>
    <tr><td>4</td><td><b>rank_gap alag populations compare kar raha tha</b> — volume rank 112 mein se, size rank 28 mein se</td><td>Har gap inflated. SoFi "32 → 3 (+29)" dikh raha tha, sahi hai "18 → 3 (+15)"</td></tr>
    <tr><td>5</td><td><b>zip3 leading zeros</b> — 007 (Puerto Rico) → 7</td><td>46,528 rows ka ZIP join toot jaata</td></tr>
    <tr><td>6</td><td><b>Jan 2025 mass filing event</b></td><td>Coordinated campaign ko real service degradation samajh lete</td></tr>
    <tr><td>7</td><td><b>2026 ka one-day stub</b> — window 1 Jan ko khatam</td><td>Trend chart mein 100% collapse dikhta, jo actually missing data hai</td></tr>
  </table>

  <h3>Category B — Code bugs (silently galat behave karte)</h3>
  <table>
    <tr><th>#</th><th>Bug</th><th>Kyun subtle tha</th></tr>
    <tr class="hi"><td>8</td><td><b><code>'None'</code> sentinel</b> — column ko 'None' string se fill kiya</td><td>pandas ka default <code>na_values</code> mein <b>'None' shaamil hai</b>! CSV likh ke padho toh saare nulls wapas aa jaate hain. Fill khud ko undo kar deta hai</td></tr>
    <tr><td>9</td><td><b>Score components collinear</b> — ρ = 0.954</td><td>Ek hi cheez 55% weight pe do baar count ho rahi thi</td></tr>
    <tr><td>10</td><td><b>.gitignore inline comments</b></td><td><code>hyperd.log  # comment</code> — gitignore inline comments support nahi karta, poori line pattern ban jaati hai, rule dead ho jaata hai</td></tr>
    <tr><td>11</td><td><b><code>hash()</code> non-determinism</b></td><td>Python string hashes har process mein randomize hote hain — generated file har baar alag banti</td></tr>
    <tr><td>12</td><td><b>Generator manual edits mita raha tha</b></td><td>Tableau mein save karne ke baad script chalao toh saara kaam gayab</td></tr>
  </table>

  <h3>Category C — Platform gotchas (documentation mein nahi milte)</h3>
  <table>
    <tr><th>#</th><th>Gotcha</th><th>Kaise pata chala</th></tr>
    <tr><td>13</td><td><b>CFPB <code>format=json</code></b> export endpoint pe bhej deta hai — 1 lakh rows ki cap</td><td>Experiment karke — parameter hata ke test kiya</td></tr>
    <tr><td>14</td><td><b><code>frm</code> offset</b> page 1 ke baad silently ignore</td><td>Page 2 ne same rows return kiye</td></tr>
    <tr><td>15</td><td><b>FDIC search ranking</b> reliable nahi — 'TRUIST' pe JPMorgan first aata hai</td><td>Isliye saara data local pull karke match kiya</td></tr>
    <tr><td>16</td><td><b><code>CREATE DATABASE</code></b> psycopg2 ke context manager mein nahi chalta</td><td>Transaction block error</td></tr>
    <tr><td>17</td><td><b><code>PERCENTILE_CONT</code></b> window function ki tarah use nahi ho sakta</td><td>Postgres error — alag CTE mein nikala</td></tr>
    <tr class="hi"><td>18</td><td><b>Tableau ka <code>natural-sort</code></b> — Tableau khud likhta hai lekin apna loader reject karta hai</td><td>Workbook load error</td></tr>
  </table>

  <div class="box say"><div class="t">"Sabse mushkil part kya tha?" — ka jawab</div>
  <p>"Sabse mushkil technically nahi, <b>discipline ka tha</b> — apne hi output pe bharosa na karna."</p>
  <p>"Ek example deta hoon. Fuzzy matching ke baad maine results ki list dekhi. Ek company thi
  Ocwen Financial jiska ratio 7,923 complaints per billion tha. Ab main chahta toh isse accept kar
  leta — score 96.6 tha, high confidence. Lekin number obviously absurd tha. Check kiya toh pata
  chala wo 'Owen Financial Corp' se match hui thi — ek letter ka farak, aur wo ek $0.4 billion ka
  chhota bank hai jabki Ocwen mortgage servicer hai."</p>
  <p>"Isko fix karne mein <b>5 round lage</b>, kyunki har fix ne naya problem banaya. Pehle fix ne
  Bank of America reject kar diya. Uska fix karne pe Mechanics Bank galat match hone laga.
  Har baar mujhe output dobara review karna pada."</p>
  <p>"Isse main ye seekha ki fuzzy matching mein <b>failure mode chunna padta hai</b>. Maine chuna
  ki galat denominator lagane se accha hai ki denominator na lage — kyunki galat match confidently
  galat answer deta hai, aur no match sirf company ko ek ranking se bahar rakhta hai. Aur maine ek
  plausibility sweep chhoda jo abhi khaali hai, taaki future regression dikhe."</p></div>
</div>

<!-- ================= RESULTS ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 14</div><h2>Final Results — 4 Business Insights</h2></div>

  <h3>Insight 1 — Volume risk signal nahi hai</h3>
  {img("fig_05_size_adjusted_ranking.png")}
  <p>Size-adjust karne pe industry ki ranking badal jaati hai. Synchrony 7th se 1st, JPMorgan 2nd
  se 25th (28 mein se). Synchrony ka rate <b>147.8 per $1B</b> hai — peer average 32.3 se
  <b>4.6 guna</b>, aur JPMorgan se <b>14.7 guna</b>.</p>
  <div class="box info"><div class="t">Recommendation</div>
  <p><b>Risk/supervisory teams ke liye:</b> complaint counts pe ranking band karo. Complaints per
  $1B assets ko primary screening metric banao. Jin institutions ka size-adjusted rank unke volume
  rank se 10+ positions upar hai (SoFi, Barclays, Santander), unko review karo — volume monitoring
  se ye kabhi trigger nahi honge.</p></div>

  <h3>Insight 2 — Student loan servicing systemic failure hai</h3>
  <table>
    <tr><th>Company</th><th class="n">Complaints</th><th class="n">Untimely rate</th><th class="n">vs national (2.32%)</th><th class="n">Relief</th></tr>
    <tr class="hi"><td>"Servicer under contract with Federal Student Aid"</td><td class="n">1,667</td><td class="n"><b>100.0%</b></td><td class="n"><b>43×</b></td><td class="n">0.00%</td></tr>
    <tr><td>EdFinancial Services</td><td class="n">4,014</td><td class="n">43.3%</td><td class="n">19×</td><td class="n">0.00%</td></tr>
    <tr><td>MOHELA</td><td class="n">17,225</td><td class="n">27.2%</td><td class="n">12×</td><td class="n">1.57%</td></tr>
  </table>
  <p>Ek entity ne <b>1,667 mein se har ek</b> complaint ka jawab late diya. Product level pe:
  student loan complaints credit card se <b>59 guna zyada</b> late jawab paate hain aur
  <b>17 guna kam</b> relief. Aur volume <b>double</b> ho gaya (10,633 → 21,307).</p>

  <h3>Insight 3 — Kis company ko complaint karte ho, ye zyada matter karta hai</h3>
  <p>Chi-square se prove kiya: company ka effect (V = 0.341) product se <b>1.8 guna strong</b>
  (V = 0.186). Relief rate <b>0.0% se 38.5%</b> tak jaata hai 112 companies mein.</p>
  <table>
    <tr><th>Company</th><th class="n">Monetary relief rate</th><th class="n">Untimely rate</th></tr>
    <tr><td>Bank of America</td><td class="n" style="color:#059669"><b>32.7%</b></td><td class="n">1.83%</td></tr>
    <tr><td>Citibank</td><td class="n">26.8%</td><td class="n">0.00%</td></tr>
    <tr><td>American Express</td><td class="n">25.5%</td><td class="n">0.39%</td></tr>
    <tr><td>Wells Fargo</td><td class="n">9.9%</td><td class="n">0.01%</td></tr>
    <tr><td>Capital One</td><td class="n" style="color:#dc2626">8.8%</td><td class="n">0.01%</td></tr>
  </table>
  <p>Bank of America Capital One se <b>3.7 guna</b> zyada rate pe monetary relief deta hai.</p>

  <h3>Insight 4 — Debt/credit management sabse tezi se badh raha hai</h3>
  <table>
    <tr><th>Product</th><th class="n">2023</th><th class="n">2025</th><th class="n">Change</th></tr>
    <tr class="hi"><td>Debt or credit management</td><td class="n">484</td><td class="n">4,267</td><td class="n"><b>+781.6%</b></td></tr>
    <tr><td>Student loan</td><td class="n">10,633</td><td class="n">21,307</td><td class="n">+100.4%</td></tr>
    <tr><td>Payday / personal loan</td><td class="n">7,242</td><td class="n">13,138</td><td class="n">+81.4%</td></tr>
    <tr><td>Credit card</td><td class="n">54,409</td><td class="n">89,976</td><td class="n">+65.4%</td></tr>
    <tr><td>Mortgage</td><td class="n">22,853</td><td class="n">24,697</td><td class="n">+8.1%</td></tr>
  </table>
  <p><b>Growth rate dekho, level nahi.</b> Ye category abhi sirf 1.1% volume hai lekin 780% grow
  kar rahi hai — 2 saal mein material problem ban jayegi, aur har volume-ranked dashboard ise
  insignificant dikhata rahega jab tak late na ho jaye.</p>

  <h3>Honest limitations — ye bolna aapko credible banata hai</h3>
  <div class="box why"><div class="t">Interview mein ye zaroor mention karna</div>
  <ol>
    <li><b>Size-adjusted metric business-model sensitive hai.</b> Assets size proxy hai, customer count nahi. Agar customer data hota toh ranking compress ho jaati.</li>
    <li><b>Complaint volume complaint karne ki propensity bhi reflect karta hai</b> — educated, higher-income customers zyada complaint karte hain. Kuch company effect actually customer-mix effect ho sakta hai.</li>
    <li><b>50% volume ka koi FDIC denominator hai hi nahi.</b> MOHELA — sabse kharab servicer — headline metric mein by construction invisible hai.</li>
    <li><b>CFPB ne 2017 mein consumer-dispute flag band kar diya</b>, toh "consumer resolution se satisfied tha ya nahi" measure nahi ho sakta. Untimely aur no-relief substitutes hain, equivalent nahi.</li>
  </ol></div>
</div>

<!-- ================= Q&A ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 15</div><h2>Interview Q&amp;A — 20 sawal aur jawab</h2></div>

  <div class="qa"><div class="q">Q1. Is project ke baare mein 2 minute mein batao</div><div class="ans">
  <p>"Maine CFPB ke public complaint database se 6.24 lakh US banking complaints analyze kiye,
  3 saal ka data. Core question ye tha: kaun si companies sabse zyada consumer risk generate karti
  hain — <b>size adjust karne ke baad</b>."</p>
  <p>"Pipeline aisa hai: CFPB API se data pull kiya cursor pagination se, pandas mein clean kiya,
  FDIC ke bank asset data se fuzzy matching karke enrich kiya, PostgreSQL mein COPY se load kiya,
  SQL window functions se analyze kiya, chi-square se validate kiya, aur Tableau dashboard banaya."</p>
  <p>"Main finding ye thi ki <b>volume risk signal nahi hai, size proxy hai</b>. Synchrony Financial
  volume pe 7th hai lekin per dollar assets ke hisaab se desh mein pehle number pe — peer average se
  4.6 guna. Aur JPMorgan volume pe 2nd worst dikhta hai lekin size-adjust karne pe 28 mein se 25th
  hai, matlab best mein se ek."</p></div></div>

  <div class="qa"><div class="q">Q2. Aapne 87% data kyun hata diya? Kya wo cheating nahi hai?</div><div class="ans">
  <p>"Ye scope decision tha, cherry-picking nahi — aur maine README mein poora document kiya hai."</p>
  <p>"Hataye gaye 82 lakh complaints credit reporting ke the, jo Equifax, Experian, TransUnion ke
  against hain. Ye <b>banks nahi hain</b> — credit bureaus hain. Inke paas FDIC insured assets nahi
  hote, toh mera headline metric inke liye calculate hi nahi ho sakta."</p>
  <p>"Agar main inhe rakhta toh do problems hoti. Ek — 87% volume hone ki wajah se ye har product,
  har state, har trend chart ko dabaa dete. Do — mera size-adjusted analysis inke liye undefined
  hota, toh main unhe silently drop karta ya galat rank karta."</p>
  <p>"Maine README mein clearly likha hai ki ye ab <b>banking risk analysis hai, whole-of-CFPB
  analysis nahi</b>. Aur maine ye bhi likha ki mere volume numbers headline CFPB figures se match
  nahi karenge, kyunki wo credit reporting se drive hote hain."</p></div></div>

  <div class="qa"><div class="q">Q3. Fuzzy matching mein accuracy kaise ensure ki?</div><div class="ans">
  <p>"Teen tarah se. Pehla — maine <b>output review kiya</b>, sirf score pe bharosa nahi kiya.
  Isi se Ocwen/Owen ka bug pakda, jo 96.6 score pe match hua tha lekin galat tha."</p>
  <p>"Doosra — maine guards <b>strict</b> rakhe. Exact normalized match, ya kam se kam 2 distinctive
  tokens plus Jaccard 0.6. Iska cost ye tha ki match rate kam ho gaya, lekin ye affordable tha
  kyunki exact matches aur curated overrides milke 99% volume carry karte hain."</p>
  <p>"Teesra — ek <b>plausibility sweep</b> banaya jo 300 complaints per $1B se zyada wali kisi bhi
  matched company ko flag karta hai. Koi real bank itna generate nahi kar sakta. Abhi ye khaali
  return karta hai, aur main isko report karta hoon auto-correct nahi — taaki regression dikhe."</p></div></div>

  <div class="qa"><div class="q">Q4. Chi-square kyun use kiya aur p-value kya tha?</div><div class="ans">
  <p>"Chi-square test of independence use kiya ye check karne ke liye ki complaint outcome company
  se independent hai ya nahi. Lekin — aur ye important hai — <b>maine p-value pe conclusion nahi
  banaya</b>."</p>
  <p>"6 lakh sample pe chi-square kisi bhi association pe p less than 0.001 dega, chahe wo kitni
  bhi choti ho. Significance guaranteed hai, isliye wo koi information nahi deta. Mera p-value
  literally 1e-300 se kam tha."</p>
  <p>"Isliye maine <b>Cramér's V</b> report kiya — effect size. Company ke liye 0.341 (strong),
  product ke liye 0.186 (weak). Ratio 1.8. Ye business statement banata hai: aap kis company ko
  complaint karte ho ye product se 1.8 guna zyada matter karta hai."</p>
  <p>"Aur maine standardized residuals bhi nikale, kyunki chi-square poore table ka ek number deta
  hai — ye nahi batata ki problem kahan hai. Residuals se dikha ki mortgage (−66) aur student loan
  (−62) expected se bahut kam relief dete hain."</p></div></div>

  <div class="qa"><div class="q">Q5. 6 lakh rows Postgres mein kaise load kiye? Kitna time laga?</div><div class="ans">
  <p>"<code>copy_expert</code> use kiya psycopg2 mein — PostgreSQL ka COPY command. 17 seconds
  mein 6.24 lakh rows, matlab <b>36,700 rows per second</b>."</p>
  <p>"Maine pandas ka <code>to_sql</code> deliberately avoid kiya. Wo batched INSERTs karta hai jo
  is size pe minutes leta hai aur WAL flood karta hai. COPY poori CSV ko ek single statement mein
  stream kar deta hai — file Python mein parse hoti hi nahi."</p>
  <p>"Load ke baad 9 indexes banaye, jisme do composite hain jo actual query shapes se match karte
  hain, aur ANALYZE chalaya taaki planner ke statistics fresh rahein."</p></div></div>

  <div class="qa"><div class="q">Q6. Missing values kaise handle kiye?</div><div class="ans">
  <p>"Sabse pehle — maine <b>missing values ki wajah se ek bhi row drop nahi ki</b>."</p>
  <p>"Kyunki is dataset mein 'missing' zyadatar ek real state encode karta hai, lost data nahi.
  Sabse acha example <code>tags</code> column hai — 83% null. Lekin us field mein sirf
  'Servicemember' ya 'Older American' aata hai. Null ka matlab hai 'koi bhi apply nahi hota'.
  Agar main mode se impute karta toh 5 lakh <b>fake veterans</b> ban jaate. Aur drop karta toh
  83% dataset chala jaata."</p>
  <p>"Toh maine har column ka alag decision liya aur reasoning ke saath log kiya. tags ko 'No tag'
  se fill kiya plus do boolean flags banaye. company_public_response ko 'No public response' se —
  kyunki company ka chup rehna khud ek information hai."</p></div></div>

  <div class="qa"><div class="q">Q7. Duplicates kaise define kiye?</div><div class="ans">
  <p>"<code>complaint_id</code> — source ki apni primary key — pe zero duplicates the. Toh maine
  business key define ki: full timestamp, company, product, sub-product, issue, sub-issue, state,
  ZIP, aur submission channel."</p>
  <p>"Is key pe 19 rows match hui — same company, same issue, <b>same second</b>. Do alag log ka
  9 fields pe same second mein match hona plausible nahi hai, toh ye double submissions hain.
  Hata diye."</p>
  <p>"Lekin agar main timestamp ko sirf date tak truncate karta toh <b>9,568 rows</b> duplicate
  dikhti. Maine wo <b>jaan-boojh ke nahi hataye</b> — kyunki wo alag log hain jo same din same bade
  bank ke against complaint kar rahe hain, jo bilkul expected hai."</p>
  <p>"Ye important hai kyunki unhe hataana <b>directional bias</b> create karta: sabse zyada
  complaints wali companies se sabse zyada rows delete hoti, matlab jo companies sabse kharab hain
  unki ranking automatically improve ho jaati."</p></div></div>

  <div class="qa"><div class="q">Q8. Agar aapko ye project dobara karna hota toh kya alag karte?</div><div class="ans">
  <p>"Teen cheezein."</p>
  <p>"Ek — <b>matching guards pehle se plan karta</b>. Maine 5 guards banaye lekin sab reactive the,
  har ek kisi false positive ke baad. Agar main pehle se soch leta ki fuzzy matching ke failure modes
  kya hain toh time bachta."</p>
  <p>"Do — <b>customer count data dhundhta</b>. Assets size ka acha proxy hai lekin perfect nahi.
  Agar deposit accounts ya cardholder numbers milte toh metric aur clean hota. Maine ye limitation
  document ki hai."</p>
  <p>"Teen — <b>automated tests likhta</b>. Abhi mere paas acceptance checks hain har script ke end
  mein, jo kaafi ache hain, lekin proper pytest suite hoti toh regression pakadna aur aasan hota."</p></div></div>

  <div class="qa"><div class="q">Q9. Sabse mushkil technical challenge?</div><div class="ans">
  <p>"Entity resolution — CFPB companies ko FDIC institutions se match karna."</p>
  <p>"Problem structural thi: CFPB holding company ka naam deta hai ('U.S. BANCORP'), FDIC insured
  subsidiary ka ('U.S. Bank National Association'). Ye same entity hain lekin naam alag."</p>
  <p>"Maine FDIC ka <code>NAMEHCR</code> field use kiya jo holding company ka naam carry karta hai.
  Lekin usme abbreviations hain — 'U S BCORP' matlab 'U.S. Bancorp'. Toh pehle abbreviations expand
  ki, phir rapidfuzz se match kiya."</p>
  <p>"Aur ek trap tha: <b>683 institutions ke paas koi holding company hai hi nahi</b>, unka field
  blank hai. Agar blank pe group by karta toh 683 alag banks ek fake $822 billion entity ban jaate.
  Maine unhe unke apne CERT number se key kiya."</p></div></div>

  <div class="qa"><div class="q">Q10. Aapke insights actionable kaise hain?</div><div class="ans">
  <p>"Har insight ke saath maine ek recommendation di hai jo <b>specific audience</b> ke liye hai,
  generic nahi."</p>
  <p>"Jaise pehle insight ke liye: 'risk teams complaint counts pe ranking band karein, complaints
  per $1B ko primary screening metric banayein, aur jin institutions ka size-adjusted rank volume
  rank se 10+ upar hai unko review karein.' Ye specific hai — SoFi, Barclays, Santander naam ke
  saath."</p>
  <p>"Student loan insight ke liye: 'response timeliness ko complaint volume se independent
  supervisory trigger banao. MOHELA akele 4,632 late responses ka hissa hai.'"</p>
  <p>"Aur maine ek section likha hai <b>'What would change my conclusions'</b> — 5 limitations
  jo mere analysis ko weak kar sakti hain. Ye isliye kiya kyunki agar koi reviewer unstated
  limitation pakadta hai toh wo sochta hai maine miss ki. Agar main khud batata hoon toh wo
  competence dikhta hai."</p></div></div>

  <div class="qa"><div class="q">Q11. Data quality kaise verify ki?</div><div class="ans">
  <p>"Har stage ke end mein acceptance checks likhe jo pass/fail print karte hain."</p>
  <p>"Stage 1 mein 13 checks: row count API total se exact match, zero duplicate IDs, zero unparsed
  dates, har product ka count scope table se match, har narrative ID ka parent complaint exist karta
  hai."</p>
  <p>"Stage 2 mein 9 checks. Ek check ne actually bug pakda — 'nulls sirf zip3 mein hone chahiye'
  fail ho gaya, aur investigate karne pe pata chala ki maine column ko <code>'None'</code> string
  se fill kiya tha, jo pandas ke default NA values mein hai. Matlab CSV likh ke padho toh nulls
  wapas aa jaate the — fill khud ko undo kar raha tha."</p>
  <p>"Stage 4 mein 7 database-level checks, jisme information_schema se verify karta hoon ki dates
  actually DATE type hain aur booleans BOOLEAN."</p></div></div>

  <div class="qa"><div class="q">Q12. Risk score ka formula kya hai aur weights kaise chune?</div><div class="ans">
  <p>"Score percentile-based hai — matlab 80 ka score ka matlab '80% peers se kharab'. Percentile
  isliye use kiya kyunki ye rates heavily right-skewed hain; ek company 100% untimely pe hai, toh
  min-max scale mein baaki sab neeche daб jaate."</p>
  <p>"Weights: no-relief 40%, untimely 35%, disputes-facts 15%, routing days 10%. Maine ye
  <b>explicitly document kiye hain ek judgement ke taur pe, derivation ke taur pe nahi</b> — taaki
  koi reader weighting se disagree kar sake bajaye reverse-engineer karne ke. Underlying rates sab
  output mein hain, toh koi bhi re-weight kar sakta hai."</p>
  <p>"Aur ek component maine <b>test karke hataya</b>. explanation_only_rate 20% pe tha, lekin wo
  no_relief se 0.954 correlate kar raha tha — ek hi cheez do baar. Dono milke 55% weight le rahe the
  aur untimely ko crowd out kar rahe the. Hataane ke baad ranking sahi hui."</p></div></div>

  <div class="qa"><div class="q">Q13. Do scores kyun banaye, ek kyun nahi?</div><div class="ans">
  <p>"Kyunki ek single composite do tarah se misleading hota."</p>
  <p>"Pehla — size-adjusted metric assets se divide karta hai, jo balance sheet size hai customer
  count nahi. Ek monoline credit card company lakhs customers serve karti hai chhote balance sheet
  pe. Ek universal bank ke paas mortgages hain jo assets badhate hain bina retail customers badhaye.
  Toh card issuers <b>business model ki wajah se</b> upar aate hain."</p>
  <p>"Doosra — wo metric 50% complaint volume ke liye undefined hai, kyunki non-banks ke FDIC assets
  hote hi nahi. Single composite chupchap aadha market drop kar deta."</p>
  <p>"Isliye <b>conduct_risk_score</b> banaya jo sirf resolution behaviour dekhta hai aur sabke liye
  valid hai — yahi main conduct claims ke liye use karta hoon. Aur <b>exposure_risk_score</b> jo
  size bhi add karta hai, sirf matched banks ke liye."</p></div></div>

  <div class="qa"><div class="q">Q14. Tableau mein business logic kyun nahi rakha?</div><div class="ans">
  <p>"Kyunki Tableau calculated fields versioned nahi hote aur review karna mushkil hai."</p>
  <p>"Maine 4 PostgreSQL views banaye. 500-complaint floor, resolved-only denominator, trend window
  bound, FDIC join — sab SQL mein hain. Agar 'risk' ki definition badalti hai toh view badlo, saare
  worksheets automatically follow karenge."</p>
  <p>"Agar ye logic Tableau mein hota toh kisi ko yaad rakhna padta ki kaun se calculated field mein
  kaun sa rule chhupa hai — aur ek worksheet update karna bhool jaate toh dashboard inconsistent
  ho jaata."</p></div></div>

  <div class="qa"><div class="q">Q15. Pipeline reproducible kaise hai?</div><div class="ans">
  <p>"Chaar tarah se."</p>
  <p>"Ek — <b>numbered scripts</b>, har ek idempotent aur re-runnable. Script 01 checkpointed hai,
  toh interrupted download resume hota hai."</p>
  <p>"Do — <b>interpreter aur dependencies pinned</b>. requirements-lock.txt verified install se
  generate hui hai."</p>
  <p>"Teen — <b>logs script se generate hote hain</b>. cleaning_log.md ke numbers 02_clean.py
  chalane pe likhe jaate hain. Agar data badla toh script chalao, numbers apne aap update. Ye kabhi
  stale nahi ho sakte."</p>
  <p>"Chaar — <b>secrets .env mein hain</b> jo gitignored hai, aur .env.example committed hai
  taaki koi aur setup kar sake."</p></div></div>

  <div class="qa"><div class="q">Q16. Jan 2025 spike ka kya kiya?</div><div class="ans">
  <p>"Pehle investigate kiya. 18,441 extra complaints the, aur <b>67% sirf do companies se</b> —
  Navy Federal 484 se 7,725 (16 guna) aur Capital One 840 se 5,876. 15 se 18 January mein
  concentrated, 17 tarikh ko akele 4,978. Dominant issue overdraft/NSF fees."</p>
  <p>"Ye signature hai <b>coordinated filing campaign</b> ki — aam taur pe kisi enforcement action
  ke baad hoti hai, service quality degrade hone ka signal nahi."</p>
  <p>"Maine data <b>delete nahi kiya</b> kyunki complaints real hain. Balki flag kiya, aur
  sensitivity check chalaya — mahina hata ke ranking dobara nikali. <b>28 mein se 28 companies ka
  rank same raha</b>, toh ranking robust hai."</p>
  <p>"Aur maine Tableau dashboard pe annotation add karne ka instruction likha hai, kyunki bina
  uske koi bhi viewer us spike ko real service collapse samjhega."</p></div></div>

  <div class="qa"><div class="q">Q17. Sabse bada business insight kya hai?</div><div class="ans">
  <p>"Ki <b>volume aur risk alag cheezein hain, aur poori industry volume dekh rahi hai</b>."</p>
  <p>"Concrete example: Wells Fargo aur JPMorgan ko lagbhag identical complaints mile — 41,051 aur
  40,391. Koi bhi volume-based dashboard inhe same risk dikhayega. Lekin JPMorgan ke paas 2.2 guna
  assets hain, toh per dollar Wells Fargo 2.2 guna friction generate karta hai."</p>
  <p>"Aur ulta bhi sach hai — Synchrony volume pe 7th hai, koi notice nahi karega, lekin per dollar
  wo <b>desh mein number one</b> hai, peer average se 4.6 guna."</p>
  <p>"Iska practical matlab ye hai ki agar aap complaint counts se monitor kar rahe ho toh aap
  systematically chhote lekin riskier institutions ko miss kar rahe ho."</p></div></div>

  <div class="qa"><div class="q">Q18. Aapne kaun se SQL concepts use kiye?</div><div class="ans">
  <p>"Window functions kaafi use kiye — <code>RANK()</code>, <code>DENSE_RANK()</code> ties dikhane
  ke liye, <code>NTILE(4)</code> quartiles ke liye, <code>ROW_NUMBER() OVER (PARTITION BY ...)</code>
  har group ka top-N nikalne ke liye."</p>
  <p>"Trend analysis ke liye <code>LAG(1)</code> previous month, <code>LAG(12)</code> year-over-year,
  <code>LEAD()</code>, aur moving average ke liye <code>AVG() OVER (ORDER BY ... ROWS BETWEEN 2
  PRECEDING AND CURRENT ROW)</code>."</p>
  <p>"<code>FILTER (WHERE ...)</code> aggregates kaafi use kiye — ye <code>CASE WHEN</code> se
  cleaner hai conditional counts ke liye."</p>
  <p>"Aur ek cheez jo maine seekhi: <code>PERCENTILE_CONT</code> ek <b>ordered-set aggregate</b>
  hai, PostgreSQL use window function ki tarah allow nahi karta. Toh peer median ko alag CTE mein
  nikal ke cross join karna pada."</p></div></div>

  <div class="qa"><div class="q">Q19. Ye project real world mein kaise use hoga?</div><div class="ans">
  <p>"Teen tarah se."</p>
  <p>"<b>Regulator ke liye:</b> supervisory prioritization. Abhi agar CFPB volume dekh ke supervision
  allocate karta hai toh bade banks pe focus jaata hai. Size-adjusted metric se pata chalta hai ki
  kaun se institutions apne size ke hisaab se outlier hain."</p>
  <p>"<b>Bank ki compliance team ke liye:</b> peer benchmarking. Agar aapka relief rate peers se
  bahut kam hai toh wo ek defensible-conduct question hai jo kisi volume dashboard mein nahi
  dikhega."</p>
  <p>"<b>Consumer advocacy ke liye:</b> transparency. Ek consumer ko nahi pata ki uske remediation
  ke chances issuer ke hisaab se 4 guna vary karte hain."</p></div></div>

  <div class="qa"><div class="q">Q20. Aapne is project se kya seekha?</div><div class="ans">
  <p>"Sabse badi seekh ye hai ki <b>data analysis mein sabse khatarnak galtiyan wo hain jo galat
  nahi dikhti</b>."</p>
  <p>"Product rename wala case perfect example hai. Chart bilkul normal dikh raha tha. Ek clean
  line jo badh rahi thi. Agar main sirf chart dekhta toh confidently likh deta ki credit card
  complaints mein 300% surge aaya. Koi error message nahi, koi red flag nahi — bas ek galat
  conclusion."</p>
  <p>"Isi tarah Ocwen/Owen match. 96.6 score tha — algorithm confident tha. Sirf ye ki number
  absurd tha, isliye maine check kiya."</p>
  <p>"Toh maine ye habit banayi ki har stage ke baad output <b>manually review karo</b> aur poochho
  'kya ye number believable hai?'. Aur automated checks likho jo assumptions verify karein. Mere
  har script ke end mein acceptance checks hain, aur unme se do ne actual bugs pakde."</p></div></div>
</div>

<!-- ================= RESUME ================= -->
<div class="section">
  <div class="sechead"><div class="num">Section 16</div><h2>Resume bullets aur closing</h2></div>

  <h3>Option A — analytical result pe focus</h3>
  <div class="box info"><p>Built an end-to-end pipeline analysing <b>624,708 CFPB banking
  complaints</b> (Python, PostgreSQL, Tableau), enriching them with FDIC asset data via fuzzy
  entity matching to compute a size-adjusted risk metric; showed that <b>raw complaint volume
  misranks the industry</b> — the 2nd-largest complaint generator ranks <b>25th of 28 once
  normalised by assets</b>, while the worst performer runs at <b>4.6× the peer average</b> — and
  proved via chi-square (Cramér's V 0.34 vs 0.19, n=624k) that complaint outcome depends
  <b>1.8× more on the company than the product</b>.</p></div>

  <h3>Option B — engineering pe focus</h3>
  <div class="box info"><p>Engineered a reproducible 7-stage data pipeline ingesting <b>624,727
  records</b> from the CFPB API (cursor pagination, retry/backoff, checkpointed resume), cleaned
  and validated them into a typed <b>PostgreSQL</b> warehouse via bulk <code>COPY</code> at
  <b>~36,700 rows/sec</b> with 9 indexes and automated integrity checks; built entity resolution
  against <b>4,255 FDIC institutions</b> with rapidfuzz, and delivered SQL views powering a
  live-connected <b>Tableau</b> dashboard plus a statistical notebook.</p></div>

  <h3>Skills jo ye project demonstrate karta hai</h3>
  <table>
    <tr><th>Category</th><th>Skills</th></tr>
    <tr><td><b>Data Engineering</b></td><td>REST API integration, cursor pagination, retry/backoff, checkpointing, ETL design, bulk loading (COPY), indexing strategy, schema design</td></tr>
    <tr><td><b>Data Cleaning</b></td><td>Missing value strategy, deduplication logic, taxonomy normalization, data quality flags, entity resolution</td></tr>
    <tr><td><b>SQL</b></td><td>Window functions, CTEs, FILTER aggregates, percentile functions, views, query optimization</td></tr>
    <tr><td><b>Statistics</b></td><td>Chi-square test, effect size (Cramér's V), standardized residuals, Spearman correlation, sensitivity analysis</td></tr>
    <tr><td><b>Business Analysis</b></td><td>Metric design, normalization, actionable recommendations, limitation disclosure</td></tr>
    <tr><td><b>Tools</b></td><td>Python, pandas, PostgreSQL, Tableau, Git, Jupyter</td></tr>
  </table>

  <div class="box tip"><div class="t">Aakhri advice — interview ke liye</div>
  <p><b>1.</b> Agar ek hi cheez yaad rakhni ho toh ye: <i>"Wells Fargo aur JPMorgan ko same
  complaints mile, lekin JPMorgan ke paas 2.2 guna assets hain — toh per dollar Wells Fargo 2.2
  guna zyada risk hai."</i> Ye ek line poora project explain kar deti hai.</p>
  <p><b>2.</b> Jab bhi mauka mile, <b>bugs ke baare mein baat karo</b>. "Maine pipeline banaya"
  common hai. "Maine apne hi code mein ye galti pakdi aur fix ki" rare hai.</p>
  <p><b>3.</b> Limitations khud batao. Ye weakness nahi, <b>credibility</b> hai. Jo analyst apni
  analysis ki seemayein jaanta hai, wo zyada trustworthy hota hai.</p>
  <p><b>4.</b> Numbers yaad rakho: 6.24 lakh rows, 3,193 companies, 36 months, 147.8 per $1B
  (Synchrony), 0.34 vs 0.19 (Cramér's V), 36,700 rows/sec (load speed).</p></div>

  <div style="margin-top:12mm;padding:6mm;background:linear-gradient(135deg,#0f172a,#4c1d95);
       color:#fff;border-radius:10px;text-align:center;">
    <div style="font-size:14pt;font-weight:800;margin-bottom:2mm">All the best, Sahil! 🚀</div>
    <div style="font-size:9.5pt;color:#c7d2fe">
      github.com/sahilsharma0309/banking-complaints-analysis<br>
      Ye project sirf ek dashboard nahi hai — ye ek complete analytical argument hai,
      jo data se shuru hoke actionable recommendation tak jaata hai.</div>
  </div>
</div>

</body></html>"""


def main() -> None:
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(HTML, encoding="utf-8")
    print(f"  HTML written: {OUT_HTML.name} ({OUT_HTML.stat().st_size/1024:.0f} KB)")

    chrome = next((c for c in CHROME_CANDIDATES if Path(c).exists()), None)
    if not chrome:
        sys.exit("Chrome/Edge not found -- cannot render PDF")
    print(f"  renderer: {Path(chrome).name}")

    if OUT_PDF.exists():
        OUT_PDF.unlink()

    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
           "--virtual-time-budget=20000",
           f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not OUT_PDF.exists():
        print(res.stdout[-1500:])
        print(res.stderr[-1500:])
        sys.exit("PDF was not produced")

    print(f"\n  PDF: {OUT_PDF}")
    print(f"  size: {OUT_PDF.stat().st_size/1024/1024:.2f} MB")
    OUT_HTML.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
