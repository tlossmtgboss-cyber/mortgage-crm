"""
Smart Document Intelligence API Routes

AI-powered document classification, POS-to-document analysis,
call transcript document need detection, and configurable requirement rules.

Endpoints:
    POST /doc-intel/classify                         — Classify uploaded document
    POST /doc-intel/classify/{document_id}           — Classify existing document
    GET  /doc-intel/classification/{document_id}     — Get classification results
    POST /doc-intel/classification/{id}/feedback     — Submit classification feedback
    POST /doc-intel/analyze-application/{loan_id}    — Analyze POS for required docs
    POST /doc-intel/analyze-application/{loan_id}/create-requests — Create requests from analysis
    POST /doc-intel/analyze-call                     — Analyze call for document needs
    POST /doc-intel/analyze-call/{call_id}/create-requests — Create requests from call
    GET  /doc-intel/call-needs/{loan_id}             — Get call-detected needs
    POST /doc-intel/call-needs/{need_id}/confirm     — Confirm a call-detected need
    POST /doc-intel/call-needs/{need_id}/dismiss     — Dismiss a call-detected need
    GET  /doc-intel/requirement-rules                — List requirement rules
    POST /doc-intel/requirement-rules                — Create requirement rule
    PUT  /doc-intel/requirement-rules/{rule_id}      — Update requirement rule
    DELETE /doc-intel/requirement-rules/{rule_id}    — Delete (soft) requirement rule
    POST /doc-intel/batch-classify/{loan_id}         — Batch classify all unclassified docs
    GET  /doc-intel/stats                            — Intelligence stats
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from database import get_db
from auth.dependencies import get_current_user
from database.models.document_intelligence import (
    AIDocumentClassification,
    DocumentRequirementRule,
    CallIntelDocumentNeed,
)
from services.smart_docs.ai_classifier_service import get_ai_classifier_service
from services.smart_docs.call_intel_extractor import get_call_intel_extractor
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from routes.smart_docs_models import (
    _get_loan_org_id,
    _verify_loan_tenant,
    _verify_document_tenant,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Intelligence"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ClassifyDocumentRequest(BaseModel):
    """Optional hints when classifying an uploaded document."""
    doc_type_hint: Optional[str] = None
    loan_id: Optional[int] = None


class AnalyzeCallRequest(BaseModel):
    """Request body for call transcript analysis."""
    call_id: int
    transcript: str
    loan_id: int
    lead_id: Optional[int] = None


class CreateRequestsFromAnalysisBody(BaseModel):
    """Request body for creating document requests from POS analysis."""
    requirements: List[Dict[str, Any]]
    auto_create_all: bool = False


class CreateRequestsFromCallBody(BaseModel):
    """Request body for creating document requests from call analysis."""
    needs: List[Dict[str, Any]]


class ClassificationFeedbackBody(BaseModel):
    """Human feedback on an AI classification."""
    is_correct: bool
    correct_type: Optional[str] = None


class ConfirmCallNeedBody(BaseModel):
    """Body for confirming a call-detected need."""
    pass


class DismissCallNeedBody(BaseModel):
    """Body for dismissing a call-detected need."""
    reason: str


class CreateRequirementRuleBody(BaseModel):
    """Body for creating a document requirement rule."""
    rule_name: str
    rule_description: Optional[str] = None
    category: str
    doc_type: str
    trigger_conditions: Optional[Dict[str, Any]] = None
    required_count: int = 1
    applies_to: str = "BORROWER"
    priority: str = "NORMAL"
    freshness_days: Optional[int] = None
    instructions: Optional[str] = None
    sort_order: int = 0


class UpdateRequirementRuleBody(BaseModel):
    """Body for updating a document requirement rule."""
    rule_name: Optional[str] = None
    rule_description: Optional[str] = None
    category: Optional[str] = None
    doc_type: Optional[str] = None
    trigger_conditions: Optional[Dict[str, Any]] = None
    required_count: Optional[int] = None
    applies_to: Optional[str] = None
    priority: Optional[str] = None
    freshness_days: Optional[int] = None
    instructions: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# =============================================================================
# HELPERS
# =============================================================================

def _get_user_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the current user object."""
    return getattr(current_user, "organization_id", None)


def _get_user_display(current_user) -> str:
    """Get a display name or email for the current user."""
    email = getattr(current_user, "email", None)
    first = getattr(current_user, "first_name", "")
    last = getattr(current_user, "last_name", "")
    name = f"{first} {last}".strip()
    return name or email or "unknown"


def _verify_org_owns_classification(
    db: Session,
    classification_id: int,
    current_user,
) -> AIDocumentClassification:
    """Fetch classification and verify tenant. Raises 404 on mismatch."""
    record = db.query(AIDocumentClassification).filter(
        AIDocumentClassification.id == classification_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Classification not found")

    org_id = _get_user_org_id(current_user)
    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if org_id and not is_admin:
        if record.organization_id is not None and record.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Classification not found")
    return record


def _verify_org_owns_rule(
    db: Session,
    rule_id: int,
    current_user,
) -> DocumentRequirementRule:
    """Fetch rule and verify tenant. Raises 404 on mismatch."""
    rule = db.query(DocumentRequirementRule).filter(
        DocumentRequirementRule.id == rule_id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    org_id = _get_user_org_id(current_user)
    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if org_id and not is_admin:
        if rule.organization_id is not None and rule.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def _verify_org_owns_call_need(
    db: Session,
    need_id: int,
    current_user,
) -> CallIntelDocumentNeed:
    """Fetch call-intel need and verify tenant. Raises 404 on mismatch."""
    need = db.query(CallIntelDocumentNeed).filter(
        CallIntelDocumentNeed.id == need_id,
    ).first()
    if not need:
        raise HTTPException(status_code=404, detail="Call need not found")

    org_id = _get_user_org_id(current_user)
    is_admin = getattr(current_user, "permission_role", "") == "admin"
    if org_id and not is_admin:
        if need.organization_id is not None and need.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Call need not found")
    return need


# =============================================================================
# 1. POST /doc-intel/classify — Classify an uploaded document
# =============================================================================

@router.post("/doc-intel/classify")
async def classify_uploaded_document(
    file: UploadFile = File(...),
    doc_type_hint: Optional[str] = Form(None),
    loan_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Classify an uploaded document using AI.

    Accepts a file upload and optional hints. Returns the predicted document
    type, confidence score, alternative predictions, and detected features.
    """
    org_id = _get_user_org_id(current_user)

    if loan_id:
        _verify_loan_tenant(db, loan_id, current_user)

    try:
        file_content = await file.read()
    except Exception as e:
        logger.error("Failed to read uploaded file: %s", e)
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    classifier = get_ai_classifier_service()
    result = classifier.classify_document(
        file_content=file_content,
        mime_type=file.content_type or "application/octet-stream",
        filename=file.filename or "unknown",
    )

    return {
        "predicted_type": result.predicted_type,
        "confidence": result.confidence,
        "alternatives": result.alternatives,
        "features_detected": result.features_detected,
        "text_snippet": result.text_snippet[:500] if result.text_snippet else None,
        "model_used": getattr(result, "model_used", None),
        "duration_ms": getattr(result, "duration_ms", None),
        "doc_type_hint": doc_type_hint,
        "loan_id": loan_id,
    }


# =============================================================================
# 2. POST /doc-intel/classify/{document_id} — Classify existing document
# =============================================================================

@router.post("/doc-intel/classify/{document_id}")
async def classify_existing_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Classify an existing document from smart_documents by fetching its
    content from S3 and running the AI classifier.
    """
    from models.smart_docs_models import SmartDocument

    doc = _verify_document_tenant(db, document_id, current_user)
    org_id = _get_loan_org_id(db, doc.loan_id) if doc.loan_id else _get_user_org_id(current_user)

    if not doc.storage_key:
        raise HTTPException(status_code=400, detail="Document has no storage key")

    s3_service = get_smart_docs_s3_service()
    download_result = s3_service.download_file(doc.storage_key)
    if not download_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve document content from storage",
        )

    file_content = download_result["content"]
    mime_type = doc.mime_type or download_result.get("content_type", "application/octet-stream")

    classifier = get_ai_classifier_service()
    result = classifier.classify_document(
        file_content=file_content,
        mime_type=mime_type,
        filename=doc.file_name or "unknown",
    )

    # Save classification to DB
    try:
        classifier.save_classification(
            db=db,
            document_id=document_id,
            result=result,
            organization_id=org_id,
        )
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to save classification for document %d", document_id)
        raise HTTPException(status_code=500, detail="Failed to save classification")

    return {
        "document_id": document_id,
        "predicted_type": result.predicted_type,
        "confidence": result.confidence,
        "alternatives": result.alternatives,
        "features_detected": result.features_detected,
        "text_snippet": result.text_snippet[:500] if result.text_snippet else None,
        "model_used": getattr(result, "model_used", None),
        "duration_ms": getattr(result, "duration_ms", None),
    }


# =============================================================================
# 3. GET /doc-intel/classification/{document_id} — Get classification results
# =============================================================================

@router.get("/doc-intel/classification/{document_id}")
async def get_classification(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get existing AI classification results for a document.
    Returns 404 if the document has not been classified yet.
    """
    _verify_document_tenant(db, document_id, current_user)

    classifier = get_ai_classifier_service()
    result = classifier.get_classification_for_document(db, document_id)

    if not result:
        raise HTTPException(status_code=404, detail="No classification found for this document")

    return result


# =============================================================================
# 4. POST /doc-intel/classification/{classification_id}/feedback
# =============================================================================

@router.post("/doc-intel/classification/{classification_id}/feedback")
async def submit_classification_feedback(
    classification_id: int,
    body: ClassificationFeedbackBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Submit human feedback on an AI classification to improve accuracy.

    If is_correct is False, optionally provide the correct_type so the
    system can learn from the correction.
    """
    record = _verify_org_owns_classification(db, classification_id, current_user)

    record.is_correct = body.is_correct
    record.corrected_by = _get_user_display(current_user)
    record.corrected_at = datetime.now(timezone.utc)

    if not body.is_correct and body.correct_type:
        record.corrected_doc_type = body.correct_type

    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to save classification feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    return {
        "classification_id": record.id,
        "document_id": record.document_id,
        "predicted_doc_type": record.predicted_doc_type,
        "is_correct": record.is_correct,
        "corrected_doc_type": record.corrected_doc_type,
        "corrected_by": record.corrected_by,
        "corrected_at": record.corrected_at.isoformat() if record.corrected_at else None,
        "message": "Feedback saved successfully",
    }


# =============================================================================
# 5. POST /doc-intel/analyze-application/{loan_id}
# =============================================================================

@router.post("/doc-intel/analyze-application/{loan_id}")
async def analyze_application_for_docs(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Analyze a POS (Point-of-Sale) loan application to determine which
    documents are required based on loan parameters and active requirement rules.

    Evaluates DocumentRequirementRule records against the loan's attributes
    (loan_type, occupancy_type, etc.) and returns a prioritized list of
    document requirements.
    """
    from sqlalchemy import text as sa_text

    _verify_loan_tenant(db, loan_id, current_user)
    org_id = _get_loan_org_id(db, loan_id)

    # Fetch loan parameters for rule evaluation
    loan = db.execute(
        sa_text("""
            SELECT id, loan_type, transaction_type, occupancy_type,
                   property_type, loan_amount, borrower_name
            FROM loans WHERE id = :loan_id
        """),
        {"loan_id": loan_id},
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all active rules for this organization (or global rules with NULL org)
    rules = db.query(DocumentRequirementRule).filter(
        DocumentRequirementRule.is_active == True,
        (
            (DocumentRequirementRule.organization_id == org_id)
            | (DocumentRequirementRule.organization_id.is_(None))
        ),
    ).order_by(
        DocumentRequirementRule.sort_order,
        DocumentRequirementRule.category,
    ).all()

    # Evaluate each rule against loan parameters
    requirements = []
    loan_type = (loan.loan_type or "").upper()
    occupancy = (loan.occupancy_type or "").upper() if hasattr(loan, "occupancy_type") and loan.occupancy_type else ""
    loan_amount = float(loan.loan_amount or 0) if loan.loan_amount else 0

    for rule in rules:
        conditions = rule.trigger_conditions or {}

        # Check loan_type filter
        allowed_types = conditions.get("loan_types")
        if allowed_types and loan_type not in [t.upper() for t in allowed_types]:
            continue

        # Check occupancy_type filter
        allowed_occupancy = conditions.get("occupancy_types")
        if allowed_occupancy and occupancy not in [o.upper() for o in allowed_occupancy]:
            continue

        # Check loan amount range
        min_amount = conditions.get("min_loan_amount")
        if min_amount is not None and loan_amount < min_amount:
            continue

        max_amount = conditions.get("max_loan_amount")
        if max_amount is not None and loan_amount > max_amount:
            continue

        requirements.append({
            "rule_id": rule.id,
            "doc_type": rule.doc_type,
            "title": rule.rule_name,
            "description": rule.rule_description,
            "category": rule.category,
            "priority": rule.priority,
            "required_count": rule.required_count,
            "applies_to": rule.applies_to,
            "freshness_days": rule.freshness_days,
            "instructions": rule.instructions,
        })

    return {
        "loan_id": loan_id,
        "borrower_name": loan.borrower_name,
        "loan_type": loan_type,
        "total_requirements": len(requirements),
        "requirements": requirements,
    }


# =============================================================================
# 6. POST /doc-intel/analyze-application/{loan_id}/create-requests
# =============================================================================

@router.post("/doc-intel/analyze-application/{loan_id}/create-requests")
async def create_requests_from_analysis(
    loan_id: int,
    body: CreateRequestsFromAnalysisBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create smart_document_requests from the POS analysis results.

    Accepts the list of requirements (from analyze-application) and
    creates corresponding document request records. Optionally creates
    all requirements when auto_create_all is True.
    """
    from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType

    _verify_loan_tenant(db, loan_id, current_user)

    created_ids = []
    errors = []

    items = body.requirements
    if not items:
        raise HTTPException(status_code=400, detail="No requirements provided")

    for req_data in items:
        try:
            doc_type_str = req_data.get("doc_type", "OTHER")
            try:
                doc_type_enum = DocType(doc_type_str)
            except ValueError:
                doc_type_enum = DocType.OTHER

            priority_str = req_data.get("priority", "NORMAL")
            try:
                priority_enum = RequestPriority(priority_str)
            except ValueError:
                priority_enum = RequestPriority.NORMAL

            request = DocumentRequest(
                loan_id=loan_id,
                doc_type=doc_type_enum,
                title=req_data.get("title", doc_type_str.replace("_", " ").title()),
                description=req_data.get("description"),
                instructions=req_data.get("instructions"),
                priority=priority_enum,
                status=RequestStatus.OPEN,
                is_active=True,
            )
            db.add(request)
            db.flush()
            created_ids.append(request.id)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to create request for %s: %s", req_data.get("doc_type"), e)
            errors.append({
                "doc_type": req_data.get("doc_type"),
                "error": str(e),
            })

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to commit document requests")
        raise HTTPException(status_code=500, detail="Failed to create document requests")

    return {
        "loan_id": loan_id,
        "created_count": len(created_ids),
        "created_request_ids": created_ids,
        "errors": errors,
        "message": f"Created {len(created_ids)} document requests",
    }


# =============================================================================
# 7. POST /doc-intel/analyze-call — Analyze call for document needs
# =============================================================================

@router.post("/doc-intel/analyze-call")
async def analyze_call_for_docs(
    body: AnalyzeCallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Analyze a call transcript for document needs.

    Uses keyword analysis, circumstance detection, and optional AI-powered
    semantic analysis to identify documents that need to be collected.
    """
    if body.loan_id:
        _verify_loan_tenant(db, body.loan_id, current_user)

    extractor = get_call_intel_extractor(db)
    result = extractor.analyze_call(
        call_id=body.call_id,
        transcript=body.transcript,
        loan_id=body.loan_id,
        lead_id=body.lead_id,
    )

    return {
        "call_id": result.call_id,
        "loan_id": result.loan_id,
        "success": result.success,
        "error": result.error,
        "total_needs": result.total_needs,
        "auto_create_count": result.auto_create_count,
        "circumstances_detected": result.circumstances_detected,
        "summary": result.summary,
        "document_needs": [
            {
                "doc_type": need.doc_type,
                "description": need.description,
                "confidence": need.confidence,
                "source_snippet": need.source_snippet[:300] if need.source_snippet else None,
                "keywords_matched": need.keywords_matched,
                "action_type": need.action_type,
                "circumstance": need.circumstance,
                "priority": need.priority,
                "auto_create_request": need.auto_create_request,
            }
            for need in result.document_needs
        ],
    }


# =============================================================================
# 8. POST /doc-intel/analyze-call/{call_id}/create-requests
# =============================================================================

@router.post("/doc-intel/analyze-call/{call_id}/create-requests")
async def create_requests_from_call(
    call_id: int,
    body: CreateRequestsFromCallBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create document requests from call-detected document needs.

    Accepts a list of needs and creates smart_document_requests for each.
    Links the created requests back to the call_intel_document_needs records.
    """
    from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType

    created_ids = []
    errors = []

    for need_data in body.needs:
        loan_id = need_data.get("loan_id")
        if loan_id:
            _verify_loan_tenant(db, loan_id, current_user)

        try:
            doc_type_str = need_data.get("doc_type", "OTHER")
            try:
                doc_type_enum = DocType(doc_type_str)
            except ValueError:
                doc_type_enum = DocType.OTHER

            priority_str = need_data.get("priority", "NORMAL")
            try:
                priority_enum = RequestPriority(priority_str)
            except ValueError:
                priority_enum = RequestPriority.NORMAL

            request = DocumentRequest(
                loan_id=loan_id,
                doc_type=doc_type_enum,
                title=need_data.get("title", f"{doc_type_str.replace('_', ' ').title()} (from call)"),
                description=need_data.get("description"),
                instructions=f"Detected from call #{call_id}",
                priority=priority_enum,
                status=RequestStatus.OPEN,
                is_active=True,
            )
            db.add(request)
            db.flush()
            created_ids.append(request.id)

            # Link back to call_intel_document_needs if we have a need_id
            need_id = need_data.get("need_id")
            if need_id:
                call_need = db.query(CallIntelDocumentNeed).filter(
                    CallIntelDocumentNeed.id == need_id,
                ).first()
                if call_need:
                    call_need.linked_request_id = request.id
                    call_need.status = "REQUEST_CREATED"

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to create request from call need: %s", e)
            errors.append({
                "doc_type": need_data.get("doc_type"),
                "error": str(e),
            })

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to commit call-based document requests")
        raise HTTPException(status_code=500, detail="Failed to create document requests")

    return {
        "call_id": call_id,
        "created_count": len(created_ids),
        "created_request_ids": created_ids,
        "errors": errors,
        "message": f"Created {len(created_ids)} document requests from call",
    }


# =============================================================================
# 9. GET /doc-intel/call-needs/{loan_id} — Get call-detected document needs
# =============================================================================

@router.get("/doc-intel/call-needs/{loan_id}")
async def get_call_document_needs(
    loan_id: int,
    status: Optional[str] = Query(None, description="Filter by status: DETECTED, CONFIRMED, DISMISSED, REQUEST_CREATED"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all document needs detected from calls for a specific loan.

    Includes the detection status lifecycle so LOs can review, confirm, or
    dismiss detected needs.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    query = db.query(CallIntelDocumentNeed).filter(
        CallIntelDocumentNeed.loan_id == loan_id,
    )

    if status:
        query = query.filter(CallIntelDocumentNeed.status == status.upper())

    needs = query.order_by(
        CallIntelDocumentNeed.created_at.desc(),
    ).all()

    return {
        "loan_id": loan_id,
        "total": len(needs),
        "needs": [
            {
                "id": need.id,
                "call_id": need.call_id,
                "call_date": need.call_date.isoformat() if need.call_date else None,
                "detected_doc_type": need.detected_doc_type,
                "detected_doc_description": need.detected_doc_description,
                "detection_confidence": need.detection_confidence,
                "source_transcript_snippet": need.source_transcript_snippet[:300] if need.source_transcript_snippet else None,
                "keywords_matched": need.keywords_matched,
                "status": need.status,
                "linked_request_id": need.linked_request_id,
                "confirmed_by": need.confirmed_by,
                "confirmed_at": need.confirmed_at.isoformat() if need.confirmed_at else None,
                "dismissed_by": need.dismissed_by,
                "dismissed_at": need.dismissed_at.isoformat() if need.dismissed_at else None,
                "dismiss_reason": need.dismiss_reason,
                "created_at": need.created_at.isoformat() if need.created_at else None,
            }
            for need in needs
        ],
    }


# =============================================================================
# 10. POST /doc-intel/call-needs/{need_id}/confirm
# =============================================================================

@router.post("/doc-intel/call-needs/{need_id}/confirm")
async def confirm_call_need(
    need_id: int,
    body: ConfirmCallNeedBody = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Confirm a call-detected document need and create a document request.

    Updates the need status to CONFIRMED and creates a corresponding
    smart_document_request entry.
    """
    from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType

    need = _verify_org_owns_call_need(db, need_id, current_user)

    if need.status in ("CONFIRMED", "REQUEST_CREATED"):
        raise HTTPException(status_code=400, detail="Need is already confirmed or has a request created")

    # Update need status
    need.status = "CONFIRMED"
    need.confirmed_by = _get_user_display(current_user)
    need.confirmed_at = datetime.now(timezone.utc)

    # Create document request
    try:
        doc_type_enum = DocType(need.detected_doc_type)
    except ValueError:
        doc_type_enum = DocType.OTHER

    request = DocumentRequest(
        loan_id=need.loan_id,
        doc_type=doc_type_enum,
        title=f"{need.detected_doc_type.replace('_', ' ').title()} (from call)",
        description=need.detected_doc_description,
        instructions=f"Confirmed from call #{need.call_id}",
        priority=RequestPriority.HIGH,
        status=RequestStatus.OPEN,
        is_active=True,
    )
    db.add(request)
    db.flush()

    # Link the request back
    need.linked_request_id = request.id
    need.status = "REQUEST_CREATED"

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to confirm call need %d: %s", need_id, e)
        raise HTTPException(status_code=500, detail="Failed to confirm need")

    return {
        "need_id": need_id,
        "status": need.status,
        "linked_request_id": request.id,
        "confirmed_by": need.confirmed_by,
        "message": "Need confirmed and document request created",
    }


# =============================================================================
# 11. POST /doc-intel/call-needs/{need_id}/dismiss
# =============================================================================

@router.post("/doc-intel/call-needs/{need_id}/dismiss")
async def dismiss_call_need(
    need_id: int,
    body: DismissCallNeedBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Dismiss a call-detected document need.

    Marks the need as DISMISSED with a reason so it does not appear in
    the active needs list.
    """
    need = _verify_org_owns_call_need(db, need_id, current_user)

    if need.status == "DISMISSED":
        raise HTTPException(status_code=400, detail="Need is already dismissed")

    need.status = "DISMISSED"
    need.dismissed_by = _get_user_display(current_user)
    need.dismissed_at = datetime.now(timezone.utc)
    need.dismiss_reason = body.reason

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to dismiss call need %d: %s", need_id, e)
        raise HTTPException(status_code=500, detail="Failed to dismiss need")

    return {
        "need_id": need_id,
        "status": "DISMISSED",
        "dismissed_by": need.dismissed_by,
        "dismiss_reason": body.reason,
        "message": "Need dismissed",
    }


# =============================================================================
# 12. GET /doc-intel/requirement-rules — List requirement rules
# =============================================================================

@router.get("/doc-intel/requirement-rules")
async def list_requirement_rules(
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    loan_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all document requirement rules.

    Filters by the user's organization. Supports optional filtering by
    category, doc_type, and loan_type (checked within trigger_conditions).
    """
    org_id = _get_user_org_id(current_user)

    query = db.query(DocumentRequirementRule)

    # Tenant filter: own org's rules plus global (NULL org) rules
    if org_id:
        query = query.filter(
            (DocumentRequirementRule.organization_id == org_id)
            | (DocumentRequirementRule.organization_id.is_(None))
        )

    if is_active is not None:
        query = query.filter(DocumentRequirementRule.is_active == is_active)

    if category:
        query = query.filter(DocumentRequirementRule.category == category)

    if doc_type:
        query = query.filter(DocumentRequirementRule.doc_type == doc_type)

    rules = query.order_by(
        DocumentRequirementRule.sort_order,
        DocumentRequirementRule.category,
    ).all()

    # Post-filter by loan_type (inside trigger_conditions JSON)
    if loan_type:
        filtered = []
        for rule in rules:
            conditions = rule.trigger_conditions or {}
            allowed_types = conditions.get("loan_types")
            if allowed_types is None or loan_type.upper() in [t.upper() for t in allowed_types]:
                filtered.append(rule)
        rules = filtered

    return {
        "total": len(rules),
        "rules": [
            {
                "id": rule.id,
                "organization_id": rule.organization_id,
                "rule_name": rule.rule_name,
                "rule_description": rule.rule_description,
                "category": rule.category,
                "doc_type": rule.doc_type,
                "trigger_conditions": rule.trigger_conditions,
                "required_count": rule.required_count,
                "applies_to": rule.applies_to,
                "priority": rule.priority,
                "freshness_days": rule.freshness_days,
                "instructions": rule.instructions,
                "is_active": rule.is_active,
                "sort_order": rule.sort_order,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            }
            for rule in rules
        ],
    }


# =============================================================================
# 13. POST /doc-intel/requirement-rules — Create requirement rule
# =============================================================================

@router.post("/doc-intel/requirement-rules")
async def create_requirement_rule(
    body: CreateRequirementRuleBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a custom document requirement rule for the user's organization."""
    org_id = _get_user_org_id(current_user)

    rule = DocumentRequirementRule(
        organization_id=org_id,
        rule_name=body.rule_name,
        rule_description=body.rule_description,
        category=body.category,
        doc_type=body.doc_type,
        trigger_conditions=body.trigger_conditions,
        required_count=body.required_count,
        applies_to=body.applies_to,
        priority=body.priority,
        freshness_days=body.freshness_days,
        instructions=body.instructions,
        sort_order=body.sort_order,
        is_active=True,
    )

    try:
        db.add(rule)
        db.commit()
        db.refresh(rule)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to create requirement rule: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create rule")

    return {
        "id": rule.id,
        "rule_name": rule.rule_name,
        "category": rule.category,
        "doc_type": rule.doc_type,
        "organization_id": rule.organization_id,
        "message": "Requirement rule created",
    }


# =============================================================================
# 14. PUT /doc-intel/requirement-rules/{rule_id} — Update requirement rule
# =============================================================================

@router.put("/doc-intel/requirement-rules/{rule_id}")
async def update_requirement_rule(
    rule_id: int,
    body: UpdateRequirementRuleBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing document requirement rule."""
    rule = _verify_org_owns_rule(db, rule_id, current_user)

    # Apply only provided fields
    update_fields = body.model_dump(exclude_unset=True)
    for field_name, value in update_fields.items():
        setattr(rule, field_name, value)

    rule.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(rule)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to update rule %d: %s", rule_id, e)
        raise HTTPException(status_code=500, detail="Failed to update rule")

    return {
        "id": rule.id,
        "rule_name": rule.rule_name,
        "category": rule.category,
        "doc_type": rule.doc_type,
        "is_active": rule.is_active,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        "message": "Rule updated",
    }


# =============================================================================
# 15. DELETE /doc-intel/requirement-rules/{rule_id} — Soft delete rule
# =============================================================================

@router.delete("/doc-intel/requirement-rules/{rule_id}")
async def delete_requirement_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Soft-delete a document requirement rule by setting is_active to False."""
    rule = _verify_org_owns_rule(db, rule_id, current_user)

    rule.is_active = False
    rule.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Failed to delete rule %d: %s", rule_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete rule")

    return {
        "id": rule_id,
        "is_active": False,
        "message": "Rule deactivated",
    }


# =============================================================================
# 16. POST /doc-intel/batch-classify/{loan_id} — Batch classify docs
# =============================================================================

@router.post("/doc-intel/batch-classify/{loan_id}")
async def batch_classify_documents(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Batch classify all unclassified documents for a loan.

    Finds all smart_documents for the loan that do not yet have an
    AIDocumentClassification record, fetches their content from S3,
    and classifies each one.
    """
    from models.smart_docs_models import SmartDocument

    _verify_loan_tenant(db, loan_id, current_user)
    org_id = _get_loan_org_id(db, loan_id)

    # Get all documents for this loan
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id,
        SmartDocument.status.notin_(["DELETED", "SUPERSEDED"]),
    ).all()

    if not documents:
        return {
            "loan_id": loan_id,
            "total_documents": 0,
            "classified": 0,
            "skipped": 0,
            "failed": 0,
            "results": [],
            "message": "No documents found for this loan",
        }

    # Find which documents already have classifications
    classified_doc_ids = set()
    existing = db.query(AIDocumentClassification.document_id).filter(
        AIDocumentClassification.document_id.in_([d.id for d in documents]),
    ).all()
    for row in existing:
        classified_doc_ids.add(row[0])

    # Filter to unclassified only
    to_classify = [d for d in documents if d.id not in classified_doc_ids]

    if not to_classify:
        return {
            "loan_id": loan_id,
            "total_documents": len(documents),
            "classified": 0,
            "skipped": len(documents),
            "failed": 0,
            "results": [],
            "message": "All documents already classified",
        }

    classifier = get_ai_classifier_service()
    s3_service = get_smart_docs_s3_service()
    results = []
    classified_count = 0
    failed_count = 0

    for doc in to_classify:
        if not doc.storage_key:
            results.append({
                "document_id": doc.id,
                "file_name": doc.file_name,
                "status": "skipped",
                "reason": "No storage key",
            })
            failed_count += 1
            continue

        try:
            download_result = s3_service.download_file(doc.storage_key)
            if not download_result.get("success"):
                results.append({
                    "document_id": doc.id,
                    "file_name": doc.file_name,
                    "status": "failed",
                    "reason": "Failed to download from S3",
                })
                failed_count += 1
                continue

            file_content = download_result["content"]
            mime_type = doc.mime_type or download_result.get("content_type", "application/octet-stream")

            classification = classifier.classify_document(
                file_content=file_content,
                mime_type=mime_type,
                filename=doc.file_name or "unknown",
            )

            classifier.save_classification(
                db=db,
                document_id=doc.id,
                result=classification,
                organization_id=org_id,
            )

            results.append({
                "document_id": doc.id,
                "file_name": doc.file_name,
                "status": "classified",
                "predicted_type": classification.predicted_type,
                "confidence": classification.confidence,
            })
            classified_count += 1

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Batch classify failed for document %d: %s", doc.id, e)
            results.append({
                "document_id": doc.id,
                "file_name": doc.file_name,
                "status": "failed",
                "reason": str(e),
            })
            failed_count += 1

    try:
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to commit batch classifications for loan %d", loan_id)
        raise HTTPException(status_code=500, detail="Failed to save batch classifications")

    return {
        "loan_id": loan_id,
        "total_documents": len(documents),
        "classified": classified_count,
        "skipped": len(classified_doc_ids),
        "failed": failed_count,
        "results": results,
        "message": f"Classified {classified_count} documents, {failed_count} failed",
    }


# =============================================================================
# 17. GET /doc-intel/stats — Intelligence stats
# =============================================================================

@router.get("/doc-intel/stats")
async def get_intelligence_stats(
    days: int = Query(30, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get document intelligence statistics.

    Returns classification accuracy rate, most common doc types,
    average confidence scores, and call intelligence detection rate.
    """
    from sqlalchemy import text as sa_text

    org_id = _get_user_org_id(current_user)

    # Build org filter for raw queries
    org_filter = ""
    params: Dict[str, Any] = {"days": days}
    if org_id:
        org_filter = "AND organization_id = :org_id"
        params["org_id"] = org_id

    # Classification stats
    class_query = (
        "SELECT"
        " COUNT(*) AS total_classifications,"
        " AVG(prediction_confidence) AS avg_confidence,"
        " COUNT(CASE WHEN is_correct = true THEN 1 END) AS correct_count,"
        " COUNT(CASE WHEN is_correct = false THEN 1 END) AS incorrect_count,"
        " COUNT(CASE WHEN is_correct IS NOT NULL THEN 1 END) AS reviewed_count"
        " FROM ai_document_classifications"
        " WHERE created_at >= CURRENT_DATE - :days "
        + org_filter
    )
    class_stats = db.execute(
        sa_text(class_query),
        params,
    ).first()

    total_classifications = class_stats.total_classifications or 0 if class_stats else 0
    avg_confidence = round(float(class_stats.avg_confidence or 0), 1) if class_stats else 0
    reviewed = class_stats.reviewed_count or 0 if class_stats else 0
    correct = class_stats.correct_count or 0 if class_stats else 0
    accuracy_rate = round((correct / reviewed) * 100, 1) if reviewed > 0 else None

    # Most common doc types
    common_query = (
        "SELECT predicted_doc_type, COUNT(*) AS count"
        " FROM ai_document_classifications"
        " WHERE created_at >= CURRENT_DATE - :days "
        + org_filter
        + " GROUP BY predicted_doc_type"
        " ORDER BY count DESC"
        " LIMIT 10"
    )
    common_types = db.execute(
        sa_text(common_query),
        params,
    ).fetchall()

    # Call intelligence stats
    call_query = (
        "SELECT"
        " COUNT(*) AS total_needs,"
        " COUNT(CASE WHEN status = 'DETECTED' THEN 1 END) AS detected,"
        " COUNT(CASE WHEN status = 'CONFIRMED' THEN 1 END) AS confirmed,"
        " COUNT(CASE WHEN status = 'DISMISSED' THEN 1 END) AS dismissed,"
        " COUNT(CASE WHEN status = 'REQUEST_CREATED' THEN 1 END) AS request_created,"
        " AVG(detection_confidence) AS avg_detection_confidence"
        " FROM call_intel_document_needs"
        " WHERE created_at >= CURRENT_DATE - :days "
        + org_filter
    )
    call_stats = db.execute(
        sa_text(call_query),
        params,
    ).first()

    total_call_needs = call_stats.total_needs or 0 if call_stats else 0
    confirmed_or_created = (
        (call_stats.confirmed or 0) + (call_stats.request_created or 0)
    ) if call_stats else 0
    call_accuracy = round(
        (confirmed_or_created / total_call_needs) * 100, 1
    ) if total_call_needs > 0 else None

    return {
        "period_days": days,
        "classification": {
            "total": total_classifications,
            "avg_confidence": avg_confidence,
            "reviewed": reviewed,
            "correct": correct,
            "incorrect": (class_stats.incorrect_count or 0) if class_stats else 0,
            "accuracy_rate": accuracy_rate,
        },
        "common_doc_types": [
            {"doc_type": row.predicted_doc_type, "count": row.count}
            for row in common_types
        ],
        "call_intelligence": {
            "total_needs": total_call_needs,
            "detected": (call_stats.detected or 0) if call_stats else 0,
            "confirmed": (call_stats.confirmed or 0) if call_stats else 0,
            "dismissed": (call_stats.dismissed or 0) if call_stats else 0,
            "request_created": (call_stats.request_created or 0) if call_stats else 0,
            "avg_detection_confidence": round(
                float(call_stats.avg_detection_confidence or 0), 1
            ) if call_stats else 0,
            "detection_accuracy_rate": call_accuracy,
        },
    }
