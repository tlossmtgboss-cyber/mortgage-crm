-- Migration: Add voice_workflow_sessions table for conversational AI workflows
-- Created: 2026-01-11

-- Table to store voice-driven workflow sessions
CREATE TABLE IF NOT EXISTS voice_workflow_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id),

    -- Workflow type and state
    workflow_type VARCHAR(50) NOT NULL,
    current_state VARCHAR(50) NOT NULL,

    -- Slot data collected during conversation
    slots JSONB DEFAULT '{}'::jsonb,

    -- Full conversation history for context
    conversation_history JSONB DEFAULT '[]'::jsonb,

    -- Timestamps
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    -- Execution result when workflow completes
    execution_result JSONB,

    -- Session status
    is_active BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_voice_workflow_sessions_user_id ON voice_workflow_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_voice_workflow_sessions_active ON voice_workflow_sessions(user_id, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_voice_workflow_sessions_type ON voice_workflow_sessions(workflow_type);
CREATE INDEX IF NOT EXISTS idx_voice_workflow_sessions_started_at ON voice_workflow_sessions(started_at DESC);

-- Add comment
COMMENT ON TABLE voice_workflow_sessions IS 'Voice-driven workflow sessions for conversational AI task completion';
