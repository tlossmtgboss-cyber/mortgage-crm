"""
Smart Docs eClosing API Routes

REST API for the eClosing platform integration.  Provides endpoints for
creating closing sessions, uploading document packages, scheduling notaries,
tracking closing status, and handling provider webhooks.

Endpoint groups:
  - Session management (authenticated, tenant-isolated)
  - Document upload (authenticated)
  - Notary scheduling (authenticated)
  - Status / eNote tracking (authenticated)
  - Webhooks (unauthenticated, provider-originated)

Prefix: /api/smart-docs/eclosing
"""

import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/eclosing",
    tags=["eClosing"],
)


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class CreateClosingRequest(BaseModel):
    """Request to create a new eClosing session."""
    closing_date: date
    closing_type: str = Field(
        default="hybrid",
        description="full_eclosing, hybrid, or ink",
    )


class UploadDocumentItem(BaseModel):
    """A single document in the closing package upload."""
    doc_type: str
    filename: str
    requires_notarization: bool = False
    requires_wet_ink: bool = False
    signing_order: int = 1
    mismo_compliant: bool = False


class UploadDocumentsRequest(BaseModel):
    """Request to upload closing documents."""
    documents: List[UploadDocumentItem]


class ScheduleNotaryRequest(BaseModel):
    """Request to schedule a notary."""
    notary_type: str = Field(
        default="RON",
        description="RON (remote online), IPEN (in-person electronic), or traditional",
    )
    preferred_date: datetime


class CompleteClosingRequest(BaseModel):
    """Request to finalize a closing session."""
    notes: Optional[str] = None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/create/{loan_id}")
async def create_closing(
    loan_id: int,
    request: CreateClosingRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new eClosing session for a loan.

    Creates a session with the configured eClosing provider and returns
    the session ID and signing URL.
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        session = service.create_closing(
            loan_id=loan_id,
            org_id=org_id,
            closing_date=request.closing_date,
            closing_type=request.closing_type,
        )
        db.commit()

        return {
            "status": "success",
            "session_id": session.session_id,
            "provider": session.provider,
            "closing_type": session.closing_type,
            "signing_url": session.signing_url,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create eClosing session for loan %d", loan_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create closing session")


@router.post("/{session_id}/documents")
async def upload_closing_documents(
    session_id: str,
    request: UploadDocumentsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Upload closing package documents to the eClosing provider.

    Each document is tagged with signing requirements (wet-ink, notarization,
    MISMO compliance).
    """
    from services.smart_docs.integrations.eclosing_service import (
        EClosingService,
        ClosingDocument,
    )

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    documents = [
        ClosingDocument(
            doc_type=doc.doc_type,
            filename=doc.filename,
            requires_notarization=doc.requires_notarization,
            requires_wet_ink=doc.requires_wet_ink,
            signing_order=doc.signing_order,
            mismo_compliant=doc.mismo_compliant,
        )
        for doc in request.documents
    ]

    try:
        service = EClosingService(db)
        result = service.upload_closing_documents(
            session_id=session_id,
            documents=documents,
            org_id=org_id,
        )
        db.commit()

        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to upload documents for session %s", session_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upload documents")


@router.get("/{session_id}/status")
async def get_closing_status(
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the current status of an eClosing session.

    Returns document-level status, notary status, and eNote status.
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        status = service.get_closing_status(session_id, org_id)

        return {
            "status": status.status,
            "documents_signed": status.documents_signed,
            "documents_pending": status.documents_pending,
            "documents_total": status.documents_total,
            "notary_status": status.notary_status,
            "enote_status": status.enote_status,
            "signing_url": status.signing_url,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get status for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to get closing status")


@router.post("/{session_id}/schedule-notary")
async def schedule_notary(
    session_id: str,
    request: ScheduleNotaryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Schedule a notary for the closing session.

    Supports RON (remote online), IPEN (in-person electronic), and
    traditional notarization types.
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        result = service.schedule_notary(
            session_id=session_id,
            notary_type=request.notary_type,
            preferred_date=request.preferred_date,
            org_id=org_id,
        )
        db.commit()

        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to schedule notary for session %s", session_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to schedule notary")


@router.post("/{session_id}/complete")
async def complete_closing(
    session_id: str,
    request: CompleteClosingRequest = CompleteClosingRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Finalize the closing session.

    Marks all documents as signed, registers eNote with MERS (mock),
    stores in eVault (mock), and returns post-closing task list.
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        result = service.complete_closing(session_id, org_id)
        db.commit()

        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to complete closing for session %s", session_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to complete closing")


@router.get("/loan/{loan_id}")
async def get_closings_for_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all eClosing sessions for a loan.

    Returns sessions ordered by creation date (newest first).
    """
    from database.models.eclosing import EClosingSession

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        sessions = db.query(EClosingSession).filter(
            EClosingSession.organization_id == org_id,
            EClosingSession.loan_id == loan_id,
        ).order_by(EClosingSession.created_at.desc()).all()

        return {
            "loan_id": loan_id,
            "total": len(sessions),
            "sessions": [
                {
                    "id": s.id,
                    "session_id": s.session_id,
                    "provider": s.provider,
                    "closing_type": s.closing_type,
                    "closing_date": s.closing_date.isoformat() if s.closing_date else None,
                    "status": s.status,
                    "signing_url": s.signing_url,
                    "notary_type": s.notary_type,
                    "notary_scheduled_at": s.notary_scheduled_at.isoformat() if s.notary_scheduled_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "documents_count": len(s.documents_package or []),
                    "enote_mers_min": s.enote_mers_min,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in sessions
            ],
        }
    except Exception as e:
        logger.exception("Failed to get closings for loan %d", loan_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve closings")


@router.get("/{session_id}/enote")
async def get_enote_status(
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get eNote status for a closing session.

    Returns MERS registration status, eVault storage, and tamper seal validity.
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        result = service.get_enote_status(session_id, org_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get eNote status for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to get eNote status")


@router.post("/webhooks")
async def handle_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle eClosing provider webhook callbacks.

    This endpoint is unauthenticated (provider-originated). In production,
    verify the webhook signature using the provider's webhook secret.

    Supported events:
      - closing.status_changed
      - document.signed
      - notary.completed
      - enote.registered
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    try:
        webhook_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # TODO: Verify webhook signature in production
    # signature = request.headers.get("X-Webhook-Signature", "")
    # if not verify_signature(signature, webhook_data):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        service = EClosingService(db)
        result = service.webhook_handler(webhook_data)
        db.commit()

        return result
    except Exception as e:
        logger.exception("Failed to process webhook: %s", str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.post("/generate-package/{loan_id}")
async def generate_closing_package(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate a closing document package for a loan.

    Identifies required closing documents based on loan type, state, and
    lender requirements. Returns documents with signing requirements
    (wet-ink, notarization, MISMO compliance).
    """
    from services.smart_docs.integrations.eclosing_service import EClosingService

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        service = EClosingService(db)
        documents = service.generate_closing_package(loan_id, org_id)

        return {
            "loan_id": loan_id,
            "document_count": len(documents),
            "documents": [
                {
                    "doc_type": doc.doc_type,
                    "filename": doc.filename,
                    "requires_notarization": doc.requires_notarization,
                    "requires_wet_ink": doc.requires_wet_ink,
                    "signing_order": doc.signing_order,
                    "mismo_compliant": doc.mismo_compliant,
                }
                for doc in documents
            ],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to generate closing package for loan %d", loan_id)
        raise HTTPException(status_code=500, detail="Failed to generate closing package")
