"""
Enterprise Challenge Migration — Creates all new tables for 8 enterprise domains.

Tables created:
  D1  loan_file_collaborators      Multi-user file ownership & RBAC on loan files
  D1  user_onboarding_state        Automated onboarding step tracking per user
  D2  file_communications          Unified SMS/email/call communication threading per file
  D2  communication_participants   Per-user notification & read-receipt tracking per file
  D6  vendors                      Appraisal, title, HOI vendor roster & performance
  D6  vendor_orders                Individual vendor orders per loan file
  D8  agent_context_store          Persistent learned context (agent/user/branch scope)
  D8  agent_context_events         Hot-path corrections, approvals, overrides
  D8  context_change_audit         Immutable audit log for all context mutations
  D8  harness_change_proposals     Weekly harness diff proposals from HarnessOptimizationAgent
  --  agent_registry               All 24+ registered agents (governance)
  --  agent_run_log                Append-only log of every agent execution

Run standalone:
    cd backend && python -m migrations.enterprise_challenge_tables

Or import from startup:
    from migrations.enterprise_challenge_tables import run_migration
    run_migration(engine)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table definitions: (table_name, CREATE TABLE IF NOT EXISTS sql)
# All tables use PostgreSQL-native types (UUID, TIMESTAMPTZ, JSONB, TEXT[]).
# Foreign keys reference existing tables: users(id), organizations(id),
# loans(id), leads(id).  The users.id and loans.id columns are INTEGER
# in the existing schema.
# ---------------------------------------------------------------------------

TABLES = [
    # ======================================================================
    # Domain 1 — Enterprise Team Onboarding & Collaborative File Access
    # ======================================================================
    (
        "loan_file_collaborators",
        """
        CREATE TABLE IF NOT EXISTS loan_file_collaborators (
            id              SERIAL PRIMARY KEY,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- RBAC role on this file (mirrors platform 8-role model)
            role            VARCHAR(50) NOT NULL DEFAULT 'read_only',
                -- admin, branch_manager, loan_officer, processor, underwriter,
                -- closer, marketing, read_only

            -- Optional per-file permission overrides (JSONB map of field -> bool)
            permissions_override JSONB DEFAULT '{}',

            -- Whether this collaborator is the primary owner of the file
            is_primary      BOOLEAN NOT NULL DEFAULT FALSE,

            -- Notification preference for file-level events
            notify          BOOLEAN NOT NULL DEFAULT TRUE,

            -- Assignment tracking
            assigned_by     INTEGER REFERENCES users(id),
            assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            removed_at      TIMESTAMPTZ,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- One user per file (active)
            CONSTRAINT uq_loan_file_collab_active
                UNIQUE (loan_id, user_id)
        )
        """
    ),
    (
        "user_onboarding_state",
        """
        CREATE TABLE IF NOT EXISTS user_onboarding_state (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Current step in the onboarding sequence
            step            VARCHAR(100) NOT NULL,
                -- profile_created, role_assigned, file_queue_set,
                -- smart_docs_provisioned, welcome_sent, agent_gym_enrolled,
                -- onboarding_complete

            -- Step ordering (1-based)
            step_order      INTEGER NOT NULL DEFAULT 1,

            -- Completion tracking
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                -- pending, in_progress, completed, skipped, failed
            completed_at    TIMESTAMPTZ,
            error_message   TEXT,

            -- Which agent run executed this step
            agent_run_id    UUID,

            -- Metadata (step-specific payload: portal URL, email ID, etc.)
            step_metadata   JSONB DEFAULT '{}',

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- One record per user per step
            CONSTRAINT uq_user_onboarding_step
                UNIQUE (user_id, step)
        )
        """
    ),

    # ======================================================================
    # Domain 2 — Unified Communication Threading
    # ======================================================================
    (
        "file_communications",
        """
        CREATE TABLE IF NOT EXISTS file_communications (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Direction & channel
            direction       VARCHAR(10) NOT NULL,       -- 'inbound' | 'outbound'
            channel         VARCHAR(20) NOT NULL,       -- 'sms' | 'email' | 'call' | 'note' | 'system'

            -- Content
            subject         TEXT,                        -- email subject, null for SMS
            body            TEXT NOT NULL,
            body_html       TEXT,                        -- rich HTML for email

            -- Participants
            from_party      VARCHAR(320) NOT NULL,       -- phone, email, or user display name
            to_party        VARCHAR(320),                -- nullable for notes / system messages

            -- AI enrichment
            ai_summary      TEXT,                        -- AI-generated summary of this message
            ai_draft_reply  TEXT,                        -- CommunicationDraftAgent auto-draft
            sentiment       VARCHAR(20),                 -- positive | neutral | negative

            -- Attachments & references
            attachments     JSONB DEFAULT '[]',          -- [{filename, url, mime_type, size_bytes}]
            external_id     VARCHAR(255),                -- Twilio SID, Graph message ID, call ID
            thread_id       VARCHAR(255),                -- email thread / SMS conversation ID

            -- Read tracking (array of user IDs who have read this message)
            read_by         JSONB DEFAULT '[]',

            -- Call-specific fields (populated when channel = 'call')
            call_duration   INTEGER,                     -- seconds
            recording_url   TEXT,
            transcript      TEXT,

            -- Soft delete
            is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),
    (
        "communication_participants",
        """
        CREATE TABLE IF NOT EXISTS communication_participants (
            id              SERIAL PRIMARY KEY,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Notification preference for this file's communications
            notify          BOOLEAN NOT NULL DEFAULT TRUE,

            -- Channels to notify on
            notify_sms      BOOLEAN NOT NULL DEFAULT TRUE,
            notify_email    BOOLEAN NOT NULL DEFAULT TRUE,
            notify_push     BOOLEAN NOT NULL DEFAULT TRUE,

            -- Read tracking
            last_read_at    TIMESTAMPTZ,
            unread_count    INTEGER NOT NULL DEFAULT 0,

            -- Participant role context
            role            VARCHAR(50),

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- One entry per user per file
            CONSTRAINT uq_comm_participant
                UNIQUE (loan_id, user_id)
        )
        """
    ),

    # ======================================================================
    # Domain 6 — Autonomous Operations Manager: Vendor Management
    # ======================================================================
    (
        "vendors",
        """
        CREATE TABLE IF NOT EXISTS vendors (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Vendor identity
            name            VARCHAR(255) NOT NULL,
            vendor_type     VARCHAR(50) NOT NULL,
                -- appraisal, title, hoi, survey, pest, flood_cert, credit_report
            contact_name    VARCHAR(255),
            contact_email   VARCHAR(320),
            contact_phone   VARCHAR(20),
            website         VARCHAR(512),

            -- Address
            address_line1   VARCHAR(255),
            address_line2   VARCHAR(255),
            city            VARCHAR(100),
            state           VARCHAR(2),
            zip_code        VARCHAR(10),

            -- Performance tracking (aggregated by ops manager agent)
            avg_turnaround_days NUMERIC(6, 2),       -- rolling average turnaround
            on_time_pct         NUMERIC(5, 2),        -- % of orders completed on time
            total_orders        INTEGER NOT NULL DEFAULT 0,
            total_completed     INTEGER NOT NULL DEFAULT 0,
            total_late          INTEGER NOT NULL DEFAULT 0,

            -- Rating & status
            quality_rating  NUMERIC(3, 2),            -- 1.00 - 5.00 scale
            is_preferred    BOOLEAN NOT NULL DEFAULT FALSE,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,

            -- License / insurance
            license_number  VARCHAR(100),
            license_expiry  DATE,
            insurance_expiry DATE,

            -- Notes
            internal_notes  TEXT,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- Unique vendor per org by name + type
            CONSTRAINT uq_vendor_org_name_type
                UNIQUE (organization_id, name, vendor_type)
        )
        """
    ),
    (
        "vendor_orders",
        """
        CREATE TABLE IF NOT EXISTS vendor_orders (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            vendor_id       INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,

            -- Order details
            order_type      VARCHAR(50) NOT NULL,
                -- appraisal, title_search, title_insurance, hoi_binder,
                -- survey, pest_inspection, flood_cert, credit_report
            order_number    VARCHAR(100),               -- external reference number
            status          VARCHAR(30) NOT NULL DEFAULT 'ordered',
                -- ordered, in_progress, received, under_review, accepted,
                -- revision_needed, cancelled, expired

            -- Assignment
            ordered_by      INTEGER REFERENCES users(id),
            ordered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- SLA tracking
            due_date        DATE,
            received_at     TIMESTAMPTZ,
            is_late         BOOLEAN NOT NULL DEFAULT FALSE,
            turnaround_days NUMERIC(6, 2),              -- actual business days taken

            -- Financials
            fee             NUMERIC(10, 2),
            paid            BOOLEAN NOT NULL DEFAULT FALSE,
            paid_at         TIMESTAMPTZ,

            -- Result
            result_summary  TEXT,
            result_document_id INTEGER,                  -- FK to documents table (soft ref)
            revision_count  INTEGER NOT NULL DEFAULT 0,

            -- Notes
            internal_notes  TEXT,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),

    # ======================================================================
    # Domain 8 — Continual Learning System
    # ======================================================================
    (
        "agent_context_store",
        """
        CREATE TABLE IF NOT EXISTS agent_context_store (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Scope determines what entity this context belongs to
            scope           TEXT NOT NULL,               -- 'agent' | 'user' | 'branch' | 'org'
            scope_id        TEXT NOT NULL,               -- agent_id | user_id | branch_id | org_id

            -- Context payload
            context_key     TEXT NOT NULL,               -- e.g. 'underwriting_preferences'
            context_value   JSONB NOT NULL,              -- structured learned context

            -- Provenance
            source          TEXT NOT NULL,               -- 'hot_path' | 'offline_consolidation' | 'manual'
            confidence      NUMERIC(4, 3),               -- 0.000 - 1.000

            -- Versioning (increment on update for audit trail)
            version         INTEGER NOT NULL DEFAULT 1,

            -- Soft-delete support (context can be reverted)
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- One active context per scope + key
            CONSTRAINT uq_agent_ctx_scope_key
                UNIQUE (scope, scope_id, context_key)
        )
        """
    ),
    (
        "agent_context_events",
        """
        CREATE TABLE IF NOT EXISTS agent_context_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Which agent produced the original output
            agent_id        TEXT NOT NULL,               -- FK to agent_registry.agent_id (soft ref)

            -- Who corrected / approved
            user_id         INTEGER REFERENCES users(id),
            organization_id INTEGER REFERENCES organizations(id),

            -- What file was the agent working on (nullable — not all runs have a file)
            loan_id         INTEGER REFERENCES loans(id),

            -- Event classification
            event_type      TEXT NOT NULL,               -- 'correction' | 'approval' | 'override' | 'feedback'

            -- Payload
            original_output JSONB,                       -- agent's original answer
            corrected_value JSONB,                       -- user's corrected version (null for approvals)
            rationale       TEXT,                        -- optional free-text reason from user

            -- Agent run reference
            agent_run_id    UUID,                        -- FK to agent_run_log.run_id (soft ref)

            -- Processing state (for consolidation pipeline)
            processed       BOOLEAN NOT NULL DEFAULT FALSE,
            processed_at    TIMESTAMPTZ,

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),
    (
        "context_change_audit",
        """
        CREATE TABLE IF NOT EXISTS context_change_audit (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- What changed
            scope           TEXT NOT NULL,               -- 'agent' | 'user' | 'branch' | 'org'
            scope_id        TEXT NOT NULL,
            context_key     TEXT,                        -- which key changed (null for bulk ops)

            -- Diff
            previous_value  JSONB,
            new_value       JSONB,

            -- Who / what triggered the change
            change_source   TEXT NOT NULL,               -- 'hot_path' | 'offline_consolidation' | 'manual' | 'revert'
            triggered_by    TEXT,                        -- job name, user_id, or agent_id

            -- Version tracking
            from_version    INTEGER,
            to_version      INTEGER,

            -- IMMUTABLE — no updated_at column
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),
    (
        "harness_change_proposals",
        """
        CREATE TABLE IF NOT EXISTS harness_change_proposals (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Which agent this proposal targets
            agent_id        TEXT NOT NULL,               -- FK to agent_registry.agent_id (soft ref)

            -- Analysis that produced this proposal
            analysis_summary JSONB NOT NULL,             -- high_latency_runs, timeouts, correction_rate, etc.
            proposed_changes JSONB NOT NULL,              -- structured diff: prompt changes, node changes, tool changes

            -- Review workflow
            status          VARCHAR(30) NOT NULL DEFAULT 'pending_review',
                -- pending_review, approved, rejected, deployed, rolled_back
            reviewed_by     INTEGER REFERENCES users(id),
            reviewed_at     TIMESTAMPTZ,
            review_notes    TEXT,

            -- AgentGym regression gate
            gym_tested      BOOLEAN NOT NULL DEFAULT FALSE,
            gym_passed      BOOLEAN,
            gym_scores      JSONB,                       -- per-dimension scores from regression suite
            gym_tested_at   TIMESTAMPTZ,

            -- Deployment tracking
            deployed_at     TIMESTAMPTZ,
            deployed_version VARCHAR(20),                -- new semver after deploy

            -- Timestamps
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),

    # ======================================================================
    # Cross-cutting — Agent Governance
    # ======================================================================
    (
        "agent_registry",
        """
        CREATE TABLE IF NOT EXISTS agent_registry (
            agent_id            TEXT PRIMARY KEY,                -- e.g. 'underwriter_audit_agent'
            display_name        TEXT NOT NULL,
            version             TEXT NOT NULL DEFAULT '1.0.0',   -- semver

            -- Classification
            category            TEXT NOT NULL,
                -- 'operations' | 'marketing' | 'compliance' | 'communication' | 'underwriting'

            -- Capabilities & permissions (PostgreSQL arrays)
            capabilities        TEXT[] NOT NULL DEFAULT '{}',
            required_permissions TEXT[] NOT NULL DEFAULT '{}',
            trigger_events      TEXT[] DEFAULT '{}',

            -- Execution config
            max_retries         INTEGER NOT NULL DEFAULT 3,
            timeout_seconds     INTEGER NOT NULL DEFAULT 90,
            fallback_behavior   TEXT NOT NULL DEFAULT 'escalate',
                -- 'skip' | 'escalate' | 'queue' | 'error'

            -- LangGraph reference
            langgraph_graph     TEXT,                            -- graph name / entrypoint

            -- Status flags
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            gym_tested          BOOLEAN NOT NULL DEFAULT FALSE,  -- must be TRUE before production

            -- Timestamps
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    ),
    (
        "agent_run_log",
        """
        CREATE TABLE IF NOT EXISTS agent_run_log (
            run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Which agent ran
            agent_id        TEXT NOT NULL,               -- FK to agent_registry.agent_id (soft ref)

            -- Context
            loan_id         INTEGER REFERENCES loans(id),
            user_id         INTEGER REFERENCES users(id),
            organization_id INTEGER REFERENCES organizations(id),

            -- Trigger
            trigger_event   TEXT,                        -- e.g. 'document.uploaded', 'cron.nightly'

            -- Input / output snapshots (SFT-ready)
            input_snapshot  JSONB,
            output_snapshot JSONB,
            findings        JSONB,                       -- agent-specific structured output

            -- Execution status
            status          TEXT NOT NULL DEFAULT 'running',
                -- 'running' | 'completed' | 'failed' | 'timed_out'

            -- Performance
            latency_ms      INTEGER,
            input_tokens    INTEGER,
            output_tokens   INTEGER,

            -- Error tracking
            error_message   TEXT,
            retry_count     INTEGER NOT NULL DEFAULT 0,

            -- Timestamps
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ
        )
        """
    ),
]


# ---------------------------------------------------------------------------
# Indexes — created after tables so we can use IF NOT EXISTS per index
# ---------------------------------------------------------------------------

INDEXES = [
    # -- D1: loan_file_collaborators
    "CREATE INDEX IF NOT EXISTS ix_lfc_loan_id ON loan_file_collaborators (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_lfc_user_id ON loan_file_collaborators (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_lfc_org_id ON loan_file_collaborators (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_lfc_org_loan ON loan_file_collaborators (organization_id, loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_lfc_role ON loan_file_collaborators (role)",
    "CREATE INDEX IF NOT EXISTS ix_lfc_primary ON loan_file_collaborators (loan_id) WHERE is_primary = TRUE",

    # -- D1: user_onboarding_state
    "CREATE INDEX IF NOT EXISTS ix_uos_user_id ON user_onboarding_state (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_uos_org_id ON user_onboarding_state (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_uos_status ON user_onboarding_state (status)",
    "CREATE INDEX IF NOT EXISTS ix_uos_user_status ON user_onboarding_state (user_id, status)",

    # -- D2: file_communications
    "CREATE INDEX IF NOT EXISTS ix_fc_loan_id ON file_communications (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_fc_org_id ON file_communications (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_fc_channel ON file_communications (channel)",
    "CREATE INDEX IF NOT EXISTS ix_fc_created ON file_communications (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_fc_loan_created ON file_communications (loan_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_fc_org_loan ON file_communications (organization_id, loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_fc_thread ON file_communications (thread_id)",
    "CREATE INDEX IF NOT EXISTS ix_fc_external ON file_communications (external_id)",

    # -- D2: communication_participants
    "CREATE INDEX IF NOT EXISTS ix_cp_loan_id ON communication_participants (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_cp_user_id ON communication_participants (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_cp_org_id ON communication_participants (organization_id)",

    # -- D6: vendors
    "CREATE INDEX IF NOT EXISTS ix_vendors_org_id ON vendors (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_vendors_type ON vendors (vendor_type)",
    "CREATE INDEX IF NOT EXISTS ix_vendors_org_type ON vendors (organization_id, vendor_type)",
    "CREATE INDEX IF NOT EXISTS ix_vendors_active ON vendors (organization_id, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_vendors_preferred ON vendors (organization_id, is_preferred) WHERE is_preferred = TRUE",

    # -- D6: vendor_orders
    "CREATE INDEX IF NOT EXISTS ix_vo_org_id ON vendor_orders (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_vo_vendor_id ON vendor_orders (vendor_id)",
    "CREATE INDEX IF NOT EXISTS ix_vo_loan_id ON vendor_orders (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_vo_status ON vendor_orders (status)",
    "CREATE INDEX IF NOT EXISTS ix_vo_due_date ON vendor_orders (due_date)",
    "CREATE INDEX IF NOT EXISTS ix_vo_org_status ON vendor_orders (organization_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_vo_loan_status ON vendor_orders (loan_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_vo_late ON vendor_orders (is_late) WHERE is_late = TRUE",

    # -- D8: agent_context_store
    "CREATE INDEX IF NOT EXISTS ix_acs_scope ON agent_context_store (scope, scope_id)",
    "CREATE INDEX IF NOT EXISTS ix_acs_key ON agent_context_store (context_key)",
    "CREATE INDEX IF NOT EXISTS ix_acs_source ON agent_context_store (source)",
    "CREATE INDEX IF NOT EXISTS ix_acs_active ON agent_context_store (is_active)",

    # -- D8: agent_context_events
    "CREATE INDEX IF NOT EXISTS ix_ace_agent ON agent_context_events (agent_id)",
    "CREATE INDEX IF NOT EXISTS ix_ace_user ON agent_context_events (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_ace_loan ON agent_context_events (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_ace_type ON agent_context_events (event_type)",
    "CREATE INDEX IF NOT EXISTS ix_ace_created ON agent_context_events (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_ace_unprocessed ON agent_context_events (processed, created_at) WHERE processed = FALSE",
    "CREATE INDEX IF NOT EXISTS ix_ace_agent_created ON agent_context_events (agent_id, created_at)",

    # -- D8: context_change_audit
    "CREATE INDEX IF NOT EXISTS ix_cca_scope ON context_change_audit (scope, scope_id)",
    "CREATE INDEX IF NOT EXISTS ix_cca_created ON context_change_audit (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_cca_source ON context_change_audit (change_source)",

    # -- D8: harness_change_proposals
    "CREATE INDEX IF NOT EXISTS ix_hcp_agent ON harness_change_proposals (agent_id)",
    "CREATE INDEX IF NOT EXISTS ix_hcp_status ON harness_change_proposals (status)",
    "CREATE INDEX IF NOT EXISTS ix_hcp_created ON harness_change_proposals (created_at)",

    # -- Cross-cutting: agent_registry
    "CREATE INDEX IF NOT EXISTS ix_ar_category ON agent_registry (category)",
    "CREATE INDEX IF NOT EXISTS ix_ar_active ON agent_registry (is_active)",

    # -- Cross-cutting: agent_run_log
    "CREATE INDEX IF NOT EXISTS ix_arl_agent ON agent_run_log (agent_id)",
    "CREATE INDEX IF NOT EXISTS ix_arl_loan ON agent_run_log (loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_arl_user ON agent_run_log (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_arl_org ON agent_run_log (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_arl_status ON agent_run_log (status)",
    "CREATE INDEX IF NOT EXISTS ix_arl_started ON agent_run_log (started_at)",
    "CREATE INDEX IF NOT EXISTS ix_arl_agent_started ON agent_run_log (agent_id, started_at)",
    "CREATE INDEX IF NOT EXISTS ix_arl_trigger ON agent_run_log (trigger_event)",
]


# ---------------------------------------------------------------------------
# Seed data: 24 registered agents required at launch
# ---------------------------------------------------------------------------

SEED_AGENTS = [
    # (agent_id, display_name, category, capabilities, required_permissions, trigger_events, timeout_seconds, fallback_behavior)
    (
        "user_provisioning_agent",
        "User Provisioning Agent",
        "operations",
        ["profile_creation", "role_assignment", "file_queue_setup", "portal_provisioning", "welcome_messaging", "gym_enrollment"],
        ["admin"],
        ["user.created"],
        30,
        "escalate",
    ),
    (
        "smart_docs_provisioning_agent",
        "Smart Docs Provisioning Agent",
        "operations",
        ["portal_creation", "checklist_generation", "purl_creation", "notification_delivery"],
        ["admin", "loan_officer", "processor"],
        ["user.created", "borrower.added"],
        30,
        "queue",
    ),
    (
        "underwriter_audit_agent",
        "Underwriter Audit Agent",
        "underwriting",
        ["income_analysis", "asset_verification", "credit_analysis", "ltv_calculation", "dti_calculation", "guideline_check", "overlay_check"],
        ["underwriter", "processor", "loan_officer", "admin"],
        ["document.uploaded", "loan_data.changed", "cron.nightly"],
        90,
        "escalate",
    ),
    (
        "deal_breaker_radar",
        "Deal Breaker Radar",
        "underwriting",
        ["hard_stop_detection", "severity_classification", "condition_ranking"],
        ["underwriter", "processor", "loan_officer", "admin"],
        ["underwriter_audit_agent.completed"],
        60,
        "escalate",
    ),
    (
        "turn_down_agent",
        "Turn Down Agent",
        "compliance",
        ["adverse_action_drafting", "compliance_routing", "denial_documentation"],
        ["underwriter", "admin"],
        ["deal_breaker_radar.hard_stop_detected"],
        60,
        "escalate",
    ),
    (
        "operations_manager_agent",
        "Operations Manager Agent",
        "operations",
        ["sla_enforcement", "workload_balancing", "pipeline_analytics", "bottleneck_detection", "team_scoring", "compliance_calendar", "vendor_management"],
        ["admin", "branch_manager"],
        ["cron.hourly", "sla.at_risk"],
        90,
        "escalate",
    ),
    (
        "communication_orchestrator",
        "Communication Orchestrator",
        "communication",
        ["message_routing", "thread_management", "notification_dispatch", "channel_detection"],
        ["loan_officer", "processor", "admin"],
        ["sms.inbound", "email.inbound"],
        30,
        "queue",
    ),
    (
        "communication_draft_agent",
        "Communication Draft Agent",
        "communication",
        ["reply_drafting", "tone_matching", "context_injection", "compliance_language"],
        ["loan_officer", "processor"],
        ["communication_orchestrator.message_received"],
        30,
        "skip",
    ),
    (
        "call_intelligence_pipeline",
        "Call Intelligence Pipeline",
        "communication",
        ["pipeline_orchestration", "agent_coordination", "result_aggregation"],
        ["loan_officer", "admin"],
        ["call.started"],
        90,
        "escalate",
    ),
    (
        "live_transcription_agent",
        "Live Transcription Agent",
        "communication",
        ["realtime_stt", "word_timestamps", "speaker_diarization"],
        ["loan_officer", "admin"],
        ["call.started"],
        90,
        "skip",
    ),
    (
        "sentiment_analysis_agent",
        "Sentiment Analysis Agent",
        "communication",
        ["sentiment_scoring", "emotion_detection", "trend_tracking"],
        ["loan_officer", "admin"],
        ["call.started"],
        90,
        "skip",
    ),
    (
        "objection_detection_agent",
        "Objection Detection Agent",
        "communication",
        ["objection_flagging", "hesitation_detection", "concern_classification"],
        ["loan_officer", "admin"],
        ["call.started"],
        90,
        "skip",
    ),
    (
        "compliance_monitor_agent",
        "Compliance Monitor Agent",
        "compliance",
        ["respa_check", "trid_check", "disclosure_verification", "fair_lending_check"],
        ["loan_officer", "admin", "underwriter"],
        ["call.started"],
        90,
        "escalate",
    ),
    (
        "coaching_prompt_agent",
        "Coaching Prompt Agent",
        "communication",
        ["coaching_cards", "talk_track_suggestions", "objection_handling"],
        ["loan_officer"],
        ["call.started"],
        90,
        "skip",
    ),
    (
        "call_summary_agent",
        "Call Summary Agent",
        "communication",
        ["call_summarization", "action_item_extraction", "followup_drafting", "compliance_scoring"],
        ["loan_officer", "processor", "admin"],
        ["call.ended"],
        60,
        "queue",
    ),
    (
        "marketing_manager_agent",
        "Marketing Manager Agent",
        "marketing",
        ["campaign_decomposition", "sub_agent_orchestration", "performance_reporting"],
        ["loan_officer", "marketing", "admin"],
        ["cron.daily", "campaign.triggered"],
        90,
        "queue",
    ),
    (
        "content_factory_agent",
        "Content Factory Agent",
        "marketing",
        ["blog_generation", "social_content", "email_campaign_creation", "brand_voice_matching"],
        ["marketing", "loan_officer", "admin"],
        ["marketing_manager_agent.content_needed"],
        90,
        "skip",
    ),
    (
        "referral_nurture_agent",
        "Referral Nurture Agent",
        "marketing",
        ["partner_communication", "milestone_updates", "co_branded_content", "market_reports"],
        ["loan_officer", "marketing", "admin"],
        ["loan_stage.changed"],
        60,
        "queue",
    ),
    (
        "lead_nurture_agent",
        "Lead Nurture Agent",
        "marketing",
        ["nurture_sequencing", "engagement_scoring", "cadence_adjustment", "drip_management"],
        ["loan_officer", "marketing", "admin"],
        ["lead.created", "lead.engaged"],
        60,
        "queue",
    ),
    (
        "seminar_host_agent",
        "Seminar Host Agent",
        "marketing",
        ["webinar_management", "registration_handling", "followup_distribution", "recording_management"],
        ["loan_officer", "marketing", "admin"],
        ["seminar.scheduled"],
        60,
        "queue",
    ),
    (
        "review_request_agent",
        "Review Request Agent",
        "marketing",
        ["review_sequencing", "platform_targeting", "response_tracking"],
        ["loan_officer", "marketing", "admin"],
        ["loan.closed"],
        30,
        "skip",
    ),
    (
        "listing_partner_agent",
        "Listing Partner Agent",
        "marketing",
        ["realtor_updates", "milestone_notifications", "listing_side_communication"],
        ["loan_officer", "marketing", "admin"],
        ["loan_stage.changed"],
        30,
        "skip",
    ),
    (
        "brand_guard_agent",
        "Brand Guard Agent",
        "compliance",
        ["tone_check", "compliance_language_check", "nmls_verification", "fair_lending_language"],
        ["marketing", "admin"],
        ["content.ready_to_publish"],
        30,
        "error",
    ),
    (
        "bulletin_ingestion_agent",
        "Bulletin Ingestion Agent",
        "underwriting",
        ["bulletin_parsing", "guideline_extraction", "overlay_detection", "vector_indexing"],
        ["admin"],
        ["cron.daily"],
        90,
        "queue",
    ),
    # --- Domain 8: Continual Learning agents ---
    (
        "agent_learning_orchestrator",
        "Agent Learning Orchestrator",
        "operations",
        ["nightly_consolidation_trigger", "weekly_harness_trigger", "correction_rate_monitoring", "training_data_export"],
        ["admin"],
        ["cron.nightly", "cron.weekly", "agent_context_events.batch_ready", "agent.correction_rate_alert"],
        90,
        "escalate",
    ),
    (
        "context_synthesis_agent",
        "Context Synthesis Agent",
        "operations",
        ["pattern_extraction", "preference_learning", "context_update_generation"],
        ["admin"],
        ["consolidation_job.batch_ready"],
        90,
        "queue",
    ),
    (
        "harness_optimization_agent",
        "Harness Optimization Agent",
        "operations",
        ["trace_analysis", "diff_proposal_generation", "regression_evaluation"],
        ["admin"],
        ["cron.weekly"],
        90,
        "queue",
    ),
    (
        "training_data_export_job",
        "Training Data Export Job",
        "operations",
        ["sft_pair_extraction", "jsonl_export", "quality_filtering"],
        ["admin"],
        ["cron.monthly"],
        90,
        "skip",
    ),
]


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

def run_migration(engine):
    """Create all enterprise challenge tables, indexes, and seed agent registry."""
    created = []
    skipped = []
    errors = []

    # -- Phase 1: Create tables --
    with engine.connect() as conn:
        for table_name, create_sql in TABLES:
            try:
                conn.execute(text(create_sql))
                conn.commit()
                created.append(table_name)
                logger.info("Created table (or already exists): %s", table_name)
            except Exception as e:
                logger.warning("Table %s: %s", table_name, e)
                errors.append((table_name, str(e)))
                conn.rollback()

    # -- Phase 2: Create indexes --
    _create_indexes(engine)

    # -- Phase 3: Seed agent registry --
    _seed_agent_registry(engine)

    logger.info(
        "Enterprise migration complete: %d tables created, %d errors",
        len(created),
        len(errors),
    )
    return {"created": created, "errors": errors}


def _create_indexes(engine):
    """Create all performance indexes (IF NOT EXISTS for idempotency)."""
    with engine.connect() as conn:
        for idx_sql in INDEXES:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                # Index may already exist under a different name — not fatal
                logger.debug("Index: %s", e)
                conn.rollback()
    logger.info("Index creation pass complete (%d indexes)", len(INDEXES))


def _seed_agent_registry(engine):
    """Register all 28 required agents (24 core + 4 continual learning).

    Uses INSERT ... ON CONFLICT DO UPDATE so re-running updates existing rows
    without duplicating them.
    """
    upsert_sql = text("""
        INSERT INTO agent_registry (
            agent_id, display_name, version, category,
            capabilities, required_permissions, trigger_events,
            max_retries, timeout_seconds, fallback_behavior,
            is_active, gym_tested,
            created_at, updated_at
        ) VALUES (
            :agent_id, :display_name, '1.0.0', :category,
            :capabilities, :required_permissions, :trigger_events,
            3, :timeout_seconds, :fallback_behavior,
            TRUE, FALSE,
            NOW(), NOW()
        )
        ON CONFLICT (agent_id) DO UPDATE SET
            display_name        = EXCLUDED.display_name,
            category            = EXCLUDED.category,
            capabilities        = EXCLUDED.capabilities,
            required_permissions = EXCLUDED.required_permissions,
            trigger_events      = EXCLUDED.trigger_events,
            timeout_seconds     = EXCLUDED.timeout_seconds,
            fallback_behavior   = EXCLUDED.fallback_behavior,
            updated_at          = NOW()
    """)

    inserted = 0
    with engine.connect() as conn:
        for agent in SEED_AGENTS:
            agent_id, display_name, category, capabilities, required_permissions, trigger_events, timeout_seconds, fallback_behavior = agent
            try:
                conn.execute(upsert_sql, {
                    "agent_id": agent_id,
                    "display_name": display_name,
                    "category": category,
                    "capabilities": capabilities,
                    "required_permissions": required_permissions,
                    "trigger_events": trigger_events,
                    "timeout_seconds": timeout_seconds,
                    "fallback_behavior": fallback_behavior,
                })
                inserted += 1
            except Exception as e:
                logger.warning("Agent seed %s: %s", agent_id, e)
                conn.rollback()
                continue
        conn.commit()

    logger.info("Agent registry seeded: %d/%d agents", inserted, len(SEED_AGENTS))


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    # Add backend/ to path so `from database import ...` works
    sys.path.insert(0, str(Path(__file__).parent.parent))

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    from sqlalchemy import create_engine
    eng = create_engine(DATABASE_URL)
    result = run_migration(eng)

    if result["errors"]:
        logger.error("Errors: %s", result["errors"])
        sys.exit(1)
    else:
        logger.info("All tables created successfully.")
