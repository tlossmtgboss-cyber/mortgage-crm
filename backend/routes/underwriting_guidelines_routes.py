"""
Underwriting Guidelines API Routes

Endpoints for uploading, managing, and querying underwriting guidelines
that the AI Underwriter agent can reference.
"""

import os
import logging
from typing import List, Optional
from datetime import datetime, date
import uuid
import io

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from models.call_monitoring_models import (
    UnderwritingGuideline,
    GuidelineSection,
    GuidelineType,
    GuidelineCategory,
    GuidelineUploadRequest,
    GuidelineUpdateRequest,
    GuidelineTextInput,
    GuidelineResponse,
    GuidelineDetailResponse,
    GuidelineSectionResponse,
    GuidelineSearchRequest,
    GuidelineSearchResult,
)

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/underwriting-guidelines", tags=["Underwriting Guidelines"],
    dependencies=[Depends(_get_current_user())],
)

# Storage configuration
UPLOAD_DIR = os.getenv("GUIDELINE_UPLOAD_DIR", "/tmp/guidelines")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".doc", ".html", ".md"}


# =============================================================================
# GUIDELINE UPLOAD ENDPOINTS
# =============================================================================

@router.post("/upload", response_model=GuidelineResponse)
async def upload_guideline(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    guideline_type: str = Form(...),
    description: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    loan_program: Optional[str] = Form("all"),
    investor_name: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    expiration_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated
    db: Session = Depends(get_db),
):
    """
    Upload a guideline document (PDF, TXT, DOCX).

    The document will be processed in the background to extract text
    and key points that the AI can reference.
    """
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not allowed. Allowed: {ALLOWED_EXTENSIONS}"
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Create upload directory if needed
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Generate unique filename — sanitize original filename to prevent path traversal
    import re as _re
    file_id = str(uuid.uuid4())[:8]
    safe_original = os.path.basename(file.filename or "upload")
    safe_original = _re.sub(r'[^a-zA-Z0-9._-]', '_', safe_original)  # Only allow safe chars
    stored_filename = f"{file_id}_{safe_original}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    # Parse dates
    eff_date = datetime.strptime(effective_date, "%Y-%m-%d").date() if effective_date else None
    exp_date = datetime.strptime(expiration_date, "%Y-%m-%d").date() if expiration_date else None

    # Create guideline record
    guideline = UnderwritingGuideline(
        id=uuid.uuid4(),
        name=name,
        description=description,
        version=version,
        guideline_type=guideline_type,
        category=category,
        loan_program=loan_program,
        investor_name=investor_name,
        source_file_name=file.filename,
        source_file_path=file_path,
        source_file_type=file_ext.replace(".", ""),
        source_file_size=len(content),
        effective_date=eff_date,
        expiration_date=exp_date,
        tags=tag_list,
        is_active=True,
        is_processed=False,
    )

    db.add(guideline)
    db.commit()
    db.refresh(guideline)

    # Process in background (extract text, generate summary)
    background_tasks.add_task(
        process_guideline_document,
        str(guideline.id),
        file_path,
        file_ext
    )

    logger.info(f"Guideline uploaded: {guideline.id} - {name}")

    return _to_guideline_response(guideline)


@router.post("/text", response_model=GuidelineResponse)
async def add_guideline_text(
    request: GuidelineTextInput,
    db: Session = Depends(get_db),
):
    """
    Add guideline content directly as text.

    Use this for manually entering guideline text or pasting from documents.
    """
    guideline = UnderwritingGuideline(
        id=uuid.uuid4(),
        name=request.name,
        description=request.description,
        guideline_type=request.guideline_type.value,
        category=request.category.value if request.category else None,
        loan_program=request.loan_program,
        full_text=request.content,
        structured_rules=request.structured_rules or {},
        tags=request.tags or [],
        is_active=True,
        is_processed=True,  # Already have text
    )

    db.add(guideline)
    db.commit()
    db.refresh(guideline)

    # Extract key points from the text
    try:
        from services.call_monitoring.guidelines_service import extract_key_points
        key_points = await extract_key_points(request.content)
        guideline.key_points = key_points
        db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Could not extract key points: {e}")

    logger.info(f"Guideline text added: {guideline.id} - {request.name}")

    return _to_guideline_response(guideline)


# =============================================================================
# GUIDELINE MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("", response_model=List[GuidelineResponse])
async def list_guidelines(
    guideline_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    loan_program: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """List all guidelines with optional filters."""
    query = db.query(UnderwritingGuideline)

    if guideline_type:
        query = query.filter(UnderwritingGuideline.guideline_type == guideline_type)
    if category:
        query = query.filter(UnderwritingGuideline.category == category)
    if loan_program:
        query = query.filter(
            or_(
                UnderwritingGuideline.loan_program == loan_program,
                UnderwritingGuideline.loan_program == "all"
            )
        )
    if is_active is not None:
        query = query.filter(UnderwritingGuideline.is_active == is_active)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                UnderwritingGuideline.name.ilike(search_term),
                UnderwritingGuideline.description.ilike(search_term),
                UnderwritingGuideline.tags.any(search)
            )
        )

    guidelines = query.order_by(UnderwritingGuideline.created_at.desc()).offset(offset).limit(limit).all()

    return [_to_guideline_response(g) for g in guidelines]


@router.get("/{guideline_id}", response_model=GuidelineDetailResponse)
async def get_guideline(
    guideline_id: str,
    db: Session = Depends(get_db),
):
    """Get detailed guideline by ID including full text and structured rules."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    return _to_guideline_detail_response(guideline)


@router.put("/{guideline_id}", response_model=GuidelineResponse)
async def update_guideline(
    guideline_id: str,
    request: GuidelineUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update guideline metadata."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    update_data = request.dict(exclude_unset=True)

    # Handle date conversions
    if "effective_date" in update_data and update_data["effective_date"]:
        update_data["effective_date"] = datetime.strptime(update_data["effective_date"], "%Y-%m-%d").date()
    if "expiration_date" in update_data and update_data["expiration_date"]:
        update_data["expiration_date"] = datetime.strptime(update_data["expiration_date"], "%Y-%m-%d").date()

    # Handle enum conversions
    if "guideline_type" in update_data and update_data["guideline_type"]:
        update_data["guideline_type"] = update_data["guideline_type"].value
    if "category" in update_data and update_data["category"]:
        update_data["category"] = update_data["category"].value

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_data.items():
        if field not in _protected:
            setattr(guideline, field, value)

    db.commit()
    db.refresh(guideline)

    return _to_guideline_response(guideline)


@router.delete("/{guideline_id}")
async def delete_guideline(
    guideline_id: str,
    db: Session = Depends(get_db),
):
    """Delete a guideline."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    # Delete file if exists
    if guideline.source_file_path and os.path.exists(guideline.source_file_path):
        try:
            os.remove(guideline.source_file_path)
        except SQLAlchemyError as e:
            logger.warning(f"Could not delete file: {e}")

    # Delete sections
    db.query(GuidelineSection).filter(GuidelineSection.guideline_id == guideline_id).delete()

    # Delete guideline
    db.delete(guideline)
    db.commit()

    return {"message": "Guideline deleted", "id": guideline_id}


@router.post("/{guideline_id}/reprocess")
async def reprocess_guideline(
    guideline_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Reprocess a guideline to re-extract text and generate new summary/key points."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    if not guideline.source_file_path:
        raise HTTPException(status_code=400, detail="No source file to reprocess")

    # Reset processing status
    guideline.is_processed = False
    db.commit()

    # Reprocess in background
    background_tasks.add_task(
        process_guideline_document,
        str(guideline.id),
        guideline.source_file_path,
        f".{guideline.source_file_type}"
    )

    return {"message": "Reprocessing started", "id": guideline_id}


# =============================================================================
# GUIDELINE SEARCH ENDPOINTS
# =============================================================================

@router.post("/search", response_model=List[GuidelineSearchResult])
async def search_guidelines(
    request: GuidelineSearchRequest,
    db: Session = Depends(get_db),
):
    """
    Search guidelines by keyword/phrase.

    Returns relevant guideline sections matching the query.
    """
    from services.call_monitoring.guidelines_service import search_guidelines as do_search

    results = await do_search(
        db=db,
        query=request.query,
        loan_program=request.loan_program,
        category=request.category,
        guideline_type=request.guideline_type,
        limit=request.limit
    )

    return results


@router.get("/search/quick")
async def quick_search(
    q: str = Query(..., min_length=2),
    loan_program: Optional[str] = Query(None),
    limit: int = Query(5, le=20),
    db: Session = Depends(get_db),
):
    """Quick search for guidelines (used by autocomplete)."""
    from services.call_monitoring.guidelines_service import search_guidelines as do_search

    results = await do_search(
        db=db,
        query=q,
        loan_program=loan_program,
        limit=limit
    )

    return results


# =============================================================================
# GUIDELINE SECTIONS ENDPOINTS
# =============================================================================

@router.get("/{guideline_id}/sections", response_model=List[GuidelineSectionResponse])
async def get_guideline_sections(
    guideline_id: str,
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get all sections from a guideline."""
    query = db.query(GuidelineSection).filter(
        GuidelineSection.guideline_id == guideline_id
    )

    if category:
        query = query.filter(GuidelineSection.category == category)

    sections = query.order_by(GuidelineSection.position_start).all()

    return [_to_section_response(s) for s in sections]


@router.post("/{guideline_id}/sections")
async def add_guideline_section(
    guideline_id: str,
    section_number: str = Form(None),
    section_title: str = Form(...),
    content: str = Form(...),
    category: Optional[str] = Form(None),
    topics: Optional[str] = Form(None),  # Comma-separated
    db: Session = Depends(get_db),
):
    """Manually add a section to a guideline."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    topic_list = [t.strip() for t in topics.split(",")] if topics else []

    section = GuidelineSection(
        id=uuid.uuid4(),
        guideline_id=guideline_id,
        section_number=section_number,
        section_title=section_title,
        content=content,
        category=category,
        topics=topic_list,
    )

    db.add(section)
    db.commit()
    db.refresh(section)

    return _to_section_response(section)


# =============================================================================
# STRUCTURED RULES ENDPOINTS
# =============================================================================

@router.get("/{guideline_id}/rules")
async def get_structured_rules(
    guideline_id: str,
    db: Session = Depends(get_db),
):
    """Get structured rules from a guideline."""
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    return guideline.structured_rules or {}


@router.put("/{guideline_id}/rules")
async def update_structured_rules(
    guideline_id: str,
    rules: dict,
    db: Session = Depends(get_db),
):
    """
    Update structured rules for a guideline.

    Example rules structure:
    ```json
    {
        "min_credit_score": {"standard": 620, "high_balance": 680},
        "max_dti": {"standard": 45, "with_compensating": 50},
        "max_ltv": {"purchase": 97, "cash_out": 80},
        "waiting_periods": {"bankruptcy": "4 years", "foreclosure": "7 years"}
    }
    ```
    """
    guideline = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.id == guideline_id
    ).first()

    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")

    guideline.structured_rules = rules
    db.commit()

    return {"message": "Rules updated", "rules": rules}


# =============================================================================
# AGGREGATE RULES ENDPOINT
# =============================================================================

@router.get("/aggregate/rules")
async def get_aggregate_rules(
    loan_program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get aggregated structured rules from all active guidelines.

    Useful for the AI to quickly look up requirements.
    Rules are merged with more specific guidelines (investor, company)
    overriding general (agency) guidelines.
    """
    query = db.query(UnderwritingGuideline).filter(
        UnderwritingGuideline.is_active == True,
        UnderwritingGuideline.structured_rules != None
    )

    if loan_program:
        query = query.filter(
            or_(
                UnderwritingGuideline.loan_program == loan_program,
                UnderwritingGuideline.loan_program == "all"
            )
        )

    # Order by priority: agency < investor < company (company overrides)
    type_order = {"agency": 1, "state": 2, "investor": 3, "company": 4, "product": 5}
    guidelines = query.all()
    guidelines.sort(key=lambda g: type_order.get(g.guideline_type, 0))

    # Merge rules
    merged_rules = {}
    for guideline in guidelines:
        if guideline.structured_rules:
            _deep_merge(merged_rules, guideline.structured_rules)

    return {
        "loan_program": loan_program,
        "rules": merged_rules,
        "sources": [
            {"name": g.name, "type": g.guideline_type}
            for g in guidelines if g.structured_rules
        ]
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _to_guideline_response(guideline: UnderwritingGuideline) -> GuidelineResponse:
    """Convert model to response schema."""
    return GuidelineResponse(
        id=str(guideline.id),
        name=guideline.name,
        description=guideline.description,
        version=guideline.version,
        guideline_type=guideline.guideline_type,
        category=guideline.category,
        loan_program=guideline.loan_program,
        investor_name=guideline.investor_name,
        source_file_name=guideline.source_file_name,
        is_active=guideline.is_active,
        is_processed=guideline.is_processed,
        effective_date=str(guideline.effective_date) if guideline.effective_date else None,
        expiration_date=str(guideline.expiration_date) if guideline.expiration_date else None,
        tags=guideline.tags,
        key_points=guideline.key_points,
        created_at=guideline.created_at,
        updated_at=guideline.updated_at,
    )


def _to_guideline_detail_response(guideline: UnderwritingGuideline) -> GuidelineDetailResponse:
    """Convert model to detailed response schema."""
    base = _to_guideline_response(guideline)
    return GuidelineDetailResponse(
        **base.dict(),
        full_text=guideline.full_text,
        summary=guideline.summary,
        structured_rules=guideline.structured_rules,
        keywords=guideline.keywords,
    )


def _to_section_response(section: GuidelineSection) -> GuidelineSectionResponse:
    """Convert model to response schema."""
    return GuidelineSectionResponse(
        id=str(section.id),
        guideline_id=str(section.guideline_id),
        section_number=section.section_number,
        section_title=section.section_title,
        content=section.content,
        summary=section.summary,
        category=section.category,
        topics=section.topics,
        page_number=section.page_number,
    )


def _deep_merge(base: dict, override: dict):
    """Deep merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


async def process_guideline_document(guideline_id: str, file_path: str, file_ext: str):
    """Background task to process uploaded guideline document."""
    from services.call_monitoring.guidelines_service import process_guideline
    await process_guideline(guideline_id, file_path, file_ext)
