"""
Portal Stage Transition Service
================================
Maps CRM Loan.stage changes to PURLWorkspace.status transitions.

Lifecycle mapping:
  DISCLOSED (LE Pending) → WorkspaceStatus.ACTIVE_LOAN
  CTC / CLEAR_TO_CLOSE   → WorkspaceStatus.CLOSING
  FUNDED                  → WorkspaceStatus.POST_CLOSE

Forward-only guard prevents status regression (e.g. ACTIVE_LOAN → LEAD).
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Status ordering — higher number = later in lifecycle. Never regress.
_STATUS_ORDER = {
    "lead": 0,
    "application": 1,
    "active_loan": 2,
    "closing": 3,
    "post_close": 4,
}

# CRM loan stages that trigger portal workspace transitions.
# Keys are UPPERCASE to match Loan.stage values in the DB.
_STAGE_TO_PORTAL_STATUS = {
    "DISCLOSED": "active_loan",
    "PROCESSING": "active_loan",
    "SUBMITTED": "active_loan",
    "UNDERWRITING": "active_loan",
    "UW_RECEIVED": "active_loan",
    "CONDITIONAL_APPROVAL": "active_loan",
    "APPROVED": "active_loan",
    "CTC": "closing",
    "CLEAR_TO_CLOSE": "closing",
    "CLOSING": "closing",
    "DOCS": "closing",
    "DOCS_OUT": "closing",
    "FUNDED": "post_close",
}


def sync_portal_stage(
    db: Session,
    loan_id: int,
    new_stage: str,
    old_stage: Optional[str] = None,
) -> Optional[str]:
    """
    Sync a PURL workspace status based on the CRM loan's new stage.

    Looks up the workspace via PURLLoan.main_loan_id → workspace_id,
    falling back to loan_number match.

    Returns the new workspace status string if a transition occurred, else None.
    Portal sync failures are logged but never raised — caller should wrap in
    try/except regardless.
    """
    from models.purl import PURLLoan, PURLWorkspace, WorkspaceStatus
    from services.purl_workspace_service import PURLWorkspaceService

    # Normalize stage to uppercase for lookup
    stage_upper = (new_stage or "").upper().strip()
    target_status = _STAGE_TO_PORTAL_STATUS.get(stage_upper)

    if not target_status:
        # Stage doesn't map to a portal transition (e.g. APPLICATION, NURTURE)
        return None

    # Find the PURL workspace linked to this loan
    purl_loan = db.query(PURLLoan).filter(
        PURLLoan.main_loan_id == loan_id
    ).first()

    if not purl_loan:
        # Fallback: try matching by loan_number
        try:
            from database.models import Loan
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if loan and loan.loan_number:
                purl_loan = db.query(PURLLoan).filter(
                    PURLLoan.loan_number == loan.loan_number
                ).first()
        except Exception as e:
            logger.debug(f"Loan number fallback lookup failed: {e}")

    if not purl_loan or not purl_loan.workspace_id:
        logger.debug(
            f"No PURL workspace linked to loan {loan_id} — skipping portal transition"
        )
        return None

    workspace = db.query(PURLWorkspace).filter(
        PURLWorkspace.id == purl_loan.workspace_id
    ).first()

    if not workspace:
        logger.warning(
            f"PURLWorkspace {purl_loan.workspace_id} not found for loan {loan_id}"
        )
        return None

    current_status = (workspace.status or "").lower().strip()
    current_order = _STATUS_ORDER.get(current_status, -1)
    target_order = _STATUS_ORDER.get(target_status, -1)

    # Forward-only guard
    if target_order <= current_order:
        logger.debug(
            f"Portal stage skip: workspace {workspace.id} already at "
            f"'{current_status}' (order {current_order}), "
            f"target '{target_status}' (order {target_order}) would be regression"
        )
        return None

    # Perform the transition via PURLWorkspaceService
    target_enum = WorkspaceStatus(target_status)

    svc = PURLWorkspaceService(db)
    success = svc.update_workspace_status(workspace.id, target_enum)

    if success:
        logger.info(
            f"Portal transition: workspace {workspace.id} (slug={workspace.slug}) "
            f"'{current_status}' → '{target_status}' "
            f"(triggered by loan {loan_id} stage → {stage_upper})"
        )
        return target_status
    else:
        logger.error(
            f"Portal transition failed: workspace {workspace.id}, "
            f"'{current_status}' → '{target_status}'"
        )
        return None
