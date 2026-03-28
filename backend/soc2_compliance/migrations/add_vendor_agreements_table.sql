-- ============================================================================
-- SOC 2 Vendor BAA/DPA Agreement Tracking
-- Maps to: CC9 (Risk Mitigation), C1 (Confidentiality), P1-P8 (Privacy)
--
-- Run: psql $DATABASE_URL -f migrations/add_vendor_agreements_table.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- VENDOR AGREEMENTS — Track BAA/DPA status per vendor
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_vendor_agreements (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- FK to vendor registry
    vendor_id       INTEGER NOT NULL REFERENCES soc2_vendor_registry(id) ON DELETE CASCADE,

    -- Agreement classification
    agreement_type  VARCHAR(20) NOT NULL,    -- baa, dpa, baa_and_dpa
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, signed, expired, not_required, under_review

    -- Execution details
    signed_date     DATE,
    effective_date  DATE,
    expiry_date     DATE,
    signed_by       VARCHAR(255),            -- Perennia signer name
    vendor_signer   VARCHAR(255),            -- Vendor-side signer name
    vendor_signer_title VARCHAR(255),        -- Vendor-side signer title

    -- Document reference
    document_url    TEXT,                     -- Link to signed document (S3, GDrive, etc.)
    document_hash   VARCHAR(128),            -- SHA-256 hash of signed PDF for integrity

    -- Scope
    data_categories TEXT[],                  -- e.g., {'PII', 'PHI', 'financial'}
    processing_purposes TEXT[],             -- e.g., {'email_delivery', 'voice_calls'}
    sub_processors  TEXT[],                 -- Known sub-processors listed in agreement

    -- Renewal / review
    auto_renew      BOOLEAN DEFAULT FALSE,
    renewal_notice_days INTEGER DEFAULT 90,  -- Days before expiry to alert
    last_review_date DATE,
    next_review_date DATE,

    -- Audit trail
    notes           TEXT,
    reviewed_by     VARCHAR(255),            -- Who last reviewed this agreement

    -- Ensure one agreement type per vendor (can have separate BAA and DPA)
    UNIQUE(vendor_id, agreement_type)
);

CREATE INDEX idx_vendor_agreements_vendor ON soc2_vendor_agreements(vendor_id);
CREATE INDEX idx_vendor_agreements_status ON soc2_vendor_agreements(status);
CREATE INDEX idx_vendor_agreements_expiry ON soc2_vendor_agreements(expiry_date)
    WHERE status = 'signed';

-- Auto-update timestamp trigger
CREATE TRIGGER update_vendor_agreements_timestamp
    BEFORE UPDATE ON soc2_vendor_agreements
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'soc2_vendor_agreements'
    ) THEN
        RAISE EXCEPTION 'Table soc2_vendor_agreements was not created';
    END IF;
    RAISE NOTICE 'soc2_vendor_agreements table created successfully.';
END $$;
