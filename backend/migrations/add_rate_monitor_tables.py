"""
Migration: Create Rate Monitor Tables
Tracks refinance opportunities for MUM clients with market rate monitoring
"""
from sqlalchemy import create_engine, text
import os


def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')


def upgrade():
    """Create Rate Monitor tables"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- ============================================================================
    -- Rate Monitor Targets
    -- Defines rate/savings thresholds for MUM clients to trigger refinance alerts
    -- ============================================================================
    CREATE TABLE IF NOT EXISTS rate_monitor_targets (
        id SERIAL PRIMARY KEY,

        -- Link to MUM client
        mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE CASCADE,

        -- Target Type: 'savings_threshold', 'rate_drop_percentage', 'manual_target'
        target_type VARCHAR(50) NOT NULL,

        -- Savings Threshold Target (e.g., $200/month triggers alert)
        monthly_savings_threshold DECIMAL(10, 2),

        -- Rate Drop Percentage Target (e.g., 0.5% below client rate triggers alert)
        rate_drop_percentage DECIMAL(5, 3),

        -- Manual Target Rate (e.g., trigger when rates hit 5.5%)
        target_rate DECIMAL(5, 3),

        -- Loan Scenario Parameters for rate lookup
        loan_type VARCHAR(50) DEFAULT 'conventional',  -- conventional, fha, va, etc.
        loan_term INTEGER DEFAULT 30,  -- 15, 20, 30 years

        -- Status
        status VARCHAR(50) DEFAULT 'active',  -- active, paused, triggered, expired
        is_active BOOLEAN DEFAULT TRUE,

        -- AI Receptionist Integration
        auto_call_enabled BOOLEAN DEFAULT FALSE,
        call_preference VARCHAR(50) DEFAULT 'business_hours',  -- business_hours, any_time, weekdays_only

        -- Call Tracking (when target triggers)
        last_triggered_at TIMESTAMP,
        trigger_count INTEGER DEFAULT 0,
        vapi_call_id VARCHAR(100),
        last_call_status VARCHAR(50),
        last_call_at TIMESTAMP,
        appointment_scheduled BOOLEAN DEFAULT FALSE,
        appointment_date TIMESTAMP,

        -- Notification Settings
        notify_email BOOLEAN DEFAULT TRUE,
        notify_sms BOOLEAN DEFAULT TRUE,
        notify_lo BOOLEAN DEFAULT TRUE,

        -- Metadata
        notes TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ============================================================================
    -- Rate Monitor History
    -- Audit trail of all rate checks performed by the background job
    -- ============================================================================
    CREATE TABLE IF NOT EXISTS rate_monitor_history (
        id SERIAL PRIMARY KEY,

        target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
        mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE SET NULL,

        -- Rate Check Details
        check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        client_rate DECIMAL(5, 3),
        market_rate DECIMAL(5, 3),
        rate_difference DECIMAL(5, 3),

        -- Calculated Values
        loan_balance DECIMAL(12, 2),
        monthly_savings DECIMAL(10, 2),
        annual_savings DECIMAL(12, 2),

        -- Threshold Comparison
        threshold_met BOOLEAN DEFAULT FALSE,
        threshold_type VARCHAR(50),  -- savings, rate_drop, manual
        threshold_value DECIMAL(10, 3),

        -- Action Taken
        alert_generated BOOLEAN DEFAULT FALSE,
        call_initiated BOOLEAN DEFAULT FALSE,

        -- Rate Source
        rate_source VARCHAR(100) DEFAULT 'optimal_blue',
        rate_scenario JSONB  -- Full scenario used for rate lookup
    );

    -- ============================================================================
    -- Rate Monitor Alerts
    -- Notifications generated when targets are triggered
    -- ============================================================================
    CREATE TABLE IF NOT EXISTS rate_monitor_alerts (
        id SERIAL PRIMARY KEY,

        target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
        mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE SET NULL,
        history_id INTEGER REFERENCES rate_monitor_history(id) ON DELETE SET NULL,

        -- Alert Details
        alert_type VARCHAR(50) NOT NULL,  -- rate_target_hit, savings_threshold, rate_drop
        priority VARCHAR(20) DEFAULT 'medium',  -- low, medium, high, urgent

        -- Rate Information
        client_rate DECIMAL(5, 3),
        market_rate DECIMAL(5, 3),
        monthly_savings DECIMAL(10, 2),
        annual_savings DECIMAL(12, 2),

        -- Status
        status VARCHAR(50) DEFAULT 'pending',  -- pending, acknowledged, called, converted, dismissed

        -- AI Call Tracking
        auto_call_attempted BOOLEAN DEFAULT FALSE,
        vapi_call_id VARCHAR(100),
        call_status VARCHAR(50),  -- initiated, in_progress, completed, failed, no_answer
        call_outcome VARCHAR(100),  -- appointment_scheduled, callback_requested, not_interested, voicemail
        call_duration INTEGER,  -- seconds
        call_summary TEXT,
        appointment_scheduled_at TIMESTAMP,

        -- Manual Follow-up
        assigned_to INTEGER,  -- User ID for manual follow-up
        follow_up_notes TEXT,
        follow_up_date DATE,

        -- Conversion Tracking
        converted_to_application BOOLEAN DEFAULT FALSE,
        application_id INTEGER,
        conversion_date DATE,

        -- Timestamps
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        acknowledged_at TIMESTAMP,
        resolved_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ============================================================================
    -- Optimal Blue Rate Cache
    -- Caches rate data from Optimal Blue API (15-minute TTL)
    -- ============================================================================
    CREATE TABLE IF NOT EXISTS optimal_blue_rate_cache (
        id SERIAL PRIMARY KEY,

        -- Cache Key (combination of loan scenario parameters)
        cache_key VARCHAR(255) UNIQUE NOT NULL,

        -- Loan Scenario
        loan_type VARCHAR(50) NOT NULL,
        loan_term INTEGER NOT NULL,
        loan_amount DECIMAL(12, 2),
        ltv DECIMAL(5, 2),
        credit_score INTEGER,
        property_type VARCHAR(50),
        occupancy VARCHAR(50),
        state VARCHAR(2),

        -- Rate Data
        rate DECIMAL(5, 3) NOT NULL,
        apr DECIMAL(5, 3),
        points DECIMAL(5, 3),
        lender_credits DECIMAL(10, 2),

        -- Additional Rate Options
        rate_options JSONB,  -- Array of different point/rate combinations

        -- Metadata
        source VARCHAR(50) DEFAULT 'optimal_blue',
        is_mock BOOLEAN DEFAULT FALSE,  -- True if using mock data
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,

        -- Raw Response
        raw_response JSONB
    );

    -- ============================================================================
    -- Indexes for Performance
    -- ============================================================================

    -- Rate Monitor Targets
    CREATE INDEX IF NOT EXISTS idx_rate_targets_mum_client ON rate_monitor_targets(mum_client_id);
    CREATE INDEX IF NOT EXISTS idx_rate_targets_status ON rate_monitor_targets(status);
    CREATE INDEX IF NOT EXISTS idx_rate_targets_active ON rate_monitor_targets(is_active) WHERE is_active = TRUE;
    CREATE INDEX IF NOT EXISTS idx_rate_targets_auto_call ON rate_monitor_targets(auto_call_enabled) WHERE auto_call_enabled = TRUE;

    -- Rate Monitor History
    CREATE INDEX IF NOT EXISTS idx_rate_history_target ON rate_monitor_history(target_id);
    CREATE INDEX IF NOT EXISTS idx_rate_history_client ON rate_monitor_history(mum_client_id);
    CREATE INDEX IF NOT EXISTS idx_rate_history_timestamp ON rate_monitor_history(check_timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_rate_history_threshold_met ON rate_monitor_history(threshold_met) WHERE threshold_met = TRUE;

    -- Rate Monitor Alerts
    CREATE INDEX IF NOT EXISTS idx_rate_alerts_target ON rate_monitor_alerts(target_id);
    CREATE INDEX IF NOT EXISTS idx_rate_alerts_client ON rate_monitor_alerts(mum_client_id);
    CREATE INDEX IF NOT EXISTS idx_rate_alerts_status ON rate_monitor_alerts(status);
    CREATE INDEX IF NOT EXISTS idx_rate_alerts_pending ON rate_monitor_alerts(status) WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_rate_alerts_created ON rate_monitor_alerts(created_at DESC);

    -- Rate Cache
    CREATE INDEX IF NOT EXISTS idx_rate_cache_key ON optimal_blue_rate_cache(cache_key);
    CREATE INDEX IF NOT EXISTS idx_rate_cache_expires ON optimal_blue_rate_cache(expires_at);
    CREATE INDEX IF NOT EXISTS idx_rate_cache_scenario ON optimal_blue_rate_cache(loan_type, loan_term, credit_score);

    -- ============================================================================
    -- Trigger for updated_at
    -- ============================================================================
    CREATE OR REPLACE FUNCTION update_rate_monitor_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ language 'plpgsql';

    DROP TRIGGER IF EXISTS rate_targets_updated_at ON rate_monitor_targets;
    CREATE TRIGGER rate_targets_updated_at
        BEFORE UPDATE ON rate_monitor_targets
        FOR EACH ROW EXECUTE FUNCTION update_rate_monitor_updated_at();

    DROP TRIGGER IF EXISTS rate_alerts_updated_at ON rate_monitor_alerts;
    CREATE TRIGGER rate_alerts_updated_at
        BEFORE UPDATE ON rate_monitor_alerts
        FOR EACH ROW EXECUTE FUNCTION update_rate_monitor_updated_at();
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("Rate Monitor tables created successfully")


def downgrade():
    """Drop Rate Monitor tables"""
    engine = create_engine(get_database_url())

    downgrade_sql = """
    DROP TABLE IF EXISTS rate_monitor_alerts CASCADE;
    DROP TABLE IF EXISTS rate_monitor_history CASCADE;
    DROP TABLE IF EXISTS optimal_blue_rate_cache CASCADE;
    DROP TABLE IF EXISTS rate_monitor_targets CASCADE;

    DROP FUNCTION IF EXISTS update_rate_monitor_updated_at() CASCADE;
    """

    with engine.connect() as conn:
        conn.execute(text(downgrade_sql))
        conn.commit()

    print("Rate Monitor tables dropped successfully")


if __name__ == "__main__":
    print("Creating Rate Monitor tables...")
    upgrade()
    print("Done!")
