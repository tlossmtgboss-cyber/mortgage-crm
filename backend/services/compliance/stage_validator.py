"""
Stage Transition Compliance Validator

Integration point that runs the appropriate compliance checks before
any loan stage change:

    - DENIED           -> ECOA adverse action check
    - Past SUBMITTED   -> HMDA data validation
    - CLOSING or later -> TRID fee tolerance check

Usage:
    from services.compliance.stage_validator import validate_stage_transition

    result = validate_stage_transition(db, loan_id, "CLOSING", organization_id=org_id)
    if not result["can_transition"]:
        # Block the transition
        ...
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Ordered pipeline stages for comparison
_STAGE_ORDER = [
    "APPLICATION",
    "DISCLOSED",
    "PROCESSING",
    "SUBMITTED",
    "UNDERWRITING",
    "UW_RECEIVED",
    "CONDITIONAL_APPROVAL",
    "APPROVED",
    "SUSPENDED",
    "CTC",
    "CLEAR_TO_CLOSE",
    "CLOSING",
    "DOCS",
    "DOCS_OUT",
    "FUNDED",
]

# Stages at or after CLOSING where TRID tolerance must be validated
_CLOSING_AND_LATER = frozenset({
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
})

# Stages past SUBMITTED where HMDA completeness is required
_POST_SUBMITTED_IDX = _STAGE_ORDER.index("SUBMITTED") + 1  # index of UNDERWRITING
_POST_SUBMITTED_STAGES = frozenset(_STAGE_ORDER[_POST_SUBMITTED_IDX:])

# Terminal stages
_TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
})


def _stage_index(stage: str) -> int:
    """Return the ordinal position of a stage, or -1 if not found."""
    try:
        return _STAGE_ORDER.index(stage.upper())
    except ValueError:
        return -1


def validate_stage_transition(
    db: Session,
    loan_id: int,
    target_stage: str,
    organization_id: Optional[int] = None,
    enforce: bool = False,
) -> dict:
    """Validate compliance requirements for a proposed loan stage transition.

    Args:
        db: Database session.
        loan_id: The loan being transitioned.
        target_stage: The proposed new stage (e.g. "CLOSING").
        organization_id: Optional org filter for tenant isolation.
        enforce: If True, the result includes a hard "blocked" flag
                 that the caller should use to prevent the transition.
                 If False (default), results are advisory.

    Returns:
        {
            "can_transition": bool,
            "loan_id": int,
            "target_stage": str,
            "checks_run": [str],
            "results": {
                "ecoa": {...} or None,
                "hmda": {...} or None,
                "trid": {...} or None,
            },
            "blocking_issues": [str],
            "warnings": [str],
        }
    """
    from database.models.lead_loan import Loan

    target = target_stage.upper().strip()

    # Load loan for context
    query = db.query(Loan).filter(Loan.id == loan_id)
    if organization_id:
        query = query.filter(Loan.organization_id == organization_id)
    loan = query.first()
    if not loan:
        return {
            "can_transition": False,
            "loan_id": loan_id,
            "target_stage": target,
            "error": f"Loan {loan_id} not found",
            "checks_run": [],
            "results": {},
            "blocking_issues": [f"Loan {loan_id} not found"],
            "warnings": [],
        }

    org_id = organization_id or loan.organization_id
    current_stage = (loan.stage or "").upper()

    checks_run = []
    results = {}
    blocking_issues = []
    warnings = []

    # -----------------------------------------------------------------
    # 1. DENIED -> ECOA adverse action check
    # -----------------------------------------------------------------
    if target == "DENIED":
        checks_run.append("ecoa")
        from services.compliance.ecoa_validator import ECOAValidator

        ecoa = ECOAValidator()
        ecoa_result = ecoa.validate(
            db, loan_id, organization_id=org_id,
        )
        results["ecoa"] = ecoa_result

        if not ecoa_result.get("compliant"):
            for req in ecoa_result.get("missing_requirements", []):
                if enforce:
                    blocking_issues.append(f"[ECOA] {req}")
                else:
                    warnings.append(f"[ECOA] {req}")

    # -----------------------------------------------------------------
    # 2. Past SUBMITTED -> HMDA data check
    # -----------------------------------------------------------------
    if target in _POST_SUBMITTED_STAGES or target in _TERMINAL_STAGES:
        # Only enforce if target is genuinely past SUBMITTED in the pipeline,
        # OR if it is a terminal stage that requires HMDA reporting
        # (FUNDED, DENIED, WITHDRAWN).
        hmda_reportable_terminal = {"FUNDED", "DENIED", "WITHDRAWN"}
        run_hmda = (
            target in _POST_SUBMITTED_STAGES
            or target in hmda_reportable_terminal
        )
        if run_hmda:
            checks_run.append("hmda")
            from services.compliance.hmda_validator import HMDAValidator

            hmda = HMDAValidator()
            hmda_result = hmda.validate(db, loan_id, organization_id=org_id)
            results["hmda"] = hmda_result

            if not hmda_result.get("compliant"):
                for field in hmda_result.get("missing_fields", []):
                    if enforce:
                        blocking_issues.append(
                            f"[HMDA] Required field missing: {field}"
                        )
                    else:
                        warnings.append(
                            f"[HMDA] Required field missing: {field}"
                        )
            # Pass through HMDA warnings
            for w in hmda_result.get("warnings", []):
                warnings.append(f"[HMDA] {w}")

    # -----------------------------------------------------------------
    # 3. CLOSING or later -> TRID fee tolerance check
    # -----------------------------------------------------------------
    if target in _CLOSING_AND_LATER:
        checks_run.append("trid")
        from services.compliance.trid_validator import TRIDValidator

        trid = TRIDValidator()
        trid_result = trid.validate(db, loan_id, organization_id=org_id)
        results["trid"] = trid_result

        if not trid_result.get("compliant"):
            for v in trid_result.get("violations", []):
                msg = v.get("message", f"TRID violation: {v.get('fee_name')}")
                if enforce:
                    blocking_issues.append(f"[TRID] {msg}")
                else:
                    warnings.append(f"[TRID] {msg}")

    can_transition = len(blocking_issues) == 0

    # Log the stage-transition validation
    _log_stage_validation(
        db, loan_id, org_id, current_stage, target,
        can_transition, checks_run, blocking_issues, warnings,
    )

    return {
        "can_transition": can_transition,
        "loan_id": loan_id,
        "loan_number": loan.loan_number,
        "current_stage": current_stage,
        "target_stage": target,
        "checks_run": checks_run,
        "results": results,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
    }


def _log_stage_validation(
    db: Session, loan_id: int, organization_id: int,
    current_stage: str, target_stage: str,
    can_transition: bool, checks_run: list,
    blocking: list, warnings: list,
):
    """Log stage-transition validation to the compliance audit log."""
    try:
        from database.models.compliance_log import ComplianceDecisionLog

        log_entry = ComplianceDecisionLog(
            organization_id=organization_id,
            decision_type="stage_transition_validation",
            contact_id=loan_id,
            decision="allowed" if can_transition else "blocked",
            reason=(
                f"Stage transition {current_stage} -> {target_stage}: "
                + ("passed" if can_transition else f"{len(blocking)} blocking issue(s)")
            ),
            details={
                "loan_id": loan_id,
                "current_stage": current_stage,
                "target_stage": target_stage,
                "checks_run": checks_run,
                "blocking_count": len(blocking),
                "warning_count": len(warnings),
                "blocking_issues": blocking,
            },
        )
        db.add(log_entry)
    except Exception as e:
        logger.warning(f"Failed to log stage-transition validation: {e}")
