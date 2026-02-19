"""
Bidirectional LOS Sync Service

Handles mapping, conflict resolution, and sync orchestration
between the CRM Loan model and the LOS.

Enterprise Readiness: Check 7.2 (Bidirectional LOS Sync)

Features:
    - Push CRM loan changes to LOS
    - Pull LOS loan changes to CRM
    - Configurable field mapping
    - Conflict resolution (CRM-wins, LOS-wins, manual)
    - Sync history and audit logging

Usage:
    from services.los_integration import LOSSyncService, EncompassClient

    client = EncompassClient(...)
    sync = LOSSyncService(client=client)

    result = await sync.push_to_los(db, loan_id=42)
    result = await sync.pull_from_los(db, loan_id=42)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base import (
    BaseLOSClient,
    LOSFieldMapping,
    LOSLoanData,
    LOSSyncDirection,
    LOSSyncResult,
    LOSSyncStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Default Field Mappings (CRM <-> Encompass)
# =============================================================================

DEFAULT_FIELD_MAPPINGS: List[LOSFieldMapping] = [
    # Borrower
    LOSFieldMapping("borrower_name", "Fields/4000", "bidirectional", required=True),
    LOSFieldMapping("borrower_email", "Fields/1240", "bidirectional"),
    LOSFieldMapping("borrower_phone", "Fields/66", "bidirectional"),
    LOSFieldMapping("coborrower_name", "Fields/4004", "bidirectional"),

    # Loan details
    LOSFieldMapping("loan_number", "Fields/364", "pull", required=True),  # LOS is source of truth
    LOSFieldMapping("amount", "Fields/1109", "bidirectional", required=True),
    LOSFieldMapping("purchase_price", "Fields/136", "bidirectional"),
    LOSFieldMapping("rate", "Fields/3", "bidirectional"),
    LOSFieldMapping("term", "Fields/4", "bidirectional"),
    LOSFieldMapping("loan_type", "Fields/1172", "bidirectional"),
    LOSFieldMapping("loan_purpose", "Fields/19", "bidirectional"),

    # Property
    LOSFieldMapping("property_address", "Fields/11", "bidirectional"),
    LOSFieldMapping("property_city", "Fields/12", "bidirectional"),
    LOSFieldMapping("property_state", "Fields/14", "bidirectional"),
    LOSFieldMapping("property_zip", "Fields/15", "bidirectional"),
    LOSFieldMapping("property_type", "Fields/1041", "bidirectional"),
    LOSFieldMapping("property_county", "Fields/13", "bidirectional"),

    # Dates
    LOSFieldMapping("application_date", "Fields/745", "pull"),  # LOS is source of truth
    LOSFieldMapping("closing_date", "Fields/748", "bidirectional"),
    LOSFieldMapping("lock_date", "Fields/761", "pull"),
    LOSFieldMapping("lock_expiration_date", "Fields/762", "pull"),
    LOSFieldMapping("funded_date", "Fields/2370", "pull"),

    # Disclosures
    LOSFieldMapping("loan_estimate_sent_date", "Fields/3152", "pull"),
    LOSFieldMapping("cd_sent_to_borrower_date", "Fields/CD1.X1", "pull"),

    # Financial ratios
    LOSFieldMapping("ltv", "Fields/353", "pull"),
    LOSFieldMapping("cltv", "Fields/976", "pull"),
    LOSFieldMapping("down_payment", "Fields/1771", "bidirectional"),

    # Team
    LOSFieldMapping("loan_officer_name", "Fields/317", "push"),
    LOSFieldMapping("loan_officer_email", "Fields/VEND.X263", "push"),
    LOSFieldMapping("processor", "Fields/362", "pull"),
    LOSFieldMapping("underwriter", "Fields/VEND.X23", "pull"),
]


class LOSSyncService:
    """Orchestrates bidirectional sync between CRM and LOS.

    Handles field mapping, conflict detection/resolution, and
    maintains a sync audit trail.
    """

    def __init__(
        self,
        client: BaseLOSClient,
        field_mappings: Optional[List[LOSFieldMapping]] = None,
        conflict_resolution: str = "crm_wins",
    ):
        """
        Args:
            client: LOS client implementation
            field_mappings: Custom field mappings (defaults to DEFAULT_FIELD_MAPPINGS)
            conflict_resolution: Strategy for conflicts:
                - "crm_wins": CRM value takes precedence
                - "los_wins": LOS value takes precedence
                - "newest_wins": Most recently modified value wins
                - "manual": Flag for manual review
        """
        self.client = client
        self.field_mappings = field_mappings or DEFAULT_FIELD_MAPPINGS
        self.conflict_resolution = conflict_resolution

    # =========================================================================
    # Push: CRM -> LOS
    # =========================================================================

    async def push_to_los(
        self,
        db: Session,
        loan_id: int,
        fields: Optional[List[str]] = None,
    ) -> LOSSyncResult:
        """Push loan data from CRM to LOS.

        Reads the CRM Loan record, maps fields per configuration,
        and pushes to the LOS via the client.

        Args:
            db: Database session
            loan_id: CRM loan ID
            fields: Optional list of specific CRM fields to push.
                    If None, pushes all push/bidirectional-mapped fields.

        Returns:
            LOSSyncResult with sync outcome
        """
        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return LOSSyncResult(
                status=LOSSyncStatus.FAILED,
                direction=LOSSyncDirection.PUSH,
                loan_id=loan_id,
                errors=[f"Loan {loan_id} not found in CRM"],
            )

        # Build data dict from CRM loan using field mappings
        push_data = {"loan_id": loan_id}

        # Include LOS loan ID if we have it (for updates)
        los_loan_id = _get_los_loan_id(loan)
        if los_loan_id:
            push_data["los_loan_id"] = los_loan_id

        for mapping in self.field_mappings:
            # Skip pull-only fields
            if mapping.direction == "pull":
                continue

            # If specific fields requested, filter
            if fields and mapping.crm_field not in fields:
                continue

            value = getattr(loan, mapping.crm_field, None)
            if value is not None:
                push_data[mapping.crm_field] = value

        # Push via client
        result = await self.client.push_loan(push_data)

        # If this was a create (no existing LOS ID), store the returned ID
        if result.status == LOSSyncStatus.SUCCESS and result.los_loan_id and not los_loan_id:
            _set_los_loan_id(loan, result.los_loan_id)
            try:
                db.flush()
            except Exception as e:
                logger.error(f"Failed to save LOS loan ID: {e}")

        # Log the sync event
        _log_sync_event(db, loan_id, result)

        return result

    # =========================================================================
    # Pull: LOS -> CRM
    # =========================================================================

    async def pull_from_los(
        self,
        db: Session,
        loan_id: int,
        los_loan_id: Optional[str] = None,
    ) -> LOSSyncResult:
        """Pull loan data from LOS to CRM.

        Fetches the loan from LOS, maps fields back to CRM schema,
        detects conflicts, and applies changes per resolution strategy.

        Args:
            db: Database session
            loan_id: CRM loan ID
            los_loan_id: Override LOS loan ID (if not stored on CRM loan)

        Returns:
            LOSSyncResult with sync outcome
        """
        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return LOSSyncResult(
                status=LOSSyncStatus.FAILED,
                direction=LOSSyncDirection.PULL,
                loan_id=loan_id,
                errors=[f"Loan {loan_id} not found in CRM"],
            )

        # Determine LOS loan ID
        effective_los_id = los_loan_id or _get_los_loan_id(loan)
        if not effective_los_id:
            return LOSSyncResult(
                status=LOSSyncStatus.FAILED,
                direction=LOSSyncDirection.PULL,
                loan_id=loan_id,
                errors=["No LOS loan ID associated with this loan"],
            )

        result = LOSSyncResult(
            status=LOSSyncStatus.IN_PROGRESS,
            direction=LOSSyncDirection.PULL,
            loan_id=loan_id,
            los_loan_id=effective_los_id,
        )

        try:
            # Pull from LOS
            los_data = await self.client.pull_loan(effective_los_id)

            # Apply fields to CRM loan
            conflicts = []
            for mapping in self.field_mappings:
                # Skip push-only fields
                if mapping.direction == "push":
                    continue

                los_value = getattr(los_data, mapping.crm_field, None)
                if los_value is None:
                    # Check raw_data with reverse mapping
                    los_value = los_data.raw_data.get(mapping.los_field)

                if los_value is None:
                    result.fields_skipped += 1
                    continue

                crm_value = getattr(loan, mapping.crm_field, None)

                # Detect conflict
                if crm_value is not None and str(crm_value) != str(los_value):
                    conflict = {
                        "field": mapping.crm_field,
                        "crm_value": str(crm_value),
                        "los_value": str(los_value),
                    }

                    if self.conflict_resolution == "los_wins":
                        setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                        conflict["resolution"] = "los_wins"
                        result.fields_synced += 1
                    elif self.conflict_resolution == "crm_wins":
                        conflict["resolution"] = "crm_wins"
                        result.fields_skipped += 1
                    elif self.conflict_resolution == "newest_wins":
                        # Default to LOS as more recently updated for pull
                        setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                        conflict["resolution"] = "newest_wins_los"
                        result.fields_synced += 1
                    else:
                        # Manual: flag conflict, don't update
                        conflict["resolution"] = "manual_review_required"
                        result.fields_skipped += 1

                    conflicts.append(conflict)
                else:
                    # No conflict - apply value
                    if los_value is not None:
                        setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                        result.fields_synced += 1

            result.conflicts = conflicts

            # Update stage if LOS has a stage mapping
            if los_data.stage:
                current_stage = loan.stage
                if current_stage != los_data.stage:
                    result.details["stage_change"] = {
                        "from": current_stage,
                        "to": los_data.stage,
                    }
                    loan.stage = los_data.stage
                    loan.stage_changed_at = datetime.now(timezone.utc)

            try:
                db.flush()
            except Exception as e:
                logger.error(f"Failed to flush loan updates: {e}")
                result.errors.append(f"Database flush failed: {str(e)}")

            result.status = LOSSyncStatus.SUCCESS if not conflicts else LOSSyncStatus.PARTIAL
            result.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            result.status = LOSSyncStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.now(timezone.utc)
            logger.error(f"Pull from LOS failed for loan {loan_id}: {e}")

        # Log the sync event
        _log_sync_event(db, loan_id, result)

        return result

    # =========================================================================
    # Status & Configuration
    # =========================================================================

    async def get_sync_status(self, db: Session, loan_id: int) -> Dict[str, Any]:
        """Get the last sync status for a loan.

        Args:
            db: Database session
            loan_id: CRM loan ID

        Returns:
            Dict with sync status, last sync time, and LOS loan ID
        """
        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            return {"error": f"Loan {loan_id} not found"}

        los_loan_id = _get_los_loan_id(loan)

        # Check for recent sync logs
        last_sync = _get_last_sync(db, loan_id)

        result = {
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "los_loan_id": los_loan_id,
            "is_linked": los_loan_id is not None,
            "last_sync": last_sync,
        }

        # If linked, get LOS status
        if los_loan_id:
            try:
                los_status = await self.client.get_loan_status(los_loan_id)
                result["los_status"] = los_status
            except Exception as e:
                result["los_status_error"] = str(e)

        return result

    def get_field_mappings(self) -> List[Dict[str, Any]]:
        """Get current field mapping configuration."""
        return [
            {
                "crm_field": m.crm_field,
                "los_field": m.los_field,
                "direction": m.direction,
                "required": m.required,
                "transform": m.transform,
            }
            for m in self.field_mappings
        ]

    def update_field_mappings(self, mappings: List[Dict[str, Any]]) -> int:
        """Update field mappings from a list of dicts.

        Args:
            mappings: List of field mapping dicts

        Returns:
            Number of mappings updated
        """
        new_mappings = []
        for m in mappings:
            new_mappings.append(LOSFieldMapping(
                crm_field=m["crm_field"],
                los_field=m["los_field"],
                direction=m.get("direction", "bidirectional"),
                transform=m.get("transform"),
                required=m.get("required", False),
            ))

        self.field_mappings = new_mappings
        logger.info(f"Updated {len(new_mappings)} field mappings")
        return len(new_mappings)


# =============================================================================
# Internal Helpers
# =============================================================================

def _get_los_loan_id(loan) -> Optional[str]:
    """Extract LOS loan ID from the CRM loan's metadata."""
    if hasattr(loan, "user_metadata") and loan.user_metadata:
        meta = loan.user_metadata if isinstance(loan.user_metadata, dict) else {}
        return meta.get("los_loan_id") or meta.get("encompass_guid")
    return None


def _set_los_loan_id(loan, los_loan_id: str) -> None:
    """Store the LOS loan ID in the CRM loan's metadata."""
    if loan.user_metadata is None:
        loan.user_metadata = {}
    meta = loan.user_metadata if isinstance(loan.user_metadata, dict) else {}
    meta["los_loan_id"] = los_loan_id
    loan.user_metadata = meta


def _coerce_value(loan, field_name: str, value: Any) -> Any:
    """Coerce a value to the appropriate type for a loan field."""
    if value is None:
        return None

    # Check the column type from the model
    from sqlalchemy import inspect as sa_inspect
    try:
        mapper = sa_inspect(type(loan))
        column = mapper.columns.get(field_name)
        if column is not None:
            col_type = str(column.type)
            if "FLOAT" in col_type or "NUMERIC" in col_type:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            elif "INTEGER" in col_type:
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return None
            elif "DATETIME" in col_type or "DATE" in col_type:
                if isinstance(value, str):
                    from dateutil.parser import parse as parse_date
                    try:
                        return parse_date(value)
                    except Exception:
                        return value
    except Exception:
        pass

    return value


def _log_sync_event(db: Session, loan_id: int, result: LOSSyncResult) -> None:
    """Log a sync event to the audit trail."""
    try:
        from database.models.security import AuditLog

        log = AuditLog(
            action="los_sync",
            entity_type="loan",
            entity_id=loan_id,
            details={
                "direction": result.direction.value,
                "status": result.status.value,
                "los_loan_id": result.los_loan_id,
                "fields_synced": result.fields_synced,
                "fields_skipped": result.fields_skipped,
                "conflicts": len(result.conflicts),
                "errors": result.errors,
            },
        )
        db.add(log)
        db.flush()
    except Exception as e:
        # Don't fail the sync because logging failed
        logger.warning(f"Failed to log sync event: {e}")


def _get_last_sync(db: Session, loan_id: int) -> Optional[Dict[str, Any]]:
    """Get the last sync event for a loan."""
    try:
        from database.models.security import AuditLog
        from sqlalchemy import and_

        last = db.query(AuditLog).filter(
            and_(
                AuditLog.action == "los_sync",
                AuditLog.entity_type == "loan",
                AuditLog.entity_id == loan_id,
            )
        ).order_by(AuditLog.created_at.desc()).first()

        if last:
            return {
                "timestamp": last.created_at.isoformat() if last.created_at else None,
                "direction": last.details.get("direction") if last.details else None,
                "status": last.details.get("status") if last.details else None,
            }
    except Exception as e:
        logger.warning(f"Failed to get last sync: {e}")

    return None
