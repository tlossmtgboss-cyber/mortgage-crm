-- Voice OS Database Schema Migration
-- This migration creates the essential tables for the Voice OS system
--
-- Run with: psql $DATABASE_URL < backend/migrations/001_voice_os_schema.sql
--
-- Tables:
--   - agents: AI voice agent configurations
--   - phone_numbers: Twilio phone number assignments
--   - call_sessions: Individual call records with transcripts and analytics

-- =====================================================
-- AGENTS TABLE
-- Stores AI voice agent configurations
-- =====================================================
CREATE TABLE IF NOT EXISTS voice_os_agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(100) NOT NULL,
  description TEXT,
  status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive')),

  -- Voice Configuration (ElevenLabs / OpenAI)
  voice_id VARCHAR(100) NOT NULL DEFAULT 'alloy', -- OpenAI: alloy, echo, fable, onyx, nova, shimmer
  voice_stability DECIMAL(3,2) DEFAULT 0.50, -- Lower = more expressive
  voice_similarity DECIMAL(3,2) DEFAULT 0.75,
  voice_style DECIMAL(3,2) DEFAULT 0.50, -- 0 = emotional, 1 = neutral

  -- LLM Configuration
  system_prompt TEXT NOT NULL,
  temperature DECIMAL(3,2) DEFAULT 0.7,
  max_tokens INTEGER DEFAULT 150, -- Short responses for voice

  -- Behavior Settings
  interrupt_enabled BOOLEAN DEFAULT true,
  filler_words_enabled BOOLEAN DEFAULT true, -- "um", "let me check"
  backchanneling_enabled BOOLEAN DEFAULT true, -- "mm-hmm", "I see"
  emotion_detection_enabled BOOLEAN DEFAULT true,

  -- Tools (JSON array of tool names)
  tools_allowed JSONB DEFAULT '["get_contact_by_phone", "create_lead", "schedule_appointment"]'::jsonb,

  -- Analytics (denormalized for speed)
  total_calls INTEGER DEFAULT 0,
  successful_calls INTEGER DEFAULT 0,
  avg_duration_seconds INTEGER DEFAULT 0,
  avg_satisfaction DECIMAL(3,2),

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for active agents lookup
CREATE INDEX IF NOT EXISTS idx_voice_os_agents_status ON voice_os_agents(status) WHERE status = 'active';

-- =====================================================
-- PHONE NUMBERS TABLE
-- Maps Twilio phone numbers to agents
-- =====================================================
CREATE TABLE IF NOT EXISTS voice_os_phone_numbers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  e164_number VARCHAR(20) UNIQUE NOT NULL, -- e.g., +18326482297
  friendly_name VARCHAR(100),
  agent_id UUID REFERENCES voice_os_agents(id) ON DELETE SET NULL,
  enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for enabled phone number lookups
CREATE INDEX IF NOT EXISTS idx_voice_os_phone_numbers_enabled ON voice_os_phone_numbers(enabled) WHERE enabled = true;

-- =====================================================
-- CALL SESSIONS TABLE
-- Records of individual voice calls with full analytics
-- =====================================================
CREATE TABLE IF NOT EXISTS voice_os_call_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_sid VARCHAR(100) UNIQUE NOT NULL, -- Twilio Call SID
  agent_id UUID REFERENCES voice_os_agents(id),

  -- Call Info
  direction VARCHAR(10) CHECK (direction IN ('inbound', 'outbound')),
  from_number VARCHAR(20) NOT NULL,
  to_number VARCHAR(20) NOT NULL,

  -- Status & Timing
  status VARCHAR(20) DEFAULT 'ringing',
  start_time TIMESTAMPTZ DEFAULT NOW(),
  answer_time TIMESTAMPTZ,
  end_time TIMESTAMPTZ,
  duration_seconds INTEGER,

  -- Contact Matching (links to existing CRM contacts)
  contact_id UUID, -- Reference to contacts table if matched
  contact_name VARCHAR(200),
  contact_email VARCHAR(255),

  -- AI Analysis
  transcript JSONB DEFAULT '[]'::jsonb, -- [{role, content, timestamp}]
  summary TEXT,
  sentiment VARCHAR(20), -- positive, neutral, negative
  emotion_detected VARCHAR(50), -- frustrated, happy, confused, etc.
  outcome VARCHAR(50), -- appointment_booked, lead_created, info_provided
  intent_detected VARCHAR(100),

  -- Actions Taken
  actions_taken JSONB DEFAULT '[]'::jsonb, -- [{action, timestamp, result}]

  -- Quality Metrics
  interruptions_count INTEGER DEFAULT 0,
  avg_response_latency_ms INTEGER,
  escalated BOOLEAN DEFAULT false,
  escalation_reason TEXT,

  -- Storage
  recording_url TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_status ON voice_os_call_sessions(status);
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_agent ON voice_os_call_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_contact ON voice_os_call_sessions(contact_id);
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_start_time ON voice_os_call_sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_outcome ON voice_os_call_sessions(outcome);
CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_from_number ON voice_os_call_sessions(from_number);

-- =====================================================
-- TRIGGERS (Auto-update agent stats on call completion)
-- =====================================================
CREATE OR REPLACE FUNCTION update_voice_os_agent_stats()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
    UPDATE voice_os_agents
    SET
      total_calls = total_calls + 1,
      successful_calls = CASE
        WHEN NEW.outcome IN ('appointment_booked', 'lead_created', 'info_provided')
        THEN successful_calls + 1
        ELSE successful_calls
      END,
      avg_duration_seconds = (
        (avg_duration_seconds * total_calls + COALESCE(NEW.duration_seconds, 0)) /
        (total_calls + 1)
      ),
      updated_at = NOW()
    WHERE id = NEW.agent_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS trigger_update_voice_os_agent_stats ON voice_os_call_sessions;

CREATE TRIGGER trigger_update_voice_os_agent_stats
AFTER UPDATE OF status ON voice_os_call_sessions
FOR EACH ROW
EXECUTE FUNCTION update_voice_os_agent_stats();

-- =====================================================
-- VIEWS (Performance monitoring)
-- =====================================================
CREATE OR REPLACE VIEW voice_os_agent_performance AS
SELECT
  a.id,
  a.name,
  a.status,
  a.total_calls,
  a.successful_calls,
  CASE
    WHEN a.total_calls > 0
    THEN ROUND((a.successful_calls::decimal / a.total_calls * 100), 1)
    ELSE 0
  END as success_rate_percent,
  a.avg_duration_seconds,
  a.avg_satisfaction,
  COUNT(cs.id) FILTER (WHERE cs.status IN ('ringing', 'in_progress')) as active_calls_now
FROM voice_os_agents a
LEFT JOIN voice_os_call_sessions cs ON a.id = cs.agent_id
GROUP BY a.id, a.name, a.status, a.total_calls, a.successful_calls,
         a.avg_duration_seconds, a.avg_satisfaction;

-- =====================================================
-- SEED DATA: Default AI Receptionist Agent
-- =====================================================
INSERT INTO voice_os_agents (
  name,
  description,
  status,
  voice_id,
  voice_stability,
  voice_similarity,
  system_prompt,
  temperature,
  max_tokens,
  interrupt_enabled,
  filler_words_enabled,
  backchanneling_enabled,
  emotion_detection_enabled,
  tools_allowed
)
VALUES (
  'Sam - AI Receptionist',
  'Friendly and professional AI receptionist for inbound calls',
  'active',
  'alloy',
  0.50,
  0.75,
  'You are Sam, a friendly and professional AI receptionist for a mortgage company.

Your role is to:
- Greet callers warmly and professionally
- Identify if they are existing clients or new prospects
- Understand their needs (new loan, refinance, loan status, etc.)
- Schedule appointments with loan officers
- Answer basic questions about the mortgage process
- Create leads for new prospects

Guidelines:
- Keep responses concise (under 3 sentences when possible)
- Be empathetic and patient
- If you cannot help, offer to transfer to a human
- Never provide specific rate quotes without proper qualification
- Always confirm important details like names, phone numbers, and appointment times',
  0.7,
  150,
  true,
  true,
  true,
  true,
  '["get_contact_by_phone", "create_lead", "update_lead_stage", "schedule_appointment", "check_availability", "create_task", "log_call_note", "get_loan_status", "escalate_to_human"]'::jsonb
)
ON CONFLICT DO NOTHING;

-- =====================================================
-- COMPLETED
-- =====================================================
-- Voice OS schema migration completed successfully!
--
-- Created tables:
--   - voice_os_agents: AI agent configurations
--   - voice_os_phone_numbers: Phone number to agent mapping
--   - voice_os_call_sessions: Call records with transcripts
--
-- Created views:
--   - voice_os_agent_performance: Real-time agent metrics
--
-- Created triggers:
--   - trigger_update_voice_os_agent_stats: Auto-update agent stats
--
-- Seeded:
--   - Default "Sam - AI Receptionist" agent
