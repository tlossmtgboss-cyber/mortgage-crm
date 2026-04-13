-- ============================================================
-- Migration: 0XX_voice_profiles.sql
-- Perennia AI — Voice Profile Schema
-- ============================================================
-- Run this via Alembic or your migration runner.
-- Requires: pgvector extension already installed on the DB.
-- ============================================================

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- ── voice_profiles ────────────────────────────────────────────
-- Stores the compiled speaker embedding for each enrolled user.
-- One row per user. Upserted on re-enrollment.
CREATE TABLE IF NOT EXISTS voice_profiles (
    id              SERIAL      PRIMARY KEY,
    user_id         INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    embedding       vector(256),                          -- resemblyzer d-vector, L2-normalised
    samples_count   INT         NOT NULL DEFAULT 0,       -- how many samples contributed
    enrolled_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_voice_profiles_user UNIQUE (user_id)
);

-- Index for cosine similarity search (used in verify + multi-tenant matching)
CREATE INDEX IF NOT EXISTS idx_voice_profiles_embedding
    ON voice_profiles
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── voice_samples ─────────────────────────────────────────────
-- Raw audio sample metadata. Audio files live in S3/R2.
-- Rows are retained for 90 days then purged by a scheduled job.
CREATE TABLE IF NOT EXISTS voice_samples (
    id          SERIAL      PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt_id   TEXT        NOT NULL,     -- matches VoicePrompt.id in mobile
    category    TEXT        NOT NULL      CHECK (category IN ('intro','professional','natural','numeric','emotional')),
    s3_key      TEXT        NOT NULL,     -- object key in S3/R2 bucket
    duration_s  FLOAT,                    -- audio duration in seconds
    processed   BOOLEAN     NOT NULL DEFAULT FALSE,   -- TRUE after embedding computed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voice_samples_user_id  ON voice_samples (user_id);
CREATE INDEX IF NOT EXISTS idx_voice_samples_processed ON voice_samples (processed) WHERE processed = FALSE;

-- ── updated_at trigger ────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_voice_profiles_updated_at ON voice_profiles;
CREATE TRIGGER trg_voice_profiles_updated_at
    BEFORE UPDATE ON voice_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── Audit log integration ─────────────────────────────────────
-- If you're using the Perennia audit_log table, this view surfaces
-- voice-profile events in the SOC 2 compliance dashboard.
CREATE OR REPLACE VIEW v_voice_profile_audit AS
SELECT
    vp.user_id,
    u.email,
    u.full_name,
    vp.enrolled_at,
    vp.samples_count,
    vp.updated_at  AS last_updated,
    CASE
        WHEN vp.enrolled_at IS NOT NULL THEN 'enrolled'
        ELSE 'pending'
    END AS enrollment_status
FROM voice_profiles vp
JOIN users u ON u.id = vp.user_id;

-- ── ENV variables required in Railway ────────────────────────
-- VOICE_SAMPLES_S3_BUCKET   = perennia-voice-samples
-- AWS_ACCESS_KEY_ID         = (your key)
-- AWS_SECRET_ACCESS_KEY     = (your secret)
-- S3_ENDPOINT_URL           = https://<account>.r2.cloudflarestorage.com  (if using R2)
-- VOICE_ENCODER_DEVICE      = cpu   (or 'cuda' if GPU available)
