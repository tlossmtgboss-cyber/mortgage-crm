"""
Lead Cascade Service

When a lead's stage changes, automatically cascade the status to associated
loans and MUM client records. Only cascades for stages where a meaningful
mapping exists — early pipeline stages (New, Attempted Contact, etc.) are
ignored because loans/MUM records typically don't exist yet.

Terminal loan stages (FUNDED, CANCELLED, DENIED, DEAD) are never regressed.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Lead stage -> (loan stage, mum status)
# None means "don't change that entity"
LEAD_TO_LOAN_MUM_MAP = {
    "Application":          ("APPLICATION", None),
    "Document Fulfillment": ("PROCESSING", None),
    "Pre-Approved":         ("APPROVED", None),
    "Disclosed":            ("DISCLOSED", None),
    "Closed":               ("FUNDED", "active"),
    "Long-Term Nurture":    ("NURTURE", "nurture"),
    "Withdrawn":            ("WITHDRAWN", "inactive"),
    "Does Not Qualify":     ("DOES_NOT_QUALIFY", "inactive"),
}

# Loans in these stages should never be changed (don't regress)
# NOTE: Previously only 4 values (missing WITHDRAWN, DOES_NOT_QUALIFY) — drift fixed 2026-03-31
from services.workflow_constants import TERMINAL_LOAN_STAGES_SET as TERMINAL_LOAN_STAGES


def cascade_lead_status(
    db: Session,
    lead_id: int,
    new_lead_stage: str,
    changed_by_id: int,
    lead_loan_number: Optional[str] = None,
    organization_id: Optional[int] = None,
) -> dict:
    """
    Cascade a lead stage change to associated loans and MUM clients.

    Returns {"loans_updated": [...], "mum_clients_updated": [...]}
    """
    mapping = LEAD_TO_LOAN_MUM_MAP.get(new_lead_stage)
    if not mapping:
        return {"loans_updated": [], "mum_clients_updated": []}

    target_loan_stage, target_mum_status = mapping
    loans_updated = []
    mum_clients_updated = []
    now = datetime.now(timezone.utc)

    # --- Update associated loans ---
    if target_loan_stage:
        # Find loans linked by lead_id OR matching loan_number
        conditions = ["l.id IS NOT NULL"]  # base truth
        params = {"terminal": tuple(TERMINAL_LOAN_STAGES)}

        or_clauses = []
        or_clauses.append("l.lead_id = :lead_id")
        params["lead_id"] = lead_id

        if lead_loan_number:
            or_clauses.append("l.loan_number = :loan_number")
            params["loan_number"] = lead_loan_number

        where_clause = f"({' OR '.join(or_clauses)})"

        # Also filter by organization if provided
        org_filter = ""
        if organization_id:
            org_filter = "AND l.organization_id = :org_id"
            params["org_id"] = organization_id

        loans = db.execute(text(f"""
            SELECT l.id, l.loan_number, l.stage
            FROM loans l
            WHERE {where_clause}
              AND COALESCE(l.stage, '') NOT IN :terminal
              {org_filter}
        """), params).fetchall()

        for loan in loans:
            loan_id = loan[0]
            loan_num = loan[1]
            old_loan_stage = loan[2]

            if old_loan_stage == target_loan_stage:
                continue  # already at target

            # Update loan stage
            db.execute(text("""
                UPDATE loans
                SET stage = :new_stage, stage_changed_at = :now
                WHERE id = :loan_id
            """), {
                "new_stage": target_loan_stage,
                "now": now,
                "loan_id": loan_id,
            })

            # Record stage history
            db.execute(text("""
                INSERT INTO stage_history
                    (entity_type, entity_id, loan_id, from_stage, to_stage,
                     changed_at, changed_by_id, notes, organization_id)
                VALUES
                    ('loan', :loan_id, :loan_id, :from_stage, :to_stage,
                     :changed_at, :changed_by_id, :notes, :org_id)
            """), {
                "loan_id": loan_id,
                "from_stage": old_loan_stage,
                "to_stage": target_loan_stage,
                "changed_at": now,
                "changed_by_id": changed_by_id,
                "notes": f"Auto-cascade from lead #{lead_id} stage change to '{new_lead_stage}'",
                "org_id": organization_id,
            })

            loans_updated.append({"id": loan_id, "loan_number": loan_num, "new_stage": target_loan_stage})
            logger.info(f"Cascade: loan {loan_id} ({loan_num}) stage {old_loan_stage} -> {target_loan_stage}")

    # --- Update associated MUM clients ---
    if target_mum_status and lead_loan_number:
        mum_params = {"loan_number": lead_loan_number, "new_status": target_mum_status}

        # Check both mum_clients and mum_client_profiles tables
        for table in ("mum_clients", "mum_client_profiles"):
            try:
                rows = db.execute(text(f"""
                    UPDATE {table}
                    SET status = :new_status
                    WHERE loan_number = :loan_number
                      AND COALESCE(status, '') != :new_status
                    RETURNING id, loan_number
                """), mum_params).fetchall()

                for row in rows:
                    mum_clients_updated.append({"id": row[0], "table": table, "new_status": target_mum_status})
                    logger.info(f"Cascade: {table} id={row[0]} status -> {target_mum_status}")
            except Exception as e:
                # Table may not exist in all environments
                logger.debug(f"Cascade: {table} update skipped — {e}")

    return {
        "loans_updated": loans_updated,
        "mum_clients_updated": mum_clients_updated,
    }
