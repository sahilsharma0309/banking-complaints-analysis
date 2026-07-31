-- ============================================================================
-- HEADLINE METRIC
-- BUSINESS QUESTION: After adjusting for company size, which financial
-- companies actually generate the most consumer risk -- and which look fine on
-- raw volume but are outliers per dollar of assets?
-- ============================================================================
--
-- Metric: complaints per $1B of FDIC-reported total assets.
--
-- Technique: join to the FDIC holding-company table, RANK on both raw volume
-- and the size-adjusted rate, and compute the GAP between the two ranks. That
-- gap is the actual finding: a company ranked 12th by volume but 1st per dollar
-- is invisible to anyone reading a volume chart.
--
-- THREE THINGS THAT KEEP THIS HONEST:
--
-- 1. total_assets_b is SUMMED across every FDIC charter under the holding
--    company. Using only the largest subsidiary would understate the
--    denominator -- by 38% for Morgan Stanley -- and inflate the rate.
--
-- 2. Only companies matched to an FDIC institution appear here. Credit bureaus,
--    NCUA credit unions, loan servicers and fintechs have no asset denominator
--    BY DESIGN; they are analysed in 03_resolution_rates_by_company.sql and
--    listed in data/processed/unmatched_companies.csv. They are excluded from
--    this ranking, never silently treated as zero.
--
-- 3. A 500-complaint floor applies. Complaints per $1B is a ratio of two
--    numbers that can both be small; without a floor a tiny bank with 4
--    complaints can top the chart on arithmetic alone.
--
-- READ THIS BEFORE QUOTING THE RANKING
-- ------------------------------------
-- Total assets is a proxy for size, not for customer count, and the two come
-- apart by business model. A monoline credit-card issuer (Synchrony, Barclays
-- Delaware, Amex) serves millions of customers on a comparatively small balance
-- sheet, while a universal bank holds mortgages and commercial loans that add
-- assets without adding retail customers. Card issuers therefore sit high in
-- this ranking partly by construction.
--
-- That does NOT make the metric useless -- it is far better than raw volume,
-- and the within-peer comparisons are meaningful. But the correct reading is
-- "high complaints per dollar of balance sheet", not "provably worse conduct".
-- Where a genuine conduct claim is made in reports/insights.md it is supported
-- by the resolution-quality measures in 03_resolution_rates_by_company.sql
-- (relief rate, untimely rate), which are per-complaint and therefore immune to
-- this distortion.

WITH matched_companies AS (
    SELECT
        e.company,
        e.fdic_name,
        e.total_assets_b,
        e.n_charters,
        e.match_method,
        e.total_complaints,
        e.complaints_in_trend_window
    FROM cfpb.company_enriched e
    WHERE e.matched
      AND e.total_assets_b > 0
      AND e.total_complaints >= 500
),
outcomes AS (
    SELECT
        company,
        count(*) FILTER (WHERE is_resolved)                       AS resolved,
        count(*) FILTER (WHERE got_monetary_relief)               AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)                       AS untimely
    FROM cfpb.complaints
    WHERE in_trend_window
    GROUP BY company
),
combined AS (
    SELECT
        m.company,
        m.fdic_name,
        m.n_charters,
        m.match_method,
        m.total_complaints,
        m.total_assets_b,
        ROUND(m.total_complaints / m.total_assets_b, 3) AS complaints_per_1b_assets,
        o.resolved,
        ROUND(100.0 * o.monetary_relief / NULLIF(o.resolved, 0), 3) AS monetary_relief_rate,
        ROUND(100.0 * o.untimely        / NULLIF(o.resolved, 0), 3) AS untimely_rate
    FROM matched_companies m
    JOIN outcomes o USING (company)
),
ranked AS (
    SELECT
        c.*,
        RANK() OVER (ORDER BY total_complaints DESC)         AS volume_rank,
        RANK() OVER (ORDER BY complaints_per_1b_assets DESC) AS size_adjusted_rank,
        ROUND(AVG(complaints_per_1b_assets) OVER (), 3)      AS peer_avg_rate,
        ROUND(complaints_per_1b_assets
              / NULLIF(AVG(complaints_per_1b_assets) OVER (), 0), 2)
                                                             AS x_peer_average
    FROM combined c
)
SELECT
    size_adjusted_rank,
    volume_rank,
    -- Positive = looks safer on volume than it really is. This is the finding.
    volume_rank - size_adjusted_rank AS rank_gap,
    CASE
        WHEN volume_rank - size_adjusted_rank >= 5
            THEN 'UNDERSTATED by volume'
        WHEN volume_rank - size_adjusted_rank <= -5
            THEN 'overstated by volume'
        ELSE 'consistent'
    END AS volume_vs_size_verdict,
    company,
    fdic_name,
    n_charters,
    total_complaints,
    total_assets_b,
    complaints_per_1b_assets,
    x_peer_average,
    peer_avg_rate,
    resolved,
    monetary_relief_rate,
    untimely_rate,
    match_method
FROM ranked
ORDER BY size_adjusted_rank;
