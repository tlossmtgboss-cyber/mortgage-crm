"""SQLAlchemy models for Microsoft 365 integration.

Tables:
  - ms_accounts                  — connected MS accounts (one per CRM user)
  - ms_graph_subscriptions       — webhook subscriptions to renew/manage
  - ms_calendar_sync_mapping     — CRM event <-> Graph event ID mapping
  - ms_email_reconciliation      — inbound emails awaiting/after matching
  - ms_teams_chat_reconciliation — inbound 1:1 Teams messages

Every table is multi-tenant (organization_id) and FK'd to the originating user.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from db import Base


class ReconciliationStatus(str, Enum):
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    AUTO_LINKED = "auto_linked"
    MANUALLY_LINKED = "manually_linked"
    DISMISSED = "dismissed"


class ReconciliationLinkType(str, Enum):
    LEAD = "lead"
    LOAN = "loan"
    PARTNER = "partner"


class CalendarSyncDirection(str, Enum):
    OUTLOOK_TO_CRM = "outlook_to_crm"
    CRM_TO_OUTLOOK = "crm_to_outlook"
    BOTH = "both"


class SubscriptionKind(str, Enum):
    CALENDAR = "calendar"
    EMAIL = "email"
    TEAMS_CHATS = "teams_chats"


class MSAccount(Base):
    __tablename__ = "ms_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_ms_account_user"),
        UniqueConstraint("ms_user_id", "organization_id", name="uq_ms_account_msuser"),
        Index("ix_ms_accounts_org_user", "organization_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    ms_user_id = Column(String(128), nullable=False)
    upn = Column(String(320), nullable=False)
    display_name = Column(String(255))

    encrypted_refresh_token = Column(LargeBinary, nullable=False)
    access_token_expires_at = Column(DateTime(timezone=True))
    encrypted_access_token = Column(LargeBinary)

    scopes = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    last_error = Column(Text)

    calendar_delta_link = Column(Text)
    email_delta_link = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    subscriptions = relationship("MSGraphSubscription", back_populates="account", cascade="all, delete-orphan")


class MSGraphSubscription(Base):
    __tablename__ = "ms_graph_subscriptions"
    __table_args__ = (
        UniqueConstraint("ms_account_id", "kind", name="uq_sub_account_kind"),
        Index("ix_sub_expires", "expiration_datetime"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    ms_account_id = Column(Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False)

    kind = Column(String(32), nullable=False)
    graph_subscription_id = Column(String(128), nullable=False, unique=True)
    resource = Column(String(255), nullable=False)
    change_type = Column(String(64), nullable=False)
    notification_url = Column(String(512), nullable=False)
    client_state_hash = Column(String(128), nullable=False)
    expiration_datetime = Column(DateTime(timezone=True), nullable=False)
    last_renewed_at = Column(DateTime(timezone=True))
    failure_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    account = relationship("MSAccount", back_populates="subscriptions")


class MSCalendarSyncMapping(Base):
    __tablename__ = "ms_calendar_sync_mapping"
    __table_args__ = (
        UniqueConstraint("crm_event_id", name="uq_cal_crm_event"),
        UniqueConstraint("ms_account_id", "graph_event_id", name="uq_cal_graph_event"),
        Index("ix_cal_org_account", "organization_id", "ms_account_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    ms_account_id = Column(Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False)

    crm_event_id = Column(Integer, nullable=False)

    graph_event_id = Column(String(255), nullable=False)
    graph_etag = Column(String(255))
    graph_change_key = Column(String(255))

    last_synced_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    direction = Column(String(32), nullable=False)
    last_synced_payload_hash = Column(String(64))

    is_deleted = Column(Boolean, nullable=False, default=False)


class MSEmailReconciliation(Base):
    __tablename__ = "ms_email_reconciliation"
    __table_args__ = (
        UniqueConstraint("ms_account_id", "internet_message_id", name="uq_email_message"),
        Index("ix_email_org_status", "organization_id", "status"),
        Index("ix_email_received", "received_at"),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_email_confidence_range",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    ms_account_id = Column(Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False)

    graph_message_id = Column(String(255), nullable=False)
    internet_message_id = Column(String(512), nullable=False)
    conversation_id = Column(String(255))

    subject = Column(String(998), nullable=False, default="")
    sender_email = Column(String(320), nullable=False)
    sender_name = Column(String(255))
    recipient_emails = Column(JSON, nullable=False, default=list)
    received_at = Column(DateTime(timezone=True), nullable=False)
    has_attachments = Column(Boolean, nullable=False, default=False)
    web_link = Column(String(1024))
    body_preview = Column(Text)

    status = Column(String(32), nullable=False, default=ReconciliationStatus.UNMATCHED.value)
    match_confidence = Column(Float)
    match_strategy = Column(String(64))
    matched_link_type = Column(String(32))
    matched_link_id = Column(Integer)
    suggested_links = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    reconciled_at = Column(DateTime(timezone=True))
    reconciled_by_user_id = Column(Integer)


class MSTeamsChatReconciliation(Base):
    __tablename__ = "ms_teams_chat_reconciliation"
    __table_args__ = (
        UniqueConstraint(
            "ms_account_id", "graph_message_id", "graph_chat_id",
            name="uq_teams_msg",
        ),
        Index("ix_teams_org_status", "organization_id", "status"),
        Index("ix_teams_sent", "sent_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    ms_account_id = Column(Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False)

    graph_chat_id = Column(String(255), nullable=False)
    graph_message_id = Column(String(255), nullable=False)
    chat_topic = Column(String(255))
    is_one_on_one = Column(Boolean, nullable=False, default=True)

    sender_email = Column(String(320), nullable=False)
    sender_name = Column(String(255))
    sent_at = Column(DateTime(timezone=True), nullable=False)
    body_text = Column(Text)
    web_link = Column(String(1024))

    status = Column(String(32), nullable=False, default=ReconciliationStatus.UNMATCHED.value)
    match_confidence = Column(Float)
    match_strategy = Column(String(64))
    matched_link_type = Column(String(32))
    matched_link_id = Column(Integer)
    suggested_links = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    reconciled_at = Column(DateTime(timezone=True))
    reconciled_by_user_id = Column(Integer)
