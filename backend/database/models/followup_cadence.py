"""
Smart Docs Follow-Up Cadence Models

Configurable multi-channel cadence sequences for document follow-up automation.
Supports org-level customization, A/B testing, quiet hours, escalation rules,
and execution tracking.

Models:
    - FollowupCadence: Cadence definition with channel sequence and rules
    - FollowupExecution: Per-borrower cadence execution tracking

Usage:
    from database.models.followup_cadence import (
        FollowupCadence,
        FollowupExecution,
    )

    # Get active cadences for an org
    cadences = db.query(FollowupCadence).filter(
        FollowupCadence.organization_id == org_id,
        FollowupCadence.is_active == True,
    ).all()

    # Get pending executions
    due = db.query(FollowupExecution).filter(
        FollowupExecution.status == "ACTIVE",
        FollowupExecution.next_send_at <= now,
    ).all()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


def utcnow():
    return datetime.now(timezone.utc)


# ============================================================================
# FOLLOWUP CADENCE (definition / template)
# ============================================================================

class FollowupCadence(Base):
    """Configurable follow-up cadence sequence definition.

    Each cadence defines a multi-channel outreach sequence with timing,
    escalation rules, and compliance settings. Cadences can be system
    defaults (is_system=True, organization_id=NULL) or org-customized.

    channel_sequence example:
        [
            {"day": 0, "channel": "email", "template": "initial_doc_request",
             "ab_variant": null},
            {"day": 2, "channel": "sms", "template": "gentle_reminder_sms",
             "ab_variant": null},
            {"day": 5, "channel": "email", "template": "followup_reminder",
             "ab_variant": "B"},
            {"day": 7, "channel": "call", "template": "call_script_docs",
             "ab_variant": null},
            {"day": 10, "channel": "escalate", "template": "escalation_to_lo",
             "ab_variant": null},
        ]
    """
    __tablename__ = "smart_docs_followup_cadences"
    __table_args__ = (
        Index("ix_sd_cadence_org_id", "organization_id"),
        Index("ix_sd_cadence_trigger", "trigger_type"),
        Index("ix_sd_cadence_active", "is_active"),
        Index("ix_sd_cadence_org_trigger", "organization_id", "trigger_type"),
        Index("ix_sd_cadence_org_active", "organization_id", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True,
        comment="NULL for system-default cadences, set for org-customized",
    )

    # Identity
    cadence_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Trigger
    trigger_type = Column(
        String(50), nullable=False,
        comment="DOC_REQUESTED, DOC_OVERDUE, DOC_EXPIRING, CONDITION_ADDED, DOC_REJECTED, MANUAL",
    )

    # Channel sequence (ordered list of steps)
    channel_sequence = Column(
        JSON, nullable=False,
        comment='[{"day": 0, "channel": "email", "template": "...", "ab_variant": null}, ...]',
    )

    # Limits and escalation
    max_attempts = Column(Integer, default=5, comment="Max outreach attempts before stopping")
    escalation_after = Column(Integer, default=3, comment="Escalate to LO after N unanswered attempts")

    # Quiet hours (TCPA + org preference)
    quiet_hours_start = Column(Integer, default=20, comment="Hour (0-23) to stop sending, e.g. 20 = 8 PM")
    quiet_hours_end = Column(Integer, default=8, comment="Hour (0-23) to resume sending, e.g. 8 = 8 AM")

    # Schedule preferences
    weekend_enabled = Column(Boolean, default=False, comment="Allow sending on weekends")
    holiday_aware = Column(Boolean, default=True, comment="Skip federal holidays")

    # A/B testing
    ab_test_enabled = Column(Boolean, default=False)
    ab_test_name = Column(String(100), nullable=True)
    ab_test_split_pct = Column(Float, default=50.0, comment="Percentage allocated to variant B")

    # Status flags
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False, comment="True for platform-default cadences")

    # Analytics (denormalized for quick reads)
    total_executions = Column(Integer, default=0)
    total_responses = Column(Integer, default=0)
    avg_response_time_hours = Column(Float, nullable=True)

    # Audit
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# ============================================================================
# FOLLOWUP EXECUTION (per-borrower tracking)
# ============================================================================

class FollowupExecution(Base):
    """Tracks a single cadence execution for a specific borrower + loan.

    Each row represents one borrower going through one cadence sequence.
    The scheduler queries for rows where status=ACTIVE and next_send_at <= now()
    to determine which messages to send next.

    Status lifecycle:
        ACTIVE -> COMPLETED (borrower responded / all steps done)
        ACTIVE -> CANCELLED (manual cancellation)
        ACTIVE -> ESCALATED (escalation_after reached)
        ACTIVE -> PAUSED (temporary hold, e.g. borrower on vacation)
    """
    __tablename__ = "smart_docs_followup_executions"
    __table_args__ = (
        Index("ix_sd_exec_org_id", "organization_id"),
        Index("ix_sd_exec_loan_id", "loan_id"),
        Index("ix_sd_exec_cadence_id", "cadence_id"),
        Index("ix_sd_exec_status", "status"),
        Index("ix_sd_exec_next_send", "status", "next_send_at"),
        Index("ix_sd_exec_org_status", "organization_id", "status"),
        Index("ix_sd_exec_org_loan", "organization_id", "loan_id"),
        Index("ix_sd_exec_borrower_email", "borrower_email"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )

    # Links
    cadence_id = Column(
        Integer, ForeignKey("smart_docs_followup_cadences.id"), nullable=False,
    )
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    document_request_id = Column(Integer, nullable=True, comment="Specific doc request triggering this")

    # Borrower contact info (denormalized for send-time efficiency)
    borrower_email = Column(String(255), nullable=True)
    borrower_phone = Column(String(20), nullable=True)
    borrower_name = Column(String(255), nullable=True)

    # Progress tracking
    current_step = Column(Integer, default=0, comment="0-based index into cadence channel_sequence")
    status = Column(
        String(20), default="ACTIVE",
        comment="ACTIVE, COMPLETED, CANCELLED, ESCALATED, PAUSED",
    )

    # Timing
    last_sent_at = Column(DateTime, nullable=True)
    next_send_at = Column(DateTime, nullable=True, index=True)
    paused_at = Column(DateTime, nullable=True)
    pause_reason = Column(String(255), nullable=True)

    # Attempt tracking
    attempts_made = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0, comment="Consecutive delivery failures")

    # Response tracking
    response_received = Column(Boolean, default=False)
    response_type = Column(
        String(50), nullable=True,
        comment="doc_uploaded, email_reply, link_clicked, call_back, appointment_booked",
    )
    response_at = Column(DateTime, nullable=True)

    # Engagement metrics (per-execution)
    emails_opened = Column(Integer, default=0)
    links_clicked = Column(Integer, default=0)
    docs_uploaded = Column(Integer, default=0)

    # A/B variant assignment
    ab_variant = Column(String(1), nullable=True, comment="A or B")

    # Escalation
    escalated_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    escalated_at = Column(DateTime, nullable=True)
    escalation_note = Column(Text, nullable=True)

    # Execution log (append-only history of each step taken)
    execution_log = Column(
        JSON, default=list,
        comment='[{"step": 0, "channel": "email", "sent_at": "...", "status": "delivered", "template": "..."}, ...]',
    )

    # Audit
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(255), nullable=True)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "FollowupCadence",
    "FollowupExecution",
]
