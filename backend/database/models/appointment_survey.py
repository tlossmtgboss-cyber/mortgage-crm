"""
Appointment Survey Models

Database models for the post-appointment survey system.

Tables:
- appointment_surveys: Captures borrower feedback after appointments with
  star ratings, NPS data, and free-text feedback. Uses a unique token for
  secure, unauthenticated access to the survey form.

Lifecycle:
    1. LO triggers survey send after an appointment completes
    2. System generates a unique token and emails the borrower a link
    3. Borrower opens /surveys/respond/{token} (no auth required)
    4. Borrower submits ratings and feedback
    5. LO and admin view aggregate results in the dashboard
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, Index, CheckConstraint,
)
from db import Base


class AppointmentSurvey(Base):
    """
    Post-appointment survey response.

    Each row represents a single survey invitation (and optionally its response).
    The token column provides secure, unauthenticated access to the survey form.
    """
    __tablename__ = "appointment_surveys"
    __table_args__ = (
        Index('ix_appt_survey_org', 'organization_id'),
        Index('ix_appt_survey_token', 'token', unique=True),
        Index('ix_appt_survey_appointment', 'appointment_id'),
        Index('ix_appt_survey_lo', 'lo_user_id'),
        Index('ix_appt_survey_completed', 'completed_at'),
        CheckConstraint('overall_rating IS NULL OR (overall_rating >= 1 AND overall_rating <= 5)',
                        name='ck_survey_overall_rating'),
        CheckConstraint('communication_rating IS NULL OR (communication_rating >= 1 AND communication_rating <= 5)',
                        name='ck_survey_communication_rating'),
        CheckConstraint('knowledge_rating IS NULL OR (knowledge_rating >= 1 AND knowledge_rating <= 5)',
                        name='ck_survey_knowledge_rating'),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                             nullable=False, index=True)

    # Link to the appointment that triggered this survey
    appointment_id = Column(Integer, nullable=False, index=True)

    # The loan officer who conducted the appointment (for per-LO reporting)
    lo_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Borrower contact info (denormalized from appointment for survey delivery)
    borrower_email = Column(String(255), nullable=False)
    borrower_name = Column(String(255), nullable=True)

    # Secure token for unauthenticated access to the survey form
    token = Column(String(64), nullable=False, unique=True, index=True)

    # --- Ratings (null until survey is completed) ---
    overall_rating = Column(Integer, nullable=True)          # 1-5
    communication_rating = Column(Integer, nullable=True)    # 1-5
    knowledge_rating = Column(Integer, nullable=True)        # 1-5

    # Free-text feedback
    feedback_text = Column(Text, nullable=True)

    # Net Promoter Score proxy: "Would you recommend this LO?"
    would_recommend = Column(Boolean, nullable=True)

    # --- Lifecycle timestamps ---
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
