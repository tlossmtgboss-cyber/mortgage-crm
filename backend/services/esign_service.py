"""
E-Signature Service

Business logic for the self-hosted e-signature system.
Handles envelope creation, signer management, field placement,
and signing session validation.
"""

import hashlib
import json
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class EsignError(Exception):
    """Custom exception for e-sign errors."""
    def __init__(self, message: str, code: str = "ESIGN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class EsignService:
    """
    Service class for e-signature operations.
    Handles business logic, validation, and database operations.
    """

    def __init__(self, db: Session, models: Dict[str, Any] = None):
        self.db = db
        self._models = models

    @property
    def models(self):
        if self._models is None:
            raise RuntimeError("EsignService not initialized with models")
        return self._models

    # =========================================================================
    # ENVELOPE OPERATIONS
    # =========================================================================

    def create_envelope(
        self,
        name: str,
        pdf_storage_key: str,
        pdf_file_name: str,
        created_by_user_id: int,
        loan_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        document_id: Optional[int] = None,
        description: Optional[str] = None,
        pdf_file_size: Optional[int] = None,
        pdf_page_count: int = 1,
        pdf_page_dimensions: Optional[List[Dict]] = None,
        email_subject: Optional[str] = None,
        email_message: Optional[str] = None,
        expires_in_days: int = 30,
    ) -> Dict[str, Any]:
        """Create a new envelope from a PDF document."""
        try:
            result = self.db.execute(text("""
                INSERT INTO esign_envelopes (
                    name, description, pdf_storage_key, pdf_file_name,
                    pdf_file_size, pdf_page_count, pdf_page_dimensions,
                    loan_id, lead_id, document_id, created_by_user_id,
                    email_subject, email_message, expires_at,
                    status, created_at, updated_at
                ) VALUES (
                    :name, :description, :pdf_storage_key, :pdf_file_name,
                    :pdf_file_size, :pdf_page_count, :pdf_page_dimensions,
                    :loan_id, :lead_id, :document_id, :created_by_user_id,
                    :email_subject, :email_message, :expires_at,
                    'draft', NOW(), NOW()
                ) RETURNING id
            """), {
                "name": name,
                "description": description,
                "pdf_storage_key": pdf_storage_key,
                "pdf_file_name": pdf_file_name,
                "pdf_file_size": pdf_file_size,
                "pdf_page_count": pdf_page_count,
                "pdf_page_dimensions": pdf_page_dimensions,
                "loan_id": loan_id,
                "lead_id": lead_id,
                "document_id": document_id,
                "created_by_user_id": created_by_user_id,
                "email_subject": email_subject,
                "email_message": email_message,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            })

            envelope_id = result.fetchone()[0]

            # Log audit event
            self._log_audit_event(
                envelope_id=envelope_id,
                action="envelope_created",
                description=f"Envelope '{name}' created",
                actor_type="staff",
                actor_id=created_by_user_id,
            )

            self.db.commit()

            return {
                "success": True,
                "envelope_id": envelope_id,
                "message": "Envelope created successfully"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error creating envelope: {e}")
            raise EsignError(str(e), "CREATE_ENVELOPE_FAILED")

    def get_envelope(self, envelope_id: int) -> Optional[Dict[str, Any]]:
        """Get envelope with signers and fields."""
        envelope = self.db.execute(text("""
            SELECT e.*, u.full_name as created_by_name, u.email as created_by_email
            FROM esign_envelopes e
            LEFT JOIN users u ON u.id = e.created_by_user_id
            WHERE e.id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            return None

        envelope_dict = dict(envelope._mapping)

        # Get signers
        signers = self.db.execute(text("""
            SELECT * FROM esign_signers
            WHERE envelope_id = :envelope_id
            ORDER BY signer_order, id
        """), {"envelope_id": envelope_id}).fetchall()

        envelope_dict["signers"] = [dict(s._mapping) for s in signers]

        # Get fields
        fields = self.db.execute(text("""
            SELECT * FROM esign_fields
            WHERE envelope_id = :envelope_id
            ORDER BY page_number, tab_order, id
        """), {"envelope_id": envelope_id}).fetchall()

        envelope_dict["fields"] = [dict(f._mapping) for f in fields]

        return envelope_dict

    def send_envelope(
        self,
        envelope_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """
        Send envelope to signers.
        Locks the envelope, generates tokens, and sends invitations.
        """
        envelope = self.db.execute(text("""
            SELECT id, status, is_locked FROM esign_envelopes WHERE id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            raise EsignError("Envelope not found", "ENVELOPE_NOT_FOUND")

        if envelope.status != "draft":
            raise EsignError(f"Cannot send envelope in status '{envelope.status}'", "INVALID_STATUS")

        # Validate signers exist
        signers = self.db.execute(text("""
            SELECT id, name, email FROM esign_signers WHERE envelope_id = :id
        """), {"id": envelope_id}).fetchall()

        if not signers:
            raise EsignError("No signers assigned to envelope", "NO_SIGNERS")

        # Validate fields exist
        fields = self.db.execute(text("""
            SELECT id, signer_id FROM esign_fields WHERE envelope_id = :id
        """), {"id": envelope_id}).fetchall()

        if not fields:
            raise EsignError("No fields placed on envelope", "NO_FIELDS")

        try:
            # Lock envelope
            self.db.execute(text("""
                UPDATE esign_envelopes
                SET status = 'sent',
                    is_locked = TRUE,
                    locked_at = NOW(),
                    locked_by_user_id = :user_id,
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": envelope_id, "user_id": user_id})

            # Generate tokens for each signer
            signer_tokens = []
            for signer in signers:
                raw_token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                expires_at = datetime.now(timezone.utc) + timedelta(days=7)

                self.db.execute(text("""
                    UPDATE esign_signers
                    SET token_hash = :token_hash,
                        token_expires_at = :expires_at,
                        status = 'sent',
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": signer.id,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                })

                signer_tokens.append({
                    "signer_id": signer.id,
                    "name": signer.name,
                    "email": signer.email,
                    "token": raw_token,
                    "expires_at": expires_at.isoformat(),
                })

            # Log audit event
            self._log_audit_event(
                envelope_id=envelope_id,
                action="envelope_sent",
                description=f"Envelope sent to {len(signers)} signer(s)",
                actor_type="staff",
                actor_id=user_id,
                event_data={"signer_count": len(signers)},
            )

            self.db.commit()

            return {
                "success": True,
                "envelope_id": envelope_id,
                "signers": signer_tokens,
                "message": f"Envelope sent to {len(signers)} signer(s)"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error sending envelope: {e}")
            raise EsignError(str(e), "SEND_ENVELOPE_FAILED")

    def void_envelope(
        self,
        envelope_id: int,
        user_id: int,
        reason: str = None,
    ) -> Dict[str, Any]:
        """Void an envelope, invalidating all signing links."""
        envelope = self.db.execute(text("""
            SELECT id, status FROM esign_envelopes WHERE id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            raise EsignError("Envelope not found", "ENVELOPE_NOT_FOUND")

        if envelope.status in ["completed", "voided"]:
            raise EsignError(f"Cannot void envelope in status '{envelope.status}'", "INVALID_STATUS")

        try:
            self.db.execute(text("""
                UPDATE esign_envelopes
                SET status = 'voided', updated_at = NOW()
                WHERE id = :id
            """), {"id": envelope_id})

            # Invalidate all signer tokens
            self.db.execute(text("""
                UPDATE esign_signers
                SET token_hash = NULL, token_expires_at = NULL, updated_at = NOW()
                WHERE envelope_id = :id
            """), {"id": envelope_id})

            # Log audit event
            self._log_audit_event(
                envelope_id=envelope_id,
                action="envelope_voided",
                description=f"Envelope voided: {reason or 'No reason provided'}",
                actor_type="staff",
                actor_id=user_id,
                event_data={"reason": reason},
            )

            self.db.commit()

            return {
                "success": True,
                "envelope_id": envelope_id,
                "message": "Envelope voided successfully"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error voiding envelope: {e}")
            raise EsignError(str(e), "VOID_ENVELOPE_FAILED")

    # =========================================================================
    # SIGNER OPERATIONS
    # =========================================================================

    def add_signer(
        self,
        envelope_id: int,
        name: str,
        email: str,
        role: Optional[str] = None,
        signer_order: int = 1,
    ) -> Dict[str, Any]:
        """Add a signer to an envelope."""
        # Verify envelope exists and is not locked
        envelope = self.db.execute(text("""
            SELECT id, is_locked FROM esign_envelopes WHERE id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            raise EsignError("Envelope not found", "ENVELOPE_NOT_FOUND")

        if envelope.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        try:
            result = self.db.execute(text("""
                INSERT INTO esign_signers (
                    envelope_id, name, email, role, signer_order,
                    status, created_at, updated_at
                ) VALUES (
                    :envelope_id, :name, :email, :role, :signer_order,
                    'pending', NOW(), NOW()
                ) RETURNING id
            """), {
                "envelope_id": envelope_id,
                "name": name,
                "email": email.lower(),
                "role": role,
                "signer_order": signer_order,
            })

            signer_id = result.fetchone()[0]
            self.db.commit()

            return {
                "success": True,
                "signer_id": signer_id,
                "message": f"Signer '{name}' added"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            if "unique_signer_per_envelope" in str(e):
                raise EsignError(f"Signer with email '{email}' already exists", "DUPLICATE_SIGNER")
            logger.error(f"Error adding signer: {e}")
            raise EsignError(str(e), "ADD_SIGNER_FAILED")

    def remove_signer(self, signer_id: int) -> Dict[str, Any]:
        """Remove a signer from an envelope."""
        signer = self.db.execute(text("""
            SELECT s.id, s.envelope_id, e.is_locked
            FROM esign_signers s
            JOIN esign_envelopes e ON e.id = s.envelope_id
            WHERE s.id = :id
        """), {"id": signer_id}).fetchone()

        if not signer:
            raise EsignError("Signer not found", "SIGNER_NOT_FOUND")

        if signer.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        try:
            self.db.execute(text("DELETE FROM esign_signers WHERE id = :id"), {"id": signer_id})
            self.db.commit()

            return {
                "success": True,
                "message": "Signer removed"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error removing signer: {e}")
            raise EsignError(str(e), "REMOVE_SIGNER_FAILED")

    # =========================================================================
    # FIELD OPERATIONS
    # =========================================================================

    def add_field(
        self,
        envelope_id: int,
        field_type: str,
        page_number: int,
        x_position_points: float,
        y_position_points: float,
        width_points: float = 144.0,
        height_points: float = 36.0,
        signer_id: Optional[int] = None,
        is_required: bool = True,
        placeholder_text: Optional[str] = None,
        tab_order: int = 0,
    ) -> Dict[str, Any]:
        """Add a field to an envelope."""
        # Verify envelope exists and is not locked
        envelope = self.db.execute(text("""
            SELECT id, is_locked FROM esign_envelopes WHERE id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            raise EsignError("Envelope not found", "ENVELOPE_NOT_FOUND")

        if envelope.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        # Validate field type
        valid_types = ["signature", "initial", "date_signed", "text", "checkbox", "dropdown"]
        if field_type not in valid_types:
            raise EsignError(f"Invalid field type: {field_type}", "INVALID_FIELD_TYPE")

        try:
            result = self.db.execute(text("""
                INSERT INTO esign_fields (
                    envelope_id, signer_id, field_type, page_number,
                    x_position_points, y_position_points, width_points, height_points,
                    is_required, placeholder_text, tab_order,
                    created_at, updated_at
                ) VALUES (
                    :envelope_id, :signer_id, :field_type, :page_number,
                    :x_position_points, :y_position_points, :width_points, :height_points,
                    :is_required, :placeholder_text, :tab_order,
                    NOW(), NOW()
                ) RETURNING id
            """), {
                "envelope_id": envelope_id,
                "signer_id": signer_id,
                "field_type": field_type,
                "page_number": page_number,
                "x_position_points": x_position_points,
                "y_position_points": y_position_points,
                "width_points": width_points,
                "height_points": height_points,
                "is_required": is_required,
                "placeholder_text": placeholder_text,
                "tab_order": tab_order,
            })

            field_id = result.fetchone()[0]
            self.db.commit()

            return {
                "success": True,
                "field_id": field_id,
                "message": f"{field_type} field added"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error adding field: {e}")
            raise EsignError(str(e), "ADD_FIELD_FAILED")

    def update_field(
        self,
        field_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Update a field's properties."""
        field = self.db.execute(text("""
            SELECT f.id, f.envelope_id, e.is_locked
            FROM esign_fields f
            JOIN esign_envelopes e ON e.id = f.envelope_id
            WHERE f.id = :id
        """), {"id": field_id}).fetchone()

        if not field:
            raise EsignError("Field not found", "FIELD_NOT_FOUND")

        if field.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        allowed_fields = [
            "signer_id", "page_number", "x_position_points", "y_position_points",
            "width_points", "height_points", "is_required", "placeholder_text", "tab_order"
        ]

        updates = []
        params = {"id": field_id}

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                updates.append(f"{key} = :{key}")
                params[key] = value

        if not updates:
            return {"success": True, "message": "No updates provided"}

        updates.append("updated_at = NOW()")

        try:
            sql = "UPDATE esign_fields SET " + ", ".join(updates) + " WHERE id = :id"
            self.db.execute(text(sql), params)

            self.db.commit()

            return {
                "success": True,
                "field_id": field_id,
                "message": "Field updated"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error updating field: {e}")
            raise EsignError(str(e), "UPDATE_FIELD_FAILED")

    def delete_field(self, field_id: int) -> Dict[str, Any]:
        """Delete a field."""
        field = self.db.execute(text("""
            SELECT f.id, f.envelope_id, e.is_locked
            FROM esign_fields f
            JOIN esign_envelopes e ON e.id = f.envelope_id
            WHERE f.id = :id
        """), {"id": field_id}).fetchone()

        if not field:
            raise EsignError("Field not found", "FIELD_NOT_FOUND")

        if field.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        try:
            self.db.execute(text("DELETE FROM esign_fields WHERE id = :id"), {"id": field_id})
            self.db.commit()

            return {
                "success": True,
                "message": "Field deleted"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error deleting field: {e}")
            raise EsignError(str(e), "DELETE_FIELD_FAILED")

    def bulk_save_fields(
        self,
        envelope_id: int,
        fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk save fields (delete existing, insert new)."""
        envelope = self.db.execute(text("""
            SELECT id, is_locked FROM esign_envelopes WHERE id = :id
        """), {"id": envelope_id}).fetchone()

        if not envelope:
            raise EsignError("Envelope not found", "ENVELOPE_NOT_FOUND")

        if envelope.is_locked:
            raise EsignError("Cannot modify locked envelope", "ENVELOPE_LOCKED")

        try:
            # Delete existing fields
            self.db.execute(text("""
                DELETE FROM esign_fields WHERE envelope_id = :id
            """), {"id": envelope_id})

            # Insert new fields
            for field in fields:
                self.db.execute(text("""
                    INSERT INTO esign_fields (
                        envelope_id, signer_id, field_type, page_number,
                        x_position_points, y_position_points, width_points, height_points,
                        is_required, placeholder_text, tab_order,
                        created_at, updated_at
                    ) VALUES (
                        :envelope_id, :signer_id, :field_type, :page_number,
                        :x_position_points, :y_position_points, :width_points, :height_points,
                        :is_required, :placeholder_text, :tab_order,
                        NOW(), NOW()
                    )
                """), {
                    "envelope_id": envelope_id,
                    "signer_id": field.get("signer_id"),
                    "field_type": field.get("field_type", "signature"),
                    "page_number": field.get("page_number", 1),
                    "x_position_points": field.get("x_position_points", 0),
                    "y_position_points": field.get("y_position_points", 0),
                    "width_points": field.get("width_points", 144.0),
                    "height_points": field.get("height_points", 36.0),
                    "is_required": field.get("is_required", True),
                    "placeholder_text": field.get("placeholder_text"),
                    "tab_order": field.get("tab_order", 0),
                })

            self.db.commit()

            return {
                "success": True,
                "field_count": len(fields),
                "message": f"{len(fields)} fields saved"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error bulk saving fields: {e}")
            raise EsignError(str(e), "BULK_SAVE_FAILED")

    # =========================================================================
    # SIGNING SESSION OPERATIONS
    # =========================================================================

    def validate_signing_token(
        self,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate a signing token and return session data."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        signer = self.db.execute(text("""
            SELECT s.*, e.name as envelope_name, e.pdf_storage_key, e.pdf_file_name,
                   e.pdf_page_count, e.pdf_page_dimensions, e.status as envelope_status
            FROM esign_signers s
            JOIN esign_envelopes e ON e.id = s.envelope_id
            WHERE s.token_hash = :token_hash
        """), {"token_hash": token_hash}).fetchone()

        if not signer:
            raise EsignError("Invalid or expired token", "INVALID_TOKEN")

        # Check token expiration
        if signer.token_expires_at and signer.token_expires_at < datetime.now(timezone.utc):
            raise EsignError("Token has expired", "TOKEN_EXPIRED")

        # Check envelope status
        if signer.envelope_status in ["voided", "expired", "declined"]:
            raise EsignError(f"Envelope is {signer.envelope_status}", "ENVELOPE_UNAVAILABLE")

        if signer.envelope_status == "completed":
            raise EsignError("Signing already completed", "ALREADY_COMPLETED")

        # Update signer access info
        if not signer.viewed_at:
            self.db.execute(text("""
                UPDATE esign_signers
                SET viewed_at = NOW(), status = 'viewed', updated_at = NOW()
                WHERE id = :id
            """), {"id": signer.id})

            # Log audit event
            self._log_audit_event(
                envelope_id=signer.envelope_id,
                signer_id=signer.id,
                action="signer_viewed",
                description=f"{signer.name} viewed the document",
                actor_type="signer",
                actor_id=signer.id,
                actor_email=signer.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        self.db.execute(text("""
            UPDATE esign_signers
            SET last_access_at = NOW(),
                last_access_ip = :ip,
                last_access_user_agent = :ua
            WHERE id = :id
        """), {"id": signer.id, "ip": ip_address, "ua": user_agent})

        # Log access event
        self._log_audit_event(
            envelope_id=signer.envelope_id,
            signer_id=signer.id,
            action="link_accessed",
            description=f"Signing link accessed",
            actor_type="signer",
            actor_id=signer.id,
            actor_email=signer.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()

        # Get fields for this signer
        fields = self.db.execute(text("""
            SELECT f.*, fv.id as value_id, fv.text_value, fv.boolean_value
            FROM esign_fields f
            LEFT JOIN esign_field_values fv ON fv.field_id = f.id AND fv.signer_id = :signer_id
            WHERE f.envelope_id = :envelope_id
              AND (f.signer_id = :signer_id OR f.signer_id IS NULL)
            ORDER BY f.page_number, f.tab_order, f.id
        """), {"envelope_id": signer.envelope_id, "signer_id": signer.id}).fetchall()

        return {
            "valid": True,
            "signer_id": signer.id,
            "signer_name": signer.name,
            "signer_email": signer.email,
            "envelope_id": signer.envelope_id,
            "envelope_name": signer.envelope_name,
            "has_adopted_signature": signer.has_adopted_signature,
            "adopted_signature_text": signer.adopted_signature_text,
            "adopted_signature_font": signer.adopted_signature_font,
            "pdf_storage_key": signer.pdf_storage_key,
            "pdf_file_name": signer.pdf_file_name,
            "pdf_page_count": signer.pdf_page_count,
            "pdf_page_dimensions": signer.pdf_page_dimensions,
            "fields": [dict(f._mapping) for f in fields],
        }

    def adopt_signature(
        self,
        token: str,
        signature_text: str,
        signature_font: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adopt a typed signature for the signing session."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        signer = self.db.execute(text("""
            SELECT id, envelope_id, name, email, has_adopted_signature
            FROM esign_signers
            WHERE token_hash = :token_hash AND token_expires_at > NOW()
        """), {"token_hash": token_hash}).fetchone()

        if not signer:
            raise EsignError("Invalid or expired token", "INVALID_TOKEN")

        try:
            self.db.execute(text("""
                UPDATE esign_signers
                SET has_adopted_signature = TRUE,
                    adopted_signature_text = :text,
                    adopted_signature_font = :font,
                    adopted_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": signer.id,
                "text": signature_text,
                "font": signature_font,
            })

            # Log audit event
            self._log_audit_event(
                envelope_id=signer.envelope_id,
                signer_id=signer.id,
                action="signature_adopted",
                description=f"{signer.name} adopted signature",
                actor_type="signer",
                actor_id=signer.id,
                actor_email=signer.email,
                ip_address=ip_address,
                user_agent=user_agent,
                event_data={"font": signature_font},
            )

            self.db.commit()

            return {
                "success": True,
                "message": "Signature adopted"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error adopting signature: {e}")
            raise EsignError(str(e), "ADOPT_SIGNATURE_FAILED")

    def submit_field_value(
        self,
        token: str,
        field_id: int,
        value: Any,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a value for a field."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        signer = self.db.execute(text("""
            SELECT id, envelope_id, name, email
            FROM esign_signers
            WHERE token_hash = :token_hash AND token_expires_at > NOW()
        """), {"token_hash": token_hash}).fetchone()

        if not signer:
            raise EsignError("Invalid or expired token", "INVALID_TOKEN")

        # Get field info
        field = self.db.execute(text("""
            SELECT id, envelope_id, field_type, signer_id
            FROM esign_fields
            WHERE id = :id AND envelope_id = :envelope_id
        """), {"id": field_id, "envelope_id": signer.envelope_id}).fetchone()

        if not field:
            raise EsignError("Field not found", "FIELD_NOT_FOUND")

        # Verify signer assignment
        if field.signer_id and field.signer_id != signer.id:
            raise EsignError("Field not assigned to this signer", "FIELD_NOT_ASSIGNED")

        try:
            # Determine value type
            value_type = field.field_type
            text_value = None
            boolean_value = None
            date_value = None

            if field.field_type in ["signature", "initial", "text", "dropdown"]:
                text_value = str(value) if value else None
                value_type = "text" if field.field_type in ["text", "dropdown"] else "signature"
            elif field.field_type == "checkbox":
                boolean_value = bool(value)
                value_type = "checkbox"
            elif field.field_type == "date_signed":
                date_value = datetime.now(timezone.utc)
                text_value = date_value.strftime("%m/%d/%Y")
                value_type = "date"

            # Delete existing value (if any) then insert new value
            self.db.execute(text("""
                DELETE FROM esign_field_values
                WHERE field_id = :field_id AND signer_id = :signer_id
            """), {"field_id": field_id, "signer_id": signer.id})

            self.db.execute(text("""
                INSERT INTO esign_field_values (
                    field_id, signer_id, value_type,
                    text_value, boolean_value, date_value,
                    completed_at, completed_ip, completed_user_agent, server_timestamp
                ) VALUES (
                    :field_id, :signer_id, :value_type,
                    :text_value, :boolean_value, :date_value,
                    NOW(), :ip, :ua, NOW()
                )
            """), {
                "field_id": field_id,
                "signer_id": signer.id,
                "value_type": value_type,
                "text_value": text_value,
                "boolean_value": boolean_value,
                "date_value": date_value,
                "ip": ip_address,
                "ua": user_agent,
            })

            # Log audit event
            self._log_audit_event(
                envelope_id=signer.envelope_id,
                signer_id=signer.id,
                field_id=field_id,
                action="field_completed",
                description=f"{signer.name} completed {field.field_type} field",
                actor_type="signer",
                actor_id=signer.id,
                actor_email=signer.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            self.db.commit()

            return {
                "success": True,
                "field_id": field_id,
                "message": "Field value saved"
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error submitting field value: {e}")
            raise EsignError(str(e), "SUBMIT_VALUE_FAILED")

    def complete_signing(
        self,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete signing for a signer.
        Validates all required fields are completed.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        signer = self.db.execute(text("""
            SELECT id, envelope_id, name, email, has_adopted_signature
            FROM esign_signers
            WHERE token_hash = :token_hash AND token_expires_at > NOW()
        """), {"token_hash": token_hash}).fetchone()

        if not signer:
            raise EsignError("Invalid or expired token", "INVALID_TOKEN")

        # Get required fields for this signer
        required_fields = self.db.execute(text("""
            SELECT f.id, f.field_type
            FROM esign_fields f
            WHERE f.envelope_id = :envelope_id
              AND f.is_required = TRUE
              AND (f.signer_id = :signer_id OR f.signer_id IS NULL)
        """), {"envelope_id": signer.envelope_id, "signer_id": signer.id}).fetchall()

        # Get completed field values
        completed_values = self.db.execute(text("""
            SELECT field_id FROM esign_field_values WHERE signer_id = :signer_id
        """), {"signer_id": signer.id}).fetchall()

        completed_field_ids = {v.field_id for v in completed_values}

        # Check for missing required fields
        missing_fields = [f for f in required_fields if f.id not in completed_field_ids]

        if missing_fields:
            raise EsignError(
                f"Missing {len(missing_fields)} required field(s)",
                "MISSING_REQUIRED_FIELDS"
            )

        # Check signature adoption for signature/initial fields
        signature_fields = [f for f in required_fields if f.field_type in ["signature", "initial"]]
        if signature_fields and not signer.has_adopted_signature:
            raise EsignError("Signature must be adopted first", "SIGNATURE_NOT_ADOPTED")

        try:
            # Mark signer as signed
            self.db.execute(text("""
                UPDATE esign_signers
                SET status = 'signed',
                    signed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": signer.id})

            # Log audit event
            self._log_audit_event(
                envelope_id=signer.envelope_id,
                signer_id=signer.id,
                action="signing_completed",
                description=f"{signer.name} completed signing",
                actor_type="signer",
                actor_id=signer.id,
                actor_email=signer.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Check if all signers have completed
            pending_signers = self.db.execute(text("""
                SELECT COUNT(*) FROM esign_signers
                WHERE envelope_id = :envelope_id AND status != 'signed'
            """), {"envelope_id": signer.envelope_id}).scalar()

            envelope_completed = pending_signers == 0

            if envelope_completed:
                self.db.execute(text("""
                    UPDATE esign_envelopes
                    SET status = 'completed',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                """), {"id": signer.envelope_id})

            self.db.commit()

            return {
                "success": True,
                "signer_completed": True,
                "envelope_completed": envelope_completed,
                "message": "Signing completed" + (" - all signers done!" if envelope_completed else "")
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error completing signing: {e}")
            raise EsignError(str(e), "COMPLETE_SIGNING_FAILED")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _log_audit_event(
        self,
        envelope_id: int,
        action: str,
        description: str,
        actor_type: str,
        signer_id: Optional[int] = None,
        field_id: Optional[int] = None,
        actor_id: Optional[int] = None,
        actor_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        event_data: Optional[Dict] = None,
    ):
        """Log an audit event."""
        self.db.execute(text("""
            INSERT INTO esign_audit_events (
                envelope_id, signer_id, field_id,
                action, description, event_data,
                actor_type, actor_id, actor_email,
                ip_address, user_agent, created_at
            ) VALUES (
                :envelope_id, :signer_id, :field_id,
                :action, :description, :event_data,
                :actor_type, :actor_id, :actor_email,
                :ip_address, :user_agent, NOW()
            )
        """), {
            "envelope_id": envelope_id,
            "signer_id": signer_id,
            "field_id": field_id,
            "action": action,
            "description": description,
            "event_data": json.dumps(event_data) if event_data else None,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })

    def get_audit_trail(self, envelope_id: int) -> List[Dict[str, Any]]:
        """Get audit trail for an envelope."""
        events = self.db.execute(text("""
            SELECT * FROM esign_audit_events
            WHERE envelope_id = :envelope_id
            ORDER BY created_at ASC
        """), {"envelope_id": envelope_id}).fetchall()

        return [dict(e._mapping) for e in events]
