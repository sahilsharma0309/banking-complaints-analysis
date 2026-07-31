-- BUSINESS QUESTION: Within each product, which specific issues drive the most
-- complaints, and which issues are most likely to end in monetary relief?
--
-- "Most complained about" and "most likely to cost the company money" are
-- different lists, and the gap between them is where remediation effort pays.
--
-- Technique: ROW_NUMBER partitioned by product to take a true top-N per group,
-- plus a within-product share so issues are comparable across products of very
-- different sizes.

WITH product_issue AS (
    SELECT
        product,
        product_short,
        issue,
        count(*)                                        AS complaints,
        count(*) FILTER (WHERE is_resolved)             AS resolved,
        count(*) FILTER (WHERE got_monetary_relief)     AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)             AS untimely,
        count(*) FILTER (WHERE is_servicemember)        AS servicemember,
        count(*) FILTER (WHERE is_older_american)       AS older_american
    FROM cfpb.complaints
    WHERE in_trend_window
    GROUP BY product, product_short, issue
),
scored AS (
    SELECT
        pi.*,
        SUM(complaints) OVER (PARTITION BY product)          AS product_total,
        ROUND(100.0 * complaints
              / SUM(complaints) OVER (PARTITION BY product), 2) AS pct_of_product,
        ROUND(100.0 * monetary_relief / NULLIF(resolved, 0), 2) AS relief_rate,
        ROW_NUMBER() OVER (PARTITION BY product ORDER BY complaints DESC)
                                                             AS rank_by_volume,
        ROW_NUMBER() OVER (PARTITION BY product
                           ORDER BY monetary_relief DESC)    AS rank_by_relief_count
    FROM product_issue pi
    WHERE complaints >= 50          -- drop taxonomy noise
)
SELECT
    product,
    product_short,
    rank_by_volume,
    issue,
    complaints,
    pct_of_product,
    product_total,
    resolved,
    monetary_relief,
    relief_rate,
    ROUND(100.0 * untimely / NULLIF(resolved, 0), 2)  AS untimely_rate,
    ROUND(100.0 * servicemember  / complaints, 2)     AS pct_servicemember,
    ROUND(100.0 * older_american / complaints, 2)     AS pct_older_american,
    rank_by_relief_count,
    -- Negative gap = an issue that costs companies money more often than its
    -- complaint volume suggests. Worth fixing first.
    rank_by_volume - rank_by_relief_count AS volume_vs_relief_rank_gap
FROM scored
WHERE rank_by_volume <= 10
ORDER BY product, rank_by_volume;
