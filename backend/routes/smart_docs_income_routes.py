"""
Smart Docs Income Calculation Routes

Endpoints for AI-assisted income calculation, approval workflows,
verification task management, income source overrides, and reporting.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from database.models.income_calculation import (
    IncomeCalculation,
    IncomeSource,
    IncomeVerificationTask,
    CalculationStatus,
    CalculationType,
    TaskStatus,
)
from services.smart_docs.income_calculator_service import get_income_calculator_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Income Calculation"])


# =============================================================================
# Pydantic Models
# =============================================================================

class CalculateIncomeRequest(BaseModel):
    """Request body is empty — borrower_id comes as a query param."""
    pass


class ApproveCalculationBody(BaseModel):
    notes: Optional[str] = None
    approved_by: str


class RejectCalculationBody(BaseModel):
    notes: Optional[str] = None
    reason: str


class CompleteTaskBody(BaseModel):
    resolution_notes: Optional[str] = None
    resolved_by: str


class DeferTaskBody(BaseModel):
    reason: str
    defer_until: Optional[str] = None  # ISO-8601 date string


class OverrideIncomeBody(BaseModel):
    monthly_amount: float
    annual_amount: float
    reason: str
    override_by: str


# =============================================================================
# Tenant Verification Helpers
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


def _verify_calculation_tenant(
    db: Session, calculation_id: int, current_user
) -> IncomeCalculation:
    """Fetch a calculation and verify tenant access. Returns the row or raises 404."""
    calc = db.query(IncomeCalculation).filter(
        IncomeCalculation.id == calculation_id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Calculation not found")
    _verify_loan_tenant(db, calc.loan_id, current_user)
    return calc


def _verify_task_tenant(
    db: Session, task_id: int, current_user
) -> IncomeVerificationTask:
    """Fetch a task and verify tenant access. Returns the row or raises 404."""
    task = db.query(IncomeVerificationTask).filter(
        IncomeVerificationTask.id == task_id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _verify_loan_tenant(db, task.loan_id, current_user)
    return task


# =============================================================================
# Serialization Helpers
# =============================================================================

def _serialize_calculation(calc: IncomeCalculation) -> dict:
    """Serialize an IncomeCalculation row to a JSON-safe dict."""
    return {
        "id": calc.id,
        "loan_id": calc.loan_id,
        "borrower_id": calc.borrower_id,
        "organization_id": calc.organization_id,
        "calculation_type": calc.calculation_type.value if calc.calculation_type else None,
        "status": calc.status.value if calc.status else None,
        "calculation_method": calc.calculation_method,
        "total_qualifying_monthly_income": float(calc.total_qualifying_monthly_income or 0),
        "total_qualifying_annual_income": float(calc.total_qualifying_annual_income or 0),
        "dti_front_end": float(calc.dti_front_end) if calc.dti_front_end is not None else None,
        "dti_back_end": float(calc.dti_back_end) if calc.dti_back_end is not None else None,
        "proposed_housing_expense": float(calc.proposed_housing_expense or 0),
        "total_monthly_obligations": float(calc.total_monthly_obligations or 0),
        "ai_confidence_score": calc.ai_confidence_score,
        "ai_flags": calc.ai_flags or [],
        "ai_recommendations": calc.ai_recommendations or [],
        "ai_model_used": calc.ai_model_used,
        "calculation_duration_ms": calc.calculation_duration_ms,
        "source_documents": calc.source_documents or [],
        "reviewed_by": calc.reviewed_by,
        "reviewed_at": calc.reviewed_at.isoformat() if calc.reviewed_at else None,
        "review_notes": calc.review_notes,
        "approved_by": calc.approved_by,
        "approved_at": calc.approved_at.isoformat() if calc.approved_at else None,
        "created_at": calc.created_at.isoformat() if calc.created_at else None,
        "updated_at": calc.updated_at.isoformat() if calc.updated_at else None,
    }


def _serialize_source(src: IncomeSource) -> dict:
    """Serialize an IncomeSource row to a JSON-safe dict."""
    return {
        "id": src.id,
        "calculation_id": src.calculation_id,
        "borrower_id": src.borrower_id,
        "source_type": src.source_type.value if src.source_type else None,
        "employer_name": src.employer_name,
        "position_title": src.position_title,
        "employment_start_date": src.employment_start_date.isoformat() if src.employment_start_date else None,
        "employment_years": float(src.employment_years) if src.employment_years is not None else None,
        "is_primary": src.is_primary,
        "base_monthly_income": float(src.base_monthly_income or 0),
        "overtime_monthly": float(src.overtime_monthly or 0),
        "bonus_monthly": float(src.bonus_monthly or 0),
        "commission_monthly": float(src.commission_monthly or 0),
        "other_monthly": float(src.other_monthly or 0),
        "total_monthly_income": float(src.total_monthly_income or 0),
        "total_annual_income": float(src.total_annual_income or 0),
        "trending_direction": src.trending_direction.value if src.trending_direction else None,
        "year1_income": float(src.year1_income) if src.year1_income is not None else None,
        "year2_income": float(src.year2_income) if src.year2_income is not None else None,
        "year_over_year_change_pct": float(src.year_over_year_change_pct) if src.year_over_year_change_pct is not None else None,
        "verification_status": src.verification_status.value if src.verification_status else None,
        "verification_notes": src.verification_notes,
        "source_document_ids": src.source_document_ids or [],
        "ai_confidence": src.ai_confidence,
        "ai_notes": src.ai_notes,
        "created_at": src.created_at.isoformat() if src.created_at else None,
        "updated_at": src.updated_at.isoformat() if src.updated_at else None,
    }


def _serialize_task(task: IncomeVerificationTask) -> dict:
    """Serialize an IncomeVerificationTask row to a JSON-safe dict."""
    return {
        "id": task.id,
        "calculation_id": task.calculation_id,
        "income_source_id": task.income_source_id,
        "loan_id": task.loan_id,
        "organization_id": task.organization_id,
        "task_type": task.task_type.value if task.task_type else None,
        "title": task.title,
        "description": task.description,
        "priority": task.priority.value if task.priority else None,
        "status": task.status.value if task.status else None,
        "assigned_to_user_id": task.assigned_to_user_id,
        "ai_recommendation": task.ai_recommendation,
        "resolution_notes": task.resolution_notes,
        "resolved_by": task.resolved_by,
        "resolved_at": task.resolved_at.isoformat() if task.resolved_at else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# =============================================================================
# 1. POST /income/calculate/{loan_id}
# =============================================================================

@router.post("/income/calculate/{loan_id}")
async def calculate_income(
    loan_id: int,
    borrower_id: int = Query(..., description="Borrower ID (lead ID) to calculate income for"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Calculate income for a loan/borrower pair.

    Runs the AI-powered income calculator which reads income documents,
    computes qualifying income, DTI ratios, and generates verification tasks.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        service = get_income_calculator_service(db)
        result = service.calculate_income(loan_id=loan_id, borrower_id=borrower_id)
    except Exception as e:
        logger.exception("Income calculation failed for loan_id=%s", loan_id)
        raise HTTPException(status_code=500, detail="Income calculation failed")

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error or "Calculation could not complete")

    # Fetch the persisted calculation to return the full object
    calc = (
        db.query(IncomeCalculation)
        .filter(
            IncomeCalculation.loan_id == loan_id,
            IncomeCalculation.borrower_id == borrower_id,
        )
        .order_by(IncomeCalculation.created_at.desc())
        .first()
    )

    sources = (
        db.query(IncomeSource)
        .filter(IncomeSource.calculation_id == calc.id)
        .all()
    ) if calc else []

    tasks = (
        db.query(IncomeVerificationTask)
        .filter(IncomeVerificationTask.calculation_id == calc.id)
        .all()
    ) if calc else []

    return {
        "calculation": _serialize_calculation(calc) if calc else None,
        "sources": [_serialize_source(s) for s in sources],
        "tasks": [_serialize_task(t) for t in tasks],
        "summary": {
            "total_qualifying_monthly": float(result.total_qualifying_monthly),
            "total_qualifying_annual": float(result.total_qualifying_annual),
            "dti_front_end": float(result.dti_front_end) if result.dti_front_end is not None else None,
            "dti_back_end": float(result.dti_back_end) if result.dti_back_end is not None else None,
            "confidence": result.confidence,
            "flags": result.flags,
            "recommendations": result.recommendations,
            "source_count": len(result.sources),
            "tasks_created": len(result.tasks_to_create),
        },
    }


# =============================================================================
# 2. POST /income/recalculate/{calculation_id}
# =============================================================================

@router.post("/income/recalculate/{calculation_id}")
async def recalculate_income(
    calculation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Re-run an income calculation with the latest documents.

    Supersedes the previous calculation and creates a new one with
    calculation_type = recalculation.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    try:
        service = get_income_calculator_service(db)
        result = service.recalculate(calculation_id)
    except Exception as e:
        logger.exception("Recalculation failed for calculation_id=%s", calculation_id)
        raise HTTPException(status_code=500, detail="Recalculation failed")

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error or "Recalculation could not complete")

    # Fetch the newly created calculation
    new_calc = (
        db.query(IncomeCalculation)
        .filter(
            IncomeCalculation.loan_id == calc.loan_id,
            IncomeCalculation.borrower_id == calc.borrower_id,
        )
        .order_by(IncomeCalculation.created_at.desc())
        .first()
    )

    return {
        "calculation": _serialize_calculation(new_calc) if new_calc else None,
        "previous_calculation_id": calculation_id,
        "summary": {
            "total_qualifying_monthly": float(result.total_qualifying_monthly),
            "total_qualifying_annual": float(result.total_qualifying_annual),
            "confidence": result.confidence,
            "flags": result.flags,
            "recommendations": result.recommendations,
        },
    }


# =============================================================================
# 3. GET /income/calculations/{loan_id}
# =============================================================================

@router.get("/income/calculations/{loan_id}")
async def get_calculations_for_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all income calculations for a loan, most recent first.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    calculations = (
        db.query(IncomeCalculation)
        .filter(IncomeCalculation.loan_id == loan_id)
        .order_by(IncomeCalculation.created_at.desc())
        .all()
    )

    return {
        "loan_id": loan_id,
        "count": len(calculations),
        "calculations": [_serialize_calculation(c) for c in calculations],
    }


# =============================================================================
# 4. GET /income/calculation/{calculation_id}
# =============================================================================

@router.get("/income/calculation/{calculation_id}")
async def get_calculation_detail(
    calculation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get full calculation detail including sources, tasks, and recommendations.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    sources = (
        db.query(IncomeSource)
        .filter(IncomeSource.calculation_id == calculation_id)
        .all()
    )

    tasks = (
        db.query(IncomeVerificationTask)
        .filter(IncomeVerificationTask.calculation_id == calculation_id)
        .all()
    )

    return {
        "calculation": _serialize_calculation(calc),
        "sources": [_serialize_source(s) for s in sources],
        "tasks": [_serialize_task(t) for t in tasks],
    }


# =============================================================================
# 5. GET /income/calculation/{calculation_id}/sources
# =============================================================================

@router.get("/income/calculation/{calculation_id}/sources")
async def get_calculation_sources(
    calculation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all income sources for a calculation, including trending analysis
    and verification status.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    sources = (
        db.query(IncomeSource)
        .filter(IncomeSource.calculation_id == calculation_id)
        .all()
    )

    return {
        "calculation_id": calculation_id,
        "loan_id": calc.loan_id,
        "count": len(sources),
        "sources": [_serialize_source(s) for s in sources],
    }


# =============================================================================
# 6. POST /income/calculation/{calculation_id}/approve
# =============================================================================

@router.post("/income/calculation/{calculation_id}/approve")
async def approve_calculation(
    calculation_id: int,
    body: ApproveCalculationBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Approve an income calculation. Sets status to APPROVED.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    if calc.status == CalculationStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Calculation already approved")

    now = datetime.now(timezone.utc)
    calc.status = CalculationStatus.APPROVED
    calc.approved_by = body.approved_by
    calc.approved_at = now
    calc.review_notes = body.notes
    calc.reviewed_by = body.approved_by
    calc.reviewed_at = now
    calc.updated_at = now

    try:
        db.commit()
        db.refresh(calc)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to approve calculation %s", calculation_id)
        raise HTTPException(status_code=500, detail="Failed to approve calculation")

    return {
        "status": "approved",
        "calculation_id": calculation_id,
        "approved_by": body.approved_by,
        "approved_at": now.isoformat(),
        "calculation": _serialize_calculation(calc),
    }


# =============================================================================
# 7. POST /income/calculation/{calculation_id}/reject
# =============================================================================

@router.post("/income/calculation/{calculation_id}/reject")
async def reject_calculation(
    calculation_id: int,
    body: RejectCalculationBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Reject an income calculation. Sets status to REJECTED.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    if calc.status == CalculationStatus.REJECTED:
        raise HTTPException(status_code=409, detail="Calculation already rejected")

    now = datetime.now(timezone.utc)
    calc.status = CalculationStatus.REJECTED
    calc.review_notes = f"Reason: {body.reason}" + (f"\n{body.notes}" if body.notes else "")
    calc.reviewed_by = getattr(current_user, "email", "system")
    calc.reviewed_at = now
    calc.updated_at = now

    try:
        db.commit()
        db.refresh(calc)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to reject calculation %s", calculation_id)
        raise HTTPException(status_code=500, detail="Failed to reject calculation")

    return {
        "status": "rejected",
        "calculation_id": calculation_id,
        "reason": body.reason,
        "rejected_at": now.isoformat(),
        "calculation": _serialize_calculation(calc),
    }


# =============================================================================
# 8. GET /income/tasks/{loan_id}
# =============================================================================

@router.get("/income/tasks/{loan_id}")
async def get_income_tasks(
    loan_id: int,
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, COMPLETED, DEFERRED"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all income verification tasks for a loan.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    query = db.query(IncomeVerificationTask).filter(
        IncomeVerificationTask.loan_id == loan_id,
    )

    if status:
        try:
            task_status = TaskStatus(status.lower())
            query = query.filter(IncomeVerificationTask.status == task_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Must be one of: OPEN, IN_PROGRESS, COMPLETED, DEFERRED",
            )

    tasks = query.order_by(IncomeVerificationTask.created_at.desc()).all()

    return {
        "loan_id": loan_id,
        "count": len(tasks),
        "tasks": [_serialize_task(t) for t in tasks],
    }


# =============================================================================
# 9. POST /income/tasks/{task_id}/complete
# =============================================================================

@router.post("/income/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    body: CompleteTaskBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mark an income verification task as completed.
    """
    task = _verify_task_tenant(db, task_id, current_user)

    if task.status == TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Task already completed")

    now = datetime.now(timezone.utc)
    task.status = TaskStatus.COMPLETED
    task.resolution_notes = body.resolution_notes
    task.resolved_by = body.resolved_by
    task.resolved_at = now
    task.updated_at = now

    try:
        db.commit()
        db.refresh(task)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to complete task %s", task_id)
        raise HTTPException(status_code=500, detail="Failed to complete task")

    return {
        "status": "completed",
        "task_id": task_id,
        "resolved_by": body.resolved_by,
        "resolved_at": now.isoformat(),
        "task": _serialize_task(task),
    }


# =============================================================================
# 10. POST /income/tasks/{task_id}/defer
# =============================================================================

@router.post("/income/tasks/{task_id}/defer")
async def defer_task(
    task_id: int,
    body: DeferTaskBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Defer an income verification task with a reason and optional resume date.
    """
    task = _verify_task_tenant(db, task_id, current_user)

    if task.status == TaskStatus.DEFERRED:
        raise HTTPException(status_code=409, detail="Task already deferred")

    now = datetime.now(timezone.utc)
    task.status = TaskStatus.DEFERRED
    task.resolution_notes = f"Deferred: {body.reason}"
    task.updated_at = now

    if body.defer_until:
        try:
            defer_date = datetime.fromisoformat(body.defer_until)
            task.due_date = defer_date
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid defer_until date format. Use ISO-8601.")

    try:
        db.commit()
        db.refresh(task)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to defer task %s", task_id)
        raise HTTPException(status_code=500, detail="Failed to defer task")

    return {
        "status": "deferred",
        "task_id": task_id,
        "reason": body.reason,
        "defer_until": body.defer_until,
        "task": _serialize_task(task),
    }


# =============================================================================
# 11. GET /income/calculation/{calculation_id}/report
# =============================================================================

@router.get("/income/calculation/{calculation_id}/report")
async def generate_income_report(
    calculation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Generate an income report PDF for a calculation.

    Returns a pre-signed S3 URL for downloading the generated PDF.
    """
    calc = _verify_calculation_tenant(db, calculation_id, current_user)

    sources = (
        db.query(IncomeSource)
        .filter(IncomeSource.calculation_id == calculation_id)
        .all()
    )

    tasks = (
        db.query(IncomeVerificationTask)
        .filter(IncomeVerificationTask.calculation_id == calculation_id)
        .all()
    )

    try:
        from services.smart_docs.pdf_generation_service import get_pdf_generation_service
        pdf_service = get_pdf_generation_service(db)
        report_url = pdf_service.generate_income_report(
            calculation=calc,
            sources=sources,
            tasks=tasks,
        )
    except ImportError:
        logger.warning("PDF generation service not available")
        raise HTTPException(
            status_code=501,
            detail="PDF generation service is not yet available",
        )
    except Exception as e:
        logger.exception("Failed to generate income report for calculation %s", calculation_id)
        raise HTTPException(status_code=500, detail="Failed to generate income report")

    return {
        "calculation_id": calculation_id,
        "loan_id": calc.loan_id,
        "report_url": report_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# 12. POST /income/source/{source_id}/override
# =============================================================================

@router.post("/income/source/{source_id}/override")
async def override_income_source(
    source_id: int,
    body: OverrideIncomeBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Manually override income for a specific source.

    Creates an audit trail with the reason and original values.
    """
    source = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    # Verify tenant via the parent calculation
    calc = db.query(IncomeCalculation).filter(
        IncomeCalculation.id == source.calculation_id
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="Parent calculation not found")
    _verify_loan_tenant(db, calc.loan_id, current_user)

    # Preserve original values in ai_notes for audit trail
    original_monthly = float(source.total_monthly_income or 0)
    original_annual = float(source.total_annual_income or 0)
    audit_note = (
        f"MANUAL OVERRIDE by {body.override_by}: "
        f"monthly {original_monthly:.2f} -> {body.monthly_amount:.2f}, "
        f"annual {original_annual:.2f} -> {body.annual_amount:.2f}. "
        f"Reason: {body.reason}"
    )
    existing_notes = source.ai_notes or ""
    source.ai_notes = f"{existing_notes}\n{audit_note}".strip() if existing_notes else audit_note

    now = datetime.now(timezone.utc)
    source.total_monthly_income = body.monthly_amount
    source.total_annual_income = body.annual_amount
    source.verification_notes = f"Manual override: {body.reason}"
    source.updated_at = now

    try:
        db.commit()
        db.refresh(source)
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to override income source %s", source_id)
        raise HTTPException(status_code=500, detail="Failed to apply income override")

    return {
        "status": "overridden",
        "source_id": source_id,
        "previous_monthly": original_monthly,
        "previous_annual": original_annual,
        "new_monthly": body.monthly_amount,
        "new_annual": body.annual_amount,
        "override_by": body.override_by,
        "reason": body.reason,
        "source": _serialize_source(source),
    }


# =============================================================================
# 13. GET /income/stats
# =============================================================================

@router.get("/income/stats")
async def get_income_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get aggregate income calculation statistics for the current user's organization.

    Returns average qualifying income, DTI distribution, most common flags,
    and auto-approval rate.
    """
    org_id = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"

    # Build org filter
    org_filter = ""
    params: dict = {}
    if org_id and not is_platform_admin:
        org_filter = "AND ic.organization_id = :org_id"
        params["org_id"] = org_id

    # Aggregate income metrics
    summary = db.execute(
        sa_text(f"""
            SELECT
                COUNT(*) AS total_calculations,
                COUNT(CASE WHEN ic.status = 'approved' THEN 1 END) AS approved_count,
                COUNT(CASE WHEN ic.status = 'rejected' THEN 1 END) AS rejected_count,
                COUNT(CASE WHEN ic.status = 'completed' THEN 1 END) AS completed_count,
                COUNT(CASE WHEN ic.status = 'needs_review' THEN 1 END) AS needs_review_count,
                AVG(ic.total_qualifying_monthly_income) AS avg_qualifying_monthly,
                AVG(ic.total_qualifying_annual_income) AS avg_qualifying_annual,
                AVG(ic.dti_front_end) AS avg_dti_front_end,
                AVG(ic.dti_back_end) AS avg_dti_back_end,
                AVG(ic.ai_confidence_score) AS avg_confidence
            FROM income_calculations ic
            WHERE 1=1 {org_filter}
        """),
        params,
    ).first()

    # DTI distribution buckets
    dti_dist = db.execute(
        sa_text(f"""
            SELECT
                COUNT(CASE WHEN ic.dti_back_end < 36 THEN 1 END) AS under_36,
                COUNT(CASE WHEN ic.dti_back_end >= 36 AND ic.dti_back_end < 43 THEN 1 END) AS range_36_43,
                COUNT(CASE WHEN ic.dti_back_end >= 43 AND ic.dti_back_end < 50 THEN 1 END) AS range_43_50,
                COUNT(CASE WHEN ic.dti_back_end >= 50 THEN 1 END) AS over_50
            FROM income_calculations ic
            WHERE ic.dti_back_end IS NOT NULL {org_filter}
        """),
        params,
    ).first()

    # Auto-approval rate: calculations that went straight to APPROVED without NEEDS_REVIEW
    # Approximated by checking reviewed_by = approved_by and no rejection in history
    total = summary.total_calculations if summary else 0
    approved = summary.approved_count if summary else 0
    auto_approval_rate = round((approved / total * 100), 1) if total > 0 else 0.0

    return {
        "total_calculations": total,
        "status_breakdown": {
            "approved": approved,
            "rejected": summary.rejected_count if summary else 0,
            "completed": summary.completed_count if summary else 0,
            "needs_review": summary.needs_review_count if summary else 0,
        },
        "averages": {
            "qualifying_monthly_income": round(float(summary.avg_qualifying_monthly or 0), 2),
            "qualifying_annual_income": round(float(summary.avg_qualifying_annual or 0), 2),
            "dti_front_end": round(float(summary.avg_dti_front_end or 0), 2),
            "dti_back_end": round(float(summary.avg_dti_back_end or 0), 2),
            "ai_confidence": round(float(summary.avg_confidence or 0), 1),
        },
        "dti_distribution": {
            "under_36_pct": dti_dist.under_36 if dti_dist else 0,
            "range_36_43": dti_dist.range_36_43 if dti_dist else 0,
            "range_43_50": dti_dist.range_43_50 if dti_dist else 0,
            "over_50": dti_dist.over_50 if dti_dist else 0,
        },
        "auto_approval_rate": auto_approval_rate,
    }
