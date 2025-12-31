-- Migration: Comparison Enhancements
-- Adds support for:
-- 1. Comparison history with saved/favorite status
-- 2. Shareable comparison links with tokens
-- 3. Batch comparisons (3+ estimates)
-- 4. Prepayment analysis data

-- Add share token and user tracking to comparisons
ALTER TABLE estimate_comparisons
ADD COLUMN IF NOT EXISTS share_token VARCHAR(32) UNIQUE,
ADD COLUMN IF NOT EXISTS is_saved BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS title VARCHAR(200),
ADD COLUMN IF NOT EXISTS notes TEXT,
ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP;

-- Index for share token lookups
CREATE INDEX IF NOT EXISTS idx_comparisons_share_token ON estimate_comparisons (share_token) WHERE share_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_comparisons_saved ON estimate_comparisons (user_id, is_saved) WHERE is_saved = TRUE;

-- Batch comparisons table - supports 3+ estimates
CREATE TABLE IF NOT EXISTS batch_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER,
    session_id VARCHAR(100),
    title VARCHAR(200),
    share_token VARCHAR(32) UNIQUE,
    is_public BOOLEAN DEFAULT FALSE,
    is_saved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_batch_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS batch_comparison_estimates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_comparison_id UUID NOT NULL,
    estimate_hash VARCHAR(64) NOT NULL,
    label VARCHAR(50),  -- e.g., "Estimate A", "Bank of America", etc.
    display_order INTEGER DEFAULT 0,
    is_winner BOOLEAN DEFAULT FALSE,
    CONSTRAINT fk_batch_comparison FOREIGN KEY (batch_comparison_id) REFERENCES batch_comparisons(id) ON DELETE CASCADE,
    CONSTRAINT fk_batch_estimate FOREIGN KEY (estimate_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_batch_estimates ON batch_comparison_estimates (batch_comparison_id);
CREATE INDEX IF NOT EXISTS idx_batch_share ON batch_comparisons (share_token) WHERE share_token IS NOT NULL;

-- Prepayment analysis cache
CREATE TABLE IF NOT EXISTS prepayment_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_id UUID,
    batch_comparison_id UUID,
    estimate_hash VARCHAR(64) NOT NULL,
    extra_monthly_payment NUMERIC(12, 2),
    extra_yearly_payment NUMERIC(12, 2),
    one_time_payment NUMERIC(12, 2),
    original_term_months INTEGER,
    new_term_months INTEGER,
    months_saved INTEGER,
    total_interest_saved NUMERIC(12, 2),
    original_total_interest NUMERIC(12, 2),
    new_total_interest NUMERIC(12, 2),
    payoff_date DATE,
    original_payoff_date DATE,
    analysis_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_prepay_comparison FOREIGN KEY (comparison_id) REFERENCES estimate_comparisons(id) ON DELETE CASCADE,
    CONSTRAINT fk_prepay_batch FOREIGN KEY (batch_comparison_id) REFERENCES batch_comparisons(id) ON DELETE CASCADE,
    CONSTRAINT fk_prepay_estimate FOREIGN KEY (estimate_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prepayment_comparison ON prepayment_analyses (comparison_id);
CREATE INDEX IF NOT EXISTS idx_prepayment_estimate ON prepayment_analyses (estimate_hash);

-- Tax impact analysis cache
CREATE TABLE IF NOT EXISTS tax_impact_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comparison_id UUID,
    estimate_hash VARCHAR(64) NOT NULL,
    filing_status VARCHAR(20) DEFAULT 'single',  -- single, married_filing_jointly, married_filing_separately, head_of_household
    annual_income NUMERIC(12, 2),
    marginal_tax_rate NUMERIC(5, 2),
    state_tax_rate NUMERIC(5, 2),
    standard_deduction NUMERIC(12, 2),
    year_1_interest NUMERIC(12, 2),
    year_1_property_tax NUMERIC(12, 2),
    year_1_total_deduction NUMERIC(12, 2),
    year_1_tax_savings NUMERIC(12, 2),
    itemize_benefit BOOLEAN,
    lifetime_tax_savings NUMERIC(12, 2),
    analysis_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_tax_comparison FOREIGN KEY (comparison_id) REFERENCES estimate_comparisons(id) ON DELETE CASCADE,
    CONSTRAINT fk_tax_estimate FOREIGN KEY (estimate_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tax_comparison ON tax_impact_analyses (comparison_id);
CREATE INDEX IF NOT EXISTS idx_tax_estimate ON tax_impact_analyses (estimate_hash);
