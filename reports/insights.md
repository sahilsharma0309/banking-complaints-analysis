# US Banking Consumer Complaints — Risk & Resolution Analysis

**Business report · Stage 8**

**Scope:** 624,195 complaints about banking and lending products filed with the
CFPB, 2023-01-01 → 2025-12-31 (36 complete months), across 3,193 companies,
enriched with FDIC total assets. Credit reporting is excluded — it is 87% of raw
CFPB volume but is filed against non-bank credit bureaus. See
[`README.md`](../README.md#scope-decision-why-credit-reporting-is-excluded).

**National baselines** used as the comparison point throughout:

| Measure | Value |
|---|---:|
| Complaints resolved | 623,992 |
| Monetary relief rate | **9.93%** |
| Untimely response rate | **2.32%** |
| Closed with explanation only | 78.13% |

---

## 1. Raw complaint volume is a size proxy, not a risk signal — and it hides the worst performers

Wells Fargo (41,051) and JPMorgan Chase (40,391) generate almost identical
complaint volume. They are not comparable risks. JPMorgan holds **2.2× the
assets**, so per dollar of balance sheet Wells Fargo generates **2.2× the
consumer friction**.

Normalising by FDIC total assets reorders the industry. **Both ranks below are
computed over the same 28 FDIC-matched depositories**, so the move is a
like-for-like comparison:

| Company | Volume rank | Size-adj. rank | Move | Complaints per $1B |
|---|---:|---:|---:|---:|
| **Optum Bank** | 28 | **10** | **▲ 18** | 25.2 |
| **First National Bank of Omaha** | 25 | **9** | **▲ 16** | 31.0 |
| **SoFi Technologies** | 18 | **3** | **▲ 15** | 81.5 |
| **Barclays Bank Delaware** | 13 | **2** | **▲ 11** | 128.8 |
| **Synchrony Financial** | 7 | **1** | ▲ 6 | **147.8** |
| Wells Fargo | 1 | 11 | ▼ 10 | 22.0 |
| Bank of America | 4 | 19 | ▼ 15 | 12.1 |
| JPMorgan Chase | 2 | 25 | **▼ 23** | 10.1 |

**Synchrony Financial is the headline case.** It is 7th by volume among these
peers — and **1st in the country per dollar of assets**, at 147.8 complaints per
$1B against a matched-peer average of 32.3. That is **4.6× the peer average**,
and **14.7× JPMorgan**, the second-largest complaint generator in the dataset.

The sharpest reversal is JPMorgan itself: **2nd by raw volume, 25th of 28 once
size-adjusted**. On a volume league table it looks like one of the worst actors
in US banking. Per dollar of balance sheet it is one of the best.

**A caveat stated rather than buried:** total assets proxies *balance-sheet
size*, not *customer count*. Card-focused issuers (Synchrony, Barclays Delaware,
Amex) serve many customers on comparatively small balance sheets, so they rank
high partly by business model. The correct reading is *"high consumer friction
per dollar of balance sheet"* — a genuine risk-concentration signal — not
*"proven misconduct"*. Insight 2 uses per-complaint measures, which are immune
to this distortion.

> **Recommendation — for risk and supervisory teams:** stop ranking institutions
> on complaint counts. Adopt complaints per $1B of assets as the primary
> screening metric and re-baseline monitoring thresholds against it. Institutions
> whose size-adjusted rank exceeds their volume rank by more than 10 places
> (SoFi, Barclays Delaware, Santander, Synchrony) warrant review that raw-volume
> monitoring would never trigger.

![Size-adjusted risk ranking](figures/fig_05_size_adjusted_ranking.png)

---

## 2. Student loan servicing is a systemic failure, not a company problem

The national untimely-response rate is **2.32%**. Student loan servicers are not
near it:

| Company | Complaints | Untimely rate | vs national | Monetary relief |
|---|---:|---:|---:|---:|
| "Servicer under contract with Federal Student Aid" | 1,667 | **100.0%** | **43×** | 0.00% |
| EdFinancial Services | 4,014 | **43.3%** | 19× | 0.00% |
| MOHELA | 17,225 | **27.2%** | 12× | 1.57% |
| Conduent | 514 | 19.3% | 8× | 0.58% |

One entity failed to respond on time to **every single one** of 1,667
complaints. MOHELA — the largest, at 17,225 complaints — missed the deadline on
more than a quarter of them and paid relief on 1.6%.

This is a sector characteristic, not a handful of bad actors. At product level:

| Product | Untimely rate | Monetary relief rate |
|---|---:|---:|
| **Student loan** | **17.69%** | **0.80%** |
| Credit card | 0.30% | 13.54% |

Student loan complaints are **59× more likely to go unanswered on time** and
**17× less likely to produce monetary relief** than credit card complaints. And
the volume is not static — student loan complaints **doubled** over the window,
from 10,633 in 2023 to 21,307 in 2025 (**+100.4%**).

> **Recommendation — for regulators and servicer oversight:** treat response
> timeliness as a supervisory trigger independent of complaint volume. MOHELA
> alone accounts for 4,632 late responses. A servicer that misses the deadline
> on a quarter of complaints has a capacity or process failure that complaint
> volume does not capture, and the doubling of inbound volume means the gap is
> widening, not closing.

---

## 3. Whether a complaint achieves anything depends more on *who* you complain to than *what* about

Tested formally with a chi-square test of independence on 623,992 resolved
complaints. At this sample size p-values are meaningless — everything is
significant — so conclusions are drawn from **Cramér's V** effect sizes:

| Association | χ² | df | Cramér's V |
|---|---:|---:|---:|
| Outcome × Product | 21,575 | 7 | 0.186 *(weak)* |
| Outcome × **Company** | 65,031 | 111 | **0.341** *(strong)* |

The company association is **1.8× stronger** than the product association. The
product you are complaining about matters; **who you are complaining about
matters nearly twice as much.**

The practical spread is severe. Across the 112 companies with ≥500 resolved
complaints, monetary relief ranges from **0.0%** to **38.5%**, against a median
of 1.3%. Among the largest banks, handling of comparable complaints diverges
sharply:

| Company | Monetary relief rate | Untimely rate |
|---|---:|---:|
| Bank of America | **32.7%** | 1.83% |
| Citibank | 26.8% | 0.00% |
| American Express | 25.5% | 0.39% |
| Wells Fargo | 9.9% | 0.01% |
| Capital One | 8.8% | 0.01% |

Bank of America resolves complaints with monetary relief at **3.7× the rate of
Capital One** — but is also the only major bank with a materially elevated
untimely rate. These are two different competencies and a single "complaint
score" would blur them.

> **Recommendation — for competitive benchmarking and consumer advocacy:**
> publish relief rates per company alongside volume. A consumer choosing a credit
> card cannot see that their odds of remediation vary nearly fourfold by issuer.
> For firms: a relief rate far below peers on comparable products is a
> defensible-conduct question that will not appear in any volume-based
> dashboard.

![Chi-square residuals](figures/fig_03_chisquare_residuals_product.png)

---

## 4. Debt and credit management is the fastest-growing risk category — from a small base, and largely invisible

Complaint growth by product, 2023 vs 2025:

| Product | 2023 | 2025 | Change |
|---|---:|---:|---:|
| **Debt or credit management** | 484 | 4,267 | **+781.6%** |
| Student loan | 10,633 | 21,307 | +100.4% |
| Payday / personal loan | 7,242 | 13,138 | +81.4% |
| Checking / savings | 49,873 | 84,191 | +68.8% |
| Credit card | 54,409 | 89,976 | +65.4% |
| Mortgage | 22,853 | 24,697 | +8.1% |

Debt and credit management — debt settlement and credit repair services — grew
nearly **nine-fold** in three years, from a base so small it contributes only
1.1% of total volume today. Its monetary relief rate is **3.55%**, roughly a
third of the national average, and its untimely rate is 8.61%, nearly 4× the
national figure.

Mortgage is the counter-example: the only product that did not meaningfully grow
(+8.1%) despite being the largest consumer credit exposure by dollar value.

> **Recommendation — for emerging-risk monitoring:** flag growth rate, not just
> level. A category at 1.1% of volume growing at 780% will be a material problem
> within two years, and every volume-ranked dashboard will show it as
> insignificant until it is too late to act early. Debt settlement and credit
> repair firms sit largely outside prudential regulation — 50% of complaint
> volume in this dataset belongs to entities with no FDIC asset denominator at
> all.

---

## What would change my conclusions

Stated so a reader can weigh the analysis rather than take it on trust:

1. **The size-adjusted metric is business-model sensitive.** Assets proxy size,
   not customers. If customer-count data were available (it is not, publicly),
   the ranking in Insight 1 would likely compress. Insights 2–3 use
   per-complaint rates and are unaffected.

2. **Complaint volume reflects propensity to complain.** Better-educated,
   higher-income and older customers complain more. Some of what looks like a
   company effect may be a customer-mix effect. The chi-square in Insight 3
   cannot separate these.

3. **50% of complaint volume has no FDIC denominator** — credit bureaus, NCUA
   credit unions, servicers, fintechs. They appear in Insights 2–4 but cannot
   appear in Insight 1's ranking at all. MOHELA, the worst large servicer, is
   invisible to the headline metric by construction.

4. **January 2025 contains a coordinated filing event** — 18,441 excess
   complaints, 67% from two companies. Flagged, not removed. The size-adjusted
   ranking was re-computed without that month and all 28 companies held the same
   rank, so Insight 1 is robust to it. Raw counts elsewhere still include it.

5. **CFPB discontinued the consumer-dispute flag in 2017**, so "did the consumer
   accept the resolution" cannot be measured. Untimely response and no-relief
   rates are substitutes, not equivalents.

---

**Method:** [`README.md`](../README.md) · **Cleaning decisions:**
[`cleaning_log.md`](cleaning_log.md) · **Match quality:**
[`enrichment_log.md`](enrichment_log.md) · **Score formula:**
[`risk_score_methodology.md`](risk_score_methodology.md) · **Statistics:**
[`notebooks/eda.ipynb`](../notebooks/eda.ipynb)
