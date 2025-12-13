-- =============================================================================
-- FIX WORKFLOW DAY SEMANTICS - MIGRATION
-- =============================================================================
-- This migration fixes a semantic design flaw where "First 24 Hours" was
-- configured with day_value=1, meaning it would fire AFTER 24 hours elapsed.
--
-- The fix changes "First 24 Hours" entries to day_value=0 so they fire
-- immediately upon workflow enrollment.
--
-- Also includes a one-time backdate of test instance 6 for immediate testing.
-- =============================================================================

-- =============================================================================
-- STEP 1: AUDIT BEFORE CHANGES (for logging purposes)
-- =============================================================================

-- This will be captured by the Python script for audit logging
-- SELECT 'BEFORE FIX' as audit_phase,
--        wc.name as workflow_name,
--        wdc.day_value,
--        wdc.day_label,
--        wdc.status_label
-- FROM workflow_day_configs wdc
-- JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
-- WHERE wdc.day_label ILIKE '%24 Hour%'
--    OR wdc.day_label ILIKE '%First%'
--    OR wdc.day_value = 1
-- ORDER BY wc.name, wdc.day_value;


-- =============================================================================
-- STEP 2: FIX SEMANTIC ISSUE - "First 24 Hours" should be day_value=0
-- =============================================================================

-- Fix: Change day_value from 1 to 0 for entries that semantically mean "immediate"
-- This ensures "First 24 Hours" fires on day 0 (immediately), not after 1 day
UPDATE workflow_day_configs
SET day_value = 0,
    updated_at = CURRENT_TIMESTAMP
WHERE day_label ILIKE '%First 24 Hour%'
   OR day_label ILIKE '%First%24%Hour%'
   OR day_label ILIKE 'Immediate%'
   OR day_label ILIKE '24 Hours'
   OR (day_value = 1 AND day_label ILIKE '%First%');


-- =============================================================================
-- STEP 3: BACKDATE TEST INSTANCE 6 FOR IMMEDIATE TESTING (One-time)
-- =============================================================================

-- Backdate instance 6 to 2 days ago to allow immediate task generation
-- This is safe for testing - the scheduler will generate Day 0, 1, 2 tasks
UPDATE workflow_instances
SET trigger_milestone_entered_at = NOW() - INTERVAL '2 days',
    last_task_generated_day = -1,  -- Reset to trigger full recalculation
    current_day = 0,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 6
  AND status = 'active';


-- =============================================================================
-- STEP 4: RESET current_day IF COLUMN EXISTS
-- =============================================================================

-- Add current_day column if it doesn't exist (for tracking purposes)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'workflow_instances'
                   AND column_name = 'current_day') THEN
        ALTER TABLE workflow_instances
            ADD COLUMN current_day INTEGER DEFAULT 0;
    END IF;
END $$;


-- =============================================================================
-- STEP 5: VERIFY CHANGES
-- =============================================================================

-- The Python script will run these verification queries after migration
