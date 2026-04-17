-- =============================================================================
-- PERENNIA AI — Recording Consent Gate
-- Migration: Add consent tracking fields to call_sessions
-- =============================================================================

-- Add consent tracking columns to call_sessions
ALTER TABLE call_sessions
    ADD COLUMN IF NOT EXISTS recording_consent_status VARCHAR(20)
        NOT NULL DEFAULT 'pending'
        CHECK (recording_consent_status IN ('pending', 'playing', 'disclosed', 'skipped', 'failed')),
    ADD COLUMN IF NOT EXISTS consent_requirement VARCHAR(20)
        CHECK (consent_requirement IN ('required', 'recommended', 'waived')),
    ADD COLUMN IF NOT EXISTS consent_disclosed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS consent_disclosure_method VARCHAR(20)
        CHECK (consent_disclosure_method IN ('audio_playback', 'tts_fallback', 'manual_verbal')),
    ADD COLUMN IF NOT EXISTS borrower_state VARCHAR(2),
    ADD COLUMN IF NOT EXISTS is_two_party_state BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS consent_override_by UUID,
    ADD COLUMN IF NOT EXISTS consent_override_at TIMESTAMPTZ;

-- Index for compliance auditing
CREATE INDEX IF NOT EXISTS idx_call_sessions_consent_status
    ON call_sessions(recording_consent_status);

CREATE INDEX IF NOT EXISTS idx_call_sessions_two_party
    ON call_sessions(is_two_party_state) WHERE is_two_party_state = true;

-- Add consent config column to organizations table
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS recording_consent_config JSONB
        NOT NULL DEFAULT '{
            "always_disclose": true,
            "disclosure_audio_url": null,
            "default_disclosure_url": "https://perennia-assets.s3.amazonaws.com/audio/recording-disclosure.wav",
            "fallback_to_tts": true,
            "tts_disclosure_text": "This call is now being recorded for quality and compliance purposes.",
            "tts_voice": "female",
            "tts_language": "en-US"
        }'::jsonb;

-- Compliance audit view: shows all calls and their consent status
CREATE OR REPLACE VIEW v_recording_consent_audit AS
SELECT
    cs.id AS session_id,
    cs.loan_officer_id,
    cs.contact_id,
    cs.borrower_state,
    cs.is_two_party_state,
    cs.recording_consent_status,
    cs.consent_requirement,
    cs.consent_disclosure_method,
    cs.consent_disclosed_at,
    cs.consent_override_by,
    cs.created_at AS call_started_at,
    CASE
        WHEN cs.is_two_party_state AND cs.recording_consent_status NOT IN ('disclosed', 'skipped')
        THEN true
        ELSE false
    END AS potential_violation,
    CASE
        WHEN cs.consent_disclosed_at IS NOT NULL AND cs.created_at IS NOT NULL
        THEN EXTRACT(EPOCH FROM (cs.consent_disclosed_at - cs.created_at))
        ELSE NULL
    END AS seconds_to_disclosure
FROM call_sessions cs
WHERE cs.recording_consent_status IS NOT NULL
ORDER BY cs.created_at DESC;
