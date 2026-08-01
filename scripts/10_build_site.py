"""
Build the GitHub Pages landing site into docs/.

Produces docs/index.html plus docs/assets/. Enable Pages with
Settings -> Pages -> Source: main branch, /docs folder. The site then lives at
https://sahilsharma0309.github.io/banking-complaints-analysis/

Self-contained: images are copied into docs/assets/ rather than base64-embedded,
so the HTML stays small and the browser can cache each figure.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGS = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

REPO = "https://github.com/sahilsharma0309/banking-complaints-analysis"
# Tracking params (?:sid=, :redirect=, :origin=viz_share_link) stripped -- the
# bare view URL resolves fine and stays readable in a resume.
TABLEAU = "https://public.tableau.com/views/banking_complaints_dashboard/Dashboard"

# NOTE: reports/PROJECT_HANDBOOK.pdf is deliberately NOT published here.
# It is a personal interview-preparation document written in Hinglish -- it
# contains rehearsal scripts, model answers and draft resume bullets. Showing
# a recruiter your prepared answers undercuts the interview, and the language
# makes it unreadable to the intended audience anyway. The public artefacts
# are the business report, the notebook and the generated logs.
REPORT = f"{REPO}/blob/main/reports/insights.md"
NOTEBOOK = f"{REPO}/blob/main/notebooks/eda.ipynb"
METHOD = f"{REPO}/blob/main/reports/cleaning_log.md"

CSS = """
:root{--bg:#0b1020;--card:#141b32;--line:#243150;--txt:#e6ebf7;--dim:#9fb0d0;
      --acc:#6366f1;--acc2:#a855f7;--warm:#fbbf24;--good:#34d399;--bad:#f87171;}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--txt);
     font:16px/1.7 'Segoe UI',system-ui,-apple-system,sans-serif;
     -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
a{color:#a5b4fc;text-decoration:none}
a:hover{text-decoration:underline}
code{font-family:Consolas,monospace;background:#1e2942;color:#c7d2fe;
     padding:2px 7px;border-radius:5px;font-size:.88em}

/* hero */
header{background:radial-gradient(1200px 600px at 20% -10%,#3b2a7a 0%,transparent 60%),
       radial-gradient(900px 500px at 90% 0%,#1e3a8a 0%,transparent 55%),#0b1020;
       border-bottom:1px solid var(--line);padding:88px 0 64px}
.kicker{letter-spacing:.3em;text-transform:uppercase;font-size:12px;
        color:#a5b4fc;font-weight:700;margin-bottom:20px}
h1{font-size:clamp(32px,5.5vw,56px);line-height:1.1;font-weight:800;
   letter-spacing:-1px;margin-bottom:18px}
h1 span{background:linear-gradient(90deg,#fbbf24,#f472b6);
        -webkit-background-clip:text;background-clip:text;color:transparent}
.lede{font-size:clamp(16px,2vw,20px);color:var(--dim);max-width:720px;margin-bottom:34px}
.cta{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:44px}
.btn{display:inline-flex;align-items:center;gap:9px;padding:13px 22px;border-radius:11px;
     font-weight:650;font-size:15px;border:1px solid var(--line);transition:.18s}
.btn:hover{text-decoration:none;transform:translateY(-2px)}
.btn.p{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;border:0}
.btn.p:hover{box-shadow:0 10px 30px rgba(99,102,241,.4)}
.btn.s{background:#161f3a;color:var(--txt)}
.btn.s:hover{background:#1c2748;border-color:#3b4a72}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.stat{background:rgba(255,255,255,.045);border:1px solid var(--line);
      border-radius:13px;padding:18px}
.stat b{display:block;font-size:26px;font-weight:800;color:var(--warm);line-height:1.15}
.stat span{font-size:12.5px;color:var(--dim);display:block;margin-top:5px}

/* sections */
section{padding:66px 0;border-bottom:1px solid var(--line)}
.tag{display:inline-block;font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
     color:var(--acc2);font-weight:700;margin-bottom:12px}
h2{font-size:clamp(24px,3.6vw,34px);font-weight:800;letter-spacing:-.5px;margin-bottom:14px}
h3{font-size:20px;font-weight:700;margin:30px 0 10px;color:#c7d2fe}
p{color:var(--dim);margin-bottom:14px;max-width:800px}
p strong,li strong{color:var(--txt)}

.hl{background:linear-gradient(135deg,#1a2444,#1e2a52);border:1px solid #34406b;
    border-left:4px solid var(--warm);border-radius:12px;padding:22px 26px;margin:24px 0}
.hl p{margin:0;color:var(--txt);font-size:17px}

table{width:100%;border-collapse:collapse;margin:20px 0;font-size:14.5px;
      background:var(--card);border-radius:12px;overflow:hidden}
th{background:#1c2545;text-align:left;padding:12px 15px;font-size:12.5px;
   text-transform:uppercase;letter-spacing:.06em;color:#a5b4fc}
td{padding:11px 15px;border-top:1px solid var(--line);color:var(--dim)}
td strong{color:var(--txt)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.star td{background:rgba(251,191,36,.09)}
.up{color:var(--good);font-weight:700}
.down{color:var(--bad);font-weight:700}

figure{margin:26px 0}
figure img{width:100%;border:1px solid var(--line);border-radius:12px;display:block}
figcaption{color:#8194b8;font-size:13.5px;margin-top:10px;text-align:center}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin:22px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:20px}
.card h4{font-size:16px;margin-bottom:8px;color:#e6ebf7}
.card p{font-size:14px;margin:0}
.card .big{font-size:30px;font-weight:800;color:var(--warm);line-height:1.1;margin-bottom:6px}

.chips{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}
.chips span{background:#1a2340;border:1px solid var(--line);border-radius:20px;
            padding:6px 14px;font-size:13px;color:#c7d2fe}

ol,ul{color:var(--dim);margin:0 0 16px 22px}
li{margin-bottom:9px}

.bug{background:linear-gradient(135deg,#2a1620,#331a26);border:1px solid #55283c;
     border-left:4px solid var(--bad);border-radius:12px;padding:20px 24px;margin:20px 0}
.bug h4{color:#fca5a5;font-size:15px;margin-bottom:8px}
.bug p{margin:0;font-size:14.5px}

footer{padding:52px 0 70px;text-align:center;color:#7185a8;font-size:14px}
footer a{margin:0 10px}
@media(max-width:640px){header{padding:60px 0 46px}section{padding:48px 0}}
"""


PAGE = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Banking Complaints — Risk &amp; Resolution Analysis | Sahil Vashisth</title>
<meta name="description" content="End-to-end analysis of 624,708 CFPB banking complaints. Proves that raw complaint volume misranks the industry once normalised by FDIC assets. Python, PostgreSQL, Tableau.">
<meta property="og:title" content="US Banking Complaints — Risk &amp; Resolution Analysis">
<meta property="og:description" content="624,708 complaints analysed. Volume is a size proxy, not a risk signal.">
<meta property="og:type" content="website">
<style>{CSS}</style>
</head><body>

<header><div class="wrap">
  <div class="kicker">Data Analyst Portfolio Project</div>
  <h1>Complaint volume is a size proxy,<br><span>not a risk signal.</span></h1>
  <p class="lede">An end-to-end analysis of <strong>624,708 US banking complaints</strong> filed with
  the CFPB. By joining FDIC asset data through fuzzy entity matching, this project shows that the
  industry's risk ranking <strong>completely reorders</strong> once you control for company size —
  and proves statistically that complaint outcome depends more on <em>who</em> you complain to than
  <em>what</em> you complain about.</p>

  <div class="cta">
    <a class="btn p" href="{TABLEAU}">Explore the live dashboard</a>
    <a class="btn s" href="{REPO}">View the code on GitHub</a>
    <a class="btn s" href="{REPORT}">Read the business report</a>
    <a class="btn s" href="{NOTEBOOK}">Analysis notebook</a>
  </div>

  <div class="stats">
    <div class="stat"><b>624,708</b><span>Complaints analysed</span></div>
    <div class="stat"><b>3,193</b><span>Companies</span></div>
    <div class="stat"><b>36</b><span>Months of data</span></div>
    <div class="stat"><b>4,255</b><span>FDIC banks matched</span></div>
    <div class="stat"><b>36.7k</b><span>Rows/sec load speed</span></div>
  </div>
</div></header>

<section><div class="wrap">
  <div class="tag">The problem</div>
  <h2>Why complaint counts mislead</h2>
  <p>Everyone ranks banks by how many complaints they receive. It is the wrong measure. A bigger
  bank has more customers, and more customers mean more complaints — so a volume league table
  mostly ranks banks by <em>size</em>.</p>
  <p>It is the same error as calling a city dangerous because it reports the most crimes, without
  dividing by population. The meaningful figure is the <strong>rate</strong>.</p>

  <div class="hl"><p>Wells Fargo received <strong>41,051</strong> complaints. JPMorgan Chase
  received <strong>40,391</strong>. On a volume chart they are twins. But JPMorgan holds
  <strong>2.2× the assets</strong> — so per dollar of balance sheet, Wells Fargo generates
  <strong>2.2× the consumer friction</strong>. Same data, opposite conclusion.</p></div>
</div></section>

<section><div class="wrap">
  <div class="tag">Headline finding</div>
  <h2>Normalising by assets reorders the industry</h2>
  <p>Both ranks below are computed over the same 28 FDIC-matched depositories, so the movement is
  a like-for-like comparison.</p>

  <table>
    <tr><th>Company</th><th class="n">Volume rank</th><th class="n">Size-adjusted rank</th>
        <th class="n">Move</th><th class="n">Complaints / $1B</th></tr>
    <tr class="star"><td><strong>Synchrony Financial</strong></td><td class="n">7</td>
        <td class="n"><strong>1</strong></td><td class="n up">&#9650; 6</td><td class="n"><strong>147.8</strong></td></tr>
    <tr><td>Barclays Bank Delaware</td><td class="n">13</td><td class="n"><strong>2</strong></td>
        <td class="n up">&#9650; 11</td><td class="n">128.8</td></tr>
    <tr><td>SoFi Technologies</td><td class="n">18</td><td class="n"><strong>3</strong></td>
        <td class="n up">&#9650; 15</td><td class="n">81.5</td></tr>
    <tr><td>Wells Fargo</td><td class="n">1</td><td class="n">11</td>
        <td class="n down">&#9660; 10</td><td class="n">22.0</td></tr>
    <tr class="star"><td><strong>JPMorgan Chase</strong></td><td class="n">2</td>
        <td class="n">25 of 28</td><td class="n down">&#9660; 23</td><td class="n">10.1</td></tr>
  </table>

  <p><strong>Synchrony is 1st in the country per dollar of assets</strong> — 4.6× the matched-peer
  average and 14.7× JPMorgan — while sitting 7th on volume, where nobody would notice it. JPMorgan
  is the mirror image: it looks like one of the worst actors in US banking on a volume table, and
  is one of the best per dollar of balance sheet.</p>

  <figure><img src="assets/fig_05_size_adjusted_ranking.png" alt="Size-adjusted complaint risk ranking">
  <figcaption>Red = far riskier than volume suggests · Blue = volume overstates the risk</figcaption></figure>
</div></section>

<section><div class="wrap">
  <div class="tag">Interactive</div>
  <h2>Explore it yourself</h2>
  <p>The dashboard is published on Tableau Public and reads from four purpose-built PostgreSQL
  views, so the 500-complaint floor, the resolved-only denominators and the FDIC join all live in
  versioned SQL rather than in the workbook.</p>
  <div class="grid">
    <div class="card"><h4>Size-adjusted risk</h4><p>Ranked bars coloured by how far each company
      moves between its volume rank and its per-dollar rank.</p></div>
    <div class="card"><h4>Monthly trend</h4><p>Complaint volume by product across 36 months, on the
      cleaned taxonomy so the Aug-2023 rename does not read as a surge.</p></div>
    <div class="card"><h4>Resolution quality</h4><p>Relief rate against untimely rate — the
      upper-left quadrant is the one that matters.</p></div>
    <div class="card"><h4>Geography</h4><p>State-level volume and resolution rates across the
      50 states and DC.</p></div>
  </div>
  <p style="margin-top:22px"><a class="btn p" href="{TABLEAU}">Open the dashboard on Tableau Public</a></p>
</div></section>

<section><div class="wrap">
  <div class="tag">Statistical validation</div>
  <h2>Who you complain to matters 1.8× more than what about</h2>
  <p>Chi-square tests of independence on 623,992 resolved complaints. At this sample size every
  p-value is below 1e-300, so <strong>significance is guaranteed and therefore uninformative</strong>.
  Conclusions are drawn from <strong>Cramér's V</strong> effect sizes instead.</p>

  <table>
    <tr><th>Association</th><th class="n">&chi;&sup2;</th><th class="n">df</th>
        <th class="n">Cramér's V</th><th>Strength</th></tr>
    <tr><td>Outcome &times; Product</td><td class="n">21,575</td><td class="n">7</td>
        <td class="n">0.186</td><td>Weak</td></tr>
    <tr class="star"><td>Outcome &times; <strong>Company</strong></td><td class="n">65,031</td>
        <td class="n">111</td><td class="n"><strong>0.341</strong></td><td><strong>Strong</strong></td></tr>
  </table>

  <p>Monetary relief rates span <strong>0.0% to 38.5%</strong> across the 112 companies with 500+
  resolved complaints. Bank of America pays monetary relief at <strong>3.7× Capital One's rate</strong>
  on comparable products.</p>

  <figure><img src="assets/fig_03_chisquare_residuals_product.png" alt="Standardised residuals heatmap">
  <figcaption>Standardised residuals — which product/outcome cells actually drive the association</figcaption></figure>
</div></section>

<section><div class="wrap">
  <div class="tag">Anomaly detection</div>
  <h2>A spike that wasn't real demand</h2>
  <p>The trend chart showed January 2025 jumping to 36,342 complaints against an ~18,000 baseline,
  then reverting immediately. A spike that reverts is rarely organic.</p>

  <div class="grid">
    <div class="card"><div class="big">18,441</div><p>Excess complaints in that single month</p></div>
    <div class="card"><div class="big">67%</div><p>Came from just two companies — Navy Federal and Capital One</p></div>
    <div class="card"><div class="big">28/28</div><p>Companies held the same rank when the month was excluded</p></div>
  </div>

  <p>Navy Federal went from 484 to 7,725 complaints (16×), concentrated on 15–18 January and
  dominated by overdraft/NSF issues — the signature of a <strong>coordinated filing campaign</strong>
  following an enforcement action, not degraded service.</p>
  <p>The complaints are real, so they were <strong>flagged rather than deleted</strong>, and a
  sensitivity check re-computed the headline metric without that month. All 28 companies held their
  rank, so the ranking is demonstrably robust to the event rather than assumed to be.</p>

  <figure><img src="assets/fig_01_monthly_trend_overall.png" alt="Monthly complaint trend">
  <figcaption>Monthly complaint volume and resolution quality, 2023–2025</figcaption></figure>
</div></section>

<section><div class="wrap">
  <div class="tag">Engineering</div>
  <h2>How it was built</h2>

  <div class="grid">
    <div class="card"><h4>1 · Acquisition</h4><p>CFPB REST API with <code>search_after</code>
      cursor pagination, exponential backoff, and checkpointed resume. 624,727 rows — an exact match
      to the API's reported total.</p></div>
    <div class="card"><h4>2 · Cleaning</h4><p>43 typed columns, an explicit dedupe key, and per-column
      missing-value decisions. <strong>Zero rows dropped</strong> for missingness.</p></div>
    <div class="card"><h4>3 · Enrichment</h4><p>Fuzzy entity resolution against 4,255 FDIC
      institutions with rapidfuzz, aggregating assets at holding-company level.</p></div>
    <div class="card"><h4>4 · Warehouse</h4><p>PostgreSQL with declared types, bulk
      <code>COPY</code> at ~36,700 rows/sec, 9 indexes, and 7 automated integrity checks.</p></div>
    <div class="card"><h4>5 · Analysis</h4><p>Six SQL files using CTEs and window functions —
      <code>RANK</code>, <code>LAG</code>, <code>ROW_NUMBER</code>, <code>PERCENT_RANK</code>.</p></div>
    <div class="card"><h4>6 · Presentation</h4><p>Four Postgres views feeding Tableau, so business
      logic lives in versioned SQL rather than in the workbook.</p></div>
  </div>

  <div class="chips">
    <span>Python 3.11</span><span>pandas</span><span>PostgreSQL 18</span><span>SQL window functions</span>
    <span>rapidfuzz</span><span>SciPy</span><span>Tableau</span><span>Jupyter</span><span>Git</span>
    <span>REST APIs</span>
  </div>

  <h3>Every log is generated, not written</h3>
  <p>The cleaning log, enrichment log and risk-score methodology are all <strong>produced by the
  scripts that do the work</strong>. Re-running a stage regenerates its documentation, so no figure
  in the repository can drift from the data it describes.</p>
</div></section>

<section><div class="wrap">
  <div class="tag">What I'd want to be asked about</div>
  <h2>Bugs I caught in my own work</h2>
  <p>Anyone can build a pipeline. These are the errors that would have produced confident, wrong
  answers with no visible symptom — and how they were found.</p>

  <div class="bug"><h4>A product rename that faked a 300% surge</h4>
  <p>CFPB renamed two product taxonomies in August 2023. Untreated, "Credit card" complaints read
  0 → 0 → 1,215 → 4,918 across Jun–Sep. Any analyst trusting that chart would have reported a real
  surge. Fixed losslessly by splitting the legacy label on <code>sub_product</code>: 32,541 + 2,769
  = 35,310, no remainder. Month-over-month swing at the boundary fell to 11.1%.</p></div>

  <div class="bug"><h4>A one-letter fuzzy match worth 7,923 complaints per $1B</h4>
  <p><code>Ocwen Financial Corporation</code> matched <code>OWEN FINANCIAL CORP</code> at 96.6 —
  a $0.4B community bank, one letter apart. The algorithm was confident; the number was absurd.
  Fixing it over-corrected and rejected Bank of America, whose every token is generic. Five guards
  followed, each from a specific false positive found by reviewing output.</p></div>

  <div class="bug"><h4>Ranks compared across different populations</h4>
  <p>A Tableau colour legend reading &minus;10 to 98 exposed it: volume was ranked across 112
  companies while the size-adjusted rate was ranked across only 28, then subtracted. Every gap was
  inflated. Caught, corrected, and the published figures updated.</p></div>

  <div class="bug"><h4>A scoring component counted twice</h4>
  <p>Two risk-score inputs correlated at Spearman &rho; = 0.954 and differed by 1.0 percentage
  point — the same construct at 55% of the total weight, crowding out the timeliness signal.
  Measured, removed, rebalanced.</p></div>

  <p>Eighteen in total. Each one is documented where it was found &mdash; in the
  <a href="{METHOD}">cleaning log</a>, the
  <a href="{REPO}/blob/main/reports/enrichment_log.md">enrichment log</a>, and the
  commit history.</p>
</div></section>

<section><div class="wrap">
  <div class="tag">Honesty</div>
  <h2>What would change these conclusions</h2>
  <ol>
    <li><strong>The size-adjusted metric is business-model sensitive.</strong> Assets proxy balance-sheet
    size, not customer count, so asset-light card issuers rank high partly by construction. Conduct
    claims in this project rest on per-complaint rates, which are immune to that distortion.</li>
    <li><strong>Complaint volume reflects propensity to complain</strong>, which varies with income,
    education and age. Some of what looks like a company effect may be a customer-mix effect.</li>
    <li><strong>Half of all complaint volume has no FDIC denominator</strong> — credit bureaus, NCUA
    credit unions, servicers and fintechs. MOHELA, the worst large servicer found, is invisible to
    the headline metric by construction.</li>
    <li><strong>CFPB discontinued the consumer-dispute flag in 2017</strong>, so whether a consumer
    accepted the resolution cannot be measured. Untimely-response and no-relief rates are
    substitutes, not equivalents.</li>
  </ol>
</div></section>

<footer><div class="wrap">
  <p style="color:#9fb0d0;margin-bottom:14px"><strong style="color:#e6ebf7">Sahil Vashisth</strong>
  &nbsp;·&nbsp; Data Analyst</p>
  <p><a href="{TABLEAU}">Live dashboard</a>·<a href="{REPO}">GitHub repository</a>·<a href="{REPORT}">Business report</a>·<a
     href="{NOTEBOOK}">Analysis notebook</a>·<a
     href="{REPO}/blob/main/reports/risk_score_methodology.md">Risk score methodology</a></p>
  <p style="margin-top:18px;font-size:13px">Data: <a
    href="https://www.consumerfinance.gov/data-research/consumer-complaints/">CFPB Consumer Complaint
    Database</a> and <a href="https://banks.data.fdic.gov/docs/">FDIC BankFind Suite</a> — both public domain.</p>
</div></footer>

</body></html>"""


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    used = ["fig_01_monthly_trend_overall.png",
            "fig_03_chisquare_residuals_product.png",
            "fig_05_size_adjusted_ranking.png"]
    for f in used:
        src = FIGS / f
        if src.exists():
            shutil.copy2(src, ASSETS / f)
            print(f"  asset: {f} ({src.stat().st_size/1024:.0f} KB)")
        else:
            print(f"  ! missing figure: {f}")

    # The Hinglish interview handbook is intentionally not copied here.
    stale = DOCS / "PROJECT_HANDBOOK.pdf"
    if stale.exists():
        stale.unlink()
        print("  removed stale docs/PROJECT_HANDBOOK.pdf (prep doc, not public)")

    # Stops GitHub Pages running the content through Jekyll, which would ignore
    # any file or folder beginning with an underscore.
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    (DOCS / "index.html").write_text(PAGE, encoding="utf-8")
    print(f"\n  wrote docs/index.html ({(DOCS/'index.html').stat().st_size/1024:.0f} KB)")
    print("\n  Enable at: Settings -> Pages -> Source: main branch, /docs folder")
    print("  Live URL : https://sahilsharma0309.github.io/banking-complaints-analysis/")


if __name__ == "__main__":
    main()
