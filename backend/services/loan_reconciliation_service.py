"""
Loan State Reconciliation Service

Validates loan stage transitions from Salesforce sync, routes loans to the correct
pipeline category (Leads → Active Loans → MUM), and maintains an audit trail
of all state changes.

Integrates into salesforce_sync_service._trigger_sla_workflows() AFTER SLA task
creation but INSTEAD OF direct MUM promotion.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================

class ReconciliationAction(str, Enum):
    ALLOW = "allow"
    PROMOTE_TO_MUM = "promote"
    FLAG_FOR_REVIEW = "flag"
    SKIP = "skip"
    REACTIVATE = "reactivate"
    ARCHIVE = "archive"
    PAUSE_SLA = "pause_sla"


@dataclass
class ReconciliationResult:
    action: ReconciliationAction
    old_stage: Optional[str]
    new_stage: Optional[str]
    salesforce_raw_stage: Optional[str] = None
    should_promote_mum: bool = False
    should_pause_sla: bool = False
    should_stop_workflows: bool = False
    should_trigger_compliance: bool = False
    should_create_disposition: bool = False
    disposition_task_id: Optional[int] = None
    is_backward_movement: bool = False
    warnings: List[str] = field(default_factory=list)
    admin_review_reason: Optional[str] = None
    audit_metadata: Dict[str, Any] = field(default_factory=dict)


from services.workflow_constants import (
    STAGE_ORDER,
    FUNDED_STAGES,
    PAUSE_STAGES,
    ARCHIVE_STAGES,
    COMPLIANCE_TRIGGER_STAGES,
    ACTIVE_LOAN_STAGES as ACTIVE_STAGES,
    STAGE_TO_DATE_FIELD,
)


# =============================================================================
# Service
# =============================================================================

class LoanReconciliationService:
    """
    Reconciles loan stage transitions during Salesforce sync.

    Uses its own fresh DB session for all write operations (audit log, admin tasks,
    raw stage storage) to avoid poisoning the caller's session if any write fails.

    Usage:
        service = LoanReconciliationService(db)
        result = service.reconcile(loan_id, old_data, new_data)
        if result.should_promote_mum:
            maybe_promote_loan_to_mum_by_raw_data(...)
    """

    DEDUP_WINDOW_MINUTES = 5

    def __init__(self, db: Session):
        self.db = db
        # Create a fresh session for write operations to avoid
        # poisoning the caller's session on commit failures.
        self._own_db = None

    def _get_own_db(self):
        """Lazily create a fresh session for write operations."""
        if self._own_db is None:
            from db import SessionLocal
            self._own_db = SessionLocal()
        return self._own_db

    def _close_own_db(self):
        """Close the fresh session if it was created."""
        if self._own_db is not None:
            try:
                self._own_db.close()
            except Exception as e:
                logger.error(f"Error in _close_own_db: {e}")
            self._own_db = None

    def reconcile(
        self,
        loan_id: int,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
    ) -> ReconciliationResult:
        """
        Main entry point. Evaluates a stage transition and returns an action.

        Args:
            loan_id: The loan's database ID
            old_data: Previous loan data (from SELECT before update)
            new_data: Incoming loan data (from Salesforce mapping)

        Returns:
            ReconciliationResult with the action to take and flags for callers
        """
        old_stage = old_data.get("stage")
        new_stage = new_data.get("stage")
        raw_sf_stage = new_data.get("salesforce_raw_stage")

        # --- Idempotency: same stage, nothing to do ---
        if old_stage and new_stage and old_stage == new_stage:
            return ReconciliationResult(
                action=ReconciliationAction.SKIP,
                old_stage=old_stage,
                new_stage=new_stage,
                salesforce_raw_stage=raw_sf_stage,
                audit_metadata={"reason": "idempotent_skip"},
            )

        # --- Dedup: same transition within window ---
        if old_stage and new_stage and self._is_duplicate_transition(loan_id, old_stage, new_stage):
            return ReconciliationResult(
                action=ReconciliationAction.SKIP,
                old_stage=old_stage,
                new_stage=new_stage,
                salesforce_raw_stage=raw_sf_stage,
                audit_metadata={"reason": "duplicate_within_window"},
            )

        # --- Unmapped stage: raw SF value present but no CRM mapping ---
        if new_stage is None and raw_sf_stage:
            reason = f"Unmapped Salesforce stage: '{raw_sf_stage}'"
            self._log_unmapped_stage(loan_id, raw_sf_stage)
            result = ReconciliationResult(
                action=ReconciliationAction.FLAG_FOR_REVIEW,
                old_stage=old_stage,
                new_stage=None,
                salesforce_raw_stage=raw_sf_stage,
                admin_review_reason=reason,
                warnings=[reason],
            )
            self._write_audit_log(loan_id, result)
            return result

        # --- Route by new_stage ---
        result = self._evaluate_transition(loan_id, old_stage, new_stage, raw_sf_stage)

        # --- Backward movement detection ---
        if old_stage and new_stage:
            old_order = STAGE_ORDER.get(old_stage, 0)
            new_order = STAGE_ORDER.get(new_stage, 0)
            # Only flag backward if both are active pipeline stages (positive ordinals)
            if old_order > 0 and new_order > 0 and new_order < old_order:
                result.is_backward_movement = True
                result.warnings.append(
                    f"Backward movement: {old_stage} (pos {old_order}) → {new_stage} (pos {new_order})"
                )

        # --- Write audit log ---
        self._write_audit_log(loan_id, result)

        # --- Store raw SF stage on loan ---
        if raw_sf_stage:
            self._store_raw_sf_stage(loan_id, raw_sf_stage)

        # --- Create disposition task for LO review (defers stage application) ---
        if result.should_create_disposition:
            loan_info = self._get_loan_info(loan_id)
            if loan_info and loan_info.get("loan_officer_id"):
                task_id = self._create_disposition_task(
                    loan_id=loan_id,
                    old_stage=result.old_stage,
                    new_stage=result.new_stage,
                    raw_sf_stage=result.salesforce_raw_stage,
                    owner_id=loan_info["loan_officer_id"],
                    loan_number=loan_info.get("loan_number", ""),
                    borrower_name=loan_info.get("borrower_name", ""),
                )
                result.disposition_task_id = task_id

        # Clean up our own session
        self._close_own_db()

        return result

    # -------------------------------------------------------------------------
    # Transition evaluation
    # -------------------------------------------------------------------------

    def _evaluate_transition(
        self,
        loan_id: int,
        old_stage: Optional[str],
        new_stage: Optional[str],
        raw_sf_stage: Optional[str],
    ) -> ReconciliationResult:
        """Determine the reconciliation action for a given transition."""

        # Funded → promote to MUM (auto-applies, no disposition needed)
        if new_stage in FUNDED_STAGES:
            return ReconciliationResult(
                action=ReconciliationAction.PROMOTE_TO_MUM,
                old_stage=old_stage,
                new_stage=new_stage,
                salesforce_raw_stage=raw_sf_stage,
                should_promote_mum=True,
            )

        # Suspended → pause SLA timers (disposition task for LO review)
        if new_stage in PAUSE_STAGES:
            return ReconciliationResult(
                action=ReconciliationAction.PAUSE_SLA,
                old_stage=old_stage,
                new_stage=new_stage,
                salesforce_raw_stage=raw_sf_stage,
                should_pause_sla=True,
                should_create_disposition=True,
            )

        # Terminal stages → archive + stop workflows (disposition task for LO review)
        if new_stage in ARCHIVE_STAGES:
            return ReconciliationResult(
                action=ReconciliationAction.ARCHIVE,
                old_stage=old_stage,
                new_stage=new_stage,
                salesforce_raw_stage=raw_sf_stage,
                should_stop_workflows=True,
                should_trigger_compliance=new_stage in COMPLIANCE_TRIGGER_STAGES,
                should_create_disposition=True,
            )

        # Reactivation: from terminal/paused back to active (disposition task for LO review)
        if old_stage and old_stage in (ARCHIVE_STAGES | PAUSE_STAGES | FUNDED_STAGES):
            if new_stage and STAGE_ORDER.get(new_stage, 0) > 0:
                return ReconciliationResult(
                    action=ReconciliationAction.REACTIVATE,
                    old_stage=old_stage,
                    new_stage=new_stage,
                    salesforce_raw_stage=raw_sf_stage,
                    warnings=[f"Reactivation from {old_stage} to {new_stage}"],
                    should_create_disposition=True,
                )

        # Normal forward progression (disposition task for LO review)
        return ReconciliationResult(
            action=ReconciliationAction.ALLOW,
            old_stage=old_stage,
            new_stage=new_stage,
            salesforce_raw_stage=raw_sf_stage,
            should_create_disposition=True,
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_loan_info(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Fetch loan officer, loan number, and borrower name for a loan."""
        try:
            own_db = self._get_own_db()
            row = own_db.execute(text("""
                SELECT loan_officer_id, loan_number, borrower_name, organization_id
                FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()
            if row:
                return {
                    "loan_officer_id": row[0],
                    "loan_number": row[1],
                    "borrower_name": row[2],
                    "organization_id": row[3],
                }
            return None
        except Exception as e:
            logger.warning(f"Could not fetch loan info for {loan_id}: {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _get_loan_info (rollback): {e2}")
            return None

    def _create_disposition_task(
        self,
        loan_id: int,
        old_stage: Optional[str],
        new_stage: Optional[str],
        raw_sf_stage: Optional[str],
        owner_id: int,
        loan_number: str,
        borrower_name: str,
    ) -> Optional[int]:
        """Create a disposition task for an LO to review a Salesforce stage change.

        Returns the task ID, or None on failure. Deduplicates against existing
        pending disposition tasks for the same loan + proposed stage.
        """
        try:
            own_db = self._get_own_db()

            # Dedup: check for existing pending disposition task with same loan + proposed stage
            existing = own_db.execute(text("""
                SELECT id FROM tasks
                WHERE loan_id = :loan_id
                  AND sf_proposed_stage = :proposed
                  AND status = 'pending'
                  AND related_type = 'sf_disposition'
                LIMIT 1
            """), {"loan_id": loan_id, "proposed": new_stage}).fetchone()

            if existing:
                logger.info(
                    f"Disposition task already exists (task {existing[0]}) "
                    f"for loan {loan_id} → {new_stage}, skipping"
                )
                return existing[0]

            old_display = old_stage or "Unknown"
            new_display = new_stage or "Unknown"
            sla_date_field = STAGE_TO_DATE_FIELD.get(new_stage) if new_stage else None

            title = f"SF Status Change: {old_display} → {new_display} — {borrower_name or 'Unknown'}"
            description = (
                f"Salesforce reports a stage change for loan {loan_number or loan_id}.\n\n"
                f"Current CRM stage: {old_display}\n"
                f"Proposed new stage: {new_display}\n"
                f"Raw Salesforce value: {raw_sf_stage or 'N/A'}\n\n"
                f"Click 'Apply' to update the loan stage"
                + (f" and stamp {sla_date_field}" if sla_date_field else "")
                + f".\nClick 'Dismiss' to keep the current stage unchanged."
            )

            result = own_db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority,
                    owner_id, loan_id, related_type,
                    sf_proposed_stage, sf_current_stage, sf_raw_stage,
                    sla_date_field, due_date, created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', 'high',
                    :owner_id, :loan_id, 'sf_disposition',
                    :proposed, :current, :raw,
                    :sla_field, NOW() + INTERVAL '1 day', NOW(), NOW()
                )
                RETURNING id
            """), {
                "title": title,
                "description": description,
                "owner_id": owner_id,
                "loan_id": loan_id,
                "proposed": new_stage,
                "current": old_stage,
                "raw": raw_sf_stage,
                "sla_field": sla_date_field,
            })
            task_id = result.fetchone()[0]
            own_db.commit()
            logger.info(
                f"Created disposition task {task_id} for loan {loan_id}: "
                f"{old_display} → {new_display}"
            )
            return task_id
        except Exception as e:
            logger.warning(f"Could not create disposition task for loan {loan_id}: {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _create_disposition_task (rollback): {e2}")
            return None

    def _is_duplicate_transition(self, loan_id: int, from_stage: str, to_stage: str) -> bool:
        """Check if the same transition was logged within the dedup window."""
        try:
            own_db = self._get_own_db()
            row = own_db.execute(text("""
                SELECT id FROM loan_state_audit_log
                WHERE loan_id = :loan_id
                  AND from_stage = :from_stage
                  AND to_stage = :to_stage
                  AND created_at >= :cutoff
                LIMIT 1
            """), {
                "loan_id": loan_id,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "cutoff": datetime.now(timezone.utc) - timedelta(minutes=self.DEDUP_WINDOW_MINUTES),
            }).fetchone()
            return row is not None
        except Exception as e:
            logger.debug(f"Dedup check unavailable (table may not exist yet): {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _is_duplicate_transition (rollback): {e2}")
            return False

    def _log_unmapped_stage(self, loan_id: int, raw_stage: str) -> None:
        """Create an admin task for an unmapped Salesforce stage."""
        try:
            own_db = self._get_own_db()
            own_db.execute(text("""
                INSERT INTO tasks (
                    title, description, task_type, status, priority,
                    related_entity_type, related_entity_id, created_at
                ) VALUES (
                    :title, :description, 'admin_review', 'open', 'high',
                    'loan', :loan_id, NOW()
                )
            """), {
                "title": f"Unmapped Salesforce stage: {raw_stage}",
                "description": (
                    f"Loan ID {loan_id} received Salesforce stage '{raw_stage}' "
                    f"which has no mapping in STAGE_MAPPING. Review and add mapping "
                    f"in salesforce_sync_service.py."
                ),
                "loan_id": loan_id,
            })
            own_db.commit()
            logger.warning(f"Created admin task for unmapped SF stage '{raw_stage}' on loan {loan_id}")
        except Exception as e:
            logger.warning(f"Could not create admin task for unmapped stage: {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _log_unmapped_stage (rollback): {e2}")

    def _write_audit_log(self, loan_id: int, result: ReconciliationResult) -> None:
        """Insert an entry into loan_state_audit_log."""
        try:
            own_db = self._get_own_db()
            own_db.execute(text("""
                INSERT INTO loan_state_audit_log (
                    loan_id, from_stage, to_stage, salesforce_raw_stage,
                    action, is_backward_movement, warnings,
                    admin_review_reason, metadata, created_at
                ) VALUES (
                    :loan_id, :from_stage, :to_stage, :raw_stage,
                    :action, :is_backward, :warnings,
                    :review_reason, :metadata, NOW()
                )
            """), {
                "loan_id": loan_id,
                "from_stage": result.old_stage,
                "to_stage": result.new_stage,
                "raw_stage": result.salesforce_raw_stage,
                "action": result.action.value,
                "is_backward": result.is_backward_movement,
                "warnings": json.dumps(result.warnings),
                "review_reason": result.admin_review_reason,
                "metadata": json.dumps(result.audit_metadata),
            })
            own_db.commit()
        except Exception as e:
            logger.debug(f"Could not write audit log (table may not exist yet): {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _write_audit_log (rollback): {e2}")

    def _store_raw_sf_stage(self, loan_id: int, raw_stage: str) -> None:
        """Persist the original Salesforce stage value on the loan record."""
        try:
            own_db = self._get_own_db()
            own_db.execute(text("""
                UPDATE loans SET salesforce_raw_stage = :raw_stage WHERE id = :loan_id
            """), {"raw_stage": raw_stage, "loan_id": loan_id})
            own_db.commit()
        except Exception as e:
            logger.debug(f"Could not store raw SF stage (column may not exist yet): {e}")
            try:
                self._get_own_db().rollback()
            except Exception as e2:
                logger.error(f"Error in _store_raw_sf_stage (rollback): {e2}")
