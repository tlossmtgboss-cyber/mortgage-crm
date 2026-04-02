"""
Date Reconciliation Service
Tracks date field updates from Salesforce and handles reconciliation when data can't be matched.

Key responsibilities:
1. Track which date fields changed during sync
2. Push date updates to MUM client profiles for non-closed loans
3. Create reconciliation tasks when loan/borrower can't be found
"""
import logging
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Date fields that trigger reconciliation tracking
DATE_FIELDS = {
    # Lead & Application Phase
    "prospect_date", "application_date", "le_pending_date", "credit_only_date",
    "file_received_date", "preapproval_date",

    # Lock Phase
    "lock_date", "lock_expiration_date",

    # Processing & Underwriting Phase
    "uw_received_date", "conditions_for_review_date", "suspended_date",
    "loan_approved_date", "approved_not_accepted_date", "approval_expires_date",

    # Appraisal Phase
    "appraisal_ordered_date", "appraisal_received_date", "appraisal_docs_expire_date",

    # Closing Disclosure Phase
    "cd_requested_date", "cd_sent_to_borrower_date", "cd_acknowledged_date",

    # Clear to Close & Docs Phase
    "clear_to_close_date", "docs_ordered_date", "docs_out_date", "credit_docs_expire_date",

    # Funding Phase
    "scheduled_closing_date", "scheduled_funding_date", "funds_ordered_date",
    "funds_sent_date", "funded_date", "closing_date", "first_payment_date",

    # Post-Closing
    "investor_purchased_date",

    # Status Changes
    "withdrawn_date", "contract_received_date",
}

# Closed/Funded stages - loans in these stages should update MUM clients
CLOSED_STAGES = {"FUNDED", "funded", "Funded", "CLOSED", "closed", "Closed"}


@dataclass
class DateUpdate:
    """Represents a date field update from Salesforce."""
    salesforce_id: str
    field_name: str
    old_value: Optional[date]
    new_value: date
    borrower_name: Optional[str] = None
    loan_number: Optional[str] = None
    borrower_email: Optional[str] = None


@dataclass
class DateReconciliationResult:
    """Result of processing date updates."""
    dates_tracked: int = 0
    mum_clients_updated: int = 0
    tasks_created: int = 0
    errors: List[str] = field(default_factory=list)


class DateReconciliationService:
    """
    Service for tracking date field changes and creating reconciliation tasks
    when data can't be matched to existing loans/borrowers.
    """

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def track_date_updates(
        self,
        salesforce_id: str,
        old_loan_data: Optional[Dict[str, Any]],
        new_loan_data: Dict[str, Any],
        matched_loan_id: Optional[int] = None,
    ) -> List[DateUpdate]:
        """
        Track which date fields changed during a sync operation.

        Args:
            salesforce_id: Salesforce record ID
            old_loan_data: Previous loan data (None if new record)
            new_loan_data: New loan data from Salesforce
            matched_loan_id: ID of matched loan in CRM (None if no match)

        Returns:
            List of DateUpdate objects for changed date fields
        """
        updates = []

        for field_name in DATE_FIELDS:
            new_value = new_loan_data.get(field_name)

            if new_value is None:
                continue

            # Normalize new_value to date
            if isinstance(new_value, datetime):
                new_value = new_value.date()
            elif isinstance(new_value, str):
                try:
                    new_value = datetime.fromisoformat(new_value.replace('Z', '+00:00')).date()
                except (ValueError, AttributeError):
                    continue
            elif not isinstance(new_value, date):
                continue

            old_value = None
            if old_loan_data:
                old_value = old_loan_data.get(field_name)
                if isinstance(old_value, datetime):
                    old_value = old_value.date()

            # Only track if value changed
            if old_value != new_value:
                updates.append(DateUpdate(
                    salesforce_id=salesforce_id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    borrower_name=new_loan_data.get("borrower_name"),
                    loan_number=new_loan_data.get("loan_number"),
                    borrower_email=new_loan_data.get("borrower_email"),
                ))

                logger.info(
                    f"Date update detected: {field_name} changed from {old_value} to {new_value} "
                    f"for SF ID {salesforce_id}"
                )

        return updates

    def process_date_update(
        self,
        update: DateUpdate,
        matched_loan_id: Optional[int],
        loan_stage: Optional[str],
    ) -> DateReconciliationResult:
        """
        Process a single date update.

        - If loan is closed/funded: Update MUM client profile
        - If loan not found: Create reconciliation task
        - If loan is active (not closed): Update loan dates normally

        Args:
            update: The date update to process
            matched_loan_id: ID of matched loan (None if not found)
            loan_stage: Current stage of the loan (if matched)

        Returns:
            DateReconciliationResult with processing outcome
        """
        result = DateReconciliationResult()
        result.dates_tracked = 1

        try:
            # Case 1: No matched loan - create reconciliation task
            if matched_loan_id is None:
                self._create_reconciliation_task(update)
                result.tasks_created = 1
                logger.info(f"Created reconciliation task for unmatched date update: {update.field_name}")
                return result

            # Case 2: Closed/Funded loan - update MUM client profile
            if loan_stage and loan_stage in CLOSED_STAGES:
                updated = self._update_mum_client_dates(matched_loan_id, update)
                if updated:
                    result.mum_clients_updated = 1
                return result

            # Case 3: Active loan - date is already being applied through normal sync
            # Just log for tracking purposes
            self._log_date_update(matched_loan_id, update)

        except Exception as e:
            result.errors.append(f"Error processing date update for {update.salesforce_id}: {str(e)}")
            logger.error(f"Error processing date update: {e}")

        return result

    def _create_reconciliation_task(self, update: DateUpdate) -> int:
        """
        Create a reconciliation task when a date update can't be matched to an existing loan.

        Returns:
            ID of the created task
        """
        # Build descriptive task title
        borrower_info = update.borrower_name or update.loan_number or f"SF:{update.salesforce_id[:8]}"
        field_label = update.field_name.replace("_", " ").title()

        title = f"Import Borrower Data - {field_label} update for {borrower_info}"

        description = f"""A date field update was received from Salesforce but the loan/borrower could not be found in the CRM.

**Salesforce Record ID:** {update.salesforce_id}
**Field Updated:** {field_label}
**New Value:** {update.new_value.strftime('%m/%d/%Y') if update.new_value else 'N/A'}
**Previous Value:** {update.old_value.strftime('%m/%d/%Y') if update.old_value else 'N/A (new record)'}

**Borrower Information from Salesforce:**
- Name: {update.borrower_name or 'Not provided'}
- Loan Number: {update.loan_number or 'Not provided'}
- Email: {update.borrower_email or 'Not provided'}

**Action Required:**
1. Import or create the borrower/loan record in the CRM
2. Link the Salesforce record to the CRM loan
3. Re-run the Salesforce sync to apply the date update

**Quick Actions:**
- [Import from Salesforce] - Click to import this specific record
- [Create New Loan] - Manually create a loan record and link it
"""

        result = self.db.execute(text("""
            INSERT INTO tasks (
                title, description, status, priority, source,
                entity_type, owner_id, created_by_id, created_at, updated_at
            ) VALUES (
                :title, :description, 'pending', 'high', 'Salesforce Date Sync',
                'reconciliation', :owner_id, :owner_id, NOW(), NOW()
            ) RETURNING id
        """), {
            "title": title,
            "description": description,
            "owner_id": self.user_id,
        })

        task_id = result.scalar()
        self.db.commit()

        logger.info(f"Created reconciliation task {task_id} for Salesforce ID {update.salesforce_id}")
        return task_id

    def _update_mum_client_dates(self, loan_id: int, update: DateUpdate) -> bool:
        """
        Update date fields on MUM client profile for closed loans.

        For closed/funded loans, date updates should go to the MUM client profile
        which tracks the ongoing relationship with the borrower.

        Returns:
            True if MUM client was updated
        """
        # Find MUM client by loan number or loan_id
        mum_client = self.db.execute(text("""
            SELECT mc.id, mc.name, mc.loan_number
            FROM mum_clients mc
            JOIN loans l ON (mc.loan_number = l.loan_number OR mc.loan_id = l.id)
            WHERE l.id = :loan_id
            LIMIT 1
        """), {"loan_id": loan_id}).fetchone()

        if not mum_client:
            # Try to find by loan number directly
            loan = self.db.execute(text("""
                SELECT loan_number, borrower_name FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            if loan and loan[0]:
                mum_client = self.db.execute(text("""
                    SELECT id, name, loan_number FROM mum_clients
                    WHERE loan_number = :loan_number
                """), {"loan_number": loan[0]}).fetchone()

        if not mum_client:
            logger.warning(f"No MUM client found for loan {loan_id}, cannot update dates")
            return False

        # Map specific date fields to MUM client profile fields
        # Most dates don't apply to MUM clients, but some might be relevant
        mum_date_mappings = {
            "funded_date": "original_close_date",
            "closing_date": "original_close_date",
            "first_payment_date": None,  # Could add if needed
        }

        mum_field = mum_date_mappings.get(update.field_name)

        if mum_field:
            sql = "UPDATE mum_clients SET " + mum_field + " = :new_value, updated_at = NOW() WHERE id = :mum_id"
            self.db.execute(text(sql), {
                "new_value": update.new_value,
                "mum_id": mum_client[0],
            })
            self.db.commit()

            logger.info(f"Updated MUM client {mum_client[0]} field {mum_field} to {update.new_value}")
            return True

        # Log the date update for tracking even if not mapped to MUM field
        self._log_mum_date_event(mum_client[0], update)
        return True

    def _log_mum_date_event(self, mum_client_id: int, update: DateUpdate):
        """Log a date update event for a MUM client."""
        # Check if mum_client_events table exists, if not just log
        try:
            self.db.execute(text("""
                INSERT INTO mum_client_events (
                    mum_client_id, event_type, event_data, created_at
                ) VALUES (
                    :mum_id, 'date_update', :event_data::jsonb, NOW()
                )
            """), {
                "mum_id": mum_client_id,
                "event_data": {
                    "field": update.field_name,
                    "old_value": update.old_value.isoformat() if update.old_value else None,
                    "new_value": update.new_value.isoformat() if update.new_value else None,
                    "salesforce_id": update.salesforce_id,
                },
            })
            self.db.commit()
        except Exception as e:
            # Table might not exist, just log
            logger.debug(f"Could not log MUM client event: {e}")

    def _log_date_update(self, loan_id: int, update: DateUpdate):
        """Log a date field update for tracking purposes."""
        try:
            self.db.execute(text("""
                INSERT INTO field_update_history (
                    entity_type, entity_id, field_name,
                    old_value, new_value, update_source, updated_at
                ) VALUES (
                    'loan', :loan_id, :field_name,
                    :old_value, :new_value, 'salesforce_sync', NOW()
                )
            """), {
                "loan_id": loan_id,
                "field_name": update.field_name,
                "old_value": str(update.old_value) if update.old_value else None,
                "new_value": str(update.new_value) if update.new_value else None,
            })
            self.db.commit()
        except Exception as e:
            # Table might not exist, just log
            logger.debug(f"Could not log field update history: {e}")

    def get_pending_date_reconciliation_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending reconciliation tasks for date updates."""
        result = self.db.execute(text("""
            SELECT id, title, description, status, priority, created_at
            FROM tasks
            WHERE source = 'Salesforce Date Sync'
              AND status = 'pending'
              AND owner_id = :owner_id
            ORDER BY created_at DESC
        """), {"owner_id": self.user_id})

        return [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "status": row[3],
                "priority": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
            }
            for row in result.fetchall()
        ]

    def resolve_reconciliation_task(
        self,
        task_id: int,
        loan_id: int,
        salesforce_id: str,
    ) -> bool:
        """
        Resolve a reconciliation task by linking the loan and re-syncing.

        Args:
            task_id: ID of the reconciliation task
            loan_id: ID of the loan to link
            salesforce_id: Salesforce record ID

        Returns:
            True if resolved successfully
        """
        try:
            # Update the loan with the Salesforce ID
            self.db.execute(text("""
                UPDATE loans
                SET salesforce_id = :sf_id,
                    salesforce_last_synced_at = NOW(),
                    salesforce_sync_status = 'linked'
                WHERE id = :loan_id
            """), {
                "sf_id": salesforce_id,
                "loan_id": loan_id,
            })

            # Mark task as completed
            self.db.execute(text("""
                UPDATE tasks
                SET status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :task_id
            """), {"task_id": task_id})

            self.db.commit()

            logger.info(f"Resolved reconciliation task {task_id}, linked loan {loan_id} to SF {salesforce_id}")
            return True

        except Exception as e:
            logger.error(f"Error resolving reconciliation task: {e}")
            self.db.rollback()
            return False


def process_salesforce_date_updates(
    db: Session,
    user_id: int,
    records: List[Dict[str, Any]],
    existing_loans: Dict[str, Dict[str, Any]],
) -> DateReconciliationResult:
    """
    Process date updates from a batch of Salesforce records.

    This should be called during the Salesforce sync process to track
    date field changes and create reconciliation tasks as needed.

    Args:
        db: Database session
        user_id: ID of the user performing the sync
        records: List of Salesforce records being synced
        existing_loans: Dict mapping salesforce_id -> existing loan data

    Returns:
        DateReconciliationResult with aggregate results
    """
    service = DateReconciliationService(db, user_id)
    result = DateReconciliationResult()

    for record in records:
        sf_id = record.get("Id") or record.get("salesforce_id")
        if not sf_id:
            continue

        existing = existing_loans.get(sf_id)
        matched_loan_id = existing.get("id") if existing else None
        loan_stage = existing.get("stage") if existing else None

        # Track which dates changed
        updates = service.track_date_updates(sf_id, existing, record, matched_loan_id)

        # Process each date update
        for update in updates:
            update_result = service.process_date_update(update, matched_loan_id, loan_stage)
            result.dates_tracked += update_result.dates_tracked
            result.mum_clients_updated += update_result.mum_clients_updated
            result.tasks_created += update_result.tasks_created
            result.errors.extend(update_result.errors)

    logger.info(
        f"Date reconciliation complete: {result.dates_tracked} dates tracked, "
        f"{result.mum_clients_updated} MUM clients updated, "
        f"{result.tasks_created} reconciliation tasks created"
    )

    return result
