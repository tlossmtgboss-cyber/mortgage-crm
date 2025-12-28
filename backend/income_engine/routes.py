"""
Income Engine API Routes

FastAPI routes for income calculation endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import logging

from database import get_db
from sqlalchemy.orm import Session

from .orchestrator import IncomeOrchestrator
from .data_contracts import (
    CalculationRequest,
    CalculationResponse,
    W2Facts,
    PaystubFacts,
    ScheduleCFacts,
    ScheduleEFacts,
    K1Facts,
    BankStatementFacts,
    FlagSeverity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/income", tags=["Income Engine"])


# =============================================================================
# PYDANTIC MODELS FOR API
# =============================================================================

class IncomeCalculationRequestAPI(BaseModel):
    """API request model for income calculation."""
    loan_id: int
    borrower_id: int = Field(default=1, description="1=primary, 2=coborrower")

    # Document IDs to process (will be fetched and extracted)
    document_ids: Optional[List[str]] = None

    # Or provide pre-extracted facts directly
    w2_facts: Optional[List[Dict[str, Any]]] = None
    paystub_facts: Optional[List[Dict[str, Any]]] = None
    schedule_c_facts: Optional[List[Dict[str, Any]]] = None
    schedule_e_facts: Optional[List[Dict[str, Any]]] = None
    k1_facts: Optional[List[Dict[str, Any]]] = None
    bank_statement_facts: Optional[List[Dict[str, Any]]] = None

    # Calculation options
    investor_code: Optional[str] = None
    program_code: Optional[str] = None
    use_24_month_average: bool = False
    generate_worksheets: bool = True


class IncomeOverrideRequest(BaseModel):
    """Request for recalculating with manual overrides."""
    loan_id: int
    borrower_id: int = 1
    overrides: Dict[str, float] = Field(
        description="Map of stream_name to override monthly amount"
    )


class IncomeStreamSummary(BaseModel):
    """Summary of a single income stream."""
    stream_type: str
    stream_name: str
    monthly_income: float
    annual_income: float
    trending_direction: Optional[str] = None
    trending_percentage: Optional[float] = None


class IncomeFlagSummary(BaseModel):
    """Summary of a calculation flag."""
    rule_id: str
    severity: str
    message: str
    required_action: Optional[str] = None


class IncomeCalculationResponse(BaseModel):
    """API response for income calculation."""
    loan_id: int
    borrower_id: int
    total_monthly_income: float
    total_annual_income: float
    is_approvable: bool
    income_streams: List[IncomeStreamSummary]
    flags: List[IncomeFlagSummary]
    flags_summary: Dict[str, int]
    ruleset_version: str
    calculated_at: str
    calculation_duration_ms: int
    worksheet_ids: List[int] = []


class ValidationResult(BaseModel):
    """Result of document validation."""
    is_valid: bool
    has_income_documents: bool
    document_summary: Dict[str, Any]
    warnings: List[str]
    recommendations: List[str]


class SupportedIncomeType(BaseModel):
    """Supported income type information."""
    type: str
    description: str
    required_documents: List[str]
    years_required: int
    notes: str


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/calculate", response_model=IncomeCalculationResponse)
async def calculate_income(
    request: IncomeCalculationRequestAPI,
    db: Session = Depends(get_db),
):
    """
    Calculate qualifying income from provided documents.

    This endpoint processes all provided document facts through the
    income calculation engines and returns the aggregated results.
    """
    try:
        orchestrator = IncomeOrchestrator(db_session=db)

        # Build calculation request from API request
        calc_request = _build_calculation_request(request)

        # Run calculation
        response = orchestrator.calculate(calc_request)

        # Convert to API response
        return _to_api_response(response)

    except Exception as e:
        logger.exception(f"Income calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate-with-override", response_model=IncomeCalculationResponse)
async def recalculate_with_override(
    request: IncomeOverrideRequest,
    db: Session = Depends(get_db),
):
    """
    Recalculate income with manual overrides for specific streams.

    Use this when an underwriter needs to adjust calculated amounts
    based on additional information or manual analysis.
    """
    try:
        orchestrator = IncomeOrchestrator(db_session=db)

        # Get existing calculation or create new one
        # For now, we'll need the original document facts
        # In production, these would be fetched from database

        # Convert overrides to Decimal
        override_streams = {
            name: Decimal(str(amount))
            for name, amount in request.overrides.items()
        }

        # This would need the original calculation request
        # For now, return error indicating we need document facts
        raise HTTPException(
            status_code=400,
            detail="Override requires original document facts. "
                   "Use /calculate endpoint with document_ids parameter."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Override calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-documents", response_model=ValidationResult)
async def validate_documents(
    request: IncomeCalculationRequestAPI,
    db: Session = Depends(get_db),
):
    """
    Validate that provided documents are sufficient for calculation.

    Returns validation status with warnings and recommendations
    for missing or incomplete documentation.
    """
    try:
        orchestrator = IncomeOrchestrator(db_session=db)

        # Build calculation request
        calc_request = _build_calculation_request(request)

        # Validate
        result = orchestrator.validate_documents(calc_request)

        return ValidationResult(**result)

    except Exception as e:
        logger.exception(f"Document validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-types", response_model=List[SupportedIncomeType])
async def get_supported_income_types():
    """
    Get list of supported income types and their requirements.

    Returns information about each income type the engine can process,
    including required documents and calculation notes.
    """
    orchestrator = IncomeOrchestrator()
    types = orchestrator.get_supported_income_types()

    return [SupportedIncomeType(**t) for t in types]


@router.get("/loan/{loan_id}/summary")
async def get_income_summary(
    loan_id: int,
    borrower_id: int = Query(default=1, description="1=primary, 2=coborrower"),
    db: Session = Depends(get_db),
):
    """
    Get income calculation summary for a loan.

    Returns the most recent income calculation results for the specified
    loan and borrower.
    """
    try:
        from models.income_engine_models import IncomeSummary

        summary = db.query(IncomeSummary).filter(
            IncomeSummary.loan_id == loan_id,
            IncomeSummary.borrower_id == borrower_id,
        ).order_by(IncomeSummary.calculated_at.desc()).first()

        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"No income summary found for loan {loan_id}"
            )

        return {
            "loan_id": summary.loan_id,
            "borrower_id": summary.borrower_id,
            "total_monthly_income": float(summary.total_monthly_income),
            "total_annual_income": float(summary.total_annual_income),
            "is_approvable": summary.is_approvable,
            "blocking_flags_count": summary.blocking_flags_count,
            "calculated_at": summary.calculated_at.isoformat(),
            "calculated_by": summary.calculated_by,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get income summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loan/{loan_id}/streams")
async def get_income_streams(
    loan_id: int,
    borrower_id: int = Query(default=1, description="1=primary, 2=coborrower"),
    db: Session = Depends(get_db),
):
    """
    Get detailed income streams for a loan.

    Returns all calculated income streams with calculation details
    and audit trail.
    """
    try:
        from models.income_engine_models import IncomeCalculationDetail

        details = db.query(IncomeCalculationDetail).filter(
            IncomeCalculationDetail.loan_id == loan_id,
            IncomeCalculationDetail.borrower_id == borrower_id,
        ).order_by(IncomeCalculationDetail.stream_name).all()

        if not details:
            raise HTTPException(
                status_code=404,
                detail=f"No income streams found for loan {loan_id}"
            )

        return [
            {
                "id": d.id,
                "stream_type": d.stream_type,
                "stream_name": d.stream_name,
                "monthly_income": float(d.monthly_income),
                "annual_income": float(d.annual_income),
                "calculation_method": d.calculation_method,
                "calculation_inputs": d.calculation_inputs,
                "calculation_steps": d.calculation_steps,
                "add_backs": d.add_backs,
                "trending_direction": d.trending_direction,
                "trending_percentage": float(d.trending_percentage) if d.trending_percentage else None,
            }
            for d in details
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get income streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loan/{loan_id}/flags")
async def get_income_flags(
    loan_id: int,
    borrower_id: int = Query(default=1, description="1=primary, 2=coborrower"),
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    db: Session = Depends(get_db),
):
    """
    Get calculation flags for a loan.

    Returns all flags generated during income calculation,
    optionally filtered by severity.
    """
    try:
        from models.income_engine_models import IncomeFlag

        query = db.query(IncomeFlag).filter(
            IncomeFlag.loan_id == loan_id,
            IncomeFlag.borrower_id == borrower_id,
        )

        if severity:
            query = query.filter(IncomeFlag.severity == severity.upper())

        flags = query.order_by(IncomeFlag.severity.desc()).all()

        return [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "message": f.message,
                "required_action": f.required_action,
                "affected_stream": f.affected_stream,
                "is_resolved": f.is_resolved,
                "resolved_by": f.resolved_by,
                "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
            }
            for f in flags
        ]

    except Exception as e:
        logger.exception(f"Failed to get income flags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/loan/{loan_id}/flags/{flag_id}/resolve")
async def resolve_income_flag(
    loan_id: int,
    flag_id: int,
    resolution_note: str = "",
    resolved_by: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Mark a calculation flag as resolved.

    Used when an underwriter has addressed the issue raised by a flag.
    """
    try:
        from models.income_engine_models import IncomeFlag

        flag = db.query(IncomeFlag).filter(
            IncomeFlag.id == flag_id,
            IncomeFlag.loan_id == loan_id,
        ).first()

        if not flag:
            raise HTTPException(
                status_code=404,
                detail=f"Flag {flag_id} not found for loan {loan_id}"
            )

        flag.is_resolved = True
        flag.resolved_at = datetime.utcnow()
        flag.resolved_by = resolved_by
        flag.resolution_note = resolution_note

        db.commit()

        return {"message": "Flag resolved", "flag_id": flag_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to resolve flag: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loan/{loan_id}/worksheets")
async def get_income_worksheets(
    loan_id: int,
    borrower_id: int = Query(default=1, description="1=primary, 2=coborrower"),
    worksheet_type: Optional[str] = Query(default=None, description="Filter by type"),
    db: Session = Depends(get_db),
):
    """
    Get generated income worksheets for a loan.

    Returns worksheet IDs and types for download/viewing.
    """
    try:
        from models.income_engine_models import IncomeWorksheet

        query = db.query(IncomeWorksheet).filter(
            IncomeWorksheet.loan_id == loan_id,
            IncomeWorksheet.borrower_id == borrower_id,
        )

        if worksheet_type:
            query = query.filter(IncomeWorksheet.worksheet_type == worksheet_type)

        worksheets = query.order_by(IncomeWorksheet.generated_at.desc()).all()

        return [
            {
                "id": w.id,
                "worksheet_type": w.worksheet_type,
                "generated_at": w.generated_at.isoformat(),
            }
            for w in worksheets
        ]

    except Exception as e:
        logger.exception(f"Failed to get worksheets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _build_calculation_request(api_request: IncomeCalculationRequestAPI) -> CalculationRequest:
    """Convert API request to internal CalculationRequest."""
    # In production, if document_ids are provided, we would fetch
    # and extract facts from those documents using AI extraction

    return CalculationRequest(
        loan_id=api_request.loan_id,
        borrower_id=api_request.borrower_id,
        w2_facts=_convert_facts(api_request.w2_facts, W2Facts) if api_request.w2_facts else [],
        paystub_facts=_convert_facts(api_request.paystub_facts, PaystubFacts) if api_request.paystub_facts else [],
        schedule_c_facts=_convert_facts(api_request.schedule_c_facts, ScheduleCFacts) if api_request.schedule_c_facts else [],
        schedule_e_facts=_convert_facts(api_request.schedule_e_facts, ScheduleEFacts) if api_request.schedule_e_facts else [],
        k1_facts=_convert_facts(api_request.k1_facts, K1Facts) if api_request.k1_facts else [],
        bank_statement_facts=_convert_facts(api_request.bank_statement_facts, BankStatementFacts) if api_request.bank_statement_facts else [],
        investor_code=api_request.investor_code,
        program_code=api_request.program_code,
        use_24_month_average=api_request.use_24_month_average,
        generate_worksheets=api_request.generate_worksheets,
    )


def _convert_facts(facts_list: List[Dict], fact_class):
    """Convert list of dicts to list of fact dataclass instances."""
    from .data_contracts import RentalProperty, BankStatementMonth

    if not facts_list:
        return []

    converted = []
    for fact_dict in facts_list:
        try:
            # Create instance from dict (dataclass doesn't have from_dict by default)
            # Filter to only include fields that exist in the dataclass
            valid_fields = {}
            for k, v in fact_dict.items():
                if hasattr(fact_class, '__dataclass_fields__') and k in fact_class.__dataclass_fields__:
                    # Handle nested dataclasses
                    if k == 'properties' and isinstance(v, list):
                        # Convert list of property dicts to RentalProperty objects
                        valid_fields[k] = [
                            RentalProperty(**prop) if isinstance(prop, dict) else prop
                            for prop in v
                        ]
                    elif k == 'monthly_data' and isinstance(v, list):
                        # Convert list of month dicts to BankStatementMonth objects
                        valid_fields[k] = [
                            BankStatementMonth(**month) if isinstance(month, dict) else month
                            for month in v
                        ]
                    else:
                        valid_fields[k] = v

            converted.append(fact_class(**valid_fields))
        except Exception as e:
            logger.warning(f"Failed to convert fact to {fact_class.__name__}: {e}")

    return converted


def _to_api_response(response: CalculationResponse) -> IncomeCalculationResponse:
    """Convert internal CalculationResponse to API response."""
    return IncomeCalculationResponse(
        loan_id=response.loan_id,
        borrower_id=response.borrower_id,
        total_monthly_income=float(response.total_monthly_income),
        total_annual_income=float(response.total_annual_income),
        is_approvable=response.is_approvable,
        income_streams=[
            IncomeStreamSummary(
                stream_type=s.stream_type.value,
                stream_name=s.stream_name,
                monthly_income=float(s.monthly_income),
                annual_income=float(s.annual_income),
                trending_direction=s.trending_direction.value if s.trending_direction else None,
                trending_percentage=float(s.trending_percentage) if s.trending_percentage else None,
            )
            for s in response.income_streams
        ],
        flags=[
            IncomeFlagSummary(
                rule_id=f.rule_id,
                severity=f.severity.value,
                message=f.message,
                required_action=f.required_action,
            )
            for f in response.flags
        ],
        flags_summary={
            "blocking": response.blocking_flags_count,
            "errors": response.error_flags_count,
            "warnings": response.warning_flags_count,
            "info": response.info_flags_count,
        },
        ruleset_version=response.ruleset_version,
        calculated_at=response.calculated_at.isoformat(),
        calculation_duration_ms=response.calculation_duration_ms,
        worksheet_ids=response.worksheet_ids,
    )
