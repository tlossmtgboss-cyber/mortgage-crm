-- Migration: Add user_integrations table
-- Description: Stores OAuth tokens for user-delegated API access (Microsoft, Google, etc.)
-- Created: 2024-12-05

-- Create the user_integrations table
CREATE TABLE IF NOT EXISTS user_integrations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    provider VARCHAR(50) NOT NULL,  -- 'microsoft', 'google', etc.

    -- OAuth tokens
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,

    -- Additional metadata
    scopes TEXT,  -- Comma-separated list of granted scopes
    email VARCHAR(255),  -- User's email on the provider
    provider_user_id VARCHAR(255),  -- User ID on provider

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT fk_user_integrations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uix_user_provider UNIQUE (user_id, provider)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_user_integrations_user_id ON user_integrations(user_id);
CREATE INDEX IF NOT EXISTS ix_user_integrations_user_provider ON user_integrations(user_id, provider);
CREATE INDEX IF NOT EXISTS ix_user_integrations_provider ON user_integrations(provider);

-- Add comment
COMMENT ON TABLE user_integrations IS 'Stores OAuth tokens for user-delegated API access to external services';
