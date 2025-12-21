"""
Portal Smart Docs Routes

Borrower-facing API endpoints for Smart Docs integration in the client portal.
These endpoints allow borrowers to:
- View their document requirements (needs list)
- See document status and freshness
- Upload documents directly to fulfill requirements
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.smart_docs_models import DocumentRequest, SmartDocument, RequestStatus, DocType
from models.purl import PURLWorkspace, PURLLoan
from services.smart_docs.needs_list_generator import NeedsListGenerator
from services.smart_docs.document_review_pipeline import DocumentReviewPipeline
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal/smart-docs", tags=["Portal Smart Docs"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class DocumentRequirementResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    instructions: Optional[str]
    doc_type: str
    priority: str
    status: str
    required_count: int
    fulfilled_count: int
    freshness_days: Optional[int]
    due_date: Optional[str]
    is_overdue: bool
    documents: list

    class Config:
        from_attributes = True


class PortalNeedsListResponse(BaseModel):
    loan_id: int
    total_requirements: int
    completed_count: int
    pending_count: int
    overdue_count: int
    completion_percentage: int
    requirements: list


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_workspace_loan(db: Session, workspace_slug: str) -> tuple:
    """Get workspace and active loan from slug.

    Returns:
        tuple: (workspace, purl_loan, main_loan_id)
        - main_loan_id is the ID used in Smart Docs tables (references loans.id)
    """
    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.slug == workspace_slug
    ).first()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    loan = db.query(PURLLoan).filter(
        PURLLoan.workspace_id == workspace.id
    ).order_by(PURLLoan.created_at.desc()).first()

    if not loan:
        raise HTTPException(status_code=404, detail="No active loan found")

    # Smart Docs uses main_loan_id (references loans.id), not purl_loan.id
    main_loan_id = loan.main_loan_id or loan.id

    return workspace, loan, main_loan_id


def format_requirement(request: DocumentRequest, documents: list) -> dict:
    """Format a document request for portal display."""
    now = datetime.utcnow()
    is_overdue = False
    if request.due_date and request.due_date < now and request.status == RequestStatus.OPEN:
        is_overdue = True

    # Count fulfilled documents for this request
    fulfilled_docs = [d for d in documents if d.request_id == request.id]

    return {
        "id": request.id,
        "title": request.title,
        "description": request.description,
        "instructions": request.instructions,
        "doc_type": request.doc_type.value if request.doc_type else "OTHER",
        "priority": request.priority.value if request.priority else "NORMAL",
        "status": request.status.value if request.status else "OPEN",
        "required_count": request.required_count or 1,
        "fulfilled_count": len(fulfilled_docs),
        "freshness_days": request.freshness_days,
        "due_date": request.due_date.isoformat() if request.due_date else None,
        "is_overdue": is_overdue,
        "documents": [
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "status": doc.status,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                "document_date": doc.document_date.isoformat() if doc.document_date else None,
                "freshness_status": doc.freshness_status,
            }
            for doc in fulfilled_docs
        ]
    }


# =============================================================================
# PORTAL ENDPOINTS
# =============================================================================

@router.get("/{workspace_slug}/requirements")
async def get_portal_requirements(
    workspace_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get document requirements for a borrower's loan.

    Returns the needs list with status, due dates, and uploaded documents.
    """
    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Get all document requests for this loan (using main_loan_id for Smart Docs)
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == main_loan_id
    ).order_by(
        DocumentRequest.priority.desc(),
        DocumentRequest.due_date.asc().nullslast()
    ).all()

    # Get all documents for this loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == main_loan_id
    ).all()

    # Format requirements
    requirements = [format_requirement(req, documents) for req in requests]

    # Calculate stats
    completed = len([r for r in requirements if r["status"] in ["ACCEPTED", "WAIVED"]])
    pending = len([r for r in requirements if r["status"] in ["OPEN", "PENDING_REVIEW"]])
    overdue = len([r for r in requirements if r["is_overdue"]])

    total = len(requirements)
    completion_pct = int((completed / total) * 100) if total > 0 else 0

    return {
        "loan_id": main_loan_id,
        "workspace_slug": workspace_slug,
        "total_requirements": total,
        "completed_count": completed,
        "pending_count": pending,
        "overdue_count": overdue,
        "completion_percentage": completion_pct,
        "requirements": requirements
    }


@router.get("/{workspace_slug}/requirements/{request_id}")
async def get_requirement_detail(
    workspace_slug: str,
    request_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific document requirement."""
    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    request = db.query(DocumentRequest).filter(
        DocumentRequest.id == request_id,
        DocumentRequest.loan_id == main_loan_id
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="Requirement not found")

    documents = db.query(SmartDocument).filter(
        SmartDocument.request_id == request_id
    ).all()

    return format_requirement(request, documents)


@router.post("/{workspace_slug}/upload")
async def upload_document_for_requirement(
    workspace_slug: str,
    file: UploadFile = File(...),
    request_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload a document to fulfill a requirement.

    The document will be validated and linked to the specific requirement.
    """
    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Verify the request belongs to this loan
    request = db.query(DocumentRequest).filter(
        DocumentRequest.id == request_id,
        DocumentRequest.loan_id == main_loan_id
    ).first()

    if not request:
        raise HTTPException(status_code=404, detail="Requirement not found")

    if request.status in [RequestStatus.ACCEPTED, RequestStatus.WAIVED]:
        raise HTTPException(status_code=400, detail="This requirement has already been fulfilled")

    # Read file content
    content = await file.read()

    # Use the document review pipeline to process the upload
    try:
        pipeline = DocumentReviewPipeline(db)
        result = pipeline.process_upload(
            file_content=content,
            filename=file.filename,
            content_type=file.content_type,
            loan_id=main_loan_id,
            borrower_id=request.borrower_id or 1,
            request_id=request_id,
            document_category=request.doc_type.value if request.doc_type else "other"
        )

        # Update request status to pending review
        if request.status == RequestStatus.OPEN:
            request.status = RequestStatus.PENDING_REVIEW
            db.commit()

        return {
            "success": True,
            "message": "Document uploaded successfully",
            "document_id": result.get("document", {}).get("id"),
            "validation": result.get("validation", {}),
            "requirement_status": request.status.value
        }

    except Exception as e:
        logger.error(f"Error processing upload: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{workspace_slug}/summary")
async def get_document_summary(
    workspace_slug: str,
    db: Session = Depends(get_db)
):
    """
    Get a summary of document collection progress for the portal dashboard.
    """
    workspace, loan, main_loan_id = get_workspace_loan(db, workspace_slug)

    # Get request counts by status
    requests = db.query(DocumentRequest).filter(
        DocumentRequest.loan_id == main_loan_id
    ).all()

    by_status = {
        "open": 0,
        "pending_review": 0,
        "accepted": 0,
        "rejected": 0,
        "waived": 0
    }

    by_priority = {
        "critical": 0,
        "high": 0,
        "normal": 0,
        "low": 0
    }

    overdue_items = []

    now = datetime.utcnow()
    for req in requests:
        status_key = req.status.value.lower() if req.status else "open"
        if status_key in by_status:
            by_status[status_key] += 1

        priority_key = req.priority.value.lower() if req.priority else "normal"
        if priority_key in by_priority:
            by_priority[priority_key] += 1

        if req.due_date and req.due_date < now and req.status == RequestStatus.OPEN:
            overdue_items.append({
                "id": req.id,
                "title": req.title,
                "due_date": req.due_date.isoformat(),
                "days_overdue": (now - req.due_date).days
            })

    total = len(requests)
    completed = by_status["accepted"] + by_status["waived"]

    return {
        "loan_id": main_loan_id,
        "total_requirements": total,
        "completed": completed,
        "pending": by_status["open"] + by_status["pending_review"],
        "completion_percentage": int((completed / total) * 100) if total > 0 else 0,
        "by_status": by_status,
        "by_priority": by_priority,
        "overdue_items": overdue_items,
        "next_action": overdue_items[0]["title"] if overdue_items else (
            requests[0].title if requests and by_status["open"] > 0 else "All documents submitted!"
        )
    }
