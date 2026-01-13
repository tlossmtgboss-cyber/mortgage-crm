-- =============================================================================
-- Migration: Add sla_milestone_type column to workflow_task_instances
-- Purpose: Allow tasks to be directly linked to SLA milestone types for
--          automatic SLA tracking when tasks are completed
-- Date: 2026-01-13
-- =============================================================================

-- Add sla_milestone_type column to workflow_task_instances table
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_task_instances'
                   AND column_name = 'sla_milestone_type') THEN
        ALTER TABLE workflow_task_instances
            ADD COLUMN sla_milestone_type VARCHAR(100);

        COMMENT ON COLUMN workflow_task_instances.sla_milestone_type IS
            'Links task to SLA milestone type (e.g., title_ordered, appraisal_received). When task is completed, the corresponding SLA milestone and loan date field are updated.';
    END IF;
END $$;

-- Add index for efficient lookup by milestone type
CREATE INDEX IF NOT EXISTS ix_workflow_task_instances_sla_milestone_type
    ON workflow_task_instances(sla_milestone_type)
    WHERE sla_milestone_type IS NOT NULL;

-- =============================================================================
-- Also ensure the tasks table has the column (for linked tasks)
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'sla_milestone_type') THEN
        ALTER TABLE tasks
            ADD COLUMN sla_milestone_type VARCHAR(100);

        COMMENT ON COLUMN tasks.sla_milestone_type IS
            'Links task to SLA milestone type for tracking compliance.';
    END IF;
END $$;

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration complete: Added sla_milestone_type column to workflow_task_instances and tasks tables';
END $$;
