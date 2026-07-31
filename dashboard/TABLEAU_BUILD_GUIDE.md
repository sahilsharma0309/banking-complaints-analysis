# Tableau build guide

> ## ⚡ Shortcut: open the pre-built workbook
>
> ```bash
> venv\Scripts\python scripts\07_tableau_handoff.py        # builds the .hyper
> venv\Scripts\python scripts\08_build_tableau_workbook.py # builds the .twb
> ```
>
> Then double-click **`dashboard/banking_complaints_dashboard.twb`**. All four
> sheets and the assembled dashboard are already built — nothing to drag, no
> relationship dialogs.
>
> The rest of this guide is the manual path. It is still worth reading once: it
> explains *what* the generated XML encodes and why each choice was made, and
> you will need §7 to publish either way.

Everything is prepared. This walks you from a blank Tableau Desktop to a
published Tableau Public dashboard.

**Assumed:** intermediate Tableau (you know what a pill, a discrete/continuous
field, a dual axis and a dashboard action are).

**Time:** ~60–90 minutes.

---

## 0. Before you start

Run the pipeline through Stage 7 so the views exist:

```bash
venv\Scripts\python scripts\07_tableau_handoff.py
```

That prints your connection details and creates four views in the `cfpb` schema.

> ### ⚠️ Read this before you plan to publish
>
> **Tableau Public cannot host a live connection to a database on your laptop.**
> `localhost` means *your machine*, and Tableau Public's servers cannot reach it.
>
> The workflow is therefore: **build on the live PostgreSQL connection** (fast,
> always current), then **convert to an extract** immediately before publishing
> (§7). If you skip that step, publishing fails or produces an empty workbook.
>
> If you would rather avoid the conversion entirely, connect to
> `dashboard/banking_complaints.hyper` from the start — same data, already an
> extract. You lose the ability to re-query the full 624k-row complaint table,
> which only matters for the optional detail sheet in §5.

---

## 1. Connect Tableau to PostgreSQL

1. Open Tableau Desktop → **Connect → To a Server → PostgreSQL**.
   *If PostgreSQL isn't listed, install the driver from
   <https://www.tableau.com/support/drivers>, choose PostgreSQL, then restart Tableau.*

2. Fill in:

   | Field | Value |
   |---|---|
   | Server | `localhost` |
   | Port | `5432` |
   | Database | `banking_complaints` |
   | Authentication | Username and Password |
   | Username | `postgres` |
   | Password | the `PGPASSWORD` value from your `.env` |
   | Require SSL | leave unchecked (local connection) |

3. **Sign In**.

4. On the data-source page, set **Schema** to `cfpb` (not `public` — if you leave
   it on `public` the view list will be empty and it looks like the load failed).

5. Drag **`v_company_summary`** onto the canvas.

6. Bottom left, click **Sheet 1**.

> **Connection type:** leave it on **Live** while building. `v_company_summary`
> is 112 rows and `v_monthly_trend` is 281 — instant either way.

### The four views

| View | Rows | Use it for |
|---|---:|---|
| `v_company_summary` | 112 | Charts 1, 3 — one row per company, ≥500 complaints |
| `v_monthly_trend` | 281 | Chart 2 — pre-aggregated monthly by product |
| `v_state_summary` | 51 | Chart 4 — one row per state + DC |
| `v_complaints_enriched` | 624,195 | Optional detail sheet / free-form filtering |

Business logic (the 500-complaint floor, resolved-only denominators, the trend
window, the FDIC join) lives **in the views**, so you don't rebuild it in
calculated fields.

---

## 2. Chart 1 — Size-adjusted risk ranking *(the headline)*

This is the chart the whole project exists to produce. It shows who is riskiest
**per dollar of balance sheet**, not by raw volume.

**Sheet name:** `Size-Adjusted Risk`

1. Data source: `v_company_summary`.
2. **Rows:** `Company` (dimension).
3. **Columns:** `Complaints Per 1b Assets` → set to **AVG**
   *(one row per company, so AVG returns the value itself; SUM would be
   identical here but AVG is safer if you later relax the filter).*
4. **Filters:**
   - `Is Fdic Matched` → **True**. Non-banks have no denominator; without this
     you get a wall of blank bars.
   - `Complaints Per 1b Assets` → **Special → Non-null values**.
5. **Marks:** Bar.
   - **Color:** `Rank Gap` → continuous. Edit colors → **Red-Blue Diverging**,
     click **Reversed**, set **Center = 0**.
     Now red = riskier than volume implies, blue = volume overstates it.
   - **Label:** `Complaints Per 1b Assets`, format to 1 decimal.
   - **Tooltip:** add `Volume Rank`, `Size Adjusted Rank`, `Rank Gap`,
     `Total Complaints`, `Total Assets B`, `Monetary Relief Rate`, `Fdic Status`.
6. Sort `Company` **descending by `Complaints Per 1b Assets`**
   *(click the sort icon on the Company axis).*
7. **Filter to the top 15:** drag `Company` to Filters → **Top** tab → By field →
   Top **15** by `Complaints Per 1b Assets` → Maximum.
8. Title: **`Complaints per $1B of assets — who is riskiest for their size`**

**Expected result:** Synchrony ~148 at the top, Barclays Delaware ~129, SoFi ~81,
Amex ~79, Capital One ~56. Wells Fargo — the #1 company by raw volume — appears
around 11th at ~22.

> **Add this caption to the sheet** (Worksheet → Show Caption): *"Total assets
> proxies balance-sheet size, not customer count. Card-focused issuers rank high
> partly by business model. Conduct comparisons should use Chart 3."*

---

## 3. Chart 2 — Complaint trend over time

**Sheet name:** `Trend`

1. Data source: `v_monthly_trend`.
2. **Columns:** `Month Start` → right-click the pill → **Month (continuous, green)**.
   *Continuous, not discrete — you want a real time axis, not 12 buckets.*
3. **Rows:** `Complaints` → **SUM**.
4. **Marks:** Line. Drag `Product Short` to **Color**.
5. Add a trend indicator: drag a second `Complaints` to Rows → right-click →
   **Dual Axis** → **Synchronize Axis** → set that mark type to Line, remove
   Color, and set it to **Average with 95% CI** from the Analytics pane if you
   want a band. *(Optional — skip if it clutters.)*
6. **Filters:** `Product Short` (show filter, multiple values dropdown),
   `Month Start` (Range of Dates, show filter).
7. Title: **`Monthly complaints by product, 2023–2025`**

> **Annotate the January 2025 spike.** Right-click the Jan-2025 point →
> **Annotate → Point**. Text:
> *"Jan-2025: coordinated filing event. 18,441 extra complaints, 67% from two
> companies (Navy Federal, Capital One). Not organic demand — see notebook §7."*
>
> Without this, every viewer will read that spike as a real service collapse.

---

## 4. Chart 3 — Resolution-quality scatter

Shows that complaint *volume* and complaint *handling* are different problems.

**Sheet name:** `Resolution Quality`

1. Data source: `v_company_summary`.
2. **Columns:** `Monetary Relief Rate` → **AVG**.
3. **Rows:** `Untimely Rate` → **AVG**.
4. **Marks:** Circle.
   - **Detail:** `Company` *(this is what makes one mark per company)*.
   - **Size:** `Total Complaints`.
   - **Color:** `Risk Tier`. Assign a sensible ramp — Low = green through
     Severe = dark red.
   - **Label:** `Company`, then **Label → Marks to Label → Most Extreme**, so
     only the outliers are named.
   - **Tooltip:** `Total Complaints`, `Resolved Complaints`, `Pct No Relief`,
     `Conduct Risk Score`, `Avg Days To Company`, `Fdic Status`.
5. **Reference lines:** right-click each axis → **Add Reference Line** →
   Entire Table → **Median** → dashed grey.
   The upper-left quadrant is now "gives little relief *and* responds late" —
   the quadrant that matters.
6. Title: **`Relief rate vs untimely rate — upper-left is worst`**

**Expected result:** a cluster near the origin, with student-loan servicers
(MOHELA, EdFinancial, and "Servicer under contract with Federal Student Aid" at
100% untimely) stranded high on the y-axis.

---

## 5. Chart 4 — Geography

**Sheet name:** `By State`

1. Data source: `v_state_summary`.
2. Double-click `State`. Tableau assigns it a geographic role and builds a map.
   *If it doesn't: right-click `State` → **Geographic Role → State/Province**.*
3. **Marks:** Map (filled).
   - **Color:** `Complaints` → SUM.
   - **Tooltip:** `Top Issue`, `Top Product`, `Monetary Relief Rate`,
     `Untimely Rate`, `Companies`, `Pct Of National`.
4. Title: **`Complaint volume by state`**

> **Worth knowing:** raw counts here mostly track population — California, Texas
> and Florida lead because they are large. For a more interesting map, switch
> **Color** to `Untimely Rate` or `Monetary Relief Rate`, which are already
> normalised and reveal genuine regional differences.

**Optional detail sheet:** connect `v_complaints_enriched` and build a text table
of `Company`, `Product Short`, `Issue`, `Date Received` for drill-down. Set this
one to an **Extract** if it feels slow.

---

## 6. Assemble the dashboard

1. **New Dashboard.** Size: **Automatic**, or fixed **1600 × 900**.
2. Layout:

```
┌──────────────────────────────────────────────────────────┐
│  Title:  US Banking Complaints — Risk & Resolution       │
├───────────────────────────┬──────────────────────────────┤
│  Size-Adjusted Risk       │  Trend                       │
│  (Chart 1)                │  (Chart 2)                   │
├───────────────────────────┼──────────────────────────────┤
│  Resolution Quality       │  By State                    │
│  (Chart 3)                │  (Chart 4)                   │
└───────────────────────────┴──────────────────────────────┘
                    [ filters down the right edge ]
```

3. **Filters** — add via each sheet's ▾ → *Filters*, then set each to
   **Apply to Worksheets → All Using This Data Source**:
   - `Product Short` — multiple values dropdown
   - `State` — multiple values dropdown
   - `Month Start` — range of dates slider
   - `Risk Tier` — multiple values list
   - `Is Fdic Matched` — single value; **default True**

4. **Dashboard action** — Dashboard → Actions → **Add Action → Filter**:
   Source `Size-Adjusted Risk` → Target `Trend` and `Resolution Quality`,
   Run on **Select**, Clearing the selection → **Show all values**.
   Clicking a company now filters the other panels to it.

5. **Add a caveat text box.** Small, bottom of the dashboard:

   > *Banking & lending products only; credit reporting excluded (87% of raw CFPB
   > volume, filed against non-bank credit bureaus). Size-adjusted metric covers
   > FDIC-insured depositories only — 50% of complaint volume belongs to
   > non-banks with no asset denominator. Jan-2025 contains a coordinated filing
   > event.*

   A reviewer who spots an unstated limitation assumes you missed it. Stating it
   reads as competence.

---

## 7. Publish to Tableau Public

**You must convert to an extract first** — see the warning at the top.

1. **Data → `v_company_summary` → Extract**, then click **Extract** on the
   radio button in the data source pane. Repeat for every data source in the
   workbook (check the Data menu — it's easy to miss one).
   - For `v_complaints_enriched`, add an extract filter first
     (Data source page → Filters → Add → `Year Month`) if you want to keep the
     file small.
2. Wait for extraction to finish (a few seconds; `v_complaints_enriched` takes
   longer).
3. **Server → Tableau Public → Save to Tableau Public As…**
4. Sign in (create a free account at <https://public.tableau.com> if needed).
5. Name it: **`US Banking Consumer Complaints — Risk & Resolution Analysis`**
6. Save. A browser tab opens with the published workbook.
7. Copy the URL — it looks like
   `https://public.tableau.com/views/<workbook>/<dashboard>`.
8. On the Tableau Public site: **Edit Details** → add a description, and tick
   **Show Workbook** so it's publicly visible.

### Put the link in the README

Replace the placeholder in `README.md`:

```markdown
## Dashboard
**[View the interactive dashboard on Tableau Public](PASTE_YOUR_URL_HERE)**
```

Then take a screenshot of the finished dashboard, save it as
`reports/figures/dashboard_screenshot.png`, and reference it in the README —
recruiters look at images before they click links.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No tables listed after connecting | Schema is set to `public`. Change it to `cfpb`. |
| "PostgreSQL driver not found" | Install from <https://www.tableau.com/support/drivers>, restart Tableau. |
| Connection refused | Postgres isn't running. `Get-Service postgresql*` in PowerShell; start it if stopped. |
| Password authentication failed | The password in Tableau must match `PGPASSWORD` in `.env` exactly. |
| Chart 1 shows many blank bars | The `Is Fdic Matched = True` filter is missing. Non-banks have no denominator. |
| Scatter shows one giant dot | `Company` isn't on **Detail**. Without it everything aggregates to one mark. |
| Map is empty | `State` lacks a geographic role. Right-click → Geographic Role → State/Province. |
| Publish fails / dashboard empty online | Still on a Live localhost connection. Convert every data source to an Extract (§7). |
| Trend line looks like it collapses at the end | You're querying a raw table instead of a view. The views already exclude the one-day 2026 stub. |

---

## Backup files

If the database is unavailable, everything is also in `dashboard/`:

| File | Rows |
|---|---:|
| `banking_complaints.hyper` | all four tables, native Tableau extract |
| `company_summary.csv` | 112 |
| `monthly_trend.csv` | 281 |
| `state_summary.csv` | 51 |
| `top_issues_by_product.csv` | 98 |

For the `.hyper`: **Connect → To a File → More… → select the file**. The tables
are in its `Extract` schema.
