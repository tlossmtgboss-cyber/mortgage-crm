"""
AI Knowledge Base Routes

Endpoints for managing the AI knowledge base including CRUD operations
for knowledge entries and document uploads.
"""

import os
import io
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from openai import OpenAI

from db import get_db

router = APIRouter(prefix="/api/v1/ai/knowledge-base", tags=["AI Knowledge Base"])
logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class KnowledgeBaseCreate(BaseModel):
    title: str
    category: str  # loan_products, compliance, underwriting, sales_scripts, company_policies, workflows, other
    content: str
    summary: Optional[str] = None
    source_type: Optional[str] = "manual"
    source_url: Optional[str] = None
    source_filename: Optional[str] = None
    file_type: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = 5


class KnowledgeBaseUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    title: str
    category: str
    content: str
    summary: Optional[str]
    source_type: str
    source_url: Optional[str]
    source_filename: Optional[str]
    file_type: Optional[str]
    tags: Optional[List[str]]
    is_active: bool
    priority: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Dependencies - Import from main at runtime to avoid circular imports
# =============================================================================

def get_current_user_flexible_dep():
    """Get current user flexible - imports from main at runtime"""
    import main
    return main.get_current_user_flexible


def get_models():
    """Get model classes from main at runtime to avoid circular imports"""
    import main
    return {
        "AIKnowledgeBase": main.AIKnowledgeBase,
        "User": main.User,
    }


# =============================================================================
# AI KNOWLEDGE BASE ENDPOINTS
# =============================================================================

@router.get("")
async def list_knowledge_base(
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_active: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """List all knowledge base entries with optional filtering"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    query = db.query(AIKnowledgeBase).filter(AIKnowledgeBase.is_active == is_active)

    if category:
        query = query.filter(AIKnowledgeBase.category == category)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                AIKnowledgeBase.title.ilike(search_term),
                AIKnowledgeBase.content.ilike(search_term),
                AIKnowledgeBase.summary.ilike(search_term)
            )
        )

    entries = query.order_by(AIKnowledgeBase.priority.desc(), AIKnowledgeBase.created_at.desc()).all()

    return [{
        "id": e.id,
        "title": e.title,
        "category": e.category,
        "content": e.content[:500] + "..." if len(e.content) > 500 else e.content,  # Truncate for list view
        "summary": e.summary,
        "source_type": e.source_type,
        "source_filename": e.source_filename,
        "tags": e.tags or [],
        "is_active": e.is_active,
        "priority": e.priority,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None
    } for e in entries]


@router.get("/categories")
async def get_knowledge_categories(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Get all available knowledge base categories with counts"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    categories = [
        {"id": "loan_products", "name": "Loan Products", "description": "Conventional, FHA, VA, USDA, Jumbo loan guidelines"},
        {"id": "compliance", "name": "Compliance & Regulations", "description": "TRID, RESPA, HMDA, state regulations"},
        {"id": "underwriting", "name": "Underwriting Guidelines", "description": "DTI, LTV, credit requirements, income docs"},
        {"id": "sales_scripts", "name": "Sales & Scripts", "description": "Objection handling, follow-up scripts, talking points"},
        {"id": "company_policies", "name": "Company Policies", "description": "Internal procedures, pricing, guidelines"},
        {"id": "workflows", "name": "Workflows & Processes", "description": "Stage definitions, checklists, procedures"},
        {"id": "market_intel", "name": "Market Intelligence", "description": "Rate trends, market conditions, economic indicators"},
        {"id": "other", "name": "Other", "description": "Miscellaneous knowledge and resources"}
    ]

    # Get counts for each category
    for cat in categories:
        count = db.query(AIKnowledgeBase).filter(
            AIKnowledgeBase.category == cat["id"],
            AIKnowledgeBase.is_active == True
        ).count()
        cat["count"] = count

    return categories


@router.get("/{entry_id}")
async def get_knowledge_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Get a single knowledge base entry with full content"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    entry = db.query(AIKnowledgeBase).filter(AIKnowledgeBase.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    return {
        "id": entry.id,
        "title": entry.title,
        "category": entry.category,
        "content": entry.content,
        "summary": entry.summary,
        "source_type": entry.source_type,
        "source_url": entry.source_url,
        "source_filename": entry.source_filename,
        "file_type": entry.file_type,
        "tags": entry.tags or [],
        "is_active": entry.is_active,
        "priority": entry.priority,
        "last_reviewed": entry.last_reviewed.isoformat() if entry.last_reviewed else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None
    }


@router.post("")
async def create_knowledge_entry(
    entry: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Create a new knowledge base entry"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    # Generate summary if not provided using AI
    summary = entry.summary
    if not summary and len(entry.content) > 200:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Summarize this content in 1-2 sentences for quick reference. Be concise."},
                    {"role": "user", "content": entry.content[:3000]}
                ],
                max_tokens=100
            )
            summary = response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Could not generate summary: {e}")
            summary = entry.content[:200] + "..."

    new_entry = AIKnowledgeBase(
        title=entry.title,
        category=entry.category,
        content=entry.content,
        summary=summary,
        source_type=entry.source_type,
        source_url=entry.source_url,
        source_filename=entry.source_filename,
        file_type=entry.file_type,
        tags=entry.tags,
        priority=entry.priority or 5,
        created_by=current_user.id,
        organization_id=getattr(current_user, 'organization_id', 1)
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return {"id": new_entry.id, "message": "Knowledge entry created successfully"}


@router.put("/{entry_id}")
async def update_knowledge_entry(
    entry_id: int,
    update: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Update an existing knowledge base entry"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    entry = db.query(AIKnowledgeBase).filter(AIKnowledgeBase.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    update_data = update.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(entry, key, value)

    db.commit()
    db.refresh(entry)

    return {"id": entry.id, "message": "Knowledge entry updated successfully"}


@router.delete("/{entry_id}")
async def delete_knowledge_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Soft delete a knowledge base entry"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    entry = db.query(AIKnowledgeBase).filter(AIKnowledgeBase.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    entry.is_active = False
    db.commit()

    return {"message": "Knowledge entry deleted successfully"}


@router.post("/upload")
async def upload_knowledge_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    priority: int = Form(5),
    tags: str = Form(""),  # Comma-separated tags
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Upload a document to the knowledge base (PDF, DOCX, TXT)"""
    models = get_models()
    AIKnowledgeBase = models["AIKnowledgeBase"]

    # Validate file type
    allowed_types = [".pdf", ".docx", ".doc", ".txt", ".md"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Supported: {', '.join(allowed_types)}")

    # Read file content
    content = await file.read()
    text_content = ""

    try:
        if file_ext == ".txt" or file_ext == ".md":
            text_content = content.decode("utf-8")
        elif file_ext == ".pdf":
            # Use PyPDF2 or similar to extract text
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                text_content = "\n".join([page.extract_text() for page in pdf_reader.pages])
            except ImportError:
                # Fallback if PyPDF2 not available
                text_content = f"[PDF content from {file.filename} - install PyPDF2 to extract text]"
        elif file_ext in [".docx", ".doc"]:
            try:
                import docx
                doc = docx.Document(io.BytesIO(content))
                text_content = "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                text_content = f"[DOCX content from {file.filename} - install python-docx to extract text]"
    except Exception as e:
        logger.error(f"Error extracting document content: {e}")
        text_content = f"[Could not extract content from {file.filename}]"

    # Generate summary using AI
    summary = None
    if text_content and len(text_content) > 200:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Summarize this document in 2-3 sentences for quick reference. Be concise."},
                    {"role": "user", "content": text_content[:4000]}
                ],
                max_tokens=150
            )
            summary = response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Could not generate summary: {e}")

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Create knowledge entry
    new_entry = AIKnowledgeBase(
        title=title,
        category=category,
        content=text_content,
        summary=summary,
        source_type="document_upload",
        source_filename=file.filename,
        file_type=file_ext.replace(".", ""),
        tags=tag_list,
        priority=priority,
        created_by=current_user.id,
        organization_id=getattr(current_user, 'organization_id', 1)
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return {
        "id": new_entry.id,
        "message": f"Document '{file.filename}' uploaded and processed successfully",
        "summary": summary,
        "content_length": len(text_content)
    }
