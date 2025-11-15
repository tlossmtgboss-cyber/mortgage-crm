-- ============================================================================
-- MISSION CONTROL DIAGNOSTIC QUERIES
-- Run with: psql $PROD_DATABASE_URL -f backend/diagnostic_queries.sql
-- ============================================================================

-- Query 1: Table Sizes
\echo '============================================================'
\echo 'QUERY 1: Mission Control Table Sizes'
\echo '============================================================'
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size('public.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename LIKE 'ai_%'
ORDER BY pg_total_relation_size('public.'||tablename) DESC;

-- Query 2: Recent Actions Detail
\echo ''
\echo '============================================================'
\echo 'QUERY 2: Recent Actions (Last 20)'
\echo '============================================================'
SELECT
    LEFT(action_id, 30) as action_id,
    agent_name,
    action_type,
    autonomy_level,
    ROUND(confidence_score::numeric, 2) as confidence,
    outcome,
    created_at
FROM ai_colleague_actions
ORDER BY created_at DESC
LIMIT 20;

-- Query 3: Agent Performance Matrix
\echo ''
\echo '============================================================'
\echo 'QUERY 3: Agent Performance Matrix (Last 30 Days)'
\echo '============================================================'
SELECT
    agent_name,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
    ROUND(COUNT(*) FILTER (WHERE autonomy_level = 'full')::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) as auto_pct,
    COUNT(*) FILTER (WHERE outcome = 'success') as success,
    ROUND(COUNT(*) FILTER (WHERE outcome = 'success')::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) as success_pct,
    ROUND(AVG(confidence_score)::NUMERIC, 3) as avg_conf,
    ROUND(AVG(impact_score)::NUMERIC, 3) as avg_impact
FROM ai_colleague_actions
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name
ORDER BY total DESC;

-- Query 4: Daily Activity Pattern (Last 7 Days)
\echo ''
\echo '============================================================'
\echo 'QUERY 4: Daily Activity Pattern (Last 7 Days)'
\echo '============================================================'
SELECT
    DATE(created_at) as day,
    COUNT(*) as actions,
    COUNT(*) FILTER (WHERE autonomy_level = 'full') as autonomous,
    COUNT(*) FILTER (WHERE outcome = 'success') as successful,
    ROUND(AVG(confidence_score)::NUMERIC, 2) as avg_conf
FROM ai_colleague_actions
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY day DESC;

-- Query 5: Failed Actions Analysis
\echo ''
\echo '============================================================'
\echo 'QUERY 5: Failed Actions Analysis'
\echo '============================================================'
SELECT
    agent_name,
    action_type,
    COUNT(*) as failure_count,
    ROUND(AVG(confidence_score)::NUMERIC, 2) as avg_conf_when_failed,
    MAX(created_at) as last_failure
FROM ai_colleague_actions
WHERE outcome = 'failure'
    AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name, action_type
ORDER BY failure_count DESC
LIMIT 10;

-- Query 6: Daily Rollup Summary
\echo ''
\echo '============================================================'
\echo 'QUERY 6: Daily Performance Rollup (Last 10 Days)'
\echo '============================================================'
SELECT
    date,
    agent_name,
    total_actions,
    autonomous_actions,
    ROUND(success_rate::numeric, 1) as success_rate,
    ROUND(avg_confidence_score::numeric, 2) as avg_conf
FROM ai_performance_daily
WHERE date >= CURRENT_DATE - INTERVAL '10 days'
ORDER BY date DESC, agent_name
LIMIT 20;

-- Query 7: Health Score Trend
\echo ''
\echo '============================================================'
\echo 'QUERY 7: Health Score History (Last 10 Calculations)'
\echo '============================================================'
SELECT
    calculated_at,
    ROUND(overall_score::numeric, 1) as overall,
    ROUND(autonomy_score::numeric, 1) as autonomy,
    ROUND(accuracy_score::numeric, 1) as accuracy,
    total_actions,
    score_trend
FROM ai_health_score
ORDER BY calculated_at DESC
LIMIT 10;

-- Query 8: Active Insights
\echo ''
\echo '============================================================'
\echo 'QUERY 8: Active AI Insights'
\echo '============================================================'
SELECT
    LEFT(insight_id, 30) as insight_id,
    insight_type,
    LEFT(pattern_description, 50) as pattern,
    ROUND(pattern_confidence::numeric, 2) as confidence,
    priority,
    discovered_at
FROM ai_journey_insights
WHERE status = 'active'
    AND (expires_at IS NULL OR expires_at > NOW())
ORDER BY priority DESC, pattern_confidence DESC
LIMIT 10;

-- Query 9: Data Quality Checks
\echo ''
\echo '============================================================'
\echo 'QUERY 9: Data Quality Issues'
\echo '============================================================'
SELECT 'Actions Without Completion Time' as issue,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE status = 'completed' AND completed_at IS NULL
UNION ALL
SELECT 'Invalid Confidence Scores' as issue,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE confidence_score < 0 OR confidence_score > 1
UNION ALL
SELECT 'Actions Without Outcome' as issue,
    COUNT(*) as count
FROM ai_colleague_actions
WHERE status = 'completed' AND outcome IS NULL;

-- Query 10: Top Performing Actions
\echo ''
\echo '============================================================'
\echo 'QUERY 10: Top Performing Action Types'
\echo '============================================================'
SELECT
    agent_name,
    action_type,
    COUNT(*) as count,
    ROUND(AVG(confidence_score)::NUMERIC, 3) as avg_conf,
    ROUND(AVG(impact_score)::NUMERIC, 3) as avg_impact
FROM ai_colleague_actions
WHERE outcome = 'success'
    AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY agent_name, action_type
HAVING COUNT(*) >= 3
ORDER BY AVG(impact_score) DESC, AVG(confidence_score) DESC
LIMIT 15;

\echo ''
\echo '============================================================'
\echo 'DIAGNOSTIC QUERIES COMPLETE'
\echo '============================================================'
