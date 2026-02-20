"""
Bidirectional LOS Sync Service

Handles mapping, conflict resolution, and sync orchestration
between the CRM Loan model and the LOS.

Enterprise Readiness: Check 7.2 (Bidirectional LOS Sync)
Enterprise Readiness: Check 7.5 (LOS Conflict Resolution)

Features:
    - Push CRM loan changes to LOS
    - Pull LOS loan changes to CRM
    - Configurable field mapping
    - Timestamp-based conflict detection (compares last_modified on both sides)
    - Conflict resolution strategies: crm_wins, los_wins, newest_wins, manual
    - Structured conflict logging via LosSyncLog
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
# Conflict Detection & Resolution (Check 7.5)
# =============================================================================

class ConflictDetector:
    """Detects and resolves field-level conflicts between CRM and LOS data.

    During a pull operation, each bidirectional field is checked:
      1. If the CRM value has changed since the last sync AND
         the LOS value has also changed since the last sync,
         the field is a true conflict.
      2. If only one side changed, it is NOT a conflict; the changed
         side's value is applied.

    Resolution strategies:
      - crm_wins:     CRM value is kept, LOS value is discarded.
      - los_wins:     LOS value is applied, CRM value is overwritten.
      - newest_wins:  Whichever side was modified more recently wins.
      - manual:       Neither side is applied; field is flagged for human review.
    """

    def __init__(self, strategy: str = "crm_wins"):
        self.strategy = strategy

    def detect_and_resolve(
        self,
        field_name: str,
        crm_value: Any,
        los_value: Any,
        crm_last_modified: Optional[datetime],
        los_last_modified: Optional[datetime],
        last_sync_at: Optional[datetime],
    ) -> Dict[str, Any]:
        """Detect whether a field has a true conflict and resolve it.

        Args:
            field_name: The CRM field name being compared.
            crm_value: Current value in the CRM.
            los_value: Current value from the LOS.
            crm_last_modified: When the CRM record was last modified.
            los_last_modified: When the LOS record was last modified.
            last_sync_at: Timestamp of the last successful sync.

        Returns:
            Dict with keys:
                is_conflict (bool): True if both sides changed since last sync.
                resolution (str): How the conflict was resolved.
                winning_value: The value to apply (or None if manual).
                winning_side (str): "crm", "los", or "manual".
                details (dict): Full context for audit logging.
        """
        str_crm = str(crm_value) if crm_value is not None else ""
        str_los = str(los_value) if los_value is not None else ""

        # No difference means no conflict
        if str_crm == str_los:
            return {
                "is_conflict": False,
                "resolution": "no_change",
                "winning_value": crm_value,
                "winning_side": "both",
                "details": {},
            }

        # Determine which sides changed since the last sync
        crm_changed_since_sync = True
        los_changed_since_sync = True

        if last_sync_at is not None:
            # Normalize timezone awareness
            sync_ts = last_sync_at if last_sync_at.tzinfo else last_sync_at.replace(tzinfo=timezone.utc)

            if crm_last_modified is not None:
                crm_ts = crm_last_modified if crm_last_modified.tzinfo else crm_last_modified.replace(tzinfo=timezone.utc)
                crm_changed_since_sync = crm_ts > sync_ts
            else:
                crm_changed_since_sync = False

            if los_last_modified is not None:
                los_ts = los_last_modified if los_last_modified.tzinfo else los_last_modified.replace(tzinfo=timezone.utc)
                los_changed_since_sync = los_ts > sync_ts
            else:
                los_changed_since_sync = False

        is_true_conflict = crm_changed_since_sync and los_changed_since_sync

        # If only one side changed, that side wins (not a conflict)
        if not is_true_conflict:
            if los_changed_since_sync:
                return {
                    "is_conflict": False,
                    "resolution": "los_only_changed",
                    "winning_value": los_value,
                    "winning_side": "los",
                    "details": {},
                }
            else:
                return {
                    "is_conflict": False,
                    "resolution": "crm_only_changed",
                    "winning_value": crm_value,
                    "winning_side": "crm",
                    "details": {},
                }

        # True conflict: both sides changed since last sync
        details = {
            "field": field_name,
            "crm_value": str_crm,
            "los_value": str_los,
            "crm_last_modified": crm_last_modified.isoformat() if crm_last_modified else None,
            "los_last_modified": los_last_modified.isoformat() if los_last_modified else None,
            "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
            "strategy": self.strategy,
        }

        if self.strategy == "los_wins":
            return {
                "is_conflict": True,
                "resolution": "los_wins",
                "winning_value": los_value,
                "winning_side": "los",
                "details": details,
            }
        elif self.strategy == "crm_wins":
            return {
                "is_conflict": True,
                "resolution": "crm_wins",
                "winning_value": crm_value,
                "winning_side": "crm",
                "details": details,
            }
        elif self.strategy == "newest_wins":
            # Compare modification timestamps to determine the winner
            crm_ts = crm_last_modified or datetime.min.replace(tzinfo=timezone.utc)
            los_ts = los_last_modified or datetime.min.replace(tzinfo=timezone.utc)
            if crm_ts.tzinfo is None:
                crm_ts = crm_ts.replace(tzinfo=timezone.utc)
            if los_ts.tzinfo is None:
                los_ts = los_ts.replace(tzinfo=timezone.utc)

            if crm_ts >= los_ts:
                details["winner_reason"] = "crm_modified_more_recently"
                return {
                    "is_conflict": True,
                    "resolution": "newest_wins_crm",
                    "winning_value": crm_value,
                    "winning_side": "crm",
                    "details": details,
                }
            else:
                details["winner_reason"] = "los_modified_more_recently"
                return {
                    "is_conflict": True,
                    "resolution": "newest_wins_los",
                    "winning_value": los_value,
                    "winning_side": "los",
                    "details": details,
                }
        else:
            # Manual: flag for human review, do not apply either value
            return {
                "is_conflict": True,
                "resolution": "manual_review_required",
                "winning_value": None,
                "winning_side": "manual",
                "details": details,
            }


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
        result.completed_at = datetime.now(timezone.utc)

        # If this was a create (no existing LOS ID), store the returned ID
        if result.status == LOSSyncStatus.SUCCESS and result.los_loan_id and not los_loan_id:
            _set_los_loan_id(loan, result.los_loan_id)
            try:
                db.flush()
            except Exception as e:
                logger.error(f"Failed to save LOS loan ID: {e}")

        # Log the sync event with latency
        _log_sync_event(db, loan_id, result)

        logger.info(
            f"LOS push for loan {loan_id}: {result.status.value} "
            f"in {result.latency_ms}ms (SLA: {'PASS' if result.within_sla else 'FAIL'})"
        )

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
        uses timestamp-based conflict detection (Check 7.5), and applies
        changes per resolution strategy.

        Conflict detection logic:
            For each bidirectional field, compare the CRM's updated_at
            and the LOS's lastModified against the last sync timestamp.
            If BOTH changed since last sync, it is a true conflict and
            the configured resolution strategy is applied.

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

            # Get last sync timestamp for conflict detection (Check 7.5)
            last_sync_info = _get_last_sync(db, loan_id)
            last_sync_at = None
            if last_sync_info and last_sync_info.get("timestamp"):
                try:
                    ts = last_sync_info["timestamp"]
                    if isinstance(ts, str):
                        last_sync_at = datetime.fromisoformat(ts)
                    elif isinstance(ts, datetime):
                        last_sync_at = ts
                except (ValueError, TypeError):
                    pass

            # Determine CRM and LOS modification timestamps
            crm_last_modified = getattr(loan, "updated_at", None) or getattr(loan, "stage_changed_at", None)
            los_last_modified = None
            raw_last_mod = los_data.raw_data.get("lastModified") or los_data.raw_data.get("Fields/LOANINFO.X1")
            if raw_last_mod and isinstance(raw_last_mod, str):
                try:
                    from dateutil.parser import parse as parse_date
                    los_last_modified = parse_date(raw_last_mod)
                except Exception:
                    pass

            # Initialize conflict detector (Check 7.5)
            conflict_detector = ConflictDetector(strategy=self.conflict_resolution)

            # Apply fields to CRM loan
            conflicts = []
            auto_resolved = 0
            manual_pending = 0
            changes = []

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

                # Use timestamp-based conflict detection for bidirectional fields
                if mapping.direction == "bidirectional" and crm_value is not None and str(crm_value) != str(los_value):
                    resolution = conflict_detector.detect_and_resolve(
                        field_name=mapping.crm_field,
                        crm_value=crm_value,
                        los_value=los_value,
                        crm_last_modified=crm_last_modified,
                        los_last_modified=los_last_modified,
                        last_sync_at=last_sync_at,
                    )

                    if resolution["is_conflict"]:
                        conflict = {
                            "field": mapping.crm_field,
                            "crm_value": str(crm_value),
                            "los_value": str(los_value),
                            "resolution": resolution["resolution"],
                            "winning_side": resolution["winning_side"],
                        }

                        if resolution["winning_side"] == "los":
                            setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                            changes.append({
                                "field": mapping.crm_field,
                                "old": str(crm_value),
                                "new": str(los_value),
                                "source": "los",
                                "conflict_resolved": True,
                            })
                            result.fields_synced += 1
                            auto_resolved += 1
                        elif resolution["winning_side"] == "crm":
                            result.fields_skipped += 1
                            auto_resolved += 1
                        else:
                            # Manual review required
                            result.fields_skipped += 1
                            manual_pending += 1

                        conflicts.append(conflict)
                    else:
                        # Not a true conflict: only one side changed
                        if resolution["winning_side"] == "los":
                            setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                            changes.append({
                                "field": mapping.crm_field,
                                "old": str(crm_value),
                                "new": str(los_value),
                                "source": "los",
                                "conflict_resolved": False,
                            })
                            result.fields_synced += 1
                        else:
                            result.fields_skipped += 1

                elif crm_value is not None and str(crm_value) != str(los_value):
                    # Pull-only field: LOS always wins, no conflict possible
                    setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                    changes.append({
                        "field": mapping.crm_field,
                        "old": str(crm_value),
                        "new": str(los_value),
                        "source": "los",
                        "conflict_resolved": False,
                    })
                    result.fields_synced += 1
                else:
                    # No difference or CRM value is None: apply LOS value
                    if los_value is not None:
                        old_val = str(crm_value) if crm_value is not None else None
                        setattr(loan, mapping.crm_field, _coerce_value(loan, mapping.crm_field, los_value))
                        if old_val != str(los_value):
                            changes.append({
                                "field": mapping.crm_field,
                                "old": old_val,
                                "new": str(los_value),
                                "source": "los",
                                "conflict_resolved": False,
                            })
                        result.fields_synced += 1

            result.conflicts = conflicts
            result.details["changes"] = changes
            result.details["conflicts_auto_resolved"] = auto_resolved
            result.details["conflicts_manual_pending"] = manual_pending

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

            if manual_pending > 0:
                result.status = LOSSyncStatus.CONFLICT
            elif conflicts:
                result.status = LOSSyncStatus.PARTIAL
            else:
                result.status = LOSSyncStatus.SUCCESS
            result.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            result.status = LOSSyncStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.now(timezone.utc)
            logger.error(f"Pull from LOS failed for loan {loan_id}: {e}")

        # Log the sync event with latency (audit trail + LosSyncLog)
        _log_sync_event(db, loan_id, result)
        _log_to_los_sync_log(db, loan_id, result)

        logger.info(
            f"LOS pull for loan {loan_id}: {result.status.value} "
            f"in {result.latency_ms}ms (SLA: {'PASS' if result.within_sla else 'FAIL'})"
            f" | conflicts: {len(conflicts)} (auto: {auto_resolved}, manual: {manual_pending})"
        )

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
                "latency_ms": result.latency_ms,
                "within_sla": result.within_sla,
            },
        )
        db.add(log)
        db.flush()
    except Exception as e:
        # Don't fail the sync because logging failed
        logger.warning(f"Failed to log sync event: {e}")


def _get_last_sync(db: Session, loan_id: int) -> Optional[Dict[str, Any]]:
    """Get the last sync event for a loan.

    Checks LosSyncLog first (preferred), then falls back to AuditLog.
    """
    # Try LosSyncLog first (richer data)
    try:
        from database.models.los_sync import LosSyncLog
        last_sync_log = db.query(LosSyncLog).filter(
            LosSyncLog.loan_id == loan_id,
            LosSyncLog.sync_status.in_(["success", "partial"]),
        ).order_by(LosSyncLog.sync_timestamp.desc()).first()

        if last_sync_log:
            return {
                "timestamp": last_sync_log.sync_timestamp.isoformat() if last_sync_log.sync_timestamp else None,
                "direction": last_sync_log.sync_direction,
                "status": last_sync_log.sync_status,
            }
    except Exception:
        pass  # LosSyncLog table may not exist yet

    # Fall back to AuditLog
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


def _log_to_los_sync_log(db: Session, loan_id: int, result: LOSSyncResult) -> None:
    """Write a detailed sync record to the LosSyncLog table (Check 7.5).

    This provides field-level conflict tracking, change history, and
    resolution audit trails that the enterprise readiness audit requires.
    """
    try:
        from database.models.los_sync import LosSyncLog

        # Map LOSSyncStatus to LosSyncLog status strings
        status_map = {
            LOSSyncStatus.SUCCESS: "success",
            LOSSyncStatus.PARTIAL: "partial",
            LOSSyncStatus.FAILED: "failed",
            LOSSyncStatus.CONFLICT: "conflict",
            LOSSyncStatus.SKIPPED: "success",
            LOSSyncStatus.IN_PROGRESS: "partial",
            LOSSyncStatus.PENDING: "partial",
        }

        fields_synced_list = []
        fields_conflicted_list = []
        changes_list = result.details.get("changes", [])

        for change in changes_list:
            fields_synced_list.append(change["field"])

        for conflict in result.conflicts:
            fields_conflicted_list.append({
                "field": conflict.get("field"),
                "crm_value": conflict.get("crm_value"),
                "los_value": conflict.get("los_value"),
                "resolution": conflict.get("resolution"),
                "winning_side": conflict.get("winning_side"),
            })

        sync_log = LosSyncLog(
            loan_id=loan_id,
            los_system="encompass",
            sync_direction=result.direction.value,
            sync_trigger="manual",
            sync_status=status_map.get(result.status, "failed"),
            fields_synced=fields_synced_list or None,
            fields_conflicted=fields_conflicted_list or None,
            changes=changes_list or None,
            conflicts_auto_resolved=result.details.get("conflicts_auto_resolved", 0),
            conflicts_manual_pending=result.details.get("conflicts_manual_pending", 0),
            error_message="; ".join(result.errors) if result.errors else None,
            duration_ms=int(result.latency_ms) if result.latency_ms else None,
            sync_timestamp=datetime.now(timezone.utc),
        )
        db.add(sync_log)
        db.flush()
    except Exception as e:
        # Don't fail the sync because structured logging failed
        logger.warning(f"Failed to write LosSyncLog: {e}")
