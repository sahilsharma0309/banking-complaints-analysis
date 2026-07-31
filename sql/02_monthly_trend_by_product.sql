-- BUSINESS QUESTION: How has complaint volume moved month over month for each
-- product since 2023, and which products are accelerating?
--
-- Technique: LAG for the previous month and the same month a year earlier,
-- LEAD to look ahead, and a 3-month moving average to damp the noise that makes
-- raw MoM percentages misleading on small products.
--
-- NOTE: reads `product` (cleaned), never `product_raw`. CFPB renamed two
-- product taxonomies in Aug-2023; on the raw labels this query would report
-- "Credit card" rising from 0 to 4,918 in a single month, which is a renaming
-- artefact rather than a real surge. See reports/cleaning_log.md.

WITH monthly AS (
    SELECT
        product,
        product_short,
        year_month,
        MIN(date_received)                          AS month_start,
        count(*)                                    AS complaints,
        count(*) FILTER (WHERE got_monetary_relief) AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)         AS untimely
    FROM cfpb.complaints
    WHERE in_trend_window
    GROUP BY product, product_short, year_month
),
with_lags AS (
    SELECT
        m.*,
        LAG(complaints, 1)  OVER w AS prev_month,
        LAG(complaints, 12) OVER w AS same_month_last_year,
        LEAD(complaints, 1) OVER w AS next_month,
        ROUND(AVG(complaints) OVER (PARTITION BY product ORDER BY year_month
                                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)
                                   AS moving_avg_3m,
        FIRST_VALUE(complaints) OVER w AS first_month_volume
    FROM monthly m
    WINDOW w AS (PARTITION BY product ORDER BY year_month)
)
SELECT
    product,
    product_short,
    year_month,
    month_start,
    complaints,
    prev_month,
    complaints - prev_month AS mom_change,
    ROUND(100.0 * (complaints - prev_month) / NULLIF(prev_month, 0), 2)
        AS mom_pct_change,
    same_month_last_year,
    ROUND(100.0 * (complaints - same_month_last_year)
          / NULLIF(same_month_last_year, 0), 2) AS yoy_pct_change,
    moving_avg_3m,
    ROUND(100.0 * (complaints - first_month_volume)
          / NULLIF(first_month_volume, 0), 2)   AS pct_change_since_start,
    monetary_relief,
    untimely,
    ROUND(100.0 * untimely / NULLIF(complaints, 0), 2) AS untimely_rate
FROM with_lags
ORDER BY product, year_month;
