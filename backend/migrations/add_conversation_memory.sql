-- Migration: Add conversation_memory table for AI Memory System
-- Date: 2024-11-14
-- Description: Creates table to store conversation metadata alongside Pinecone vectors

CREATE TABLE IF NOT EXISTS conversation_memory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
    conversation_summary TEXT NOT NULL,
    key_points JSONB,
    sentiment VARCHAR(50),
    intent VARCHAR(255),
    pinecone_id VARCHAR(255) UNIQUE,
    relevance_score FLOAT,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_id ON conversation_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_memory_lead_id ON conversation_memory(lead_id);
CREATE INDEX IF NOT EXISTS idx_conversation_memory_loan_id ON conversation_memory(loan_id);
CREATE INDEX IF NOT EXISTS idx_conversation_memory_pinecone_id ON conversation_memory(pinecone_id);
CREATE INDEX IF NOT EXISTS idx_conversation_memory_created_at ON conversation_memory(created_at);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_conversation_memory_updated_at ON conversation_memory;
CREATE TRIGGER update_conversation_memory_updated_at
    BEFORE UPDATE ON conversation_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Verify table creation
SELECT
    'conversation_memory table created successfully' as status,
    COUNT(*) as row_count
FROM conversation_memory;
