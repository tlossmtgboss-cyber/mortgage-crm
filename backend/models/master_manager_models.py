"""
Master Manager Platform Models
Talent & Capacity OS for Mortgage Operations

Multi-tenant design with organization_id on all tables.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, Float,
    ForeignKey, JSON, Index, UniqueConstraint, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from enum import Enum
import uuid

from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class CapacityStatus(str, Enum):
    AVAILABLE = "available"
    NEAR_CAPACITY = "near_capacity"
    AT_CAPACITY = "at_capacity"
    OVER_CAPACITY = "over_capacity"


class AvailabilityStatus(str, Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TRAINING = "training"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class TalentStateEnum(str, Enum):
    ACTIVE = "active"
    NEAR_CAPACITY = "near_capacity"
    OVER_CAPACITY = "over_capacity"
    BENCH_WARM = "bench_warm"
    BENCH_TRAINING = "bench_training"
    PROMOTION_READY = "promotion_ready"
    AT_RISK = "at_risk"
    EXIT_LIKELY = "exit_likely"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    NEW_HIRE = "new_hire"


class RoleCategory(str, Enum):
    REVENUE = "revenue"
    OPERATIONS = "operations"
    SPECIALIZED = "specialized"
    MANAGEMENT = "management"


class PerformanceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class CandidateStatus(str, Enum):
    NEW = "new"
    SCREENING = "screening"
    PHONE_SCREEN = "phone_screen"
    INTERVIEW = "interview"
    ASSESSMENT = "assessment"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class CandidatePlacement(str, Enum):
    IMMEDIATE = "immediate"
    BENCH_TRAIN = "bench_train"
    FUTURE_FIT = "future_fit"
    REFERRAL_ONLY = "referral_only"
    DO_NOT_PLACE = "do_not_place"


# =============================================================================
# ROLE DEFINITION MODEL
# =============================================================================

class RoleDefinition(Base):
    """
    Role intelligence - defines expectations and standards per role.
    This extends the existing onboarding_roles with operational metrics.
    """
    __tablename__ = "mm_role_definitions"
    __table_args__ = (
        UniqueConstraint('organization_id', 'role_name', name='uix_mm_role_org_name'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Role Identity
    role_name = Column(String(100), nullable=False, index=True)
    role_category = Column(String(30), default=RoleCategory.OPERATIONS.value)
    description = Column(Text)

    # Links to existing onboarding role
    onboarding_role_id = Column(Integer, ForeignKey("onboarding_roles.id"), nullable=True)

    # Capacity Standards
    default_max_files = Column(Integer, default=25)
    default_max_leads = Column(Integer, default=50)
    default_max_tasks_daily = Column(Integer, default=30)

    # Performance Expectations
    expected_throughput = Column(JSON, default=dict)
    # Structure: {
    #   "files_per_month": 8,
    #   "leads_per_week": 20,
    #   "tasks_per_day": 25,
    #   "avg_cycle_time_days": 30
    # }

    error_tolerance_pct = Column(Float, default=2.0)  # Max acceptable error rate
    learning_curve_days = Column(Integer, default=90)  # Expected ramp time

    # Risk Profile
    replacement_difficulty = Column(Integer, default=5)  # 1-10 scale
    is_single_point_failure_risk = Column(Boolean, default=False)

    # Skills & Requirements
    required_skills = Column(JSON, default=list)
    # Structure: ["LOS proficiency", "compliance knowledge", "communication"]

    certifications_required = Column(JSON, default=list)
    # Structure: ["NMLS", "state_license_CA", etc.]

    # Failure Patterns (for early warning)
    common_failure_modes = Column(JSON, default=list)
    # Structure: ["overwhelm_at_volume", "accuracy_under_pressure", "communication_gaps"]

    # Salary Range (for profitability calculations)
    salary_range_min = Column(Integer)
    salary_range_max = Column(Integer)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# TALENT CAPACITY MODEL
# =============================================================================

class TalentCapacity(Base):
    """
    Real-time capacity tracking for each team member.
    Updated by background jobs and triggers.
    """
    __tablename__ = "mm_talent_capacity"
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', name='uix_mm_capacity_org_user'),
        Index('ix_mm_capacity_status', 'capacity_status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_definition_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)

    # Capacity Configuration (can override role defaults)
    max_files_concurrent = Column(Integer, default=25)
    max_leads_concurrent = Column(Integer, default=50)
    max_tasks_daily = Column(Integer, default=30)

    # Current State (updated by background jobs)
    current_file_count = Column(Integer, default=0)
    current_lead_count = Column(Integer, default=0)
    current_task_count = Column(Integer, default=0)

    # Derived Metrics
    file_capacity_pct = Column(Float, default=0.0)
    lead_capacity_pct = Column(Float, default=0.0)
    task_capacity_pct = Column(Float, default=0.0)
    overall_capacity_pct = Column(Float, default=0.0)  # Weighted composite

    capacity_status = Column(String(20), default=CapacityStatus.AVAILABLE.value, index=True)

    # Risk Indicators
    burnout_risk_score = Column(Float, default=0.0)  # 0-100
    attrition_risk_score = Column(Float, default=0.0)  # 0-100

    # Availability
    is_available = Column(Boolean, default=True, index=True)
    availability_status = Column(String(20), default=AvailabilityStatus.ACTIVE.value)
    return_date = Column(Date, nullable=True)
    availability_notes = Column(Text)

    # Assignment Lock (prevent over-assignment during high load)
    is_locked_for_assignment = Column(Boolean, default=False)
    locked_until = Column(DateTime, nullable=True)
    lock_reason = Column(String(255))

    # Timestamps
    last_calculated_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    role_definition = relationship("RoleDefinition", foreign_keys=[role_definition_id])


# =============================================================================
# TALENT STATE MODEL
# =============================================================================

class TalentState(Base):
    """
    Human state machine - tracks the operational state of each team member.
    States: active, near_capacity, over_capacity, bench_warm, bench_training,
            promotion_ready, at_risk, exit_likely, on_leave, suspended, new_hire
    """
    __tablename__ = "mm_talent_state"
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', name='uix_mm_state_org_user'),
        Index('ix_mm_state_state', 'state'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Current State
    state = Column(String(30), nullable=False, default=TalentStateEnum.NEW_HIRE.value, index=True)
    state_reason = Column(String(255))
    state_changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    state_changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # New Hire / Ramp Tracking
    is_new_hire = Column(Boolean, default=True)
    is_in_ramp = Column(Boolean, default=True)
    hire_date = Column(Date)
    ramp_day = Column(Integer, default=0)  # Days since hire
    ramp_completion_date = Column(Date)  # Expected ramp completion
    ramp_progress_pct = Column(Float, default=0.0)  # 0-100%

    # Promotion Track
    promotion_eligible = Column(Boolean, default=False)
    promotion_readiness_score = Column(Float)  # 0-100
    target_role_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)
    last_promotion_at = Column(Date)
    promotion_blocked_reason = Column(String(255))

    # Performance Improvement Plan
    has_active_pip = Column(Boolean, default=False)
    pip_start_date = Column(Date)
    pip_end_date = Column(Date)
    pip_reason = Column(Text)
    pip_goals = Column(JSON)

    # Exit Risk
    exit_risk_level = Column(String(20))  # low, medium, high, critical
    exit_risk_factors = Column(JSON)  # List of contributing factors
    retention_actions = Column(JSON)  # Recommended actions

    # Manager
    manager_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    manager = relationship("User", foreign_keys=[manager_user_id])
    target_role = relationship("RoleDefinition", foreign_keys=[target_role_id])


# =============================================================================
# TALENT STATE HISTORY
# =============================================================================

class TalentStateHistory(Base):
    """
    Audit trail for state transitions.
    """
    __tablename__ = "mm_talent_state_history"
    __table_args__ = (
        Index('ix_mm_state_history_user', 'user_id'),
        Index('ix_mm_state_history_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    previous_state = Column(String(30))
    new_state = Column(String(30), nullable=False)
    reason = Column(Text)
    changed_by = Column(Integer, ForeignKey("users.id"))

    # Snapshot of metrics at time of change
    capacity_pct_at_change = Column(Float)
    performance_score_at_change = Column(Float)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# =============================================================================
# TALENT PERFORMANCE MODEL
# =============================================================================

class TalentPerformance(Base):
    """
    Performance metrics snapshots - rolled up daily, weekly, monthly.
    """
    __tablename__ = "mm_talent_performance"
    __table_args__ = (
        UniqueConstraint('organization_id', 'user_id', 'period_start', 'period_type',
                        name='uix_mm_perf_org_user_period'),
        Index('ix_mm_perf_period', 'period_start', 'period_type'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Period
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(20), nullable=False)  # daily, weekly, monthly, quarterly

    # Volume Metrics
    files_in_pipeline = Column(Integer, default=0)
    files_funded = Column(Integer, default=0)
    files_cancelled = Column(Integer, default=0)
    leads_handled = Column(Integer, default=0)
    leads_converted = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_overdue = Column(Integer, default=0)

    # Quality Metrics
    error_count = Column(Integer, default=0)
    error_rate_pct = Column(Float, default=0.0)
    rework_count = Column(Integer, default=0)
    rework_rate_pct = Column(Float, default=0.0)

    # Satisfaction Metrics
    borrower_nps = Column(Float)
    borrower_csat = Column(Float)
    lo_satisfaction = Column(Float)  # Internal satisfaction from LOs

    # Efficiency Metrics
    avg_task_duration_mins = Column(Float)
    avg_file_cycle_time_days = Column(Float)
    sla_compliance_pct = Column(Float)
    on_time_completion_pct = Column(Float)

    # Communication Metrics
    avg_response_time_mins = Column(Float)
    communication_score = Column(Float)  # 0-100
    emails_sent = Column(Integer, default=0)
    calls_made = Column(Integer, default=0)

    # Composite Scores
    overall_score = Column(Float)  # Weighted composite 0-100
    performance_grade = Column(String(2))  # A, B, C, D, F

    # Benchmarks
    vs_team_avg_pct = Column(Float)  # % vs team average
    vs_role_benchmark_pct = Column(Float)  # % vs role benchmark
    percentile_rank = Column(Integer)  # 1-100

    # Trends
    trend_direction = Column(String(10))  # improving, stable, declining
    trend_change_pct = Column(Float)  # % change from previous period

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])


# =============================================================================
# CAPACITY ALERTS
# =============================================================================

class CapacityAlert(Base):
    """
    Alerts generated by the capacity and risk detection system.
    """
    __tablename__ = "mm_capacity_alerts"
    __table_args__ = (
        Index('ix_mm_alerts_org_status', 'organization_id', 'status'),
        Index('ix_mm_alerts_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Alert Type
    alert_type = Column(String(50), nullable=False, index=True)
    # Types: over_capacity, near_capacity, burnout_risk, attrition_risk,
    #        spof_detected, coverage_gap, performance_decline, sla_breach

    severity = Column(String(20), nullable=False)  # info, warning, critical

    # Target
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    role_definition_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)

    # Content
    title = Column(String(255), nullable=False)
    description = Column(Text)
    metrics_snapshot = Column(JSON)  # Relevant metrics at time of alert

    # Recommendations
    recommended_actions = Column(JSON)  # List of suggested actions

    # Status
    status = Column(String(20), default="open", index=True)  # open, acknowledged, resolved, dismissed
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])


# =============================================================================
# COVERAGE MAP
# =============================================================================

class CoverageMap(Base):
    """
    Tracks coverage and backup assignments for roles.
    Identifies single points of failure.
    """
    __tablename__ = "mm_coverage_map"
    __table_args__ = (
        UniqueConstraint('organization_id', 'primary_user_id', 'role_definition_id',
                        name='uix_mm_coverage_org_user_role'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Primary
    primary_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_definition_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=False)

    # Backups (ordered by priority)
    backup_user_ids = Column(JSON, default=list)  # List of user IDs

    # Cross-training status
    cross_trained_users = Column(JSON, default=list)  # Users who can cover but aren't primary backup

    # Risk Assessment
    is_single_point_failure = Column(Boolean, default=False)
    coverage_score = Column(Float)  # 0-100, higher is better

    # Notes
    coverage_notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    primary_user = relationship("User", foreign_keys=[primary_user_id])
    role_definition = relationship("RoleDefinition", foreign_keys=[role_definition_id])


# =============================================================================
# CANDIDATE MODEL (For Recruiting - Phase 2)
# =============================================================================

class Candidate(Base):
    """
    Candidate tracking for recruiting pipeline.
    """
    __tablename__ = "mm_candidates"
    __table_args__ = (
        UniqueConstraint('organization_id', 'email', name='uix_mm_candidate_org_email'),
        Index('ix_mm_candidate_status', 'status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Basic Info
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20))

    # Source Tracking
    source = Column(String(50))  # referral, career_page, linkedin, indeed, recruiter
    referrer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    campaign_id = Column(String(100))
    utm_source = Column(String(100))
    utm_medium = Column(String(100))
    utm_campaign = Column(String(100))

    # Target Role
    target_role_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)
    target_role_name = Column(String(100))  # Denormalized for display

    # Pipeline Status
    status = Column(String(30), default=CandidateStatus.NEW.value, index=True)
    status_changed_at = Column(DateTime)
    status_changed_by = Column(Integer, ForeignKey("users.id"))

    # Placement Recommendation
    placement_recommendation = Column(String(30))  # immediate, bench_train, future_fit, etc.

    # Talent Profile (Intelligence Layer)
    talent_profile = Column(JSON, default=dict)
    # Structure: {
    #   "experience_depth": 0-100,
    #   "cognitive_load_tolerance": 0-100,
    #   "speed_vs_accuracy_bias": "speed" | "accuracy" | "balanced",
    #   "coachability_index": 0-100,
    #   "system_adherence_score": 0-100,
    #   "communication_style": "D" | "I" | "S" | "C"
    # }

    # Experience
    years_experience = Column(Integer)
    years_mortgage_experience = Column(Integer)
    has_mortgage_experience = Column(Boolean, default=False)
    previous_companies = Column(JSON)  # List of {company, role, duration}
    licenses = Column(JSON)  # NMLS, state licenses

    # Resume/Application
    resume_url = Column(Text)
    cover_letter = Column(Text)
    linkedin_url = Column(String(255))

    # Assessment Scores (populated after assessments)
    vetting_score = Column(Float)
    behavioral_score = Column(Float)
    technical_score = Column(Float)
    culture_fit_score = Column(Float)
    overall_score = Column(Float)

    # Behavioral Signals (predictive)
    time_to_complete_app_mins = Column(Integer)
    instruction_following_score = Column(Float)
    revision_behavior_score = Column(Float)

    # Interview
    interview_scheduled_at = Column(DateTime)
    interview_completed_at = Column(DateTime)
    interview_notes = Column(Text)
    interview_score = Column(Float)

    # Offer
    offer_extended_at = Column(DateTime)
    offer_amount = Column(Integer)
    offer_accepted_at = Column(DateTime)
    offer_rejected_at = Column(DateTime)
    rejection_reason = Column(Text)

    # Hired
    hired_at = Column(DateTime)
    hired_as_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    start_date = Column(Date)

    # Notes
    recruiter_notes = Column(Text)
    hiring_manager_notes = Column(Text)

    # Soft delete
    is_active = Column(Boolean, default=True)

    # Timestamps
    applied_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_user_id])
    target_role = relationship("RoleDefinition", foreign_keys=[target_role_id])
    hired_as_user = relationship("User", foreign_keys=[hired_as_user_id])


# =============================================================================
# JOB POSTING MODEL (For Recruiting - Phase 2)
# =============================================================================

class JobPosting(Base):
    """
    Job postings for career page.
    """
    __tablename__ = "mm_job_postings"
    __table_args__ = (
        UniqueConstraint('organization_id', 'slug', name='uix_mm_job_org_slug'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Basic Info
    title = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, index=True)
    role_definition_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)

    # Content
    summary = Column(Text)  # Short description
    description = Column(Text)  # Full job description (markdown)
    requirements = Column(JSON)  # List of requirements
    responsibilities = Column(JSON)  # List of responsibilities
    benefits = Column(JSON)  # List of benefits

    # Compensation (optional)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    salary_type = Column(String(20))  # hourly, salary, commission

    # Settings
    is_published = Column(Boolean, default=False, index=True)
    is_internal = Column(Boolean, default=False)  # Internal posting only
    is_remote = Column(Boolean, default=False)
    location = Column(String(100))
    employment_type = Column(String(30))  # full_time, part_time, contract

    # Visibility
    published_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Metrics
    views = Column(Integer, default=0)
    applications = Column(Integer, default=0)

    # SEO
    meta_title = Column(String(200))
    meta_description = Column(String(500))

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    role_definition = relationship("RoleDefinition", foreign_keys=[role_definition_id])


# =============================================================================
# INTERVIEW MODEL (For Recruiting - Phase 2)
# =============================================================================

class InterviewType(str, Enum):
    PHONE_SCREEN = "phone_screen"
    VIDEO = "video"
    IN_PERSON = "in_person"
    PANEL = "panel"
    TECHNICAL = "technical"
    CULTURE = "culture"
    FINAL = "final"


class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class Interview(Base):
    """
    Interview scheduling and feedback tracking.
    """
    __tablename__ = "mm_interviews"
    __table_args__ = (
        Index('ix_mm_interview_candidate', 'candidate_id'),
        Index('ix_mm_interview_scheduled', 'scheduled_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    candidate_id = Column(Integer, ForeignKey("mm_candidates.id"), nullable=False, index=True)

    # Interview Details
    interview_type = Column(String(30), default=InterviewType.VIDEO.value)
    interview_round = Column(Integer, default=1)  # 1st, 2nd, 3rd round
    title = Column(String(200))  # e.g., "Phone Screen with HR"

    # Scheduling
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=30)
    timezone = Column(String(50), default="America/New_York")
    location = Column(String(255))  # Physical location or meeting link
    meeting_link = Column(Text)  # Zoom/Teams/etc link
    calendar_event_id = Column(String(255))  # External calendar ID

    # Interviewers
    interviewer_user_ids = Column(JSON, default=list)  # List of user IDs
    primary_interviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Status
    status = Column(String(30), default=InterviewStatus.SCHEDULED.value, index=True)
    confirmation_sent_at = Column(DateTime)
    reminder_sent_at = Column(DateTime)

    # Feedback
    feedback = Column(JSON, default=dict)
    # Structure: {
    #   "interviewer_id": {
    #     "overall_score": 1-5,
    #     "technical_score": 1-5,
    #     "culture_score": 1-5,
    #     "communication_score": 1-5,
    #     "recommendation": "strong_hire" | "hire" | "no_hire" | "strong_no_hire",
    #     "strengths": ["..."],
    #     "concerns": ["..."],
    #     "notes": "..."
    #   }
    # }
    overall_score = Column(Float)  # Aggregated score
    recommendation = Column(String(30))  # hire, no_hire, next_round, hold
    decision_notes = Column(Text)

    # Completed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    no_show_reason = Column(String(255))
    cancellation_reason = Column(String(255))

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    candidate = relationship("Candidate", foreign_keys=[candidate_id])
    primary_interviewer = relationship("User", foreign_keys=[primary_interviewer_id])


# =============================================================================
# OFFER MODEL (For Recruiting - Phase 2)
# =============================================================================

class OfferStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    NEGOTIATING = "negotiating"


class Offer(Base):
    """
    Job offers with approval workflow.
    """
    __tablename__ = "mm_offers"
    __table_args__ = (
        Index('ix_mm_offer_candidate', 'candidate_id'),
        Index('ix_mm_offer_status', 'status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    candidate_id = Column(Integer, ForeignKey("mm_candidates.id"), nullable=False, index=True)
    job_posting_id = Column(Integer, ForeignKey("mm_job_postings.id"), nullable=True)

    # Offer Details
    offer_number = Column(String(50), unique=True, index=True)  # e.g., "OFF-2024-001"
    role_title = Column(String(200), nullable=False)
    role_definition_id = Column(Integer, ForeignKey("mm_role_definitions.id"), nullable=True)
    department = Column(String(100))
    reports_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Compensation
    salary_amount = Column(Integer, nullable=False)
    salary_type = Column(String(20), default="salary")  # hourly, salary
    bonus_amount = Column(Integer)
    bonus_type = Column(String(30))  # signing, performance, guaranteed
    commission_structure = Column(JSON)  # Commission details if applicable
    equity_amount = Column(Integer)
    equity_type = Column(String(30))  # stock_options, rsu, phantom

    # Benefits
    benefits_summary = Column(Text)
    pto_days = Column(Integer)
    health_insurance = Column(Boolean, default=True)
    retirement_match_pct = Column(Float)

    # Terms
    employment_type = Column(String(30), default="full_time")  # full_time, part_time, contract
    start_date = Column(Date)
    is_remote = Column(Boolean, default=False)
    work_location = Column(String(255))

    # Status & Workflow
    status = Column(String(30), default=OfferStatus.DRAFT.value, index=True)
    approval_chain = Column(JSON, default=list)
    # Structure: [{"user_id": 1, "approved": true, "approved_at": "...", "notes": "..."}]
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime)

    # Sending
    sent_at = Column(DateTime)
    sent_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    viewed_at = Column(DateTime)
    expires_at = Column(DateTime)
    offer_letter_url = Column(Text)  # Generated PDF or DocuSign link

    # Response
    responded_at = Column(DateTime)
    response_notes = Column(Text)

    # Negotiation
    negotiation_history = Column(JSON, default=list)
    # Structure: [{"date": "...", "requested": {...}, "counter": {...}, "notes": "..."}]
    counter_offer_count = Column(Integer, default=0)

    # Acceptance
    accepted_at = Column(DateTime)
    signature_url = Column(Text)  # Signed offer letter
    onboarding_started = Column(Boolean, default=False)

    # Decline/Withdrawal
    declined_at = Column(DateTime)
    declined_reason = Column(String(100))
    declined_notes = Column(Text)
    withdrawn_at = Column(DateTime)
    withdrawn_reason = Column(Text)

    # Internal Notes
    internal_notes = Column(Text)

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    candidate = relationship("Candidate", foreign_keys=[candidate_id])
    job_posting = relationship("JobPosting", foreign_keys=[job_posting_id])
    role_definition = relationship("RoleDefinition", foreign_keys=[role_definition_id])
    reports_to = relationship("User", foreign_keys=[reports_to_user_id])


# =============================================================================
# CANDIDATE ACTIVITY LOG (For Recruiting - Phase 2)
# =============================================================================

class CandidateActivity(Base):
    """
    Activity log for candidate pipeline - tracks all touchpoints.
    """
    __tablename__ = "mm_candidate_activities"
    __table_args__ = (
        Index('ix_mm_cand_activity_candidate', 'candidate_id'),
        Index('ix_mm_cand_activity_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    candidate_id = Column(Integer, ForeignKey("mm_candidates.id"), nullable=False, index=True)

    # Activity Details
    activity_type = Column(String(50), nullable=False, index=True)
    # Types: status_change, email_sent, email_opened, call, interview_scheduled,
    #        interview_completed, assessment_sent, assessment_completed,
    #        offer_sent, offer_viewed, offer_accepted, offer_declined,
    #        note_added, document_uploaded, feedback_submitted

    description = Column(Text)
    meta_data = Column('metadata', JSON, default=dict)
    # Flexible data based on activity type

    # Associated entities
    interview_id = Column(Integer, ForeignKey("mm_interviews.id"), nullable=True)
    offer_id = Column(Integer, ForeignKey("mm_offers.id"), nullable=True)

    # Actor
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_automated = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    candidate = relationship("Candidate", foreign_keys=[candidate_id])


# =============================================================================
# CANDIDATE NOTE (For Recruiting - Phase 2)
# =============================================================================

class CandidateNote(Base):
    """
    Notes and comments on candidates from team members.
    """
    __tablename__ = "mm_candidate_notes"
    __table_args__ = (
        Index('ix_mm_cand_note_candidate', 'candidate_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    candidate_id = Column(Integer, ForeignKey("mm_candidates.id"), nullable=False, index=True)

    # Note Content
    note_type = Column(String(30), default="general")
    # Types: general, interview, reference_check, background_check, hiring_decision
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False)  # Only visible to author

    # Author
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    candidate = relationship("Candidate", foreign_keys=[candidate_id])
    author = relationship("User", foreign_keys=[created_by])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_capacity_status(capacity_pct: float) -> str:
    """Determine capacity status from percentage."""
    if capacity_pct >= 100:
        return CapacityStatus.OVER_CAPACITY.value
    elif capacity_pct >= 90:
        return CapacityStatus.AT_CAPACITY.value
    elif capacity_pct >= 75:
        return CapacityStatus.NEAR_CAPACITY.value
    return CapacityStatus.AVAILABLE.value


def calculate_performance_grade(score: float) -> str:
    """Calculate letter grade from numeric score."""
    if score >= 90:
        return PerformanceGrade.A.value
    elif score >= 80:
        return PerformanceGrade.B.value
    elif score >= 70:
        return PerformanceGrade.C.value
    elif score >= 60:
        return PerformanceGrade.D.value
    return PerformanceGrade.F.value
