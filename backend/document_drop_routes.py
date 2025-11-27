"""
Document Drop Routes
Backend API endpoints for drag-and-drop document upload and classification
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Initialize router
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

logger = logging.getLogger(__name__)

# =============================================================================
# Pydantic Schemas
# =============================================================================

class DocumentUploadResponse(BaseModel):
    """Response from document upload"""
    success: bool
    document_id: Optional[int] = None
    filename: str
    doc_type: str
    message: str


class DocumentClassifyResponse(BaseModel):
    """Response from document classification"""
    success: bool
    suggested_type: Optional[str] = None
    confidence: Optional[float] = None
    extracted_text: Optional[str] = None
    detected_entities: dict = {}


# =============================================================================
# Dependency Injection Setup
# =============================================================================

def get_db():
    """Get database session"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Document Classification with AI
# =============================================================================

async def classify_document_with_ai(filename: str, file_content: bytes) -> dict:
    """
    Use Claude AI to classify the document type
    """
    try:
        import anthropic

        # Get file extension
        ext = filename.lower().split('.')[-1] if '.' in filename else ''

        # For PDFs and images, we'd need OCR first
        # For now, classify based on filename patterns
        classification = classify_by_filename(filename)
        if classification["suggested_type"]:
            return classification

        # If we have text content, try AI classification
        if ext in ['txt', 'csv']:
            text_content = file_content.decode('utf-8', errors='ignore')[:2000]

            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            prompt = f"""Classify this mortgage document based on its content.

FILENAME: {filename}

CONTENT (first 2000 chars):
{text_content}

Classify into ONE of these types:
- PAY_STUB: Pay stubs, earnings statements
- W2: W-2 forms
- TAX_RETURN: Tax returns (1040, etc.)
- BANK_STATEMENT: Bank statements
- INVESTMENT_STATEMENT: Investment/retirement account statements
- DRIVERS_LICENSE: Driver's license
- PASSPORT: Passport
- PURCHASE_CONTRACT: Real estate purchase contracts
- APPRAISAL: Property appraisals
- TITLE_REPORT: Title reports, title insurance
- INSURANCE_DECLARATION: Homeowner's insurance declarations
- CREDIT_REPORT: Credit reports
- LOAN_ESTIMATE: Loan estimates
- CLOSING_DISCLOSURE: Closing disclosures
- OTHER: Cannot determine

Respond with JSON only:
{{"suggested_type": "TYPE_HERE", "confidence": 0.0-1.0, "reasoning": "why"}}"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            import json
            response_text = response.content[0].text
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response_text[json_start:json_end])
                return {
                    "success": True,
                    "suggested_type": result.get("suggested_type"),
                    "confidence": result.get("confidence", 0.7)
                }

    except Exception as e:
        logger.error(f"AI classification error: {e}")

    # Fallback to filename-based classification
    return classify_by_filename(filename)


def classify_by_filename(filename: str) -> dict:
    """Classify document based on filename patterns"""
    filename_lower = filename.lower()

    patterns = {
        'PAY_STUB': ['paystub', 'pay_stub', 'paycheck', 'earnings', 'wage'],
        'W2': ['w2', 'w-2'],
        'TAX_RETURN': ['tax', '1040', 'return', 'irs'],
        'BANK_STATEMENT': ['bank', 'statement', 'checking', 'savings'],
        'INVESTMENT_STATEMENT': ['investment', '401k', 'ira', 'brokerage', 'fidelity', 'vanguard'],
        'DRIVERS_LICENSE': ['driver', 'license', 'dl', 'id card'],
        'PASSPORT': ['passport'],
        'PURCHASE_CONTRACT': ['contract', 'purchase', 'agreement', 'offer'],
        'APPRAISAL': ['appraisal', 'valuation'],
        'TITLE_REPORT': ['title', 'commitment'],
        'INSURANCE_DECLARATION': ['insurance', 'declaration', 'policy', 'hoi'],
        'CREDIT_REPORT': ['credit', 'experian', 'equifax', 'transunion', 'fico'],
        'LOAN_ESTIMATE': ['loan estimate', 'le', 'good faith'],
        'CLOSING_DISCLOSURE': ['closing disclosure', 'cd', 'hud'],
    }

    for doc_type, keywords in patterns.items():
        if any(kw in filename_lower for kw in keywords):
            return {
                "success": True,
                "suggested_type": doc_type,
                "confidence": 0.7
            }

    return {
        "success": True,
        "suggested_type": None,
        "confidence": 0
    }


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    borrower_id: Optional[int] = Form(None),
    loan_id: Optional[int] = Form(None),
    doc_type: str = Form("OTHER"),
    db: Session = Depends(get_db)
):
    """
    Upload a document and attach to borrower/loan
    """
    try:
        from main import Document, DocumentType, DocumentCategory

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Generate unique filename
        ext = file.filename.split('.')[-1] if '.' in file.filename else ''
        unique_filename = f"{uuid.uuid4().hex[:12]}_{file.filename}"

        # Determine storage path (in production, upload to S3/GCS)
        storage_path = f"documents/{datetime.now().strftime('%Y/%m/%d')}/{unique_filename}"

        # Map string doc_type to enum
        try:
            doc_type_enum = DocumentType(doc_type)
        except ValueError:
            doc_type_enum = DocumentType.OTHER

        # Determine category based on doc type
        category_mapping = {
            'PAY_STUB': 'INCOME',
            'W2': 'INCOME',
            'TAX_RETURN': 'INCOME',
            'BANK_STATEMENT': 'ASSETS',
            'INVESTMENT_STATEMENT': 'ASSETS',
            'DRIVERS_LICENSE': 'IDENTITY',
            'PASSPORT': 'IDENTITY',
            'PURCHASE_CONTRACT': 'PROPERTY',
            'APPRAISAL': 'PROPERTY',
            'TITLE_REPORT': 'PROPERTY',
            'INSURANCE_DECLARATION': 'PROPERTY',
            'CREDIT_REPORT': 'CREDIT',
            'LOAN_ESTIMATE': 'DISCLOSURES',
            'CLOSING_DISCLOSURE': 'DISCLOSURES',
        }

        try:
            doc_category = DocumentCategory(category_mapping.get(doc_type, 'OTHER'))
        except ValueError:
            doc_category = DocumentCategory.OTHER

        # Create document record
        doc = Document(
            doc_type=doc_type_enum,
            doc_category=doc_category,
            filename=unique_filename,
            original_filename=file.filename,
            file_size=file_size,
            mime_type=file.content_type,
            file_location=storage_path,
            source="DOCUMENT_DROP",
            status="active",
            borrower_id=borrower_id,
            loan_id=loan_id
        )

        db.add(doc)
        db.commit()
        db.refresh(doc)

        # In production, upload file to cloud storage here
        # For now, we just store the metadata

        return DocumentUploadResponse(
            success=True,
            document_id=doc.id,
            filename=file.filename,
            doc_type=doc_type,
            message=f"Document uploaded successfully"
        )

    except Exception as e:
        logger.error(f"Document upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify", response_model=DocumentClassifyResponse)
async def classify_document(
    file: UploadFile = File(...)
):
    """
    Classify a document using AI without uploading
    """
    try:
        content = await file.read()

        result = await classify_document_with_ai(file.filename, content)

        return DocumentClassifyResponse(
            success=result.get("success", True),
            suggested_type=result.get("suggested_type"),
            confidence=result.get("confidence"),
            extracted_text=None,  # Would include OCR text in production
            detected_entities={}
        )

    except Exception as e:
        logger.error(f"Document classification error: {e}")
        return DocumentClassifyResponse(
            success=False,
            suggested_type=None,
            confidence=None
        )


@router.get("/")
async def get_documents(
    borrower_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get documents for a borrower or loan
    """
    try:
        from main import Document

        query = db.query(Document).filter(Document.status == "active")

        if borrower_id:
            query = query.filter(Document.borrower_id == borrower_id)
        if loan_id:
            query = query.filter(Document.loan_id == loan_id)

        documents = query.order_by(Document.uploaded_at.desc()).limit(100).all()

        return {
            "documents": [
                {
                    "id": doc.id,
                    "filename": doc.original_filename or doc.filename,
                    "doc_type": doc.doc_type.value if doc.doc_type else "OTHER",
                    "doc_category": doc.doc_category.value if doc.doc_category else "OTHER",
                    "file_size": doc.file_size,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                    "borrower_id": doc.borrower_id,
                    "loan_id": doc.loan_id
                }
                for doc in documents
            ]
        }

    except Exception as e:
        logger.error(f"Get documents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "document-drop",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
