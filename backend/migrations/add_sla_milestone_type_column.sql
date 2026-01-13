-- =============================================================================
-- SLA MILESTONE TYPE COLUMN MIGRATION
-- =============================================================================
-- Adds SLA milestone tracking columns to the tasks table for linking tasks
-- to specific SLA milestones and deadline tracking.
--
-- Run with: psql -d your_database -f backend/migrations/add_sla_milestone_type_column.sql
-- =============================================================================

-- Add sla_milestone_id column (references the SLA milestone definition)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_milestone_id') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_milestone_id INTEGER;
        RAISE NOTICE 'Added sla_milestone_id column to tasks table';
    ELSE
        RAISE NOTICE 'sla_milestone_id column already exists on tasks table';
    END IF;
END $$;

-- Add sla_milestone_type column (type identifier: 'disclosure', 'appraisal', 'closing', etc.)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_milestone_type') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_milestone_type VARCHAR(100);
        RAISE NOTICE 'Added sla_milestone_type column to tasks table';
    ELSE
        RAISE NOTICE 'sla_milestone_type column already exists on tasks table';
    END IF;
END $$;

-- Add sla_date_field column (which date field triggers the SLA: 'application_date', 'disclosure_sent_at', etc.)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_date_field') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_date_field VARCHAR(100);
        RAISE NOTICE 'Added sla_date_field column to tasks table';
    ELSE
        RAISE NOTICE 'sla_date_field column already exists on tasks table';
    END IF;
END $$;

-- Add milestone_date column (the actual date/deadline for this milestone)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'milestone_date') THEN
        ALTER TABLE tasks
            ADD COLUMN milestone_date TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added milestone_date column to tasks table';
    ELSE
        RAISE NOTICE 'milestone_date column already exists on tasks table';
    END IF;
END $$;

-- Add sla_days_allowed column (number of days allowed to complete this SLA)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_days_allowed') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_days_allowed INTEGER;
        RAISE NOTICE 'Added sla_days_allowed column to tasks table';
    ELSE
        RAISE NOTICE 'sla_days_allowed column already exists on tasks table';
    END IF;
END $$;

-- Add sla_status column (tracking SLA compliance: 'on_track', 'at_risk', 'overdue', 'completed')
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_status') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_status VARCHAR(50) DEFAULT 'on_track';
        RAISE NOTICE 'Added sla_status column to tasks table';
    ELSE
        RAISE NOTICE 'sla_status column already exists on tasks table';
    END IF;
END $$;

-- =============================================================================
-- PERFORMANCE INDEXES
-- =============================================================================

-- Index for querying tasks by SLA milestone type
CREATE INDEX IF NOT EXISTS ix_tasks_sla_milestone_type
    ON tasks(sla_milestone_type)
    WHERE sla_milestone_type IS NOT NULL;

-- Index for querying tasks by SLA status
CREATE INDEX IF NOT EXISTS ix_tasks_sla_status
    ON tasks(sla_status)
    WHERE sla_status IS NOT NULL;

-- Index for querying tasks by milestone date (for deadline tracking)
CREATE INDEX IF NOT EXISTS ix_tasks_milestone_date
    ON tasks(milestone_date)
    WHERE milestone_date IS NOT NULL;

-- Composite index for SLA reporting queries
CREATE INDEX IF NOT EXISTS ix_tasks_sla_composite
    ON tasks(sla_milestone_type, sla_status, milestone_date)
    WHERE sla_milestone_type IS NOT NULL;

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
RAISE NOTICE 'SLA milestone type column migration completed successfully';
