-- BUSINESS QUESTION: Which companies resolve complaints worst -- lowest
-- monetary-relief rate and highest untimely-response rate -- once you control
-- for how many complaints they actually receive?
--
-- Technique: FILTER aggregates, a minimum-volume floor, and PERCENT_RANK to
-- position each company against the peer distribution rather than a raw sort.
--
-- TWO MEASUREMENT DECISIONS THAT CHANGE THE ANSWER:
--
-- 1. The denominator is `is_resolved`, not total complaints. 202 complaints are
--    still 'In progress' and have no outcome. Dividing by total volume would
--    penalise companies for having recent open cases.
--
-- 2. A 500-complaint floor is applied. Without it the "worst" list is dominated
--    by companies with 3 complaints and 0 relief -- a 0% relief rate on n=3 is
--    noise, not a finding. The floor is stated in the output so the cut is
--    visible rather than hidden.

WITH resolved AS (
    SELECT *
    FROM cfpb.complaints
    WHERE in_trend_window
      AND is_resolved              -- exclude 'In progress': no outcome yet
),
company_outcomes AS (
    SELECT
        company,
        count(*)                                            AS resolved_complaints,
        count(*) FILTER (WHERE got_monetary_relief)         AS monetary_relief,
        count(*) FILTER (WHERE got_any_relief)              AS any_relief,
        count(*) FILTER (WHERE closed_explanation_only)     AS explanation_only,
        count(*) FILTER (WHERE is_untimely)                 AS untimely,
        count(*) FILTER (WHERE company_disputes_facts)      AS disputes_facts,
        ROUND(AVG(days_to_company) FILTER (WHERE NOT dq_long_routing_lag), 3)
                                                            AS avg_days_to_company
    FROM resolved
    GROUP BY company
),
rates AS (
    SELECT
        company,
        resolved_complaints,
        monetary_relief,
        untimely,
        avg_days_to_company,
        ROUND(100.0 * monetary_relief    / resolved_complaints, 3) AS monetary_relief_rate,
        ROUND(100.0 * any_relief         / resolved_complaints, 3) AS any_relief_rate,
        ROUND(100.0 * explanation_only   / resolved_complaints, 3) AS explanation_only_rate,
        ROUND(100.0 * untimely           / resolved_complaints, 3) AS untimely_rate,
        ROUND(100.0 * disputes_facts     / resolved_complaints, 3) AS disputes_facts_rate
    FROM company_outcomes
    WHERE resolved_complaints >= 500      -- volume floor, see header
),
peer_median AS (
    -- PERCENTILE_CONT is an ordered-set aggregate; PostgreSQL does not allow it
    -- as a window function (no OVER ()), so the peer median is computed once
    -- here and cross-joined back in.
    SELECT
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY monetary_relief_rate)
            AS median_relief_rate,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY untimely_rate)
            AS median_untimely_rate
    FROM rates
)
SELECT
    r.company,
    r.resolved_complaints,
    r.monetary_relief_rate,
    r.any_relief_rate,
    r.explanation_only_rate,
    r.untimely_rate,
    r.disputes_facts_rate,
    r.avg_days_to_company,
    RANK() OVER (ORDER BY monetary_relief_rate ASC)  AS worst_relief_rank,
    RANK() OVER (ORDER BY untimely_rate DESC)        AS worst_timeliness_rank,
    ROUND(PERCENT_RANK() OVER (ORDER BY monetary_relief_rate ASC)::numeric, 4)
        AS relief_percentile_worst_first,
    ROUND(PERCENT_RANK() OVER (ORDER BY untimely_rate DESC)::numeric, 4)
        AS untimely_percentile_worst_first,
    -- Distance from the peer median, so "bad" is expressed relative to industry
    -- rather than as an absolute number that means nothing on its own.
    ROUND(pm.median_relief_rate::numeric, 3)                       AS peer_median_relief_rate,
    ROUND(r.monetary_relief_rate - pm.median_relief_rate::numeric, 3)
        AS relief_rate_vs_median,
    ROUND(r.untimely_rate - pm.median_untimely_rate::numeric, 3)
        AS untimely_rate_vs_median
FROM rates r
CROSS JOIN peer_median pm
ORDER BY untimely_rate DESC, monetary_relief_rate ASC;
