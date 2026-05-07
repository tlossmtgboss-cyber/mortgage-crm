"""
Audit Immutability Guard — App-Level Delete/Update Prevention

SQLAlchemy ORM event listeners that enforce immutability on audit and compliance
tables. This is defense-in-depth alongside schema-level constraints (DB triggers,
RLS policies). The ORM layer catches violations BEFORE they hit the database,
providing clear error messages and structured logging.

Protected tables (DELETE blocked unconditionally):
    - audit_events (AuditEvent)
    - mobile_audit_events (MobileAuditEvent)
    - compliance_decision_log (ComplianceDecisionLog)
    - decision_audit_logs (DecisionAuditLog)
    - disclosure_events (DisclosureEvent)
    - memory_audit_events (MemoryAuditEvent)
    - erasure_requests (ErasureRequest) — only when status is 'completed'

Protected tables (UPDATE blocked on critical fields):
    - All of the above except ErasureRequest have ALL updates blocked
    - ErasureRequest allows status transitions and lifecycle field updates
      but blocks changes to: requester_id, organization_id, data_subject_email,
      data_subject_user_id, requested_at, reason

Regulatory context:
    - TCPA (47 U.S.C. 227): Evidence of compliance checks must be retained
    - TRID (12 CFR 1026.19): Disclosure timing audit trail
    - SOC 2 Type II: Append-only audit log integrity
    - GDPR Article 17: Erasure request records must be retained even after execution
    - RESPA/ECOA: 7-year retention for mortgage records

Usage:
    from middleware.audit_immutability import register_audit_protection

    # Call after configure_mappers() and model imports
    register_audit_protection()
"""

from __future__ import annotations

import logging

from sqlalchemy import event, inspect

from exceptions import ComplianceViolationError

logger = logging.getLogger(__name__)


# =============================================================================
# Exception for audit immutability violations
# =============================================================================

class AuditImmutabilityError(ComplianceViolationError):
    """Raised when code attempts to mutate an immutable audit record."""

    def __init__(
        self,
        operation: str,
        table_name: str,
        record_id=None,
        field: str | None = None,
    ):
        self.operation = operation
        self.table_name = table_name
        self.record_id = record_id
        self.field = field

        if field:
            msg = (
                f"BLOCKED: {operation} on protected field '{field}' of "
                f"'{table_name}' (record {record_id}). "
                f"Audit records are immutable for regulatory compliance."
            )
        else:
            msg = (
                f"BLOCKED: {operation} on '{table_name}' (record {record_id}). "
                f"Audit records are immutable for regulatory compliance."
            )

        super().__init__(
            message=msg,
            violation_type="audit_immutability",
            severity="critical",
        )


# =============================================================================
# Configuration: which models and fields are protected
# =============================================================================

# Fields on ErasureRequest that are immutable once created.
# Status, lifecycle timestamps, audit_log, and error_message are mutable
# to support the pending -> approved -> executing -> completed flow.
ERASURE_REQUEST_IMMUTABLE_FIELDS: frozenset[str] = frozenset({
    "requester_id",
    "organization_id",
    "data_subject_email",
    "data_subject_user_id",
    "requested_at",
    "reason",
})


# =============================================================================
# Event listener callbacks
# =============================================================================

def _block_delete(mapper, connection, target):
    """Block DELETE on fully immutable audit tables."""
    table_name = getattr(target, "__tablename__", "unknown")
    record_id = getattr(target, "id", None)

    logger.critical(
        "AUDIT_IMMUTABILITY_VIOLATION: DELETE attempted on %s (id=%s)",
        table_name,
        record_id,
    )

    raise AuditImmutabilityError(
        operation="DELETE",
        table_name=table_name,
        record_id=record_id,
    )


def _block_delete_completed_erasure(mapper, connection, target):
    """Block DELETE on ErasureRequest only when status is 'completed'.

    Pending/approved/executing requests may be cancelled (deleted) by admins,
    but completed erasure records must be retained as proof of GDPR compliance.
    """
    table_name = getattr(target, "__tablename__", "unknown")
    record_id = getattr(target, "id", None)
    status = getattr(target, "status", None)

    if status == "completed":
        logger.critical(
            "AUDIT_IMMUTABILITY_VIOLATION: DELETE attempted on completed "
            "erasure_request (id=%s). Completed erasure records are immutable.",
            record_id,
        )
        raise AuditImmutabilityError(
            operation="DELETE",
            table_name=table_name,
            record_id=record_id,
        )

    # Non-completed erasure requests can be deleted (admin cancellation)
    logger.warning(
        "Erasure request DELETE allowed (status=%s, id=%s) — not yet completed",
        status,
        record_id,
    )


def _block_all_updates(mapper, connection, target):
    """Block ALL updates on fully immutable audit tables.

    These tables are append-only — no field should ever change after insert.
    """
    table_name = getattr(target, "__tablename__", "unknown")
    record_id = getattr(target, "id", None)

    # Use SQLAlchemy inspection to find which attributes actually changed
    state = inspect(target)
    changed_fields = []
    for attr in state.attrs:
        hist = attr.history
        if hist.has_changes():
            changed_fields.append(attr.key)

    if not changed_fields:
        # No actual changes detected (can happen with session.merge)
        return

    logger.critical(
        "AUDIT_IMMUTABILITY_VIOLATION: UPDATE attempted on %s (id=%s), "
        "changed fields: %s",
        table_name,
        record_id,
        changed_fields,
    )

    raise AuditImmutabilityError(
        operation="UPDATE",
        table_name=table_name,
        record_id=record_id,
        field=", ".join(changed_fields),
    )


def _block_erasure_critical_field_updates(mapper, connection, target):
    """Block updates to critical fields on ErasureRequest.

    Allows status transitions and lifecycle field updates (approved_at,
    executed_at, completed_at, audit_log, error_message, status) but
    blocks changes to identity and provenance fields.
    """
    table_name = getattr(target, "__tablename__", "unknown")
    record_id = getattr(target, "id", None)

    state = inspect(target)
    for attr in state.attrs:
        if attr.key not in ERASURE_REQUEST_IMMUTABLE_FIELDS:
            continue

        hist = attr.history
        if hist.has_changes():
            logger.critical(
                "AUDIT_IMMUTABILITY_VIOLATION: UPDATE on immutable field '%s' "
                "of erasure_request (id=%s). Old=%s, New=%s",
                attr.key,
                record_id,
                hist.deleted,
                hist.added,
            )
            raise AuditImmutabilityError(
                operation="UPDATE",
                table_name=table_name,
                record_id=record_id,
                field=attr.key,
            )

    # Non-critical field updates are allowed — log at INFO for observability
    changed = [
        a.key for a in state.attrs if a.history.has_changes()
    ]
    if changed:
        logger.info(
            "Erasure request UPDATE allowed (id=%s): fields=%s",
            record_id,
            changed,
        )


# =============================================================================
# Registration
# =============================================================================

_registered = False


def register_audit_protection():
    """Register SQLAlchemy event listeners for audit record immutability.

    Safe to call multiple times — listeners are only registered once.

    Call this AFTER all models are imported and configure_mappers() has run,
    typically during app startup in main.py or init_db.py.
    """
    global _registered
    if _registered:
        logger.debug("Audit immutability protection already registered, skipping")
        return

    # Lazy imports to avoid circular dependency at module load time.
    # These models must already be imported by the time this function runs.
    from database.models.audit_event import AuditEvent
    from database.models.audit import MobileAuditEvent
    from database.models.compliance_log import ComplianceDecisionLog
    from database.models.decision_audit import DecisionAuditLog
    from database.models.compliance import DisclosureEvent
    from database.models.memory_audit import MemoryAuditEvent
    from database.models.gdpr import ErasureRequest

    # ------------------------------------------------------------------
    # Fully immutable tables: block ALL deletes and ALL updates
    # ------------------------------------------------------------------
    fully_immutable_models = [
        AuditEvent,
        MobileAuditEvent,
        ComplianceDecisionLog,
        DecisionAuditLog,
        DisclosureEvent,
        MemoryAuditEvent,
    ]

    for model in fully_immutable_models:
        event.listen(model, "before_delete", _block_delete)
        event.listen(model, "before_update", _block_all_updates)
        logger.info(
            "Audit immutability: registered DELETE+UPDATE protection on %s (%s)",
            model.__name__,
            model.__tablename__,
        )

    # ------------------------------------------------------------------
    # ErasureRequest: conditional delete (completed only), partial update
    # ------------------------------------------------------------------
    event.listen(ErasureRequest, "before_delete", _block_delete_completed_erasure)
    event.listen(ErasureRequest, "before_update", _block_erasure_critical_field_updates)
    logger.info(
        "Audit immutability: registered conditional DELETE + partial UPDATE "
        "protection on ErasureRequest (erasure_requests)"
    )

    _registered = True
    logger.info(
        "Audit immutability protection registered for %d models",
        len(fully_immutable_models) + 1,
    )
