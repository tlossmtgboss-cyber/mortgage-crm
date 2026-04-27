"""
Smart Docs Bank Statement Analysis Routes

Endpoints for AI-assisted bank statement analysis: large deposit detection,
NSF/overdraft tracking, IRS payment analysis, income verification from
deposits, undisclosed debt detection, risk scoring, and report generation.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Bank Statement Analysis"])


# =============================================================================
# Pydantic Models
# =============================================================================

class LargeDepositItem(BaseModel):
    index: int
    date: Optional[str] = None
    amount: float
    description: Optional[str] = None
    risk_level: str = "medium"  # low, medium, high
    sourcing_status: str = "unsourced"  # unsourced, sourced, waived
    explanation: Optional[str] = None
    supporting_document_id: Optional[int] = None
    sourced_by: Optional[str] = None


class NSFEventItem(BaseModel):
    date: Optional[str] = None
    amount: float
    description: Optional[str] = None
    fee_amount: float = 0.0
    severity: str = "medium"  # low, medium, high


class IRSPaymentItem(BaseModel):
    date: Optional[str] = None
    amount: float
    description: Optional[str] = None
    payment_type: Optional[str] = None  # estimated_tax, installment, penalty


class PayrollDepositItem(BaseModel):
    date: Optional[str] = None
    amount: float
    employer_match: Optional[str] = None
    frequency: Optional[str] = None  # biweekly, semimonthly, monthly, weekly


class UndisclosedDebtItem(BaseModel):
    payee: Optional[str] = None
    amount: float
    frequency: Optional[str] = None  # monthly, biweekly, weekly
    category: Optional[str] = None  # loan_payment, insurance, child_support, other
    months_observed: int = 0


class RiskFlag(BaseModel):
    flag_type: str
    severity: str  # low, medium, high, critical
    description: str
    recommendation: Optional[str] = None


class AnalyzeBankStatementsResponse(BaseModel):
    loan_id: int
    borrower_id: int
    analysis_id: Optional[str] = None
    analyzed_at: str
    statement_count: int = 0
    months_covered: int = 0
    large_deposits: List[LargeDepositItem] = []
    nsf_events: List[NSFEventItem] = []
    irs_payments: List[IRSPaymentItem] = []
    payroll_deposits: List[PayrollDepositItem] = []
    recurring_obligations: List[UndisclosedDebtItem] = []
    risk_score: float = 0.0
    risk_level: str = "low"
    risk_flags: List[RiskFlag] = []
    recommendations: List[str] = []


class LargeDepositResponse(BaseModel):
    loan_id: int
    deposits: List[LargeDepositItem] = []
    total_unsourced_count: int = 0
    total_unsourced_amount: float = 0.0


class SourceDepositBody(BaseModel):
    explanation: str
    supporting_document_id: Optional[int] = None
    sourced_by: str


class NSFEventResponse(BaseModel):
    loan_id: int
    events: List[NSFEventItem] = []
    total_nsf_count: int = 0
    total_fees: float = 0.0
    overdraft_day_count: int = 0
    severity_assessment: str = "low"


class IRSPaymentResponse(BaseModel):
    loan_id: int
    payments: List[IRSPaymentItem] = []
    total_irs_payments: float = 0.0
    payment_plan_detected: bool = False
    estimated_tax_payments: bool = False


class IncomeVerificationResponse(BaseModel):
    loan_id: int
    payroll_deposits: List[PayrollDepositItem] = []
    estimated_monthly_income: float = 0.0
    stated_monthly_income: Optional[float] = None
    income_variance_pct: Optional[float] = None
    consistency_rating: str = "unknown"  # excellent, good, fair, poor, unknown
    employer_names: List[str] = []
    deposit_frequency: Optional[str] = None


class UndisclosedDebtResponse(BaseModel):
    loan_id: int
    debts: List[UndisclosedDebtItem] = []
    total_monthly_obligations: float = 0.0
    potential_dti_impact: Optional[float] = None


class CompareIncomeBody(BaseModel):
    stated_monthly_income: float = Field(..., gt=0, description="Borrower's stated monthly income")


class RiskSummaryResponse(BaseModel):
    loan_id: int
    overall_risk_score: float = 0.0
    risk_level: str = "low"  # low, medium, high, critical
    flags: List[RiskFlag] = []
    recommendations: List[str] = []
    large_deposit_count: int = 0
    nsf_event_count: int = 0
    irs_payment_count: int = 0
    undisclosed_debt_count: int = 0
    income_consistency: Optional[str] = None


class BankAnalysisTask(BaseModel):
    task_type: str  # sourcing_letter, loe_needed, irs_docs, nsf_explanation
    description: str
    related_item: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "medium"  # low, medium, high


# =============================================================================
# Tenant Verification Helper
# =============================================================================

def _verify_loan_tenant(db: Session, loan_id: int, current_user) -> None:
    """Verify the requesting user's org owns the loan. Raises 404 if not."""
    org_id = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"
    if org_id and not is_platform_admin:
        row = db.execute(
            sa_text("SELECT organization_id FROM loans WHERE id = :id"),
            {"id": loan_id},
        ).first()
        loan_org = row[0] if row else None
        if loan_org is not None and loan_org != org_id:
            raise HTTPException(status_code=404, detail="Not found")


def _get_analyzer(db: Session):
    """Get bank statement analyzer service, raising 501 if unavailable."""
    try:
        from services.smart_docs.bank_statement_analyzer import get_bank_statement_analyzer
        return get_bank_statement_analyzer(db)
    except ImportError:
        logger.warning("Bank statement analyzer service not available")
        raise HTTPException(
            status_code=501,
            detail="Bank statement analyzer service is not yet available",
        )


def _get_cached_analysis(db: Session, loan_id: int) -> Optional[dict]:
    """Fetch the most recent bank analysis result from JSON storage on the loan."""
    row = db.execute(
        sa_text("""
            SELECT bank_analysis_result, bank_analysis_at
            FROM loans
            WHERE id = :loan_id
        """),
        {"loan_id": loan_id},
    ).first()

    if row and row[0]:
        return row[0] if isinstance(row[0], dict) else None
    return None


# =============================================================================
# 1. POST /bank-analysis/analyze/{loan_id}
# =============================================================================

@router.post("/bank-analysis/analyze/{loan_id}")
async def analyze_bank_statements(
    loan_id: int,
    borrower_id: int = Query(..., description="Borrower ID to analyze bank statements for"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Analyze bank statements for a loan/borrower pair.

    Runs comprehensive analysis: large deposit detection, NSF events,
    IRS payment identification, payroll pattern analysis, recurring
    obligation detection, and risk scoring.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    analyzer = _get_analyzer(db)

    try:
        result = analyzer.analyze(loan_id=loan_id, borrower_id=borrower_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bank statement analysis failed for loan_id=%s", loan_id)
        raise HTTPException(status_code=500, detail="Bank statement analysis failed")

    if not result or not getattr(result, "success", True) is True:
        error_msg = getattr(result, "error", "Analysis could not complete") if result else "No result returned"
        raise HTTPException(status_code=422, detail=error_msg)

    # Persist the analysis result on the loan for later retrieval
    try:
        analysis_data = result.to_dict() if hasattr(result, "to_dict") else result
        db.execute(
            sa_text("""
                UPDATE loans
                SET bank_analysis_result = CAST(:result AS jsonb),
                    bank_analysis_at = :now
                WHERE id = :loan_id
            """),
            {
                "result": __import__("json").dumps(analysis_data),
                "now": datetime.now(timezone.utc),
                "loan_id": loan_id,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("Failed to persist bank analysis result for loan %s: %s", loan_id, e)
        db.rollback()

    return {
        "loan_id": loan_id,
        "borrower_id": borrower_id,
        "analysis": analysis_data,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# 2. GET /bank-analysis/results/{loan_id}
# =============================================================================

@router.get("/bank-analysis/results/{loan_id}")
async def get_analysis_results(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the most recent bank statement analysis results for a loan.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank statement analysis found for this loan. Run POST /bank-analysis/analyze/{loan_id} first.",
        )

    # Fetch the timestamp
    row = db.execute(
        sa_text("SELECT bank_analysis_at FROM loans WHERE id = :loan_id"),
        {"loan_id": loan_id},
    ).first()

    return {
        "loan_id": loan_id,
        "analysis": cached,
        "analyzed_at": row[0].isoformat() if row and row[0] else None,
    }


# =============================================================================
# 3. POST /bank-analysis/reanalyze/{loan_id}
# =============================================================================

@router.post("/bank-analysis/reanalyze/{loan_id}")
async def reanalyze_bank_statements(
    loan_id: int,
    borrower_id: int = Query(..., description="Borrower ID to re-analyze"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Re-run bank statement analysis with the latest uploaded statements.

    Useful after new bank statements are uploaded. Overwrites the
    previous analysis result.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    analyzer = _get_analyzer(db)

    try:
        result = analyzer.analyze(
            loan_id=loan_id,
            borrower_id=borrower_id,
            force_refresh=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bank statement re-analysis failed for loan_id=%s", loan_id)
        raise HTTPException(status_code=500, detail="Bank statement re-analysis failed")

    if not result or not getattr(result, "success", True) is True:
        error_msg = getattr(result, "error", "Re-analysis could not complete") if result else "No result returned"
        raise HTTPException(status_code=422, detail=error_msg)

    analysis_data = result.to_dict() if hasattr(result, "to_dict") else result

    # Persist updated result
    try:
        db.execute(
            sa_text("""
                UPDATE loans
                SET bank_analysis_result = CAST(:result AS jsonb),
                    bank_analysis_at = :now
                WHERE id = :loan_id
            """),
            {
                "result": __import__("json").dumps(analysis_data),
                "now": datetime.now(timezone.utc),
                "loan_id": loan_id,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("Failed to persist re-analysis result for loan %s: %s", loan_id, e)
        db.rollback()

    return {
        "loan_id": loan_id,
        "borrower_id": borrower_id,
        "analysis": analysis_data,
        "reanalyzed_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# 4. GET /bank-analysis/large-deposits/{loan_id}
# =============================================================================

@router.get("/bank-analysis/large-deposits/{loan_id}")
async def get_large_deposits(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get large deposits requiring sourcing documentation.

    Returns deposits that exceed the threshold (typically 50% of qualifying
    monthly income or $1,000+ for FHA), including sourcing status.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    deposits = cached.get("large_deposits", [])
    unsourced = [d for d in deposits if d.get("sourcing_status") != "sourced"]

    return {
        "loan_id": loan_id,
        "deposits": deposits,
        "total_count": len(deposits),
        "total_unsourced_count": len(unsourced),
        "total_unsourced_amount": sum(d.get("amount", 0) for d in unsourced),
    }


# =============================================================================
# 5. POST /bank-analysis/large-deposits/{deposit_index}/source
# =============================================================================

@router.post("/bank-analysis/large-deposits/{deposit_index}/source")
async def source_large_deposit(
    deposit_index: int,
    body: SourceDepositBody,
    loan_id: int = Query(..., description="Loan ID the deposit belongs to"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mark a large deposit as sourced with explanation and optional supporting document.

    Uses SELECT FOR UPDATE on the loan row to prevent concurrent modifications
    to the bank_analysis_result JSON (race condition where two users source
    different deposits simultaneously and overwrite each other's changes).
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        import json
        from services.smart_docs.db_transaction import atomic_operation

        with atomic_operation(db):
            # Lock the loan row before reading the cached analysis to prevent
            # concurrent sourcing operations from overwriting each other.
            locked_row = db.execute(
                sa_text("""
                    SELECT bank_analysis_result
                    FROM loans
                    WHERE id = :loan_id
                    FOR UPDATE
                """),
                {"loan_id": loan_id},
            ).first()

            if not locked_row or not locked_row[0]:
                raise HTTPException(
                    status_code=404,
                    detail="No bank analysis found. Run analysis first.",
                )

            cached = locked_row[0] if isinstance(locked_row[0], dict) else None
            if not cached:
                raise HTTPException(
                    status_code=404,
                    detail="No bank analysis found. Run analysis first.",
                )

            deposits = cached.get("large_deposits", [])
            if deposit_index < 0 or deposit_index >= len(deposits):
                raise HTTPException(
                    status_code=404,
                    detail=f"Deposit index {deposit_index} not found. Valid range: 0-{len(deposits) - 1}",
                )

            # Update the deposit record
            now = datetime.now(timezone.utc)
            deposits[deposit_index]["sourcing_status"] = "sourced"
            deposits[deposit_index]["explanation"] = body.explanation
            deposits[deposit_index]["supporting_document_id"] = body.supporting_document_id
            deposits[deposit_index]["sourced_by"] = body.sourced_by
            deposits[deposit_index]["sourced_at"] = now.isoformat()

            # Persist updated analysis back to the loan
            cached["large_deposits"] = deposits

            db.execute(
                sa_text("""
                    UPDATE loans
                    SET bank_analysis_result = CAST(:result AS jsonb)
                    WHERE id = :loan_id
                """),
                {
                    "result": json.dumps(cached),
                    "loan_id": loan_id,
                },
            )
            # atomic_operation commits here

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Failed to update deposit sourcing for loan %s", loan_id)
        raise HTTPException(status_code=500, detail="Failed to update deposit sourcing status")

    return {
        "status": "sourced",
        "deposit_index": deposit_index,
        "loan_id": loan_id,
        "explanation": body.explanation,
        "supporting_document_id": body.supporting_document_id,
        "sourced_by": body.sourced_by,
        "sourced_at": now.isoformat(),
        "deposit": deposits[deposit_index],
    }


# =============================================================================
# 6. GET /bank-analysis/nsf-events/{loan_id}
# =============================================================================

@router.get("/bank-analysis/nsf-events/{loan_id}")
async def get_nsf_events(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get NSF (Non-Sufficient Funds) and overdraft events from the analysis.

    Returns list of events with severity assessment, total fees, and
    overdraft day count.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    nsf_events = cached.get("nsf_events", [])
    total_fees = sum(e.get("fee_amount", 0) for e in nsf_events)
    overdraft_days = cached.get("overdraft_day_count", 0)

    # Assess overall severity
    event_count = len(nsf_events)
    if event_count == 0:
        severity = "none"
    elif event_count <= 2 and total_fees < 100:
        severity = "low"
    elif event_count <= 5:
        severity = "medium"
    else:
        severity = "high"

    return {
        "loan_id": loan_id,
        "events": nsf_events,
        "total_nsf_count": event_count,
        "total_fees": round(total_fees, 2),
        "overdraft_day_count": overdraft_days,
        "severity_assessment": severity,
    }


# =============================================================================
# 7. GET /bank-analysis/irs-payments/{loan_id}
# =============================================================================

@router.get("/bank-analysis/irs-payments/{loan_id}")
async def get_irs_payments(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get IRS payment analysis from bank statements.

    Returns IRS payments found, payment plan detection status, and
    total IRS-related payments.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    irs_payments = cached.get("irs_payments", [])
    total_amount = sum(p.get("amount", 0) for p in irs_payments)

    # Detect payment plans (regular recurring IRS payments)
    payment_plan = cached.get("irs_payment_plan_detected", False)
    estimated_tax = any(
        p.get("payment_type") == "estimated_tax" for p in irs_payments
    )

    return {
        "loan_id": loan_id,
        "payments": irs_payments,
        "total_irs_payments": round(total_amount, 2),
        "payment_plan_detected": payment_plan,
        "estimated_tax_payments": estimated_tax,
        "payment_count": len(irs_payments),
    }


# =============================================================================
# 8. GET /bank-analysis/income-verification/{loan_id}
# =============================================================================

@router.get("/bank-analysis/income-verification/{loan_id}")
async def get_income_verification(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get income verification data derived from deposit analysis.

    Returns payroll deposit patterns, estimated monthly income,
    consistency rating, and comparison against stated income if available.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    payroll = cached.get("payroll_deposits", [])
    estimated_monthly = cached.get("estimated_monthly_income", 0.0)
    consistency = cached.get("income_consistency_rating", "unknown")
    employer_names = cached.get("employer_names", [])
    frequency = cached.get("deposit_frequency", None)

    # Look up stated income from the loan for comparison
    loan_row = db.execute(
        sa_text("""
            SELECT borrower_income, borrower_monthly_income
            FROM loans
            WHERE id = :loan_id
        """),
        {"loan_id": loan_id},
    ).first()

    stated_monthly = None
    variance_pct = None
    if loan_row:
        stated_monthly = float(loan_row[1] or 0) if loan_row[1] else (
            float(loan_row[0] or 0) / 12 if loan_row[0] else None
        )
        if stated_monthly and stated_monthly > 0 and estimated_monthly > 0:
            variance_pct = round(
                ((estimated_monthly - stated_monthly) / stated_monthly) * 100, 2
            )

    return {
        "loan_id": loan_id,
        "payroll_deposits": payroll,
        "estimated_monthly_income": round(estimated_monthly, 2),
        "stated_monthly_income": round(stated_monthly, 2) if stated_monthly else None,
        "income_variance_pct": variance_pct,
        "consistency_rating": consistency,
        "employer_names": employer_names,
        "deposit_frequency": frequency,
    }


# =============================================================================
# 9. GET /bank-analysis/undisclosed-debts/{loan_id}
# =============================================================================

@router.get("/bank-analysis/undisclosed-debts/{loan_id}")
async def get_undisclosed_debts(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get potential undisclosed obligations detected in bank statements.

    Returns recurring payments that do not match known credit report items,
    including payee, amount, frequency, and category.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    debts = cached.get("recurring_obligations", [])
    total_monthly = sum(d.get("amount", 0) for d in debts)

    # Estimate DTI impact if we have income data
    estimated_income = cached.get("estimated_monthly_income", 0)
    dti_impact = None
    if estimated_income and estimated_income > 0 and total_monthly > 0:
        dti_impact = round((total_monthly / estimated_income) * 100, 2)

    return {
        "loan_id": loan_id,
        "debts": debts,
        "total_count": len(debts),
        "total_monthly_obligations": round(total_monthly, 2),
        "potential_dti_impact": dti_impact,
    }


# =============================================================================
# 10. GET /bank-analysis/risk-summary/{loan_id}
# =============================================================================

@router.get("/bank-analysis/risk-summary/{loan_id}")
async def get_risk_summary(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get overall risk summary from the bank statement analysis.

    Combines all risk factors: large deposits, NSF events, IRS payments,
    undisclosed debts, and income consistency into an overall assessment.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    risk_score = cached.get("risk_score", 0.0)
    risk_level = cached.get("risk_level", "low")
    risk_flags = cached.get("risk_flags", [])
    recommendations = cached.get("recommendations", [])

    large_deposits = cached.get("large_deposits", [])
    nsf_events = cached.get("nsf_events", [])
    irs_payments = cached.get("irs_payments", [])
    debts = cached.get("recurring_obligations", [])
    consistency = cached.get("income_consistency_rating", None)

    return {
        "loan_id": loan_id,
        "overall_risk_score": round(risk_score, 1),
        "risk_level": risk_level,
        "flags": risk_flags,
        "recommendations": recommendations,
        "large_deposit_count": len(large_deposits),
        "nsf_event_count": len(nsf_events),
        "irs_payment_count": len(irs_payments),
        "undisclosed_debt_count": len(debts),
        "income_consistency": consistency,
    }


# =============================================================================
# 11. POST /bank-analysis/compare-income/{loan_id}
# =============================================================================

@router.post("/bank-analysis/compare-income/{loan_id}")
async def compare_stated_vs_deposit_income(
    loan_id: int,
    body: CompareIncomeBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Compare stated income against income derived from bank deposits.

    Accepts the borrower's stated monthly income and returns a variance
    analysis against the deposit-based estimate.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    estimated_monthly = cached.get("estimated_monthly_income", 0.0)
    stated = body.stated_monthly_income

    if estimated_monthly <= 0:
        raise HTTPException(
            status_code=422,
            detail="No deposit-based income estimate available in analysis results",
        )

    variance = estimated_monthly - stated
    variance_pct = round((variance / stated) * 100, 2) if stated > 0 else 0.0
    abs_variance_pct = abs(variance_pct)

    # Determine assessment
    if abs_variance_pct <= 5:
        assessment = "consistent"
        severity = "low"
    elif abs_variance_pct <= 15:
        assessment = "minor_variance"
        severity = "low"
    elif abs_variance_pct <= 25:
        assessment = "moderate_variance"
        severity = "medium"
    else:
        assessment = "significant_variance"
        severity = "high"

    recommendation = None
    if variance_pct > 25:
        recommendation = "Deposit income significantly exceeds stated income. Verify additional income sources."
    elif variance_pct < -25:
        recommendation = "Stated income significantly exceeds deposit income. Request additional verification documentation."
    elif abs_variance_pct > 10:
        recommendation = "Income variance detected. Review deposit patterns for completeness."

    return {
        "loan_id": loan_id,
        "stated_monthly_income": round(stated, 2),
        "estimated_monthly_income": round(estimated_monthly, 2),
        "variance_amount": round(variance, 2),
        "variance_pct": variance_pct,
        "assessment": assessment,
        "severity": severity,
        "recommendation": recommendation,
        "deposit_frequency": cached.get("deposit_frequency"),
        "months_analyzed": cached.get("months_covered", 0),
    }


# =============================================================================
# 12. GET /bank-analysis/tasks/{loan_id}
# =============================================================================

@router.get("/bank-analysis/tasks/{loan_id}")
async def get_analysis_tasks(
    loan_id: int,
    status: Optional[str] = Query(None, description="Filter by status: pending, in_progress, completed"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get tasks generated from the bank statement analysis.

    Returns tasks such as sourcing letters needed, LOEs needed,
    IRS documentation requests, and NSF explanations.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    # Build tasks from analysis data
    tasks = []

    # Large deposits needing sourcing
    for i, deposit in enumerate(cached.get("large_deposits", [])):
        if deposit.get("sourcing_status") != "sourced":
            tasks.append({
                "task_type": "sourcing_letter",
                "description": f"Source large deposit of ${deposit.get('amount', 0):,.2f} on {deposit.get('date', 'unknown date')}",
                "related_item": f"large_deposit_{i}",
                "status": "pending",
                "priority": "high" if deposit.get("risk_level") == "high" else "medium",
            })

    # NSF events needing explanation
    nsf_events = cached.get("nsf_events", [])
    if nsf_events:
        tasks.append({
            "task_type": "nsf_explanation",
            "description": f"Obtain LOE for {len(nsf_events)} NSF/overdraft event(s)",
            "related_item": "nsf_events",
            "status": "pending",
            "priority": "high" if len(nsf_events) > 3 else "medium",
        })

    # IRS payments needing documentation
    irs_payments = cached.get("irs_payments", [])
    if irs_payments:
        tasks.append({
            "task_type": "irs_docs",
            "description": f"Request IRS documentation for {len(irs_payments)} payment(s) totaling ${sum(p.get('amount', 0) for p in irs_payments):,.2f}",
            "related_item": "irs_payments",
            "status": "pending",
            "priority": "high" if cached.get("irs_payment_plan_detected") else "medium",
        })

    # Undisclosed debts needing LOE
    debts = cached.get("recurring_obligations", [])
    if debts:
        tasks.append({
            "task_type": "loe_needed",
            "description": f"Obtain LOE for {len(debts)} potential undisclosed obligation(s)",
            "related_item": "recurring_obligations",
            "status": "pending",
            "priority": "high",
        })

    # Apply status filter
    if status:
        tasks = [t for t in tasks if t["status"] == status.lower()]

    return {
        "loan_id": loan_id,
        "tasks": tasks,
        "total_count": len(tasks),
        "pending_count": len([t for t in tasks if t["status"] == "pending"]),
        "high_priority_count": len([t for t in tasks if t["priority"] == "high"]),
    }


# =============================================================================
# 13. POST /bank-analysis/generate-report/{loan_id}
# =============================================================================

@router.post("/bank-analysis/generate-report/{loan_id}")
async def generate_bank_analysis_report(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Generate a comprehensive bank analysis PDF report.

    Returns a pre-signed URL for downloading the generated PDF.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    cached = _get_cached_analysis(db, loan_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No bank analysis found. Run analysis first.",
        )

    # Fetch loan details for the report
    loan_row = db.execute(
        sa_text("""
            SELECT loan_number, borrower_name, loan_type, amount
            FROM loans
            WHERE id = :loan_id
        """),
        {"loan_id": loan_id},
    ).first()

    try:
        from services.smart_docs.pdf_generation_service import get_pdf_generation_service
        pdf_service = get_pdf_generation_service(db)
        report_url = pdf_service.generate_bank_analysis_report(
            loan_id=loan_id,
            loan_number=loan_row[0] if loan_row else None,
            borrower_name=loan_row[1] if loan_row else None,
            analysis_data=cached,
        )
    except ImportError:
        logger.warning("PDF generation service not available")
        raise HTTPException(
            status_code=501,
            detail="PDF generation service is not yet available",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate bank analysis report for loan %s", loan_id)
        raise HTTPException(status_code=500, detail="Failed to generate bank analysis report")

    return {
        "loan_id": loan_id,
        "loan_number": loan_row[0] if loan_row else None,
        "report_url": report_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# 14. GET /bank-analysis/stats
# =============================================================================

@router.get("/bank-analysis/stats")
async def get_bank_analysis_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get organization-wide bank statement analysis statistics.

    Returns average risk score, common flags, NSF frequency,
    and large deposit frequency across all analyzed loans.
    """
    org_id = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"

    org_filter = ""
    params: dict = {}
    if org_id and not is_platform_admin:
        org_filter = "AND l.organization_id = :org_id"
        params["org_id"] = org_id

    # Get aggregate stats from loans that have bank analysis results
    summary_query = (
        "SELECT"
        " COUNT(*) AS total_analyzed,"
        " AVG((bank_analysis_result->>'risk_score')::float) AS avg_risk_score,"
        " COUNT(CASE"
        "     WHEN (bank_analysis_result->>'risk_level') = 'high' THEN 1"
        "     WHEN (bank_analysis_result->>'risk_level') = 'critical' THEN 1"
        " END) AS high_risk_count,"
        " AVG(jsonb_array_length("
        "     COALESCE(bank_analysis_result->'large_deposits', '[]'::jsonb)"
        " )) AS avg_large_deposits,"
        " AVG(jsonb_array_length("
        "     COALESCE(bank_analysis_result->'nsf_events', '[]'::jsonb)"
        " )) AS avg_nsf_events,"
        " AVG(jsonb_array_length("
        "     COALESCE(bank_analysis_result->'irs_payments', '[]'::jsonb)"
        " )) AS avg_irs_payments,"
        " AVG(jsonb_array_length("
        "     COALESCE(bank_analysis_result->'recurring_obligations', '[]'::jsonb)"
        " )) AS avg_undisclosed_debts"
        " FROM loans l"
        " WHERE l.bank_analysis_result IS NOT NULL "
        + org_filter
    )
    summary = db.execute(
        sa_text(summary_query),
        params,
    ).first()

    if not summary or not summary[0]:
        return {
            "total_analyzed": 0,
            "avg_risk_score": 0.0,
            "high_risk_count": 0,
            "avg_large_deposits_per_loan": 0.0,
            "avg_nsf_events_per_loan": 0.0,
            "avg_irs_payments_per_loan": 0.0,
            "avg_undisclosed_debts_per_loan": 0.0,
        }

    return {
        "total_analyzed": summary[0] or 0,
        "avg_risk_score": round(float(summary[1] or 0), 1),
        "high_risk_count": summary[2] or 0,
        "avg_large_deposits_per_loan": round(float(summary[3] or 0), 1),
        "avg_nsf_events_per_loan": round(float(summary[4] or 0), 1),
        "avg_irs_payments_per_loan": round(float(summary[5] or 0), 1),
        "avg_undisclosed_debts_per_loan": round(float(summary[6] or 0), 1),
    }
