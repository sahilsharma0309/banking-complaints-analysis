-- BUSINESS QUESTION: Which companies generate the most consumer complaints, and
-- how concentrated is complaint volume across the industry?
--
-- This is the NAIVE view of risk on purpose -- it is the baseline that
-- 04_size_adjusted_risk.sql exists to overturn. Read them together.
--
-- Technique: RANK() vs DENSE_RANK() to expose ties, a window SUM for the
-- running share of total volume, and NTILE to bucket the long tail.
-- Bounded to the trend window (2023-01-01 .. 2025-12-31, 36 complete months)
-- so the one-day 2026 stub cannot distort totals.

WITH company_volume AS (
    SELECT
        company,
        count(*)                                          AS complaints,
        count(*) FILTER (WHERE is_resolved)               AS resolved,
        count(*) FILTER (WHERE got_monetary_relief)       AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)               AS untimely,
        count(DISTINCT product)                           AS products_touched,
        count(DISTINCT state) FILTER (WHERE state_type = 'state') AS states_touched,
        min(date_received)                                AS first_complaint,
        max(date_received)                                AS last_complaint
    FROM cfpb.complaints
    WHERE in_trend_window
    GROUP BY company
),
ranked AS (
    SELECT
        cv.*,
        RANK()       OVER (ORDER BY complaints DESC) AS volume_rank,
        DENSE_RANK() OVER (ORDER BY complaints DESC) AS volume_dense_rank,
        NTILE(4)     OVER (ORDER BY complaints DESC) AS volume_quartile,
        ROUND(100.0 * complaints
              / SUM(complaints) OVER (), 4)          AS pct_of_all_complaints,
        ROUND(100.0 * SUM(complaints) OVER (ORDER BY complaints DESC
                                            ROWS UNBOUNDED PRECEDING)
              / SUM(complaints) OVER (), 2)          AS cumulative_pct
    FROM company_volume cv
)
SELECT
    volume_rank,
    volume_dense_rank,
    company,
    complaints,
    pct_of_all_complaints,
    cumulative_pct,
    resolved,
    ROUND(100.0 * monetary_relief / NULLIF(resolved, 0), 2) AS monetary_relief_rate,
    ROUND(100.0 * untimely        / NULLIF(resolved, 0), 2) AS untimely_rate,
    products_touched,
    states_touched,
    first_complaint,
    last_complaint
FROM ranked
WHERE volume_rank <= 100
ORDER BY volume_rank;
