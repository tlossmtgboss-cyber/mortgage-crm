"""
E-Signature System SQLAlchemy Models

Models for the self-hosted DocuSign-style e-signature system.
Supports field placement, signature adoption, and PDF generation.

Tables:
- EsignEnvelope: Container for signing request
- EsignSigner: Signer with magic link token
- EsignField: Field placement with PDF coordinates
- EsignFieldValue: Submitted field values
- EsignAuditEvent: Audit trail
- EsignCompletedDocument: Final signed PDFs
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
import enum
import hashlib
import secrets

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, BigInteger, Index
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class EnvelopeStatus(str, enum.Enum):
    """Envelope lifecycle status"""
    DRAFT = "draft"
    SENT = "sent"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    VOIDED = "voided"
    DECLINED = "declined"
    EXPIRED = "expired"


class SignerStatus(str, enum.Enum):
    """Signer status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    VIEWED = "viewed"
    SIGNED = "signed"
    DECLINED = "declined"


class FieldType(str, enum.Enum):
    """Field types for e-signature"""
    SIGNATURE = "signature"
    INITIAL = "initial"
    DATE_SIGNED = "date_signed"
    TEXT = "text"
    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"


class AuditAction(str, enum.Enum):
    """Audit event actions"""
    ENVELOPE_CREATED = "envelope_created"
    ENVELOPE_SENT = "envelope_sent"
    ENVELOPE_VOIDED = "envelope_voided"
    SIGNER_VIEWED = "signer_viewed"
    SIGNATURE_ADOPTED = "signature_adopted"
    FIELD_COMPLETED = "field_completed"
    SIGNING_COMPLETED = "signing_completed"
    DOCUMENT_GENERATED = "document_generated"
    REMINDER_SENT = "reminder_sent"
    LINK_ACCESSED = "link_accessed"
    ENVELOPE_DECLINED = "envelope_declined"


class ActorType(str, enum.Enum):
    """Actor types for audit trail"""
    STAFF = "staff"
    SIGNER = "signer"
    SYSTEM = "system"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_signer_token() -> tuple[str, str]:
    """
    Generate a secure token for signer magic links.
    Returns (raw_token, token_hash).
    Raw token is sent to signer, hash is stored in DB.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """Hash a raw token for lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# =============================================================================
# MODEL FACTORY
# =============================================================================

from model_cache import base_memoize


@base_memoize
def create_esign_models(Base):
    """
    Factory function to create E-Sign models with the provided SQLAlchemy Base.
    Follows established pattern to avoid circular imports.
    """

    class EsignEnvelope(Base):
        """
        Container for a signing request.
        Represents a PDF document that needs signatures from one or more signers.
        """
        __tablename__ = 'esign_envelopes'

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Document reference
        document_id = Column(Integer, ForeignKey('perennia_documents.id', ondelete='SET NULL'), nullable=True, index=True)
        loan_id = Column(Integer, ForeignKey('loans.id', ondelete='SET NULL'), nullable=True, index=True)
        lead_id = Column(Integer, ForeignKey('leads.id', ondelete='SET NULL'), nullable=True, index=True)

        # Envelope info
        name = Column(String(500), nullable=False)
        description = Column(Text, nullable=True)
        status = Column(String(20), default=EnvelopeStatus.DRAFT.value)

        # PDF metadata
        pdf_storage_key = Column(String(500), nullable=False)
        pdf_file_name = Column(String(500), nullable=False)
        pdf_file_size = Column(BigInteger, nullable=True)
        pdf_page_count = Column(Integer, default=1)
        pdf_page_dimensions = Column(JSONB, nullable=True)  # [{width_points, height_points}, ...]

        # Locking (prevents field edits after send)
        is_locked = Column(Boolean, default=False)
        locked_at = Column(DateTime(timezone=True), nullable=True)
        locked_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

        # Configuration
        expires_at = Column(DateTime(timezone=True), nullable=True)
        reminder_days = Column(ARRAY(Integer), default=[1, 3, 7])
        email_subject = Column(String(500), nullable=True)
        email_message = Column(Text, nullable=True)

        # Completion
        completed_at = Column(DateTime(timezone=True), nullable=True)
        signed_pdf_storage_key = Column(String(500), nullable=True)
        audit_pdf_storage_key = Column(String(500), nullable=True)

        # Created by
        created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        signers = relationship("EsignSigner", back_populates="envelope", cascade="all, delete-orphan")
        fields = relationship("EsignField", back_populates="envelope", cascade="all, delete-orphan")
        audit_events = relationship("EsignAuditEvent", back_populates="envelope", cascade="all, delete-orphan")
        completed_documents = relationship("EsignCompletedDocument", back_populates="envelope", cascade="all, delete-orphan")

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'document_id': self.document_id,
                'loan_id': self.loan_id,
                'lead_id': self.lead_id,
                'name': self.name,
                'description': self.description,
                'status': self.status,
                'pdf_file_name': self.pdf_file_name,
                'pdf_file_size': self.pdf_file_size,
                'pdf_page_count': self.pdf_page_count,
                'is_locked': self.is_locked,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None,
                'signer_count': len(self.signers) if self.signers else 0,
                'field_count': len(self.fields) if self.fields else 0,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }

        def is_all_signed(self) -> bool:
            """Check if all signers have signed."""
            if not self.signers:
                return False
            return all(s.status == SignerStatus.SIGNED.value for s in self.signers)


    class EsignSigner(Base):
        """
        Signer assignment for an envelope.
        Contains magic link token for passwordless signing.
        """
        __tablename__ = 'esign_signers'

        id = Column(Integer, primary_key=True, autoincrement=True)
        envelope_id = Column(Integer, ForeignKey('esign_envelopes.id', ondelete='CASCADE'), nullable=False, index=True)

        # Signer info
        signer_order = Column(Integer, default=1)
        name = Column(String(255), nullable=False)
        email = Column(String(255), nullable=False)
        role = Column(String(100), nullable=True)  # 'borrower', 'co-borrower', 'agent'

        # Status
        status = Column(String(20), default=SignerStatus.PENDING.value)

        # Magic link token (stored as SHA-256 hash)
        token_hash = Column(String(64), unique=True, nullable=True, index=True)
        token_expires_at = Column(DateTime(timezone=True), nullable=True)

        # Signature adoption
        has_adopted_signature = Column(Boolean, default=False)
        adopted_signature_text = Column(String(255), nullable=True)
        adopted_signature_font = Column(String(100), nullable=True)
        adopted_signature_image_key = Column(String(500), nullable=True)
        adopted_at = Column(DateTime(timezone=True), nullable=True)

        # Signing session
        viewed_at = Column(DateTime(timezone=True), nullable=True)
        signed_at = Column(DateTime(timezone=True), nullable=True)
        declined_at = Column(DateTime(timezone=True), nullable=True)
        decline_reason = Column(Text, nullable=True)

        # Session tracking
        last_access_at = Column(DateTime(timezone=True), nullable=True)
        last_access_ip = Column(String(45), nullable=True)
        last_access_user_agent = Column(Text, nullable=True)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        envelope = relationship("EsignEnvelope", back_populates="signers")
        fields = relationship("EsignField", back_populates="signer")
        field_values = relationship("EsignFieldValue", back_populates="signer", cascade="all, delete-orphan")

        def to_dict(self, include_token: bool = False) -> Dict[str, Any]:
            result = {
                'id': self.id,
                'envelope_id': self.envelope_id,
                'signer_order': self.signer_order,
                'name': self.name,
                'email': self.email,
                'role': self.role,
                'status': self.status,
                'has_adopted_signature': self.has_adopted_signature,
                'viewed_at': self.viewed_at.isoformat() if self.viewed_at else None,
                'signed_at': self.signed_at.isoformat() if self.signed_at else None,
                'declined_at': self.declined_at.isoformat() if self.declined_at else None,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }
            if include_token:
                result['token_expires_at'] = self.token_expires_at.isoformat() if self.token_expires_at else None
            return result

        def generate_token(self, expires_in_days: int = 7) -> str:
            """Generate a new magic link token. Returns raw token."""
            raw_token, self.token_hash = generate_signer_token()
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            return raw_token

        def is_token_valid(self) -> bool:
            """Check if token is still valid."""
            if not self.token_hash or not self.token_expires_at:
                return False
            return datetime.now(timezone.utc) < self.token_expires_at


    class EsignField(Base):
        """
        Field placement on a PDF page.
        Coordinates stored in PDF points (72 points/inch), origin at bottom-left.
        """
        __tablename__ = 'esign_fields'

        id = Column(Integer, primary_key=True, autoincrement=True)
        envelope_id = Column(Integer, ForeignKey('esign_envelopes.id', ondelete='CASCADE'), nullable=False, index=True)
        signer_id = Column(Integer, ForeignKey('esign_signers.id', ondelete='SET NULL'), nullable=True, index=True)

        # Field type
        field_type = Column(String(20), nullable=False)

        # Position (PDF points, origin at bottom-left)
        page_number = Column(Integer, nullable=False, default=1)
        x_position_points = Column(Numeric(10, 2), nullable=False)
        y_position_points = Column(Numeric(10, 2), nullable=False)
        width_points = Column(Numeric(10, 2), nullable=False, default=144.0)  # 2 inches
        height_points = Column(Numeric(10, 2), nullable=False, default=36.0)  # 0.5 inches

        # Field configuration
        is_required = Column(Boolean, default=True)
        placeholder_text = Column(String(255), nullable=True)
        default_value = Column(Text, nullable=True)
        validation_regex = Column(String(255), nullable=True)
        max_length = Column(Integer, nullable=True)

        # For dropdown fields
        dropdown_options = Column(JSONB, nullable=True)  # ["Option 1", "Option 2"]

        # Display
        font_name = Column(String(100), default='Helvetica')
        font_size = Column(Numeric(5, 2), default=12.0)
        font_color = Column(String(20), default='#000000')
        background_color = Column(String(20), nullable=True)
        border_color = Column(String(20), default='#0066CC')

        # Ordering
        tab_order = Column(Integer, default=0)

        # Timestamps
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        envelope = relationship("EsignEnvelope", back_populates="fields")
        signer = relationship("EsignSigner", back_populates="fields")
        values = relationship("EsignFieldValue", back_populates="field", cascade="all, delete-orphan")

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'envelope_id': self.envelope_id,
                'signer_id': self.signer_id,
                'field_type': self.field_type,
                'page_number': self.page_number,
                'x_position_points': float(self.x_position_points) if self.x_position_points else 0,
                'y_position_points': float(self.y_position_points) if self.y_position_points else 0,
                'width_points': float(self.width_points) if self.width_points else 144.0,
                'height_points': float(self.height_points) if self.height_points else 36.0,
                'is_required': self.is_required,
                'placeholder_text': self.placeholder_text,
                'tab_order': self.tab_order,
                'font_name': self.font_name,
                'font_size': float(self.font_size) if self.font_size else 12.0,
                'font_color': self.font_color,
                'border_color': self.border_color,
                'dropdown_options': self.dropdown_options,
            }


    class EsignFieldValue(Base):
        """
        Submitted value for a field.
        Records what the signer entered/signed.
        """
        __tablename__ = 'esign_field_values'

        id = Column(Integer, primary_key=True, autoincrement=True)
        field_id = Column(Integer, ForeignKey('esign_fields.id', ondelete='CASCADE'), nullable=False, index=True)
        signer_id = Column(Integer, ForeignKey('esign_signers.id', ondelete='CASCADE'), nullable=False, index=True)

        # Value
        value_type = Column(String(20), nullable=False)  # text, signature, checkbox, date
        text_value = Column(Text, nullable=True)
        boolean_value = Column(Boolean, nullable=True)
        date_value = Column(DateTime(timezone=True), nullable=True)
        signature_image_key = Column(String(500), nullable=True)  # S3 key for drawn signature

        # Completion metadata
        completed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
        completed_ip = Column(String(45), nullable=True)
        completed_user_agent = Column(Text, nullable=True)

        # Server timestamp for date_signed fields
        server_timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

        # Relationships
        field = relationship("EsignField", back_populates="values")
        signer = relationship("EsignSigner", back_populates="field_values")

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'field_id': self.field_id,
                'signer_id': self.signer_id,
                'value_type': self.value_type,
                'text_value': self.text_value,
                'boolean_value': self.boolean_value,
                'date_value': self.date_value.isoformat() if self.date_value else None,
                'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            }


    class EsignAuditEvent(Base):
        """
        Audit trail for all e-signature activities.
        Immutable log for compliance and legal purposes.
        """
        __tablename__ = 'esign_audit_events'

        id = Column(Integer, primary_key=True, autoincrement=True)
        envelope_id = Column(Integer, ForeignKey('esign_envelopes.id', ondelete='CASCADE'), nullable=False, index=True)
        signer_id = Column(Integer, ForeignKey('esign_signers.id', ondelete='SET NULL'), nullable=True, index=True)
        field_id = Column(Integer, ForeignKey('esign_fields.id', ondelete='SET NULL'), nullable=True)

        # Event info
        action = Column(String(50), nullable=False, index=True)
        description = Column(Text, nullable=True)
        event_data = Column(JSONB, nullable=True)

        # Actor info
        actor_type = Column(String(20), nullable=False)  # 'staff', 'signer', 'system'
        actor_id = Column(Integer, nullable=True)  # user_id for staff, signer_id for signers
        actor_email = Column(String(255), nullable=True)

        # Request metadata
        ip_address = Column(String(45), nullable=True)
        user_agent = Column(Text, nullable=True)

        # Timestamp (immutable)
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

        # Relationships
        envelope = relationship("EsignEnvelope", back_populates="audit_events")

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'envelope_id': self.envelope_id,
                'signer_id': self.signer_id,
                'field_id': self.field_id,
                'action': self.action,
                'description': self.description,
                'event_data': self.event_data,
                'actor_type': self.actor_type,
                'actor_email': self.actor_email,
                'ip_address': self.ip_address,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }


    class EsignCompletedDocument(Base):
        """
        Final signed PDF and audit trail documents.
        Generated when all signers have completed.
        """
        __tablename__ = 'esign_completed_documents'

        id = Column(Integer, primary_key=True, autoincrement=True)
        envelope_id = Column(Integer, ForeignKey('esign_envelopes.id', ondelete='CASCADE'), nullable=False, index=True)

        # Document info
        document_type = Column(String(20), nullable=False)  # 'signed_pdf', 'audit_trail', 'combined'
        file_name = Column(String(500), nullable=False)
        storage_key = Column(String(500), nullable=False)
        file_size = Column(BigInteger, nullable=True)

        # Integrity
        sha256_hash = Column(String(64), nullable=True)

        # Timestamp
        created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

        # Relationships
        envelope = relationship("EsignEnvelope", back_populates="completed_documents")

        def to_dict(self) -> Dict[str, Any]:
            return {
                'id': self.id,
                'envelope_id': self.envelope_id,
                'document_type': self.document_type,
                'file_name': self.file_name,
                'file_size': self.file_size,
                'sha256_hash': self.sha256_hash,
                'created_at': self.created_at.isoformat() if self.created_at else None,
            }


    # Return all models
    return {
        'EsignEnvelope': EsignEnvelope,
        'EsignSigner': EsignSigner,
        'EsignField': EsignField,
        'EsignFieldValue': EsignFieldValue,
        'EsignAuditEvent': EsignAuditEvent,
        'EsignCompletedDocument': EsignCompletedDocument,
    }


# =============================================================================
# STANDALONE USAGE (for testing)
# =============================================================================

if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.ext.declarative import declarative_base
    import os

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    engine = create_engine(DATABASE_URL)
    Base = declarative_base()

    models = create_esign_models(Base)
    print("E-Sign models created successfully!")
    for name in models:
        print(f"  - {name}")
