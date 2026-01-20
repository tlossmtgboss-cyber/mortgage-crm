-- Add organization_id column to loans table for multi-tenant support
-- This links loans to the correct organization for filtering

-- Add column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'loans' AND column_name = 'organization_id'
    ) THEN
        ALTER TABLE loans ADD COLUMN organization_id INTEGER;
    END IF;
END $$;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS ix_loans_organization_id ON loans(organization_id);

-- Set default organization_id to 1 for existing loans without one
UPDATE loans SET organization_id = 1 WHERE organization_id IS NULL;
