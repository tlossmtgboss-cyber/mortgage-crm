"""
Form 1084 (Fannie Mae Cash Flow Analysis) Routes

Endpoints for generating Fannie Mae Form 1084 from income calculations.
Provides HTML preview, PDF generation, and raw structured data for
UI rendering or custom templates.

All endpoints require authentication and verify tenant isolation
before returning data.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db
from auth.dependencies import get_current_user
from database.models.income_calculation import (
    IncomeCalculation,
    IncomeSource,
    CalculationStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/income/form-1084", tags=["Form 1084"])
security = HTTPBearer()


# =============================================================================
# Pydantic Models
# =============================================================================

class Form1084PreviewResponse(BaseModel):
    """HTML preview of a Form 1084 Cash Flow Analysis."""
    html: str
    borrower_name: str
    loan_number: Optional[str] = None
    total_qualifying_monthly: float
    total_qualifying_annual: float
    generated_at: str
    sections: dict  # income breakdown by section


class Form1084GenerateRequest(BaseModel):
    """Options for PDF generation."""
    calculation_id: Optional[int] = None
    include_notes: bool = True
    include_flags: bool = True


class Form1084DataResponse(BaseModel):
    """Raw structured data for Form 1084."""
    loan_id: int
    calculation_id: int
    borrower_name: str
    loan_number: Optional[str] = None
    total_qualifying_monthly: float
    total_qualifying_annual: float
    dti_front_end: Optional[float] = None
    dti_back_end: Optional[float] = None
    calculation_method: Optional[str] = None
    calculation_status: str
    income_sources: list[dict]
    ai_flags: Optional[list] = None
    ai_recommendations: Optional[list] = None
    ai_confidence_score: Optional[int] = None
    generated_at: str


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


def _get_latest_calculation(
    db: Session, loan_id: int, calculation_id: Optional[int] = None
) -> IncomeCalculation:
    """Fetch the latest IncomeCalculation for a loan, or a specific one by ID.

    Returns the calculation or raises 404.
    """
    if calculation_id:
        calc = (
            db.query(IncomeCalculation)
            .filter(
                IncomeCalculation.id == calculation_id,
                IncomeCalculation.loan_id == loan_id,
            )
            .first()
        )
    else:
        calc = (
            db.query(IncomeCalculation)
            .filter(IncomeCalculation.loan_id == loan_id)
            .order_by(IncomeCalculation.created_at.desc())
            .first()
        )

    if not calc:
        raise HTTPException(
            status_code=404,
            detail=f"No income calculation found for loan {loan_id}",
        )
    return calc


def _get_loan_info(db: Session, loan_id: int) -> dict:
    """Fetch borrower_name and loan_number from the loans table."""
    row = db.execute(
        sa_text(
            "SELECT borrower_name, loan_number FROM loans WHERE id = :id"
        ),
        {"id": loan_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Loan not found")
    return {"borrower_name": row[0] or "Unknown", "loan_number": row[1]}


def _get_income_sources(db: Session, calculation_id: int) -> list[dict]:
    """Fetch all IncomeSource records for a calculation, serialized as dicts."""
    sources = (
        db.query(IncomeSource)
        .filter(IncomeSource.calculation_id == calculation_id)
        .order_by(IncomeSource.is_primary.desc(), IncomeSource.id)
        .all()
    )
    result = []
    for s in sources:
        result.append({
            "id": s.id,
            "source_type": s.source_type.value if s.source_type else None,
            "employer_name": s.employer_name,
            "position_title": s.position_title,
            "employment_start_date": (
                s.employment_start_date.isoformat() if s.employment_start_date else None
            ),
            "employment_years": float(s.employment_years) if s.employment_years else None,
            "is_primary": s.is_primary,
            "base_monthly_income": float(s.base_monthly_income) if s.base_monthly_income else 0.0,
            "overtime_monthly": float(s.overtime_monthly) if s.overtime_monthly else 0.0,
            "bonus_monthly": float(s.bonus_monthly) if s.bonus_monthly else 0.0,
            "commission_monthly": float(s.commission_monthly) if s.commission_monthly else 0.0,
            "other_monthly": float(s.other_monthly) if s.other_monthly else 0.0,
            "total_monthly_income": float(s.total_monthly_income) if s.total_monthly_income else 0.0,
            "total_annual_income": float(s.total_annual_income) if s.total_annual_income else 0.0,
            "trending_direction": s.trending_direction.value if s.trending_direction else None,
            "year1_income": float(s.year1_income) if s.year1_income else None,
            "year2_income": float(s.year2_income) if s.year2_income else None,
            "year_over_year_change_pct": (
                float(s.year_over_year_change_pct) if s.year_over_year_change_pct else None
            ),
            "verification_status": s.verification_status.value if s.verification_status else None,
            "ai_confidence": s.ai_confidence,
            "ai_notes": s.ai_notes,
        })
    return result


def _build_sections(income_sources: list[dict]) -> dict:
    """Organize income sources into Form 1084 sections by source type."""
    sections: dict = {}
    for src in income_sources:
        source_type = src.get("source_type", "other") or "other"
        if source_type not in sections:
            sections[source_type] = {
                "sources": [],
                "section_total_monthly": 0.0,
                "section_total_annual": 0.0,
            }
        sections[source_type]["sources"].append(src)
        sections[source_type]["section_total_monthly"] += src.get("total_monthly_income", 0.0)
        sections[source_type]["section_total_annual"] += src.get("total_annual_income", 0.0)
    return sections


def _log_generation_audit(
    db: Session,
    current_user,
    calc: IncomeCalculation,
    action: str,
) -> None:
    """Log Form 1084 generation to the audit trail."""
    try:
        from services.audit_service import create_audit_entry

        create_audit_entry(
            db=db,
            user_id=current_user.id,
            changed_by_id=current_user.id,
            change_type=action,
            entity_type="form_1084",
            entity_id=calc.id,
            before_state=None,
            after_state={
                "loan_id": calc.loan_id,
                "calculation_id": calc.id,
                "calculation_status": calc.status.value if calc.status else None,
            },
            organization_id=getattr(current_user, "organization_id", None),
        )
    except Exception as e:
        logger.warning(
            "Could not write Form 1084 audit entry: %s — falling back to logger",
            e,
        )
        logger.info(
            "FORM_1084_AUDIT action=%s user=%s calc_id=%s loan_id=%s",
            action,
            current_user.id,
            calc.id,
            calc.loan_id,
        )


# =============================================================================
# HTML Preview Generation
# =============================================================================

def _render_html_preview(
    loan_info: dict,
    calc: IncomeCalculation,
    income_sources: list[dict],
    sections: dict,
) -> str:
    """Render a basic HTML preview of the Form 1084 Cash Flow Analysis."""
    borrower_name = loan_info["borrower_name"]
    loan_number = loan_info["loan_number"] or "N/A"
    total_monthly = float(calc.total_qualifying_monthly_income or 0)
    total_annual = float(calc.total_qualifying_annual_income or 0)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build income source rows
    source_rows = ""
    for src in income_sources:
        source_rows += f"""
        <tr>
            <td>{src.get('employer_name', 'N/A')}</td>
            <td>{src.get('source_type', 'N/A')}</td>
            <td>${src.get('base_monthly_income', 0):,.2f}</td>
            <td>${src.get('overtime_monthly', 0):,.2f}</td>
            <td>${src.get('bonus_monthly', 0):,.2f}</td>
            <td>${src.get('commission_monthly', 0):,.2f}</td>
            <td>${src.get('other_monthly', 0):,.2f}</td>
            <td><strong>${src.get('total_monthly_income', 0):,.2f}</strong></td>
        </tr>"""

    # AI flags section
    flags_html = ""
    if calc.ai_flags:
        flags_items = "".join(f"<li>{flag}</li>" for flag in calc.ai_flags)
        flags_html = f"""
        <div class="flags">
            <h3>AI Flags</h3>
            <ul>{flags_items}</ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Form 1084 — Cash Flow Analysis</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
        h1 {{ color: #1a365d; border-bottom: 2px solid #1a365d; padding-bottom: 8px; }}
        h2 {{ color: #2d4a7a; margin-top: 24px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
        th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #f0f4f8; font-weight: 600; }}
        .summary {{ background: #f7fafc; border: 1px solid #e2e8f0; padding: 16px; border-radius: 6px; margin: 16px 0; }}
        .summary td {{ border: none; padding: 4px 12px; }}
        .flags {{ background: #fffbeb; border: 1px solid #f6e05e; padding: 12px; border-radius: 6px; margin: 16px 0; }}
        .flags h3 {{ margin-top: 0; color: #b7791f; }}
        .footer {{ color: #718096; font-size: 0.85em; margin-top: 24px; border-top: 1px solid #e2e8f0; padding-top: 8px; }}
    </style>
</head>
<body>
    <h1>Fannie Mae Form 1084 — Cash Flow Analysis</h1>
    <div class="summary">
        <table>
            <tr><td><strong>Borrower:</strong></td><td>{borrower_name}</td></tr>
            <tr><td><strong>Loan Number:</strong></td><td>{loan_number}</td></tr>
            <tr><td><strong>Calculation Method:</strong></td><td>{calc.calculation_method or 'Standard'}</td></tr>
            <tr><td><strong>Status:</strong></td><td>{calc.status.value if calc.status else 'N/A'}</td></tr>
            <tr><td><strong>Total Qualifying Monthly Income:</strong></td><td>${total_monthly:,.2f}</td></tr>
            <tr><td><strong>Total Qualifying Annual Income:</strong></td><td>${total_annual:,.2f}</td></tr>
        </table>
    </div>

    <h2>Income Sources</h2>
    <table>
        <thead>
            <tr>
                <th>Employer / Source</th>
                <th>Type</th>
                <th>Base</th>
                <th>Overtime</th>
                <th>Bonus</th>
                <th>Commission</th>
                <th>Other</th>
                <th>Total Monthly</th>
            </tr>
        </thead>
        <tbody>
            {source_rows}
        </tbody>
    </table>

    {flags_html}

    <div class="footer">
        Generated {generated_at} | Calculation ID: {calc.id} | AI Confidence: {calc.ai_confidence_score or 'N/A'}%
    </div>
</body>
</html>"""
    return html


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/{loan_id}/preview",
    response_model=Form1084PreviewResponse,
    summary="Preview Form 1084 as HTML",
)
async def preview_form_1084(
    loan_id: int,
    calculation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Return an HTML preview of Form 1084 for the loan's latest income calculation.

    Optionally pass `calculation_id` as a query param to preview a specific
    calculation instead of the most recent one.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    calc = _get_latest_calculation(db, loan_id, calculation_id)
    loan_info = _get_loan_info(db, loan_id)
    income_sources = _get_income_sources(db, calc.id)
    sections = _build_sections(income_sources)

    html = _render_html_preview(loan_info, calc, income_sources, sections)
    generated_at = datetime.now(timezone.utc).isoformat()

    _log_generation_audit(db, current_user, calc, "form_1084_preview")

    return Form1084PreviewResponse(
        html=html,
        borrower_name=loan_info["borrower_name"],
        loan_number=loan_info["loan_number"],
        total_qualifying_monthly=float(calc.total_qualifying_monthly_income or 0),
        total_qualifying_annual=float(calc.total_qualifying_annual_income or 0),
        generated_at=generated_at,
        sections=sections,
    )


@router.post(
    "/{loan_id}/generate",
    summary="Generate Form 1084 as PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Downloadable Form 1084 PDF",
        }
    },
)
async def generate_form_1084_pdf(
    loan_id: int,
    body: Optional[Form1084GenerateRequest] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Generate and return a downloadable PDF of Form 1084.

    Uses the loan's latest income calculation unless `calculation_id` is
    specified in the request body. Returns a PDF file with
    Content-Disposition attachment header.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    calculation_id = body.calculation_id if body else None
    include_notes = body.include_notes if body else True
    include_flags = body.include_flags if body else True

    calc = _get_latest_calculation(db, loan_id, calculation_id)
    loan_info = _get_loan_info(db, loan_id)
    income_sources = _get_income_sources(db, calc.id)
    sections = _build_sections(income_sources)

    # Generate HTML first, then convert to PDF
    html = _render_html_preview(loan_info, calc, income_sources, sections)

    # Strip flags/notes from HTML if not requested
    if not include_flags:
        # Remove the flags div from the HTML
        import re
        html = re.sub(r'<div class="flags">.*?</div>', '', html, flags=re.DOTALL)

    # Attempt PDF generation via weasyprint or fall back to HTML-as-PDF
    try:
        from services.smart_docs.form_1084_service import Form1084Service

        pdf_bytes = Form1084Service.html_to_pdf(html)
    except ImportError:
        logger.warning(
            "Form1084Service not available; attempting weasyprint directly"
        )
        try:
            from weasyprint import HTML as WeasyprintHTML

            pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        except ImportError:
            logger.error(
                "Neither Form1084Service nor weasyprint available for PDF generation"
            )
            raise HTTPException(
                status_code=503,
                detail="PDF generation service unavailable. Install weasyprint or configure Form1084Service.",
            )

    # Build filename: Form_1084_{borrower_name}_{date}.pdf
    borrower_slug = loan_info["borrower_name"].replace(" ", "_").replace("/", "_")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"Form_1084_{borrower_slug}_{date_str}.pdf"

    _log_generation_audit(db, current_user, calc, "form_1084_pdf_generate")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{loan_id}/data",
    response_model=Form1084DataResponse,
    summary="Get raw Form 1084 data",
)
async def get_form_1084_data(
    loan_id: int,
    calculation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Return raw structured data for Form 1084.

    Useful for UI rendering or custom templates. Returns all income
    sections, DTI ratios, AI flags, and source details as JSON.

    Optionally pass `calculation_id` as a query param to fetch a specific
    calculation instead of the most recent one.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    calc = _get_latest_calculation(db, loan_id, calculation_id)
    loan_info = _get_loan_info(db, loan_id)
    income_sources = _get_income_sources(db, calc.id)

    _log_generation_audit(db, current_user, calc, "form_1084_data_export")

    return Form1084DataResponse(
        loan_id=loan_id,
        calculation_id=calc.id,
        borrower_name=loan_info["borrower_name"],
        loan_number=loan_info["loan_number"],
        total_qualifying_monthly=float(calc.total_qualifying_monthly_income or 0),
        total_qualifying_annual=float(calc.total_qualifying_annual_income or 0),
        dti_front_end=float(calc.dti_front_end) if calc.dti_front_end else None,
        dti_back_end=float(calc.dti_back_end) if calc.dti_back_end else None,
        calculation_method=calc.calculation_method,
        calculation_status=calc.status.value if calc.status else "unknown",
        income_sources=income_sources,
        ai_flags=calc.ai_flags,
        ai_recommendations=calc.ai_recommendations,
        ai_confidence_score=calc.ai_confidence_score,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
