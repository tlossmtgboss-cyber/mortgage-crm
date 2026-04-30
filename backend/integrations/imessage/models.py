"""
SQLAlchemy ORM models for the Perennia iMessage system.

Tables (all multi-tenant, encrypted-at-rest where noted):

  imessage_lines           — physical Mac mini relays + their Apple ID handle
  imessage_threads         — one row per (tenant, contact, line) pair
  imessage_messages        — every message exchanged
  imessage_lookup_cache    — phone → service ("iMessage" | "SMS") cache
  imessage_webhook_log     — append-only audit of every BB webhook
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Perennia DB base — re-exported via database/__init__.py
from database import Base

# Perennia handles encryption at the application layer (encryption_utils),
# not via a custom SQLAlchemy column type. Use plain String storage here;
# the service layer encrypts/decrypts as needed.
EncryptedText = String


# -----------------------------------------------------------------------------
# imessage_lines
# -----------------------------------------------------------------------------
class IMessageLine(Base):
    """
    One Mac mini = one line. Multi-tenant: multiple tenants can share a Mac
    if they're TL Development internal teams; production SaaS use should
    keep a Mac per tenant for SOC 2 isolation.
    """

    __tablename__ = "imessage_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "handle", name="uq_imessage_line_tenant_handle"),
        Index("ix_imessage_line_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # The handle as Apple sees it: "+18649820355" or "[email protected]"
    handle: Mapped[str] = mapped_column(String(120), nullable=False)
    bb_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    # Per-line override; when null, we use the global IMESSAGE_BB_PASSWORD.
    bb_password: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    cf_access_client_id: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    cf_access_client_secret: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_ping_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_ping_status: Mapped[Optional[str]] = mapped_column(String(16))
    daily_send_limit: Mapped[int] = mapped_column(Integer, default=2500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# -----------------------------------------------------------------------------
# imessage_threads
# -----------------------------------------------------------------------------
class IMessageThread(Base):
    """
    A long-lived conversation between a tenant and a borrower. Holds the BB
    chatGuid we'll reuse for every send, plus the most-recently observed
    service (iMessage vs SMS). Required because BB requires a stable
    chatGuid for ongoing conversations.
    """

    __tablename__ = "imessage_threads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "contact_id", "line_id", name="uq_imessage_thread"),
        Index("ix_imessage_thread_chat_guid", "chat_guid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("imessage_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chat_guid: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_known_service: Mapped[Optional[str]] = mapped_column(String(16))
    # `is_group`, `participants` for future co-borrower / LO threads
    is_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    participants: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages = relationship(
        "IMessageMessage", back_populates="thread", cascade="all, delete-orphan"
    )


# -----------------------------------------------------------------------------
# imessage_messages
# -----------------------------------------------------------------------------
class IMessageMessage(Base):
    """One message — outbound or inbound. Body encrypted at rest."""

    __tablename__ = "imessage_messages"
    __table_args__ = (
        UniqueConstraint(
            "bb_message_guid", name="uq_imessage_messages_bb_guid"
        ),
        Index("ix_imessage_thread_created", "thread_id", "created_at"),
        Index("ix_imessage_temp_guid", "bb_temp_guid"),
        Index("ix_imessage_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("imessage_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_seat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    body: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    media_urls: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    send_style: Mapped[Optional[str]] = mapped_column(String(32))

    # BB identifiers
    bb_message_guid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bb_temp_guid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    bb_chat_guid: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # For tapbacks + replies
    associated_message_guid: Mapped[Optional[str]] = mapped_column(String(64))
    tapback: Mapped[Optional[str]] = mapped_column(String(16))
    reply_to_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("imessage_messages.id", ondelete="SET NULL"),
    )

    # Errors
    error_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Lifecycle timestamps
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Raw BB payload for forensic / replay
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    thread = relationship("IMessageThread", back_populates="messages")


# -----------------------------------------------------------------------------
# imessage_lookup_cache
# -----------------------------------------------------------------------------
class IMessageLookupCache(Base):
    """
    Cache of "is this number iMessage or SMS only" per Mac line.

    BlueBubbles' way to detect: send a text via private API and inspect the
    handle service in the response. We cache the result so we don't pay the
    round-trip on every send.
    """

    __tablename__ = "imessage_lookup_cache"
    __table_args__ = (
        UniqueConstraint("line_id", "handle", name="uq_imessage_lookup"),
        Index("ix_imessage_lookup_checked_at", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("imessage_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    handle: Mapped[str] = mapped_column(String(120), nullable=False)
    service: Mapped[str] = mapped_column(String(16), nullable=False)  # "iMessage"|"SMS"
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# -----------------------------------------------------------------------------
# imessage_webhook_log
# -----------------------------------------------------------------------------
class IMessageWebhookLog(Base):
    """Append-only log of every BB webhook for audit + dedupe + replay."""

    __tablename__ = "imessage_webhook_log"
    __table_args__ = (
        Index(
            "ix_imessage_webhook_dedupe",
            "event_type",
            "bb_guid",
            "event_signature",
            unique=True,
        ),
        Index("ix_imessage_webhook_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True))
    line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("imessage_lines.id", ondelete="SET NULL"),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bb_guid: Mapped[Optional[str]] = mapped_column(String(64))
    # Hash of (event_type, bb_guid, dateDelivered, dateRead, error, isFromMe)
    # so we collapse duplicate redeliveries.
    event_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
