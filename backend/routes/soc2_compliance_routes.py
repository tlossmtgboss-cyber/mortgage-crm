"""
SOC 2 Compliance Admin Routes — Perennia AI
============================================

Admin-only endpoints for SOC 2 Type II readiness assessment, evidence
collection, and security control inventory.

Prefix: /api/v1/admin/soc2
Tags:   ["SOC 2 Compliance"]

Endpoints:
    GET  /api/v1/admin/soc2/readiness  — Run readiness assessment (PASS/FAIL/PARTIAL per control)
    GET  /api/v1/admin/soc2/evidence   — Generate evidence package
    GET  /api/v1/admin/soc2/controls   — List all security controls with status

All endpoints require admin, site_admin, or platform_admin permission_role.

Registration pattern: APIRouter (auto-included by FastAPI app discovery).
Uses lazy runtime imports from main to avoid circular dependencies, following
the same pattern as routes/security_dashboard_routes.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1/admin/soc2",
    tags=["SOC 2 Compliance"],
)

# ============================================================================
# ADMIN ROLES — mirrors routes/backup_routes.py
# ============================================================================

_ADMIN_ROLES = ("admin", "site_admin", "platform_admin")


# ============================================================================
# RUNTIME DEPENDENCY HELPERS
# (Lazy imports to avoid circular import at module load time)
# ============================================================================

def _get_current_user_dep():
    """Return get_current_user from main at request time."""
    import main  # noqa: PLC0415
    return main.get_current_user


def _get_db_dep():
    """Return get_db from database at request time."""
    from database import get_db  # noqa: PLC0415
    return get_db


# ============================================================================
# HELPERS
# ============================================================================

def _require_admin(current_user: Any) -> None:
    """Raise HTTP 403 if the user is not an admin role."""
    role = getattr(current_user, "permission_role", "")
    if role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Access denied. Required role: {_ADMIN_ROLES}. "
                f"Your role: '{role}'."
            ),
        )


def _run_readiness() -> Dict[str, Any]:
    """
    Execute the readiness checklist and return the full report as a dict.
    Imports soc2.readiness_checklist at call time so the module is not loaded
    until the endpoint is actually hit.
    """
    try:
        import sys
        import os
        # Ensure backend root is on sys.path so 'soc2' package is importable
        backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)

        from dataclasses import asdict
        from soc2.readiness_checklist import run_assessment, Status

        report = run_assessment()
        report_dict = asdict(report)

        # Add a top-level pass_rate for quick dashboard consumption
        total = sum(report_dict["summary"].values())
        passed = report_dict["summary"].get(Status.PASS.value, 0)
        partial = report_dict["summary"].get(Status.PARTIAL.value, 0)
        report_dict["pass_rate_pct"] = round(
            ((passed + partial * 0.5) / max(total, 1)) * 100, 1
        )
        return report_dict

    except Exception as exc:
        logger.exception("Readiness checklist execution failed")
        raise HTTPException(
            status_code=500,
            detail=f"Readiness assessment failed: {str(exc)}",
        )


def _run_evidence_collection(
    sections: Optional[List[str]] = None,
    connect_db: bool = False,
) -> Dict[str, Any]:
    """
    Execute the evidence collector and return the package as a dict.
    """
    try:
        import sys
        import os
        backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)

        from dataclasses import asdict
        from soc2.evidence_collector import collect_evidence

        package = collect_evidence(sections=sections, connect_db=connect_db)
        return asdict(package)

    except Exception as exc:
        logger.exception("Evidence collection failed")
        raise HTTPException(
            status_code=500,
            detail=f"Evidence collection failed: {str(exc)}",
        )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get(
    "/readiness",
    summary="Run SOC 2 Readiness Assessment",
    response_description=(
        "Structured readiness report with PASS/FAIL/PARTIAL status per control "
        "across all five Trust Service Criteria."
    ),
)
async def get_soc2_readiness(
    current_user=Depends(_get_current_user_dep()),
) -> Dict[str, Any]:
    """
    Execute the SOC 2 Type II readiness checklist against the live codebase.

    Returns a structured report with:
    - Status (PASS / PARTIAL / FAIL / SKIP) for each control
    - Trust Service Criterion mapping (Security, Availability, Processing
      Integrity, Confidentiality, Privacy)
    - Evidence file paths for each control
    - Required gaps with remediation guidance
    - Optional recommendations

    This endpoint scans the backend directory on each call. For large codebases
    the scan takes < 1 second. Results are not cached — each call reflects the
    current state of the codebase.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)

    logger.info(
        "SOC 2 readiness assessment requested by %s (%s)",
        getattr(current_user, "email", "unknown"),
        getattr(current_user, "permission_role", "unknown"),
    )

    report = _run_readiness()

    return {
        "requested_by": getattr(current_user, "email", "unknown"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "report": report,
    }


@router.get(
    "/evidence",
    summary="Generate SOC 2 Evidence Package",
    response_description=(
        "Evidence package with structured data for each SOC 2 evidence section."
    ),
)
async def get_soc2_evidence(
    section: Optional[str] = Query(
        default=None,
        description=(
            "Specific evidence section to collect. "
            "Leave blank for all sections. "
            "Options: endpoints, security_headers, rbac_roles, audit_log_sample, "
            "encryption_inventory, access_matrix, vendor_registry, retention_policies, "
            "mfa_config, incident_summary."
        ),
    ),
    include_db: bool = Query(
        default=False,
        description=(
            "Attempt live database queries for richer evidence "
            "(audit log samples, user counts, vendor registry). "
            "Requires DATABASE_URL to be set."
        ),
    ),
    current_user=Depends(_get_current_user_dep()),
) -> Dict[str, Any]:
    """
    Generate a SOC 2 evidence package for auditor review.

    Collects evidence from the codebase and optionally the live database,
    covering:
    - API endpoint authentication inventory
    - Security header configuration
    - RBAC role definitions and user counts
    - Audit log sample (last 25 events)
    - Encryption configuration inventory
    - Access control matrix by role
    - Third-party vendor risk registry
    - Data retention policy table
    - MFA configuration and adoption rate
    - Security incident summary

    Use `include_db=true` to pull live database evidence (audit logs,
    user counts, incident records). Requires DATABASE_URL.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)

    logger.info(
        "SOC 2 evidence collection requested by %s (section=%s, include_db=%s)",
        getattr(current_user, "email", "unknown"),
        section or "all",
        include_db,
    )

    sections = [section] if section else None
    package = _run_evidence_collection(sections=sections, connect_db=include_db)

    return {
        "requested_by": getattr(current_user, "email", "unknown"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "include_db": include_db,
        "evidence": package,
    }


@router.get(
    "/controls",
    summary="List All Security Controls with Status",
    response_description="Flat list of all security controls with current status.",
)
async def get_soc2_controls(
    criterion: Optional[str] = Query(
        default=None,
        description=(
            "Filter by Trust Service Criterion. "
            "Options: Security (CC), Availability (A), "
            "Processing Integrity (PI), Confidentiality (C), Privacy (P)."
        ),
    ),
    status: Optional[str] = Query(
        default=None,
        description=(
            "Filter by status. Options: PASS, PARTIAL, FAIL, SKIP."
        ),
    ),
    current_user=Depends(_get_current_user_dep()),
) -> Dict[str, Any]:
    """
    Return a flat inventory of all security controls with their current status.

    Useful for:
    - Security dashboard widgets
    - Gap analysis spreadsheets
    - Auditor control listings (the POC — Point of Contact list)
    - CI/CD status badges

    Supports filtering by Trust Service Criterion and status.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)

    report = _run_readiness()
    checks: List[Dict] = report.get("checks", [])

    # Apply filters
    if criterion:
        criterion_lower = criterion.lower()
        checks = [
            c for c in checks
            if criterion_lower in (c.get("criterion") or "").lower()
        ]

    if status:
        status_upper = status.upper()
        checks = [
            c for c in checks
            if (c.get("status") or "").upper() == status_upper
        ]

    # Build concise summary per criterion
    by_criterion: Dict[str, Dict] = {}
    for check in report.get("checks", []):
        crit = check.get("criterion", "Unknown")
        if crit not in by_criterion:
            by_criterion[crit] = {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "SKIP": 0}
        s = (check.get("status") or "SKIP").upper()
        by_criterion[crit][s] = by_criterion[crit].get(s, 0) + 1

    return {
        "requested_by": getattr(current_user, "email", "unknown"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": report.get("overall_status", "UNKNOWN"),
        "summary": report.get("summary", {}),
        "pass_rate_pct": report.get("pass_rate_pct", 0),
        "by_criterion": by_criterion,
        "controls": checks,
        "total_controls": len(report.get("checks", [])),
        "filtered_controls": len(checks),
        "required_gaps": report.get("gaps", []),
        "recommendations": report.get("recommendations", []),
    }
