"""
Migration: Add Recruiting Workflow CRM System
Creates comprehensive tables for multi-year relationship development with LOs and Realtors.

Features:
- Multi-year relationship tracking with automated stage progression
- Timing intelligence via signal detection + scoring engine
- Mutual connection graph for warm intro pathways
- Objection taxonomy to tailor future messaging
- Contact preference learning (best channel + time-of-day per person)
- Playbook automation for high-intent moments
- Cadence system for automated nurture sequences
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")


def run_migration():
    engine = create_engine(DATABASE_URL)

    migration_sql = """
    -- =============================================================================
    -- RECRUITING WORKFLOW CRM - COMPREHENSIVE SCHEMA
    -- =============================================================================

    -- =============================================================================
    -- ENUMS
    -- =============================================================================

    -- Person types (LO vs Realtor)
    DO $$ BEGIN
        CREATE TYPE rw_person_type AS ENUM ('LOAN_OFFICER', 'REALTOR');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Relationship stage (multi-year funnel)
    DO $$ BEGIN
        CREATE TYPE rw_relationship_stage AS ENUM (
            'DISCOVERED', 'CONNECTED', 'NURTURING', 'WARMING', 'ACTIVE_CONVERSATION',
            'EVALUATING_SWITCH', 'COMMITTED', 'ONBOARDING', 'ACTIVE_PARTNER', 'DORMANT', 'DO_NOT_CONTACT'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Communication channels
    DO $$ BEGIN
        CREATE TYPE rw_comm_channel AS ENUM (
            'SMS', 'EMAIL', 'PHONE', 'LINKEDIN', 'INSTAGRAM', 'FACEBOOK', 'IN_PERSON', 'DIRECT_MAIL'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Event types for orchestration
    DO $$ BEGIN
        CREATE TYPE rw_event_type AS ENUM (
            'PERSON_CREATED', 'PERSON_UPDATED',
            'OUTBOUND_SENT', 'INBOUND_RECEIVED',
            'MEETING_SCHEDULED', 'MEETING_COMPLETED',
            'NOTE_ADDED', 'TASK_COMPLETED',
            'REFERRAL_GIVEN', 'DEAL_CLOSED',
            'OBJECTION_LOGGED', 'SIGNAL_DETECTED',
            'PLAYBOOK_TRIGGERED', 'CADENCE_STEP_DUE',
            'PREFERENCE_UPDATED', 'CONSENT_UPDATED',
            'STAGE_CHANGED', 'SCORE_UPDATED'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Objection taxonomy
    DO $$ BEGIN
        CREATE TYPE rw_objection_category AS ENUM (
            'COMPENSATION', 'TECH_STACK', 'SUPPORT_STAFF', 'OPERATIONS', 'PROCESSING', 'UNDERWRITING',
            'BRAND_REPUTATION', 'LEAD_FLOW', 'MARKETING', 'CULTURE', 'MANAGEMENT', 'TRAINING',
            'COMPLIANCE_RISK', 'NON_COMPETE', 'TIMING', 'INERTIA', 'LOYALTY', 'GEOGRAPHY',
            'PRODUCT_LIMITATION', 'PRICING_RATES', 'OTHER'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Signal types for timing detection
    DO $$ BEGIN
        CREATE TYPE rw_signal_type AS ENUM (
            'JOB_CHANGE', 'TEAM_CHANGE', 'PRODUCTION_SPIKE', 'PRODUCTION_DROP', 'COMMISSION_CHANGE',
            'TECH_PAIN', 'OPS_PAIN', 'BRANCH_INSTABILITY', 'MANAGEMENT_CONFLICT',
            'MARKET_SHIFT', 'NEW_MARKET_ENTRY', 'LIFE_EVENT', 'REFERRAL_ACTIVITY',
            'ENGAGEMENT_SPIKE', 'MEETING_INTENT', 'OBJECTION_SOFTENED', 'TIME_WINDOW',
            'LENDER_DISSATISFACTION', 'TEAM_GROWTH', 'SEASONAL_SURGE'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- Edge types for relationship mapping
    DO $$ BEGIN
        CREATE TYPE rw_edge_type AS ENUM (
            'PAST_DEAL', 'REFERRAL_SENT', 'REFERRAL_RECEIVED', 'CO_WORKED_WITH',
            'SAME_ORG', 'INTRO_REQUESTED', 'INTRO_MADE', 'SOCIAL_MUTUAL', 'EVENT_MET'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    -- =============================================================================
    -- CORE TABLES
    -- =============================================================================

    -- Organizations (brokerages, lenders, teams)
    CREATE TABLE IF NOT EXISTS rw_org (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        org_type TEXT,  -- brokerage, lender, team, real_estate_office
        website TEXT,
        address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        phone TEXT,
        nmls_id TEXT,
        notes TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_org_name ON rw_org(name);
    CREATE INDEX IF NOT EXISTS idx_rw_org_type ON rw_org(org_type);

    -- People (LOs + Realtors) - Core recruiting targets
    CREATE TABLE IF NOT EXISTS rw_person (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),

        -- Type and basic info
        person_type rw_person_type NOT NULL,
        first_name TEXT,
        last_name TEXT,
        display_name TEXT GENERATED ALWAYS AS (
            TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))
        ) STORED,

        -- Contact information
        primary_email TEXT,
        secondary_email TEXT,
        primary_phone TEXT,
        secondary_phone TEXT,

        -- Social profiles
        linkedin_url TEXT,
        instagram_handle TEXT,
        facebook_url TEXT,
        twitter_handle TEXT,

        -- Location
        location_city TEXT,
        location_state TEXT,
        location_zip TEXT,
        timezone TEXT DEFAULT 'America/New_York',

        -- Professional info
        current_org_id UUID REFERENCES rw_org(id),
        title TEXT,
        nmls_id TEXT,
        license_state TEXT,
        years_experience INTEGER,

        -- Production data (for LOs)
        annual_volume DECIMAL(15, 2),
        annual_units INTEGER,
        avg_loan_size DECIMAL(12, 2),

        -- Relationship state
        relationship_stage rw_relationship_stage NOT NULL DEFAULT 'DISCOVERED',
        owner_user_id INTEGER REFERENCES users(id),  -- CRM owner / recruiter

        -- Consent flags
        consent_sms BOOLEAN DEFAULT FALSE,
        consent_email BOOLEAN DEFAULT TRUE,
        consent_phone BOOLEAN DEFAULT TRUE,
        do_not_contact BOOLEAN DEFAULT FALSE,

        -- Source tracking
        source TEXT,  -- how they were discovered
        source_campaign TEXT,
        referrer_person_id UUID,  -- who referred them

        -- Metadata
        tags TEXT[],
        custom_fields JSONB DEFAULT '{}'::jsonb,

        -- Timestamps
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_person_type_stage ON rw_person(person_type, relationship_stage);
    CREATE INDEX IF NOT EXISTS idx_rw_person_owner ON rw_person(owner_user_id);
    CREATE INDEX IF NOT EXISTS idx_rw_person_org ON rw_person(current_org_id);
    CREATE INDEX IF NOT EXISTS idx_rw_person_email ON rw_person(primary_email);
    CREATE INDEX IF NOT EXISTS idx_rw_person_phone ON rw_person(primary_phone);
    CREATE INDEX IF NOT EXISTS idx_rw_person_stage ON rw_person(relationship_stage);
    CREATE INDEX IF NOT EXISTS idx_rw_person_organization ON rw_person(organization_id);

    -- Self-referential FK for referrer
    ALTER TABLE rw_person DROP CONSTRAINT IF EXISTS fk_rw_person_referrer;
    ALTER TABLE rw_person ADD CONSTRAINT fk_rw_person_referrer
        FOREIGN KEY (referrer_person_id) REFERENCES rw_person(id) ON DELETE SET NULL;

    -- =============================================================================
    -- RELATIONSHIP INTELLIGENCE
    -- =============================================================================

    -- Relationship intelligence (AI scores + state)
    CREATE TABLE IF NOT EXISTS rw_relationship_intel (
        person_id UUID PRIMARY KEY REFERENCES rw_person(id) ON DELETE CASCADE,

        -- Timing / intent scores (0-100)
        timing_score INTEGER NOT NULL DEFAULT 0,
        trust_score INTEGER NOT NULL DEFAULT 0,
        reciprocity_score INTEGER NOT NULL DEFAULT 0,
        risk_score INTEGER NOT NULL DEFAULT 0,
        engagement_score INTEGER NOT NULL DEFAULT 0,

        -- Composite score
        overall_score INTEGER GENERATED ALWAYS AS (
            LEAST(100, GREATEST(0, (timing_score * 40 + trust_score * 25 + engagement_score * 20 + reciprocity_score * 15) / 100))
        ) STORED,

        -- AI-generated insights
        why_they_might_switch TEXT,
        what_they_care_about TEXT,
        what_they_hate TEXT,
        ideal_offer TEXT,
        predicted_timeline TEXT,

        -- Timing metadata
        last_signal_at TIMESTAMPTZ,
        last_signal_type rw_signal_type,
        last_meaningful_touch_at TIMESTAMPTZ,
        next_best_action TEXT,
        next_best_action_reason TEXT,

        -- Decay tracking
        last_score_decay_at TIMESTAMPTZ DEFAULT now(),

        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- =============================================================================
    -- MUTUAL CONNECTION GRAPH
    -- =============================================================================

    -- Relationship edges (network graph)
    CREATE TABLE IF NOT EXISTS rw_person_edge (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        from_person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,
        to_person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,
        edge_type rw_edge_type NOT NULL,

        -- Strength + evidence
        strength INTEGER NOT NULL DEFAULT 1,  -- 1-10 scale
        evidence TEXT,
        deal_id INTEGER,  -- reference to loan if applicable

        -- Metadata
        occurred_at TIMESTAMPTZ,
        verified BOOLEAN DEFAULT FALSE,
        verified_by INTEGER REFERENCES users(id),
        notes TEXT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

        -- Prevent duplicate edges of same type
        UNIQUE(from_person_id, to_person_id, edge_type)
    );

    CREATE INDEX IF NOT EXISTS idx_rw_edges_from_to ON rw_person_edge(from_person_id, to_person_id);
    CREATE INDEX IF NOT EXISTS idx_rw_edges_to_from ON rw_person_edge(to_person_id, from_person_id);
    CREATE INDEX IF NOT EXISTS idx_rw_edges_type ON rw_person_edge(edge_type);
    CREATE INDEX IF NOT EXISTS idx_rw_edges_strength ON rw_person_edge(strength DESC);

    -- =============================================================================
    -- SIGNALS
    -- =============================================================================

    -- Detected signals for timing intelligence
    CREATE TABLE IF NOT EXISTS rw_signal (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        signal_type rw_signal_type NOT NULL,
        confidence DECIMAL(3, 2) NOT NULL DEFAULT 0.5,  -- 0.00 - 1.00
        weight INTEGER NOT NULL DEFAULT 10,  -- points to add to timing_score

        -- Evidence
        evidence TEXT,
        source TEXT,  -- email, note, social, external
        source_reference TEXT,  -- ID or URL of source

        -- Processing
        processed BOOLEAN DEFAULT FALSE,
        processed_at TIMESTAMPTZ,
        score_delta INTEGER,  -- actual points added after processing

        -- Metadata
        detected_by INTEGER REFERENCES users(id),  -- null if AI detected
        ai_detected BOOLEAN DEFAULT FALSE,
        expires_at TIMESTAMPTZ,  -- some signals have time windows

        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_signal_person ON rw_signal(person_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_signal_type ON rw_signal(signal_type);
    CREATE INDEX IF NOT EXISTS idx_rw_signal_unprocessed ON rw_signal(processed) WHERE processed = FALSE;

    -- =============================================================================
    -- OBJECTION TAXONOMY
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_objection (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        category rw_objection_category NOT NULL,
        subcategory TEXT,
        severity INTEGER NOT NULL DEFAULT 3,  -- 1-5 scale

        -- Details
        statement TEXT,  -- their exact words if captured
        context TEXT,  -- situation where objection came up
        our_response TEXT,  -- how we addressed it

        -- Status tracking
        status TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, ADDRESSED, RESOLVED, DISMISSED
        addressed_at TIMESTAMPTZ,
        resolved_at TIMESTAMPTZ,
        resolution_notes TEXT,

        -- Follow-up
        next_revisit_at TIMESTAMPTZ,
        revisit_count INTEGER DEFAULT 0,

        -- Attribution
        captured_by_user_id INTEGER REFERENCES users(id),
        captured_via TEXT,  -- call, email, meeting, note

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_objection_person ON rw_objection(person_id, category, status);
    CREATE INDEX IF NOT EXISTS idx_rw_objection_status ON rw_objection(status);
    CREATE INDEX IF NOT EXISTS idx_rw_objection_revisit ON rw_objection(next_revisit_at) WHERE status = 'OPEN';

    -- =============================================================================
    -- CONTACT PREFERENCE LEARNING
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_contact_preference (
        person_id UUID PRIMARY KEY REFERENCES rw_person(id) ON DELETE CASCADE,

        -- Explicit preferences (user-stated)
        preferred_channels rw_comm_channel[] DEFAULT ARRAY[]::rw_comm_channel[],
        do_not_use_channels rw_comm_channel[] DEFAULT ARRAY[]::rw_comm_channel[],
        preferred_days INTEGER[] DEFAULT ARRAY[]::INTEGER[],  -- 0=Sun .. 6=Sat
        preferred_time_start TIME,
        preferred_time_end TIME,

        -- Learned engagement stats (from comm_outcome)
        sms_response_rate DECIMAL(5, 2) DEFAULT 0,
        email_open_rate DECIMAL(5, 2) DEFAULT 0,
        email_reply_rate DECIMAL(5, 2) DEFAULT 0,
        phone_answer_rate DECIMAL(5, 2) DEFAULT 0,

        -- Learned best contact windows
        best_contact_minute INTEGER,  -- minutes since midnight (0-1439)
        best_contact_day INTEGER,  -- 0=Sun .. 6=Sat
        best_channel rw_comm_channel,

        -- Stats for learning
        total_outreach_count INTEGER DEFAULT 0,
        total_response_count INTEGER DEFAULT 0,
        last_response_at TIMESTAMPTZ,

        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- Communication outcome tracking for learning
    CREATE TABLE IF NOT EXISTS rw_comm_outcome (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        channel rw_comm_channel NOT NULL,
        direction TEXT NOT NULL DEFAULT 'outbound',  -- outbound, inbound

        -- Timing
        sent_at TIMESTAMPTZ NOT NULL,
        sent_day_of_week INTEGER,  -- 0-6
        sent_minute_of_day INTEGER,  -- 0-1439

        -- Outcomes
        delivered BOOLEAN DEFAULT TRUE,
        opened_at TIMESTAMPTZ,
        clicked_at TIMESTAMPTZ,
        replied_at TIMESTAMPTZ,
        booked_meeting_at TIMESTAMPTZ,

        -- Scoring
        outcome_score INTEGER NOT NULL DEFAULT 0,  -- 0-100

        -- Context
        template_key TEXT,
        campaign_id TEXT,
        message_preview TEXT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_comm_outcome_person ON rw_comm_outcome(person_id, channel, sent_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_comm_outcome_learning ON rw_comm_outcome(person_id, sent_day_of_week, sent_minute_of_day);

    -- =============================================================================
    -- EVENT LOG (Orchestration Backbone)
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_crm_event (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),

        event_type rw_event_type NOT NULL,
        person_id UUID REFERENCES rw_person(id) ON DELETE SET NULL,

        -- Actor
        user_id INTEGER REFERENCES users(id),  -- who triggered, null if system

        -- Payload
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,

        -- Processing
        processed BOOLEAN DEFAULT FALSE,
        processed_at TIMESTAMPTZ,

        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_event_person_time ON rw_crm_event(person_id, occurred_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_event_type_time ON rw_crm_event(event_type, occurred_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_event_unprocessed ON rw_crm_event(processed) WHERE processed = FALSE;
    CREATE INDEX IF NOT EXISTS idx_rw_event_org ON rw_crm_event(organization_id, occurred_at DESC);

    -- =============================================================================
    -- CADENCE SYSTEM
    -- =============================================================================

    -- Cadence definitions
    CREATE TABLE IF NOT EXISTS rw_cadence (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),

        name TEXT NOT NULL,
        key TEXT UNIQUE NOT NULL,  -- machine-friendly key
        description TEXT,

        person_type rw_person_type NOT NULL,
        target_stages rw_relationship_stage[] DEFAULT ARRAY[]::rw_relationship_stage[],

        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        is_default BOOLEAN DEFAULT FALSE,  -- default for this person_type

        -- Settings
        pause_on_reply BOOLEAN DEFAULT TRUE,
        pause_on_meeting BOOLEAN DEFAULT TRUE,
        exit_on_stage_change BOOLEAN DEFAULT FALSE,

        -- Metadata
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_cadence_type ON rw_cadence(person_type, is_active);
    CREATE INDEX IF NOT EXISTS idx_rw_cadence_key ON rw_cadence(key);

    -- Cadence steps
    CREATE TABLE IF NOT EXISTS rw_cadence_step (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        cadence_id UUID NOT NULL REFERENCES rw_cadence(id) ON DELETE CASCADE,

        step_order INTEGER NOT NULL,
        step_name TEXT,

        -- Timing
        min_days_after_prev INTEGER NOT NULL,  -- minimum days to wait
        max_days_after_prev INTEGER,  -- optional max (for randomization)

        -- Action
        channel rw_comm_channel NOT NULL,
        template_key TEXT NOT NULL,

        -- Goals and conditions
        goal TEXT,  -- what we're trying to achieve
        skip_if_conditions JSONB DEFAULT '{}'::jsonb,  -- conditions to skip this step

        is_required BOOLEAN DEFAULT TRUE,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_cadence_step_cadence ON rw_cadence_step(cadence_id, step_order);

    -- Cadence enrollments
    CREATE TABLE IF NOT EXISTS rw_cadence_enrollment (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,
        cadence_id UUID NOT NULL REFERENCES rw_cadence(id) ON DELETE CASCADE,

        -- Status
        status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, PAUSED, COMPLETED, CANCELLED

        -- Progress
        current_step INTEGER NOT NULL DEFAULT 1,
        completed_steps INTEGER[] DEFAULT ARRAY[]::INTEGER[],

        -- Timing
        enrolled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        next_step_due_at TIMESTAMPTZ NOT NULL,
        last_step_at TIMESTAMPTZ,
        paused_at TIMESTAMPTZ,
        paused_until TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,

        -- Context
        enrolled_by INTEGER REFERENCES users(id),
        pause_reason TEXT,

        -- Stats
        steps_executed INTEGER DEFAULT 0,
        responses_received INTEGER DEFAULT 0,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

        -- Only one active enrollment per person per cadence
        UNIQUE(person_id, cadence_id) DEFERRABLE INITIALLY DEFERRED
    );

    CREATE INDEX IF NOT EXISTS idx_rw_enrollment_due ON rw_cadence_enrollment(status, next_step_due_at)
        WHERE status = 'ACTIVE';
    CREATE INDEX IF NOT EXISTS idx_rw_enrollment_person ON rw_cadence_enrollment(person_id, status);

    -- =============================================================================
    -- PLAYBOOK SYSTEM
    -- =============================================================================

    -- Playbook definitions
    CREATE TABLE IF NOT EXISTS rw_playbook (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),

        key TEXT UNIQUE NOT NULL,  -- e.g., LO_HIGH_INTENT_SURGE
        name TEXT NOT NULL,
        description TEXT,

        person_type rw_person_type NOT NULL,

        -- Trigger conditions (JSON)
        trigger_config JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- Structure: {
        --   "timing_score_min": 70,
        --   "signal_types": ["MEETING_INTENT", "BRANCH_INSTABILITY"],
        --   "stage_in": ["NURTURING", "WARMING"],
        --   "operator": "OR"  -- AND/OR for signal matching
        -- }

        -- Actions to execute
        actions JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- Structure: [
        --   { "type": "SMS", "timing": "within_15_min", "template": "..." },
        --   { "type": "TASK", "title": "...", "priority": "HIGH" },
        --   { "type": "EMAIL", "template_key": "..." },
        --   { "type": "PAUSE_CADENCE", "days": 14 },
        --   { "type": "INTRO_REQUEST", "condition": "if_mutual_exists" }
        -- ]

        -- Settings
        is_active BOOLEAN DEFAULT TRUE,
        priority INTEGER DEFAULT 50,  -- higher = checked first
        cooldown_days INTEGER DEFAULT 30,  -- min days between triggers for same person

        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_playbook_type ON rw_playbook(person_type, is_active);
    CREATE INDEX IF NOT EXISTS idx_rw_playbook_key ON rw_playbook(key);

    -- Playbook execution runs
    CREATE TABLE IF NOT EXISTS rw_playbook_run (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        playbook_id UUID NOT NULL REFERENCES rw_playbook(id),
        person_id UUID NOT NULL REFERENCES rw_person(id),

        -- Trigger context
        triggered_by_signal_id UUID REFERENCES rw_signal(id),
        triggered_by_event_id UUID REFERENCES rw_crm_event(id),
        trigger_context JSONB NOT NULL DEFAULT '{}'::jsonb,

        -- Execution status
        status TEXT NOT NULL DEFAULT 'STARTED',  -- STARTED, IN_PROGRESS, COMPLETED, FAILED, CANCELLED

        -- Actions tracking
        actions_total INTEGER NOT NULL DEFAULT 0,
        actions_completed INTEGER DEFAULT 0,
        actions_log JSONB DEFAULT '[]'::jsonb,

        -- Results
        outcome TEXT,
        outcome_notes TEXT,

        -- Timing
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at TIMESTAMPTZ
    );

    CREATE INDEX IF NOT EXISTS idx_rw_playbook_run_person ON rw_playbook_run(person_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_playbook_run_status ON rw_playbook_run(status);

    -- =============================================================================
    -- MESSAGE TEMPLATES
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_message_template (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),

        key TEXT NOT NULL,  -- unique per org
        name TEXT NOT NULL,

        channel rw_comm_channel NOT NULL,
        person_type rw_person_type,  -- null = both

        -- Content
        subject TEXT,  -- for email
        body TEXT NOT NULL,

        -- Personalization fields used
        merge_fields TEXT[] DEFAULT ARRAY[]::TEXT[],  -- e.g., ['first_name', 'company']

        -- Categorization
        category TEXT,  -- initial, followup, nurture, reengagement, objection_handling
        purpose TEXT,  -- value, micro_yes, book_meeting, send_asset, intro_request

        -- Stats
        times_used INTEGER DEFAULT 0,
        avg_response_rate DECIMAL(5, 2),

        is_active BOOLEAN DEFAULT TRUE,

        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

        UNIQUE(organization_id, key)
    );

    CREATE INDEX IF NOT EXISTS idx_rw_template_channel ON rw_message_template(channel, person_type, is_active);
    CREATE INDEX IF NOT EXISTS idx_rw_template_key ON rw_message_template(organization_id, key);

    -- =============================================================================
    -- TASKS (Recruiting workflow tasks)
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_task (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organization_id INTEGER REFERENCES organizations(id),
        person_id UUID REFERENCES rw_person(id) ON DELETE CASCADE,

        -- Task details
        title TEXT NOT NULL,
        description TEXT,
        task_type TEXT,  -- call, email, meeting, research, intro_request, follow_up

        -- Priority and timing
        priority TEXT DEFAULT 'MEDIUM',  -- LOW, MEDIUM, HIGH, URGENT
        due_at TIMESTAMPTZ,
        reminder_at TIMESTAMPTZ,

        -- Assignment
        assigned_to INTEGER REFERENCES users(id),

        -- Status
        status TEXT DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, COMPLETED, CANCELLED, SNOOZED
        completed_at TIMESTAMPTZ,
        completed_by INTEGER REFERENCES users(id),

        -- Source (what created this task)
        source_type TEXT,  -- playbook, cadence, manual, ai
        source_id UUID,  -- playbook_run_id or cadence_enrollment_id

        -- Results
        outcome TEXT,
        outcome_notes TEXT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_task_person ON rw_task(person_id, status);
    CREATE INDEX IF NOT EXISTS idx_rw_task_assigned ON rw_task(assigned_to, status, due_at);
    CREATE INDEX IF NOT EXISTS idx_rw_task_due ON rw_task(status, due_at) WHERE status IN ('PENDING', 'IN_PROGRESS');

    -- =============================================================================
    -- NOTES
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_note (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        content TEXT NOT NULL,
        note_type TEXT,  -- general, call_summary, meeting_notes, research, objection

        -- Attribution
        created_by INTEGER REFERENCES users(id),

        -- AI processing
        ai_processed BOOLEAN DEFAULT FALSE,
        ai_extracted_signals JSONB,
        ai_extracted_objections JSONB,

        -- Visibility
        is_private BOOLEAN DEFAULT FALSE,
        pinned BOOLEAN DEFAULT FALSE,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_note_person ON rw_note(person_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_rw_note_pinned ON rw_note(person_id, pinned) WHERE pinned = TRUE;

    -- =============================================================================
    -- MEETINGS
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_meeting (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        title TEXT NOT NULL,
        description TEXT,
        meeting_type TEXT,  -- discovery, follow_up, presentation, negotiation, onboarding

        -- Scheduling
        scheduled_at TIMESTAMPTZ NOT NULL,
        duration_minutes INTEGER DEFAULT 30,
        location TEXT,  -- physical address or video link

        -- Status
        status TEXT DEFAULT 'SCHEDULED',  -- SCHEDULED, CONFIRMED, COMPLETED, CANCELLED, NO_SHOW

        -- Attendees
        organizer_user_id INTEGER REFERENCES users(id),
        attendee_emails TEXT[],

        -- Outcomes
        completed_at TIMESTAMPTZ,
        outcome TEXT,  -- positive, neutral, negative, rescheduled
        notes TEXT,
        next_steps TEXT,

        -- Calendar integration
        external_calendar_id TEXT,
        external_event_id TEXT,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_meeting_person ON rw_meeting(person_id, scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_rw_meeting_organizer ON rw_meeting(organizer_user_id, scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_rw_meeting_status ON rw_meeting(status, scheduled_at);

    -- =============================================================================
    -- INTRO REQUESTS
    -- =============================================================================

    CREATE TABLE IF NOT EXISTS rw_intro_request (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

        -- The person we want an intro to
        target_person_id UUID NOT NULL REFERENCES rw_person(id) ON DELETE CASCADE,

        -- The mutual connection we're asking
        connector_person_id UUID NOT NULL REFERENCES rw_person(id),

        -- The relationship edge that links them
        edge_id UUID REFERENCES rw_person_edge(id),

        -- Status
        status TEXT DEFAULT 'PENDING',  -- PENDING, SENT, ACCEPTED, DECLINED, COMPLETED

        -- Request details
        reason TEXT,
        suggested_message TEXT,

        -- Requester
        requested_by INTEGER REFERENCES users(id),

        -- Outcomes
        sent_at TIMESTAMPTZ,
        response_at TIMESTAMPTZ,
        response_notes TEXT,
        intro_made_at TIMESTAMPTZ,

        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS idx_rw_intro_target ON rw_intro_request(target_person_id);
    CREATE INDEX IF NOT EXISTS idx_rw_intro_connector ON rw_intro_request(connector_person_id);

    -- =============================================================================
    -- TRIGGERS: Auto-update timestamps
    -- =============================================================================

    CREATE OR REPLACE FUNCTION rw_update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Apply to all tables with updated_at
    DO $$
    DECLARE
        tbl TEXT;
    BEGIN
        FOR tbl IN
            SELECT unnest(ARRAY[
                'rw_org', 'rw_person', 'rw_relationship_intel', 'rw_objection',
                'rw_contact_preference', 'rw_cadence', 'rw_cadence_enrollment',
                'rw_playbook', 'rw_message_template', 'rw_task', 'rw_note', 'rw_meeting'
            ])
        LOOP
            EXECUTE format('DROP TRIGGER IF EXISTS update_%s_updated_at ON %s', tbl, tbl);
            EXECUTE format('CREATE TRIGGER update_%s_updated_at BEFORE UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION rw_update_updated_at()', tbl, tbl);
        END LOOP;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'Trigger creation note: %', SQLERRM;
    END $$;

    -- =============================================================================
    -- FUNCTIONS: Timing Score Calculation
    -- =============================================================================

    -- Signal weight lookup
    CREATE OR REPLACE FUNCTION rw_get_signal_weight(
        p_signal_type rw_signal_type,
        p_person_type rw_person_type
    ) RETURNS INTEGER AS $$
    BEGIN
        IF p_person_type = 'LOAN_OFFICER' THEN
            RETURN CASE p_signal_type
                WHEN 'MEETING_INTENT' THEN 35
                WHEN 'BRANCH_INSTABILITY' THEN 25
                WHEN 'OPS_PAIN' THEN 20
                WHEN 'TECH_PAIN' THEN 15
                WHEN 'ENGAGEMENT_SPIKE' THEN 18
                WHEN 'JOB_CHANGE' THEN 30
                WHEN 'PRODUCTION_DROP' THEN 20
                WHEN 'COMMISSION_CHANGE' THEN 22
                WHEN 'MANAGEMENT_CONFLICT' THEN 25
                WHEN 'OBJECTION_SOFTENED' THEN 15
                WHEN 'TIME_WINDOW' THEN 10
                ELSE 10
            END;
        ELSE  -- REALTOR
            RETURN CASE p_signal_type
                WHEN 'LENDER_DISSATISFACTION' THEN 25
                WHEN 'REFERRAL_ACTIVITY' THEN 20
                WHEN 'ENGAGEMENT_SPIKE' THEN 18
                WHEN 'TEAM_GROWTH' THEN 15
                WHEN 'MEETING_INTENT' THEN 30
                WHEN 'SEASONAL_SURGE' THEN 12
                WHEN 'OBJECTION_SOFTENED' THEN 15
                WHEN 'TIME_WINDOW' THEN 10
                ELSE 10
            END;
        END IF;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    -- Process a signal and update timing score
    CREATE OR REPLACE FUNCTION rw_process_signal(
        p_signal_id UUID
    ) RETURNS INTEGER AS $$
    DECLARE
        v_signal RECORD;
        v_person RECORD;
        v_weight INTEGER;
        v_new_score INTEGER;
    BEGIN
        -- Get signal details
        SELECT * INTO v_signal FROM rw_signal WHERE id = p_signal_id AND processed = FALSE;
        IF NOT FOUND THEN
            RETURN 0;
        END IF;

        -- Get person details
        SELECT * INTO v_person FROM rw_person WHERE id = v_signal.person_id;

        -- Calculate weight
        v_weight := rw_get_signal_weight(v_signal.signal_type, v_person.person_type);

        -- Update timing score (capped at 100)
        UPDATE rw_relationship_intel
        SET
            timing_score = LEAST(100, timing_score + v_weight),
            last_signal_at = now(),
            last_signal_type = v_signal.signal_type,
            updated_at = now()
        WHERE person_id = v_signal.person_id
        RETURNING timing_score INTO v_new_score;

        -- Mark signal as processed
        UPDATE rw_signal
        SET
            processed = TRUE,
            processed_at = now(),
            score_delta = v_weight
        WHERE id = p_signal_id;

        RETURN v_new_score;
    END;
    $$ LANGUAGE plpgsql;

    -- Daily score decay function
    CREATE OR REPLACE FUNCTION rw_decay_timing_scores() RETURNS INTEGER AS $$
    DECLARE
        v_count INTEGER;
    BEGIN
        UPDATE rw_relationship_intel
        SET
            timing_score = FLOOR(timing_score * 0.98),
            last_score_decay_at = now()
        WHERE timing_score > 0
          AND (last_score_decay_at IS NULL OR last_score_decay_at < CURRENT_DATE);

        GET DIAGNOSTICS v_count = ROW_COUNT;
        RETURN v_count;
    END;
    $$ LANGUAGE plpgsql;

    -- =============================================================================
    -- FUNCTIONS: Mutual Connections
    -- =============================================================================

    -- Find mutual connections between two people
    CREATE OR REPLACE FUNCTION rw_find_mutuals(
        p_person_a UUID,
        p_person_b UUID
    ) RETURNS TABLE(
        person_id UUID,
        display_name TEXT,
        total_strength INTEGER,
        edge_types TEXT[]
    ) AS $$
    BEGIN
        RETURN QUERY
        WITH a_neighbors AS (
            SELECT to_person_id AS n, edge_type, strength FROM rw_person_edge WHERE from_person_id = p_person_a
            UNION ALL
            SELECT from_person_id AS n, edge_type, strength FROM rw_person_edge WHERE to_person_id = p_person_a
        ),
        b_neighbors AS (
            SELECT to_person_id AS n, edge_type, strength FROM rw_person_edge WHERE from_person_id = p_person_b
            UNION ALL
            SELECT from_person_id AS n, edge_type, strength FROM rw_person_edge WHERE to_person_id = p_person_b
        ),
        mutual_ids AS (
            SELECT DISTINCT an.n
            FROM a_neighbors an
            JOIN b_neighbors bn ON an.n = bn.n
        )
        SELECT
            p.id,
            p.display_name,
            (
                SELECT COALESCE(SUM(e.strength), 0)::INTEGER
                FROM rw_person_edge e
                WHERE (e.from_person_id = p.id OR e.to_person_id = p.id)
                  AND (e.from_person_id IN (p_person_a, p_person_b) OR e.to_person_id IN (p_person_a, p_person_b))
            ),
            ARRAY(
                SELECT DISTINCT e.edge_type::TEXT
                FROM rw_person_edge e
                WHERE (e.from_person_id = p.id OR e.to_person_id = p.id)
                  AND (e.from_person_id IN (p_person_a, p_person_b) OR e.to_person_id IN (p_person_a, p_person_b))
            )
        FROM mutual_ids m
        JOIN rw_person p ON p.id = m.n
        ORDER BY 3 DESC;
    END;
    $$ LANGUAGE plpgsql;

    -- Get top connections for a person
    CREATE OR REPLACE FUNCTION rw_get_top_connections(
        p_person_id UUID,
        p_limit INTEGER DEFAULT 10
    ) RETURNS TABLE(
        connected_person_id UUID,
        display_name TEXT,
        relationship_stage rw_relationship_stage,
        total_strength INTEGER,
        edge_count INTEGER,
        strongest_edge_type rw_edge_type
    ) AS $$
    BEGIN
        RETURN QUERY
        WITH edges AS (
            SELECT
                CASE WHEN from_person_id = p_person_id THEN to_person_id ELSE from_person_id END as other_id,
                edge_type,
                strength
            FROM rw_person_edge
            WHERE from_person_id = p_person_id OR to_person_id = p_person_id
        ),
        aggregated AS (
            SELECT
                other_id,
                SUM(strength)::INTEGER as total_strength,
                COUNT(*)::INTEGER as edge_count,
                (ARRAY_AGG(edge_type ORDER BY strength DESC))[1] as strongest_type
            FROM edges
            GROUP BY other_id
        )
        SELECT
            a.other_id,
            p.display_name,
            p.relationship_stage,
            a.total_strength,
            a.edge_count,
            a.strongest_type
        FROM aggregated a
        JOIN rw_person p ON p.id = a.other_id
        ORDER BY a.total_strength DESC
        LIMIT p_limit;
    END;
    $$ LANGUAGE plpgsql;

    -- =============================================================================
    -- FUNCTIONS: Objection Revisit Intervals
    -- =============================================================================

    CREATE OR REPLACE FUNCTION rw_get_objection_revisit_days(
        p_category rw_objection_category
    ) RETURNS INTEGER AS $$
    BEGIN
        RETURN CASE p_category
            WHEN 'TIMING' THEN 45
            WHEN 'INERTIA' THEN 60
            WHEN 'COMPENSATION' THEN 90
            WHEN 'OPERATIONS' THEN 21
            WHEN 'PROCESSING' THEN 30
            WHEN 'TECH_STACK' THEN 30
            WHEN 'SUPPORT_STAFF' THEN 30
            WHEN 'UNDERWRITING' THEN 30
            WHEN 'BRAND_REPUTATION' THEN 60
            WHEN 'LEAD_FLOW' THEN 45
            WHEN 'MARKETING' THEN 45
            WHEN 'CULTURE' THEN 60
            WHEN 'MANAGEMENT' THEN 45
            WHEN 'TRAINING' THEN 45
            WHEN 'COMPLIANCE_RISK' THEN 60
            WHEN 'NON_COMPETE' THEN 90
            WHEN 'LOYALTY' THEN 60
            WHEN 'GEOGRAPHY' THEN 90
            WHEN 'PRODUCT_LIMITATION' THEN 45
            WHEN 'PRICING_RATES' THEN 30
            ELSE 45
        END;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    -- Auto-set revisit date trigger
    CREATE OR REPLACE FUNCTION rw_set_objection_revisit()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.next_revisit_at IS NULL AND NEW.status = 'OPEN' THEN
            NEW.next_revisit_at := NOW() + (rw_get_objection_revisit_days(NEW.category) || ' days')::INTERVAL;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS set_objection_revisit ON rw_objection;
    CREATE TRIGGER set_objection_revisit
        BEFORE INSERT ON rw_objection
        FOR EACH ROW EXECUTE FUNCTION rw_set_objection_revisit();

    -- =============================================================================
    -- VIEWS: Useful aggregations
    -- =============================================================================

    -- Person summary view with intel
    CREATE OR REPLACE VIEW rw_person_summary AS
    SELECT
        p.*,
        ri.timing_score,
        ri.trust_score,
        ri.engagement_score,
        ri.overall_score,
        ri.last_signal_at,
        ri.last_signal_type,
        ri.next_best_action,
        o.name as org_name,
        (SELECT COUNT(*) FROM rw_objection obj WHERE obj.person_id = p.id AND obj.status = 'OPEN') as open_objections,
        (SELECT COUNT(*) FROM rw_task t WHERE t.person_id = p.id AND t.status IN ('PENDING', 'IN_PROGRESS')) as pending_tasks,
        (SELECT MAX(created_at) FROM rw_comm_outcome co WHERE co.person_id = p.id) as last_outreach_at
    FROM rw_person p
    LEFT JOIN rw_relationship_intel ri ON ri.person_id = p.id
    LEFT JOIN rw_org o ON o.id = p.current_org_id;

    -- Hot leads view (timing_score >= 70)
    CREATE OR REPLACE VIEW rw_hot_leads AS
    SELECT
        ps.*
    FROM rw_person_summary ps
    WHERE ps.timing_score >= 70
      AND ps.relationship_stage NOT IN ('ACTIVE_PARTNER', 'DO_NOT_CONTACT', 'DORMANT')
      AND ps.do_not_contact = FALSE
    ORDER BY ps.timing_score DESC, ps.last_signal_at DESC;

    -- Cadence due view
    CREATE OR REPLACE VIEW rw_cadence_due AS
    SELECT
        ce.*,
        c.name as cadence_name,
        c.key as cadence_key,
        cs.channel as next_channel,
        cs.template_key as next_template,
        cs.goal as next_goal,
        p.display_name as person_name,
        p.person_type,
        p.primary_email,
        p.primary_phone
    FROM rw_cadence_enrollment ce
    JOIN rw_cadence c ON c.id = ce.cadence_id
    JOIN rw_cadence_step cs ON cs.cadence_id = c.id AND cs.step_order = ce.current_step
    JOIN rw_person p ON p.id = ce.person_id
    WHERE ce.status = 'ACTIVE'
      AND ce.next_step_due_at <= NOW()
      AND p.do_not_contact = FALSE;

    -- Objections due for revisit
    CREATE OR REPLACE VIEW rw_objections_due AS
    SELECT
        obj.*,
        p.display_name as person_name,
        p.person_type,
        p.relationship_stage,
        ri.timing_score
    FROM rw_objection obj
    JOIN rw_person p ON p.id = obj.person_id
    LEFT JOIN rw_relationship_intel ri ON ri.person_id = p.id
    WHERE obj.status = 'OPEN'
      AND obj.next_revisit_at <= NOW()
    ORDER BY obj.severity DESC, obj.next_revisit_at;

    """

    with engine.connect() as conn:
        # Execute migration
        conn.execute(text(migration_sql))
        conn.commit()
        print("Recruiting Workflow CRM tables created successfully!")

        # Verify core tables
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name LIKE 'rw_%'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        print(f"\nTables created: {tables}")

        # Verify enums
        result = conn.execute(text("""
            SELECT typname FROM pg_type
            WHERE typname LIKE 'rw_%'
            ORDER BY typname
        """))
        enums = [row[0] for row in result]
        print(f"\nEnums created: {enums}")

    return {"message": "Recruiting Workflow CRM migration completed successfully", "tables": tables}


if __name__ == "__main__":
    run_migration()
