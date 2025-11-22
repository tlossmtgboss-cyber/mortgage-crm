-- AI Task Automation & Learning System
-- Migration to add AI task automation tables and modifications

-- ============================================
-- TABLE 1: AI Task Type Authorizations
-- ============================================
-- Per-user, per-workflow authorization for AI automation

CREATE TABLE IF NOT EXISTS ai_task_type_authorizations (
    authorization_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    workflow_id UUID NOT NULL,
    company_id UUID NOT NULL,

    task_type_name VARCHAR(255) NOT NULL,
    workflow_category VARCHAR(100),

    authorization_status VARCHAR(50) NOT NULL DEFAULT 'not_authorized',
    -- Status values: 'not_authorized', 'training', 'active', 'paused', 'revoked'

    training_progress_count INT DEFAULT 0,
    confidence_threshold DECIMAL(5,2) DEFAULT 90.0,

    date_authorized TIMESTAMP,
    date_training_completed TIMESTAMP,
    date_revoked TIMESTAMP,
    revoked_by_user_id UUID,
    retain_training_data BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_user_workflow UNIQUE(user_id, workflow_id),
    CONSTRAINT valid_auth_status CHECK (authorization_status IN ('not_authorized', 'training', 'active', 'paused', 'revoked'))
);

CREATE INDEX IF NOT EXISTS idx_auth_user_workflow ON ai_task_type_authorizations(user_id, workflow_id);
CREATE INDEX IF NOT EXISTS idx_auth_company ON ai_task_type_authorizations(company_id);
CREATE INDEX IF NOT EXISTS idx_auth_status ON ai_task_type_authorizations(authorization_status);

-- ============================================
-- TABLE 2: AI Training History
-- ============================================
-- Tracks all training attempts and user feedback

CREATE TABLE IF NOT EXISTS ai_training_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    authorization_id UUID NOT NULL REFERENCES ai_task_type_authorizations(authorization_id) ON DELETE CASCADE,
    task_instance_id UUID NOT NULL,
    company_id UUID NOT NULL,

    ai_action_taken JSONB,
    ai_confidence_score DECIMAL(5,2),
    execution_time_ms INT,

    user_response VARCHAR(50),
    -- Values: 'approved', 'rejected', 'error', 'pending'

    feedback_text TEXT,
    feedback_structured JSONB,

    reviewed_by_user_id UUID,
    reviewed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_training_response CHECK (user_response IN ('approved', 'rejected', 'error', 'pending'))
);

CREATE INDEX IF NOT EXISTS idx_training_authorization ON ai_training_history(authorization_id);
CREATE INDEX IF NOT EXISTS idx_training_task ON ai_training_history(task_instance_id);
CREATE INDEX IF NOT EXISTS idx_training_company ON ai_training_history(company_id);
CREATE INDEX IF NOT EXISTS idx_training_reviewed ON ai_training_history(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_training_user_response ON ai_training_history(user_response);

-- ============================================
-- TABLE 3: AI Audit Log
-- ============================================
-- Complete audit trail of all AI actions for compliance

CREATE TABLE IF NOT EXISTS ai_audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    company_id UUID NOT NULL,
    task_instance_id UUID,
    authorization_id UUID,

    action_type VARCHAR(50) NOT NULL,
    -- Values: 'auto_complete', 'training', 'error', 'manual_override', 'authorization_change', 'rollback'

    action_details JSONB,
    result_status VARCHAR(50),
    -- Values: 'success', 'failed', 'pending'

    error_message TEXT,
    confidence_score DECIMAL(5,2),
    execution_time_ms INT,

    api_calls_made JSONB,
    tokens_used INT,
    estimated_cost DECIMAL(10,4),

    timestamp TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_audit_action_type CHECK (action_type IN ('auto_complete', 'training', 'error', 'manual_override', 'authorization_change', 'rollback')),
    CONSTRAINT valid_audit_result CHECK (result_status IS NULL OR result_status IN ('success', 'failed', 'pending'))
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON ai_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_company ON ai_audit_log(company_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON ai_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON ai_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_task ON ai_audit_log(task_instance_id);
CREATE INDEX IF NOT EXISTS idx_audit_result ON ai_audit_log(result_status);

-- ============================================
-- TABLE 4: AI Cost Tracking
-- ============================================
-- Per-user cost tracking for billing and monitoring

CREATE TABLE IF NOT EXISTS ai_cost_tracking (
    cost_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    company_id UUID NOT NULL,
    authorization_id UUID,
    task_instance_id UUID,

    cost_type VARCHAR(50) NOT NULL,
    -- Values: 'api_call', 'token_usage', 'storage', 'infrastructure'

    amount DECIMAL(10,4) NOT NULL,
    tokens_used INT,
    api_provider VARCHAR(50),

    period_month INT,
    period_year INT,

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_cost_type CHECK (cost_type IN ('api_call', 'token_usage', 'storage', 'infrastructure'))
);

CREATE INDEX IF NOT EXISTS idx_cost_user_period ON ai_cost_tracking(user_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS idx_cost_company_period ON ai_cost_tracking(company_id, period_year, period_month);
CREATE INDEX IF NOT EXISTS idx_cost_authorization ON ai_cost_tracking(authorization_id);

-- ============================================
-- TABLE 5: AI Rollback States
-- ============================================
-- Snapshots for reverting AI to previous trained state

CREATE TABLE IF NOT EXISTS ai_rollback_states (
    state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    authorization_id UUID NOT NULL REFERENCES ai_task_type_authorizations(authorization_id) ON DELETE CASCADE,

    state_snapshot JSONB NOT NULL,
    performance_metrics JSONB,
    tasks_completed_count INT DEFAULT 0,

    snapshot_reason VARCHAR(50) NOT NULL,
    -- Values: 'training_complete', 'manual_save', 'pre_rollback', 'scheduled'

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_snapshot_reason CHECK (snapshot_reason IN ('training_complete', 'manual_save', 'pre_rollback', 'scheduled'))
);

CREATE INDEX IF NOT EXISTS idx_rollback_authorization ON ai_rollback_states(authorization_id);
CREATE INDEX IF NOT EXISTS idx_rollback_created ON ai_rollback_states(created_at);

-- ============================================
-- MODIFY EXISTING TASKS TABLE
-- ============================================
-- Add AI-related columns to existing tasks table

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_type_id UUID;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_confidence_score DECIMAL(5,2);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completion_method VARCHAR(50);
-- Values: 'manual', 'ai_auto', 'ai_pending_review', 'ai_error'
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_completed_at TIMESTAMP;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_approved_at TIMESTAMP;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error_details JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_recommendation JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS related_task_id UUID;

CREATE INDEX IF NOT EXISTS idx_tasks_completion_method ON tasks(completion_method);
CREATE INDEX IF NOT EXISTS idx_tasks_task_type ON tasks(task_type_id);
CREATE INDEX IF NOT EXISTS idx_tasks_ai_completed ON tasks(ai_completed_at);

-- ============================================
-- ROW-LEVEL SECURITY (Multi-Tenant Isolation)
-- ============================================
-- Enable RLS on all AI tables for data isolation

ALTER TABLE ai_task_type_authorizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_training_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_cost_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_rollback_states ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
-- Note: These policies use app.current_company_id which must be set in application context

-- Policy for ai_task_type_authorizations
DROP POLICY IF EXISTS ai_authorization_isolation ON ai_task_type_authorizations;
CREATE POLICY ai_authorization_isolation ON ai_task_type_authorizations
    FOR ALL
    USING (company_id = COALESCE(current_setting('app.current_company_id', true)::uuid, company_id));

-- Policy for ai_training_history
DROP POLICY IF EXISTS ai_training_isolation ON ai_training_history;
CREATE POLICY ai_training_isolation ON ai_training_history
    FOR ALL
    USING (company_id = COALESCE(current_setting('app.current_company_id', true)::uuid, company_id));

-- Policy for ai_audit_log
DROP POLICY IF EXISTS ai_audit_isolation ON ai_audit_log;
CREATE POLICY ai_audit_isolation ON ai_audit_log
    FOR ALL
    USING (company_id = COALESCE(current_setting('app.current_company_id', true)::uuid, company_id));

-- Policy for ai_cost_tracking
DROP POLICY IF EXISTS ai_cost_isolation ON ai_cost_tracking;
CREATE POLICY ai_cost_isolation ON ai_cost_tracking
    FOR ALL
    USING (company_id = COALESCE(current_setting('app.current_company_id', true)::uuid, company_id));

-- Policy for ai_rollback_states (uses authorization's company_id)
DROP POLICY IF EXISTS ai_rollback_isolation ON ai_rollback_states;
CREATE POLICY ai_rollback_isolation ON ai_rollback_states
    FOR ALL
    USING (
        authorization_id IN (
            SELECT authorization_id
            FROM ai_task_type_authorizations
            WHERE company_id = COALESCE(current_setting('app.current_company_id', true)::uuid, company_id)
        )
    );

-- ============================================
-- HELPER VIEWS (Optional)
-- ============================================

-- View: Active AI authorizations with metrics
CREATE OR REPLACE VIEW ai_authorization_metrics AS
SELECT
    a.authorization_id,
    a.user_id,
    a.workflow_id,
    a.company_id,
    a.task_type_name,
    a.authorization_status,
    a.training_progress_count,
    a.confidence_threshold,
    a.date_authorized,
    a.date_training_completed,
    COUNT(DISTINCT th.task_instance_id) FILTER (WHERE th.user_response = 'approved') as approved_count,
    COUNT(DISTINCT th.task_instance_id) FILTER (WHERE th.user_response = 'rejected') as rejected_count,
    AVG(th.ai_confidence_score) as avg_confidence,
    MAX(al.timestamp) as last_activity
FROM ai_task_type_authorizations a
LEFT JOIN ai_training_history th ON a.authorization_id = th.authorization_id
LEFT JOIN ai_audit_log al ON a.authorization_id = al.authorization_id
GROUP BY a.authorization_id;

-- View: Monthly AI costs summary
CREATE OR REPLACE VIEW ai_monthly_costs AS
SELECT
    user_id,
    company_id,
    period_year,
    period_month,
    COUNT(DISTINCT task_instance_id) as total_tasks,
    SUM(amount) as total_cost,
    SUM(tokens_used) as total_tokens,
    AVG(amount) as avg_cost_per_task
FROM ai_cost_tracking
GROUP BY user_id, company_id, period_year, period_month;

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE ai_task_type_authorizations IS 'Stores per-user, per-workflow AI automation authorizations';
COMMENT ON TABLE ai_training_history IS 'Tracks all AI training attempts and user feedback for learning';
COMMENT ON TABLE ai_audit_log IS 'Complete audit trail of all AI actions for compliance and debugging';
COMMENT ON TABLE ai_cost_tracking IS 'Tracks AI usage costs per user for billing and monitoring';
COMMENT ON TABLE ai_rollback_states IS 'Snapshots of AI state for rollback functionality';

COMMENT ON COLUMN ai_task_type_authorizations.authorization_status IS 'Current status: not_authorized, training, active, paused, revoked';
COMMENT ON COLUMN ai_task_type_authorizations.training_progress_count IS 'Number of approved training tasks (0-5)';
COMMENT ON COLUMN ai_task_type_authorizations.confidence_threshold IS 'Minimum confidence for auto-completion (default 90%)';

COMMENT ON COLUMN tasks.completion_method IS 'How task was completed: manual, ai_auto, ai_pending_review, ai_error';
COMMENT ON COLUMN tasks.ai_recommendation IS 'AI-generated recommendation for task completion';
COMMENT ON COLUMN tasks.related_task_id IS 'Reference to original task (for error notification tasks)';

-- ============================================
-- MIGRATION COMPLETE
-- ============================================
-- To apply this migration:
-- psql $DATABASE_URL < backend/migrations/add_ai_task_automation.sql
--
-- Or via Railway:
-- railway run psql $DATABASE_URL < backend/migrations/add_ai_task_automation.sql
