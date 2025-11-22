-- Morning Check-in AI Feature
-- Captures daily business data and calculates referral partner ROI

-- Daily check-in sessions
CREATE TABLE IF NOT EXISTS daily_checkins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL,
    hours_worked DECIMAL(4,2),
    leads_added INTEGER DEFAULT 0,
    partner_conversations INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, checkin_date)
);

-- Partner interactions log
CREATE TABLE IF NOT EXISTS partner_interactions (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER REFERENCES referral_partners(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    interaction_date DATE NOT NULL,
    interaction_type VARCHAR(50) NOT NULL, -- call, meeting, event, lunch, email, text
    duration_minutes INTEGER DEFAULT 0,
    notes TEXT,
    checkin_id INTEGER REFERENCES daily_checkins(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partner time investment tracking (aggregated)
CREATE TABLE IF NOT EXISTS partner_time_investments (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER REFERENCES referral_partners(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    month_year DATE NOT NULL, -- First day of month for grouping
    meeting_hours DECIMAL(5,2) DEFAULT 0,
    lead_followup_hours DECIMAL(5,2) DEFAULT 0,
    event_hours DECIMAL(5,2) DEFAULT 0,
    processing_hours DECIMAL(5,2) DEFAULT 0,
    other_hours DECIMAL(5,2) DEFAULT 0,
    total_hours DECIMAL(6,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(partner_id, user_id, month_year)
);

-- Partner ROI snapshots (calculated periodically)
CREATE TABLE IF NOT EXISTS partner_roi_snapshots (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER REFERENCES referral_partners(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,

    -- Lead metrics
    leads_total INTEGER DEFAULT 0,
    leads_last_12_months INTEGER DEFAULT 0,
    leads_converted INTEGER DEFAULT 0,
    conversion_rate DECIMAL(5,2) DEFAULT 0,

    -- Pipeline metrics
    active_loans_count INTEGER DEFAULT 0,
    active_loans_value DECIMAL(12,2) DEFAULT 0,

    -- Closed loan metrics (last 12 months)
    closed_loans_count INTEGER DEFAULT 0,
    closed_loans_volume DECIMAL(14,2) DEFAULT 0,
    average_loan_size DECIMAL(12,2) DEFAULT 0,
    total_revenue DECIMAL(12,2) DEFAULT 0,

    -- Time investment
    total_hours_invested DECIMAL(8,2) DEFAULT 0,
    hourly_rate DECIMAL(8,2) DEFAULT 150, -- User's hourly rate
    time_cost DECIMAL(12,2) DEFAULT 0,

    -- ROI calculations
    net_profit DECIMAL(12,2) DEFAULT 0,
    roi_percentage DECIMAL(8,2) DEFAULT 0,
    revenue_per_hour DECIMAL(8,2) DEFAULT 0,

    -- Trend indicators
    lead_trend VARCHAR(20), -- up, down, stable
    roi_trend VARCHAR(20),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(partner_id, user_id, snapshot_date)
);

-- User settings for check-in
CREATE TABLE IF NOT EXISTS user_checkin_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    hourly_rate DECIMAL(8,2) DEFAULT 150,
    checkin_reminder_time TIME DEFAULT '08:00:00',
    checkin_enabled BOOLEAN DEFAULT true,
    auto_calculate_roi BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add referral_partner_id to leads if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'leads' AND column_name = 'referral_partner_id'
    ) THEN
        ALTER TABLE leads ADD COLUMN referral_partner_id INTEGER REFERENCES referral_partners(id);
    END IF;
END $$;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_daily_checkins_user_date ON daily_checkins(user_id, checkin_date);
CREATE INDEX IF NOT EXISTS idx_partner_interactions_partner ON partner_interactions(partner_id);
CREATE INDEX IF NOT EXISTS idx_partner_interactions_user_date ON partner_interactions(user_id, interaction_date);
CREATE INDEX IF NOT EXISTS idx_partner_roi_snapshots_partner ON partner_roi_snapshots(partner_id, user_id);
CREATE INDEX IF NOT EXISTS idx_partner_time_investments_partner ON partner_time_investments(partner_id, user_id);
CREATE INDEX IF NOT EXISTS idx_leads_referral_partner ON leads(referral_partner_id);

-- Create view for current partner ROI metrics
CREATE OR REPLACE VIEW partner_roi_current AS
SELECT
    rp.id as partner_id,
    rp.name as partner_name,
    rp.company,
    rp.user_id,

    -- Lead counts
    COUNT(DISTINCT l.id) as total_leads,
    COUNT(DISTINCT CASE WHEN l.created_at > NOW() - INTERVAL '12 months' THEN l.id END) as leads_12m,
    COUNT(DISTINCT CASE WHEN l.stage IN ('Closed Won', 'Funded') THEN l.id END) as converted_leads,

    -- Conversion rate
    CASE
        WHEN COUNT(DISTINCT l.id) > 0
        THEN ROUND(100.0 * COUNT(DISTINCT CASE WHEN l.stage IN ('Closed Won', 'Funded') THEN l.id END) / COUNT(DISTINCT l.id), 1)
        ELSE 0
    END as conversion_rate,

    -- Active pipeline
    COUNT(DISTINCT CASE WHEN l.stage NOT IN ('Closed Won', 'Closed Lost', 'Funded', 'Inactive') THEN l.id END) as active_leads,
    COALESCE(SUM(CASE WHEN l.stage NOT IN ('Closed Won', 'Closed Lost', 'Funded', 'Inactive') THEN l.loan_amount END), 0) as active_pipeline_value,

    -- Revenue (using loan amount * estimated commission rate)
    COALESCE(SUM(CASE WHEN l.stage IN ('Closed Won', 'Funded') AND l.created_at > NOW() - INTERVAL '12 months'
        THEN l.loan_amount * 0.01 END), 0) as estimated_revenue_12m,

    -- Time investment (from interactions)
    COALESCE(SUM(pi.duration_minutes) / 60.0, 0) as total_hours_invested,

    -- Last contact
    MAX(pi.interaction_date) as last_contact_date

FROM referral_partners rp
LEFT JOIN leads l ON l.referral_partner_id = rp.id
LEFT JOIN partner_interactions pi ON pi.partner_id = rp.id
GROUP BY rp.id, rp.name, rp.company, rp.user_id;

-- Insert default settings for existing users
INSERT INTO user_checkin_settings (user_id, hourly_rate, checkin_enabled)
SELECT id, 150, true FROM users
ON CONFLICT (user_id) DO NOTHING;
