"""
Smart Docs E-Signature API Routes

REST API for the built-in e-signature system.  Uses the database models from
database/models/esignature.py (ESignatureEnvelope, ESignatureRecipient,
ESignatureField, ESignatureAuditEvent, ESignatureTemplate) and the
cryptographic primitives from esignature_crypto_service.

Endpoint groups:
- Envelope management (authenticated)
- Signing sessions (token-based, no login required)
- Templates (authenticated)
- Stats / dashboard (authenticated)
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from database.models.esignature import (
    AuditEventType,
    EnvelopeStatus,
    ESignatureAuditEvent,
    ESignatureEnvelope,
    ESignatureField,
    ESignatureRecipient,
    ESignatureTemplate,
    RecipientAuthMethod,
    RecipientStatus,
    RecipientType,
    SignatureFieldType,
)
from services.smart_docs.esignature_crypto_service import get_esignature_crypto_service
from services.smart_docs.esign_consent_service import ESignConsentService
from services.smart_docs.esign_kba_service import KBAService
from validation.smart_docs_validators import validate_regex_safe

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class EnvelopeRecipientInput(BaseModel):
    """A single recipient to add to an envelope."""
    name: str
    email: EmailStr
    type: str = RecipientType.SIGNER.value
    signing_order: int = 1
    auth_method: str = RecipientAuthMethod.EMAIL_LINK.value
    phone: Optional[str] = None
    access_code: Optional[str] = None


class EnvelopeFieldInput(BaseModel):
    """A single field placement on the document."""
    type: str = SignatureFieldType.SIGNATURE.value
    page: int = 1
    x: float
    y: float
    w: float = 200.0
    h: float = 50.0
    recipient_index: int = 0
    required: bool = True
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    group_name: Optional[str] = None
    dropdown_options: Optional[List[str]] = None
    validation_regex: Optional[str] = None


class CreateEnvelopeRequest(BaseModel):
    """Request body for creating a new signing envelope."""
    loan_id: int
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    document_storage_key: str = Field(..., max_length=1024, description="S3 key of the document to sign")
    original_filename: Optional[str] = None
    page_count: Optional[int] = None
    recipients: List[EnvelopeRecipientInput]
    fields: Optional[List[EnvelopeFieldInput]] = None
    expires_in_days: int = Field(default=30, ge=1, le=365)
    reminder_frequency_hours: int = Field(default=48, ge=0)


class SendEnvelopeRequest(BaseModel):
    """Optional body when sending an envelope (currently unused, reserved)."""
    custom_email_subject: Optional[str] = None
    custom_email_message: Optional[str] = None


class VoidEnvelopeRequest(BaseModel):
    """Request body for voiding an envelope."""
    reason: str = Field(..., min_length=1, max_length=2000)


class VerifyAccessCodeRequest(BaseModel):
    """Request body for access code verification."""
    code: str = Field(..., min_length=4, max_length=10)


class FieldValueSubmission(BaseModel):
    """A single field value in a signature submission."""
    field_id: int
    value: str


class SubmitSignatureRequest(BaseModel):
    """Request body for submitting a completed signing session."""
    fields: List[FieldValueSubmission]
    signature_image: Optional[str] = Field(
        default=None,
        description="Base64-encoded signature image (PNG or SVG)",
    )


class DeclineSigningRequest(BaseModel):
    """Request body for declining to sign."""
    reason: Optional[str] = Field(default=None, max_length=2000)


class CreateTemplateRequest(BaseModel):
    """Request body for creating an e-signature template."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    document_storage_key: str = Field(..., max_length=1024)
    fields_config: Optional[List[Dict]] = None
    default_recipients: Optional[List[Dict]] = None
    category: Optional[str] = Field(default=None, max_length=128)


class CreateEnvelopeFromTemplateRequest(BaseModel):
    """Request body for creating an envelope from a template."""
    loan_id: int
    recipients: List[EnvelopeRecipientInput]
    title: Optional[str] = None
    description: Optional[str] = None
    expires_in_days: int = Field(default=30, ge=1, le=365)


class RecordConsentRequest(BaseModel):
    """Request body for recording ESIGN Act consent."""
    consented: bool = Field(..., description="True if signer agrees to e-sign")


class WithdrawConsentRequest(BaseModel):
    """Request body for withdrawing previously-given consent."""
    reason: Optional[str] = Field(default=None, max_length=2000)


class KBAVerifyRequest(BaseModel):
    """Request body for verifying KBA answers."""
    session_id: str = Field(..., description="KBA session UUID")
    answers: List[int] = Field(..., description="List of selected answer indices")


# =============================================================================
# Router
# =============================================================================

router = APIRouter(
    prefix="/api/v1/esign",
    tags=["E-Signature"],
)


# =============================================================================
# Helpers
# =============================================================================

def _get_client_ip(request: Request) -> str:
    """Extract client IP from the request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _verify_envelope_tenant(
    db: Session,
    envelope: ESignatureEnvelope,
    current_user: Any,
) -> None:
    """Raise 404 if the user's org does not own the envelope."""
    user_org = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"
    if user_org and not is_platform_admin:
        if envelope.organization_id is not None and envelope.organization_id != user_org:
            raise HTTPException(status_code=404, detail="Not found")


def _verify_loan_tenant(db: Session, loan_id: int, current_user: Any) -> None:
    """Verify the user's org owns the loan. Raises 404 if not."""
    from sqlalchemy import text as sa_text

    user_org = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"
    if user_org and not is_platform_admin:
        row = db.execute(
            sa_text("SELECT organization_id FROM loans WHERE id = :id"),
            {"id": loan_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Loan not found")
        if row[0] is not None and row[0] != user_org:
            raise HTTPException(status_code=404, detail="Not found")


def _get_envelope_or_404(
    db: Session,
    envelope_uuid: str,
    current_user: Any,
) -> ESignatureEnvelope:
    """Fetch an envelope by UUID with tenant check, or raise 404."""
    envelope = (
        db.query(ESignatureEnvelope)
        .filter(ESignatureEnvelope.envelope_uuid == envelope_uuid)
        .first()
    )
    if not envelope:
        raise HTTPException(status_code=404, detail="Envelope not found")
    _verify_envelope_tenant(db, envelope, current_user)
    return envelope


def _record_audit_event(
    db: Session,
    envelope_id: int,
    event_type: str,
    description: str,
    recipient_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict] = None,
    document_hash: Optional[str] = None,
) -> ESignatureAuditEvent:
    """Insert an immutable audit event."""
    event = ESignatureAuditEvent(
        envelope_id=envelope_id,
        recipient_id=recipient_id,
        event_type=event_type,
        event_description=description,
        ip_address=ip_address,
        user_agent=user_agent,
        extra_metadata=metadata,
        document_hash_at_event=document_hash,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def _send_signing_invitations_background(
    signers: List[Dict],
    envelope_title: str,
):
    """Background task: send signing invitation emails to recipients."""
    import html as html_mod

    try:
        from email_service import EmailService

        email_svc = EmailService()
        for signer in signers:
            try:
                signing_url = f"https://app.perenniaai.com/sign/{signer['token']}"
                safe_name = html_mod.escape(signer["name"])
                safe_title = html_mod.escape(envelope_title)
                safe_expires = html_mod.escape(signer.get("expires_at", "N/A"))
                safe_url = html_mod.escape(signing_url)
                subject = f"Signature Required: {envelope_title}"
                email_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>Hello {safe_name},</h2>
                    <p>You have been requested to review and sign a document: <strong>{safe_title}</strong></p>
                    <p style="margin: 20px 0;">
                        <a href="{safe_url}"
                           style="background-color: #2563eb; color: white; padding: 12px 24px;
                                  text-decoration: none; border-radius: 6px; display: inline-block;">
                            Review &amp; Sign Document
                        </a>
                    </p>
                    <p><strong>This link expires on {safe_expires}.</strong></p>
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        If you did not expect this request, you can safely ignore it.
                    </p>
                </body>
                </html>
                """
                email_svc.send_email(
                    to_email=signer["email"],
                    subject=subject,
                    html_content=email_html,
                )
                logger.info("Sent signing invitation to %s", signer["email"])
            except Exception as e:
                logger.error("Failed to send invitation to %s: %s", signer["email"], e)
    except ImportError:
        logger.error("EmailService not available for signing invitations")
    except Exception as e:
        logger.error("Error in signing invitation background task: %s", e)


# =============================================================================
# ENVELOPE MANAGEMENT (Authenticated)
# =============================================================================

@router.post("/envelopes")
async def create_envelope(
    body: CreateEnvelopeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Create a new signing envelope with recipients and optional field placements.

    The document referenced by ``document_storage_key`` must already be uploaded
    to S3.  Recipients are created in the specified signing order.  Fields are
    optionally placed on the document pages.
    """
    # Tenant check on the loan
    _verify_loan_tenant(db, body.loan_id, current_user)

    if not body.recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    crypto = get_esignature_crypto_service()
    envelope_uuid = crypto.generate_envelope_uuid()

    try:
        # Create envelope
        envelope = ESignatureEnvelope(
            organization_id=getattr(current_user, "organization_id", None),
            loan_id=body.loan_id,
            created_by_user_id=current_user.id,
            envelope_uuid=envelope_uuid,
            title=body.title,
            description=body.description,
            original_filename=body.original_filename,
            page_count=body.page_count,
            status=EnvelopeStatus.DRAFT.value,
            document_storage_key=body.document_storage_key,
            total_recipients=len([r for r in body.recipients if r.type in (RecipientType.SIGNER.value, "signer")]),
            completed_recipients=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
            ip_address_created=_get_client_ip(request),
            reminder_frequency_hours=body.reminder_frequency_hours,
        )
        db.add(envelope)
        db.flush()  # get envelope.id

        # Create recipients
        recipients_created = []
        for idx, r in enumerate(body.recipients):
            access_code_hash = None
            if r.access_code:
                access_code_hash = crypto.hash_access_code(r.access_code)

            recipient = ESignatureRecipient(
                envelope_id=envelope.id,
                recipient_type=r.type,
                signing_order=r.signing_order,
                name=r.name,
                email=r.email,
                phone=r.phone,
                access_code=access_code_hash,
                auth_method=r.auth_method,
                status=RecipientStatus.PENDING.value,
            )
            db.add(recipient)
            db.flush()
            recipients_created.append({
                "id": recipient.id,
                "name": recipient.name,
                "email": recipient.email,
                "type": recipient.recipient_type,
                "signing_order": recipient.signing_order,
            })

        # Create fields
        fields_created = []
        if body.fields:
            for f in body.fields:
                # Map recipient_index to actual recipient id
                recipient_id = None
                if 0 <= f.recipient_index < len(recipients_created):
                    recipient_id = recipients_created[f.recipient_index]["id"]

                # Validate regex pattern if provided (ReDoS prevention)
                field_regex = f.validation_regex
                if field_regex is not None:
                    if not validate_regex_safe(field_regex):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Unsafe or invalid validation_regex for field "
                                f"at index {body.fields.index(f)}: pattern rejected "
                                f"(nested quantifiers, excessive length, or invalid syntax)"
                            ),
                        )

                field = ESignatureField(
                    envelope_id=envelope.id,
                    recipient_id=recipient_id,
                    field_type=f.type,
                    field_uuid=str(uuid.uuid4()),
                    page_number=f.page,
                    x_position=f.x,
                    y_position=f.y,
                    width=f.w,
                    height=f.h,
                    is_required=f.required,
                    placeholder_text=f.placeholder,
                    default_value=f.default_value,
                    group_name=f.group_name,
                    dropdown_options=f.dropdown_options,
                    validation_regex=field_regex,
                )
                db.add(field)
                db.flush()
                fields_created.append({
                    "id": field.id,
                    "field_uuid": field.field_uuid,
                    "type": field.field_type,
                    "page": field.page_number,
                })

        # Audit event
        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Envelope created with {len(recipients_created)} recipients and {len(fields_created)} fields",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        db.commit()

        logger.info(
            "Created envelope %s for loan %s by user %s",
            envelope_uuid,
            body.loan_id,
            current_user.id,
        )

        return {
            "envelope_uuid": envelope_uuid,
            "status": envelope.status,
            "title": envelope.title,
            "recipients": recipients_created,
            "fields": fields_created,
            "expires_at": envelope.expires_at.isoformat() if envelope.expires_at else None,
            "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error creating envelope: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create envelope")
    except Exception as e:
        db.rollback()
        logger.exception("Error creating envelope: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create envelope")


@router.post("/envelopes/{envelope_uuid}/send")
async def send_envelope(
    envelope_uuid: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Send an envelope for signing.

    Generates unique signing tokens for each recipient in the current signing
    order and dispatches invitation emails in the background.
    """
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    # Only creator or admin can send
    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if envelope.created_by_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Only the envelope creator or an admin can send")

    if envelope.status not in (EnvelopeStatus.DRAFT.value, "draft"):
        raise HTTPException(status_code=400, detail=f"Cannot send envelope in '{envelope.status}' status")

    crypto = get_esignature_crypto_service()

    try:
        # Get recipients for the first signing order
        recipients = (
            db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .order_by(ESignatureRecipient.signing_order)
            .all()
        )

        if not recipients:
            raise HTTPException(status_code=400, detail="Envelope has no recipients")

        first_order = recipients[0].signing_order
        signers_to_notify = []

        for recip in recipients:
            # Generate token for first-order recipients; others get tokens
            # when the previous order completes.
            if recip.signing_order == first_order:
                token, expires_at = crypto.generate_signing_token(
                    recipient_id=recip.id,
                    envelope_uuid=envelope_uuid,
                )
                recip.signing_token = token
                recip.signing_token_expires_at = expires_at
                recip.status = RecipientStatus.SENT.value

                signers_to_notify.append({
                    "name": recip.name,
                    "email": recip.email,
                    "token": token,
                    "expires_at": expires_at.isoformat(),
                })

        # Update envelope status
        envelope.status = EnvelopeStatus.SENT.value
        envelope.sent_at = datetime.now(timezone.utc)

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.SENT.value,
            description=f"Envelope sent to {len(signers_to_notify)} recipients",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        db.commit()

        # Send emails in background
        if signers_to_notify:
            background_tasks.add_task(
                _send_signing_invitations_background,
                signers_to_notify,
                envelope.title,
            )

        logger.info("Sent envelope %s to %d recipients", envelope_uuid, len(signers_to_notify))

        return {
            "envelope_uuid": envelope_uuid,
            "status": EnvelopeStatus.SENT.value,
            "recipients_notified": len(signers_to_notify),
            "sent_at": envelope.sent_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error sending envelope %s: %s", envelope_uuid, e)
        raise HTTPException(status_code=500, detail="Failed to send envelope")


@router.get("/envelopes/{envelope_uuid}")
async def get_envelope_status(
    envelope_uuid: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Get full envelope status including recipients, fields, and progress."""
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    recipients = (
        db.query(ESignatureRecipient)
        .filter(ESignatureRecipient.envelope_id == envelope.id)
        .order_by(ESignatureRecipient.signing_order)
        .all()
    )

    fields = (
        db.query(ESignatureField)
        .filter(ESignatureField.envelope_id == envelope.id)
        .order_by(ESignatureField.page_number, ESignatureField.y_position)
        .all()
    )

    total_signers = len([r for r in recipients if r.recipient_type in (RecipientType.SIGNER.value, "signer")])
    signed_count = len([r for r in recipients if r.status in (RecipientStatus.SIGNED.value, "signed")])

    return {
        "envelope_uuid": envelope.envelope_uuid,
        "title": envelope.title,
        "description": envelope.description,
        "status": envelope.status,
        "loan_id": envelope.loan_id,
        "created_by_user_id": envelope.created_by_user_id,
        "document_storage_key": envelope.document_storage_key,
        "original_filename": envelope.original_filename,
        "page_count": envelope.page_count,
        "document_hash_sha256": envelope.document_hash_sha256,
        "total_recipients": envelope.total_recipients,
        "completed_recipients": envelope.completed_recipients,
        "progress": {
            "total_signers": total_signers,
            "signed": signed_count,
            "percentage": round((signed_count / total_signers) * 100) if total_signers > 0 else 0,
        },
        "sent_at": envelope.sent_at.isoformat() if envelope.sent_at else None,
        "viewed_at": envelope.viewed_at.isoformat() if envelope.viewed_at else None,
        "completed_at": envelope.completed_at.isoformat() if envelope.completed_at else None,
        "voided_at": envelope.voided_at.isoformat() if envelope.voided_at else None,
        "void_reason": envelope.void_reason,
        "expires_at": envelope.expires_at.isoformat() if envelope.expires_at else None,
        "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
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
                "id": f.id,
                "field_uuid": f.field_uuid,
                "field_type": f.field_type,
                "page_number": f.page_number,
                "x": f.x_position,
                "y": f.y_position,
                "w": f.width,
                "h": f.height,
                "recipient_id": f.recipient_id,
                "is_required": f.is_required,
                "value": f.value,
                "filled_at": f.filled_at.isoformat() if f.filled_at else None,
            }
            for f in fields
        ],
    }


@router.get("/envelopes/{envelope_uuid}/audit-trail")
async def get_envelope_audit_trail(
    envelope_uuid: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Get the chronological audit trail for an envelope."""
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    events = (
        db.query(ESignatureAuditEvent)
        .filter(ESignatureAuditEvent.envelope_id == envelope.id)
        .order_by(ESignatureAuditEvent.timestamp.asc())
        .all()
    )

    return {
        "envelope_uuid": envelope_uuid,
        "title": envelope.title,
        "events": [
            {
                "id": ev.id,
                "event_type": ev.event_type,
                "description": ev.event_description,
                "recipient_id": ev.recipient_id,
                "ip_address": ev.ip_address,
                "user_agent": ev.user_agent,
                "metadata": ev.extra_metadata,
                "document_hash": ev.document_hash_at_event,
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
            }
            for ev in events
        ],
        "count": len(events),
    }


@router.post("/envelopes/{envelope_uuid}/void")
async def void_envelope(
    envelope_uuid: str,
    body: VoidEnvelopeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Void an active envelope. Only the creator or an admin can void."""
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if envelope.created_by_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Only the envelope creator or an admin can void")

    terminal = (
        EnvelopeStatus.COMPLETED.value,
        EnvelopeStatus.VOIDED.value,
        EnvelopeStatus.EXPIRED.value,
    )
    if envelope.status in terminal:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot void envelope in '{envelope.status}' status",
        )

    try:
        envelope.status = EnvelopeStatus.VOIDED.value
        envelope.voided_at = datetime.now(timezone.utc)
        envelope.void_reason = body.reason

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.VOIDED.value,
            description=f"Envelope voided: {body.reason}",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        db.commit()

        logger.info("Voided envelope %s by user %s", envelope_uuid, current_user.id)

        return {
            "envelope_uuid": envelope_uuid,
            "status": EnvelopeStatus.VOIDED.value,
            "voided_at": envelope.voided_at.isoformat(),
            "reason": body.reason,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error voiding envelope %s: %s", envelope_uuid, e)
        raise HTTPException(status_code=500, detail="Failed to void envelope")


@router.post("/envelopes/{envelope_uuid}/remind")
async def send_reminder(
    envelope_uuid: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Send a reminder to all pending recipients on a sent envelope."""
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    sendable = (EnvelopeStatus.SENT.value, EnvelopeStatus.VIEWED.value, EnvelopeStatus.PARTIALLY_SIGNED.value)
    if envelope.status not in sendable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send reminders for envelope in '{envelope.status}' status",
        )

    crypto = get_esignature_crypto_service()

    try:
        # Find pending recipients who have tokens
        pending = (
            db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
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

        signers_to_remind = []
        for recip in pending:
            # Re-generate token if expired
            token = recip.signing_token
            if recip.signing_token_expires_at and recip.signing_token_expires_at < datetime.now(timezone.utc):
                token, expires_at = crypto.generate_signing_token(
                    recipient_id=recip.id,
                    envelope_uuid=envelope_uuid,
                )
                recip.signing_token = token
                recip.signing_token_expires_at = expires_at

            signers_to_remind.append({
                "name": recip.name,
                "email": recip.email,
                "token": token,
                "expires_at": recip.signing_token_expires_at.isoformat() if recip.signing_token_expires_at else None,
            })

        envelope.last_reminder_sent_at = datetime.now(timezone.utc)

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.REMINDER_SENT.value,
            description=f"Reminder sent to {len(signers_to_remind)} recipients",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        db.commit()

        background_tasks.add_task(
            _send_signing_invitations_background,
            signers_to_remind,
            envelope.title,
        )

        return {
            "envelope_uuid": envelope_uuid,
            "reminders_sent": len(signers_to_remind),
            "reminded_at": envelope.last_reminder_sent_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error sending reminders for %s: %s", envelope_uuid, e)
        raise HTTPException(status_code=500, detail="Failed to send reminders")


@router.get("/envelopes/{envelope_uuid}/download")
async def download_signed_document(
    request: Request,
    envelope_uuid: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Get a pre-signed S3 URL for the completed signed document.

    Returns the signed document if the envelope is completed, or the original
    document otherwise.
    """
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    storage_key = envelope.signed_document_storage_key or envelope.document_storage_key
    if not storage_key:
        raise HTTPException(status_code=404, detail="No document available for download")

    try:
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

        s3_svc = get_smart_docs_s3_service()
        if not s3_svc.is_available:
            raise HTTPException(status_code=503, detail="Document storage not available")

        presigned = s3_svc.generate_presigned_download_url(storage_key)
        if not presigned:
            raise HTTPException(status_code=500, detail="Failed to generate download URL")

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.DOWNLOADED.value,
            description="Signed document downloaded",
            metadata={"by_user_id": current_user.id},
        )

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id,
                organization_id=getattr(current_user, "organization_id", None),
                resource_type="signed_document", export_format="pdf",
                ip_address=_get_client_ip(request),
                details={"envelope_uuid": envelope_uuid, "is_signed": envelope.signed_document_storage_key is not None},
            )
        except Exception:
            pass

        db.commit()

        return {
            "envelope_uuid": envelope_uuid,
            "download_url": presigned.get("url") or presigned.get("presigned_url"),
            "filename": envelope.original_filename or f"{envelope.title}.pdf",
            "is_signed": envelope.signed_document_storage_key is not None,
            "expires_in_seconds": presigned.get("expires_in", 300),
        }

    except HTTPException:
        raise
    except ImportError:
        logger.error("S3 storage service not available")
        raise HTTPException(status_code=503, detail="Document storage not available")
    except Exception as e:
        logger.exception("Error generating download URL for %s: %s", envelope_uuid, e)
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.get("/envelopes/{envelope_uuid}/certificate")
async def download_completion_certificate(
    envelope_uuid: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Get a pre-signed S3 URL for the completion certificate PDF.

    Only available for completed envelopes.
    """
    envelope = _get_envelope_or_404(db, envelope_uuid, current_user)

    if envelope.status != EnvelopeStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Completion certificate is only available for completed envelopes",
        )

    if not envelope.completion_certificate_key:
        raise HTTPException(status_code=404, detail="Completion certificate not yet generated")

    try:
        from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

        s3_svc = get_smart_docs_s3_service()
        if not s3_svc.is_available:
            raise HTTPException(status_code=503, detail="Document storage not available")

        presigned = s3_svc.generate_presigned_download_url(envelope.completion_certificate_key)
        if not presigned:
            raise HTTPException(status_code=500, detail="Failed to generate certificate URL")

        return {
            "envelope_uuid": envelope_uuid,
            "download_url": presigned.get("url") or presigned.get("presigned_url"),
            "filename": f"certificate_{envelope_uuid}.pdf",
            "expires_in_seconds": presigned.get("expires_in", 300),
        }

    except HTTPException:
        raise
    except ImportError:
        logger.error("S3 storage service not available")
        raise HTTPException(status_code=503, detail="Document storage not available")
    except Exception as e:
        logger.exception("Error generating certificate URL for %s: %s", envelope_uuid, e)
        raise HTTPException(status_code=500, detail="Failed to generate certificate URL")


@router.get("/loan/{loan_id}/envelopes")
async def get_loan_envelopes(
    loan_id: int,
    status: Optional[str] = Query(default=None, description="Filter by envelope status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Get all envelopes associated with a loan."""
    _verify_loan_tenant(db, loan_id, current_user)

    query = (
        db.query(ESignatureEnvelope)
        .filter(ESignatureEnvelope.loan_id == loan_id)
    )
    if status:
        query = query.filter(ESignatureEnvelope.status == status)

    total = query.count()
    envelopes = (
        query
        .order_by(ESignatureEnvelope.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "loan_id": loan_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "envelopes": [
            {
                "envelope_uuid": env.envelope_uuid,
                "title": env.title,
                "status": env.status,
                "total_recipients": env.total_recipients,
                "completed_recipients": env.completed_recipients,
                "sent_at": env.sent_at.isoformat() if env.sent_at else None,
                "completed_at": env.completed_at.isoformat() if env.completed_at else None,
                "expires_at": env.expires_at.isoformat() if env.expires_at else None,
                "created_at": env.created_at.isoformat() if env.created_at else None,
            }
            for env in envelopes
        ],
    }


# =============================================================================
# SIGNING SESSION ENDPOINTS (Token-based auth, no login required)
# =============================================================================

def _get_recipient_by_token(db: Session, token: str) -> ESignatureRecipient:
    """Look up a recipient by their signing token. Raises 401 on failure."""
    recipient = (
        db.query(ESignatureRecipient)
        .filter(ESignatureRecipient.signing_token == token)
        .first()
    )
    if not recipient:
        raise HTTPException(status_code=401, detail="Invalid signing token")

    if recipient.signing_token_expires_at and recipient.signing_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Signing token has expired")

    return recipient


def _get_envelope_for_signing(db: Session, envelope_id: int) -> ESignatureEnvelope:
    """Get the envelope and validate it is still signable."""
    envelope = db.query(ESignatureEnvelope).filter(ESignatureEnvelope.id == envelope_id).first()
    if not envelope:
        raise HTTPException(status_code=404, detail="Envelope not found")

    non_signable = (EnvelopeStatus.VOIDED.value, EnvelopeStatus.EXPIRED.value, EnvelopeStatus.COMPLETED.value)
    if envelope.status in non_signable:
        raise HTTPException(status_code=410, detail=f"Document is no longer available ({envelope.status})")

    if envelope.expires_at and envelope.expires_at < datetime.now(timezone.utc):
        envelope.status = EnvelopeStatus.EXPIRED.value
        db.commit()
        raise HTTPException(status_code=410, detail="Signing session has expired")

    return envelope


@router.get("/sign/{token}")
async def start_signing_session(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Start a signing session using a signing token.

    PUBLIC ENDPOINT -- no authentication required.  The token itself serves as
    the credential.  Records the signer's IP and user agent for audit purposes.
    Returns the document URL and the fields the signer must fill.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        # Check if access code verification is required
        requires_access_code = (
            recipient.auth_method in (RecipientAuthMethod.ACCESS_CODE.value, "access_code")
            and recipient.access_code is not None
        )

        # Check ESIGN consent and KBA requirements
        consent_svc = ESignConsentService(db)
        has_consent = consent_svc.verify_consent(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        )
        requires_consent = not has_consent

        kba_svc = KBAService(db)
        requires_kba = kba_svc.check_kba_required_for_recipient(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        )

        # Mark as viewed if first time
        if not recipient.viewed_at:
            recipient.viewed_at = datetime.now(timezone.utc)
            if recipient.status in (RecipientStatus.SENT.value, RecipientStatus.DELIVERED.value):
                recipient.status = RecipientStatus.VIEWED.value

            if not envelope.viewed_at:
                envelope.viewed_at = datetime.now(timezone.utc)
                if envelope.status == EnvelopeStatus.SENT.value:
                    envelope.status = EnvelopeStatus.VIEWED.value

            _record_audit_event(
                db,
                envelope_id=envelope.id,
                recipient_id=recipient.id,
                event_type=AuditEventType.VIEWED.value,
                description=f"Document viewed by {recipient.name} ({recipient.email})",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Get fields assigned to this recipient
        fields = (
            db.query(ESignatureField)
            .filter(
                ESignatureField.envelope_id == envelope.id,
                ESignatureField.recipient_id == recipient.id,
            )
            .order_by(ESignatureField.page_number, ESignatureField.y_position)
            .all()
        )

        db.commit()

        # Build presigned document URL
        document_url = None
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

            s3_svc = get_smart_docs_s3_service()
            if s3_svc.is_available and envelope.document_storage_key:
                presigned = s3_svc.generate_presigned_download_url(envelope.document_storage_key)
                if presigned:
                    document_url = presigned.get("url") or presigned.get("presigned_url")
        except Exception as e:
            logger.warning("Could not generate presigned document URL: %s", e)

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "title": envelope.title,
            "description": envelope.description,
            "page_count": envelope.page_count,
            "document_url": document_url,
            "document_storage_key": envelope.document_storage_key,
            "requires_access_code": requires_access_code,
            "requires_consent": requires_consent,
            "requires_kba": requires_kba,
            "signer": {
                "name": recipient.name,
                "email": recipient.email,
                "status": recipient.status,
            },
            "fields": [
                {
                    "id": f.id,
                    "field_uuid": f.field_uuid,
                    "field_type": f.field_type,
                    "page_number": f.page_number,
                    "x": f.x_position,
                    "y": f.y_position,
                    "w": f.width,
                    "h": f.height,
                    "is_required": f.is_required,
                    "placeholder": f.placeholder_text,
                    "default_value": f.default_value,
                    "dropdown_options": f.dropdown_options,
                    "group_name": f.group_name,
                    "value": f.value,
                }
                for f in fields
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error starting signing session: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start signing session")


@router.post("/sign/{token}/verify-access-code")
async def verify_access_code(
    token: str,
    body: VerifyAccessCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Verify access code for signing sessions that require it.

    PUBLIC ENDPOINT -- no login required.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if not recipient.access_code:
        return {"verified": True, "message": "No access code required"}

    crypto = get_esignature_crypto_service()
    is_valid = crypto.verify_access_code(body.code, recipient.access_code)

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    if is_valid:
        _record_audit_event(
            db,
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type=AuditEventType.AUTH_PASSED.value,
            description=f"Access code verified for {recipient.email}",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        return {"verified": True, "message": "Access code verified"}
    else:
        _record_audit_event(
            db,
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type=AuditEventType.AUTH_FAILED.value,
            description=f"Access code verification failed for {recipient.email}",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Invalid access code")


@router.post("/sign/{token}/submit")
async def submit_signature(
    token: str,
    body: SubmitSignatureRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit a completed signing session.

    PUBLIC ENDPOINT -- no login required.  Validates that all required fields
    have values, records the signature, and advances envelope state.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if recipient.status in (RecipientStatus.SIGNED.value, RecipientStatus.DECLINED.value):
        raise HTTPException(status_code=400, detail=f"Recipient has already {recipient.status}")

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    crypto = get_esignature_crypto_service()

    try:
        # --- ESIGN Act: verify consent before allowing signature ---
        consent_svc = ESignConsentService(db)
        if not consent_svc.verify_consent(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "ESIGN Act consent is required before signing. "
                    "Please review the consent disclosure and provide consent."
                ),
            )

        # --- KBA: verify identity if required for this recipient ---
        kba_svc = KBAService(db)
        if kba_svc.check_kba_required_for_recipient(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        ):
            from database.models.esignature import ESignKBASession

            kba_session = (
                db.query(ESignKBASession)
                .filter(
                    ESignKBASession.recipient_id == recipient.id,
                    ESignKBASession.envelope_id == envelope.id,
                    ESignKBASession.passed.is_(True),
                )
                .first()
            )
            if not kba_session:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Identity verification (KBA) is required before signing. "
                        "Please complete the identity verification step."
                    ),
                )

        # Get all fields assigned to this recipient
        recipient_fields = (
            db.query(ESignatureField)
            .filter(
                ESignatureField.envelope_id == envelope.id,
                ESignatureField.recipient_id == recipient.id,
            )
            .all()
        )
        field_map = {f.id: f for f in recipient_fields}

        # Apply submitted values
        submitted_field_ids = set()
        for fv in body.fields:
            field = field_map.get(fv.field_id)
            if not field:
                raise HTTPException(
                    status_code=400,
                    detail=f"Field {fv.field_id} not found or not assigned to this signer",
                )
            field.value = fv.value
            field.filled_at = datetime.now(timezone.utc)
            submitted_field_ids.add(fv.field_id)

            _record_audit_event(
                db,
                envelope_id=envelope.id,
                recipient_id=recipient.id,
                event_type=AuditEventType.FIELD_FILLED.value,
                description=f"Field {field.field_uuid} ({field.field_type}) filled",
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Validate all required fields have values
        for field in recipient_fields:
            if field.is_required and not field.value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Required field '{field.field_uuid}' ({field.field_type}) is missing a value",
                )

        # Store signature image if provided
        if body.signature_image:
            try:
                from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
                from middleware.upload_limits import MAX_SIGNATURE_IMAGE_SIZE

                s3_svc = get_smart_docs_s3_service()
                if s3_svc.is_available:
                    import base64

                    sig_bytes = base64.b64decode(body.signature_image)

                    # Enforce size limit on decoded signature image
                    if len(sig_bytes) > MAX_SIGNATURE_IMAGE_SIZE:
                        max_mb = MAX_SIGNATURE_IMAGE_SIZE / (1024 * 1024)
                        raise HTTPException(
                            status_code=413,
                            detail=f"Signature image too large (max {max_mb:.0f} MB)",
                        )

                    sig_key = f"esign/signatures/{envelope.envelope_uuid}/{recipient.id}/signature.png"
                    s3_svc.upload_file(sig_bytes, sig_key, content_type="image/png")
                    recipient.signature_image_key = sig_key
            except HTTPException:
                raise
            except Exception as e:
                logger.warning("Failed to store signature image: %s", e)

        # Generate signature hash
        document_hash = envelope.document_hash_sha256 or ""
        now = datetime.now(timezone.utc)
        signature_hash = crypto.generate_signature_hash(
            document_hash=document_hash,
            signer_email=recipient.email,
            signed_at=now,
            ip_address=ip_address,
        )

        # Update recipient status
        recipient.status = RecipientStatus.SIGNED.value
        recipient.signed_at = now
        recipient.signing_ip_address = ip_address
        recipient.signing_user_agent = user_agent

        # Update envelope counters
        envelope.completed_recipients = (envelope.completed_recipients or 0) + 1

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type=AuditEventType.SIGNED.value,
            description=f"Document signed by {recipient.name} ({recipient.email})",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"signature_hash": signature_hash},
            document_hash=document_hash,
        )

        # Check if all signers have completed
        all_signers = (
            db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == envelope.id,
                ESignatureRecipient.recipient_type.in_([
                    RecipientType.SIGNER.value,
                    RecipientType.APPROVER.value,
                ]),
            )
            .all()
        )
        all_complete = all(
            s.status in (RecipientStatus.SIGNED.value, "signed")
            for s in all_signers
        )

        envelope_completed = False

        if all_complete:
            envelope.status = EnvelopeStatus.COMPLETED.value
            envelope.completed_at = now
            envelope_completed = True

            # Generate completion certificate data
            signer_dicts = [
                {
                    "name": s.name,
                    "email": s.email,
                    "signed_at": s.signed_at.isoformat() if s.signed_at else now.isoformat(),
                    "ip_address": s.signing_ip_address or "unknown",
                    "user_agent": s.signing_user_agent or "unknown",
                }
                for s in all_signers
            ]
            cert = crypto.generate_completion_certificate(
                envelope_uuid=envelope.envelope_uuid,
                title=envelope.title,
                signers=signer_dicts,
                document_hash=document_hash,
            )

            _record_audit_event(
                db,
                envelope_id=envelope.id,
                event_type=AuditEventType.COMPLETED.value,
                description=f"All {len(all_signers)} signers completed. Certificate: {cert.certificate_id}",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"certificate_id": cert.certificate_id},
                document_hash=document_hash,
            )

            logger.info("Envelope %s completed with %d signers", envelope.envelope_uuid, len(all_signers))
        else:
            # Move to partially_signed
            if envelope.status != EnvelopeStatus.PARTIALLY_SIGNED.value:
                envelope.status = EnvelopeStatus.PARTIALLY_SIGNED.value

            # Notify next signing order recipients if applicable
            current_order = recipient.signing_order
            next_recipients = (
                db.query(ESignatureRecipient)
                .filter(
                    ESignatureRecipient.envelope_id == envelope.id,
                    ESignatureRecipient.signing_order > current_order,
                    ESignatureRecipient.status == RecipientStatus.PENDING.value,
                )
                .order_by(ESignatureRecipient.signing_order)
                .all()
            )

            if next_recipients:
                # Get all signed recipients of the current order
                current_order_done = all(
                    s.status in (RecipientStatus.SIGNED.value, "signed")
                    for s in all_signers
                    if s.signing_order == current_order
                )
                if current_order_done:
                    next_order = next_recipients[0].signing_order
                    signers_to_notify = []
                    for nr in next_recipients:
                        if nr.signing_order != next_order:
                            break
                        new_token, expires_at = crypto.generate_signing_token(
                            recipient_id=nr.id,
                            envelope_uuid=envelope.envelope_uuid,
                        )
                        nr.signing_token = new_token
                        nr.signing_token_expires_at = expires_at
                        nr.status = RecipientStatus.SENT.value
                        signers_to_notify.append({
                            "name": nr.name,
                            "email": nr.email,
                            "token": new_token,
                            "expires_at": expires_at.isoformat(),
                        })

                    if signers_to_notify:
                        background_tasks.add_task(
                            _send_signing_invitations_background,
                            signers_to_notify,
                            envelope.title,
                        )

        db.commit()

        return {
            "status": "signed",
            "signer": recipient.name,
            "signed_at": recipient.signed_at.isoformat(),
            "signature_hash": signature_hash,
            "envelope_status": envelope.status,
            "envelope_completed": envelope_completed,
            "completed_recipients": envelope.completed_recipients,
            "total_recipients": envelope.total_recipients,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error submitting signature for token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to submit signature")


@router.post("/sign/{token}/decline")
async def decline_signing(
    token: str,
    body: DeclineSigningRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Decline to sign a document.

    PUBLIC ENDPOINT -- no login required.  Records the decline reason and
    transitions the envelope to declined status.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if recipient.status in (RecipientStatus.SIGNED.value, RecipientStatus.DECLINED.value):
        raise HTTPException(status_code=400, detail=f"Recipient has already {recipient.status}")

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        now = datetime.now(timezone.utc)
        recipient.status = RecipientStatus.DECLINED.value
        recipient.declined_at = now
        recipient.decline_reason = body.reason
        recipient.signing_ip_address = ip_address
        recipient.signing_user_agent = user_agent

        envelope.status = EnvelopeStatus.DECLINED.value

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type=AuditEventType.DECLINED.value,
            description=f"Signing declined by {recipient.name} ({recipient.email}): {body.reason or 'No reason given'}",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()

        logger.info(
            "Signing declined for envelope %s by %s",
            envelope.envelope_uuid,
            recipient.email,
        )

        return {
            "status": "declined",
            "signer": recipient.name,
            "declined_at": now.isoformat(),
            "reason": body.reason,
            "envelope_status": EnvelopeStatus.DECLINED.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error declining signature: %s", e)
        raise HTTPException(status_code=500, detail="Failed to decline signing")


# =============================================================================
# ESIGN CONSENT ENDPOINTS (Token-based auth, no login required)
# =============================================================================

@router.get("/sign/{token}/consent-disclosure")
async def get_consent_disclosure(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get the ESIGN Act consent disclosure text.

    PUBLIC ENDPOINT -- no login required.  Must be shown to the signer
    before they can proceed with electronic signing.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    consent_svc = ESignConsentService(db)
    disclosure = consent_svc.get_consent_disclosure_text(
        org_id=envelope.organization_id,
    )

    # Also check if consent has already been given
    has_consent = consent_svc.verify_consent(
        recipient_id=recipient.id,
        envelope_id=envelope.id,
    )

    return {
        "envelope_uuid": envelope.envelope_uuid,
        "recipient_name": recipient.name,
        "disclosure_text": disclosure["text"],
        "disclosure_version": disclosure["version"],
        "consent_already_given": has_consent,
    }


@router.post("/sign/{token}/consent")
async def record_consent(
    token: str,
    body: RecordConsentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Record the signer's ESIGN Act consent decision.

    PUBLIC ENDPOINT -- no login required.  If ``consented`` is False,
    the system triggers a paper alternative workflow and creates a task
    for staff to print and mail physical copies.

    Must be called before ``/sign/{token}/submit``.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if recipient.status in (RecipientStatus.SIGNED.value, RecipientStatus.DECLINED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Recipient has already {recipient.status}",
        )

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        consent_svc = ESignConsentService(db)
        result = consent_svc.record_consent(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
            org_id=envelope.organization_id,
            consented=body.consented,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "consent_given": result["consent_given"],
            "consent_text_version": result["consent_text_version"],
            "consented_at": result["consented_at"],
            "paper_delivery_requested": result["paper_task_id"] is not None,
            "paper_task_id": result["paper_task_id"],
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error recording consent: %s", e)
        raise HTTPException(status_code=500, detail="Failed to record consent")


@router.post("/sign/{token}/request-paper")
async def request_paper_alternative(
    token: str,
    body: WithdrawConsentRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Request paper alternative (withdraw consent or decline e-signature).

    PUBLIC ENDPOINT -- no login required.  If the signer previously gave
    consent, this withdraws it.  Either way, a paper delivery task is
    created for staff.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        consent_svc = ESignConsentService(db)

        # Check if consent exists to withdraw
        has_consent = consent_svc.verify_consent(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
        )

        if has_consent:
            result = consent_svc.withdraw_consent(
                recipient_id=recipient.id,
                envelope_id=envelope.id,
                reason=body.reason or "Paper alternative requested",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.commit()
            return {
                "envelope_uuid": envelope.envelope_uuid,
                "consent_withdrawn": True,
                "withdrawn_at": result["withdrawn_at"],
                "paper_task_id": result["paper_task_id"],
                "message": "Consent withdrawn. Paper copies will be mailed to you.",
            }
        else:
            # No consent to withdraw -- just create the paper task
            paper_task_id = consent_svc.create_paper_delivery_task(
                recipient_id=recipient.id,
                envelope_id=envelope.id,
                org_id=envelope.organization_id,
            )
            db.commit()
            return {
                "envelope_uuid": envelope.envelope_uuid,
                "consent_withdrawn": False,
                "paper_task_id": paper_task_id,
                "message": "Paper copies will be mailed to you.",
            }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error requesting paper alternative: %s", e)
        raise HTTPException(status_code=500, detail="Failed to request paper alternative")


# =============================================================================
# KBA ENDPOINTS (Token-based auth, no login required)
# =============================================================================

@router.post("/sign/{token}/kba/start")
async def start_kba_session(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Start a Knowledge-Based Authentication session.

    PUBLIC ENDPOINT -- no login required.  Generates identity verification
    questions for the signer based on their profile data.  Returns the
    questions (without correct answers) and a session UUID for answer
    submission.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if recipient.status in (RecipientStatus.SIGNED.value, RecipientStatus.DECLINED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Recipient has already {recipient.status}",
        )

    if recipient.status == RecipientStatus.AUTH_FAILED.value:
        raise HTTPException(
            status_code=403,
            detail="Identity verification has been locked due to too many failed attempts",
        )

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        kba_svc = KBAService(db)
        result = kba_svc.create_kba_session(
            recipient_id=recipient.id,
            envelope_id=envelope.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "session_id": result["session_uuid"],
            "questions": result["questions"],
            "attempts_remaining": result["attempts_remaining"],
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error starting KBA session: %s", e)
        raise HTTPException(status_code=500, detail="Failed to start KBA session")


@router.post("/sign/{token}/kba/verify")
async def verify_kba_answers(
    token: str,
    body: KBAVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Verify KBA answers for identity authentication.

    PUBLIC ENDPOINT -- no login required.  Checks the signer's answers
    against the stored correct answers.  Requires 75% correct to pass.
    After 3 failed attempts the session is locked and the recipient is
    marked AUTH_FAILED.
    """
    recipient = _get_recipient_by_token(db, token)
    envelope = _get_envelope_for_signing(db, recipient.envelope_id)

    if recipient.status == RecipientStatus.AUTH_FAILED.value:
        raise HTTPException(
            status_code=403,
            detail="Identity verification has been locked due to too many failed attempts",
        )

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    try:
        kba_svc = KBAService(db)
        result = kba_svc.verify_kba_answers(
            session_id=body.session_id,
            answers=body.answers,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()

        return {
            "envelope_uuid": envelope.envelope_uuid,
            "passed": result.passed,
            "attempts_remaining": result.attempts_remaining,
            "locked": result.locked,
            "score": result.score,
            "correct_count": result.correct_count,
            "total_questions": result.total_questions,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error verifying KBA answers: %s", e)
        raise HTTPException(status_code=500, detail="Failed to verify KBA answers")


# =============================================================================
# TEMPLATE ENDPOINTS (Authenticated)
# =============================================================================

@router.post("/templates")
async def create_template(
    body: CreateTemplateRequest,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """Create a reusable e-signature template with pre-configured field placements."""
    try:
        template = ESignatureTemplate(
            organization_id=getattr(current_user, "organization_id", None),
            created_by_user_id=current_user.id,
            name=body.name,
            description=body.description,
            document_storage_key=body.document_storage_key,
            fields_config=body.fields_config,
            default_recipients=body.default_recipients,
            category=body.category,
            is_active=True,
            usage_count=0,
        )
        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info("Created e-sign template '%s' (id=%s)", body.name, template.id)

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "document_storage_key": template.document_storage_key,
            "fields_config": template.fields_config,
            "default_recipients": template.default_recipients,
            "created_at": template.created_at.isoformat() if template.created_at else None,
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Database error creating template: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create template")


@router.get("/templates")
async def list_templates(
    category: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """List e-signature templates filtered by the user's organization."""
    user_org = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"

    query = db.query(ESignatureTemplate)

    if user_org and not is_platform_admin:
        query = query.filter(ESignatureTemplate.organization_id == user_org)
    if category:
        query = query.filter(ESignatureTemplate.category == category)
    if active_only:
        query = query.filter(ESignatureTemplate.is_active.is_(True))

    total = query.count()
    templates = (
        query
        .order_by(ESignatureTemplate.usage_count.desc(), ESignatureTemplate.name)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "document_storage_key": t.document_storage_key,
                "fields_config": t.fields_config,
                "default_recipients": t.default_recipients,
                "is_active": t.is_active,
                "usage_count": t.usage_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in templates
        ],
    }


@router.post("/templates/{template_id}/create-envelope")
async def create_envelope_from_template(
    template_id: int,
    body: CreateEnvelopeFromTemplateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Create a new envelope from an existing template.

    Copies the template's document and field configuration into a new envelope,
    then attaches the provided recipients.
    """
    user_org = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"

    template = db.query(ESignatureTemplate).filter(ESignatureTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Tenant check
    if user_org and not is_platform_admin:
        if template.organization_id is not None and template.organization_id != user_org:
            raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Template is inactive")

    _verify_loan_tenant(db, body.loan_id, current_user)

    if not body.recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    crypto = get_esignature_crypto_service()
    envelope_uuid = crypto.generate_envelope_uuid()

    try:
        # Create envelope from template
        envelope = ESignatureEnvelope(
            organization_id=user_org,
            loan_id=body.loan_id,
            created_by_user_id=current_user.id,
            envelope_uuid=envelope_uuid,
            title=body.title or template.name,
            description=body.description or template.description,
            status=EnvelopeStatus.DRAFT.value,
            document_storage_key=template.document_storage_key,
            total_recipients=len([r for r in body.recipients if r.type in (RecipientType.SIGNER.value, "signer")]),
            completed_recipients=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
            ip_address_created=_get_client_ip(request),
        )
        db.add(envelope)
        db.flush()

        # Create recipients
        recipients_created = []
        for r in body.recipients:
            access_code_hash = None
            if r.access_code:
                access_code_hash = crypto.hash_access_code(r.access_code)

            recipient = ESignatureRecipient(
                envelope_id=envelope.id,
                recipient_type=r.type,
                signing_order=r.signing_order,
                name=r.name,
                email=r.email,
                phone=r.phone,
                access_code=access_code_hash,
                auth_method=r.auth_method,
                status=RecipientStatus.PENDING.value,
            )
            db.add(recipient)
            db.flush()
            recipients_created.append({
                "id": recipient.id,
                "name": recipient.name,
                "email": recipient.email,
                "type": recipient.recipient_type,
                "signing_order": recipient.signing_order,
            })

        # Copy fields from template config
        fields_created = []
        if template.fields_config:
            for fc in template.fields_config:
                # Map template recipient_role to actual recipient
                recipient_id = None
                role_label = fc.get("recipient_role", "")
                if template.default_recipients:
                    for idx, dr in enumerate(template.default_recipients):
                        if dr.get("role_label") == role_label and idx < len(recipients_created):
                            recipient_id = recipients_created[idx]["id"]
                            break

                # Fallback: assign to first recipient
                if recipient_id is None and recipients_created:
                    recipient_id = recipients_created[0]["id"]

                field = ESignatureField(
                    envelope_id=envelope.id,
                    recipient_id=recipient_id,
                    field_type=fc.get("field_type", SignatureFieldType.SIGNATURE.value),
                    field_uuid=str(uuid.uuid4()),
                    page_number=fc.get("page_number", 1),
                    x_position=fc.get("x", 100),
                    y_position=fc.get("y", 500),
                    width=fc.get("width", 200),
                    height=fc.get("height", 50),
                    is_required=fc.get("is_required", True),
                    placeholder_text=fc.get("placeholder_text"),
                    group_name=fc.get("group_name"),
                    dropdown_options=fc.get("dropdown_options"),
                )
                db.add(field)
                db.flush()
                fields_created.append({
                    "id": field.id,
                    "field_uuid": field.field_uuid,
                    "type": field.field_type,
                    "page": field.page_number,
                })

        # Increment template usage
        template.usage_count = (template.usage_count or 0) + 1

        _record_audit_event(
            db,
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Envelope created from template '{template.name}' (id={template.id})",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        db.commit()

        logger.info(
            "Created envelope %s from template %s for loan %s",
            envelope_uuid,
            template_id,
            body.loan_id,
        )

        return {
            "envelope_uuid": envelope_uuid,
            "status": envelope.status,
            "title": envelope.title,
            "template_id": template.id,
            "template_name": template.name,
            "recipients": recipients_created,
            "fields": fields_created,
            "expires_at": envelope.expires_at.isoformat() if envelope.expires_at else None,
            "created_at": envelope.created_at.isoformat() if envelope.created_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Error creating envelope from template %s: %s", template_id, e)
        raise HTTPException(status_code=500, detail="Failed to create envelope from template")


# =============================================================================
# STATS / DASHBOARD (Authenticated)
# =============================================================================

@router.get("/stats")
async def get_esign_stats(
    days: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    """
    Get e-signature statistics for the user's organization.

    Returns aggregate metrics: total envelopes, completion rates, average
    completion time, and status breakdown.
    """
    user_org = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        base_query = db.query(ESignatureEnvelope).filter(
            ESignatureEnvelope.created_at >= cutoff,
        )
        if user_org and not is_platform_admin:
            base_query = base_query.filter(ESignatureEnvelope.organization_id == user_org)

        total = base_query.count()

        # Status breakdown
        status_counts = (
            base_query
            .with_entities(ESignatureEnvelope.status, func.count(ESignatureEnvelope.id))
            .group_by(ESignatureEnvelope.status)
            .all()
        )
        by_status = {status: count for status, count in status_counts}

        completed = by_status.get(EnvelopeStatus.COMPLETED.value, 0)
        sent = by_status.get(EnvelopeStatus.SENT.value, 0)
        declined = by_status.get(EnvelopeStatus.DECLINED.value, 0)
        voided = by_status.get(EnvelopeStatus.VOIDED.value, 0)
        draft = by_status.get(EnvelopeStatus.DRAFT.value, 0)

        # Average completion time (sent_at -> completed_at)
        avg_completion_hours = None
        completed_envelopes = (
            base_query
            .filter(
                ESignatureEnvelope.status == EnvelopeStatus.COMPLETED.value,
                ESignatureEnvelope.sent_at.isnot(None),
                ESignatureEnvelope.completed_at.isnot(None),
            )
            .all()
        )

        if completed_envelopes:
            total_hours = sum(
                (e.completed_at - e.sent_at).total_seconds() / 3600
                for e in completed_envelopes
                if e.completed_at and e.sent_at
            )
            avg_completion_hours = round(total_hours / len(completed_envelopes), 1)

        # Completion rate (of non-draft envelopes)
        non_draft = total - draft
        completion_rate = round((completed / non_draft) * 100, 1) if non_draft > 0 else 0

        return {
            "period_days": days,
            "total_envelopes": total,
            "by_status": by_status,
            "completed": completed,
            "pending": sent + by_status.get(EnvelopeStatus.VIEWED.value, 0) + by_status.get(EnvelopeStatus.PARTIALLY_SIGNED.value, 0),
            "declined": declined,
            "voided": voided,
            "draft": draft,
            "completion_rate_pct": completion_rate,
            "avg_completion_hours": avg_completion_hours,
        }

    except SQLAlchemyError as e:
        logger.exception("Error fetching e-sign stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


# =============================================================================
# INDIVIDUAL SIGNER AND FIELD MANAGEMENT (Enterprise Features)
# =============================================================================

@router.post("/envelopes/{envelope_uuid}/signers")
async def add_signer(
    envelope_uuid: str,
    signer_data: EnvelopeRecipientInput,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a single signer to an existing envelope.
    
    Enterprise feature for dynamic signer management.
    """
    try:
        # Get envelope
        envelope = (
            db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.envelope_uuid == envelope_uuid,
                ESignatureEnvelope.organization_id == current_user.organization_id,
            )
            .first()
        )
        
        if not envelope:
            raise HTTPException(status_code=404, detail="Envelope not found")
            
        # Check if envelope is in draft status
        if envelope.status != EnvelopeStatus.DRAFT.value:
            raise HTTPException(
                status_code=400, 
                detail="Cannot add signers to non-draft envelope"
            )
        
        # Create new recipient
        access_code_hash = None
        if signer_data.access_code:
            crypto = get_esignature_crypto_service()
            access_code_hash = crypto.hash_access_code(signer_data.access_code)

        recipient = ESignatureRecipient(
            envelope_id=envelope.id,
            name=signer_data.name,
            email=signer_data.email,
            type=signer_data.type,
            status=RecipientStatus.PENDING.value,
            signing_order=signer_data.signing_order,
            auth_method=signer_data.auth_method,
            phone=signer_data.phone,
            access_code_hash=access_code_hash,
        )
        db.add(recipient)
        
        # Update envelope recipient count if it's a signer
        if signer_data.type == RecipientType.SIGNER.value:
            envelope.total_recipients += 1
            
        # Create audit event
        audit = ESignatureAuditEvent(
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Signer added: {signer_data.name} ({signer_data.email})",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
        )
        db.add(audit)
        
        db.commit()
        db.refresh(recipient)
        
        return {
            "id": recipient.id,
            "name": recipient.name,
            "email": recipient.email,
            "type": recipient.type,
            "status": recipient.status,
            "signing_order": recipient.signing_order,
            "auth_method": recipient.auth_method,
        }
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Error adding signer: %s", e)
        raise HTTPException(status_code=500, detail="Failed to add signer")


@router.post("/envelopes/{envelope_uuid}/fields")
async def add_field(
    envelope_uuid: str,
    field_data: EnvelopeFieldInput,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a single field to an existing envelope.
    
    Enterprise feature for dynamic field management.
    """
    try:
        # Get envelope and recipients
        envelope = (
            db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.envelope_uuid == envelope_uuid,
                ESignatureEnvelope.organization_id == current_user.organization_id,
            )
            .first()
        )
        
        if not envelope:
            raise HTTPException(status_code=404, detail="Envelope not found")
            
        # Check if envelope is in draft status
        if envelope.status != EnvelopeStatus.DRAFT.value:
            raise HTTPException(
                status_code=400, 
                detail="Cannot add fields to non-draft envelope"
            )
        
        # Get recipients to validate recipient_index
        recipients = (
            db.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == envelope.id)
            .order_by(ESignatureRecipient.signing_order)
            .all()
        )
        
        if field_data.recipient_index >= len(recipients):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid recipient_index {field_data.recipient_index}"
            )
            
        assigned_recipient = recipients[field_data.recipient_index]
        
        # Validate regex if provided
        if field_data.validation_regex:
            validate_regex_safe(field_data.validation_regex)

        # Create new field
        field = ESignatureField(
            envelope_id=envelope.id,
            recipient_id=assigned_recipient.id,
            type=field_data.type,
            page=field_data.page,
            x=field_data.x,
            y=field_data.y,
            w=field_data.w,
            h=field_data.h,
            required=field_data.required,
            placeholder=field_data.placeholder,
            default_value=field_data.default_value,
            group_name=field_data.group_name,
            dropdown_options=field_data.dropdown_options,
            validation_regex=field_data.validation_regex,
        )
        db.add(field)
        
        # Create audit event
        audit = ESignatureAuditEvent(
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Field added: {field_data.type} on page {field_data.page}",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
        )
        db.add(audit)
        
        db.commit()
        db.refresh(field)
        
        return {
            "id": field.id,
            "type": field.type,
            "page": field.page,
            "x": field.x,
            "y": field.y,
            "w": field.w,
            "h": field.h,
            "required": field.required,
            "recipient_id": field.recipient_id,
            "placeholder": field.placeholder,
        }
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Error adding field: %s", e)
        raise HTTPException(status_code=500, detail="Failed to add field")


@router.delete("/envelopes/{envelope_uuid}/signers/{signer_id}")
async def remove_signer(
    envelope_uuid: str,
    signer_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a signer from an envelope.
    
    Enterprise feature for dynamic signer management.
    """
    try:
        # Get envelope
        envelope = (
            db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.envelope_uuid == envelope_uuid,
                ESignatureEnvelope.organization_id == current_user.organization_id,
            )
            .first()
        )
        
        if not envelope:
            raise HTTPException(status_code=404, detail="Envelope not found")
            
        # Check if envelope is in draft status
        if envelope.status != EnvelopeStatus.DRAFT.value:
            raise HTTPException(
                status_code=400, 
                detail="Cannot remove signers from non-draft envelope"
            )
        
        # Get signer
        signer = (
            db.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.id == signer_id,
                ESignatureRecipient.envelope_id == envelope.id,
            )
            .first()
        )
        
        if not signer:
            raise HTTPException(status_code=404, detail="Signer not found")
            
        # Remove associated fields first
        db.query(ESignatureField).filter(
            ESignatureField.recipient_id == signer_id
        ).delete()
        
        # Update envelope recipient count if it's a signer
        if signer.type == RecipientType.SIGNER.value:
            envelope.total_recipients = max(0, envelope.total_recipients - 1)
            
        # Create audit event before deletion
        audit = ESignatureAuditEvent(
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Signer removed: {signer.name} ({signer.email})",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
        )
        db.add(audit)
        
        # Remove signer
        db.delete(signer)
        db.commit()
        
        return {"message": "Signer removed successfully"}
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Error removing signer: %s", e)
        raise HTTPException(status_code=500, detail="Failed to remove signer")


@router.delete("/envelopes/{envelope_uuid}/fields/{field_id}")
async def remove_field(
    envelope_uuid: str,
    field_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a field from an envelope.
    
    Enterprise feature for dynamic field management.
    """
    try:
        # Get envelope
        envelope = (
            db.query(ESignatureEnvelope)
            .filter(
                ESignatureEnvelope.envelope_uuid == envelope_uuid,
                ESignatureEnvelope.organization_id == current_user.organization_id,
            )
            .first()
        )
        
        if not envelope:
            raise HTTPException(status_code=404, detail="Envelope not found")
            
        # Check if envelope is in draft status
        if envelope.status != EnvelopeStatus.DRAFT.value:
            raise HTTPException(
                status_code=400, 
                detail="Cannot remove fields from non-draft envelope"
            )
        
        # Get field
        field = (
            db.query(ESignatureField)
            .filter(
                ESignatureField.id == field_id,
                ESignatureField.envelope_id == envelope.id,
            )
            .first()
        )
        
        if not field:
            raise HTTPException(status_code=404, detail="Field not found")
            
        # Create audit event before deletion
        audit = ESignatureAuditEvent(
            envelope_id=envelope.id,
            event_type=AuditEventType.CREATED.value,
            description=f"Field removed: {field.type} on page {field.page}",
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
        )
        db.add(audit)
        
        # Remove field
        db.delete(field)
        db.commit()
        
        return {"message": "Field removed successfully"}
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Error removing field: %s", e)
        raise HTTPException(status_code=500, detail="Failed to remove field")
