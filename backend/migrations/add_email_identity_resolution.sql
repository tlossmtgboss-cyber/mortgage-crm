-- ================================================================
-- Email Identity Resolution System - Database Migration
-- Perennia AI CRM
-- Version: 1.0
-- Date: 2024-01-15
-- ================================================================

BEGIN;

-- ================================================================
-- 1. Update email_reconciliation_queue table
-- ================================================================

-- Add match metadata columns if they don't exist
ALTER TABLE email_reconciliation_queue
ADD COLUMN IF NOT EXISTS match_evidence TEXT,
ADD COLUMN IF NOT EXISTS match_client_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS match_loan_number VARCHAR(100);

-- Ensure is_priority column exists with proper default
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='email_reconciliation_queue'
        AND column_name='is_priority'
    ) THEN
        ALTER TABLE email_reconciliation_queue
        ADD COLUMN is_priority BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Update existing NULL values to FALSE
UPDATE email_reconciliation_queue
SET is_priority = FALSE
WHERE is_priority IS NULL;

-- Add NOT NULL constraint after backfilling
ALTER TABLE email_reconciliation_queue
ALTER COLUMN is_priority SET DEFAULT FALSE,
ALTER COLUMN is_priority SET NOT NULL;

-- ================================================================
-- 2. Create/verify known_client_emails table
-- ================================================================

CREATE TABLE IF NOT EXISTS known_client_emails (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_address VARCHAR(255) NOT NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    client_name VARCHAR(255),
    source_type VARCHAR(50) DEFAULT 'manual', -- 'lead', 'loan', 'contact', 'manual'
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_email UNIQUE(user_id, email_address)
);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_known_client_emails_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_known_client_emails_timestamp
ON known_client_emails;

CREATE TRIGGER trigger_update_known_client_emails_timestamp
    BEFORE UPDATE ON known_client_emails
    FOR EACH ROW
    EXECUTE FUNCTION update_known_client_emails_timestamp();

-- ================================================================
-- 3. Add co-borrower email to loans table
-- ================================================================

ALTER TABLE loans
ADD COLUMN IF NOT EXISTS coborrower_email VARCHAR(255);

-- ================================================================
-- 4. Create optimized indexes
-- ================================================================

-- Email reconciliation queue indexes
CREATE INDEX IF NOT EXISTS idx_email_queue_thread_user
ON email_reconciliation_queue(thread_id, user_id, received_date DESC)
WHERE thread_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_email_queue_priority
ON email_reconciliation_queue(user_id, is_priority, received_date DESC)
WHERE is_priority = TRUE AND status = 'pending';

CREATE INDEX IF NOT EXISTS idx_email_queue_status_user
ON email_reconciliation_queue(user_id, status, received_date DESC);

CREATE INDEX IF NOT EXISTS idx_email_queue_match_lookup
ON email_reconciliation_queue(user_id, matched_loan_id, matched_lead_id, matched_contact_id)
WHERE matched_loan_id IS NOT NULL
   OR matched_lead_id IS NOT NULL
   OR matched_contact_id IS NOT NULL;

-- Known client emails indexes
CREATE INDEX IF NOT EXISTS idx_known_client_emails_lookup
ON known_client_emails(email_address, user_id);

CREATE INDEX IF NOT EXISTS idx_known_client_emails_user
ON known_client_emails(user_id, last_synced DESC);

CREATE INDEX IF NOT EXISTS idx_known_client_emails_contact
ON known_client_emails(contact_id)
WHERE contact_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_known_client_emails_loan
ON known_client_emails(loan_id)
WHERE loan_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_known_client_emails_lead
ON known_client_emails(lead_id)
WHERE lead_id IS NOT NULL;

-- Loan table indexes for email matching
CREATE INDEX IF NOT EXISTS idx_loans_borrower_email
ON loans(lower(borrower_email), loan_officer_id)
WHERE borrower_email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_loans_coborrower_email
ON loans(lower(coborrower_email), loan_officer_id)
WHERE coborrower_email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_loans_loan_number_officer
ON loans(loan_number, loan_officer_id)
WHERE loan_number IS NOT NULL;

-- Lead table indexes for email matching
CREATE INDEX IF NOT EXISTS idx_leads_email_owner
ON leads(lower(email), owner_id)
WHERE email IS NOT NULL AND status NOT IN ('dead', 'closed_lost');

-- Contact table indexes
CREATE INDEX IF NOT EXISTS idx_contacts_email_user
ON contacts(lower(email), user_id)
WHERE email IS NOT NULL;

-- ================================================================
-- 5. Create helper views
-- ================================================================

-- View for high-priority unprocessed emails
CREATE OR REPLACE VIEW v_priority_emails AS
SELECT
    e.*,
    CASE
        WHEN e.matched_loan_id IS NOT NULL THEN l.borrower_name
        WHEN e.matched_lead_id IS NOT NULL THEN ld.name
        WHEN e.matched_contact_id IS NOT NULL THEN CONCAT(c.first_name, ' ', c.last_name)
        ELSE e.match_client_name
    END AS resolved_client_name,
    l.loan_number as resolved_loan_number,
    l.property_address as loan_property,
    ld.phone as lead_phone,
    c.phone as contact_phone
FROM email_reconciliation_queue e
LEFT JOIN loans l ON e.matched_loan_id = l.id
LEFT JOIN leads ld ON e.matched_lead_id = ld.id
LEFT JOIN contacts c ON e.matched_contact_id = c.id
WHERE e.is_priority = TRUE
  AND e.status = 'pending'
ORDER BY e.received_date DESC;

-- View for match analytics
CREATE OR REPLACE VIEW v_email_match_stats AS
SELECT
    user_id,
    match_method,
    COUNT(*) as match_count,
    AVG(match_confidence) as avg_confidence,
    COUNT(*) FILTER (WHERE is_priority = TRUE) as priority_count,
    MIN(created_at) as first_match,
    MAX(created_at) as last_match
FROM email_reconciliation_queue
WHERE match_method IS NOT NULL
  AND created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY user_id, match_method;

-- ================================================================
-- 6. Add helpful functions
-- ================================================================

-- Function to get all emails for a client across entities
CREATE OR REPLACE FUNCTION get_client_emails(
    p_user_id INTEGER,
    p_contact_id INTEGER DEFAULT NULL,
    p_loan_id INTEGER DEFAULT NULL,
    p_lead_id INTEGER DEFAULT NULL
)
RETURNS TABLE(email_address VARCHAR, source_type VARCHAR) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        kce.email_address,
        kce.source_type
    FROM known_client_emails kce
    WHERE kce.user_id = p_user_id
      AND (
          (p_contact_id IS NOT NULL AND kce.contact_id = p_contact_id) OR
          (p_loan_id IS NOT NULL AND kce.loan_id = p_loan_id) OR
          (p_lead_id IS NOT NULL AND kce.lead_id = p_lead_id)
      )
    ORDER BY kce.email_address;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to sync a single entity's emails
CREATE OR REPLACE FUNCTION sync_entity_emails(
    p_user_id INTEGER,
    p_entity_type VARCHAR,
    p_entity_id INTEGER
)
RETURNS INTEGER AS $$
DECLARE
    v_email VARCHAR;
    v_client_name VARCHAR;
    v_synced_count INTEGER := 0;
BEGIN
    IF p_entity_type = 'lead' THEN
        SELECT email, name INTO v_email, v_client_name
        FROM leads WHERE id = p_entity_id;

        IF v_email IS NOT NULL THEN
            INSERT INTO known_client_emails (
                user_id, email_address, lead_id, client_name, source_type
            ) VALUES (
                p_user_id, LOWER(v_email), p_entity_id, v_client_name, 'lead'
            )
            ON CONFLICT (user_id, email_address)
            DO UPDATE SET
                lead_id = EXCLUDED.lead_id,
                client_name = EXCLUDED.client_name,
                last_synced = CURRENT_TIMESTAMP;
            v_synced_count := 1;
        END IF;

    ELSIF p_entity_type = 'loan' THEN
        SELECT borrower_email, borrower_name INTO v_email, v_client_name
        FROM loans WHERE id = p_entity_id;

        IF v_email IS NOT NULL THEN
            INSERT INTO known_client_emails (
                user_id, email_address, loan_id, client_name, source_type
            ) VALUES (
                p_user_id, LOWER(v_email), p_entity_id, v_client_name, 'loan'
            )
            ON CONFLICT (user_id, email_address)
            DO UPDATE SET
                loan_id = EXCLUDED.loan_id,
                client_name = EXCLUDED.client_name,
                last_synced = CURRENT_TIMESTAMP;
            v_synced_count := v_synced_count + 1;
        END IF;

        -- Also sync co-borrower email
        SELECT coborrower_email INTO v_email
        FROM loans WHERE id = p_entity_id;

        IF v_email IS NOT NULL THEN
            INSERT INTO known_client_emails (
                user_id, email_address, loan_id, client_name, source_type
            ) VALUES (
                p_user_id, LOWER(v_email), p_entity_id, v_client_name || ' (Co-Borrower)', 'loan'
            )
            ON CONFLICT (user_id, email_address)
            DO UPDATE SET
                loan_id = EXCLUDED.loan_id,
                last_synced = CURRENT_TIMESTAMP;
            v_synced_count := v_synced_count + 1;
        END IF;

    ELSIF p_entity_type = 'contact' THEN
        SELECT email, CONCAT(first_name, ' ', last_name) INTO v_email, v_client_name
        FROM contacts WHERE id = p_entity_id;

        IF v_email IS NOT NULL THEN
            INSERT INTO known_client_emails (
                user_id, email_address, contact_id, client_name, source_type
            ) VALUES (
                p_user_id, LOWER(v_email), p_entity_id, v_client_name, 'contact'
            )
            ON CONFLICT (user_id, email_address)
            DO UPDATE SET
                contact_id = EXCLUDED.contact_id,
                client_name = EXCLUDED.client_name,
                last_synced = CURRENT_TIMESTAMP;
            v_synced_count := 1;
        END IF;
    END IF;

    RETURN v_synced_count;
END;
$$ LANGUAGE plpgsql;

-- ================================================================
-- 7. Add audit columns to track changes
-- ================================================================

ALTER TABLE known_client_emails
ADD COLUMN IF NOT EXISTS synced_from_api BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS manual_override BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS notes TEXT;

-- ================================================================
-- 8. Data cleanup and validation
-- ================================================================

-- Remove duplicate known client emails (keep most recent)
DELETE FROM known_client_emails a
USING known_client_emails b
WHERE a.id < b.id
  AND a.user_id = b.user_id
  AND a.email_address = b.email_address;

-- Normalize existing email addresses
UPDATE email_reconciliation_queue
SET from_email = LOWER(TRIM(from_email))
WHERE from_email IS NOT NULL AND from_email != LOWER(TRIM(from_email));

UPDATE known_client_emails
SET email_address = LOWER(TRIM(email_address))
WHERE email_address != LOWER(TRIM(email_address));

-- ================================================================
-- 9. Grant permissions (adjust role name as needed)
-- ================================================================

-- GRANT SELECT, INSERT, UPDATE ON email_reconciliation_queue TO app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON known_client_emails TO app_user;
-- GRANT USAGE, SELECT ON SEQUENCE known_client_emails_id_seq TO app_user;

-- ================================================================
-- 10. Create update log table (optional, for auditing)
-- ================================================================

CREATE TABLE IF NOT EXISTS email_identity_resolution_log (
    id SERIAL PRIMARY KEY,
    email_queue_id INTEGER REFERENCES email_reconciliation_queue(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    match_method VARCHAR(100),
    match_confidence NUMERIC(3,2),
    matched_contact_id INTEGER,
    matched_loan_id INTEGER,
    matched_lead_id INTEGER,
    resolution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_identity_log_queue
ON email_identity_resolution_log(email_queue_id);

CREATE INDEX IF NOT EXISTS idx_identity_log_user_date
ON email_identity_resolution_log(user_id, created_at DESC);

-- ================================================================
-- Final verification
-- ================================================================

DO $$
DECLARE
    v_queue_count INTEGER;
    v_known_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_queue_count FROM email_reconciliation_queue;
    SELECT COUNT(*) INTO v_known_count FROM known_client_emails;

    RAISE NOTICE 'Migration completed successfully!';
    RAISE NOTICE 'Email queue records: %', v_queue_count;
    RAISE NOTICE 'Known client emails: %', v_known_count;
    RAISE NOTICE 'Next step: Run /api/v1/email-intelligence/sync-known-clients';
END $$;

COMMIT;

-- ================================================================
-- Rollback script (save separately as rollback_email_identity.sql)
-- ================================================================

/*
BEGIN;

-- Drop new objects
DROP VIEW IF EXISTS v_priority_emails;
DROP VIEW IF EXISTS v_email_match_stats;
DROP FUNCTION IF EXISTS get_client_emails(INTEGER, INTEGER, INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sync_entity_emails(INTEGER, VARCHAR, INTEGER);
DROP TABLE IF EXISTS email_identity_resolution_log;

-- Remove new columns
ALTER TABLE email_reconciliation_queue
DROP COLUMN IF EXISTS match_evidence,
DROP COLUMN IF EXISTS match_client_name,
DROP COLUMN IF EXISTS match_loan_number;

ALTER TABLE loans
DROP COLUMN IF EXISTS coborrower_email;

-- Note: Keep known_client_emails table as it may contain valuable data
-- To completely remove:
-- DROP TABLE IF EXISTS known_client_emails;

COMMIT;
*/
