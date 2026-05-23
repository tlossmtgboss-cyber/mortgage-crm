"""
Migration: Add AI Call Monitoring System Tables

This migration creates all tables needed for the Call Monitoring AI System:
- call_sessions: Central session tracking
- call_participants: Multi-party call support
- agent_runs: AI agent execution tracking
- agent_events: Append-only audit log
- call_artifacts: Generated outputs with approval workflow
- intake_field_updates: 1003 field extraction
- risk_flags: Underwriter risk identification

Run with: python -m migrations.add_call_monitoring_system
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from sqlalchemy import text


def run_migration():
    """Run the call monitoring system migration."""
    print("=" * 60)
    print("AI Call Monitoring System Migration")
    print("=" * 60)

    sql_statements = """
    -- =============================================================================
    -- AI CALL MONITORING SYSTEM TABLES
    -- =============================================================================

    -- 1. Call Sessions - Central session tracking
    CREATE TABLE IF NOT EXISTS call_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        -- Capture source
        capture_mode VARCHAR(30) NOT NULL,
        -- Note: FK to ci_call_recordings removed - run CI platform migration first
        recording_id UUID,

        -- Linked entities
        loan_id UUID,
        lead_id UUID,
        contact_id UUID,
        user_id UUID REFERENCES users(id),

        -- Session status
        status VARCHAR(30) NOT NULL DEFAULT 'active',

        -- Transcript state
        transcript_state VARCHAR(30) DEFAULT 'pending',
        full_transcript TEXT,
        transcript_word_count INTEGER,

        -- Participants summary (for quick display)
        participants JSONB DEFAULT '[]'::jsonb,

        -- Call metadata
        metadata JSONB DEFAULT '{}'::jsonb,
        tags TEXT[] DEFAULT ARRAY[]::TEXT[],

        -- Confidence (for ambient mic mode)
        overall_confidence NUMERIC(5,4),

        -- Timing
        started_at TIMESTAMPTZ NOT NULL,
        ended_at TIMESTAMPTZ,
        duration_seconds INTEGER,

        -- Processing timing
        processing_started_at TIMESTAMPTZ,
        processing_completed_at TIMESTAMPTZ,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Add organization_id if table already existed without it
    ALTER TABLE call_sessions ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_call_sessions_status ON call_sessions(status);
    CREATE INDEX IF NOT EXISTS ix_call_sessions_org_id ON call_sessions(organization_id);
    CREATE INDEX IF NOT EXISTS ix_call_sessions_loan_id ON call_sessions(loan_id);
    CREATE INDEX IF NOT EXISTS ix_call_sessions_lead_id ON call_sessions(lead_id);
    CREATE INDEX IF NOT EXISTS ix_call_sessions_started_at ON call_sessions(started_at);
    CREATE INDEX IF NOT EXISTS ix_call_sessions_user_id ON call_sessions(user_id);

    -- 2. Call Participants - Multi-party tracking
    CREATE TABLE IF NOT EXISTS call_participants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,

        -- Participant identification
        role VARCHAR(30) NOT NULL,
        name VARCHAR(200),
        phone VARCHAR(20),
        email VARCHAR(255),

        -- Speaker diarization
        speaker_label VARCHAR(50),

        -- Link to existing entities
        contact_id UUID,
        user_id UUID REFERENCES users(id),

        -- Participation timing
        joined_at TIMESTAMPTZ,
        left_at TIMESTAMPTZ,

        -- Talk metrics
        talk_time_seconds INTEGER,
        word_count INTEGER,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE call_participants ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_call_participants_session ON call_participants(session_id);
    CREATE INDEX IF NOT EXISTS ix_call_participants_role ON call_participants(role);

    -- 3. Agent Runs - AI agent execution tracking
    CREATE TABLE IF NOT EXISTS agent_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,

        -- Agent identification
        agent_type VARCHAR(30) NOT NULL,

        -- Execution status
        status VARCHAR(30) NOT NULL DEFAULT 'pending',

        -- Input context provided to agent
        input_context JSONB DEFAULT '{}'::jsonb,

        -- Generated artifacts summary
        artifacts JSONB DEFAULT '[]'::jsonb,

        -- Raw LLM output (for debugging/audit)
        raw_output TEXT,

        -- Processing metrics
        model_used VARCHAR(100),
        tokens_used INTEGER,
        input_tokens INTEGER,
        output_tokens INTEGER,
        processing_time_ms INTEGER,
        cost_cents INTEGER,

        -- Error tracking
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,

        -- Timing
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_agent_runs_session ON agent_runs(session_id);
    CREATE INDEX IF NOT EXISTS ix_agent_runs_type ON agent_runs(agent_type);
    CREATE INDEX IF NOT EXISTS ix_agent_runs_status ON agent_runs(status);

    -- 4. Agent Events - Append-only audit log
    CREATE TABLE IF NOT EXISTS agent_events (
        id BIGSERIAL PRIMARY KEY,
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
        run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,

        -- Event identification
        event_type VARCHAR(50) NOT NULL,
        agent_type VARCHAR(30),

        -- Event data
        payload JSONB DEFAULT '{}'::jsonb,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timing
        event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        transcript_timestamp_ms INTEGER
    );

    ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_agent_events_session ON agent_events(session_id);
    CREATE INDEX IF NOT EXISTS ix_agent_events_run ON agent_events(run_id);
    CREATE INDEX IF NOT EXISTS ix_agent_events_type ON agent_events(event_type);
    CREATE INDEX IF NOT EXISTS ix_agent_events_time ON agent_events(event_time);

    -- 5. Call Artifacts - Generated outputs with approval workflow
    CREATE TABLE IF NOT EXISTS call_artifacts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
        run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,

        -- Artifact type
        artifact_type VARCHAR(50) NOT NULL,

        -- Content
        title VARCHAR(500),
        content TEXT,
        structured_data JSONB DEFAULT '{}'::jsonb,

        -- Approval workflow
        approval_status VARCHAR(30) DEFAULT 'pending',
        requires_approval BOOLEAN DEFAULT TRUE,
        approved_by UUID REFERENCES users(id),
        approved_at TIMESTAMPTZ,
        rejection_reason TEXT,

        -- Execution status (for actionable artifacts like tasks)
        execution_status VARCHAR(30) DEFAULT 'pending',
        executed_at TIMESTAMPTZ,
        execution_result JSONB,

        -- Link to created entity (after execution)
        linked_entity_type VARCHAR(50),
        linked_entity_id UUID,

        -- Confidence and evidence
        confidence NUMERIC(5,4),
        source_evidence TEXT,
        source_timestamp_ms INTEGER,

        -- Metadata
        metadata JSONB DEFAULT '{}'::jsonb,
        priority VARCHAR(20),

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE call_artifacts ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_call_artifacts_session ON call_artifacts(session_id);
    CREATE INDEX IF NOT EXISTS ix_call_artifacts_type ON call_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS ix_call_artifacts_approval ON call_artifacts(approval_status);
    CREATE INDEX IF NOT EXISTS ix_call_artifacts_linked ON call_artifacts(linked_entity_type, linked_entity_id);

    -- 6. Intake Field Updates - 1003 field extraction
    CREATE TABLE IF NOT EXISTS intake_field_updates (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
        artifact_id UUID REFERENCES call_artifacts(id) ON DELETE SET NULL,

        -- Target entity
        entity_type VARCHAR(50) NOT NULL,
        entity_id UUID NOT NULL,

        -- Field identification
        field_name VARCHAR(200) NOT NULL,
        field_path VARCHAR(500),

        -- Values
        current_value JSONB,
        proposed_value JSONB,

        -- Confidence
        confidence NUMERIC(5,4),
        evidence_text TEXT,

        -- Conflict handling
        has_conflict BOOLEAN DEFAULT FALSE,
        conflict_resolution VARCHAR(50),

        -- Status
        status VARCHAR(30) DEFAULT 'pending',
        applied_by UUID REFERENCES users(id),
        applied_at TIMESTAMPTZ,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE intake_field_updates ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_intake_field_session ON intake_field_updates(session_id);
    CREATE INDEX IF NOT EXISTS ix_intake_field_entity ON intake_field_updates(entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS ix_intake_field_status ON intake_field_updates(status);

    -- 7. Call Risk Flags - Underwriter risk identification from calls
    -- (Named call_risk_flags to avoid conflict with portal risk_flags table)
    CREATE TABLE IF NOT EXISTS call_risk_flags (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id UUID NOT NULL REFERENCES call_sessions(id) ON DELETE CASCADE,
        artifact_id UUID REFERENCES call_artifacts(id) ON DELETE SET NULL,

        -- Risk classification
        risk_category VARCHAR(50) NOT NULL,
        severity VARCHAR(20) NOT NULL,

        -- Content
        title VARCHAR(500) NOT NULL,
        description TEXT,
        evidence TEXT,
        recommended_action TEXT,

        -- Condition suggestion
        condition_type VARCHAR(50),

        -- Status
        status VARCHAR(30) DEFAULT 'open',
        resolution_notes TEXT,
        resolved_by UUID REFERENCES users(id),
        resolved_at TIMESTAMPTZ,

        -- Links
        loan_id UUID,
        condition_id UUID,

        -- Multi-tenant
        organization_id INTEGER,

        -- Timestamps
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    ALTER TABLE call_risk_flags ADD COLUMN IF NOT EXISTS organization_id INTEGER;

    CREATE INDEX IF NOT EXISTS ix_call_risk_flags_session ON call_risk_flags(session_id);
    CREATE INDEX IF NOT EXISTS ix_call_risk_flags_category ON call_risk_flags(risk_category);
    CREATE INDEX IF NOT EXISTS ix_call_risk_flags_severity ON call_risk_flags(severity);
    CREATE INDEX IF NOT EXISTS ix_call_risk_flags_loan ON call_risk_flags(loan_id);
    CREATE INDEX IF NOT EXISTS ix_call_risk_flags_status ON call_risk_flags(status);

    -- =============================================================================
    -- TRIGGER FOR UPDATED_AT
    -- =============================================================================

    -- Create trigger function if it doesn't exist
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ language 'plpgsql';

    -- Add triggers to all tables with updated_at
    DROP TRIGGER IF EXISTS update_call_sessions_updated_at ON call_sessions;
    CREATE TRIGGER update_call_sessions_updated_at
        BEFORE UPDATE ON call_sessions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    DROP TRIGGER IF EXISTS update_agent_runs_updated_at ON agent_runs;
    CREATE TRIGGER update_agent_runs_updated_at
        BEFORE UPDATE ON agent_runs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    DROP TRIGGER IF EXISTS update_call_artifacts_updated_at ON call_artifacts;
    CREATE TRIGGER update_call_artifacts_updated_at
        BEFORE UPDATE ON call_artifacts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    DROP TRIGGER IF EXISTS update_intake_field_updates_updated_at ON intake_field_updates;
    CREATE TRIGGER update_intake_field_updates_updated_at
        BEFORE UPDATE ON intake_field_updates
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

    DROP TRIGGER IF EXISTS update_risk_flags_updated_at ON risk_flags;
    CREATE TRIGGER update_risk_flags_updated_at
        BEFORE UPDATE ON risk_flags
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """

    # Split and execute statements
    statements = [s.strip() for s in sql_statements.split(';') if s.strip()]

    with engine.connect() as conn:
        with conn.begin():
            success_count = 0
            error_count = 0

            for i, stmt in enumerate(statements):
                if not stmt or stmt.startswith('--'):
                    continue
                conn.execute(text("SAVEPOINT call_monitor_stmt"))
                try:
                    conn.execute(text(stmt))
                    conn.execute(text("RELEASE SAVEPOINT call_monitor_stmt"))
                    success_count += 1
                    if 'CREATE TABLE' in stmt:
                        table_name = stmt.split('CREATE TABLE IF NOT EXISTS')[1].split('(')[0].strip() if 'IF NOT EXISTS' in stmt else 'unknown'
                        print(f"  ✓ Created table: {table_name}")
                except Exception as e:
                    conn.execute(text("ROLLBACK TO SAVEPOINT call_monitor_stmt"))
                    error_msg = str(e)
                    if 'already exists' in error_msg.lower():
                        print(f"  ⊘ Skipped (exists): statement {i+1}")
                    else:
                        error_count += 1
                        print(f"  ✗ Error in statement {i+1}: {error_msg[:100]}")

    print("\n" + "=" * 60)
    print(f"Migration completed: {success_count} statements succeeded, {error_count} errors")
    print("=" * 60)

    return error_count == 0


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
