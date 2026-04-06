"""
Agent Registry — formal registration of all AI agents with governance metadata.

Tables:
- agent_registry: Every agent must be registered here before production use.
- agent_run_log: Immutable log of every agent execution (inputs, outputs, tokens, latency).
- harness_change_proposals: Tracks harness optimization proposals pending Admin review.

Usage:
    from database.models.agent_registry import AgentRegistryEntry, AgentRunLog, HarnessChangeProposal
    from database.models.agent_registry import seed_required_agents

    # Seed all 24 required agents at startup
    seed_required_agents(db_session)
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Text, Index,
)
from db import Base


class AgentRegistryEntry(Base):
    """Every agent must be registered here before production use."""
    __tablename__ = "agent_registry"
    __table_args__ = (
        Index("ix_agent_registry_category", "category"),
        Index("ix_agent_registry_is_active", "is_active"),
        {"extend_existing": True},
    )

    agent_id = Column(String, primary_key=True)  # e.g. 'underwriter_audit_agent_v2'
    display_name = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1.0.0")  # semver
    category = Column(String, nullable=False)  # operations|marketing|compliance|communication|underwriting|learning
    capabilities = Column(JSON, default=[])  # list of capability strings
    required_permissions = Column(JSON, default=[])  # RBAC roles that can invoke
    trigger_events = Column(JSON, default=[])  # events that auto-invoke
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=90)
    fallback_behavior = Column(String, nullable=False, default="escalate")  # skip|escalate|queue|error
    langgraph_graph = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    gym_tested = Column(Boolean, default=False)  # must be True before production
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentRunLog(Base):
    """Immutable log of every agent execution."""
    __tablename__ = "agent_run_log"
    __table_args__ = (
        Index("ix_agent_run_log_agent_id", "agent_id"),
        Index("ix_agent_run_log_org", "organization_id"),
        Index("ix_agent_run_log_status", "status"),
        Index("ix_agent_run_log_started", "started_at"),
        {"extend_existing": True},
    )

    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, index=True)  # references agent_registry
    file_id = Column(Integer, nullable=True)  # loan file if applicable
    user_id = Column(Integer, nullable=True)
    organization_id = Column(Integer, nullable=True, index=True)
    trigger_event = Column(String, nullable=True)
    input_snapshot = Column(JSON, nullable=True)
    output_snapshot = Column(JSON, nullable=True)
    findings = Column(JSON, nullable=True)
    status = Column(String, default="running")  # running|completed|failed|timed_out
    latency_ms = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class HarnessChangeProposal(Base):
    """Tracks harness optimization proposals pending Admin review."""
    __tablename__ = "harness_change_proposals"
    __table_args__ = (
        Index("ix_harness_proposals_agent", "agent_id"),
        Index("ix_harness_proposals_status", "status"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False, index=True)
    analysis_summary = Column(JSON, nullable=True)
    proposed_changes = Column(JSON, nullable=True)
    status = Column(String, default="pending_review")  # pending_review|approved|rejected|deployed
    gym_tested = Column(Boolean, default=False)
    gym_results = Column(JSON, nullable=True)
    reviewed_by = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create agent registry tables if they don't exist."""
    AgentRegistryEntry.__table__.create(engine, checkfirst=True)
    AgentRunLog.__table__.create(engine, checkfirst=True)
    HarnessChangeProposal.__table__.create(engine, checkfirst=True)


# ---------------------------------------------------------------------------
# 24 Required agents — from Enterprise Challenge spec
# ---------------------------------------------------------------------------

REQUIRED_AGENTS = [
    # --- Domain 1: Enterprise Team Onboarding ---
    {
        "agent_id": "user_provisioning_agent",
        "display_name": "User Provisioning Agent",
        "version": "1.0.0",
        "category": "operations",
        "capabilities": ["create_user_profile", "assign_default_role", "set_file_queue", "provision_smart_docs_portal", "send_welcome_comms", "enroll_onboarding_curriculum"],
        "required_permissions": ["Admin"],
        "trigger_events": ["user.created"],
        "max_retries": 3,
        "timeout_seconds": 30,
        "fallback_behavior": "escalate",
        "langgraph_graph": "user_provisioning_graph",
    },
    {
        "agent_id": "smart_docs_provisioning_agent",
        "display_name": "Smart Docs Provisioning Agent",
        "version": "1.0.0",
        "category": "operations",
        "capabilities": ["create_purl_token", "generate_checklist", "send_portal_link", "freshness_validation", "screenshot_rejection"],
        "required_permissions": ["Admin", "Loan Officer", "Processor"],
        "trigger_events": ["user.created", "borrower.added"],
        "max_retries": 3,
        "timeout_seconds": 10,
        "fallback_behavior": "escalate",
        "langgraph_graph": "smart_docs_provisioning_graph",
    },

    # --- Domain 2: Unified Communication Threading ---
    {
        "agent_id": "communication_orchestrator",
        "display_name": "Communication Orchestrator",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["route_inbound_message", "classify_intent", "match_to_file", "notify_collaborators"],
        "required_permissions": ["Admin", "Loan Officer", "Processor"],
        "trigger_events": ["sms.inbound", "email.inbound"],
        "max_retries": 3,
        "timeout_seconds": 15,
        "fallback_behavior": "queue",
        "langgraph_graph": "communication_orchestrator_graph",
    },
    {
        "agent_id": "communication_draft_agent",
        "display_name": "Communication Draft Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["draft_sms_reply", "draft_email_reply", "tone_matching", "context_injection"],
        "required_permissions": ["Admin", "Loan Officer", "Processor"],
        "trigger_events": ["communication_orchestrator.message_received"],
        "max_retries": 2,
        "timeout_seconds": 30,
        "fallback_behavior": "skip",
        "langgraph_graph": "communication_draft_graph",
    },

    # --- Domain 4: Mobile Call Intelligence (5 parallel agents) ---
    {
        "agent_id": "call_intelligence_pipeline",
        "display_name": "Call Intelligence Pipeline",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["orchestrate_call_agents", "parallel_dispatch", "aggregate_results"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["call.started"],
        "max_retries": 2,
        "timeout_seconds": 300,
        "fallback_behavior": "escalate",
        "langgraph_graph": "call_intelligence_graph",
    },
    {
        "agent_id": "live_transcription_agent",
        "display_name": "Live Transcription Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["realtime_stt", "word_level_timestamps", "speaker_diarization"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["call.started"],
        "max_retries": 1,
        "timeout_seconds": 300,
        "fallback_behavior": "error",
        "langgraph_graph": "live_transcription_graph",
    },
    {
        "agent_id": "sentiment_analysis_agent",
        "display_name": "Sentiment Analysis Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["borrower_sentiment_scoring", "sentiment_trend", "emotional_shift_detection"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["call.started"],
        "max_retries": 2,
        "timeout_seconds": 300,
        "fallback_behavior": "skip",
        "langgraph_graph": "sentiment_analysis_graph",
    },
    {
        "agent_id": "objection_detection_agent",
        "display_name": "Objection Detection Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["objection_flagging", "hesitation_detection", "rebuttal_suggestion"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["call.started"],
        "max_retries": 2,
        "timeout_seconds": 300,
        "fallback_behavior": "skip",
        "langgraph_graph": "objection_detection_graph",
    },
    {
        "agent_id": "compliance_monitor_agent",
        "display_name": "Compliance Monitor Agent",
        "version": "1.0.0",
        "category": "compliance",
        "capabilities": ["respa_disclosure_check", "trid_disclosure_check", "fair_lending_audit", "required_language_verification"],
        "required_permissions": ["Admin", "Loan Officer", "Processor"],
        "trigger_events": ["call.started"],
        "max_retries": 2,
        "timeout_seconds": 300,
        "fallback_behavior": "escalate",
        "langgraph_graph": "compliance_monitor_graph",
    },
    {
        "agent_id": "coaching_prompt_agent",
        "display_name": "Coaching Prompt Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["coaching_card_generation", "realtime_lo_guidance", "best_practice_prompt"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["call.started"],
        "max_retries": 1,
        "timeout_seconds": 300,
        "fallback_behavior": "skip",
        "langgraph_graph": "coaching_prompt_graph",
    },
    {
        "agent_id": "call_summary_agent",
        "display_name": "Call Summary Agent",
        "version": "1.0.0",
        "category": "communication",
        "capabilities": ["call_summary_generation", "action_item_extraction", "followup_draft", "compliance_scoring"],
        "required_permissions": ["Admin", "Loan Officer", "Processor"],
        "trigger_events": ["call.ended"],
        "max_retries": 3,
        "timeout_seconds": 90,
        "fallback_behavior": "queue",
        "langgraph_graph": "call_summary_graph",
    },

    # --- Domain 5: Autonomous AI Underwriter ---
    {
        "agent_id": "underwriter_audit_agent",
        "display_name": "Underwriter Audit Agent",
        "version": "1.0.0",
        "category": "underwriting",
        "capabilities": ["income_analysis", "asset_verification", "credit_analysis", "ltv_cltv_calculation", "dti_calculation", "guideline_crosscheck", "investor_overlay_check", "condition_generation"],
        "required_permissions": ["Admin", "Underwriter", "Processor"],
        "trigger_events": ["document.uploaded", "loan_data.changed", "cron.nightly"],
        "max_retries": 3,
        "timeout_seconds": 90,
        "fallback_behavior": "escalate",
        "langgraph_graph": "underwriter_audit_graph",
    },
    {
        "agent_id": "deal_breaker_radar",
        "display_name": "Deal Breaker Radar",
        "version": "1.0.0",
        "category": "underwriting",
        "capabilities": ["hard_stop_detection", "soft_flag_detection", "severity_classification", "remediation_suggestion"],
        "required_permissions": ["Admin", "Underwriter", "Processor", "Loan Officer"],
        "trigger_events": ["underwriter_audit_agent.completed"],
        "max_retries": 2,
        "timeout_seconds": 30,
        "fallback_behavior": "escalate",
        "langgraph_graph": "deal_breaker_radar_graph",
    },
    {
        "agent_id": "turn_down_agent",
        "display_name": "Turn Down Agent",
        "version": "1.0.0",
        "category": "compliance",
        "capabilities": ["adverse_action_notice_drafting", "denial_reason_classification", "compliance_routing"],
        "required_permissions": ["Admin", "Underwriter"],
        "trigger_events": ["deal_breaker_radar.hard_stop_detected"],
        "max_retries": 3,
        "timeout_seconds": 60,
        "fallback_behavior": "escalate",
        "langgraph_graph": "turn_down_graph",
    },
    {
        "agent_id": "bulletin_ingestion_agent",
        "display_name": "Bulletin Ingestion Agent",
        "version": "1.0.0",
        "category": "underwriting",
        "capabilities": ["bulletin_parsing", "guideline_update_detection", "overlay_extraction", "rag_index_update"],
        "required_permissions": ["Admin"],
        "trigger_events": ["cron.daily"],
        "max_retries": 3,
        "timeout_seconds": 120,
        "fallback_behavior": "queue",
        "langgraph_graph": "bulletin_ingestion_graph",
    },

    # --- Domain 6: Autonomous Operations Manager ---
    {
        "agent_id": "operations_manager_agent",
        "display_name": "Operations Manager Agent",
        "version": "1.0.0",
        "category": "operations",
        "capabilities": ["sla_enforcement", "workload_balancing", "pipeline_analytics", "bottleneck_detection", "team_performance_scoring", "compliance_calendar", "vendor_management", "ops_report_generation"],
        "required_permissions": ["Admin", "Branch Manager"],
        "trigger_events": ["cron.hourly", "sla.at_risk"],
        "max_retries": 3,
        "timeout_seconds": 120,
        "fallback_behavior": "escalate",
        "langgraph_graph": "operations_manager_graph",
    },

    # --- Domain 7: Autonomous Marketing Manager & Assistants ---
    {
        "agent_id": "marketing_manager_agent",
        "display_name": "Marketing Manager Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["campaign_decomposition", "sub_agent_dispatch", "performance_reporting", "budget_tracking"],
        "required_permissions": ["Admin", "Loan Officer", "Marketing"],
        "trigger_events": ["cron.daily", "campaign.triggered"],
        "max_retries": 3,
        "timeout_seconds": 120,
        "fallback_behavior": "queue",
        "langgraph_graph": "marketing_manager_graph",
    },
    {
        "agent_id": "content_factory_agent",
        "display_name": "Content Factory Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["blog_generation", "social_media_content", "email_campaign_content", "brand_voice_matching"],
        "required_permissions": ["Admin", "Loan Officer", "Marketing"],
        "trigger_events": ["marketing_manager_agent.content_needed"],
        "max_retries": 3,
        "timeout_seconds": 90,
        "fallback_behavior": "queue",
        "langgraph_graph": "content_factory_graph",
    },
    {
        "agent_id": "referral_nurture_agent",
        "display_name": "Referral Nurture Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["partner_relationship_management", "milestone_updates", "cobranded_content", "market_report_distribution"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["loan_stage.changed"],
        "max_retries": 3,
        "timeout_seconds": 60,
        "fallback_behavior": "queue",
        "langgraph_graph": "referral_nurture_graph",
    },
    {
        "agent_id": "lead_nurture_agent",
        "display_name": "Lead Nurture Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["nurture_sequence_management", "engagement_scoring", "cadence_adjustment", "12_month_automation"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["lead.created", "lead.engaged"],
        "max_retries": 3,
        "timeout_seconds": 60,
        "fallback_behavior": "skip",
        "langgraph_graph": "lead_nurture_graph",
    },
    {
        "agent_id": "seminar_host_agent",
        "display_name": "Seminar Host Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["webinar_management", "registration_handling", "followup_automation", "recording_distribution"],
        "required_permissions": ["Admin", "Loan Officer", "Marketing"],
        "trigger_events": ["seminar.scheduled"],
        "max_retries": 3,
        "timeout_seconds": 90,
        "fallback_behavior": "queue",
        "langgraph_graph": "seminar_host_graph",
    },
    {
        "agent_id": "review_request_agent",
        "display_name": "Review Request Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["review_request_sequencing", "google_review_prompt", "zillow_review_prompt", "response_rate_tracking"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["loan.closed"],
        "max_retries": 3,
        "timeout_seconds": 30,
        "fallback_behavior": "skip",
        "langgraph_graph": "review_request_graph",
    },
    {
        "agent_id": "listing_partner_agent",
        "display_name": "Listing Partner Agent",
        "version": "1.0.0",
        "category": "marketing",
        "capabilities": ["realtor_milestone_updates", "stage_notification", "cobranded_status_reports"],
        "required_permissions": ["Admin", "Loan Officer"],
        "trigger_events": ["loan_stage.changed"],
        "max_retries": 3,
        "timeout_seconds": 30,
        "fallback_behavior": "skip",
        "langgraph_graph": "listing_partner_graph",
    },
    {
        "agent_id": "brand_guard_agent",
        "display_name": "Brand Guard Agent",
        "version": "1.0.0",
        "category": "compliance",
        "capabilities": ["tone_check", "compliance_language_check", "nmls_verification", "fair_lending_language_check"],
        "required_permissions": ["Admin", "Marketing"],
        "trigger_events": ["content.ready_to_publish"],
        "max_retries": 2,
        "timeout_seconds": 30,
        "fallback_behavior": "escalate",
        "langgraph_graph": "brand_guard_graph",
    },
]


def seed_required_agents(db_session) -> int:
    """
    Seed (upsert) all 24 required agents into the agent_registry table.

    Uses merge() so this is idempotent — safe to call on every startup.
    Returns count of agents registered.
    """
    count = 0
    for agent_def in REQUIRED_AGENTS:
        existing = db_session.query(AgentRegistryEntry).filter_by(
            agent_id=agent_def["agent_id"]
        ).first()

        if existing:
            # Update mutable fields but preserve is_active / gym_tested state
            existing.display_name = agent_def["display_name"]
            existing.version = agent_def["version"]
            existing.category = agent_def["category"]
            existing.capabilities = agent_def["capabilities"]
            existing.required_permissions = agent_def["required_permissions"]
            existing.trigger_events = agent_def["trigger_events"]
            existing.max_retries = agent_def["max_retries"]
            existing.timeout_seconds = agent_def["timeout_seconds"]
            existing.fallback_behavior = agent_def["fallback_behavior"]
            existing.langgraph_graph = agent_def.get("langgraph_graph")
            existing.updated_at = datetime.now(timezone.utc)
        else:
            entry = AgentRegistryEntry(
                agent_id=agent_def["agent_id"],
                display_name=agent_def["display_name"],
                version=agent_def["version"],
                category=agent_def["category"],
                capabilities=agent_def["capabilities"],
                required_permissions=agent_def["required_permissions"],
                trigger_events=agent_def["trigger_events"],
                max_retries=agent_def["max_retries"],
                timeout_seconds=agent_def["timeout_seconds"],
                fallback_behavior=agent_def["fallback_behavior"],
                langgraph_graph=agent_def.get("langgraph_graph"),
                is_active=True,
                gym_tested=False,
            )
            db_session.add(entry)
        count += 1

    db_session.commit()
    return count
