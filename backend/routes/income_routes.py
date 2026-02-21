"""
Income API Routes

Endpoints for income extraction, calculation, and management.
Supports the AI-powered income extraction system.
"""

import logging
import os
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.income_models import (
    IncomeSource, PaystubExtraction, Employment,
    IncomeType, IncomeCalculationMethod, IncomeVerificationStatus, PayrollFrequency
)
from services.smart_docs.document_data_extractor import get_document_data_extractor
from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
from services.income import get_income_calculation_service
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from main import get_current_user_flexible
    user = await get_current_user_flexible(token=credentials.credentials, request=None, db=db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


router = APIRouter(
    prefix="/api/v1/income",
    tags=["Income"],
    dependencies=[Depends(_require_auth)],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class IncomeSourceCreate(BaseModel):
    """Request model for creating an income source."""
    borrower_id: int
    loan_id: int
    income_type: str
    source_name: Optional[str] = None
    source_description: Optional[str] = None
    is_primary: bool = False
    employment_id: Optional[int] = None


class IncomeSourceUpdate(BaseModel):
    """Request model for updating an income source."""
    source_name: Optional[str] = None
    source_description: Optional[str] = None
    monthly_qualifying_income: Optional[float] = None
    annual_qualifying_income: Optional[float] = None
    calculation_method: Optional[str] = None
    verification_status: Optional[str] = None
    verification_notes: Optional[str] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None


class IncomeSourceResponse(BaseModel):
    """Response model for income source."""
    id: int
    borrower_id: int
    loan_id: int
    income_type: str
    source_name: Optional[str]
    is_primary: bool
    is_active: bool
    monthly_qualifying_income: Optional[float]
    annual_qualifying_income: Optional[float]
    calculation_method: Optional[str]
    verification_status: str
    trending_direction: Optional[str]
    declining_income_flag: bool
    variable_income_flag: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaystubExtractionResponse(BaseModel):
    """Response model for paystub extraction."""
    id: int
    document_id: int
    employer_name: Optional[str]
    employee_name: Optional[str]
    pay_date: Optional[str]
    pay_frequency: Optional[str]
    gross_pay: Optional[float]
    net_pay: Optional[float]
    ytd_gross: Optional[float]
    calculated_annual_income: Optional[float]
    calculated_monthly_income: Optional[float]
    expires_at: Optional[str]
    is_expired: bool
    extraction_confidence: Optional[int]
    applied_to_profile: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ApplyExtractionRequest(BaseModel):
    """Request model for applying extracted data."""
    extraction_id: int
    fields_to_apply: List[str]  # List of field names to apply
    create_employment: bool = True
    create_income_source: bool = True


class ExtractIncomeFromDocumentsRequest(BaseModel):
    """Request model for extracting income from documents."""
    loan_id: int
    borrower_id: int
    income_type: str


class IncomeSummaryResponse(BaseModel):
    """Response model for income summary."""
    borrower_id: int
    loan_id: int
    total_monthly_income: float
    total_annual_income: float
    source_count: int
    verified_count: int
    has_declining_income: bool
    sources: List[IncomeSourceResponse]


# =============================================================================
# INCOME SOURCE ENDPOINTS
# =============================================================================

@router.get("/borrowers/{borrower_id}/sources")
async def get_income_sources(
    borrower_id: int,
    loan_id: Optional[int] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """Get all income sources for a borrower."""
    query = db.query(IncomeSource).filter(IncomeSource.borrower_id == borrower_id)

    if loan_id:
        query = query.filter(IncomeSource.loan_id == loan_id)
    if active_only:
        query = query.filter(IncomeSource.is_active == True)

    sources = query.order_by(IncomeSource.is_primary.desc(), IncomeSource.created_at).all()

    return {
        "borrower_id": borrower_id,
        "count": len(sources),
        "sources": [_format_income_source(s) for s in sources],
    }


@router.post("/borrowers/{borrower_id}/sources")
async def create_income_source(
    borrower_id: int,
    request: IncomeSourceCreate,
    db: Session = Depends(get_db),
):
    """Create a new income source."""
    try:
        income_type = IncomeType(request.income_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid income type: {request.income_type}")

    source = IncomeSource(
        borrower_id=borrower_id,
        loan_id=request.loan_id,
        income_type=income_type,
        source_name=request.source_name,
        source_description=request.source_description,
        is_primary=request.is_primary,
        employment_id=request.employment_id,
        verification_status=IncomeVerificationStatus.PENDING,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return _format_income_source(source)


@router.get("/loans/{loan_id}/sources")
async def get_loan_income_sources(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """
    Get all income sources for a loan.
    Returns sources with their current data for populating the income calculator.
    """
    sources = db.query(IncomeSource).filter(
        IncomeSource.loan_id == loan_id,
        IncomeSource.is_active == True
    ).order_by(IncomeSource.is_primary.desc(), IncomeSource.created_at).all()

    # Map IncomeType enum to frontend income type IDs
    type_mapping = {
        IncomeType.W2_EMPLOYMENT: "W2_SALARY",
        IncomeType.COMMISSION: "COMMISSION",
        IncomeType.OVERTIME: "OT_BONUS",
        IncomeType.BONUS: "OT_BONUS",
        IncomeType.SOCIAL_SECURITY: "NONTAX_SS",
        IncomeType.RETIREMENT_PENSION: "NONTAX_OTHER",
        IncomeType.ALIMONY_CHILD_SUPPORT: "NONTAX_OTHER",
        IncomeType.BANK_STATEMENT: "BANK_PERSONAL",
        IncomeType.RENTAL_SCHEDULE_E: "RENTAL_SCHEDULE_E",
        IncomeType.SELF_EMPLOYED_SCHEDULE_C: "SELF_EMPLOYMENT_1084",
        IncomeType.SELF_EMPLOYED_S_CORP: "SELF_EMPLOYMENT_1084",
        IncomeType.SELF_EMPLOYED_PARTNERSHIP: "SELF_EMPLOYMENT_1084",
        IncomeType.CONTRACTOR_1099: "COMMISSION",
    }

    formatted_sources = []
    for source in sources:
        frontend_type = type_mapping.get(source.income_type, source.income_type.value if source.income_type else None)
        verification_status_value = source.verification_status.value if source.verification_status else "PENDING"
        is_verified = verification_status_value == "VERIFIED"
        formatted_sources.append({
            "id": source.id,
            "income_type": frontend_type,
            "income_type_raw": source.income_type.value if source.income_type else None,
            "source_name": source.source_name,
            "monthly_qualifying_income": float(source.monthly_qualifying_income) if source.monthly_qualifying_income else None,
            "annual_qualifying_income": float(source.annual_qualifying_income) if source.annual_qualifying_income else None,
            "is_verified": is_verified,
            "verification_status": verification_status_value,
            "is_primary": source.is_primary,
            "notes": getattr(source, 'verification_notes', None) or getattr(source, 'calculation_notes', None),
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        })

    return {
        "loan_id": loan_id,
        "count": len(formatted_sources),
        "sources": formatted_sources,
    }


@router.get("/sources/{source_id}")
async def get_income_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific income source."""
    source = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    return _format_income_source(source)


@router.patch("/sources/{source_id}")
async def update_income_source(
    source_id: int,
    request: IncomeSourceUpdate,
    db: Session = Depends(get_db),
):
    """Update an income source."""
    source = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    update_data = request.dict(exclude_unset=True)

    # Handle enum conversions
    if "calculation_method" in update_data and update_data["calculation_method"]:
        try:
            update_data["calculation_method"] = IncomeCalculationMethod(update_data["calculation_method"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid calculation method")

    if "verification_status" in update_data and update_data["verification_status"]:
        try:
            update_data["verification_status"] = IncomeVerificationStatus(update_data["verification_status"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid verification status")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_data.items():
        if key not in _protected:
            setattr(source, key, value)

    source.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(source)

    return _format_income_source(source)


@router.delete("/sources/{source_id}")
async def delete_income_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Delete (soft-delete) an income source."""
    source = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    source.is_active = False
    source.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Income source deactivated"}


@router.post("/sources/{source_id}/calculate")
async def calculate_income(
    source_id: int,
    db: Session = Depends(get_db),
):
    """Trigger income calculation for a source."""
    from models.smart_docs_models import SmartDocument
    from decimal import Decimal

    source = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    calc_service = get_income_calculation_service()

    # Strategy 1: Get paystub extractions linked to this source
    paystubs = db.query(PaystubExtraction).filter(
        PaystubExtraction.income_source_id == source_id
    ).order_by(PaystubExtraction.pay_date.desc()).all()

    # Strategy 2: If no linked paystubs, find unlinked ones for same borrower/loan
    if not paystubs and source.borrower_id and source.loan_id:
        paystubs = db.query(PaystubExtraction).filter(
            PaystubExtraction.borrower_id == source.borrower_id,
            PaystubExtraction.loan_id == source.loan_id,
            PaystubExtraction.income_source_id.is_(None)
        ).order_by(PaystubExtraction.pay_date.desc()).all()

        # Link found paystubs to this source
        for ps in paystubs:
            ps.income_source_id = source_id
        if paystubs:
            db.flush()

    paystub_data = [_paystub_to_dict(p) for p in paystubs]

    # Strategy 3: If still no paystubs, try to extract from SmartDocument data
    if not paystub_data and source.loan_id:
        # Find paystub documents with extracted data
        docs = db.query(SmartDocument).filter(
            SmartDocument.loan_id == source.loan_id
        ).all()

        for doc in docs:
            doc_type_str = str(doc.doc_type.value if hasattr(doc.doc_type, 'value') else doc.doc_type).lower() if doc.doc_type else ''

            # Check if it's a paystub with extracted amount
            if 'paystub' in doc_type_str and doc.extracted_amount:
                # Build paystub-like data from SmartDocument
                paystub_data.append({
                    "pay_date": None,  # May not have exact date
                    "pay_frequency": "BIWEEKLY",  # Default assumption
                    "gross_pay": float(doc.extracted_amount),
                    "net_pay": None,
                    "ytd_gross": None,
                    "ytd_net": None,
                    "hourly_rate": None,
                    "regular_hours": None,
                    "overtime_hours": None,
                })

                # Also update source name if we have employer
                if doc.extracted_employer and not source.source_name:
                    source.source_name = doc.extracted_employer

    # Calculate based on income type
    if source.income_type == IncomeType.W2_EMPLOYMENT:
        result = calc_service.calculate_w2_income(paystub_data)
    elif source.income_type in [IncomeType.SELF_EMPLOYED_SCHEDULE_C, IncomeType.SELF_EMPLOYED_S_CORP]:
        # Would need tax return data
        result = calc_service.calculate_w2_income(paystub_data)  # Fallback
    else:
        result = calc_service.calculate_w2_income(paystub_data)

    if result.success:
        source.monthly_qualifying_income = result.monthly_qualifying_income
        source.annual_qualifying_income = result.annual_qualifying_income
        source.calculation_method = IncomeCalculationMethod(result.calculation_method) if result.calculation_method else None
        source.calculation_notes = "\n".join(result.notes)
        source.calculation_date = datetime.utcnow()
        source.declining_income_flag = result.flags.get("declining_income", False)
        source.variable_income_flag = result.flags.get("variable_income", False)
        source.updated_at = datetime.utcnow()
        db.commit()

    return result.to_dict()


# =============================================================================
# DOCUMENT EXTRACTION ENDPOINTS
# =============================================================================

@router.post("/extract-from-documents")
async def extract_income_from_documents(
    request: ExtractIncomeFromDocumentsRequest,
    db: Session = Depends(get_db),
):
    """
    Extract income data from uploaded documents for a specific income type.
    Creates or updates income source with extracted values.
    """
    from models.smart_docs_models import SmartDocument, DocType
    from decimal import Decimal

    # Extract parameters from request body
    loan_id = request.loan_id
    borrower_id = request.borrower_id
    income_type = request.income_type

    # Map income types to document types
    income_to_doc_types = {
        "W2_EMPLOYMENT": ["paystub", "w2", "offer_letter", "voe"],
        "SELF_EMPLOYED_SCHEDULE_C": ["tax_return", "schedule_c", "profit_loss"],
        "RENTAL_SCHEDULE_E": ["tax_return", "schedule_e", "lease"],
        "SELF_EMPLOYED_S_CORP": ["tax_return", "k1"],
        "BANK_STATEMENT": ["bank_statement"],
    }

    doc_type_patterns = income_to_doc_types.get(income_type, [])
    if not doc_type_patterns:
        raise HTTPException(status_code=400, detail=f"Unknown income type: {income_type}")

    # Find documents for this loan matching the income type
    all_docs = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id
    ).all()

    # Filter by doc_type pattern
    documents = []
    for doc in all_docs:
        doc_type_str = str(doc.doc_type.value if hasattr(doc.doc_type, 'value') else doc.doc_type).lower()
        if any(pattern.lower() in doc_type_str for pattern in doc_type_patterns):
            documents.append(doc)

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found for this income type")

    # Get or create income source
    try:
        income_type_enum = IncomeType(income_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid income type: {income_type}")

    source = db.query(IncomeSource).filter(
        IncomeSource.loan_id == loan_id,
        IncomeSource.borrower_id == borrower_id,
        IncomeSource.income_type == income_type_enum
    ).first()

    if not source:
        source = IncomeSource(
            borrower_id=borrower_id,
            loan_id=loan_id,
            income_type=income_type_enum,
            is_primary=False,
            verification_status=IncomeVerificationStatus.DOCUMENTS_RECEIVED,
        )
        db.add(source)
        db.flush()

    # Extract data from documents using actual SmartDocument fields
    extracted_income = {}

    for doc in documents:
        # Check if document has any extracted data
        has_data = (
            doc.extracted_dates or
            doc.extracted_names or
            doc.extracted_employer or
            doc.extracted_amount
        )
        if not has_data:
            continue

        doc_type_str = str(doc.doc_type.value if hasattr(doc.doc_type, 'value') else doc.doc_type).lower() if doc.doc_type else ''

        # Get employer name from document
        if doc.extracted_employer:
            source.source_name = doc.extracted_employer
            extracted_income['employer_name'] = doc.extracted_employer

        # Get amount (could be gross pay, YTD, etc. depending on doc type)
        if doc.extracted_amount:
            if 'paystub' in doc_type_str:
                # For paystubs, extracted_amount is typically gross pay
                extracted_income['last_gross_pay'] = float(doc.extracted_amount)
            elif 'w2' in doc_type_str:
                # For W-2s, extracted_amount is wages
                extracted_income['w2_wages'] = float(doc.extracted_amount)
            elif 'bank' in doc_type_str:
                # For bank statements, this might be total deposits
                extracted_income['total_deposits'] = float(doc.extracted_amount)

        # Extract dates (might contain pay_date, period_end, etc.)
        if doc.extracted_dates:
            for date_key, date_val in doc.extracted_dates.items():
                extracted_income[date_key] = date_val

    # Calculate income based on extracted data
    if 'w2_wages' in extracted_income:
        annual = Decimal(str(extracted_income['w2_wages']))
        monthly = annual / Decimal('12')

        source.gross_annual_income = annual
        source.gross_monthly_income = monthly
        source.monthly_qualifying_income = monthly
        source.annual_qualifying_income = annual
        source.calculation_method = IncomeCalculationMethod.TWO_YEAR_AVERAGE
        source.verification_status = IncomeVerificationStatus.DOCUMENTS_RECEIVED

    elif 'last_gross_pay' in extracted_income:
        # For paystubs, annualize the gross pay based on assumed bi-weekly frequency
        gross_pay = Decimal(str(extracted_income['last_gross_pay']))

        # Assume bi-weekly (26 pay periods) if not specified
        annual = gross_pay * Decimal('26')
        monthly = annual / Decimal('12')

        source.gross_annual_income = annual
        source.gross_monthly_income = monthly
        source.monthly_qualifying_income = monthly
        source.annual_qualifying_income = annual
        source.calculation_method = IncomeCalculationMethod.CURRENT_PERIOD
        source.verification_status = IncomeVerificationStatus.DOCUMENTS_RECEIVED

    elif 'total_deposits' in extracted_income:
        # For bank statements, average deposits as monthly income
        monthly = Decimal(str(extracted_income['total_deposits']))
        annual = monthly * Decimal('12')

        source.gross_annual_income = annual
        source.gross_monthly_income = monthly
        source.monthly_qualifying_income = monthly
        source.annual_qualifying_income = annual
        source.calculation_method = IncomeCalculationMethod.BANK_STATEMENT
        source.verification_status = IncomeVerificationStatus.DOCUMENTS_RECEIVED

    source.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(source)

    return {
        "success": True,
        "message": f"Extracted income from {len(documents)} documents",
        "source_id": source.id,
        "source_name": source.source_name,
        "monthly_income": float(source.monthly_qualifying_income or 0),
        "annual_income": float(source.annual_qualifying_income or 0),
        "extracted_fields": list(extracted_income.keys()),
    }


@router.get("/loan/{loan_id}/extractions")
async def get_loan_extractions(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """Get all extracted income data for a loan, organized by income type."""
    from models.smart_docs_models import SmartDocument

    # Get documents with any extracted data
    documents = db.query(SmartDocument).filter(
        SmartDocument.loan_id == loan_id
    ).all()

    extractions = {}

    for doc in documents:
        # Check if document has any extracted data
        has_data = (
            doc.extracted_dates or
            doc.extracted_names or
            doc.extracted_employer or
            doc.extracted_amount
        )
        if not has_data:
            continue

        # Map document type to income type
        doc_type_str = str(doc.doc_type.value if hasattr(doc.doc_type, 'value') else doc.doc_type).lower() if doc.doc_type else ''

        if any(p in doc_type_str for p in ['paystub', 'w2', 'offer']):
            income_type = "W2_EMPLOYMENT"
        elif 'tax' in doc_type_str or 'schedule' in doc_type_str:
            income_type = "SELF_EMPLOYED_SCHEDULE_C"
        elif 'bank' in doc_type_str:
            income_type = "BANK_STATEMENT"
        elif 'lease' in doc_type_str:
            income_type = "RENTAL_SCHEDULE_E"
        else:
            income_type = "OTHER"

        if income_type not in extractions:
            extractions[income_type] = {}

        # Add extracted data from individual fields
        if doc.extracted_employer:
            extractions[income_type]["employer"] = doc.extracted_employer
        if doc.extracted_amount:
            extractions[income_type]["amount"] = float(doc.extracted_amount)
        if doc.extracted_dates:
            for date_key, date_val in doc.extracted_dates.items():
                extractions[income_type][date_key] = date_val
        if doc.extracted_names:
            if isinstance(doc.extracted_names, dict):
                for name_key, name_val in doc.extracted_names.items():
                    extractions[income_type][name_key] = name_val
            elif isinstance(doc.extracted_names, list):
                extractions[income_type]["names"] = doc.extracted_names

    return {"extractions": extractions}


# =============================================================================
# INCOME SUMMARY ENDPOINTS
# =============================================================================

@router.get("/borrowers/{borrower_id}/summary")
async def get_income_summary(
    borrower_id: int,
    loan_id: int,
    db: Session = Depends(get_db),
):
    """Get qualifying income summary for a borrower."""
    sources = db.query(IncomeSource).filter(
        IncomeSource.borrower_id == borrower_id,
        IncomeSource.loan_id == loan_id,
        IncomeSource.is_active == True,
    ).all()

    total_monthly = sum(float(s.monthly_qualifying_income or 0) for s in sources)
    total_annual = sum(float(s.annual_qualifying_income or 0) for s in sources)
    verified_count = sum(1 for s in sources if s.verification_status == IncomeVerificationStatus.VERIFIED)
    has_declining = any(s.declining_income_flag for s in sources)

    return {
        "borrower_id": borrower_id,
        "loan_id": loan_id,
        "total_monthly_income": total_monthly,
        "total_annual_income": total_annual,
        "source_count": len(sources),
        "verified_count": verified_count,
        "has_declining_income": has_declining,
        "sources": [_format_income_source(s) for s in sources],
    }


@router.get("/loans/{loan_id}/qualifying-income")
async def get_loan_qualifying_income(
    loan_id: int,
    db: Session = Depends(get_db),
):
    """Get total qualifying income for a loan (all borrowers)."""
    sources = db.query(IncomeSource).filter(
        IncomeSource.loan_id == loan_id,
        IncomeSource.is_active == True,
    ).all()

    total_monthly = sum(float(s.monthly_qualifying_income or 0) for s in sources)
    total_annual = sum(float(s.annual_qualifying_income or 0) for s in sources)

    # Group by borrower
    by_borrower = {}
    for source in sources:
        if source.borrower_id not in by_borrower:
            by_borrower[source.borrower_id] = {
                "monthly": 0,
                "annual": 0,
                "sources": [],
            }
        by_borrower[source.borrower_id]["monthly"] += float(source.monthly_qualifying_income or 0)
        by_borrower[source.borrower_id]["annual"] += float(source.annual_qualifying_income or 0)
        by_borrower[source.borrower_id]["sources"].append(_format_income_source(source))

    return {
        "loan_id": loan_id,
        "total_monthly_qualifying_income": total_monthly,
        "total_annual_qualifying_income": total_annual,
        "by_borrower": by_borrower,
    }


# =============================================================================
# PAYSTUB EXTRACTION ENDPOINTS
# =============================================================================

@router.post("/documents/{document_id}/extract")
async def extract_paystub_data(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Extract income data from a paystub document using AI.

    The document must exist in smart_documents table.
    """
    from models.smart_docs_models import SmartDocument

    # Get the document
    doc = db.query(SmartDocument).filter(SmartDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get file content from S3
    s3_service = get_smart_docs_s3_service()
    if not doc.storage_key:
        raise HTTPException(status_code=400, detail="Document has no storage key")

    download_result = s3_service.download_file(doc.storage_key)
    if not download_result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to download document")

    # Extract data
    extractor = get_document_data_extractor()
    extraction_result = extractor.extract_paystub_for_income(
        file_content=download_result["content"],
        mime_type=doc.mime_type or "application/pdf",
    )

    if not extraction_result.get("success"):
        raise HTTPException(status_code=500, detail=extraction_result.get("error", "Extraction failed"))

    # Save extraction to database
    extraction = PaystubExtraction(
        document_id=document_id,
        borrower_id=doc.borrower_id,
        loan_id=doc.loan_id,
        # Employer
        employer_name=extraction_result.get("employer_name"),
        employer_address_line1=extraction_result.get("employer_address_line1"),
        employer_city=extraction_result.get("employer_city"),
        employer_state=extraction_result.get("employer_state"),
        employer_zip=extraction_result.get("employer_zip"),
        employer_phone=extraction_result.get("employer_phone"),
        employer_ein=extraction_result.get("employer_ein"),
        # Employee
        employee_name=extraction_result.get("employee_name"),
        employee_ssn_last4=extraction_result.get("employee_ssn_last4"),
        employee_id=extraction_result.get("employee_id"),
        hire_date=_parse_date(extraction_result.get("hire_date")),
        # Pay period
        pay_period_start=_parse_date(extraction_result.get("pay_period_start")),
        pay_period_end=_parse_date(extraction_result.get("pay_period_end")),
        pay_date=_parse_date(extraction_result.get("pay_date")),
        pay_frequency=_parse_pay_frequency(extraction_result.get("pay_frequency")),
        # Earnings
        gross_pay=extraction_result.get("gross_pay"),
        net_pay=extraction_result.get("net_pay"),
        regular_hours=extraction_result.get("regular_hours"),
        overtime_hours=extraction_result.get("overtime_hours"),
        hourly_rate=extraction_result.get("hourly_rate"),
        # YTD
        ytd_gross=extraction_result.get("ytd_gross"),
        ytd_net=extraction_result.get("ytd_net"),
        # Calculated
        calculated_annual_income=extraction_result.get("calculated_annual_income"),
        calculated_monthly_income=extraction_result.get("calculated_monthly_income"),
        # Freshness
        doc_date=_parse_date(extraction_result.get("doc_date")),
        expires_at=_parse_date(extraction_result.get("expires_at")),
        is_expired=extraction_result.get("is_expired", False),
        # Metadata
        extraction_confidence=extraction_result.get("extraction_confidence"),
        field_confidences=extraction_result.get("field_confidences"),
        extraction_model=extraction_result.get("extraction_model"),
        extraction_warnings=extraction_result.get("extraction_warnings"),
    )

    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    return {
        "success": True,
        "extraction_id": extraction.id,
        "document_id": document_id,
        "extracted_data": extraction_result,
    }


@router.get("/extractions/{extraction_id}")
async def get_paystub_extraction(
    extraction_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific paystub extraction."""
    extraction = db.query(PaystubExtraction).filter(
        PaystubExtraction.id == extraction_id
    ).first()

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    return _format_paystub_extraction(extraction)


@router.get("/documents/{document_id}/extractions")
async def get_document_extractions(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get all extractions for a document."""
    extractions = db.query(PaystubExtraction).filter(
        PaystubExtraction.document_id == document_id
    ).order_by(PaystubExtraction.created_at.desc()).all()

    return {
        "document_id": document_id,
        "count": len(extractions),
        "extractions": [_format_paystub_extraction(e) for e in extractions],
    }


@router.post("/apply-extraction")
async def apply_extraction_to_profile(
    request: ApplyExtractionRequest,
    db: Session = Depends(get_db),
):
    """
    Apply extracted paystub data to borrower profile.

    Creates or updates:
    - Employment record
    - Income source record
    """
    extraction = db.query(PaystubExtraction).filter(
        PaystubExtraction.id == request.extraction_id
    ).first()

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    applied_records = {
        "employment_id": None,
        "income_source_id": None,
        "fields_applied": [],
    }

    # Create/update employment record
    if request.create_employment and extraction.employer_name:
        employment = db.query(Employment).filter(
            Employment.borrower_id == extraction.borrower_id,
            Employment.loan_id == extraction.loan_id,
            Employment.employer_name == extraction.employer_name,
        ).first()

        if not employment:
            employment = Employment(
                borrower_id=extraction.borrower_id,
                loan_id=extraction.loan_id,
                employer_name=extraction.employer_name,
            )
            db.add(employment)
            db.flush()

        # Update employment fields
        if "employer_address_line1" in request.fields_to_apply:
            employment.employer_address_line1 = extraction.employer_address_line1
            applied_records["fields_applied"].append("employer_address_line1")
        if "employer_city" in request.fields_to_apply:
            employment.employer_city = extraction.employer_city
            applied_records["fields_applied"].append("employer_city")
        if "employer_state" in request.fields_to_apply:
            employment.employer_state = extraction.employer_state
            applied_records["fields_applied"].append("employer_state")
        if "employer_zip" in request.fields_to_apply:
            employment.employer_zip = extraction.employer_zip
            applied_records["fields_applied"].append("employer_zip")
        if "employer_phone" in request.fields_to_apply:
            employment.employer_phone = extraction.employer_phone
            applied_records["fields_applied"].append("employer_phone")
        if "employer_ein" in request.fields_to_apply:
            employment.employer_ein = extraction.employer_ein
            applied_records["fields_applied"].append("employer_ein")
        if "hire_date" in request.fields_to_apply:
            employment.start_date = extraction.hire_date
            applied_records["fields_applied"].append("hire_date")
        if "pay_frequency" in request.fields_to_apply:
            employment.pay_frequency = extraction.pay_frequency
            applied_records["fields_applied"].append("pay_frequency")
        if "hourly_rate" in request.fields_to_apply:
            employment.hourly_rate = extraction.hourly_rate
            employment.is_hourly = True
            employment.is_salaried = False
            applied_records["fields_applied"].append("hourly_rate")

        employment.monthly_income = extraction.calculated_monthly_income
        employment.annual_income = extraction.calculated_annual_income
        employment.last_updated_from_paystub_at = datetime.utcnow()
        employment.last_paystub_id = extraction.document_id
        employment.updated_at = datetime.utcnow()

        applied_records["employment_id"] = employment.id

    # Create/update income source
    if request.create_income_source:
        income_source = db.query(IncomeSource).filter(
            IncomeSource.borrower_id == extraction.borrower_id,
            IncomeSource.loan_id == extraction.loan_id,
            IncomeSource.source_name == extraction.employer_name,
            IncomeSource.income_type == IncomeType.W2_EMPLOYMENT,
        ).first()

        if not income_source:
            income_source = IncomeSource(
                borrower_id=extraction.borrower_id,
                loan_id=extraction.loan_id,
                income_type=IncomeType.W2_EMPLOYMENT,
                source_name=extraction.employer_name,
                verification_status=IncomeVerificationStatus.DOCUMENTS_RECEIVED,
            )
            db.add(income_source)
            db.flush()

        income_source.gross_monthly_income = extraction.calculated_monthly_income
        income_source.gross_annual_income = extraction.calculated_annual_income
        income_source.monthly_qualifying_income = extraction.calculated_monthly_income
        income_source.annual_qualifying_income = extraction.calculated_annual_income
        income_source.extracted_data = _paystub_to_dict(extraction)
        income_source.supporting_document_ids = [extraction.document_id]
        income_source.updated_at = datetime.utcnow()

        if applied_records.get("employment_id"):
            income_source.employment_id = applied_records["employment_id"]

        applied_records["income_source_id"] = income_source.id

        # Link extraction to income source
        extraction.income_source_id = income_source.id

    # Mark extraction as applied
    extraction.applied_to_profile = True
    extraction.applied_at = datetime.utcnow()
    extraction.applied_fields = request.fields_to_apply

    db.commit()

    return {
        "success": True,
        "extraction_id": extraction.id,
        "applied": applied_records,
    }


# =============================================================================
# EMPLOYMENT ENDPOINTS
# =============================================================================

@router.get("/borrowers/{borrower_id}/employments")
async def get_borrower_employments(
    borrower_id: int,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Get all employment records for a borrower."""
    query = db.query(Employment).filter(Employment.borrower_id == borrower_id)
    if loan_id:
        query = query.filter(Employment.loan_id == loan_id)

    employments = query.order_by(Employment.created_at.desc()).all()

    return {
        "borrower_id": borrower_id,
        "count": len(employments),
        "employments": [_format_employment(e) for e in employments],
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_income_source(source: IncomeSource) -> dict:
    """Format income source for API response."""
    return {
        "id": source.id,
        "borrower_id": source.borrower_id,
        "loan_id": source.loan_id,
        "employment_id": source.employment_id,
        "income_type": source.income_type.value if source.income_type else None,
        "source_name": source.source_name,
        "source_description": source.source_description,
        "is_primary": source.is_primary,
        "is_active": source.is_active,
        "gross_monthly_income": float(source.gross_monthly_income) if source.gross_monthly_income else None,
        "gross_annual_income": float(source.gross_annual_income) if source.gross_annual_income else None,
        "monthly_qualifying_income": float(source.monthly_qualifying_income) if source.monthly_qualifying_income else None,
        "annual_qualifying_income": float(source.annual_qualifying_income) if source.annual_qualifying_income else None,
        "calculation_method": source.calculation_method.value if source.calculation_method else None,
        "calculation_date": source.calculation_date.isoformat() if source.calculation_date else None,
        "verification_status": source.verification_status.value if source.verification_status else None,
        "verified_at": source.verified_at.isoformat() if source.verified_at else None,
        "trending_direction": source.trending_direction,
        "declining_income_flag": source.declining_income_flag or False,
        "variable_income_flag": source.variable_income_flag or False,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


def _format_paystub_extraction(extraction: PaystubExtraction) -> dict:
    """Format paystub extraction for API response."""
    return {
        "id": extraction.id,
        "document_id": extraction.document_id,
        "income_source_id": extraction.income_source_id,
        "borrower_id": extraction.borrower_id,
        "loan_id": extraction.loan_id,
        # Employer
        "employer_name": extraction.employer_name,
        "employer_address_line1": extraction.employer_address_line1,
        "employer_city": extraction.employer_city,
        "employer_state": extraction.employer_state,
        "employer_zip": extraction.employer_zip,
        "employer_phone": extraction.employer_phone,
        "employer_ein": extraction.employer_ein,
        # Employee
        "employee_name": extraction.employee_name,
        "employee_ssn_last4": extraction.employee_ssn_last4,
        "employee_id": extraction.employee_id,
        "hire_date": extraction.hire_date.isoformat() if extraction.hire_date else None,
        # Pay period
        "pay_period_start": extraction.pay_period_start.isoformat() if extraction.pay_period_start else None,
        "pay_period_end": extraction.pay_period_end.isoformat() if extraction.pay_period_end else None,
        "pay_date": extraction.pay_date.isoformat() if extraction.pay_date else None,
        "pay_frequency": extraction.pay_frequency.value if extraction.pay_frequency else None,
        # Earnings
        "gross_pay": float(extraction.gross_pay) if extraction.gross_pay else None,
        "net_pay": float(extraction.net_pay) if extraction.net_pay else None,
        "regular_hours": float(extraction.regular_hours) if extraction.regular_hours else None,
        "overtime_hours": float(extraction.overtime_hours) if extraction.overtime_hours else None,
        "hourly_rate": float(extraction.hourly_rate) if extraction.hourly_rate else None,
        # YTD
        "ytd_gross": float(extraction.ytd_gross) if extraction.ytd_gross else None,
        "ytd_net": float(extraction.ytd_net) if extraction.ytd_net else None,
        # Calculated
        "calculated_annual_income": float(extraction.calculated_annual_income) if extraction.calculated_annual_income else None,
        "calculated_monthly_income": float(extraction.calculated_monthly_income) if extraction.calculated_monthly_income else None,
        # Freshness
        "doc_date": extraction.doc_date.isoformat() if extraction.doc_date else None,
        "expires_at": extraction.expires_at.isoformat() if extraction.expires_at else None,
        "is_expired": extraction.is_expired or False,
        # Metadata
        "extraction_confidence": extraction.extraction_confidence,
        "extraction_model": extraction.extraction_model,
        "extraction_warnings": extraction.extraction_warnings,
        "applied_to_profile": extraction.applied_to_profile or False,
        "applied_at": extraction.applied_at.isoformat() if extraction.applied_at else None,
        "applied_fields": extraction.applied_fields,
        "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
    }


def _format_employment(employment: Employment) -> dict:
    """Format employment record for API response."""
    return {
        "id": employment.id,
        "borrower_id": employment.borrower_id,
        "loan_id": employment.loan_id,
        "employer_name": employment.employer_name,
        "employer_address_line1": employment.employer_address_line1,
        "employer_city": employment.employer_city,
        "employer_state": employment.employer_state,
        "employer_zip": employment.employer_zip,
        "employer_phone": employment.employer_phone,
        "job_title": employment.job_title,
        "start_date": employment.start_date.isoformat() if employment.start_date else None,
        "end_date": employment.end_date.isoformat() if employment.end_date else None,
        "is_salaried": employment.is_salaried,
        "is_hourly": employment.is_hourly,
        "pay_frequency": employment.pay_frequency.value if employment.pay_frequency else None,
        "hourly_rate": float(employment.hourly_rate) if employment.hourly_rate else None,
        "monthly_income": float(employment.monthly_income) if employment.monthly_income else None,
        "annual_income": float(employment.annual_income) if employment.annual_income else None,
        "verification_status": employment.verification_status.value if employment.verification_status else None,
        "last_updated_from_paystub_at": employment.last_updated_from_paystub_at.isoformat() if employment.last_updated_from_paystub_at else None,
        "created_at": employment.created_at.isoformat() if employment.created_at else None,
        "updated_at": employment.updated_at.isoformat() if employment.updated_at else None,
    }


def _paystub_to_dict(paystub: PaystubExtraction) -> dict:
    """Convert paystub extraction to dict for calculation service."""
    return {
        "pay_date": paystub.pay_date.isoformat() if paystub.pay_date else None,
        "pay_frequency": paystub.pay_frequency.value if paystub.pay_frequency else None,
        "gross_pay": float(paystub.gross_pay) if paystub.gross_pay else None,
        "net_pay": float(paystub.net_pay) if paystub.net_pay else None,
        "ytd_gross": float(paystub.ytd_gross) if paystub.ytd_gross else None,
        "ytd_net": float(paystub.ytd_net) if paystub.ytd_net else None,
        "hourly_rate": float(paystub.hourly_rate) if paystub.hourly_rate else None,
        "regular_hours": float(paystub.regular_hours) if paystub.regular_hours else None,
        "overtime_hours": float(paystub.overtime_hours) if paystub.overtime_hours else None,
    }


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_pay_frequency(freq_str: Optional[str]) -> Optional[PayrollFrequency]:
    """Parse pay frequency string to enum."""
    if not freq_str:
        return None
    try:
        return PayrollFrequency(freq_str.upper())
    except ValueError:
        return None


# =============================================================================
# ADMIN / MIGRATION ENDPOINT
# =============================================================================

@router.get("/admin/fix-paystub-columns")
async def fix_paystub_columns(
    admin_key: str = None,
    db: Session = Depends(get_db)
):
    """Add missing columns to paystub_extractions table."""
    from sqlalchemy import text

    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = []
    alter_statements = [
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS calculated_annual_income DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS calculated_monthly_income DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS annualization_method VARCHAR(50)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS raw_ocr_text TEXT",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS extraction_errors JSONB",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS doc_date DATE",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS is_expired BOOLEAN DEFAULT FALSE",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS applied_fields JSONB",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS loan_id INTEGER",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS field_confidences JSONB",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS extraction_model VARCHAR(64)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS extraction_warnings JSONB",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS employee_address_line2 VARCHAR(255)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS employee_city VARCHAR(100)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS employee_state VARCHAR(50)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS employee_zip VARCHAR(20)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS tips DECIMAL(12,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS other_earnings DECIMAL(12,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_regular_earnings DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_overtime_earnings DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_tips DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS dental_insurance DECIMAL(10,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS vision_insurance DECIMAL(10,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS life_insurance DECIMAL(10,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS hsa_fsa DECIMAL(10,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS deductions_breakdown JSONB",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_federal_tax DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_state_tax DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_social_security DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_medicare DECIMAL(15,2)",
        "ALTER TABLE paystub_extractions ADD COLUMN IF NOT EXISTS ytd_retirement DECIMAL(15,2)",
    ]

    try:
        for stmt in alter_statements:
            try:
                db.execute(text(stmt))
                col_name = stmt.split("ADD COLUMN IF NOT EXISTS ")[1].split()[0]
                results.append({"column": col_name, "status": "added"})
            except SQLAlchemyError as e:
                col_name = stmt.split("ADD COLUMN IF NOT EXISTS ")[1].split()[0] if "ADD COLUMN" in stmt else "unknown"
                results.append({"column": col_name, "status": "skipped", "error": "Internal server error"[:50]})

        db.commit()

        return {
            "success": True,
            "message": f"Processed {len(results)} column alterations",
            "results": results
        }
    except SQLAlchemyError as e:
        logger.error(f"Fix paystub columns failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# NOTE: Duplicate inline-SQL run-migration handler removed.
# The canonical ORM-based version is the @router.get("/admin/run-migration") below.


@router.get("/admin/seed-test-data")
async def seed_test_income_data(
    loan_id: int = 1,
    admin_key: str = None,
    db: Session = Depends(get_db),
):
    """
    Seed test income data for a loan.
    Admin endpoint - requires admin_key parameter.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from decimal import Decimal

    try:
        results = []

        # Create W-2 Employment Income Source
        w2_source = IncomeSource(
            borrower_id=1,
            loan_id=loan_id,
            income_type=IncomeType.W2_EMPLOYMENT,
            source_name="Acme Corporation",
            source_description="Software Engineer - Full Time W-2 Employment",
            is_primary=True,
            verification_status=IncomeVerificationStatus.VERIFIED,
            monthly_qualifying_income=Decimal("7500.00"),
            annual_qualifying_income=Decimal("90000.00"),
            gross_monthly_income=Decimal("7916.67"),
            gross_annual_income=Decimal("95000.00"),
            calculation_method=IncomeCalculationMethod.YTD_ANNUALIZED,
        )
        db.add(w2_source)
        db.flush()
        results.append({"source": "W-2 Employment", "name": "Acme Corporation", "monthly": 7500})

        # Create Rental Income Source
        rental_source = IncomeSource(
            borrower_id=1,
            loan_id=loan_id,
            income_type=IncomeType.RENTAL_SCHEDULE_E,
            source_name="123 Investment Property",
            source_description="Schedule E Rental Property - Single Family",
            is_primary=False,
            verification_status=IncomeVerificationStatus.DOCUMENTS_RECEIVED,
            monthly_qualifying_income=Decimal("1200.00"),
            annual_qualifying_income=Decimal("14400.00"),
            gross_monthly_income=Decimal("2000.00"),
            gross_annual_income=Decimal("24000.00"),
            calculation_method=IncomeCalculationMethod.SCHEDULE_E_AVERAGE,
        )
        db.add(rental_source)
        db.flush()
        results.append({"source": "Rental Income", "name": "123 Investment Property", "monthly": 1200})

        # Create Self-Employment Income Source
        self_emp_source = IncomeSource(
            borrower_id=1,
            loan_id=loan_id,
            income_type=IncomeType.SELF_EMPLOYED_SCHEDULE_C,
            source_name="Johnson Consulting LLC",
            source_description="Schedule C - Independent Consulting Business",
            is_primary=False,
            verification_status=IncomeVerificationStatus.NEEDS_ADDITIONAL_DOCS,
            monthly_qualifying_income=Decimal("3500.00"),
            annual_qualifying_income=Decimal("42000.00"),
            gross_monthly_income=Decimal("5000.00"),
            gross_annual_income=Decimal("60000.00"),
            calculation_method=IncomeCalculationMethod.TWO_YEAR_AVERAGE,
        )
        db.add(self_emp_source)
        db.flush()
        results.append({"source": "Self-Employment", "name": "Johnson Consulting LLC", "monthly": 3500})

        db.commit()

        total_monthly = sum(r["monthly"] for r in results)

        return {
            "success": True,
            "message": f"Created {len(results)} income sources for loan {loan_id}",
            "loan_id": loan_id,
            "sources": results,
            "total_monthly_income": total_monthly,
            "total_annual_income": total_monthly * 12,
        }
    except SQLAlchemyError as e:
        logger.error(f"Seed test data failed: {e}")
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error",
        }


@router.get("/admin/run-migration")
async def run_income_migration(
    admin_key: str = None,
    db: Session = Depends(get_db),
):
    """
    Run database migration to create income tables.
    This endpoint is public for initial setup.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    from sqlalchemy import inspect, text
    from models.income_models import (
        IncomeSource, PaystubExtraction, Employment,
        SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory
    )
    from database import Base, engine

    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        tables_to_create = [
            ('income_sources', IncomeSource),
            ('paystub_extractions', PaystubExtraction),
            ('employments', Employment),
            ('self_employment_income', SelfEmploymentIncome),
            ('rental_income_properties', RentalIncomeProperty),
            ('income_calculation_history', IncomeCalculationHistory),
        ]

        created = []
        already_exists = []

        for table_name, model in tables_to_create:
            if table_name in existing_tables:
                already_exists.append(table_name)
            else:
                model.__table__.create(engine, checkfirst=True)
                created.append(table_name)

        return {
            "success": True,
            "created_tables": created,
            "already_existed": already_exists,
            "message": f"Created {len(created)} tables, {len(already_exists)} already existed",
        }
    except Exception as e:
        logger.error(f"Income migration failed: {e}")
        return {
            "success": False,
            "error": "Internal server error",
        }
