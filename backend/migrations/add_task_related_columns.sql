-- Migration: Add related_type and related_contact_name columns to tasks table
-- These columns are required for duplicate merge task creation
-- Date: 2026-01-08

-- Add related_type column (for categorizing task type like 'duplicate_lead', 'duplicate_loan')
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'related_type') THEN
        ALTER TABLE tasks
            ADD COLUMN related_type VARCHAR(100);
    END IF;
END $$;

-- Add related_contact_name column (for storing related entity name)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM information_schema.columns
                   WHERE table_name = 'tasks'
                   AND column_name = 'related_contact_name') THEN
        ALTER TABLE tasks
            ADD COLUMN related_contact_name VARCHAR(255);
    END IF;
END $$;

-- Create index for related_type for faster filtering
CREATE INDEX IF NOT EXISTS ix_tasks_related_type ON tasks(related_type);

-- Verification query (uncomment to check columns exist)
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'tasks' AND column_name IN ('related_type', 'related_contact_name');
