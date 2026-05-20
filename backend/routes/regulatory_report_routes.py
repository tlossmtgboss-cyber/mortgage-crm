"""
Regulatory Report Routes — CMP-008

HMDA LAR export, state regulatory filing generation, and compliance report management:
    POST /api/v1/admin/compliance/hmda/generate       — Generate HMDA LAR export
    GET  /api/v1/admin/compliance/hmda/fields/{loan_id} — HMDA field validation for loan
    POST /api/v1/admin/compliance/state-filing/generate — Generate state-specific filing
    GET  /api/v1/admin/compliance/reports               — List generated reports
    GET  /api/v1/admin/compliance/reports/{id}/download  — Download report file
"""
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone, date
import json
import csv
import io
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# HMDA Field Definitions (Regulation C — 12 CFR 1003)
# ============================================================================

HMDA_LAR_FIELDS = [
    "record_identifier", "lei", "activity_year", "uli",
    "application_date", "loan_type", "loan_purpose", "preapproval",
    "construction_method", "occupancy_type", "loan_amount", "action_taken",
    "action_taken_date", "state_code", "county_code", "census_tract",
    "applicant_ethnicity_1", "applicant_race_1", "applicant_sex",
    "co_applicant_ethnicity_1", "co_applicant_race_1", "co_applicant_sex",
    "applicant_age", "co_applicant_age", "income",
    "purchaser_type", "rate_spread", "hoepa_status",
    "lien_status", "applicant_credit_score", "co_applicant_credit_score",
    "applicant_credit_score_model", "denial_reason_1", "denial_reason_2",
    "denial_reason_3", "total_loan_costs", "total_points_and_fees",
    "origination_charges", "discount_points", "lender_credits",
    "interest_rate", "prepayment_penalty_term", "dti_ratio",
    "combined_ltv", "loan_term", "introductory_rate_period",
    "property_value", "manufactured_home_type", "manufactured_home_land_type",
    "total_units", "multifamily_units", "submission_of_application",
    "initially_payable_to", "nmls_id",
]

# HMDA Action Taken codes
ACTION_TAKEN_MAP = {
    "funded": 1,           # Loan originated
    "approved": 2,         # Application approved but not accepted
    "denied": 3,           # Application denied
    "withdrawn": 4,        # Application withdrawn by applicant
    "cancelled": 5,        # File closed for incompleteness
    "purchased": 6,        # Loan purchased by institution
}

# HMDA Loan Type codes
LOAN_TYPE_MAP = {
    "conventional": 1,
    "fha": 2,
    "va": 3,
    "usda": 4,
}

# HMDA Loan Purpose codes
LOAN_PURPOSE_MAP = {
    "purchase": 1,
    "refinance": 31,
    "cash_out_refinance": 32,
    "home_improvement": 2,
    "other": 4,
}


from pydantic import validator

class HMDAGenerateRequest(BaseModel):
    year: int
    quarter: Optional[int] = None  # None = full year
    include_denied: bool = True
    include_withdrawn: bool = True

    @validator("year")
    def year_in_range(cls, v):
        if not (2000 <= v <= 2100):
            raise ValueError("year must be between 2000 and 2100")
        return v

    @validator("quarter")
    def quarter_in_range(cls, v):
        if v is not None and not (1 <= v <= 4):
            raise ValueError("quarter must be 1-4")
        return v


class StateFilingRequest(BaseModel):
    state_code: str  # e.g., "CA", "TX", "NY"
    filing_type: str  # "quarterly_activity", "annual_report", "license_renewal"
    period_start: str  # ISO date
    period_end: str  # ISO date


def register_regulatory_report_routes(app, get_db, get_current_user, **kwargs):
    """Register regulatory report generation endpoints (CMP-008)."""

    def _require_compliance(current_user):
        role = getattr(current_user, 'permission_role', None) or getattr(current_user, 'role', None)
        if role not in ('admin', 'site_admin', 'compliance', 'leadership'):
            raise HTTPException(status_code=403, detail="Compliance access required")

    # ==================================================================
    # HMDA LAR Export Generation
    # ==================================================================
    @app.post("/api/v1/admin/compliance/hmda/generate", tags=["Regulatory Reports"])
    async def generate_hmda_lar(
        body: HMDAGenerateRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Generate HMDA Loan Application Register (LAR) export (CMP-008).

        Produces a pipe-delimited file per CFPB HMDA filing specifications.
        Covers all loans with action taken during the reporting period.
        """
        _require_compliance(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        # Build date range filter
        if body.quarter:
            q_start_month = (body.quarter - 1) * 3 + 1
            q_end_month = body.quarter * 3
            date_filter = "AND EXTRACT(MONTH FROM l.status_changed_at) BETWEEN :q_start_month AND :q_end_month"
            period_label = f"{body.year}-Q{body.quarter}"
        else:
            date_filter = ""
            q_start_month = None
            q_end_month = None
            period_label = str(body.year)

        # Status filter based on HMDA-reportable actions
        status_list = ["'funded'", "'approved'"]
        if body.include_denied:
            status_list.append("'denied'")
        if body.include_withdrawn:
            status_list.extend(["'withdrawn'", "'cancelled'"])

        # Query loans for the reporting period
        status_in = ",".join(status_list)
        query_sql = """
            SELECT
                l.id, l.loan_number, l.loan_type, l.loan_purpose, l.loan_amount,
                l.interest_rate, l.status, l.status_changed_at,
                l.property_address, l.property_state, l.property_county,
                l.property_zip, l.property_type, l.occupancy_type,
                l.borrower_name, l.borrower_credit_score,
                l.dti_ratio, l.ltv_ratio, l.loan_term_months,
                l.denial_reason, l.property_value,
                u.nmls_id as lo_nmls,
                o.name as org_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            LEFT JOIN organizations o ON o.id = l.organization_id
            WHERE l.organization_id = :org_id
              AND EXTRACT(YEAR FROM l.status_changed_at) = :year
              AND l.status IN (""" + status_in + """)
              """ + date_filter + """
            ORDER BY l.status_changed_at
        """
        loans = await db.execute(text(query_sql), {
            "org_id": org_id, "year": body.year,
            **({"q_start_month": q_start_month, "q_end_month": q_end_month} if q_start_month else {}),
        }).fetchall()

        # Generate LAR records
        lar_records = []
        validation_warnings = []

        for loan in loans:
            record = {
                "record_identifier": 2,  # LAR record
                "lei": "",  # Org's LEI — should come from org settings
                "activity_year": body.year,
                "uli": loan[1] or f"ULI-{loan[0]}",
                "application_date": "",
                "loan_type": LOAN_TYPE_MAP.get(loan[2], 1),
                "loan_purpose": LOAN_PURPOSE_MAP.get(loan[3], 4),
                "preapproval": 2,  # Not applicable
                "construction_method": 1,  # Site-built
                "occupancy_type": {"primary": 1, "second_home": 2, "investment": 3}.get(loan[13], 1),
                "loan_amount": int(loan[4] or 0),
                "action_taken": ACTION_TAKEN_MAP.get(loan[6], 5),
                "action_taken_date": str(loan[7].date()) if loan[7] else "",
                "state_code": loan[9] or "",
                "county_code": loan[10] or "",
                "census_tract": "",
                "applicant_ethnicity_1": "",  # Collected separately
                "applicant_race_1": "",
                "applicant_sex": "",
                "co_applicant_ethnicity_1": "",
                "co_applicant_race_1": "",
                "co_applicant_sex": "",
                "applicant_age": "",
                "co_applicant_age": "",
                "income": "",
                "purchaser_type": 0,
                "rate_spread": "",
                "hoepa_status": 2,  # Not a HOEPA loan (default)
                "lien_status": 1,   # First lien (default)
                "applicant_credit_score": loan[15] or "",
                "co_applicant_credit_score": "",
                "applicant_credit_score_model": 1 if loan[15] else "",
                "denial_reason_1": loan[19] or "" if loan[6] == "denied" else "",
                "denial_reason_2": "",
                "denial_reason_3": "",
                "total_loan_costs": "",
                "total_points_and_fees": "",
                "origination_charges": "",
                "discount_points": "",
                "lender_credits": "",
                "interest_rate": float(loan[5]) if loan[5] else "",
                "prepayment_penalty_term": "",
                "dti_ratio": float(loan[16]) if loan[16] else "",
                "combined_ltv": float(loan[17]) if loan[17] else "",
                "loan_term": loan[18] or "",
                "introductory_rate_period": "",
                "property_value": int(loan[20]) if loan[20] else "",
                "manufactured_home_type": "",
                "manufactured_home_land_type": "",
                "total_units": 1,
                "multifamily_units": "",
                "submission_of_application": 1,
                "initially_payable_to": 1,
                "nmls_id": loan[21] or "",
            }

            # Validate required fields
            missing_fields = []
            for required in ["loan_amount", "action_taken", "state_code"]:
                if not record.get(required):
                    missing_fields.append(required)
            if missing_fields:
                validation_warnings.append({
                    "loan_id": loan[0],
                    "loan_number": loan[1],
                    "missing_fields": missing_fields,
                })

            lar_records.append(record)

        # Generate pipe-delimited LAR file content
        lar_lines = []
        for rec in lar_records:
            line = "|".join(str(rec.get(f, "")) for f in HMDA_LAR_FIELDS)
            lar_lines.append(line)

        lar_content = "\n".join(lar_lines)

        # Store generated report
        report_id_row = await db.execute(text("""
            INSERT INTO regulatory_reports
                (organization_id, report_type, report_name, period_label,
                 record_count, content_format, content_data,
                 validation_warnings, generated_by_id, generated_at)
            VALUES
                (:org_id, 'hmda_lar', :name, :period, :count, 'pipe_delimited',
                 :content, :warnings, :user_id, NOW())
            RETURNING id
        """), {
            "org_id": org_id,
            "name": f"HMDA LAR — {period_label}",
            "period": period_label,
            "count": len(lar_records),
            "content": lar_content,
            "warnings": json.dumps(validation_warnings),
            "user_id": current_user.id,
        })
        report_id = report_id_row.fetchone()[0]
        await db.commit()

        return {
            "report_id": report_id,
            "report_type": "hmda_lar",
            "period": period_label,
            "record_count": len(lar_records),
            "validation_warnings": len(validation_warnings),
            "warnings": validation_warnings[:10],  # First 10 for preview
            "message": f"HMDA LAR generated: {len(lar_records)} records for {period_label}",
        }

    # ==================================================================
    # HMDA Field Validation for Single Loan
    # ==================================================================
    @app.get("/api/v1/admin/compliance/hmda/fields/{loan_id}", tags=["Regulatory Reports"])
    async def validate_hmda_fields(
        loan_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Validate HMDA-required fields for a single loan (CMP-008)."""
        _require_compliance(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        loan = await db.execute(text("""
            SELECT l.id, l.loan_number, l.loan_type, l.loan_purpose, l.loan_amount,
                   l.interest_rate, l.status, l.property_state, l.property_county,
                   l.borrower_credit_score, l.dti_ratio, l.ltv_ratio, l.denial_reason,
                   l.property_value, l.loan_term_months, l.occupancy_type
            FROM loans l
            WHERE l.id = :id AND l.organization_id = :org_id
        """), {"id": loan_id, "org_id": org_id}).fetchone()

        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Check each required HMDA field
        field_status = {}
        required_fields = {
            "loan_type": loan[2],
            "loan_purpose": loan[3],
            "loan_amount": loan[4],
            "interest_rate": loan[5],
            "property_state": loan[7],
            "property_county": loan[8],
            "credit_score": loan[9],
            "dti_ratio": loan[10],
            "ltv_ratio": loan[11],
            "property_value": loan[13],
            "loan_term": loan[14],
            "occupancy_type": loan[15],
        }

        missing = []
        present = []
        for field_name, value in required_fields.items():
            if value is None or value == "":
                field_status[field_name] = "missing"
                missing.append(field_name)
            else:
                field_status[field_name] = "present"
                present.append(field_name)

        # Denial-specific requirements
        if loan[6] == "denied" and not loan[12]:
            field_status["denial_reason"] = "missing"
            missing.append("denial_reason")

        completeness = len(present) / len(required_fields) * 100 if required_fields else 0

        return {
            "loan_id": loan_id,
            "loan_number": loan[1],
            "hmda_ready": len(missing) == 0,
            "completeness_pct": round(completeness, 1),
            "present_fields": present,
            "missing_fields": missing,
            "field_status": field_status,
        }

    # ==================================================================
    # State Regulatory Filing Generation
    # ==================================================================
    @app.post("/api/v1/admin/compliance/state-filing/generate", tags=["Regulatory Reports"])
    async def generate_state_filing(
        body: StateFilingRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Generate state-specific regulatory filing (CMP-008)."""
        _require_compliance(current_user)
        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        state = body.state_code.upper()

        # Get loan activity for the period
        activity = await db.execute(text("""
            SELECT
                COUNT(*) as total_loans,
                COUNT(CASE WHEN status = 'funded' THEN 1 END) as funded,
                COUNT(CASE WHEN status = 'denied' THEN 1 END) as denied,
                COUNT(CASE WHEN status = 'withdrawn' THEN 1 END) as withdrawn,
                COALESCE(SUM(CASE WHEN status = 'funded' THEN loan_amount END), 0) as funded_volume,
                COALESCE(AVG(CASE WHEN status = 'funded' THEN interest_rate END), 0) as avg_rate,
                COUNT(DISTINCT loan_officer_id) as active_los
            FROM loans
            WHERE organization_id = :org_id
              AND property_state = :state
              AND status_changed_at BETWEEN :start AND :end
        """), {
            "org_id": org_id, "state": state,
            "start": body.period_start, "end": body.period_end,
        }).fetchone()

        # Get LO license info for this state
        los = await db.execute(text("""
            SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.nmls_id, u.email
            FROM users u
            LEFT JOIN email_signatures es ON es.user_id = u.id
            WHERE u.organization_id = :org_id
              AND u.permission_role IN ('loan_officer', 'branch_manager')
              AND u.is_active = true
        """), {"org_id": org_id}).fetchall()

        filing_data = {
            "state": state,
            "filing_type": body.filing_type,
            "period": f"{body.period_start} to {body.period_end}",
            "summary": {
                "total_applications": activity[0],
                "loans_originated": activity[1],
                "loans_denied": activity[2],
                "loans_withdrawn": activity[3],
                "total_funded_volume": float(activity[4]),
                "avg_interest_rate": round(float(activity[5]), 3),
                "active_loan_officers": activity[6],
            },
            "licensed_personnel": [
                {"id": lo[0], "name": lo[1], "nmls_id": lo[2], "email": lo[3]}
                for lo in los
            ],
        }

        # Store the report
        report_id_row = await db.execute(text("""
            INSERT INTO regulatory_reports
                (organization_id, report_type, report_name, period_label,
                 record_count, content_format, content_data,
                 validation_warnings, generated_by_id, generated_at)
            VALUES
                (:org_id, :rtype, :name, :period, :count, 'json',
                 :content, '[]', :user_id, NOW())
            RETURNING id
        """), {
            "org_id": org_id,
            "rtype": f"state_filing_{state.lower()}",
            "name": f"{state} {body.filing_type.replace('_', ' ').title()} — {body.period_start} to {body.period_end}",
            "period": f"{body.period_start}/{body.period_end}",
            "count": activity[0],
            "content": json.dumps(filing_data),
            "user_id": current_user.id,
        })
        report_id = report_id_row.fetchone()[0]
        await db.commit()

        return {
            "report_id": report_id,
            "report_type": f"state_filing_{state.lower()}",
            "filing_data": filing_data,
            "message": f"{state} {body.filing_type} generated",
        }

    # ==================================================================
    # List Generated Reports
    # ==================================================================
    @app.get("/api/v1/admin/compliance/reports", tags=["Regulatory Reports"])
    async def list_regulatory_reports(
        report_type: Optional[str] = Query(None),
        limit: int = Query(50, le=200),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """List all generated regulatory reports for the organization (CMP-008)."""
        _require_compliance(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        query = """
            SELECT id, report_type, report_name, period_label,
                   record_count, content_format, generated_at,
                   validation_warnings
            FROM regulatory_reports
            WHERE organization_id = :org_id
        """
        params = {"org_id": org_id, "limit": limit}
        if report_type:
            query += " AND report_type = :rtype"
            params["rtype"] = report_type

        query += " ORDER BY generated_at DESC LIMIT :limit"

        rows = await db.execute(text(query), params).fetchall()
        reports = []
        for r in rows:
            warnings = json.loads(r[7]) if r[7] else []
            reports.append({
                "id": r[0], "report_type": r[1], "report_name": r[2],
                "period_label": r[3], "record_count": r[4],
                "content_format": r[5], "generated_at": str(r[6]) if r[6] else None,
                "warning_count": len(warnings),
            })

        return {"reports": reports, "count": len(reports)}

    # ==================================================================
    # Download Report
    # ==================================================================
    @app.get("/api/v1/admin/compliance/reports/{report_id}/download", tags=["Regulatory Reports"])
    async def download_regulatory_report(
        request: Request,
        report_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Download a generated regulatory report (CMP-008)."""
        _require_compliance(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        row = await db.execute(text("""
            SELECT report_type, report_name, content_format, content_data,
                   validation_warnings, generated_at, record_count
            FROM regulatory_reports
            WHERE id = :id AND organization_id = :org_id
        """), {"id": report_id, "org_id": org_id}).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Report not found")

        try:
            from utils.export_audit import log_export_event, _get_client_ip
            log_export_event(
                db=db, user_id=current_user.id, organization_id=org_id,
                resource_type="regulatory_report", export_format=row[2] or "json",
                ip_address=_get_client_ip(request),
                details={"report_id": report_id, "report_type": row[0], "record_count": row[6]},
            )
        except Exception as _exc:  # noqa: BLE001
            pass

        return {
            "report_type": row[0],
            "report_name": row[1],
            "content_format": row[2],
            "content": row[3],
            "validation_warnings": json.loads(row[4]) if row[4] else [],
            "generated_at": str(row[5]) if row[5] else None,
            "record_count": row[6],
        }

    logger.info("  Regulatory report routes registered (CMP-008)")
