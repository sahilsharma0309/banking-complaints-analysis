-- BUSINESS QUESTION: How does complaint risk vary geographically -- which
-- states generate the most complaints, what is each state's dominant issue, and
-- where are companies slowest to respond?
--
-- Technique: ROW_NUMBER partitioned by state to pick each state's top issue,
-- then a second CTE joins state totals back so the top issue is reported
-- alongside the state's overall profile rather than in isolation.
--
-- SCOPE: restricted to state_type = 'state' (50 states + DC). Territories are
-- reported separately and military APO/FPO codes (AA/AE/AP) are excluded
-- entirely -- they are postal routing codes, not places, and would render as
-- phantom geography on a map.

WITH state_totals AS (
    SELECT
        state,
        count(*)                                    AS complaints,
        count(*) FILTER (WHERE is_resolved)         AS resolved,
        count(*) FILTER (WHERE got_monetary_relief) AS monetary_relief,
        count(*) FILTER (WHERE is_untimely)         AS untimely,
        count(DISTINCT company)                     AS companies_complained_about,
        ROUND(AVG(days_to_company) FILTER (WHERE NOT dq_long_routing_lag), 2)
                                                    AS avg_days_to_company
    FROM cfpb.complaints
    WHERE in_trend_window
      AND state_type = 'state'
    GROUP BY state
),
state_issue AS (
    SELECT
        state,
        issue,
        count(*) AS issue_complaints,
        ROW_NUMBER() OVER (PARTITION BY state ORDER BY count(*) DESC) AS rn
    FROM cfpb.complaints
    WHERE in_trend_window
      AND state_type = 'state'
    GROUP BY state, issue
),
state_product AS (
    SELECT
        state,
        product_short,
        count(*) AS product_complaints,
        ROW_NUMBER() OVER (PARTITION BY state ORDER BY count(*) DESC) AS rn
    FROM cfpb.complaints
    WHERE in_trend_window
      AND state_type = 'state'
    GROUP BY state, product_short
)
SELECT
    RANK() OVER (ORDER BY t.complaints DESC)                     AS volume_rank,
    t.state,
    t.complaints,
    ROUND(100.0 * t.complaints / SUM(t.complaints) OVER (), 3)   AS pct_of_national,
    t.companies_complained_about,
    si.issue                                                     AS top_issue,
    si.issue_complaints                                          AS top_issue_complaints,
    ROUND(100.0 * si.issue_complaints / t.complaints, 2)         AS top_issue_pct,
    sp.product_short                                             AS top_product,
    ROUND(100.0 * sp.product_complaints / t.complaints, 2)       AS top_product_pct,
    ROUND(100.0 * t.monetary_relief / NULLIF(t.resolved, 0), 2)  AS monetary_relief_rate,
    ROUND(100.0 * t.untimely        / NULLIF(t.resolved, 0), 2)  AS untimely_rate,
    t.avg_days_to_company,
    -- How each state's relief rate compares with the national picture.
    ROUND(100.0 * t.monetary_relief / NULLIF(t.resolved, 0)
          - 100.0 * SUM(t.monetary_relief) OVER () / SUM(t.resolved) OVER (), 2)
        AS relief_rate_vs_national
FROM state_totals t
JOIN state_issue   si ON si.state = t.state AND si.rn = 1
JOIN state_product sp ON sp.state = t.state AND sp.rn = 1
ORDER BY volume_rank;
