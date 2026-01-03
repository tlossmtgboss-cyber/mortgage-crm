"""
Partner Recruiting Engine Migration
Creates tables for partner candidates, meetings, proposals, activities, notes, and assessments.
This mirrors the Employee Recruiting Engine but is for Loan Officers recruiting referral partners.
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Create all partner recruiting tables."""

    migration_sql = """
    -- =============================================================================
    -- PARTNER RECRUITING ENGINE TABLES
    -- =============================================================================

    -- =============================================================================
    -- PARTNER CANDIDATES TABLE (Main table for partner recruits)
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_candidates (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        owner_id INTEGER NOT NULL REFERENCES users(id),  -- LO who owns this recruit

        -- Basic Info
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        email VARCHAR(255) NOT NULL,
        phone VARCHAR(20),

        -- Partner Type
        partner_type VARCHAR(50) NOT NULL DEFAULT 'realtor',
        -- Types: realtor, financial_planner, cpa, estate_attorney, insurance_agent, title_agent, builder, other
        license_number VARCHAR(100),
        license_state VARCHAR(10),

        -- Business Info
        company_name VARCHAR(255),
        business_name VARCHAR(255),
        title VARCHAR(100),
        years_in_business INTEGER,
        website VARCHAR(255),

        -- Address
        street_address VARCHAR(255),
        city VARCHAR(100),
        state VARCHAR(50),
        zip_code VARCHAR(20),

        -- Source Tracking
        source VARCHAR(50),  -- retr, referral, networking, cold_outreach, event, website, linkedin
        source_detail VARCHAR(255),
        referrer_user_id INTEGER REFERENCES users(id),

        -- Pipeline Status
        status VARCHAR(30) DEFAULT 'new',
        -- Statuses: new, contacted, qualified, meeting_scheduled, met, proposal_sent, negotiating, onboarded, declined, inactive
        status_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status_changed_by INTEGER REFERENCES users(id),

        -- Assessment Scores (0-100 scale)
        production_volume DECIMAL(15,2),  -- Their annual business volume
        referral_potential_score FLOAT,   -- Estimated referral potential
        relationship_score FLOAT,         -- Relationship quality
        professionalism_score FLOAT,      -- Their business practices
        market_presence_score FLOAT,      -- Local market influence
        communication_score FLOAT,        -- Responsiveness
        overall_score FLOAT,              -- Weighted composite

        -- Qualification Data
        current_loan_partners JSONB DEFAULT '[]',  -- Lenders they currently work with
        avg_referrals_per_month INTEGER,
        preferred_loan_types JSONB DEFAULT '[]',   -- conventional, fha, va, jumbo, etc.
        target_client_demographics TEXT,
        geographic_focus JSONB DEFAULT '[]',       -- Areas they work in

        -- Communication Preferences
        preferred_contact_method VARCHAR(30),  -- phone, email, text
        best_contact_time VARCHAR(50),
        linkedin_url VARCHAR(255),

        -- Onboarding
        onboarded_at TIMESTAMP,
        referral_partner_id INTEGER,  -- Link when converted to ReferralPartner

        -- Notes
        notes TEXT,
        tags JSONB DEFAULT '[]',

        -- Soft delete
        is_active BOOLEAN DEFAULT true,

        -- Timestamps
        last_activity_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_partner_candidates_owner ON partner_candidates(owner_id);
    CREATE INDEX IF NOT EXISTS ix_partner_candidates_status ON partner_candidates(status);
    CREATE INDEX IF NOT EXISTS ix_partner_candidates_type ON partner_candidates(partner_type);
    CREATE INDEX IF NOT EXISTS ix_partner_candidates_active ON partner_candidates(is_active) WHERE is_active = true;

    -- Unique constraint: same LO can't have duplicate email
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uix_partner_candidates_owner_email'
        ) THEN
            CREATE UNIQUE INDEX uix_partner_candidates_owner_email
            ON partner_candidates(owner_id, email) WHERE is_active = true;
        END IF;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Unique index creation: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- PARTNER MEETINGS TABLE (Equivalent to mm_interviews)
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_meetings (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        partner_candidate_id INTEGER NOT NULL REFERENCES partner_candidates(id) ON DELETE CASCADE,

        -- Meeting Details
        meeting_type VARCHAR(30) DEFAULT 'coffee',
        -- Types: phone, video, coffee, lunch, office_visit, networking_event
        meeting_round INTEGER DEFAULT 1,
        title VARCHAR(200),

        -- Scheduling
        scheduled_at TIMESTAMP NOT NULL,
        duration_minutes INTEGER DEFAULT 30,
        timezone VARCHAR(50) DEFAULT 'America/New_York',
        location VARCHAR(255),
        meeting_link TEXT,
        calendar_event_id VARCHAR(255),

        -- Status
        status VARCHAR(30) DEFAULT 'scheduled',
        -- Statuses: scheduled, confirmed, completed, cancelled, no_show, rescheduled
        confirmation_sent_at TIMESTAMP,
        reminder_sent_at TIMESTAMP,

        -- Outcome (filled after meeting)
        outcome VARCHAR(50),
        -- Outcomes: very_positive, positive, neutral, negative, needs_followup
        next_steps TEXT,
        key_takeaways TEXT,
        objections TEXT,
        interest_level INTEGER,  -- 1-5 scale

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

    CREATE INDEX IF NOT EXISTS ix_partner_meetings_candidate ON partner_meetings(partner_candidate_id);
    CREATE INDEX IF NOT EXISTS ix_partner_meetings_scheduled ON partner_meetings(scheduled_at);
    CREATE INDEX IF NOT EXISTS ix_partner_meetings_status ON partner_meetings(status);

    -- =============================================================================
    -- PARTNER PROPOSALS TABLE (Equivalent to mm_offers)
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_proposals (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        partner_candidate_id INTEGER NOT NULL REFERENCES partner_candidates(id) ON DELETE CASCADE,

        -- Proposal Details
        proposal_number VARCHAR(50) UNIQUE,  -- PROP-2024-001
        proposal_type VARCHAR(50) DEFAULT 'standard',
        -- Types: standard, premium, custom, exclusive

        -- Value Proposition (JSONB for flexibility)
        referral_commission_structure JSONB DEFAULT '{}',
        -- e.g., {"type": "per_closed", "amount": 250, "description": "$250 per closed referral"}
        co_marketing_benefits JSONB DEFAULT '[]',
        -- e.g., ["Co-branded flyers", "Joint open house events", "Shared social media"]
        technology_access JSONB DEFAULT '[]',
        -- e.g., ["Client portal access", "Rate alerts", "Pre-approval letters"]
        exclusive_territory TEXT,
        additional_benefits TEXT,

        -- Status & Workflow
        status VARCHAR(30) DEFAULT 'draft',
        -- Statuses: draft, pending_approval, approved, sent, viewed, accepted, declined, expired, countered

        -- Approval (if needed)
        requires_approval BOOLEAN DEFAULT false,
        approved_by INTEGER REFERENCES users(id),
        approved_at TIMESTAMP,

        -- Sending
        sent_at TIMESTAMP,
        sent_by INTEGER REFERENCES users(id),
        viewed_at TIMESTAMP,
        expires_at TIMESTAMP,
        proposal_document_url TEXT,

        -- Response
        responded_at TIMESTAMP,
        response_notes TEXT,
        counter_proposal JSONB,

        -- Acceptance
        accepted_at TIMESTAMP,
        partnership_agreement_url TEXT,

        -- Decline
        declined_at TIMESTAMP,
        declined_reason VARCHAR(255),

        -- Internal
        internal_notes TEXT,

        -- Metadata
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_partner_proposals_candidate ON partner_proposals(partner_candidate_id);
    CREATE INDEX IF NOT EXISTS ix_partner_proposals_status ON partner_proposals(status);

    -- =============================================================================
    -- PARTNER ACTIVITIES TABLE (Activity log)
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_activities (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        partner_candidate_id INTEGER NOT NULL REFERENCES partner_candidates(id) ON DELETE CASCADE,

        -- Activity Details
        activity_type VARCHAR(50) NOT NULL,
        -- Types: status_change, email_sent, call_made, call_received, sms_sent,
        --        meeting_scheduled, meeting_completed, meeting_cancelled,
        --        proposal_created, proposal_sent, proposal_viewed, proposal_accepted, proposal_declined,
        --        note_added, assessment_updated, onboarded, linkedin_connected
        description TEXT,
        metadata JSONB DEFAULT '{}',

        -- Associated entities
        meeting_id INTEGER REFERENCES partner_meetings(id),
        proposal_id INTEGER REFERENCES partner_proposals(id),

        -- Actor
        performed_by INTEGER REFERENCES users(id),
        is_automated BOOLEAN DEFAULT false,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
    );

    CREATE INDEX IF NOT EXISTS ix_partner_activities_candidate ON partner_activities(partner_candidate_id);
    CREATE INDEX IF NOT EXISTS ix_partner_activities_created ON partner_activities(created_at);
    CREATE INDEX IF NOT EXISTS ix_partner_activities_type ON partner_activities(activity_type);

    -- =============================================================================
    -- PARTNER NOTES TABLE
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_notes (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        partner_candidate_id INTEGER NOT NULL REFERENCES partner_candidates(id) ON DELETE CASCADE,

        -- Note Content
        note_type VARCHAR(30) DEFAULT 'general',
        -- Types: general, meeting, qualification, objection, follow_up, call, relationship
        content TEXT NOT NULL,
        is_private BOOLEAN DEFAULT false,
        is_pinned BOOLEAN DEFAULT false,

        -- Author
        created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_partner_notes_candidate ON partner_notes(partner_candidate_id);

    -- =============================================================================
    -- PARTNER ASSESSMENTS TABLE (Partner-specific scoring)
    -- =============================================================================
    CREATE TABLE IF NOT EXISTS partner_assessments (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id),
        partner_candidate_id INTEGER NOT NULL REFERENCES partner_candidates(id) ON DELETE CASCADE,

        -- Assessment Scores (0-100 scale)
        production_score FLOAT,       -- Based on their business volume
        referral_potential_score FLOAT,  -- Estimated referral capacity
        relationship_score FLOAT,     -- How well we connect
        professionalism_score FLOAT,  -- Their business practices
        market_presence_score FLOAT,  -- Local market influence
        communication_score FLOAT,    -- Responsiveness and clarity

        -- Overall (weighted average)
        overall_score FLOAT,
        overall_grade VARCHAR(2),  -- A+, A, A-, B+, B, B-, C+, C, C-, D, F

        -- Breakdown (for detailed view)
        score_breakdown JSONB DEFAULT '{}',

        -- AI Analysis
        ai_analysis JSONB,
        ai_analysis_run_at TIMESTAMP,
        strengths JSONB DEFAULT '[]',
        concerns JSONB DEFAULT '[]',
        talking_points JSONB DEFAULT '[]',
        recommended_approach TEXT,

        -- Manual override
        scores_overridden BOOLEAN DEFAULT false,
        override_reason TEXT,
        override_by INTEGER REFERENCES users(id),
        override_at TIMESTAMP,

        -- Metadata
        assessed_by INTEGER REFERENCES users(id),
        assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE UNIQUE INDEX IF NOT EXISTS uix_partner_assessments_candidate
    ON partner_assessments(partner_candidate_id);

    CREATE INDEX IF NOT EXISTS ix_partner_assessments_score ON partner_assessments(overall_score);

    -- =============================================================================
    -- TRIGGER: Auto-update updated_at timestamps
    -- =============================================================================
    DO $$
    BEGIN
        -- Partner Candidates
        DROP TRIGGER IF EXISTS update_partner_candidates_updated_at ON partner_candidates;
        CREATE TRIGGER update_partner_candidates_updated_at
            BEFORE UPDATE ON partner_candidates
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Partner Meetings
        DROP TRIGGER IF EXISTS update_partner_meetings_updated_at ON partner_meetings;
        CREATE TRIGGER update_partner_meetings_updated_at
            BEFORE UPDATE ON partner_meetings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Partner Proposals
        DROP TRIGGER IF EXISTS update_partner_proposals_updated_at ON partner_proposals;
        CREATE TRIGGER update_partner_proposals_updated_at
            BEFORE UPDATE ON partner_proposals
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Partner Notes
        DROP TRIGGER IF EXISTS update_partner_notes_updated_at ON partner_notes;
        CREATE TRIGGER update_partner_notes_updated_at
            BEFORE UPDATE ON partner_notes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

        -- Partner Assessments
        DROP TRIGGER IF EXISTS update_partner_assessments_updated_at ON partner_assessments;
        CREATE TRIGGER update_partner_assessments_updated_at
            BEFORE UPDATE ON partner_assessments
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Trigger creation: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- GENERATE PROPOSAL NUMBER FUNCTION
    -- =============================================================================
    CREATE OR REPLACE FUNCTION generate_partner_proposal_number()
    RETURNS TRIGGER AS $$
    DECLARE
        year_str TEXT;
        next_num INTEGER;
    BEGIN
        IF NEW.proposal_number IS NULL THEN
            year_str := TO_CHAR(CURRENT_DATE, 'YYYY');
            SELECT COALESCE(MAX(
                CAST(SUBSTRING(proposal_number FROM 'PROP-' || year_str || '-([0-9]+)') AS INTEGER)
            ), 0) + 1
            INTO next_num
            FROM partner_proposals
            WHERE proposal_number LIKE 'PROP-' || year_str || '-%';

            NEW.proposal_number := 'PROP-' || year_str || '-' || LPAD(next_num::TEXT, 4, '0');
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS generate_partner_proposal_number_trigger ON partner_proposals;
    CREATE TRIGGER generate_partner_proposal_number_trigger
        BEFORE INSERT ON partner_proposals
        FOR EACH ROW EXECUTE FUNCTION generate_partner_proposal_number();

    -- =============================================================================
    -- ADD referral_partner_id FK CONSTRAINT (if referral_partners table exists)
    -- =============================================================================
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'referral_partners') THEN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_partner_candidates_referral_partner'
            ) THEN
                ALTER TABLE partner_candidates
                ADD CONSTRAINT fk_partner_candidates_referral_partner
                FOREIGN KEY (referral_partner_id) REFERENCES referral_partners(id);
            END IF;
        END IF;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'FK constraint creation: %', SQLERRM;
    END $$;
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()
        logger.info("Partner Recruiting tables created successfully")

    return {"message": "Partner Recruiting migration completed successfully"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
