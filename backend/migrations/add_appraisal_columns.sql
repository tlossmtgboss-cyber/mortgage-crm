-- Add appraisal and additional loan columns
-- Run this migration to add missing columns to loans table

ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_ordered_date TIMESTAMP;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_scheduled_date TIMESTAMP;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_completed_date TIMESTAMP;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS appraisal_value DECIMAL(15, 2);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS lock_expiration_date TIMESTAMP;
ALTER TABLE loans ADD COLUMN IF NOT EXISTS property_city VARCHAR(100);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS property_state VARCHAR(50);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS property_zip VARCHAR(20);
ALTER TABLE loans ADD COLUMN IF NOT EXISTS lender VARCHAR(255);
