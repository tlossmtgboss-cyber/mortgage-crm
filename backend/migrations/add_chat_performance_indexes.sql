-- Chat State Machine Performance Indexes
-- Run these in production to optimize high-traffic scenarios
--
-- Usage: psql -d perennia -f add_chat_performance_indexes.sql
-- Or run via Alembic migration

-- ============================================================================
-- SESSION LOOKUP OPTIMIZATION
-- ============================================================================

-- Active session lookup by visitor (most common query pattern)
-- Partial index: only active sessions from last 24 hours
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_visitor_active
ON chat_sessions(visitor_id, created_at DESC)
WHERE created_at > NOW() - INTERVAL '24 hours' AND is_active = true;

-- User ID lookup for authenticated users
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_user_active
ON chat_sessions(user_id, created_at DESC)
WHERE user_id IS NOT NULL AND is_active = true;

-- Microsite-based session lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_microsite_active
ON chat_sessions(microsite_id, created_at DESC)
WHERE microsite_id IS NOT NULL AND is_active = true;


-- ============================================================================
-- MESSAGE RETRIEVAL OPTIMIZATION
-- ============================================================================

-- Message retrieval by session (for loading conversation history)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_messages_session_created
ON chat_messages(session_id, created_at DESC);

-- Message lookup by turn number for specific message retrieval
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_messages_session_turn
ON chat_messages(session_id, turn_number);


-- ============================================================================
-- ANALYTICS OPTIMIZATION
-- ============================================================================

-- Analytics queries: phase progression, CTA effectiveness
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_analytics
ON chat_sessions(created_at, current_phase, cta_offered, cta_accepted)
WHERE created_at > NOW() - INTERVAL '90 days';

-- Conversion funnel analysis
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_conversion
ON chat_sessions(created_at, converted_to_lead, intent_score)
WHERE created_at > NOW() - INTERVAL '90 days';

-- Daily/weekly reporting aggregations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_daily_reporting
ON chat_sessions(DATE(created_at), microsite_id, current_phase);


-- ============================================================================
-- CALL REQUEST TRACKING
-- ============================================================================

-- Pending call queue (for real-time call management)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_call_requests_status_created
ON call_requests(status, created_at DESC)
WHERE status IN ('pending', 'connecting', 'in_progress');

-- Scheduled callbacks lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_call_requests_scheduled
ON call_requests(scheduled_at, status)
WHERE scheduled_at IS NOT NULL AND status = 'pending';

-- LO call history
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_call_requests_lo_history
ON call_requests(loan_officer_id, created_at DESC)
WHERE loan_officer_id IS NOT NULL;


-- ============================================================================
-- INTENT SIGNAL SEARCH (GIN for JSONB)
-- ============================================================================

-- GIN index for searching within intent_signals JSONB array
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_intent_signals_gin
ON chat_sessions USING gin(intent_signals);

-- Detected intents on messages
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_messages_detected_intents_gin
ON chat_messages USING gin(detected_intents)
WHERE detected_intents IS NOT NULL;


-- ============================================================================
-- OPERATIONAL MONITORING
-- ============================================================================

-- Sessions needing follow-up (high intent, stalled)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_needs_followup
ON chat_sessions(last_message_at, current_phase, intent_score)
WHERE current_phase IN (3, 4)
  AND cta_offered IS NULL
  AND is_active = true
  AND last_message_at > NOW() - INTERVAL '1 hour';

-- Abandoned high-intent sessions (for recovery workflows)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_chat_sessions_abandoned_high_intent
ON chat_sessions(last_message_at, intent_score)
WHERE intent_score >= 60
  AND current_phase >= 3
  AND cta_accepted = false
  AND is_active = true
  AND last_message_at < NOW() - INTERVAL '2 hours';

-- Failed calls for monitoring
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_call_requests_failed_recent
ON call_requests(created_at DESC)
WHERE status = 'failed'
  AND created_at > NOW() - INTERVAL '24 hours';


-- ============================================================================
-- STATISTICS UPDATE (for query planner)
-- ============================================================================

-- Analyze tables after creating indexes
ANALYZE chat_sessions;
ANALYZE chat_messages;
ANALYZE call_requests;


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Verify indexes were created
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_indexes
WHERE tablename IN ('chat_sessions', 'chat_messages', 'call_requests')
  AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;
