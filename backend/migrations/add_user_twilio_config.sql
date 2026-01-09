-- User Twilio Configuration Table
-- Stores per-user Twilio credentials and setup status

CREATE TABLE IF NOT EXISTS user_twilio_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Twilio Credentials (encrypted at rest recommended)
    account_sid VARCHAR(34),
    auth_token VARCHAR(255),

    -- Phone Number
    phone_number VARCHAR(20),
    phone_number_sid VARCHAR(34),

    -- Messaging Service
    messaging_service_sid VARCHAR(34),

    -- A2P 10DLC Registration
    brand_sid VARCHAR(34),
    campaign_sid VARCHAR(34),
    a2p_status VARCHAR(50) DEFAULT 'pending',

    -- Trust Hub / Customer Profile
    customer_profile_sid VARCHAR(34),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Ensure one config per user
    CONSTRAINT unique_user_twilio_config UNIQUE (user_id)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_twilio_config_user_id ON user_twilio_config(user_id);
CREATE INDEX IF NOT EXISTS idx_user_twilio_config_account_sid ON user_twilio_config(account_sid);

-- Add comment
COMMENT ON TABLE user_twilio_config IS 'Stores per-user Twilio configuration for self-service setup';
