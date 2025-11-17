-- Migration: Add onboarding tables and user verification fields
-- Run this via: railway run psql < onboarding_migration.sql

-- Add fields to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS nmls_number VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_address VARCHAR(500);
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_role VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_hours JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP WITH TIME ZONE;

-- Create indexes on users table
CREATE INDEX IF NOT EXISTS idx_users_nmls_number ON users(nmls_number);
CREATE INDEX IF NOT EXISTS idx_users_email_verified_at ON users(email_verified_at);
CREATE INDEX IF NOT EXISTS idx_users_phone_verified_at ON users(phone_verified_at);

-- Create onboarding_progress table
CREATE TABLE IF NOT EXISTS onboarding_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    current_step INTEGER NOT NULL DEFAULT 1,
    step_1_data JSONB,
    step_2_data JSONB,
    step_3_data JSONB,
    step_4_data JSONB,
    step_5_data JSONB,
    step_6_data JSONB,
    step_7_data JSONB,
    step_8_data JSONB,
    step_9_data JSONB,
    step_10_data JSONB,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_progress_user_id ON onboarding_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_progress_current_step ON onboarding_progress(current_step);

-- Create onboarding_errors table
CREATE TABLE IF NOT EXISTS onboarding_errors (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    error_code VARCHAR(20) NOT NULL,
    step_number INTEGER NOT NULL,
    error_message TEXT NOT NULL,
    error_context JSONB,
    user_action VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_errors_user_id ON onboarding_errors(user_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_errors_error_code ON onboarding_errors(error_code);
CREATE INDEX IF NOT EXISTS idx_onboarding_errors_step_number ON onboarding_errors(step_number);
CREATE INDEX IF NOT EXISTS idx_onboarding_errors_created_at ON onboarding_errors(created_at);

-- Create verification_tokens table
CREATE TABLE IF NOT EXISTS verification_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_type VARCHAR(20) NOT NULL,
    token VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires_at ON verification_tokens(expires_at);

-- Verify migration
\echo 'Migration complete! Verifying tables...'
\dt onboarding*
\dt verification*
\echo 'Verifying users table columns...'
SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' AND column_name IN ('phone', 'nmls_number', 'business_address', 'current_role', 'business_hours', 'email_verified_at', 'phone_verified_at');
