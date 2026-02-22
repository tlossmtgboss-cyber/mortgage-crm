"""
Unified Income Calculator API Routes

Provides endpoints for:
1. Document detection and income type identification
2. Income calculation for all 14 types
3. Review workflow management
4. Confidence scoring and auto-approval
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from services.income.unified_income_calculator import (
    UnifiedIncomeType,
    PayFrequency,
    get_unified_income_calculator,
    W2HourlyData,
    W2SalaryData,
    OTBonusData,
    CommissionData,
    NonTaxSSData,
    NonTaxOtherData,
    BankStatementPersonalData,
    BankStatementBusinessData,
    RentalScheduleEData,
    SelfEmployment1084Data,
)
from services.income.ai_income_detection_service import (
    get_ai_income_detection_service,
    IncomeDocumentType,
)
from services.income.income_review_workflow import (
    get_income_review_workflow,
    get_income_review_orchestrator,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/unified-income", tags=["Unified Income"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class W2HourlyRequest(BaseModel):
    hourly_rate: float = Field(..., description="Hourly pay rate")
    hours_per_period: float = Field(40, description="Hours per pay period")
    pay_frequency: str = Field("BI_WEEKLY", description="WEEKLY, BI_WEEKLY, SEMI_MONTHLY, MONTHLY")
    ytd_earnings: Optional[float] = None
    ytd_months: Optional[int] = None
    w2_year1_earnings: Optional[float] = None
    w2_year1_months: int = 12
    w2_year2_earnings: Optional[float] = None
    w2_year2_months: int = 12


class W2SalaryRequest(BaseModel):
    base_salary: float = Field(..., description="Base salary per pay period")
    pay_frequency: str = Field("MONTHLY", description="WEEKLY, BI_WEEKLY, SEMI_MONTHLY, MONTHLY")
    ytd_salary: Optional[float] = None
    ytd_months: Optional[int] = None
    w2_year1_earnings: Optional[float] = None
    w2_year1_months: int = 12
    w2_year2_earnings: Optional[float] = None
    w2_year2_months: int = 12


class OTBonusRequest(BaseModel):
    ytd_ot_bonus: float = 0
    ytd_months: int = 0
    year1_ot_bonus: Optional[float] = None
    year1_months: int = 12
    year2_ot_bonus: Optional[float] = None
    year2_months: int = 12


class CommissionRequest(BaseModel):
    ytd_commission: float = 0
    ytd_expenses_2106: float = 0
    ytd_months: int = 0
    year1_commission: Optional[float] = None
    year1_expenses_2106: float = 0
    year1_months: int = 12
    year2_commission: Optional[float] = None
    year2_expenses_2106: float = 0
    year2_months: int = 12


class NonTaxSSRequest(BaseModel):
    annual_benefit: float
    taxable_portion: Optional[float] = None
    non_taxable_portion: Optional[float] = None
    has_documentation: bool = False


class NonTaxOtherRequest(BaseModel):
    income_type: str  # pension, ira, child_support, disability
    annual_amount: float
    is_taxable: bool = False


class BankStatementPersonalRequest(BaseModel):
    monthly_deposits: List[float]
    expense_factor: float = 50


class BankStatementBusinessRequest(BaseModel):
    monthly_deposits: List[float]
    method: int = 1  # 1, 2, or 3
    monthly_expenses: Optional[List[float]] = None
    expense_ratio: float = 50
    pl_net_income: Optional[float] = None
    ownership_percentage: float = 100


class RentalScheduleERequest(BaseModel):
    property_address: str
    gross_rents_line3: float = 0
    total_expenses_line20: float = 0
    depreciation_line18: float = 0
    amortization_casualty_line19: float = 0
    monthly_insurance: float = 0
    monthly_mortgage_interest: float = 0
    monthly_taxes: float = 0
    monthly_hoa: float = 0
    year2_gross_rents: Optional[float] = None
    year2_total_expenses: Optional[float] = None
    year2_depreciation: Optional[float] = None


class SelfEmployment1084Request(BaseModel):
    business_name: str
    business_type: str  # sole_prop, s_corp, partnership, c_corp
    ownership_percentage: float = 100

    # Schedule C
    schedule_c_net_profit_line31: float = 0
    schedule_c_depreciation_line13: float = 0
    schedule_c_depletion_line12: float = 0
    schedule_c_business_use_home: float = 0
    schedule_c_mileage: float = 0
    mileage_depreciation_rate: float = 0.28

    # K-1 1065
    k1_1065_ordinary_income_line1: float = 0
    k1_1065_guaranteed_payments_line4: float = 0

    # K-1 1120S
    k1_1120s_ordinary_income_line1: float = 0
    k1_1120s_net_rental_line2: float = 0

    # Form 1120
    form_1120_taxable_income_line30: float = 0
    form_1120_total_tax_line31: float = 0
    form_1120_depreciation_line20: float = 0
    form_1120_dividends_paid: float = 0


class DetectionRequest(BaseModel):
    text: str = Field(..., description="OCR or extracted text from document")
    filename: Optional[str] = None


class ReviewActionRequest(BaseModel):
    item_id: str
    action: str  # approve, reject, request_revision
    reviewer: str
    comment: Optional[str] = None
    override_monthly: Optional[float] = None
    override_annual: Optional[float] = None
    revision_notes: Optional[str] = None


# =============================================================================
# DOCUMENT DETECTION ENDPOINTS
# =============================================================================

@router.post("/detect")
async def detect_income_document(request: DetectionRequest):
    """
    Detect income document type from OCR text.

    Returns:
    - document_type: Detected type (paystub, W2, Schedule C, etc.)
    - confidence: 0-100 confidence score
    - suggested_income_type: Recommended income calculation type
    - extracted_fields: Fields extracted with per-field confidence
    """
    detector = get_ai_income_detection_service()
    result = detector.detect_from_text(request.text, request.filename)
    return result.to_dict()


@router.get("/document-types")
async def get_document_types():
    """Get list of supported document types."""
    return {
        "document_types": [t.value for t in IncomeDocumentType],
        "income_types": [t.value for t in UnifiedIncomeType],
    }


@router.get("/required-documents/{income_type}")
async def get_required_documents(income_type: str):
    """Get list of required documents for an income type."""
    try:
        income_type_enum = UnifiedIncomeType(income_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid income type: {income_type}")

    detector = get_ai_income_detection_service()
    return {
        "income_type": income_type,
        "required_documents": detector.get_required_documents(income_type_enum),
    }


# =============================================================================
# INCOME CALCULATION ENDPOINTS
# =============================================================================

@router.post("/calculate/w2-hourly")
async def calculate_w2_hourly(request: W2HourlyRequest):
    """Calculate W2 hourly income."""
    calculator = get_unified_income_calculator()

    try:
        pay_freq = PayFrequency(request.pay_frequency)
    except ValueError:
        pay_freq = PayFrequency.BI_WEEKLY

    data = W2HourlyData(
        hourly_rate=Decimal(str(request.hourly_rate)),
        hours_per_period=Decimal(str(request.hours_per_period)),
        pay_frequency=pay_freq,
        ytd_earnings=Decimal(str(request.ytd_earnings)) if request.ytd_earnings else None,
        ytd_months=request.ytd_months,
        w2_year1_earnings=Decimal(str(request.w2_year1_earnings)) if request.w2_year1_earnings else None,
        w2_year1_months=request.w2_year1_months,
        w2_year2_earnings=Decimal(str(request.w2_year2_earnings)) if request.w2_year2_earnings else None,
        w2_year2_months=request.w2_year2_months,
    )

    result = calculator.calculate_w2_hourly(data)
    return result.to_dict()


@router.post("/calculate/w2-salary")
async def calculate_w2_salary(request: W2SalaryRequest):
    """Calculate W2 salary income."""
    calculator = get_unified_income_calculator()

    try:
        pay_freq = PayFrequency(request.pay_frequency)
    except ValueError:
        pay_freq = PayFrequency.MONTHLY

    data = W2SalaryData(
        base_salary=Decimal(str(request.base_salary)),
        pay_frequency=pay_freq,
        ytd_salary=Decimal(str(request.ytd_salary)) if request.ytd_salary else None,
        ytd_months=request.ytd_months,
        w2_year1_earnings=Decimal(str(request.w2_year1_earnings)) if request.w2_year1_earnings else None,
        w2_year1_months=request.w2_year1_months,
        w2_year2_earnings=Decimal(str(request.w2_year2_earnings)) if request.w2_year2_earnings else None,
        w2_year2_months=request.w2_year2_months,
    )

    result = calculator.calculate_w2_salary(data)
    return result.to_dict()


@router.post("/calculate/ot-bonus")
async def calculate_ot_bonus(request: OTBonusRequest):
    """Calculate overtime and bonus income."""
    calculator = get_unified_income_calculator()

    data = OTBonusData(
        ytd_ot_bonus=Decimal(str(request.ytd_ot_bonus)),
        ytd_months=request.ytd_months,
        year1_ot_bonus=Decimal(str(request.year1_ot_bonus)) if request.year1_ot_bonus else None,
        year1_months=request.year1_months,
        year2_ot_bonus=Decimal(str(request.year2_ot_bonus)) if request.year2_ot_bonus else None,
        year2_months=request.year2_months,
    )

    result = calculator.calculate_ot_bonus(data)
    return result.to_dict()


@router.post("/calculate/commission")
async def calculate_commission(request: CommissionRequest):
    """Calculate commission income with 2106 expense deduction."""
    calculator = get_unified_income_calculator()

    data = CommissionData(
        ytd_commission=Decimal(str(request.ytd_commission)),
        ytd_expenses_2106=Decimal(str(request.ytd_expenses_2106)),
        ytd_months=request.ytd_months,
        year1_commission=Decimal(str(request.year1_commission)) if request.year1_commission else None,
        year1_expenses_2106=Decimal(str(request.year1_expenses_2106)),
        year1_months=request.year1_months,
        year2_commission=Decimal(str(request.year2_commission)) if request.year2_commission else None,
        year2_expenses_2106=Decimal(str(request.year2_expenses_2106)),
        year2_months=request.year2_months,
    )

    result = calculator.calculate_commission(data)
    return result.to_dict()


@router.post("/calculate/nontax-ss")
async def calculate_nontax_ss(request: NonTaxSSRequest):
    """Calculate non-taxable Social Security with 25% gross-up."""
    calculator = get_unified_income_calculator()

    data = NonTaxSSData(
        annual_benefit=Decimal(str(request.annual_benefit)),
        taxable_portion=Decimal(str(request.taxable_portion)) if request.taxable_portion else None,
        non_taxable_portion=Decimal(str(request.non_taxable_portion)) if request.non_taxable_portion else None,
        has_documentation=request.has_documentation,
    )

    result = calculator.calculate_nontax_ss(data)
    return result.to_dict()


@router.post("/calculate/nontax-other")
async def calculate_nontax_other(request: NonTaxOtherRequest):
    """Calculate other non-taxable income with 25% gross-up."""
    calculator = get_unified_income_calculator()

    data = NonTaxOtherData(
        income_type=request.income_type,
        annual_amount=Decimal(str(request.annual_amount)),
        is_taxable=request.is_taxable,
    )

    result = calculator.calculate_nontax_other(data)
    return result.to_dict()


@router.post("/calculate/bank-statement-personal")
async def calculate_bank_statement_personal(request: BankStatementPersonalRequest):
    """Calculate personal bank statement income (Non-QM)."""
    calculator = get_unified_income_calculator()

    data = BankStatementPersonalData(
        monthly_deposits=[Decimal(str(d)) for d in request.monthly_deposits],
        expense_factor=Decimal(str(request.expense_factor)),
        months_analyzed=len(request.monthly_deposits),
    )

    result = calculator.calculate_bank_statement_personal(data)
    return result.to_dict()


@router.post("/calculate/bank-statement-business")
async def calculate_bank_statement_business(request: BankStatementBusinessRequest):
    """Calculate business bank statement income (Non-QM)."""
    calculator = get_unified_income_calculator()

    data = BankStatementBusinessData(
        monthly_deposits=[Decimal(str(d)) for d in request.monthly_deposits],
        method=request.method,
        monthly_expenses=[Decimal(str(e)) for e in request.monthly_expenses] if request.monthly_expenses else None,
        expense_ratio=Decimal(str(request.expense_ratio)),
        pl_net_income=Decimal(str(request.pl_net_income)) if request.pl_net_income else None,
        ownership_percentage=Decimal(str(request.ownership_percentage)),
    )

    result = calculator.calculate_bank_statement_business(data)
    return result.to_dict()


@router.post("/calculate/rental-schedule-e")
async def calculate_rental_schedule_e(request: RentalScheduleERequest):
    """Calculate rental income from Schedule E."""
    calculator = get_unified_income_calculator()

    data = RentalScheduleEData(
        property_address=request.property_address,
        gross_rents_line3=Decimal(str(request.gross_rents_line3)),
        total_expenses_line20=Decimal(str(request.total_expenses_line20)),
        depreciation_line18=Decimal(str(request.depreciation_line18)),
        amortization_casualty_line19=Decimal(str(request.amortization_casualty_line19)),
        monthly_insurance=Decimal(str(request.monthly_insurance)),
        monthly_mortgage_interest=Decimal(str(request.monthly_mortgage_interest)),
        monthly_taxes=Decimal(str(request.monthly_taxes)),
        monthly_hoa=Decimal(str(request.monthly_hoa)),
        year2_gross_rents=Decimal(str(request.year2_gross_rents)) if request.year2_gross_rents else None,
        year2_total_expenses=Decimal(str(request.year2_total_expenses)) if request.year2_total_expenses else None,
        year2_depreciation=Decimal(str(request.year2_depreciation)) if request.year2_depreciation else None,
    )

    result = calculator.calculate_rental_schedule_e(data)
    return result.to_dict()


@router.post("/calculate/self-employment-1084")
async def calculate_self_employment_1084(request: SelfEmployment1084Request):
    """Calculate self-employment income per Fannie Mae 1084."""
    calculator = get_unified_income_calculator()

    data = SelfEmployment1084Data(
        business_name=request.business_name,
        business_type=request.business_type,
        ownership_percentage=Decimal(str(request.ownership_percentage)),
        schedule_c_net_profit_line31=Decimal(str(request.schedule_c_net_profit_line31)),
        schedule_c_depreciation_line13=Decimal(str(request.schedule_c_depreciation_line13)),
        schedule_c_depletion_line12=Decimal(str(request.schedule_c_depletion_line12)),
        schedule_c_business_use_home=Decimal(str(request.schedule_c_business_use_home)),
        schedule_c_mileage=Decimal(str(request.schedule_c_mileage)),
        mileage_depreciation_rate=Decimal(str(request.mileage_depreciation_rate)),
        k1_1065_ordinary_income_line1=Decimal(str(request.k1_1065_ordinary_income_line1)),
        k1_1065_guaranteed_payments_line4=Decimal(str(request.k1_1065_guaranteed_payments_line4)),
        k1_1120s_ordinary_income_line1=Decimal(str(request.k1_1120s_ordinary_income_line1)),
        k1_1120s_net_rental_line2=Decimal(str(request.k1_1120s_net_rental_line2)),
        form_1120_taxable_income_line30=Decimal(str(request.form_1120_taxable_income_line30)),
        form_1120_total_tax_line31=Decimal(str(request.form_1120_total_tax_line31)),
        form_1120_depreciation_line20=Decimal(str(request.form_1120_depreciation_line20)),
        form_1120_dividends_paid=Decimal(str(request.form_1120_dividends_paid)),
    )

    result = calculator.calculate_self_employment_1084(data)
    return result.to_dict()


# =============================================================================
# REVIEW WORKFLOW ENDPOINTS
# =============================================================================

@router.get("/review/queue")
async def get_review_queue(
    loan_id: Optional[int] = None,
    reviewer: Optional[str] = None,
    min_confidence: Optional[int] = None,
    max_confidence: Optional[int] = None,
):
    """Get items pending review."""
    workflow = get_income_review_workflow()
    items = workflow.get_pending_reviews(
        loan_id=loan_id,
        reviewer=reviewer,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
    )
    return {
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }


@router.get("/review/queue/summary")
async def get_queue_summary():
    """Get summary of review queue status."""
    workflow = get_income_review_workflow()
    summary = workflow.get_queue_summary()
    return {
        "pending_review": summary.pending_review_count,
        "in_review": summary.in_review_count,
        "revision_requested": summary.revision_requested_count,
        "auto_approved_today": summary.auto_approved_today,
        "approved_today": summary.approved_today,
        "rejected_today": summary.rejected_today,
        "average_confidence": summary.average_confidence,
        "oldest_pending_hours": summary.oldest_pending_hours,
    }


@router.get("/review/item/{item_id}")
async def get_review_item(item_id: str):
    """Get a specific review item."""
    workflow = get_income_review_workflow()
    item = workflow.get_review_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item.to_dict()


@router.get("/review/item/{item_id}/history")
async def get_review_history(item_id: str):
    """Get complete review history for an item."""
    workflow = get_income_review_workflow()
    history = workflow.get_review_history(item_id)
    return {"history": history}


@router.post("/review/action")
async def perform_review_action(request: ReviewActionRequest):
    """Perform a review action (approve, reject, request revision)."""
    workflow = get_income_review_workflow()

    try:
        if request.action == "approve":
            override_values = None
            if request.override_monthly or request.override_annual:
                override_values = {}
                if request.override_monthly:
                    override_values["monthly_income"] = request.override_monthly
                if request.override_annual:
                    override_values["annual_income"] = request.override_annual

            item = workflow.approve(
                item_id=request.item_id,
                reviewer=request.reviewer,
                comment=request.comment,
                override_values=override_values,
            )

        elif request.action == "reject":
            if not request.comment:
                raise HTTPException(status_code=400, detail="Rejection reason required")
            item = workflow.reject(
                item_id=request.item_id,
                reviewer=request.reviewer,
                reason=request.comment,
            )

        elif request.action == "request_revision":
            if not request.revision_notes:
                raise HTTPException(status_code=400, detail="Revision notes required")
            item = workflow.request_revision(
                item_id=request.item_id,
                reviewer=request.reviewer,
                revision_notes=request.revision_notes,
            )

        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

        return item.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/review/assign")
async def assign_reviewer(
    item_id: str,
    reviewer: str,
    assigned_by: str,
):
    """Assign a reviewer to an item."""
    workflow = get_income_review_workflow()
    try:
        item = workflow.assign_reviewer(item_id, reviewer, assigned_by)
        return item.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


# =============================================================================
# LOAN INCOME SUMMARY ENDPOINTS
# =============================================================================

@router.get("/loan/{loan_id}/income")
async def get_loan_income(loan_id: int):
    """Get complete income status for a loan."""
    orchestrator = get_income_review_orchestrator()
    return orchestrator.get_loan_income_status(loan_id)


@router.get("/loan/{loan_id}/income/approved")
async def get_approved_income(loan_id: int):
    """Get only approved income for a loan."""
    workflow = get_income_review_workflow()
    approved = workflow.get_approved_income_for_loan(loan_id)
    totals = workflow.calculate_total_qualifying_income(loan_id)

    return {
        "loan_id": loan_id,
        "total_monthly": float(totals["total_monthly"]),
        "total_annual": float(totals["total_annual"]),
        "income_sources": [item.to_dict() for item in approved],
    }


# =============================================================================
# PROCESS DOCUMENT ENDPOINT
# =============================================================================

@router.post("/process-document")
async def process_document(
    loan_id: int = Form(...),
    borrower_id: int = Form(...),
    document_text: str = Form(...),
    document_filename: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None),
):
    """
    Process a document through the complete workflow.

    1. Detects document type
    2. Extracts fields
    3. Calculates income
    4. Submits for review or auto-approves
    """
    orchestrator = get_income_review_orchestrator()
    item = orchestrator.process_document(
        loan_id=loan_id,
        borrower_id=borrower_id,
        document_text=document_text,
        document_filename=document_filename,
        document_id=document_id,
    )
    return item.to_dict()
