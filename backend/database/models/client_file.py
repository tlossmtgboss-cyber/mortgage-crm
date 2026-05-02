from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ClientFile(Base):
    __tablename__ = "client_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False
    )
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leads.id"), nullable=True, unique=True
    )

    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    primary_email: Mapped[Optional[str]] = mapped_column(String)
    primary_phone: Mapped[Optional[str]] = mapped_column(String)
    lifecycle_stage: Mapped[str] = mapped_column(
        String, nullable=False, server_default="new_lead"
    )
    source: Mapped[Optional[str]] = mapped_column(String)
    preferred_channel: Mapped[Optional[str]] = mapped_column(String)
    sticky_note: Mapped[Optional[str]] = mapped_column(Text)

    assigned_loan_officer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_loan_assistant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_processor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )
    assigned_underwriter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )

    property_address: Mapped[Optional[dict]] = mapped_column(JSONB)
    active_loan_program: Mapped[Optional[str]] = mapped_column(String)
    active_loan_purpose: Mapped[Optional[str]] = mapped_column(String)
    active_loan_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    active_loan_fico: Mapped[Optional[int]] = mapped_column(Integer)
    active_loan_ltv: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    active_loan_lock_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    active_loan_projected_close_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now()
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id")
    )


class ClientFileCollaborator(Base):
    __tablename__ = "client_file_collaborators"
    __table_args__ = (
        UniqueConstraint("client_file_id", "user_id",
                         name="uq_cf_collaborators_client_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False
    )
    client_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_files.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="viewer")
    notify_on_inbound: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
