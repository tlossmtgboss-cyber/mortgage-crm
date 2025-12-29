"""
Master Manager Platform - Phase 2: Recruiting Engine Migration
Creates tables for job postings, candidates, interviews, offers, and activity tracking.
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Create all recruiting tables for Phase 2."""

    migration_sql = """
    -- =============================================================================
    -- PHASE 2: RECRUITING ENGINE TABLES
    -- =============================================================================

    -- mm_job_postings already exists from Phase 1, but let's ensure it has all columns
    DO $$
    BEGIN
        -- Add any missing columns to job postings
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_job_postings' AND column_name = 'views') THEN
            ALTER TABLE mm_job_postings ADD COLUMN views INTEGER DEFAULT 0;
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_job_postings' AND column_name = 'applications') THEN
            ALTER TABLE mm_job_postings ADD COLUMN applications INTEGER DEFAULT 0;
        END IF;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Job postings columns check: %', SQLERRM;
    END $$;

    -- mm_candidates already exists from Phase 1, ensure all columns exist
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_candidates' AND column_name = 'last_activity_at') THEN
            ALTER TABLE mm_candidates ADD COLUMN last_activity_at TIMESTAMP;
        END IF;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Candidates columns check: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- INTERVIEWS TABLE
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS mm_interviews (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,

        -- Interview Details
        interview_type VARCHAR(30) DEFAULT 'video',
        interview_round INTEGER DEFAULT 1,
        title VARCHAR(200),

        -- Scheduling
        scheduled_at TIMESTAMP NOT NULL,
        duration_minutes INTEGER DEFAULT 30,
        timezone VARCHAR(50) DEFAULT 'America/New_York',
        location VARCHAR(255),
        meeting_link TEXT,
        calendar_event_id VARCHAR(255),

        -- Interviewers
        interviewer_user_ids JSONB DEFAULT '[]'::jsonb,
        primary_interviewer_id INTEGER REFERENCES users(id),

        -- Status
        status VARCHAR(30) DEFAULT 'scheduled',
        confirmation_sent_at TIMESTAMP,
        reminder_sent_at TIMESTAMP,

        -- Feedback
        feedback JSONB DEFAULT '{}'::jsonb,
        overall_score FLOAT,
        recommendation VARCHAR(30),
        decision_notes TEXT,

        -- Completed
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        no_show_reason VARCHAR(255),
        cancellation_reason VARCHAR(255),

        -- Metadata
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_mm_interview_candidate ON mm_interviews(candidate_id);
    CREATE INDEX IF NOT EXISTS ix_mm_interview_scheduled ON mm_interviews(scheduled_at);
    CREATE INDEX IF NOT EXISTS ix_mm_interview_status ON mm_interviews(status);

    -- =============================================================================
    -- OFFERS TABLE
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS mm_offers (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,
        job_posting_id INTEGER REFERENCES mm_job_postings(id),

        -- Offer Details
        offer_number VARCHAR(50) UNIQUE,
        role_title VARCHAR(200) NOT NULL,
        role_definition_id INTEGER REFERENCES mm_role_definitions(id),
        department VARCHAR(100),
        reports_to_user_id INTEGER REFERENCES users(id),

        -- Compensation
        salary_amount INTEGER NOT NULL,
        salary_type VARCHAR(20) DEFAULT 'salary',
        bonus_amount INTEGER,
        bonus_type VARCHAR(30),
        commission_structure JSONB,
        equity_amount INTEGER,
        equity_type VARCHAR(30),

        -- Benefits
        benefits_summary TEXT,
        pto_days INTEGER,
        health_insurance BOOLEAN DEFAULT true,
        retirement_match_pct FLOAT,

        -- Terms
        employment_type VARCHAR(30) DEFAULT 'full_time',
        start_date DATE,
        is_remote BOOLEAN DEFAULT false,
        work_location VARCHAR(255),

        -- Status & Workflow
        status VARCHAR(30) DEFAULT 'draft',
        approval_chain JSONB DEFAULT '[]'::jsonb,
        approved_by INTEGER REFERENCES users(id),
        approved_at TIMESTAMP,

        -- Sending
        sent_at TIMESTAMP,
        sent_by INTEGER REFERENCES users(id),
        viewed_at TIMESTAMP,
        expires_at TIMESTAMP,
        offer_letter_url TEXT,

        -- Response
        responded_at TIMESTAMP,
        response_notes TEXT,

        -- Negotiation
        negotiation_history JSONB DEFAULT '[]'::jsonb,
        counter_offer_count INTEGER DEFAULT 0,

        -- Acceptance
        accepted_at TIMESTAMP,
        signature_url TEXT,
        onboarding_started BOOLEAN DEFAULT false,

        -- Decline/Withdrawal
        declined_at TIMESTAMP,
        declined_reason VARCHAR(100),
        declined_notes TEXT,
        withdrawn_at TIMESTAMP,
        withdrawn_reason TEXT,

        -- Internal Notes
        internal_notes TEXT,

        -- Metadata
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_mm_offer_candidate ON mm_offers(candidate_id);
    CREATE INDEX IF NOT EXISTS ix_mm_offer_status ON mm_offers(status);
    CREATE INDEX IF NOT EXISTS ix_mm_offer_number ON mm_offers(offer_number);

    -- =============================================================================
    -- CANDIDATE ACTIVITIES TABLE
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS mm_candidate_activities (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,

        -- Activity Details
        activity_type VARCHAR(50) NOT NULL,
        description TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,

        -- Associated entities
        interview_id INTEGER REFERENCES mm_interviews(id),
        offer_id INTEGER REFERENCES mm_offers(id),

        -- Actor
        performed_by INTEGER REFERENCES users(id),
        is_automated BOOLEAN DEFAULT false,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_mm_cand_activity_candidate ON mm_candidate_activities(candidate_id);
    CREATE INDEX IF NOT EXISTS ix_mm_cand_activity_created ON mm_candidate_activities(created_at);
    CREATE INDEX IF NOT EXISTS ix_mm_cand_activity_type ON mm_candidate_activities(activity_type);

    -- =============================================================================
    -- CANDIDATE NOTES TABLE
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS mm_candidate_notes (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        candidate_id INTEGER NOT NULL REFERENCES mm_candidates(id) ON DELETE CASCADE,

        -- Note Content
        note_type VARCHAR(30) DEFAULT 'general',
        content TEXT NOT NULL,
        is_private BOOLEAN DEFAULT false,

        -- Author
        created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_mm_cand_note_candidate ON mm_candidate_notes(candidate_id);

    -- =============================================================================
    -- TRIGGER: Auto-update updated_at timestamps
    -- =============================================================================
    DO $$
    BEGIN
        -- Interviews
        DROP TRIGGER IF EXISTS update_mm_interviews_updated_at ON mm_interviews;
        CREATE TRIGGER update_mm_interviews_updated_at
            BEFORE UPDATE ON mm_interviews
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Offers
        DROP TRIGGER IF EXISTS update_mm_offers_updated_at ON mm_offers;
        CREATE TRIGGER update_mm_offers_updated_at
            BEFORE UPDATE ON mm_offers
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Notes
        DROP TRIGGER IF EXISTS update_mm_candidate_notes_updated_at ON mm_candidate_notes;
        CREATE TRIGGER update_mm_candidate_notes_updated_at
            BEFORE UPDATE ON mm_candidate_notes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Trigger creation: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- GENERATE OFFER NUMBER FUNCTION
    -- =============================================================================
    CREATE OR REPLACE FUNCTION generate_offer_number()
    RETURNS TRIGGER AS $$
    DECLARE
        year_str TEXT;
        next_num INTEGER;
    BEGIN
        IF NEW.offer_number IS NULL THEN
            year_str := TO_CHAR(CURRENT_DATE, 'YYYY');
            SELECT COALESCE(MAX(
                CAST(SUBSTRING(offer_number FROM 'OFF-' || year_str || '-([0-9]+)') AS INTEGER)
            ), 0) + 1
            INTO next_num
            FROM mm_offers
            WHERE offer_number LIKE 'OFF-' || year_str || '-%';

            NEW.offer_number := 'OFF-' || year_str || '-' || LPAD(next_num::TEXT, 4, '0');
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS generate_offer_number_trigger ON mm_offers;
    CREATE TRIGGER generate_offer_number_trigger
        BEFORE INSERT ON mm_offers
        FOR EACH ROW EXECUTE FUNCTION generate_offer_number();
    """

    with engine.connect() as conn:
        # Execute migration
        conn.execute(text(migration_sql))
        conn.commit()
        logger.info("Phase 2 Recruiting tables created successfully")

    return {"message": "Recruiting migration completed successfully"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
