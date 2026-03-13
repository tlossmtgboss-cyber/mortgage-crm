"""
E-Signature Envelope Management Service

Built-in e-signature system -- no third-party providers (DocuSign, etc.).
All signing operations happen on our platform with a full audit trail.

Manages the complete lifecycle of signing envelopes:
  1. CREATE: LO creates envelope with document, recipients, and fields
  2. SEND: System sends signing links to recipients (in signing order)
  3. VIEW: Recipient opens the document via signing URL
  4. SIGN: Recipient fills fields and applies signature
  5. COMPLETE: All recipients signed -> generate completion certificate

Features:
  - Sequential or parallel signing order
  - Multiple authentication methods (email link, SMS code, access code)
  - Field-level signing (signature, initials, date, text, checkbox)
  - Real-time status tracking with recipient-level granularity
  - Comprehensive immutable audit trail
  - Completion certificate generation (HMAC-based)
  - Automated reminder management
  - Void / cancel capability with recipient notification
  - Template-based envelope creation
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response data classes
# ---------------------------------------------------------------------------

@dataclass
class EnvelopeCreateRequest:
    """Request to create a new signing envelope."""
    loan_id: int
    organization_id: int
    created_by_user_id: int
    title: str
    description: Optional[str]
    document_storage_key: str  # S3 key of document to sign
    recipients: List[Dict]  # [{name, email, type, signing_order, auth_method}]
    fields: List[Dict]  # [{type, page, x, y, width, height, recipient_index, required}]
    expires_in_days: int = 30
    reminder_frequency_hours: int = 48
    ip_address: Optional[str] = None


@dataclass
class SigningSession:
    """Active signing session data returned to the frontend."""
    envelope_uuid: str
    recipient_id: int
    signer_name: str
    signer_email: str
    document_url: str
    fields: List[Dict]
    envelope_title: str
    expires_at: str
    is_last_signer: bool


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ESignatureEnvelopeService:
    """
    Manages the complete lifecycle of e-signature envelopes.

    Workflow:
    1. CREATE: LO creates envelope with document, recipients, fields
    2. SEND: System sends signing links to recipients (in order)
    3. VIEW: Recipient opens the document
    4. SIGN: Recipient fills fields and signs
    5. COMPLETE: All recipients signed -> generate certificate

    Features:
    - Sequential or parallel signing order
    - Multiple authentication methods (email link, SMS code, access code)
    - Field-level signing (signature, initials, date, text, checkbox)
    - Real-time status tracking
    - Comprehensive audit trail
    - Completion certificate generation
    - Reminder management
    - Void/cancel capability
    """

    def __init__(self, db: Session):
        self.db = db
        from services.smart_docs.esignature_crypto_service import get_esignature_crypto_service
        self.crypto = get_esignature_crypto_service()
        self._frontend_base_url = os.getenv(
            "ESIGN_FRONTEND_URL",
            "https://app.perenniaai.com/esign",
        )
        self._api_base_url = os.getenv(
            "ESIGN_API_BASE_URL",
            "https://api.perenniaai.com/api/v1/esign",
        )

    # ------------------------------------------------------------------
    # 1. Create envelope
    # ------------------------------------------------------------------

    def create_envelope(self, request: EnvelopeCreateRequest) -> Dict:
        """
        Create a new signing envelope with recipients and fields.

        This is an atomic operation: envelope + recipients + fields + audit
        event are all committed together.  If any step fails, everything
        is rolled back.

        Steps:
          - Fetch the document from S3 and compute its SHA-256 hash
          - Create ESignatureEnvelope record (status=DRAFT)
          - Create ESignatureRecipient records for each recipient
          - Create ESignatureField records for each field
          - Log CREATED audit event

        Returns:
            Dict with envelope details including envelope_uuid.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            ESignatureField,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
            RecipientAuthMethod,
        )
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        from services.smart_docs.db_transaction import atomic_operation

        now = datetime.now(timezone.utc)
        envelope_uuid = self.crypto.generate_envelope_uuid()

        # --- Fetch document from S3 and compute hash (outside transaction) ---
        s3 = get_smart_docs_s3_service()
        doc_result = s3.download_file(request.document_storage_key)
        if not doc_result.get("success"):
            raise ValueError(
                f"Failed to fetch document from S3: {doc_result.get('error', 'unknown')}"
            )
        document_content: bytes = doc_result["content"]
        document_hash = self.crypto.hash_document(document_content)

        try:
            with atomic_operation(self.db):
                # --- Create envelope record ---
                envelope = ESignatureEnvelope()
                envelope.envelope_uuid = envelope_uuid
                envelope.organization_id = request.organization_id
                envelope.loan_id = request.loan_id
                envelope.created_by_user_id = request.created_by_user_id
                envelope.title = request.title
                envelope.description = request.description
                envelope.document_storage_key = request.document_storage_key
                envelope.document_hash_sha256 = document_hash
                envelope.status = EnvelopeStatus.DRAFT.value
                envelope.total_recipients = len(
                    [r for r in request.recipients if r.get("type", "signer") == "signer"]
                )
                envelope.completed_recipients = 0
                envelope.expires_at = now + timedelta(days=request.expires_in_days)
                envelope.reminder_frequency_hours = request.reminder_frequency_hours
                envelope.ip_address_created = request.ip_address
                envelope.created_at = now
                envelope.updated_at = now

                self.db.add(envelope)
                self.db.flush()  # populate envelope.id

                # --- Create recipient records ---
                recipient_records: List[ESignatureRecipient] = []
                for idx, r in enumerate(request.recipients):
                    rec = ESignatureRecipient()
                    rec.envelope_id = envelope.id
                    rec.name = r["name"]
                    rec.email = r["email"]
                    rec.phone = r.get("phone")
                    rec.recipient_type = r.get("type", RecipientType.SIGNER.value)
                    rec.signing_order = r.get("signing_order", idx + 1)
                    rec.auth_method = r.get("auth_method", RecipientAuthMethod.EMAIL_LINK.value)
                    rec.status = RecipientStatus.PENDING.value
                    rec.created_at = now
                    rec.updated_at = now

                    # Generate access code if auth method requires it
                    if rec.auth_method == RecipientAuthMethod.ACCESS_CODE.value:
                        raw_code = self.crypto.generate_access_code()
                        rec.access_code = self.crypto.hash_access_code(raw_code)

                    self.db.add(rec)
                    self.db.flush()
                    recipient_records.append(rec)

                # --- Create field records ---
                for f in request.fields:
                    recipient_index = f.get("recipient_index", 0)
                    recipient_id = (
                        recipient_records[recipient_index].id
                        if recipient_index < len(recipient_records)
                        else None
                    )

                    field = ESignatureField()
                    field.envelope_id = envelope.id
                    field.recipient_id = recipient_id
                    field.field_type = f["type"]
                    field.field_uuid = str(uuid.uuid4())
                    field.page_number = f["page"]
                    field.x_position = f["x"]
                    field.y_position = f["y"]
                    field.width = f["width"]
                    field.height = f["height"]
                    field.is_required = f.get("required", True)
                    field.placeholder_text = f.get("placeholder")
                    field.default_value = f.get("default_value")
                    field.validation_regex = f.get("validation_regex")
                    field.dropdown_options = f.get("dropdown_options")
                    field.group_name = f.get("group_name")
                    field.created_at = now

                    self.db.add(field)

                # --- Audit event ---
                self._log_audit_event(
                    envelope_id=envelope.id,
                    recipient_id=None,
                    event_type="created",
                    description=f"Envelope '{request.title}' created with {len(request.recipients)} recipients",
                    ip_address=request.ip_address,
                    metadata={
                        "document_hash": document_hash,
                        "total_recipients": len(request.recipients),
                        "total_fields": len(request.fields),
                    },
                )
                # atomic_operation commits here
        except Exception as e:
            logger.exception(
                "Failed to create envelope for loan %s: %s",
                request.loan_id, e,
            )
            raise

        logger.info(
            "Created envelope %s for loan %s with %d recipients, %d fields",
            envelope_uuid,
            request.loan_id,
            len(request.recipients),
            len(request.fields),
        )

        return {
            "envelope_uuid": envelope_uuid,
            "envelope_id": envelope.id,
            "status": envelope.status,
            "title": envelope.title,
            "document_hash": document_hash,
            "total_recipients": envelope.total_recipients,
            "expires_at": envelope.expires_at.isoformat(),
            "recipients": [
                {
                    "id": r.id,
                    "name": r.name,
                    "email": r.email,
                    "type": r.recipient_type,
                    "signing_order": r.signing_order,
                    "status": r.status,
                }
                for r in recipient_records
            ],
        }

    # ------------------------------------------------------------------
    # 2. Send envelope
    # ------------------------------------------------------------------

    def send_envelope(self, envelope_uuid: str, sender_user_id: int) -> Dict:
        """
        Transition the envelope from DRAFT to SENT and dispatch signing
        invitations to the first-order recipients.

        Returns:
            Dict with send confirmation and recipient details.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
        )

        now = datetime.now(timezone.utc)

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        if envelope.status not in (EnvelopeStatus.DRAFT.value,):
            raise ValueError(
                f"Cannot send envelope in status '{envelope.status}' -- must be DRAFT"
            )

        # Get sender name for emails
        sender_name = self._get_user_display_name(sender_user_id)

        # Update envelope status
        envelope.status = EnvelopeStatus.SENT.value
        envelope.sent_at = now
        envelope.updated_at = now

        # Find recipients in the first signing order group
        recipients = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )

        if not recipients:
            raise ValueError("Envelope has no recipients")

        first_order = min(r.signing_order for r in recipients)
        first_batch = [
            r for r in recipients
            if r.signing_order == first_order
            and r.recipient_type in (RecipientType.SIGNER.value, RecipientType.APPROVER.value)
        ]

        sent_recipients = []
        for recipient in first_batch:
            # Generate signing token
            token, expires_at = self.crypto.generate_signing_token(
                recipient_id=recipient.id,
                envelope_uuid=envelope_uuid,
            )
            recipient.signing_token = token
            recipient.signing_token_expires_at = expires_at
            recipient.status = RecipientStatus.SENT.value
            recipient.updated_at = now

            # Build signing URL
            signing_url = f"{self._frontend_base_url}/sign/{token}"

            # Send signing email
            try:
                self._send_signing_email(
                    recipient_name=recipient.name,
                    recipient_email=recipient.email,
                    envelope_title=envelope.title,
                    signing_url=signing_url,
                    sender_name=sender_name,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send signing email to %s for envelope %s: %s",
                    recipient.email,
                    envelope_uuid,
                    e,
                )

            # Audit
            self._log_audit_event(
                envelope_id=envelope.id,
                recipient_id=recipient.id,
                event_type="sent",
                description=f"Signing invitation sent to {recipient.name} ({recipient.email})",
                metadata={"signing_order": recipient.signing_order},
            )

            sent_recipients.append({
                "id": recipient.id,
                "name": recipient.name,
                "email": recipient.email,
                "signing_order": recipient.signing_order,
            })

        # Also notify CC recipients immediately
        cc_recipients = [
            r for r in recipients
            if r.recipient_type == RecipientType.CC.value
        ]
        for cc in cc_recipients:
            cc.status = RecipientStatus.DELIVERED.value
            cc.updated_at = now

        self.db.commit()

        logger.info(
            "Sent envelope %s to %d first-order recipients",
            envelope_uuid,
            len(sent_recipients),
        )

        return {
            "envelope_uuid": envelope_uuid,
            "status": envelope.status,
            "sent_at": now.isoformat(),
            "recipients_notified": len(sent_recipients),
            "recipients": sent_recipients,
        }

    # ------------------------------------------------------------------
    # 3. Get signing session
    # ------------------------------------------------------------------

    def get_signing_session(
        self,
        token: str,
        ip_address: str,
        user_agent: str,
    ) -> SigningSession:
        """
        Validate a signing token and return a session for the signer.

        - Marks the recipient as VIEWED on first access.
        - Generates a pre-signed S3 URL for document viewing.
        - Returns the fields the signer needs to fill.

        Raises:
            ValueError: If the token is invalid or envelope is not signable.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            ESignatureField,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
        )
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

        now = datetime.now(timezone.utc)

        # Look up recipient by token
        recipient = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.signing_token == token)
            .first()
        )
        if not recipient:
            raise ValueError("Invalid signing token")

        # Check token expiry
        if recipient.signing_token_expires_at and now > recipient.signing_token_expires_at:
            raise ValueError("Signing token has expired")

        # Check recipient is in a state that allows viewing
        if recipient.status in (
            RecipientStatus.SIGNED.value,
            RecipientStatus.DECLINED.value,
        ):
            raise ValueError(f"Recipient has already {recipient.status}")

        # Load envelope
        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.id == recipient.envelope_id)
            .first()
        )
        if not envelope:
            raise ValueError("Envelope not found")

        # Check envelope is still active
        if envelope.status in (
            EnvelopeStatus.COMPLETED.value,
            EnvelopeStatus.VOIDED.value,
            EnvelopeStatus.DECLINED.value,
            EnvelopeStatus.EXPIRED.value,
        ):
            raise ValueError(f"Envelope is {envelope.status} and cannot be signed")

        # Check envelope expiry
        if envelope.expires_at and now > envelope.expires_at:
            envelope.status = EnvelopeStatus.EXPIRED.value
            envelope.updated_at = now
            self.db.commit()
            raise ValueError("Envelope has expired")

        # Mark as viewed on first access
        if recipient.status in (
            RecipientStatus.PENDING.value,
            RecipientStatus.SENT.value,
            RecipientStatus.DELIVERED.value,
        ):
            recipient.status = RecipientStatus.VIEWED.value
            recipient.viewed_at = now
            recipient.updated_at = now

            # Update envelope status if this is the first view
            if envelope.status == EnvelopeStatus.SENT.value:
                envelope.status = EnvelopeStatus.VIEWED.value
                envelope.viewed_at = now
                envelope.updated_at = now

            self._log_audit_event(
                envelope_id=envelope.id,
                recipient_id=recipient.id,
                event_type="viewed",
                description=f"{recipient.name} viewed the document",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"document_hash": envelope.document_hash_sha256},
            )
            self.db.commit()

        # Generate pre-signed URL for document
        s3 = get_smart_docs_s3_service()
        url_result = s3.get_presigned_download_url(
            storage_key=envelope.document_storage_key,
            file_name=envelope.original_filename or f"{envelope.title}.pdf",
            expires_in=3600,  # 1 hour for signing sessions
            inline=True,
            organization_id=envelope.organization_id,
        )
        document_url = url_result.get("presigned_url", "")

        # Get fields assigned to this recipient
        fields = (
            self.db.query(ESignatureField)
            .filter(
                ESignatureField.envelope_id == envelope.id,
                ESignatureField.recipient_id == recipient.id,
            )
            .order_by(ESignatureField.page_number.asc(), ESignatureField.y_position.asc())
            .all()
        )

        field_dicts = [
            {
                "field_uuid": f.field_uuid,
                "type": f.field_type,
                "page": f.page_number,
                "x": f.x_position,
                "y": f.y_position,
                "width": f.width,
                "height": f.height,
                "required": f.is_required,
                "placeholder": f.placeholder_text,
                "default_value": f.default_value,
                "validation_regex": f.validation_regex,
                "dropdown_options": f.dropdown_options,
                "group_name": f.group_name,
                "value": f.value,
            }
            for f in fields
        ]

        # Determine if this is the last signer
        all_signers = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
            )
            .all()
        )
        unsigned_others = [
            s for s in all_signers
            if s.id != recipient.id and s.status != RecipientStatus.SIGNED.value
        ]
        is_last_signer = len(unsigned_others) == 0

        return SigningSession(
            envelope_uuid=envelope.envelope_uuid,
            recipient_id=recipient.id,
            signer_name=recipient.name,
            signer_email=recipient.email,
            document_url=document_url,
            fields=field_dicts,
            envelope_title=envelope.title,
            expires_at=envelope.expires_at.isoformat() if envelope.expires_at else "",
            is_last_signer=is_last_signer,
        )

    # ------------------------------------------------------------------
    # 4. Submit signature
    # ------------------------------------------------------------------

    def submit_signature(
        self,
        token: str,
        field_values: Dict,
        signature_image: Optional[bytes],
        ip_address: str,
        user_agent: str,
        geo_location: Optional[str] = None,
    ) -> Dict:
        """
        Process a recipient's signature submission.

        Uses SELECT FOR UPDATE on the recipient row to prevent concurrent
        signing race conditions (e.g. double-click, duplicate tab).
        The entire signing operation (field updates, status change,
        envelope completion check) is atomic.

        - Validates the token and all required fields.
        - Generates a cryptographic signature hash.
        - Stores the signature image to S3 (if provided).
        - Updates field values and recipient status to SIGNED.
        - If all recipients are done, completes the envelope.
        - If sequential signing, sends to the next recipient group.

        Returns:
            Dict with signing result and next-step information.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            ESignatureField,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
        )
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        from services.smart_docs.db_transaction import select_for_update

        now = datetime.now(timezone.utc)

        # --- Validate token and lock the recipient row ---
        # First look up the recipient ID by token (lightweight query)
        recipient_lookup = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.signing_token == token)
            .first()
        )
        if not recipient_lookup:
            raise ValueError("Invalid signing token")

        # Now lock the row with SELECT FOR UPDATE to prevent concurrent signing
        recipient = select_for_update(self.db, ESignatureRecipient, recipient_lookup.id)
        if not recipient:
            raise ValueError("Invalid signing token")

        if recipient.signing_token_expires_at and now > recipient.signing_token_expires_at:
            raise ValueError("Signing token has expired")

        if recipient.status == RecipientStatus.SIGNED.value:
            raise ValueError("Recipient has already signed")

        if recipient.status == RecipientStatus.DECLINED.value:
            raise ValueError("Recipient has declined signing")

        # Lock the envelope too to prevent concurrent modifications
        envelope = select_for_update(self.db, ESignatureEnvelope, recipient.envelope_id)
        if not envelope:
            raise ValueError("Envelope not found")

        if envelope.status in (
            EnvelopeStatus.COMPLETED.value,
            EnvelopeStatus.VOIDED.value,
            EnvelopeStatus.DECLINED.value,
            EnvelopeStatus.EXPIRED.value,
        ):
            raise ValueError(f"Envelope is {envelope.status} and cannot be signed")

        # --- ESIGN Act: verify consent before allowing signature ---
        from services.smart_docs.esign_consent_service import ESignConsentService
        consent_svc = ESignConsentService(self.db)
        if not consent_svc.verify_consent(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        ):
            raise ValueError(
                "ESIGN Act consent is required before signing. "
                "Please review the consent disclosure and provide consent."
            )

        # --- KBA: verify identity if required ---
        from services.smart_docs.esign_kba_service import KBAService
        kba_svc = KBAService(self.db)
        if kba_svc.check_kba_required_for_recipient(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        ):
            from database.models.esignature import ESignKBASession
            kba_session = (
                self.db.query(ESignKBASession)
                .filter(
                    ESignKBASession.recipient_id == recipient.id,
                    ESignKBASession.envelope_id == envelope.id,
                    ESignKBASession.passed.is_(True),
                )
                .first()
            )
            if not kba_session:
                raise ValueError(
                    "Identity verification (KBA) is required before signing. "
                    "Please complete the identity verification step."
                )

        # --- Validate required fields ---
        fields = (
            self.db.query(ESignatureField)
            .filter(
                ESignatureField.envelope_id == envelope.id,
                ESignatureField.recipient_id == recipient.id,
            )
            .all()
        )

        missing_fields = []
        for field in fields:
            if field.is_required and field.field_uuid not in field_values:
                missing_fields.append(field.field_uuid)

        if missing_fields:
            raise ValueError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        # --- Generate signature hash ---
        signature_hash = self.crypto.generate_signature_hash(
            document_hash=envelope.document_hash_sha256,
            signer_email=recipient.email,
            signed_at=now,
            ip_address=ip_address,
        )

        # --- Store signature image to S3 ---
        signature_image_key = None
        if signature_image:
            s3 = get_smart_docs_s3_service()
            sig_key = (
                f"org/{envelope.organization_id}/esign/"
                f"{envelope.envelope_uuid}/signatures/"
                f"{recipient.id}_{uuid.uuid4().hex[:8]}.png"
            )
            upload_result = s3.upload_file(
                file_content=signature_image,
                storage_key=sig_key,
                content_type="image/png",
                metadata={
                    "envelope_uuid": envelope.envelope_uuid,
                    "recipient_id": str(recipient.id),
                    "signed_at": now.isoformat(),
                },
            )
            if upload_result.get("success"):
                signature_image_key = sig_key
            else:
                logger.warning(
                    "Failed to upload signature image for recipient %s: %s",
                    recipient.id,
                    upload_result.get("error"),
                )

        # --- All DB mutations within atomic_operation ---
        from services.smart_docs.db_transaction import atomic_operation

        try:
            with atomic_operation(self.db):
                # Update field values
                for field in fields:
                    value = field_values.get(field.field_uuid)
                    if value is not None:
                        field.value = str(value)
                        field.filled_at = now

                        self._log_audit_event(
                            envelope_id=envelope.id,
                            recipient_id=recipient.id,
                            event_type="field_filled",
                            description=f"Field {field.field_type} filled on page {field.page_number}",
                            ip_address=ip_address,
                            user_agent=user_agent,
                            metadata={
                                "field_uuid": field.field_uuid,
                                "field_type": field.field_type,
                                "page": field.page_number,
                            },
                        )

                # Update recipient status
                recipient.status = RecipientStatus.SIGNED.value
                recipient.signed_at = now
                recipient.signing_ip_address = ip_address
                recipient.signing_user_agent = user_agent
                recipient.signing_geo_location = geo_location
                recipient.signature_image_key = signature_image_key
                recipient.updated_at = now

                # Audit: SIGNED
                self._log_audit_event(
                    envelope_id=envelope.id,
                    recipient_id=recipient.id,
                    event_type="signed",
                    description=f"{recipient.name} ({recipient.email}) signed the document",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    metadata={
                        "signature_hash": signature_hash,
                        "document_hash": envelope.document_hash_sha256,
                        "geo_location": geo_location,
                    },
                )

                # Update envelope counters
                envelope.completed_recipients = (envelope.completed_recipients or 0) + 1
                envelope.updated_at = now

                # Check if all signers are done
                all_signers = (
                    self.db.query(ESignatureRecipient)
                    .filter(
                        ESignatureRecipient.envelope_id == envelope.id,
                        ESignatureRecipient.recipient_type.in_([
                            RecipientType.SIGNER.value,
                            RecipientType.APPROVER.value,
                        ]),
                    )
                    .all()
                )
                all_signed = all(
                    s.status == RecipientStatus.SIGNED.value for s in all_signers
                )

                result = {
                    "envelope_uuid": envelope.envelope_uuid,
                    "recipient_id": recipient.id,
                    "signer_name": recipient.name,
                    "signed_at": now.isoformat(),
                    "signature_hash": signature_hash,
                    "fields_filled": len([f for f in fields if f.value is not None]),
                    "all_signed": all_signed,
                    "next_action": None,
                }

                if all_signed:
                    # Complete the envelope within the same transaction
                    self.db.flush()
                    completion = self.complete_envelope(envelope.id)
                    result["next_action"] = "completed"
                    result["completion"] = completion
                else:
                    # Check if we need to send to the next signing order group
                    envelope.status = EnvelopeStatus.PARTIALLY_SIGNED.value

                    next_recipients = self._send_next_signing_group(envelope, all_signers)
                    if next_recipients:
                        result["next_action"] = "next_group_notified"
                        result["next_recipients"] = [
                            {"name": r.name, "email": r.email} for r in next_recipients
                        ]
                    else:
                        result["next_action"] = "awaiting_signatures"
                # atomic_operation commits here
        except Exception as e:
            logger.exception(
                "Failed to submit signature for envelope %s by %s: %s",
                envelope.envelope_uuid, recipient.email, e,
            )
            raise

        logger.info(
            "Signature submitted by %s for envelope %s (all_signed=%s)",
            recipient.email,
            envelope.envelope_uuid,
            all_signed,
        )

        return result

    # ------------------------------------------------------------------
    # 5. Complete envelope
    # ------------------------------------------------------------------

    def complete_envelope(self, envelope_id: int) -> Dict:
        """
        Finalize a fully-signed envelope.

        Verifies ALL recipients have signed within the same transaction
        before marking as COMPLETED.  This prevents race conditions where
        two concurrent signing requests both think they are the last signer.

        - Verifies all signers have status SIGNED
        - Generates a completion certificate via the crypto service.
        - Stores the certificate data as JSON in S3.
        - Updates envelope status to COMPLETED.
        - Logs COMPLETED audit event.
        - Sends completion notification to all recipients.

        Returns:
            Dict with completion details.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
        )
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
        import json

        now = datetime.now(timezone.utc)

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.id == envelope_id)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_id} not found")

        # Gather signer details for the certificate
        signers = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
            )
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )

        # Verify all signers have actually signed (guard against race condition)
        unsigned = [s for s in signers if s.status != RecipientStatus.SIGNED.value]
        if unsigned:
            unsigned_names = ", ".join(s.name for s in unsigned)
            raise ValueError(
                f"Cannot complete envelope: {len(unsigned)} signer(s) have not signed: {unsigned_names}"
            )

        signer_data = [
            {
                "name": s.name,
                "email": s.email,
                "signed_at": s.signed_at.isoformat() if s.signed_at else now.isoformat(),
                "ip_address": s.signing_ip_address or "unknown",
                "user_agent": s.signing_user_agent or "unknown",
            }
            for s in signers
        ]

        # Generate completion certificate
        certificate = self.crypto.generate_completion_certificate(
            envelope_uuid=envelope.envelope_uuid,
            title=envelope.title,
            signers=signer_data,
            document_hash=envelope.document_hash_sha256,
        )

        # Store certificate JSON to S3
        s3 = get_smart_docs_s3_service()
        cert_key = (
            f"org/{envelope.organization_id}/esign/"
            f"{envelope.envelope_uuid}/certificate.json"
        )
        cert_json = json.dumps(certificate.to_dict(), indent=2, default=str)
        cert_upload = s3.upload_file(
            file_content=cert_json.encode("utf-8"),
            storage_key=cert_key,
            content_type="application/json",
            metadata={"envelope_uuid": envelope.envelope_uuid},
        )

        if cert_upload.get("success"):
            envelope.completion_certificate_key = cert_key
        else:
            logger.warning(
                "Failed to store completion certificate for envelope %s: %s",
                envelope.envelope_uuid,
                cert_upload.get("error"),
            )

        # Update envelope status
        envelope.status = EnvelopeStatus.COMPLETED.value
        envelope.completed_at = now
        envelope.updated_at = now

        # Audit
        self._log_audit_event(
            envelope_id=envelope.id,
            recipient_id=None,
            event_type="completed",
            description=(
                f"Envelope completed -- all {len(signers)} signers have signed. "
                f"Certificate: {certificate.certificate_id}"
            ),
            metadata={
                "certificate_id": certificate.certificate_id,
                "document_hash": envelope.document_hash_sha256,
                "signer_count": len(signers),
            },
        )

        # Notify all recipients of completion
        all_recipients = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .all()
        )
        for r in all_recipients:
            try:
                self._send_completion_email(
                    recipient_name=r.name,
                    recipient_email=r.email,
                    envelope_title=envelope.title,
                    certificate_id=certificate.certificate_id,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send completion email to %s: %s",
                    r.email,
                    e,
                )

        self.db.flush()

        logger.info(
            "Envelope %s completed with certificate %s",
            envelope.envelope_uuid,
            certificate.certificate_id,
        )

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "status": EnvelopeStatus.COMPLETED.value,
            "completed_at": now.isoformat(),
            "certificate_id": certificate.certificate_id,
            "certificate_key": cert_key,
            "verification_url": certificate.verification_url,
            "signer_count": len(signers),
        }

    # ------------------------------------------------------------------
    # 6. Decline signing
    # ------------------------------------------------------------------

    def decline_signing(
        self,
        token: str,
        reason: str,
        ip_address: str,
        user_agent: str,
    ) -> Dict:
        """
        Record a recipient's refusal to sign.

        - Updates the recipient status to DECLINED.
        - Updates the envelope status to DECLINED (the entire envelope is
          abandoned when any signer declines).
        - Notifies the sender.

        Returns:
            Dict with decline details.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            EnvelopeStatus,
            RecipientStatus,
        )

        now = datetime.now(timezone.utc)

        recipient = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.signing_token == token)
            .first()
        )
        if not recipient:
            raise ValueError("Invalid signing token")

        if recipient.status == RecipientStatus.SIGNED.value:
            raise ValueError("Recipient has already signed -- cannot decline")

        if recipient.status == RecipientStatus.DECLINED.value:
            raise ValueError("Recipient has already declined")

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.id == recipient.envelope_id)
            .first()
        )
        if not envelope:
            raise ValueError("Envelope not found")

        # Update recipient
        recipient.status = RecipientStatus.DECLINED.value
        recipient.declined_at = now
        recipient.decline_reason = reason
        recipient.signing_ip_address = ip_address
        recipient.signing_user_agent = user_agent
        recipient.updated_at = now

        # Update envelope
        envelope.status = EnvelopeStatus.DECLINED.value
        envelope.updated_at = now

        # Audit
        self._log_audit_event(
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type="declined",
            description=f"{recipient.name} declined to sign: {reason}",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": reason},
        )

        # Notify the sender
        try:
            sender_name = self._get_user_display_name(envelope.created_by_user_id)
            sender_email = self._get_user_email(envelope.created_by_user_id)
            if sender_email:
                self._send_decline_notification_email(
                    sender_email=sender_email,
                    sender_name=sender_name,
                    decliner_name=recipient.name,
                    envelope_title=envelope.title,
                    reason=reason,
                )
        except Exception as e:
            logger.exception("Failed to send decline notification: %s", e)

        self.db.commit()

        logger.info(
            "Recipient %s declined envelope %s: %s",
            recipient.email,
            envelope.envelope_uuid,
            reason,
        )

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "recipient_id": recipient.id,
            "decliner_name": recipient.name,
            "reason": reason,
            "envelope_status": envelope.status,
            "declined_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 7. Void envelope
    # ------------------------------------------------------------------

    def void_envelope(
        self,
        envelope_uuid: str,
        reason: str,
        voided_by_user_id: int,
    ) -> Dict:
        """
        Void (cancel) an envelope, invalidating all pending signing tokens.

        Returns:
            Dict with void confirmation.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            EnvelopeStatus,
            RecipientStatus,
        )

        now = datetime.now(timezone.utc)

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        if envelope.status in (
            EnvelopeStatus.COMPLETED.value,
            EnvelopeStatus.VOIDED.value,
        ):
            raise ValueError(
                f"Cannot void envelope in status '{envelope.status}'"
            )

        # Update envelope
        envelope.status = EnvelopeStatus.VOIDED.value
        envelope.voided_at = now
        envelope.void_reason = reason
        envelope.updated_at = now

        # Invalidate all pending signing tokens
        recipients = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .all()
        )

        for r in recipients:
            if r.status not in (RecipientStatus.SIGNED.value, RecipientStatus.DECLINED.value):
                r.signing_token = None
                r.signing_token_expires_at = None
                r.updated_at = now

        # Audit
        voider_name = self._get_user_display_name(voided_by_user_id)
        self._log_audit_event(
            envelope_id=envelope.id,
            recipient_id=None,
            event_type="voided",
            description=f"Envelope voided by {voider_name}: {reason}",
            metadata={
                "reason": reason,
                "voided_by_user_id": voided_by_user_id,
            },
        )

        # Notify recipients
        for r in recipients:
            if r.status != RecipientStatus.SIGNED.value:
                try:
                    self._send_void_notification_email(
                        recipient_name=r.name,
                        recipient_email=r.email,
                        envelope_title=envelope.title,
                        reason=reason,
                    )
                except Exception as e:
                    logger.exception(
                        "Failed to send void notification to %s: %s",
                        r.email,
                        e,
                    )

        self.db.commit()

        logger.info("Voided envelope %s: %s", envelope_uuid, reason)

        return {
            "envelope_uuid": envelope_uuid,
            "status": EnvelopeStatus.VOIDED.value,
            "voided_at": now.isoformat(),
            "reason": reason,
            "voided_by": voider_name,
        }

    # ------------------------------------------------------------------
    # 8. Get envelope status
    # ------------------------------------------------------------------

    def get_envelope_status(self, envelope_uuid: str) -> Dict:
        """
        Return complete envelope status including all recipients, fields,
        and summary audit trail.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            ESignatureField,
            ESignatureAuditEvent,
        )

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        recipients = (
            self.db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )

        fields = (
            self.db.query(ESignatureField)
            .filter(ESignatureField.envelope_id == envelope.id)
            .order_by(ESignatureField.page_number.asc(), ESignatureField.y_position.asc())
            .all()
        )

        recent_events = (
            self.db.query(ESignatureAuditEvent)
            .filter(ESignatureAuditEvent.envelope_id == envelope.id)
            .order_by(ESignatureAuditEvent.timestamp.desc())
            .limit(20)
            .all()
        )

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "title": envelope.title,
            "description": envelope.description,
            "status": envelope.status,
            "loan_id": envelope.loan_id,
            "organization_id": envelope.organization_id,
            "document_hash": envelope.document_hash_sha256,
            "total_recipients": envelope.total_recipients,
            "completed_recipients": envelope.completed_recipients,
            "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
            "sent_at": envelope.sent_at.isoformat() if envelope.sent_at else None,
            "viewed_at": envelope.viewed_at.isoformat() if envelope.viewed_at else None,
            "completed_at": envelope.completed_at.isoformat() if envelope.completed_at else None,
            "voided_at": envelope.voided_at.isoformat() if envelope.voided_at else None,
            "expires_at": envelope.expires_at.isoformat() if envelope.expires_at else None,
            "void_reason": envelope.void_reason,
            "recipients": [
                {
                    "id": r.id,
                    "name": r.name,
                    "email": r.email,
                    "type": r.recipient_type,
                    "signing_order": r.signing_order,
                    "auth_method": r.auth_method,
                    "status": r.status,
                    "viewed_at": r.viewed_at.isoformat() if r.viewed_at else None,
                    "signed_at": r.signed_at.isoformat() if r.signed_at else None,
                    "declined_at": r.declined_at.isoformat() if r.declined_at else None,
                    "decline_reason": r.decline_reason,
                }
                for r in recipients
            ],
            "fields": [
                {
                    "field_uuid": f.field_uuid,
                    "type": f.field_type,
                    "page": f.page_number,
                    "required": f.is_required,
                    "filled": f.value is not None,
                    "filled_at": f.filled_at.isoformat() if f.filled_at else None,
                    "recipient_id": f.recipient_id,
                }
                for f in fields
            ],
            "recent_events": [
                {
                    "event_type": e.event_type,
                    "description": e.event_description,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "ip_address": e.ip_address,
                    "recipient_id": e.recipient_id,
                }
                for e in recent_events
            ],
        }

    # ------------------------------------------------------------------
    # 9. Get audit trail
    # ------------------------------------------------------------------

    def get_audit_trail(self, envelope_uuid: str) -> List[Dict]:
        """
        Return the full chronological audit trail for an envelope.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureAuditEvent,
        )

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        events = (
            self.db.query(ESignatureAuditEvent)
            .filter(ESignatureAuditEvent.envelope_id == envelope.id)
            .order_by(ESignatureAuditEvent.timestamp.asc())
            .all()
        )

        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "description": e.event_description,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "geo_location": e.geo_location,
                "recipient_id": e.recipient_id,
                "document_hash_at_event": e.document_hash_at_event,
                "metadata": e.metadata,
            }
            for e in events
        ]

    # ------------------------------------------------------------------
    # 10. Send reminder
    # ------------------------------------------------------------------

    def send_reminder(self, envelope_uuid: str) -> Dict:
        """
        Send a reminder to all pending (unsigned) recipients.

        Updates last_reminder_sent_at on the envelope.

        Returns:
            Dict with reminder details.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureRecipient,
            EnvelopeStatus,
            RecipientStatus,
            RecipientType,
        )

        now = datetime.now(timezone.utc)

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        if envelope.status not in (
            EnvelopeStatus.SENT.value,
            EnvelopeStatus.VIEWED.value,
            EnvelopeStatus.PARTIALLY_SIGNED.value,
        ):
            raise ValueError(
                f"Cannot send reminders for envelope in status '{envelope.status}'"
            )

        # Find pending signers that have already been sent a token
        pending = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
                ESignatureRecipient.status.in_([
                    RecipientStatus.SENT.value,
                    RecipientStatus.DELIVERED.value,
                    RecipientStatus.VIEWED.value,
                ]),
                ESignatureRecipient.signing_token.isnot(None),
            )
            .all()
        )

        if not pending:
            return {
                "envelope_uuid": envelope_uuid,
                "reminders_sent": 0,
                "message": "No pending recipients to remind",
            }

        sender_name = self._get_user_display_name(envelope.created_by_user_id)
        reminded = []

        for r in pending:
            signing_url = f"{self._frontend_base_url}/sign/{r.signing_token}"
            try:
                self._send_reminder_email(
                    recipient_name=r.name,
                    recipient_email=r.email,
                    envelope_title=envelope.title,
                    signing_url=signing_url,
                    sender_name=sender_name,
                )
                reminded.append({"name": r.name, "email": r.email})
            except Exception as e:
                logger.exception(
                    "Failed to send reminder to %s: %s", r.email, e
                )

            self._log_audit_event(
                envelope_id=envelope.id,
                recipient_id=r.id,
                event_type="reminder_sent",
                description=f"Reminder sent to {r.name} ({r.email})",
            )

        envelope.last_reminder_sent_at = now
        envelope.updated_at = now
        self.db.commit()

        logger.info(
            "Sent %d reminders for envelope %s",
            len(reminded),
            envelope_uuid,
        )

        return {
            "envelope_uuid": envelope_uuid,
            "reminders_sent": len(reminded),
            "recipients": reminded,
        }

    # ------------------------------------------------------------------
    # 11. Check expired envelopes
    # ------------------------------------------------------------------

    def check_expired_envelopes(self) -> int:
        """
        Find all envelopes that have passed their expires_at date and
        transition them to EXPIRED status.

        Returns:
            Count of newly expired envelopes.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            EnvelopeStatus,
        )

        now = datetime.now(timezone.utc)

        active_statuses = [
            EnvelopeStatus.DRAFT.value,
            EnvelopeStatus.SENT.value,
            EnvelopeStatus.VIEWED.value,
            EnvelopeStatus.PARTIALLY_SIGNED.value,
        ]

        expired_envelopes = (
            self.db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.status.in_(active_statuses),
                ESignatureEnvelope.expires_at.isnot(None),
                ESignatureEnvelope.expires_at < now,
            )
            .all()
        )

        count = 0
        for envelope in expired_envelopes:
            envelope.status = EnvelopeStatus.EXPIRED.value
            envelope.updated_at = now

            self._log_audit_event(
                envelope_id=envelope.id,
                recipient_id=None,
                event_type="expired",
                description=(
                    f"Envelope expired (was due {envelope.expires_at.isoformat()})"
                ),
                metadata={"expires_at": envelope.expires_at.isoformat()},
            )
            count += 1

        if count > 0:
            self.db.commit()
            logger.info("Expired %d envelopes", count)

        return count

    # ------------------------------------------------------------------
    # 12. Create from template
    # ------------------------------------------------------------------

    def create_from_template(
        self,
        template_id: int,
        loan_id: int,
        organization_id: int,
        user_id: int,
        recipients: List[Dict],
        ip_address: Optional[str] = None,
    ) -> Dict:
        """
        Create a new envelope from a saved template.

        The template provides the document storage key and pre-configured
        field positions.  The caller supplies the recipients (matched to
        template role slots by position).

        Returns:
            Dict with the created envelope details.
        """
        from database.models.esignature import ESignatureTemplate

        template = (
            self.db.query(ESignatureTemplate)
            .filter(
                ESignatureTemplate.id == template_id,
                ESignatureTemplate.organization_id == organization_id,
                ESignatureTemplate.is_active.is_(True),
            )
            .first()
        )
        if not template:
            raise ValueError(f"Template {template_id} not found or inactive")

        if not template.document_storage_key:
            raise ValueError("Template has no document configured")

        # Map template fields to the provided recipients
        fields_config = template.fields_config or []
        mapped_fields = []
        for fc in fields_config:
            mapped_fields.append({
                "type": fc.get("field_type", "signature"),
                "page": fc.get("page_number", 1),
                "x": fc.get("x", 0),
                "y": fc.get("y", 0),
                "width": fc.get("width", 200),
                "height": fc.get("height", 50),
                "required": fc.get("is_required", True),
                "recipient_index": fc.get("recipient_index", 0),
                "placeholder": fc.get("placeholder_text"),
                "default_value": fc.get("default_value"),
                "validation_regex": fc.get("validation_regex"),
                "dropdown_options": fc.get("dropdown_options"),
                "group_name": fc.get("group_name"),
            })

        request = EnvelopeCreateRequest(
            loan_id=loan_id,
            organization_id=organization_id,
            created_by_user_id=user_id,
            title=template.name,
            description=template.description,
            document_storage_key=template.document_storage_key,
            recipients=recipients,
            fields=mapped_fields,
            ip_address=ip_address,
        )

        result = self.create_envelope(request)

        # Increment template usage count
        template.usage_count = (template.usage_count or 0) + 1
        template.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        result["template_id"] = template_id
        result["template_name"] = template.name

        logger.info(
            "Created envelope %s from template %s (%s)",
            result["envelope_uuid"],
            template_id,
            template.name,
        )

        return result

    # ------------------------------------------------------------------
    # 13. Download signed document
    # ------------------------------------------------------------------

    def download_signed_document(
        self,
        envelope_uuid: str,
        user_id: int,
        ip_address: str,
    ) -> Dict:
        """
        Generate a pre-signed download URL for the signed document
        or, if not yet completed, the original document.

        Logs a DOWNLOADED audit event.

        Returns:
            Dict with the pre-signed download URL and metadata.
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            EnvelopeStatus,
        )
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

        envelope = (
            self.db.query(ESignatureEnvelope)
            .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
            .first()
        )
        if not envelope:
            raise ValueError(f"Envelope {envelope_uuid} not found")

        # Determine which document to serve
        if (
            envelope.status == EnvelopeStatus.COMPLETED.value
            and envelope.signed_document_storage_key
        ):
            storage_key = envelope.signed_document_storage_key
            doc_type = "signed"
        else:
            storage_key = envelope.document_storage_key
            doc_type = "original"

        s3 = get_smart_docs_s3_service()
        url_result = s3.get_presigned_download_url(
            storage_key=storage_key,
            file_name=f"{envelope.title}_{doc_type}.pdf",
            expires_in=600,  # 10 minutes
            inline=False,
            organization_id=envelope.organization_id,
        )

        if not url_result.get("success"):
            raise ValueError(
                f"Failed to generate download URL: {url_result.get('error', 'unknown')}"
            )

        # Audit
        self._log_audit_event(
            envelope_id=envelope.id,
            recipient_id=None,
            event_type="downloaded",
            description=f"Document downloaded by user {user_id} ({doc_type})",
            ip_address=ip_address,
            metadata={
                "user_id": user_id,
                "doc_type": doc_type,
                "storage_key": storage_key,
            },
        )
        self.db.commit()

        return {
            "envelope_uuid": envelope_uuid,
            "download_url": url_result["presigned_url"],
            "expires_in": url_result.get("expires_in", 600),
            "doc_type": doc_type,
            "title": envelope.title,
        }

    # ------------------------------------------------------------------
    # 14. Get envelopes for loan
    # ------------------------------------------------------------------

    def get_envelopes_for_loan(
        self,
        loan_id: int,
        organization_id: int,
    ) -> List[Dict]:
        """
        Return all envelopes associated with a loan, ordered by creation
        date (newest first).
        """
        from database.models.esignature import ESignatureEnvelope

        envelopes = (
            self.db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.loan_id == loan_id,
                ESignatureEnvelope.organization_id == organization_id,
            )
            .order_by(ESignatureEnvelope.created_at.desc())
            .all()
        )

        return [
            {
                "envelope_uuid": e.envelope_uuid,
                "title": e.title,
                "status": e.status,
                "total_recipients": e.total_recipients,
                "completed_recipients": e.completed_recipients,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            }
            for e in envelopes
        ]

    # ------------------------------------------------------------------
    # Private: send to next signing group
    # ------------------------------------------------------------------

    def _send_next_signing_group(
        self,
        envelope,
        all_signers,
    ) -> List:
        """
        After a signer completes, check if the next sequential signing
        group should be notified.  Returns the list of newly notified
        recipients, or an empty list if none.
        """
        from database.models.esignature import (
            RecipientStatus,
            RecipientType,
        )

        now = datetime.now(timezone.utc)

        # Get the set of signing orders that are fully completed
        signed_orders = set()
        pending_orders = set()
        for s in all_signers:
            if s.status == RecipientStatus.SIGNED.value:
                signed_orders.add(s.signing_order)
            else:
                pending_orders.add(s.signing_order)

        # Remove orders that still have pending signers
        for s in all_signers:
            if (
                s.status != RecipientStatus.SIGNED.value
                and s.signing_order in signed_orders
            ):
                signed_orders.discard(s.signing_order)

        # Find the lowest pending order that hasn't been notified yet
        # (status is still PENDING -- not yet SENT)
        from database.models.esignature import ESignatureRecipient

        next_batch_recipients = (
            self.db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
                ESignatureRecipient.status == RecipientStatus.PENDING.value,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
            )
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )

        if not next_batch_recipients:
            return []

        # Get the minimum order among pending recipients
        next_order = min(r.signing_order for r in next_batch_recipients)

        # Only send if all lower orders are fully signed
        lower_orders_complete = all(
            s.status == RecipientStatus.SIGNED.value
            for s in all_signers
            if s.signing_order < next_order
        )
        if not lower_orders_complete:
            return []

        batch = [r for r in next_batch_recipients if r.signing_order == next_order]

        sender_name = self._get_user_display_name(envelope.created_by_user_id)
        notified = []

        for r in batch:
            token, expires_at = self.crypto.generate_signing_token(
                recipient_id=r.id,
                envelope_uuid=envelope.envelope_uuid,
            )
            r.signing_token = token
            r.signing_token_expires_at = expires_at
            r.status = RecipientStatus.SENT.value
            r.updated_at = now

            signing_url = f"{self._frontend_base_url}/sign/{token}"
            try:
                self._send_signing_email(
                    recipient_name=r.name,
                    recipient_email=r.email,
                    envelope_title=envelope.title,
                    signing_url=signing_url,
                    sender_name=sender_name,
                )
            except Exception as e:
                logger.exception(
                    "Failed to send signing email to next-group recipient %s: %s",
                    r.email,
                    e,
                )

            self._log_audit_event(
                envelope_id=envelope.id,
                recipient_id=r.id,
                event_type="sent",
                description=f"Signing invitation sent to {r.name} ({r.email}) [order {r.signing_order}]",
                metadata={"signing_order": r.signing_order},
            )
            notified.append(r)

        return notified

    # ------------------------------------------------------------------
    # Private: email helpers
    # ------------------------------------------------------------------

    def _send_signing_email(
        self,
        recipient_name: str,
        recipient_email: str,
        envelope_title: str,
        signing_url: str,
        sender_name: str,
    ) -> None:
        """Compose and send a signing invitation email."""
        try:
            from email_service import EmailService

            email_svc = EmailService()
            subject = f"Please sign: {envelope_title}"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;">
            <div style="max-width:600px;margin:0 auto;padding:24px;">
            <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="background:#1e3a5f;padding:24px;text-align:center;">
                    <h1 style="margin:0;color:white;font-size:22px;">Document Ready for Signing</h1>
                </div>
                <div style="padding:24px;">
                    <p style="margin:0 0 16px;color:#374151;">Hi {recipient_name},</p>
                    <p style="margin:0 0 20px;color:#4b5563;">
                        {sender_name} has sent you <strong>{envelope_title}</strong> for your signature.
                        Please review the document and sign at your earliest convenience.
                    </p>
                    <div style="text-align:center;margin:24px 0;">
                        <a href="{signing_url}"
                           style="display:inline-block;padding:14px 32px;background:#2563eb;color:white;
                                  text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">
                            Review &amp; Sign Document
                        </a>
                    </div>
                    <p style="margin:24px 0 0;color:#6b7280;font-size:13px;">
                        This signing link is unique to you. Do not forward this email.
                    </p>
                    <p style="margin:12px 0 0;color:#6b7280;font-size:12px;border-top:1px solid #e5e7eb;padding-top:12px;">
                        <strong>ESIGN Act Notice:</strong> By proceeding to sign electronically,
                        you will be asked to consent to electronic signatures and records.
                        You have the right to receive paper copies of any document. If you do
                        not wish to sign electronically, you may request a paper alternative
                        during the signing process.
                    </p>
                </div>
                <div style="background:#f9fafb;padding:16px 24px;text-align:center;border-top:1px solid #e5e7eb;">
                    <p style="margin:0;color:#9ca3af;font-size:12px;">
                        Powered by Perennia AI &mdash; Secure E-Signature
                    </p>
                </div>
            </div>
            </div>
            </body>
            </html>
            """

            plain_text = (
                f"Hi {recipient_name},\n\n"
                f"{sender_name} has sent you \"{envelope_title}\" for your signature.\n\n"
                f"Please review and sign the document using this link:\n{signing_url}\n\n"
                f"This signing link is unique to you. Do not forward this email.\n\n"
                f"ESIGN Act Notice: By proceeding to sign electronically, you will be "
                f"asked to consent to electronic signatures and records. You have the "
                f"right to receive paper copies. If you do not wish to sign "
                f"electronically, you may request a paper alternative during the "
                f"signing process.\n"
            )

            email_svc.send_html_email(
                to_email=recipient_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )
            logger.info("Signing email sent to %s for '%s'", recipient_email, envelope_title)

        except Exception as e:
            logger.exception("Failed to send signing email to %s: %s", recipient_email, e)
            raise

    def _send_reminder_email(
        self,
        recipient_name: str,
        recipient_email: str,
        envelope_title: str,
        signing_url: str,
        sender_name: str,
    ) -> None:
        """Send a reminder email for a pending signature."""
        try:
            from email_service import EmailService

            email_svc = EmailService()
            subject = f"Reminder: Please sign {envelope_title}"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;">
            <div style="max-width:600px;margin:0 auto;padding:24px;">
            <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="background:#92400e;padding:24px;text-align:center;">
                    <h1 style="margin:0;color:white;font-size:22px;">Signature Reminder</h1>
                </div>
                <div style="padding:24px;">
                    <p style="margin:0 0 16px;color:#374151;">Hi {recipient_name},</p>
                    <p style="margin:0 0 20px;color:#4b5563;">
                        This is a friendly reminder that <strong>{envelope_title}</strong> from
                        {sender_name} is still awaiting your signature.
                    </p>
                    <div style="text-align:center;margin:24px 0;">
                        <a href="{signing_url}"
                           style="display:inline-block;padding:14px 32px;background:#d97706;color:white;
                                  text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">
                            Review &amp; Sign Now
                        </a>
                    </div>
                </div>
                <div style="background:#f9fafb;padding:16px 24px;text-align:center;border-top:1px solid #e5e7eb;">
                    <p style="margin:0;color:#9ca3af;font-size:12px;">
                        Powered by Perennia AI &mdash; Secure E-Signature
                    </p>
                </div>
            </div>
            </div>
            </body>
            </html>
            """

            plain_text = (
                f"Hi {recipient_name},\n\n"
                f"This is a reminder that \"{envelope_title}\" from {sender_name} "
                f"is still awaiting your signature.\n\n"
                f"Please sign here: {signing_url}\n"
            )

            email_svc.send_html_email(
                to_email=recipient_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )
        except Exception as e:
            logger.exception("Failed to send reminder email to %s: %s", recipient_email, e)
            raise

    def _send_completion_email(
        self,
        recipient_name: str,
        recipient_email: str,
        envelope_title: str,
        certificate_id: str,
    ) -> None:
        """Notify a recipient that the envelope is fully signed."""
        try:
            from email_service import EmailService

            email_svc = EmailService()
            subject = f"Completed: {envelope_title}"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;">
            <div style="max-width:600px;margin:0 auto;padding:24px;">
            <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="background:#065f46;padding:24px;text-align:center;">
                    <h1 style="margin:0;color:white;font-size:22px;">Signing Complete</h1>
                </div>
                <div style="padding:24px;">
                    <p style="margin:0 0 16px;color:#374151;">Hi {recipient_name},</p>
                    <p style="margin:0 0 20px;color:#4b5563;">
                        All parties have signed <strong>{envelope_title}</strong>.
                        The document is now complete and a copy will be available in your loan file.
                    </p>
                    <div style="background:#ecfdf5;border:1px solid #a7f3d0;padding:16px;border-radius:8px;margin:16px 0;">
                        <p style="margin:0;color:#065f46;font-size:14px;">
                            <strong>Certificate ID:</strong> {certificate_id}
                        </p>
                    </div>
                </div>
                <div style="background:#f9fafb;padding:16px 24px;text-align:center;border-top:1px solid #e5e7eb;">
                    <p style="margin:0;color:#9ca3af;font-size:12px;">
                        Powered by Perennia AI &mdash; Secure E-Signature
                    </p>
                </div>
            </div>
            </div>
            </body>
            </html>
            """

            plain_text = (
                f"Hi {recipient_name},\n\n"
                f"All parties have signed \"{envelope_title}\". "
                f"The document is now complete.\n\n"
                f"Certificate ID: {certificate_id}\n"
            )

            email_svc.send_html_email(
                to_email=recipient_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )
        except Exception as e:
            logger.exception(
                "Failed to send completion email to %s: %s",
                recipient_email,
                e,
            )

    def _send_decline_notification_email(
        self,
        sender_email: str,
        sender_name: str,
        decliner_name: str,
        envelope_title: str,
        reason: str,
    ) -> None:
        """Notify the sender that a recipient declined to sign."""
        try:
            from email_service import EmailService

            email_svc = EmailService()
            subject = f"Signing Declined: {envelope_title}"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;">
            <div style="max-width:600px;margin:0 auto;padding:24px;">
            <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="background:#991b1b;padding:24px;text-align:center;">
                    <h1 style="margin:0;color:white;font-size:22px;">Signing Declined</h1>
                </div>
                <div style="padding:24px;">
                    <p style="margin:0 0 16px;color:#374151;">Hi {sender_name},</p>
                    <p style="margin:0 0 20px;color:#4b5563;">
                        <strong>{decliner_name}</strong> has declined to sign
                        <strong>{envelope_title}</strong>.
                    </p>
                    <div style="background:#fef2f2;border:1px solid #fecaca;padding:16px;border-radius:8px;margin:16px 0;">
                        <p style="margin:0 0 4px;color:#991b1b;font-weight:600;">Reason:</p>
                        <p style="margin:0;color:#7f1d1d;">{reason}</p>
                    </div>
                    <p style="margin:16px 0 0;color:#6b7280;font-size:14px;">
                        You may need to address the concern and create a new envelope.
                    </p>
                </div>
                <div style="background:#f9fafb;padding:16px 24px;text-align:center;border-top:1px solid #e5e7eb;">
                    <p style="margin:0;color:#9ca3af;font-size:12px;">
                        Powered by Perennia AI &mdash; Secure E-Signature
                    </p>
                </div>
            </div>
            </div>
            </body>
            </html>
            """

            plain_text = (
                f"Hi {sender_name},\n\n"
                f"{decliner_name} has declined to sign \"{envelope_title}\".\n\n"
                f"Reason: {reason}\n\n"
                f"You may need to address the concern and create a new envelope.\n"
            )

            email_svc.send_html_email(
                to_email=sender_email,
                subject=subject,
                html_body=html_body,
                plain_text_body=plain_text,
            )
        except Exception as e:
            logger.exception(
                "Failed to send decline notification to %s: %s",
                sender_email,
                e,
            )

    def _send_void_notification_email(
        self,
        recipient_name: str,
        recipient_email: str,
        envelope_title: str,
        reason: str,
    ) -> None:
        """Notify a recipient that the envelope has been voided."""
        try:
            from email_service import EmailService

            email_svc = EmailService()
            subject = f"Voided: {envelope_title}"

            plain_text = (
                f"Hi {recipient_name},\n\n"
                f"The document \"{envelope_title}\" has been voided and is no longer "
                f"available for signing.\n\n"
                f"Reason: {reason}\n\n"
                f"If you have questions, please contact the sender.\n"
            )

            email_svc.send_html_email(
                to_email=recipient_email,
                subject=subject,
                html_body=f"<p>{plain_text.replace(chr(10), '<br>')}</p>",
                plain_text_body=plain_text,
            )
        except Exception as e:
            logger.exception(
                "Failed to send void notification to %s: %s",
                recipient_email,
                e,
            )

    # ------------------------------------------------------------------
    # Private: audit logging
    # ------------------------------------------------------------------

    def _log_audit_event(
        self,
        envelope_id: int,
        recipient_id: Optional[int],
        event_type: str,
        description: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Create an immutable audit trail entry in esignature_audit_events.
        """
        from database.models.esignature import ESignatureAuditEvent, ESignatureEnvelope

        now = datetime.now(timezone.utc)

        # Capture the current document hash for tamper detection
        document_hash = None
        try:
            envelope = (
                self.db.query(ESignatureEnvelope)
                .filter(ESignatureEnvelope.id == envelope_id)
                .first()
            )
            if envelope:
                document_hash = envelope.document_hash_sha256
        except Exception:
            pass  # Non-critical -- do not fail audit logging

        event = ESignatureAuditEvent()
        event.envelope_id = envelope_id
        event.recipient_id = recipient_id
        event.event_type = event_type
        event.event_description = description
        event.ip_address = ip_address
        event.user_agent = user_agent
        event.metadata = metadata
        event.document_hash_at_event = document_hash
        event.timestamp = now

        self.db.add(event)
        # Do not commit here -- caller is responsible for commit timing

    # ------------------------------------------------------------------
    # Private: user lookups
    # ------------------------------------------------------------------

    def _get_user_display_name(self, user_id: Optional[int]) -> str:
        """Look up a user's display name. Returns 'Unknown' on failure."""
        if not user_id:
            return "Unknown"
        try:
            result = self.db.execute(
                text(
                    "SELECT first_name, last_name FROM users WHERE id = :uid"
                ),
                {"uid": user_id},
            ).first()
            if result:
                first = result[0] or ""
                last = result[1] or ""
                name = f"{first} {last}".strip()
                return name if name else "Unknown"
        except Exception as e:
            logger.warning("Failed to look up user %s: %s", user_id, e)
        return "Unknown"

    def _get_user_email(self, user_id: Optional[int]) -> Optional[str]:
        """Look up a user's email address."""
        if not user_id:
            return None
        try:
            result = self.db.execute(
                text("SELECT email FROM users WHERE id = :uid"),
                {"uid": user_id},
            ).first()
            if result:
                return result[0]
        except Exception as e:
            logger.warning("Failed to look up email for user %s: %s", user_id, e)
        return None


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

def get_esignature_envelope_service(db: Session) -> ESignatureEnvelopeService:
    """
    Create an ESignatureEnvelopeService bound to the given database session.

    Unlike stateless singletons, this service is session-scoped because it
    needs a live SQLAlchemy session for transactional operations.
    """
    return ESignatureEnvelopeService(db)
