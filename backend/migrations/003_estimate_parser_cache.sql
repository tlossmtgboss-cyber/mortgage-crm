-- Migration: Estimate Parser Cache Tables
-- Creates tables for caching parsed loan estimates and tracking comparisons

-- Parse cache table - prevents re-processing identical uploads
CREATE TABLE IF NOT EXISTS estimate_parse_cache (
    doc_hash VARCHAR(64) PRIMARY KEY,
    parsed_json JSONB NOT NULL,
    confidence_score NUMERIC(3, 2),
    needs_review BOOLEAN DEFAULT FALSE,
    source_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    accessed_at TIMESTAMP DEFAULT NOW(),
    access_count INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_estimate_cache_created ON estimate_parse_cache (created_at);
CREATE INDEX IF NOT EXISTS idx_estimate_cache_needs_review ON estimate_parse_cache (needs_review) WHERE needs_review = true;
CREATE INDEX IF NOT EXISTS idx_estimate_cache_source_type ON estimate_parse_cache (source_type);

-- Failed parse tracking - for manual review queue
CREATE TABLE IF NOT EXISTS estimate_parse_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL,
    doc_hash VARCHAR(64) NOT NULL,
    error_stage VARCHAR(50) NOT NULL,
    error_message TEXT,
    raw_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failures_created ON estimate_parse_failures (created_at);
CREATE INDEX IF NOT EXISTS idx_failures_stage ON estimate_parse_failures (error_stage);
CREATE INDEX IF NOT EXISTS idx_failures_doc_hash ON estimate_parse_failures (doc_hash);

-- Estimate comparisons - track what users compared
CREATE TABLE IF NOT EXISTS estimate_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER,
    session_id VARCHAR(100),
    estimate_a_hash VARCHAR(64) NOT NULL,
    estimate_b_hash VARCHAR(64) NOT NULL,
    winner VARCHAR(1),
    winner_reason VARCHAR(200),
    savings_amount NUMERIC(12, 2),
    comparison_data JSONB,
    converted BOOLEAN DEFAULT FALSE,
    converted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_estimate_a FOREIGN KEY (estimate_a_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE,
    CONSTRAINT fk_estimate_b FOREIGN KEY (estimate_b_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_comparisons_user ON estimate_comparisons (user_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_created ON estimate_comparisons (created_at);
CREATE INDEX IF NOT EXISTS idx_comparisons_converted ON estimate_comparisons (converted);
