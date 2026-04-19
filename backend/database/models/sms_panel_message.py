"""SMS Panel Message model — ORM backing for the sms_panel_messages table.

This table is the two-way SMS Archive: every inbound and outbound SMS sent
through Telnyx is recorded here so the SMS Archive panel can display a
unified conversation history per phone number, scoped by organization.

Previously this table was created via raw ``CREATE TABLE IF NOT EXISTS`` in
sms_conversation_routes._ensure_tables().  Having an ORM model means
Base.metadata.create_all() will create it, column validation is enforced,
and the table participates in normal SQLAlchemy migrations.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from db import Base


class SMSPanelMessage(Base):
    """A single SMS message displayed in the SMS Archive panel."""

    __tablename__ = "sms_panel_messages"

    # Primary key — UUID string assigned at INSERT time
    id = Column(String(36), primary_key=True)

    # Phone number (E.164 or raw digits) — the counterparty
    phone = Column(Text, nullable=False)

    # Optional FK to the lead/contact record (string because some callers
    # pass UUIDs while others pass integer IDs cast to string)
    contact_id = Column(Text, nullable=True)

    # Tenant isolation
    organization_id = Column(Integer, nullable=True, index=True)

    # 'inbound' or 'outbound'
    direction = Column(Text, nullable=False, server_default="outbound")

    # Message body
    body = Column(Text, nullable=False, server_default="")

    # Who sent the message (human-readable name)
    sender_name = Column(Text, server_default="")

    # FK to users.id — the LO or AI agent who sent it
    sender_user_id = Column(Integer, nullable=True)

    # Role of the sender (e.g. 'lo', 'admin', 'ai', 'borrower')
    sender_role = Column(Text, nullable=True)

    # Delivery status: 'sent', 'delivered', 'failed', 'queued', 'received'
    status = Column(Text, server_default="sent")

    # Attached media URLs (Telnyx MMS or S3 pre-signed)
    media_urls = Column(JSONB, server_default="'[]'::jsonb")

    # S3 object keys for media attachments (uploaded to our bucket)
    media_s3_keys = Column(JSONB, server_default="'[]'::jsonb")

    # Context fields for borrower portal messages
    page_type = Column(Text, server_default="client")
    borrower_type = Column(Text, server_default="primary")

    # Telnyx message ID for dedup and delivery-status correlation
    telnyx_message_id = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # Composite index for conversation lookup (org + phone)
        Index("ix_sms_panel_org_phone", "organization_id", "phone"),
        # Fast lookup by Telnyx message ID (delivery status updates)
        Index("ix_sms_panel_telnyx_msg", "telnyx_message_id"),
        # Chronological ordering
        Index("ix_sms_panel_created", "created_at"),
        # Single-column indexes already declared inline:
        #   organization_id (index=True on Column)
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<SMSPanelMessage id={self.id!r} phone={self.phone!r} "
            f"direction={self.direction!r} status={self.status!r}>"
        )
