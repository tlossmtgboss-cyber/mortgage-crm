-- AI Delegated Tasks Table Migration
-- This table stores user preferences for delegating specific email types to AI auto-handling

CREATE TABLE IF NOT EXISTS ai_delegated_tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_intent VARCHAR NOT NULL,  -- Email intent type (e.g., "Clear to Close", "Rate Lock Request")
    action_type VARCHAR NOT NULL,   -- Action type (e.g., "status_update", "field_update")
    action_value VARCHAR,            -- Action value (e.g., "Clear to Close", "rate_lock_data")
    action_title VARCHAR,            -- Human-readable action title
    action_description TEXT,         -- Description of what AI will do
    approval_count INTEGER DEFAULT 1, -- Number of times user approved this
    last_approved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,  -- Can be revoked by setting to FALSE

    -- Ensure one delegation per user per intent+action combination
    UNIQUE(user_id, email_intent, action_type)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_ai_delegated_tasks_user_active
    ON ai_delegated_tasks(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_ai_delegated_tasks_intent
    ON ai_delegated_tasks(email_intent);

-- Add comment
COMMENT ON TABLE ai_delegated_tasks IS 'Stores user-approved AI delegation settings for auto-handling specific email types';
