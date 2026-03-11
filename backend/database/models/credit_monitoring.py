"""
Credit Bureau Monitoring Models

Tracks credit monitoring subscriptions and alerts for leads, clients, and past
borrowers. The core recapture engine: when a monitored contact shops for a
mortgage elsewhere, a CreditInquiryAlert fires and the originating LO gets an
immediate opportunity to re-engage.

Key tables:
    credit_monitoring_subscriptions  — who is enrolled and with which bureau
    credit_alerts                    — every bureau-reported change event
    credit_inquiry_alerts            — sub-record for inquiry-type alerts (recapture signal)

Usage:
    from database.models.credit_monitoring import (
        CreditMonitoringSubscription,
        CreditAlert,
        CreditInquiryAlert,
        MonitoringStatus,
        AlertType,
        InquiryType,
        CreditBureauProvider,
    )
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SQLEnum

from db import Base


# ============================================================================
# ENUMS
# ============================================================================

class MonitoringStatus(str, enum.Enum):
    """Lifecycle status of a credit monitoring subscription."""
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class CreditBureauProvider(str, enum.Enum):
    """Credit bureau that provides the monitoring feed."""
    EXPERIAN = "experian"
    EQUIFAX = "equifax"
    TRANSUNION = "transunion"


class ContactType(str, enum.Enum):
    """The CRM entity type that this subscription monitors."""
    LEAD = "lead"
    CLIENT = "client"           # MUMClient / past borrower
    LOAN_CONTACT = "loan_contact"  # Active loan borrower


class AlertType(str, enum.Enum):
    """Categories of credit bureau alert events."""
    INQUIRY = "inquiry"                 # Hard pull — mortgage recapture signal
    NEW_ACCOUNT = "new_account"         # New tradeline opened
    SCORE_CHANGE = "score_change"       # FICO moved ± threshold
    DELINQUENCY = "delinquency"         # Late / collection / charge-off
    PUBLIC_RECORD = "public_record"     # Bankruptcy, lien, judgment
    ADDRESS_CHANGE = "address_change"   # Possible relocation / purchase intent


class InquiryType(str, enum.Enum):
    """Type of credit inquiry — mortgage is the primary recapture trigger."""
    MORTGAGE = "mortgage"
    AUTO = "auto"
    CREDIT_CARD = "credit_card"
    PERSONAL_LOAN = "personal_loan"
    STUDENT_LOAN = "student_loan"
    OTHER = "other"


class NotificationChannel(str, enum.Enum):
    """How the LO was notified about this alert."""
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    PUSH = "push"


# ============================================================================
# CREDIT MONITORING SUBSCRIPTION
# ============================================================================

class CreditMonitoringSubscription(Base):
    """Enrollment record for a contact in continuous credit bureau monitoring.

    One subscription per contact per bureau. A contact can be enrolled with
    multiple bureaus simultaneously (separate rows).

    The ssn_last_four column stores only the last 4 digits — never the full
    SSN. The actual bureau enrollment uses a tokenized reference that the
    bureau returns at enroll time (stored in provider_reference_id).
    """
    __tablename__ = "credit_monitoring_subscriptions"
    __table_args__ = (
        Index("ix_cms_org_id", "organization_id"),
        Index("ix_cms_contact_id_type", "contact_id", "contact_type"),
        Index("ix_cms_status", "monitoring_status"),
        Index("ix_cms_lo_id", "lo_id"),
        # Enforce one active subscription per contact+bureau per org
        Index(
            "ix_cms_unique_active",
            "organization_id", "contact_id", "contact_type", "provider",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Contact being monitored — polymorphic: lead, mum_client, or loan borrower
    contact_id = Column(Integer, nullable=False)
    contact_type = Column(SQLEnum(ContactType), nullable=False, default=ContactType.LEAD)

    # Basic PII used for bureau enrollment (minimal — bureau gets full SSN via
    # a one-time secure submit from the borrower portal, not stored here)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(20))
    ssn_last_four = Column(String(4))  # Last 4 only; full SSN never stored in CRM

    # Bureau configuration
    provider = Column(SQLEnum(CreditBureauProvider), nullable=False, default=CreditBureauProvider.EXPERIAN)
    # Opaque reference ID returned by the bureau at enrollment time
    provider_reference_id = Column(String(255), index=True)

    # Lifecycle
    monitoring_status = Column(SQLEnum(MonitoringStatus), nullable=False, default=MonitoringStatus.ACTIVE, index=True)
    enrolled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    paused_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    cancellation_reason = Column(String(500))

    # Owning LO (receives alert notifications)
    lo_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Snapshot of credit score at enrollment for baseline delta calculation
    baseline_credit_score = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    alerts = relationship("CreditAlert", back_populates="subscription", cascade="all, delete-orphan")
    lo = relationship("User", foreign_keys=[lo_id])


# ============================================================================
# CREDIT ALERT
# ============================================================================

class CreditAlert(Base):
    """A single credit bureau change event for a monitored contact.

    Created when the bureau webhook fires. The alert_type determines which
    sub-table (if any) holds the detail record — currently only INQUIRY type
    has a dedicated sub-table (CreditInquiryAlert).
    """
    __tablename__ = "credit_alerts"
    __table_args__ = (
        Index("ix_ca_subscription_id", "subscription_id"),
        Index("ix_ca_alert_type", "alert_type"),
        Index("ix_ca_detected_at", "detected_at"),
        Index("ix_ca_lo_id", "lo_id"),
        Index("ix_ca_is_actioned", "is_actioned"),
        Index("ix_ca_org_id", "organization_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("credit_monitoring_subscriptions.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Alert classification
    alert_type = Column(SQLEnum(AlertType), nullable=False, index=True)
    provider = Column(SQLEnum(CreditBureauProvider), nullable=False)

    # Structured payload from bureau (varies by alert_type and provider)
    details = Column(JSON, default=dict)

    # Credit score delta (populated for SCORE_CHANGE; optionally for others)
    credit_score_before = Column(Integer)
    credit_score_after = Column(Integer)
    score_delta = Column(Integer)  # after - before; negative = drop

    # Recapture / opportunity scoring
    recapture_score = Column(Integer)  # 0-100; how hot is this for LO action
    is_mortgage_recapture = Column(Boolean, default=False, index=True)  # True when alert_type=INQUIRY + inquiry_type=MORTGAGE

    # Timing
    detected_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    bureau_event_date = Column(DateTime)  # Date the bureau recorded the event (may differ from detected_at)

    # Notification tracking
    lo_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    notified_at = Column(DateTime)
    notification_channel = Column(SQLEnum(NotificationChannel))

    # Action tracking
    is_actioned = Column(Boolean, default=False, index=True)
    actioned_at = Column(DateTime)
    actioned_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action_taken = Column(String(500))  # Free-text: "called borrower", "sent rate sheet", etc.
    action_notes = Column(Text)

    # Outcome tracking (was this alert eventually converted to a loan?)
    converted_to_loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    subscription = relationship("CreditMonitoringSubscription", back_populates="alerts")
    lo = relationship("User", foreign_keys=[lo_id])
    actioned_by = relationship("User", foreign_keys=[actioned_by_id])
    inquiry_detail = relationship(
        "CreditInquiryAlert",
        back_populates="credit_alert",
        uselist=False,
        cascade="all, delete-orphan",
    )


# ============================================================================
# CREDIT INQUIRY ALERT (recapture sub-record)
# ============================================================================

class CreditInquiryAlert(Base):
    """Detail record for INQUIRY-type credit alerts.

    When a bureau reports a hard pull on a monitored contact, this record
    captures who pulled credit and for what purpose. A mortgage inquiry from
    a competing lender is the highest-value recapture signal in the CRM.

    The LO should be notified within minutes of bureau delivery so they can
    reach out before the competing LO closes the deal.
    """
    __tablename__ = "credit_inquiry_alerts"
    __table_args__ = (
        Index("ix_cia_credit_alert_id", "credit_alert_id"),
        Index("ix_cia_inquiry_type", "inquiry_type"),
        Index("ix_cia_inquiry_date", "inquiry_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    credit_alert_id = Column(Integer, ForeignKey("credit_alerts.id"), nullable=False, unique=True, index=True)

    # Who pulled the credit
    inquiring_company = Column(String(255))  # Lender / dealer / issuer name from bureau
    inquiring_company_normalized = Column(String(255))  # Cleaned/normalized name for deduplication

    # What they pulled for
    inquiry_type = Column(SQLEnum(InquiryType), nullable=False, default=InquiryType.OTHER)

    # When the pull happened at the bureau (not when we detected it)
    inquiry_date = Column(DateTime, nullable=False)

    # Mortgage-specific enrichment (populated when inquiry_type = MORTGAGE)
    estimated_loan_amount = Column(Numeric(12, 2))  # If inferrable from bureau data
    property_state = Column(String(2))              # If included in bureau data

    # Urgency metadata
    is_competing_lender = Column(Boolean, default=True)  # False only if pulled by us
    urgency_flag = Column(String(20), default="high")     # high / medium / low

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    credit_alert = relationship("CreditAlert", back_populates="inquiry_detail")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Enums
    "MonitoringStatus",
    "CreditBureauProvider",
    "ContactType",
    "AlertType",
    "InquiryType",
    "NotificationChannel",
    # Models
    "CreditMonitoringSubscription",
    "CreditAlert",
    "CreditInquiryAlert",
]
