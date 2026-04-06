"""
Loan File Collaborator & User Onboarding State Models

Domain 1: Enterprise Team Onboarding & Collaborative File Access

Tables:
- loan_file_collaborators: Tracks which users have access to which loan files,
  with role-based permissions and per-file overrides.  Enables multi-user
  collaboration on a single loan file (processor, underwriter, closer, etc.).
- user_onboarding_state: Tracks each user's progress through the AI-guided
  onboarding flow, linking to the agent run that is driving the experience.

Usage:
    from database.models.file_collaborator import LoanFileCollaborator, UserOnboardingState

    # Grant a processor access to a loan file
    collab = LoanFileCollaborator(
        organization_id=1,
        file_id=42,
        user_id=7,
        role="processor",
        assigned_by=3,
    )
    db.add(collab)
    db.commit()

    # Track onboarding progress
    state = UserOnboardingState(
        organization_id=1,
        user_id=7,
        step="connect_email",
        step_number=2,
        status="in_progress",
    )
    db.add(state)
    db.commit()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, ForeignKey,
    Index, UniqueConstraint,
)

from db import Base


class LoanFileCollaborator(Base):
    """
    Maps users to loan files with role-based access control.

    Each row grants a single user access to a single loan file within
    the same organization.  The ``role`` column controls default
    permissions (e.g. processors can update conditions, underwriters
    can approve/deny) while ``permissions_override`` allows per-file
    customisation without touching the role definition.

    Roles:
        admin, branch_manager, loan_officer, processor,
        underwriter, closer, marketing, read_only
    """
    __tablename__ = "loan_file_collaborators"
    __table_args__ = (
        UniqueConstraint("file_id", "user_id", name="uq_file_collaborator_file_user"),
        Index("ix_lfc_org_file", "organization_id", "file_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant isolation
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )

    # The loan file this access record applies to
    file_id = Column(
        Integer, ForeignKey("loans.id"), nullable=False, index=True,
    )

    # The user being granted access
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )

    # Role on this file (determines default permission set)
    role = Column(
        String(50), nullable=False, default="read_only",
    )  # admin | branch_manager | loan_officer | processor | underwriter | closer | marketing | read_only

    # Optional per-file permission overrides (JSONB)
    # e.g. {"can_edit_conditions": true, "can_view_financials": false}
    permissions_override = Column(JSON, nullable=True)

    # When and by whom the access was granted
    assigned_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    assigned_by = Column(
        Integer, ForeignKey("users.id"), nullable=True,
    )

    # Soft-delete / deactivation
    is_active = Column(Boolean, nullable=False, default=True)

    # Whether the user receives notifications for this file
    notify = Column(Boolean, nullable=False, default=True)

    # Last time the user opened / interacted with this file
    last_accessed_at = Column(DateTime, nullable=True)


class UserOnboardingState(Base):
    """
    Tracks a user's progress through the AI-guided onboarding flow.

    Each user has at most one active onboarding state record.  The
    ``agent_run_id`` links back to the agent_run_log so the onboarding
    agent can resume where the user left off.

    Steps (default 6):
        1. welcome / profile setup
        2. connect_email (Microsoft Graph OAuth)
        3. connect_calendar
        4. import_pipeline (Encompass / Salesforce / CSV)
        5. configure_notifications
        6. first_ai_interaction (guided Aria demo)

    Status values: pending, in_progress, completed, failed
    """
    __tablename__ = "user_onboarding_state"
    __table_args__ = (
        Index("ix_uos_org_user", "organization_id", "user_id"),
        Index("ix_uos_status", "status"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant isolation
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )

    # One onboarding record per user (unique)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True,
    )

    # Current step
    step = Column(String(100), nullable=False, default="welcome")
    step_number = Column(Integer, nullable=False, default=1)
    total_steps = Column(Integer, nullable=False, default=6)

    # Completion timestamp (set when status → completed)
    completed_at = Column(DateTime, nullable=True)

    # Links to the agent_run_log entry driving this onboarding session
    agent_run_id = Column(String(255), nullable=True)

    # Overall status
    status = Column(
        String(20), nullable=False, default="pending",
    )  # pending | in_progress | completed | failed

    # Arbitrary metadata (step-specific context, error details, etc.)
    onboarding_metadata = Column("metadata", JSON, nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create the loan_file_collaborators and user_onboarding_state tables if they don't exist."""
    LoanFileCollaborator.__table__.create(engine, checkfirst=True)
    UserOnboardingState.__table__.create(engine, checkfirst=True)
