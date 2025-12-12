-- =============================================================================
-- SLA WORKFLOW TASK GENERATION SYSTEM - PHASE 1 DATABASE MIGRATION
-- =============================================================================
-- This migration creates the database schema for the SLA-driven workflow task
-- generation system. It includes:
-- - New enum types for workflow status tracking
-- - Core tables for workflow instances and task tracking
-- - AI confidence tracking for autonomous task execution
-- - Role assignment tables for lead/loan workflows
-- - Column additions to existing tables
-- - Performance indexes
-- - Row-Level Security (RLS) policies for multi-tenant isolation
-- =============================================================================

-- =============================================================================
-- SECTION 1: ENUM TYPES
-- =============================================================================

-- Workflow instance lifecycle status
DO $$ BEGIN
    CREATE TYPE workflow_instance_status AS ENUM (
        'active',           -- Currently executing, generating tasks
        'paused',           -- Temporarily stopped (e.g., user request, stage change)
        'completed',        -- Reached terminal status (funded, closed)
        'cancelled',        -- Manually cancelled or superseded
        'error'             -- System error, requires admin attention
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Individual workflow task status
DO $$ BEGIN
    CREATE TYPE workflow_task_status AS ENUM (
        'scheduled',        -- Task created, waiting for due date
        'pending',          -- Due date reached, ready for execution
        'in_progress',      -- Task being worked on
        'completed',        -- Successfully completed
        'skipped',          -- Skipped (e.g., contact made via other method)
        'failed',           -- Execution failed
        'cancelled'         -- Cancelled (workflow cancelled or sibling completed)
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Task type/communication method
DO $$ BEGIN
    CREATE TYPE workflow_task_type AS ENUM (
        'phone',            -- Phone call task
        'phone_am',         -- Morning phone call (Lead Purchase)
        'phone_pm',         -- Afternoon phone call (Lead Purchase)
        'text',             -- SMS/Text message
        'text_am',          -- Morning text (Lead Purchase)
        'text_pm',          -- Afternoon text (Lead Purchase)
        'email',            -- Email outreach
        'referral_partner', -- Referral partner notification
        'dialer',           -- Power dialer queue task
        'manual'            -- Manual follow-up task
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Task routing destination
DO $$ BEGIN
    CREATE TYPE workflow_route AS ENUM (
        'task_list',        -- Standard task list assignment
        'dialer_queue',     -- Power dialer queue
        'ai_autonomous',    -- AI handles autonomously
        'email_automation', -- Automated email system
        'sms_automation'    -- Automated SMS system
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Lead source category for workflow assignment
DO $$ BEGIN
    CREATE TYPE lead_source_category AS ENUM (
        'organic',          -- Website, referral, walk-in
        'purchased',        -- Purchased lead (triggers Lead Purchase workflow)
        'partner',          -- Partner/agent referral
        'marketing',        -- Paid advertising leads
        'other'             -- Uncategorized
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================================
-- SECTION 2: WORKFLOW INSTANCES TABLE
-- =============================================================================
-- Tracks the lifecycle of a workflow assigned to a lead/loan

CREATE TABLE IF NOT EXISTS workflow_instances (
    id SERIAL PRIMARY KEY,

    -- Multi-tenant isolation
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Workflow template reference
    workflow_configuration_id INTEGER NOT NULL REFERENCES workflow_configurations(id) ON DELETE RESTRICT,

    -- Target entity (exactly one must be set)
    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,

    -- Current state
    status workflow_instance_status NOT NULL DEFAULT 'active',

    -- Milestone tracking (what triggered this workflow)
    trigger_milestone_status VARCHAR(100),      -- Status that triggered workflow start
    trigger_milestone_entered_at TIMESTAMP WITH TIME ZONE,

    -- Lifecycle timestamps
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paused_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,

    -- Cancellation tracking
    cancelled_by_id INTEGER REFERENCES users(id),
    cancellation_reason TEXT,
    superseded_by_id INTEGER REFERENCES workflow_instances(id),  -- If replaced by another workflow

    -- Task generation tracking
    last_task_generated_day INTEGER DEFAULT 0,  -- Tracks which day_config we've generated up to
    next_task_due_at TIMESTAMP WITH TIME ZONE,  -- Denormalized for efficient scheduling queries

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_workflow_instance_entity CHECK (
        (lead_id IS NOT NULL AND loan_id IS NULL) OR
        (lead_id IS NULL AND loan_id IS NOT NULL)
    ),
    CONSTRAINT chk_workflow_instance_cancelled CHECK (
        (status != 'cancelled') OR (cancelled_at IS NOT NULL AND cancelled_by_id IS NOT NULL)
    )
);

-- Unique constraint: Only one active workflow per entity per workflow type
CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_instances_active_lead
    ON workflow_instances(lead_id, workflow_configuration_id)
    WHERE lead_id IS NOT NULL AND status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_instances_active_loan
    ON workflow_instances(loan_id, workflow_configuration_id)
    WHERE loan_id IS NOT NULL AND status = 'active';


-- =============================================================================
-- SECTION 3: EXTENDED WORKFLOW_TASK_INSTANCES TABLE
-- =============================================================================
-- Note: This extends/replaces the existing workflow_task_instances from
-- workflow_config_models.py with additional fields for the SLA system

-- Add new columns to existing workflow_task_instances if they exist
DO $$
BEGIN
    -- Check if table exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'workflow_task_instances') THEN

        -- Add workflow_instance_id if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'workflow_instance_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN workflow_instance_id INTEGER REFERENCES workflow_instances(id) ON DELETE CASCADE;
        END IF;

        -- Add organization_id if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'organization_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
        END IF;

        -- Add task_type if not exists (enum version)
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'task_type') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN task_type workflow_task_type;
        END IF;

        -- Add route if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'route') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN route workflow_route NOT NULL DEFAULT 'task_list';
        END IF;

        -- Add task_group_key if not exists (for sibling cancellation)
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'task_group_key') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN task_group_key VARCHAR(100);
        END IF;

        -- Add linked_task_id if not exists (reference to tasks table)
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'linked_task_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN linked_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL;
        END IF;

        -- Add dialer_session_task_id if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'dialer_session_task_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN dialer_session_task_id INTEGER;
        END IF;

        -- Add assigned_role_id if not exists (dynamic role reference)
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'assigned_role_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN assigned_role_id INTEGER REFERENCES roles(id);
        END IF;

        -- Add ai_eligible if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'ai_eligible') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN ai_eligible BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;

        -- Add ai_confidence if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'ai_confidence') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN ai_confidence DECIMAL(3,3);
        END IF;

        -- Add ai_executed_at if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'ai_executed_at') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN ai_executed_at TIMESTAMP WITH TIME ZONE;
        END IF;

        -- Add completion_source if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'completion_source') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN completion_source VARCHAR(50);  -- 'user', 'ai', 'dialer', 'automation'
        END IF;

        -- Add completed_by_id if not exists
        IF NOT EXISTS (SELECT FROM information_schema.columns
                       WHERE table_name = 'workflow_task_instances'
                       AND column_name = 'completed_by_id') THEN
            ALTER TABLE workflow_task_instances
                ADD COLUMN completed_by_id INTEGER REFERENCES users(id);
        END IF;

        -- Update status column to use enum if it's currently varchar
        -- Note: This requires data migration, handled separately

    END IF;
END $$;


-- =============================================================================
-- SECTION 4: AI CONFIDENCE TRACKING TABLE
-- =============================================================================
-- Tracks AI confidence levels for task execution decisions

CREATE TABLE IF NOT EXISTS workflow_ai_confidence (
    id SERIAL PRIMARY KEY,

    -- Reference to task
    workflow_task_instance_id INTEGER NOT NULL REFERENCES workflow_task_instances(id) ON DELETE CASCADE,

    -- AI evaluation details
    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confidence_score DECIMAL(4,3) NOT NULL,  -- 0.000 to 1.000

    -- Factors that influenced the score
    factors JSONB NOT NULL DEFAULT '{}',
    -- Example: {
    --   "contact_history_quality": 0.8,
    --   "lead_engagement_score": 0.7,
    --   "time_since_last_contact": 0.9,
    --   "template_match_score": 0.85
    -- }

    -- Decision made
    decision VARCHAR(50) NOT NULL,  -- 'auto_execute', 'queue_for_review', 'escalate'
    threshold_used DECIMAL(4,3) NOT NULL,  -- The threshold applied (e.g., 0.950)

    -- Execution details (if auto-executed)
    executed BOOLEAN NOT NULL DEFAULT FALSE,
    execution_result JSONB,  -- Result/error details

    -- Audit trail
    model_version VARCHAR(50),  -- AI model version used

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- SECTION 5: ROLE ASSIGNMENT TABLES
-- =============================================================================
-- Per-lead and per-loan role assignments for workflow task routing

-- Lead-level role assignments
CREATE TABLE IF NOT EXISTS lead_workflow_role_assignments (
    id SERIAL PRIMARY KEY,

    -- Multi-tenant
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Target lead
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,

    -- Role assignment
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Assignment metadata
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_id INTEGER REFERENCES users(id),

    -- Active/inactive for soft deletes
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Unique: One user per role per lead
    CONSTRAINT uq_lead_role_assignment UNIQUE (lead_id, role_id, is_active)
        DEFERRABLE INITIALLY DEFERRED
);

-- Loan-level role assignments
CREATE TABLE IF NOT EXISTS loan_workflow_role_assignments (
    id SERIAL PRIMARY KEY,

    -- Multi-tenant
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Target loan
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,

    -- Role assignment
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Assignment metadata
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_id INTEGER REFERENCES users(id),

    -- Active/inactive for soft deletes
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Unique: One user per role per loan
    CONSTRAINT uq_loan_role_assignment UNIQUE (loan_id, role_id, is_active)
        DEFERRABLE INITIALLY DEFERRED
);


-- =============================================================================
-- SECTION 6: COLUMN ADDITIONS TO EXISTING TABLES
-- =============================================================================

-- Add workflow_task_instance_id to tasks table
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'workflow_task_instance_id') THEN
        ALTER TABLE tasks
            ADD COLUMN workflow_task_instance_id INTEGER REFERENCES workflow_task_instances(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add task_group_key to tasks table (for sibling task grouping)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'task_group_key') THEN
        ALTER TABLE tasks
            ADD COLUMN task_group_key VARCHAR(100);
    END IF;
END $$;

-- Add SLA milestone tracking columns to tasks table
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_milestone_id') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_milestone_id INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_milestone_type') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_milestone_type VARCHAR(100);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_date_field') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_date_field VARCHAR(100);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'milestone_date') THEN
        ALTER TABLE tasks
            ADD COLUMN milestone_date TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Add abbreviation to roles table
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'roles'
                   AND column_name = 'abbreviation') THEN
        ALTER TABLE roles
            ADD COLUMN abbreviation VARCHAR(10);
    END IF;
END $$;

-- Add source_category and source_vendor to leads table
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'leads'
                   AND column_name = 'source_category') THEN
        ALTER TABLE leads
            ADD COLUMN source_category lead_source_category DEFAULT 'organic';
    END IF;

    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'leads'
                   AND column_name = 'source_vendor') THEN
        ALTER TABLE leads
            ADD COLUMN source_vendor VARCHAR(100);
    END IF;
END $$;

-- Add organization_id and user_id to workflow_configurations for customization scope
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_configurations'
                   AND column_name = 'organization_id') THEN
        ALTER TABLE workflow_configurations
            ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_configurations'
                   AND column_name = 'user_id') THEN
        ALTER TABLE workflow_configurations
            ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_configurations'
                   AND column_name = 'is_system_template') THEN
        ALTER TABLE workflow_configurations
            ADD COLUMN is_system_template BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_configurations'
                   AND column_name = 'parent_template_id') THEN
        ALTER TABLE workflow_configurations
            ADD COLUMN parent_template_id INTEGER REFERENCES workflow_configurations(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add current_workflow_instance_id to leads for quick lookup
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'leads'
                   AND column_name = 'current_workflow_instance_id') THEN
        ALTER TABLE leads
            ADD COLUMN current_workflow_instance_id INTEGER REFERENCES workflow_instances(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add current_workflow_instance_id to loans for quick lookup
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'loans'
                   AND column_name = 'current_workflow_instance_id') THEN
        ALTER TABLE loans
            ADD COLUMN current_workflow_instance_id INTEGER REFERENCES workflow_instances(id) ON DELETE SET NULL;
    END IF;
END $$;


-- =============================================================================
-- SECTION 7: PERFORMANCE INDEXES
-- =============================================================================

-- Workflow instances indexes
CREATE INDEX IF NOT EXISTS ix_workflow_instances_org_status
    ON workflow_instances(organization_id, status);

CREATE INDEX IF NOT EXISTS ix_workflow_instances_next_task_due
    ON workflow_instances(next_task_due_at)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_workflow_instances_lead_id
    ON workflow_instances(lead_id)
    WHERE lead_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_workflow_instances_loan_id
    ON workflow_instances(loan_id)
    WHERE loan_id IS NOT NULL;

-- Workflow task instances indexes
CREATE INDEX IF NOT EXISTS ix_workflow_task_instances_instance_status
    ON workflow_task_instances(workflow_instance_id, status);

CREATE INDEX IF NOT EXISTS ix_workflow_task_instances_scheduled
    ON workflow_task_instances(scheduled_date)
    WHERE status = 'scheduled';

CREATE INDEX IF NOT EXISTS ix_workflow_task_instances_group_key
    ON workflow_task_instances(task_group_key)
    WHERE task_group_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_workflow_task_instances_linked_task
    ON workflow_task_instances(linked_task_id)
    WHERE linked_task_id IS NOT NULL;

-- AI confidence indexes
CREATE INDEX IF NOT EXISTS ix_workflow_ai_confidence_task
    ON workflow_ai_confidence(workflow_task_instance_id);

CREATE INDEX IF NOT EXISTS ix_workflow_ai_confidence_decision
    ON workflow_ai_confidence(decision, created_at);

-- Role assignment indexes
CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_lead
    ON lead_workflow_role_assignments(lead_id, is_active);

CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_user
    ON lead_workflow_role_assignments(assigned_user_id, is_active);

CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_loan
    ON loan_workflow_role_assignments(loan_id, is_active);

CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_user
    ON loan_workflow_role_assignments(assigned_user_id, is_active);

-- Tasks table workflow index
CREATE INDEX IF NOT EXISTS ix_tasks_workflow_task_instance
    ON tasks(workflow_task_instance_id)
    WHERE workflow_task_instance_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_tasks_group_key
    ON tasks(task_group_key)
    WHERE task_group_key IS NOT NULL;

-- Leads source category index
CREATE INDEX IF NOT EXISTS ix_leads_source_category
    ON leads(source_category);


-- =============================================================================
-- SECTION 8: ROW-LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

-- Enable RLS on workflow tables
ALTER TABLE workflow_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_workflow_role_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE loan_workflow_role_assignments ENABLE ROW LEVEL SECURITY;

-- Note: workflow_task_instances and workflow_ai_confidence are accessed via
-- workflow_instances, so their RLS is inherited through the foreign key relationship

-- RLS Policy: Users can only see workflow instances for their organization
DO $$
BEGIN
    DROP POLICY IF EXISTS workflow_instances_org_isolation ON workflow_instances;
    CREATE POLICY workflow_instances_org_isolation ON workflow_instances
        FOR ALL
        USING (
            organization_id IN (
                SELECT organization_id FROM users WHERE id = current_setting('app.current_user_id')::INTEGER
            )
        );
EXCEPTION
    WHEN undefined_object THEN NULL;  -- Policy might not exist
END $$;

-- RLS Policy: Lead role assignments
DO $$
BEGIN
    DROP POLICY IF EXISTS lead_role_assignments_org_isolation ON lead_workflow_role_assignments;
    CREATE POLICY lead_role_assignments_org_isolation ON lead_workflow_role_assignments
        FOR ALL
        USING (
            organization_id IN (
                SELECT organization_id FROM users WHERE id = current_setting('app.current_user_id')::INTEGER
            )
        );
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

-- RLS Policy: Loan role assignments
DO $$
BEGIN
    DROP POLICY IF EXISTS loan_role_assignments_org_isolation ON loan_workflow_role_assignments;
    CREATE POLICY loan_role_assignments_org_isolation ON loan_workflow_role_assignments
        FOR ALL
        USING (
            organization_id IN (
                SELECT organization_id FROM users WHERE id = current_setting('app.current_user_id')::INTEGER
            )
        );
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;


-- =============================================================================
-- SECTION 9: UPDATE TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_workflow_instances_updated_at ON workflow_instances;
    CREATE TRIGGER update_workflow_instances_updated_at
        BEFORE UPDATE ON workflow_instances
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;

DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_lead_role_assignments_updated_at ON lead_workflow_role_assignments;
    CREATE TRIGGER update_lead_role_assignments_updated_at
        BEFORE UPDATE ON lead_workflow_role_assignments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;

DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_loan_role_assignments_updated_at ON loan_workflow_role_assignments;
    CREATE TRIGGER update_loan_role_assignments_updated_at
        BEFORE UPDATE ON loan_workflow_role_assignments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;


-- =============================================================================
-- SECTION 10: SEED DATA - UPDATE ROLE ABBREVIATIONS
-- =============================================================================

-- Update existing roles with abbreviations
UPDATE roles SET abbreviation = 'LO' WHERE name = 'Loan Officer' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'JR' WHERE name = 'Junior Loan Officer' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'PA' WHERE name = 'Production Assistant' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'CON' WHERE name = 'Concierge' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'PROC' WHERE name = 'Processor' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'UW' WHERE name = 'Underwriter' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'CLS' WHERE name = 'Closer' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'MGR' WHERE name = 'Manager' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'ADM' WHERE name = 'Administrator' AND abbreviation IS NULL;
UPDATE roles SET abbreviation = 'AI' WHERE name = 'AI Assistant' AND abbreviation IS NULL;


-- =============================================================================
-- SECTION 11: MARK EXISTING WORKFLOW CONFIGURATIONS AS SYSTEM TEMPLATES
-- =============================================================================

-- Mark existing workflow configurations as system templates (they have no org_id)
UPDATE workflow_configurations
SET is_system_template = TRUE
WHERE organization_id IS NULL AND user_id IS NULL;


-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
