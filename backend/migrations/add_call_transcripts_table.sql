-- Migration: Add call_transcripts table for Twilio Voice Intelligence
-- Created: 2026-01-10

-- Table to store AI-transcribed call recordings with insights
CREATE TABLE IF NOT EXISTS call_transcripts (
    id SERIAL PRIMARY KEY,
    transcript_sid VARCHAR(100) UNIQUE NOT NULL,

    -- Link to call recording/activity
    call_sid VARCHAR(100),
    recording_sid VARCHAR(100),
    activity_id VARCHAR(100),

    -- Transcript data
    status VARCHAR(50) DEFAULT 'pending',
    duration_seconds INTEGER,
    language_code VARCHAR(10) DEFAULT 'en-US',
    full_text TEXT,

    -- Speaker-labeled sentences (JSONB array)
    sentences JSONB DEFAULT '[]'::jsonb,

    -- AI Insights
    sentiment JSONB,           -- Overall call sentiment
    topics JSONB DEFAULT '[]'::jsonb,   -- Detected topics
    action_items JSONB DEFAULT '[]'::jsonb,  -- Action items from call
    entities JSONB DEFAULT '[]'::jsonb,  -- Detected entities (names, amounts, dates)
    summary TEXT,               -- AI-generated call summary

    -- Redaction info
    redaction_enabled BOOLEAN DEFAULT TRUE,
    pii_detected BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_call_transcripts_call_sid ON call_transcripts(call_sid);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_recording_sid ON call_transcripts(recording_sid);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_activity_id ON call_transcripts(activity_id);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_status ON call_transcripts(status);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_created_at ON call_transcripts(created_at DESC);

-- Add comment
COMMENT ON TABLE call_transcripts IS 'AI-transcribed call recordings from Twilio Voice Intelligence with sentiment, topics, and action items';
