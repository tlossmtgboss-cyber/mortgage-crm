"""
E-Signature API Routes

API endpoints for the self-hosted e-signature system.
Provides endpoints for:
- Envelope management (CRUD, send, void)
- Field placement (create, update, delete, bulk save)
- Signing session (token auth, signature adoption, field completion)
- Document generation (signed PDF, audit trail)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from typing import Optional, List, Callable, Any, Dict
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone, timedelta
import logging
import io

from services.esign_service import EsignService, EsignError
from services.esign_pdf_service import get_esign_pdf_service
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/esign", tags=["E-Signature"])


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db: Callable = None
_get_current_user: Callable = None
_User: Any = None
_esign_models: Dict[str, Any] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, user_model: Any, esign_models: Dict[str, Any] = None):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_db, _get_current_user, _User, _esign_models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _User = user_model
    _esign_models = esign_models
    logger.info("E-Sign routes dependencies set")


def get_db():
    """Get database session dependency."""
    if _get_db is None:
        raise RuntimeError("E-Sign routes not initialized. Call set_dependencies first.")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
def get_esign_service(db: Session = Depends(get_db)) -> EsignService:
    """Get EsignService instance."""
    return EsignService(db, _esign_models)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

def send_signer_invitations(signers: List[Dict], envelope_name: str = None):
    """
    Background task to send email invitations to signers.

    Args:
        signers: List of signer dicts with 'name', 'email', 'token', 'expires_at'
        envelope_name: Optional envelope name for the email subject
    """
    try:
        from email_service import EmailService
        email_service = EmailService()

        for signer in signers:
            try:
                # Build signing URL
                signing_url = f"/sign/{signer['token']}"

                subject = f"Signature Required: {envelope_name}" if envelope_name else "Your Signature is Required"

                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2>Hello {signer['name']},</h2>
                    <p>You have been requested to sign a document.</p>
                    <p>Please click the button below to review and sign the document:</p>
                    <p style="margin: 20px 0;">
                        <a href="{signing_url}"
                           style="background-color: #2563eb; color: white; padding: 12px 24px;
                                  text-decoration: none; border-radius: 6px; display: inline-block;">
                            Review & Sign Document
                        </a>
                    </p>
                    <p><strong>This link will expire on {signer['expires_at'][:10]}.</strong></p>
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        If you have any questions, please contact the sender directly.
                    </p>
                </body>
                </html>
                """

                email_service.send_email(
                    to_email=signer['email'],
                    subject=subject,
                    html_content=html_content
                )
                logger.info(f"Sent signing invitation to {signer['email']}")

            except Exception as e:
                logger.error(f"Failed to send invitation to {signer['email']}: {e}")
                # Continue with other signers even if one fails

    except ImportError:
        logger.error("EmailService not available for sending signer invitations")
    except Exception as e:
        logger.error(f"Error in send_signer_invitations background task: {e}")


def generate_signed_documents(envelope_id: int):
    """
    Background task to generate the final signed PDF with all signatures applied.

    Args:
        envelope_id: The envelope ID to generate documents for
    """
    try:
        # Get database session
        if _get_db is None:
            logger.error("Database not available for document generation")
            return

        # Create a new session for the background task
        db_gen = _get_db()
        db = next(db_gen)

        try:
            from services.esign_pdf_service import get_esign_pdf_service
            from services.perennia_s3_service import get_s3_service

            s3_service = get_s3_service()
            pdf_service = get_esign_pdf_service(s3_service=s3_service)

            # Generate the signed PDF (fetches from S3, flattens, uploads back)
            result = pdf_service.generate_signed_pdf(envelope_id, db=db)

            if result.get("success"):
                logger.info(f"Successfully generated signed PDF for envelope {envelope_id}: "
                           f"signed={result['documents']['signed']['file_size']} bytes, "
                           f"complete={result['documents']['complete']['file_size']} bytes")
            else:
                logger.error(f"Failed to generate signed PDF for envelope {envelope_id}: {result.get('error')}")

        except ImportError as e:
            logger.error(f"Service not available for document generation: {e}")
        except Exception as e:
            logger.error(f"Error generating signed PDF for envelope {envelope_id}: {e}")
        finally:
            # Close the session
            try:
                next(db_gen, None)
            except StopIteration:
                pass

    except Exception as e:
        logger.error(f"Error in generate_signed_documents background task: {e}")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateEnvelopePayload(BaseModel):
    name: str
    pdf_storage_key: str
    pdf_file_name: str
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    document_id: Optional[int] = None
    description: Optional[str] = None
    pdf_file_size: Optional[int] = None
    pdf_page_count: int = 1
    pdf_page_dimensions: Optional[List[Dict]] = None
    email_subject: Optional[str] = None
    email_message: Optional[str] = None
    expires_in_days: int = 30


class AddSignerPayload(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = None
    signer_order: int = 1


class AddFieldPayload(BaseModel):
    field_type: str  # signature, initial, date_signed, text, checkbox, dropdown
    page_number: int = 1
    x_position_points: float
    y_position_points: float
    width_points: float = 144.0
    height_points: float = 36.0
    signer_id: Optional[int] = None
    is_required: bool = True
    placeholder_text: Optional[str] = None
    tab_order: int = 0


class UpdateFieldPayload(BaseModel):
    signer_id: Optional[int] = None
    page_number: Optional[int] = None
    x_position_points: Optional[float] = None
    y_position_points: Optional[float] = None
    width_points: Optional[float] = None
    height_points: Optional[float] = None
    is_required: Optional[bool] = None
    placeholder_text: Optional[str] = None
    tab_order: Optional[int] = None


class BulkSaveFieldsPayload(BaseModel):
    fields: List[AddFieldPayload]


class VoidEnvelopePayload(BaseModel):
    reason: Optional[str] = None


class AdoptSignaturePayload(BaseModel):
    signature_text: str
    signature_font: str = "Helvetica-Oblique"


class SubmitFieldValuePayload(BaseModel):
    value: Any


# =============================================================================
# ENVELOPE MANAGEMENT (Staff Auth)
# =============================================================================

@router.post("/envelopes")
async def create_envelope(
    payload: CreateEnvelopePayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Create a new envelope from a PDF document."""
    try:
        result = service.create_envelope(
            name=payload.name,
            pdf_storage_key=payload.pdf_storage_key,
            pdf_file_name=payload.pdf_file_name,
            created_by_user_id=current_user.id,
            loan_id=payload.loan_id,
            lead_id=payload.lead_id,
            document_id=payload.document_id,
            description=payload.description,
            pdf_file_size=payload.pdf_file_size,
            pdf_page_count=payload.pdf_page_count,
            pdf_page_dimensions=payload.pdf_page_dimensions,
            email_subject=payload.email_subject,
            email_message=payload.email_message,
            expires_in_days=payload.expires_in_days,
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.get("/envelopes")
async def list_envelopes(
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List envelopes with filters."""
    filters = []
    params = {"limit": limit, "offset": offset}

    if loan_id:
        filters.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if lead_id:
        filters.append("lead_id = :lead_id")
        params["lead_id"] = lead_id
    if status:
        filters.append("status = :status")
        params["status"] = status

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    sql = (
        "SELECT e.*, COALESCE(es.full_name, u.email) as created_by_name,"
        " (SELECT COUNT(*) FROM esign_signers WHERE envelope_id = e.id) as signer_count,"
        " (SELECT COUNT(*) FROM esign_fields WHERE envelope_id = e.id) as field_count"
        " FROM esign_envelopes e"
        " LEFT JOIN users u ON u.id = e.created_by_user_id"
        " LEFT JOIN email_signatures es ON es.user_id = u.id"
        " " + where_clause +
        " ORDER BY e.created_at DESC"
        " LIMIT :limit OFFSET :offset"
    )
    result = await db.execute(text(sql), params)

    envelopes = [dict(row._mapping) for row in result]

    return {
        "envelopes": envelopes,
        "count": len(envelopes),
        "limit": limit,
        "offset": offset
    }


@router.get("/envelopes/{envelope_id}")
async def get_envelope(
    envelope_id: int,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Get envelope with signers and fields."""
    envelope = service.get_envelope(envelope_id)
    if not envelope:
        raise HTTPException(status_code=404, detail="Envelope not found")
    return envelope


@router.post("/envelopes/{envelope_id}/send")
async def send_envelope(
    envelope_id: int,
    background_tasks: BackgroundTasks,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Send envelope to signers."""
    try:
        result = service.send_envelope(envelope_id, current_user.id)

        # Queue email sending in background
        if result.get("signers"):
            envelope = service.get_envelope(envelope_id)
            envelope_name = envelope.get("name") if envelope else None
            background_tasks.add_task(send_signer_invitations, result["signers"], envelope_name)

        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.post("/envelopes/{envelope_id}/void")
async def void_envelope(
    envelope_id: int,
    payload: VoidEnvelopePayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Void an envelope."""
    try:
        result = service.void_envelope(envelope_id, current_user.id, payload.reason)
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


# =============================================================================
# SIGNER MANAGEMENT (Staff Auth)
# =============================================================================

@router.post("/envelopes/{envelope_id}/signers")
async def add_signer(
    envelope_id: int,
    payload: AddSignerPayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Add a signer to an envelope."""
    try:
        result = service.add_signer(
            envelope_id=envelope_id,
            name=payload.name,
            email=payload.email,
            role=payload.role,
            signer_order=payload.signer_order,
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.delete("/envelopes/{envelope_id}/signers/{signer_id}")
async def remove_signer(
    envelope_id: int,
    signer_id: int,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Remove a signer from an envelope."""
    try:
        result = service.remove_signer(signer_id)
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


# =============================================================================
# FIELD PLACEMENT (Staff Auth)
# =============================================================================

@router.post("/envelopes/{envelope_id}/fields")
async def add_field(
    envelope_id: int,
    payload: AddFieldPayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Add a field to an envelope."""
    try:
        result = service.add_field(
            envelope_id=envelope_id,
            field_type=payload.field_type,
            page_number=payload.page_number,
            x_position_points=payload.x_position_points,
            y_position_points=payload.y_position_points,
            width_points=payload.width_points,
            height_points=payload.height_points,
            signer_id=payload.signer_id,
            is_required=payload.is_required,
            placeholder_text=payload.placeholder_text,
            tab_order=payload.tab_order,
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.put("/envelopes/{envelope_id}/fields/{field_id}")
async def update_field(
    envelope_id: int,
    field_id: int,
    payload: UpdateFieldPayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Update a field."""
    try:
        result = service.update_field(
            field_id=field_id,
            **payload.dict(exclude_none=True)
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.delete("/envelopes/{envelope_id}/fields/{field_id}")
async def delete_field(
    envelope_id: int,
    field_id: int,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Delete a field."""
    try:
        result = service.delete_field(field_id)
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.post("/envelopes/{envelope_id}/fields/bulk")
async def bulk_save_fields(
    envelope_id: int,
    payload: BulkSaveFieldsPayload,
    current_user: Any = Depends(get_current_user),
    service: EsignService = Depends(get_esign_service)
):
    """Bulk save fields (replace all existing fields)."""
    try:
        fields_data = [f.dict() for f in payload.fields]
        result = service.bulk_save_fields(envelope_id, fields_data)
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


# =============================================================================
# SIGNING SESSION (Token Auth - No Login Required)
# =============================================================================

@router.get("/sign/{token}")
async def validate_signing_token(
    token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Validate signing token and get session data.
    PUBLIC ENDPOINT - No authentication required.
    """
    service = EsignService(db, _esign_models)
    try:
        result = service.validate_signing_token(
            token=token,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=401, detail={"error": e.code, "message": e.message})


@router.get("/sign/{token}/document")
async def get_signing_document(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get PDF document for signing.
    Returns presigned S3 URL or streams the PDF.
    PUBLIC ENDPOINT.
    """
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    signer = await db.execute(text("""
        SELECT s.id, e.pdf_storage_key, e.pdf_file_name, e.status as envelope_status
        FROM esign_signers s
        JOIN esign_envelopes e ON e.id = s.envelope_id
        WHERE s.token_hash = :token_hash AND s.token_expires_at > NOW()
    """), {"token_hash": token_hash}).fetchone()

    if not signer:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if signer.envelope_status in ["voided", "expired"]:
        raise HTTPException(status_code=410, detail="Document no longer available")

    # Return storage key for client to fetch from S3
    # In production, generate a presigned URL
    try:
        from services.perennia_s3_service import get_s3_service
        s3_service = get_s3_service()
        presigned = s3_service.get_presigned_download_url(signer.pdf_storage_key)
        if presigned.get("success"):
            return {
                "download_url": presigned["presigned_url"],
                "file_name": signer.pdf_file_name,
                "expires_in": presigned.get("expires_in", 3600)
            }
    except Exception as e:
        logger.warning(f"S3 presigned URL generation failed: {e}")

    # Fallback
    return {
        "storage_key": signer.pdf_storage_key,
        "file_name": signer.pdf_file_name,
        "note": "S3 not configured - use storage_key directly"
    }


@router.post("/sign/{token}/adopt")
async def adopt_signature(
    token: str,
    payload: AdoptSignaturePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Adopt a typed signature.
    PUBLIC ENDPOINT.
    """
    service = EsignService(db, _esign_models)
    try:
        result = service.adopt_signature(
            token=token,
            signature_text=payload.signature_text,
            signature_font=payload.signature_font,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.post("/sign/{token}/fields/{field_id}")
async def submit_field_value(
    token: str,
    field_id: int,
    payload: SubmitFieldValuePayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submit a value for a field.
    PUBLIC ENDPOINT.
    """
    service = EsignService(db, _esign_models)
    try:
        result = service.submit_field_value(
            token=token,
            field_id=field_id,
            value=payload.value,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


@router.post("/sign/{token}/complete")
async def complete_signing(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Complete signing session.
    Validates all required fields are completed.
    PUBLIC ENDPOINT.
    """
    service = EsignService(db, _esign_models)
    try:
        result = service.complete_signing(
            token=token,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )

        # If envelope is complete, generate signed PDF in background
        if result.get("envelope_completed") and result.get("envelope_id"):
            background_tasks.add_task(generate_signed_documents, result["envelope_id"])

        return result
    except EsignError as e:
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message})


# =============================================================================
# DOCUMENT GENERATION (Staff Auth)
# =============================================================================

@router.post("/envelopes/{envelope_id}/generate")
async def generate_signed_document(
    envelope_id: int,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate the final signed PDF and audit trail.
    Only available for completed envelopes.

    Fetches the original PDF from S3, flattens all field values onto it,
    generates an audit trail PDF, combines them, and uploads the results
    back to S3.
    """
    envelope = await db.execute(text("""
        SELECT * FROM esign_envelopes WHERE id = :id
    """), {"id": envelope_id}).fetchone()

    if not envelope:
        raise HTTPException(status_code=404, detail="Envelope not found")

    if envelope.status != "completed":
        raise HTTPException(status_code=400, detail="Envelope not yet completed")

    try:
        from services.perennia_s3_service import get_s3_service

        s3_service = get_s3_service()
        pdf_service = get_esign_pdf_service(s3_service=s3_service)

        result = pdf_service.generate_signed_pdf(envelope_id, db=db)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate signed document")
            )

        return result

    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"Service not available for document generation: {e}")
        raise HTTPException(
            status_code=503,
            detail="PDF generation service not available"
        )
    except Exception as e:
        logger.error(f"Error generating signed document for envelope {envelope_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Document generation failed"
        )


@router.get("/envelopes/{envelope_id}/documents")
async def list_completed_documents(
    envelope_id: int,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List completed documents for an envelope."""
    docs = await db.execute(text("""
        SELECT * FROM esign_completed_documents
        WHERE envelope_id = :id
        ORDER BY created_at DESC
    """), {"id": envelope_id}).fetchall()

    return {
        "documents": [dict(d._mapping) for d in docs],
        "count": len(docs)
    }


@router.get("/envelopes/{envelope_id}/audit")
async def get_audit_trail(
    envelope_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get audit trail for an envelope."""
    service = EsignService(db, _esign_models)
    events = service.get_audit_trail(envelope_id)

    return {
        "envelope_id": envelope_id,
        "events": events,
        "count": len(events)
    }


# =============================================================================
# PDF UTILITIES
# =============================================================================

@router.post("/pdf/metadata")
async def extract_pdf_metadata(
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user)
):
    """Extract metadata from an uploaded PDF."""
    if not file.content_type or "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="File must be a PDF")

    pdf_bytes = await file.read()

    pdf_service = get_esign_pdf_service()
    result = pdf_service.get_pdf_metadata(pdf_bytes)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to process PDF"))

    return {
        "file_name": file.filename,
        **result
    }


# =============================================================================
# DIAGNOSTIC ENDPOINTS
# =============================================================================

@router.get("/diagnostic/summary")
async def get_esign_system_summary(
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get system summary and health check.
    NO AUTH required for deployment verification.
    """
    try:
        summary = {}

        # Count envelopes by status
        status_counts = await db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM esign_envelopes
            GROUP BY status
        """)).fetchall()
        summary["envelopes_by_status"] = {row[0]: row[1] for row in status_counts}

        # Total counts
        summary["total_envelopes"] = await db.execute(text("SELECT COUNT(*) FROM esign_envelopes")).scalar()
        summary["total_signers"] = await db.execute(text("SELECT COUNT(*) FROM esign_signers")).scalar()
        summary["total_fields"] = await db.execute(text("SELECT COUNT(*) FROM esign_fields")).scalar()
        summary["total_audit_events"] = await db.execute(text("SELECT COUNT(*) FROM esign_audit_events")).scalar()

        return {
            "system": "esign",
            "status": "operational",
            "summary": summary
        }

    except SQLAlchemyError as e:
        return {
            "system": "esign",
            "status": "error",
            "error": "Internal server error"
        }


@router.post("/diagnostic/run-migration")
async def run_esign_migration(
    db: AsyncSession = Depends(get_async_db)
):
    """
    Run E-Sign migration.
    NO AUTH required for deployment.
    """
    try:
        from migrations.add_esign_tables import run_migration
        result = run_migration(db)
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": "Internal server error"
        }
