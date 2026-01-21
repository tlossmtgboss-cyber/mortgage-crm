-- Rate Sheet Upload & AI Outreach System
-- Migration: add_rate_sheet_tables.sql
-- Created: 2026-01-20

-- Table 1: rate_sheets - Uploaded rate sheet tracking
CREATE TABLE IF NOT EXISTS rate_sheets (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) UNIQUE,
    s3_key VARCHAR(500),
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, parsed, failed
    parsed_data JSONB,
    effective_date DATE,
    lender_name VARCHAR(255),
    error_message TEXT,
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: rate_sheet_rates - Parsed rates from each sheet
CREATE TABLE IF NOT EXISTS rate_sheet_rates (
    id SERIAL PRIMARY KEY,
    rate_sheet_id INTEGER NOT NULL REFERENCES rate_sheets(id) ON DELETE CASCADE,
    loan_type VARCHAR(50) NOT NULL,      -- conventional, fha, va, usda, jumbo
    loan_term INTEGER NOT NULL,          -- 15, 20, 30
    rate NUMERIC(5,3) NOT NULL,
    apr NUMERIC(5,3),
    points NUMERIC(5,3),
    min_credit_score INTEGER,
    max_credit_score INTEGER,
    min_ltv NUMERIC(5,2),
    max_ltv NUMERIC(5,2),
    occupancy VARCHAR(50),               -- primary, second_home, investment
    property_type VARCHAR(50),           -- single_family, condo, townhouse, multi_family
    confidence_score NUMERIC(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: refinance_opportunities - Identified opportunities
CREATE TABLE IF NOT EXISTS refinance_opportunities (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id),
    rate_sheet_id INTEGER REFERENCES rate_sheets(id),

    -- Client info (denormalized for quick access)
    client_name VARCHAR(255),
    client_phone VARCHAR(50),
    client_email VARCHAR(255),

    -- Current loan details
    current_rate NUMERIC(5,3) NOT NULL,
    current_loan_amount NUMERIC(12,2) NOT NULL,
    loan_type VARCHAR(50),
    loan_term INTEGER,
    funded_date DATE,

    -- New rate opportunity
    new_rate NUMERIC(5,3) NOT NULL,
    rate_difference NUMERIC(5,3) NOT NULL,
    monthly_savings NUMERIC(10,2),
    annual_savings NUMERIC(12,2),

    -- Scoring
    priority VARCHAR(20) DEFAULT 'medium',  -- low, medium, high, urgent
    opportunity_score NUMERIC(5,2),

    -- Outreach tracking
    status VARCHAR(50) DEFAULT 'identified',  -- identified, sms_sent, called, scheduled, converted, declined, opted_out
    sms_sent_at TIMESTAMP,
    sms_message_sid VARCHAR(100),
    call_initiated_at TIMESTAMP,
    vapi_call_id VARCHAR(100),
    call_status VARCHAR(50),
    call_outcome VARCHAR(100),
    call_duration INTEGER,
    call_summary TEXT,
    appointment_scheduled_at TIMESTAMP,

    -- Metadata
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for rate_sheets
CREATE INDEX IF NOT EXISTS idx_rate_sheets_status ON rate_sheets(status);
CREATE INDEX IF NOT EXISTS idx_rate_sheets_effective_date ON rate_sheets(effective_date);
CREATE INDEX IF NOT EXISTS idx_rate_sheets_created_at ON rate_sheets(created_at);

-- Indexes for rate_sheet_rates
CREATE INDEX IF NOT EXISTS idx_rate_sheet_rates_sheet_id ON rate_sheet_rates(rate_sheet_id);
CREATE INDEX IF NOT EXISTS idx_rate_sheet_rates_loan_type ON rate_sheet_rates(loan_type);
CREATE INDEX IF NOT EXISTS idx_rate_sheet_rates_loan_term ON rate_sheet_rates(loan_term);
CREATE INDEX IF NOT EXISTS idx_rate_sheet_rates_rate ON rate_sheet_rates(rate);

-- Indexes for refinance_opportunities
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_loan_id ON refinance_opportunities(loan_id);
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_rate_sheet_id ON refinance_opportunities(rate_sheet_id);
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_status ON refinance_opportunities(status);
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_priority ON refinance_opportunities(priority);
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_created_at ON refinance_opportunities(created_at);
CREATE INDEX IF NOT EXISTS idx_refi_opportunities_monthly_savings ON refinance_opportunities(monthly_savings DESC);

-- Updated_at trigger function (if not exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_rate_sheets_updated_at ON rate_sheets;
CREATE TRIGGER update_rate_sheets_updated_at
    BEFORE UPDATE ON rate_sheets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_refinance_opportunities_updated_at ON refinance_opportunities;
CREATE TRIGGER update_refinance_opportunities_updated_at
    BEFORE UPDATE ON refinance_opportunities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
