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
        from agents.anthropic_client import get_anthropic_client

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

            client = get_anthropic_client()

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
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    try:
        from database.enums import DocumentType, DocumentCategory
        from database.models import Document

        # Read file content with size limit
        content = await file.read(MAX_FILE_SIZE + 1)
        file_size = len(content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large. Maximum size is 50 MB.")

        # Generate unique filename with sanitization
        import re as _re
        raw_name = os.path.basename(file.filename or 'upload')
        safe_name = _re.sub(r'[^\w\.\-]', '_', raw_name)[:100]
        ext = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else ''
        unique_filename = f"{uuid.uuid4().hex[:12]}_{safe_name}"

        # Determine storage path (in production, upload to S3/GCS)
        storage_path = f"documents/{datetime.now().strftime('%Y/%m/%d')}/{unique_filename}"

        # Map incoming doc_type to DocumentType enum
        doc_type_mapping = {
            'PAY_STUB': 'PAYSTUB',
            'PAYSTUB': 'PAYSTUB',
            'W2': 'W2',
            'TAX_RETURN': 'TAX_RETURN_1040',
            'BANK_STATEMENT': 'BANK_STATEMENT',
            'INVESTMENT_STATEMENT': 'INVESTMENT_STATEMENT',
            'DRIVERS_LICENSE': 'DRIVERS_LICENSE',
            'PASSPORT': 'PASSPORT',
            'PURCHASE_CONTRACT': 'PURCHASE_CONTRACT',
            'APPRAISAL': 'APPRAISAL',
            'TITLE_REPORT': 'TITLE_COMMITMENT',
            'INSURANCE_DECLARATION': 'HOMEOWNERS_INSURANCE',
            'CREDIT_REPORT': 'CREDIT_REPORT',
            'LOAN_ESTIMATE': 'LOAN_ESTIMATE',
            'CLOSING_DISCLOSURE': 'CLOSING_DISCLOSURE',
            'OTHER': 'MISC',
        }

        mapped_type = doc_type_mapping.get(doc_type, 'MISC')
        try:
            doc_type_enum = DocumentType[mapped_type]
        except (KeyError, ValueError):
            doc_type_enum = DocumentType.MISC

        # Determine category based on doc type
        category_mapping = {
            'PAYSTUB': 'INCOME',
            'W2': 'INCOME',
            'TAX_RETURN_1040': 'INCOME',
            'TAX_RETURN_1099': 'INCOME',
            'BANK_STATEMENT': 'ASSETS',
            'INVESTMENT_STATEMENT': 'ASSETS',
            'RETIREMENT_STATEMENT': 'ASSETS',
            'DRIVERS_LICENSE': 'IDENTITY',
            'PASSPORT': 'IDENTITY',
            'PURCHASE_CONTRACT': 'PROPERTY',
            'APPRAISAL': 'PROPERTY',
            'TITLE_COMMITMENT': 'PROPERTY',
            'HOMEOWNERS_INSURANCE': 'PROPERTY',
            'CREDIT_REPORT': 'CREDIT',
            'LOAN_ESTIMATE': 'DISCLOSURES',
            'CLOSING_DISCLOSURE': 'DISCLOSURES',
        }

        category_name = category_mapping.get(mapped_type, 'MISC')
        try:
            doc_category = DocumentCategory[category_name]
        except (KeyError, ValueError):
            # Default to INCOME if not found
            doc_category = DocumentCategory.INCOME

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

        # TRIGGER: If this is a purchase contract, initiate portal automation
        if doc_type_enum.name == 'PURCHASE_CONTRACT' and loan_id:
            try:
                from services.contract_portal_automation_service import ContractPortalAutomationService
                from services.notification_service import NotificationService

                notification_service = NotificationService()
                automation_service = ContractPortalAutomationService(db, notification_service)
                automation_result = automation_service.process_contract_received(
                    loan_id=loan_id,
                    triggered_by="document_upload"
                )
                logger.info(f"Contract portal automation triggered for loan {loan_id}: {automation_result}")
            except Exception as automation_error:
                # Don't fail the upload if automation fails
                logger.error(f"Contract portal automation failed for loan {loan_id}: {automation_error}")

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/classify", response_model=DocumentClassifyResponse)
async def classify_document(
    file: UploadFile = File(...)
):
    """
    Classify a document using AI without uploading
    """
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    try:
        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")

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
        from database.models import Document

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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "document-drop",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
