"""
Domain-specific exception classes for Perennia AI.

These replace generic `except Exception` blocks with meaningful,
catchable exceptions that can be handled differently at each layer.

Usage:
    from exceptions import LoanNotFoundError, ComplianceViolationError

    try:
        loan = get_loan_or_raise(db, loan_id)
    except LoanNotFoundError as e:
        return {"error": str(e), "loan_id": e.entity_id}
"""
from typing import Optional, Any


class PerenniaError(Exception):
    """Base exception for all Perennia AI domain errors."""

    def __init__(self, message: str, code: str = "PERENNIA_ERROR", details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


# =============================================================================
# Entity Not Found Errors
# =============================================================================

class EntityNotFoundError(PerenniaError):
    """Base class for entity-not-found errors."""

    def __init__(self, entity_type: str, entity_id: Any, message: Optional[str] = None):
        self.entity_type = entity_type
        self.entity_id = entity_id
        msg = message or f"{entity_type} with id '{entity_id}' not found"
        super().__init__(msg, code=f"{entity_type.upper()}_NOT_FOUND")


class LoanNotFoundError(EntityNotFoundError):
    """Raised when a loan cannot be found by ID or loan number."""

    def __init__(self, loan_id: Any, message: Optional[str] = None):
        super().__init__("Loan", loan_id, message)


class LeadNotFoundError(EntityNotFoundError):
    """Raised when a lead cannot be found by ID."""

    def __init__(self, lead_id: Any, message: Optional[str] = None):
        super().__init__("Lead", lead_id, message)


class UserNotFoundError(EntityNotFoundError):
    """Raised when a user cannot be found."""

    def __init__(self, user_id: Any, message: Optional[str] = None):
        super().__init__("User", user_id, message)


class DocumentNotFoundError(EntityNotFoundError):
    """Raised when a document cannot be found."""

    def __init__(self, doc_id: Any, message: Optional[str] = None):
        super().__init__("Document", doc_id, message)


# =============================================================================
# Security & Tenant Isolation Errors
# =============================================================================

class TenantIsolationError(PerenniaError):
    """Raised when a cross-tenant access attempt is detected."""

    def __init__(
        self,
        message: str = "Cross-tenant access denied",
        requesting_org_id: Optional[int] = None,
        target_org_id: Optional[int] = None,
    ):
        self.requesting_org_id = requesting_org_id
        self.target_org_id = target_org_id
        super().__init__(
            message,
            code="TENANT_ISOLATION_VIOLATION",
            details={
                "requesting_org_id": requesting_org_id,
                "target_org_id": target_org_id,
            },
        )


class AuthenticationError(PerenniaError):
    """Raised for authentication failures (invalid token, expired, etc.)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTHENTICATION_ERROR")


class AuthorizationError(PerenniaError):
    """Raised when user lacks permission for an action."""

    def __init__(self, message: str = "Insufficient permissions", required_role: Optional[str] = None):
        self.required_role = required_role
        super().__init__(message, code="AUTHORIZATION_ERROR")


# =============================================================================
# Compliance Errors
# =============================================================================

class ComplianceViolationError(PerenniaError):
    """Raised when a compliance rule is violated."""

    def __init__(
        self,
        message: str,
        violation_type: Optional[str] = None,
        severity: str = "high",
        loan_id: Optional[Any] = None,
    ):
        self.violation_type = violation_type
        self.severity = severity
        self.loan_id = loan_id
        super().__init__(
            message,
            code="COMPLIANCE_VIOLATION",
            details={
                "violation_type": violation_type,
                "severity": severity,
                "loan_id": loan_id,
            },
        )


class AuditImmutabilityError(ComplianceViolationError):
    """Raised when code attempts to mutate an immutable audit record.

    This is the canonical exception class. The middleware module
    (middleware.audit_immutability) subclasses this for its own use,
    but callers should catch this base type.
    """

    def __init__(
        self,
        message: str = "Audit record mutation blocked",
        operation: Optional[str] = None,
        table_name: Optional[str] = None,
        record_id: Any = None,
        field: Optional[str] = None,
    ):
        self.operation = operation
        self.table_name = table_name
        self.record_id = record_id
        self.field = field
        super().__init__(
            message=message,
            violation_type="audit_immutability",
            severity="critical",
        )


class SLABreachError(PerenniaError):
    """Raised when an SLA deadline is breached."""

    def __init__(
        self,
        message: str,
        milestone: Optional[str] = None,
        days_overdue: Optional[int] = None,
    ):
        self.milestone = milestone
        self.days_overdue = days_overdue
        super().__init__(
            message,
            code="SLA_BREACH",
            details={"milestone": milestone, "days_overdue": days_overdue},
        )


# =============================================================================
# Data Integrity Errors
# =============================================================================

class InvalidStageError(PerenniaError):
    """Raised when an invalid pipeline stage value is used."""

    def __init__(self, stage: str, valid_stages: Optional[list] = None, entity_type: str = "Loan"):
        self.stage = stage
        self.valid_stages = valid_stages
        msg = f"Invalid {entity_type} stage: '{stage}'"
        if valid_stages:
            msg += f". Valid stages: {', '.join(valid_stages)}"
        super().__init__(msg, code="INVALID_STAGE")


class DuplicateEntityError(PerenniaError):
    """Raised when attempting to create a duplicate entity."""

    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(
            f"Duplicate {entity_type}: '{identifier}' already exists",
            code="DUPLICATE_ENTITY",
        )


# =============================================================================
# Integration Errors
# =============================================================================

class SalesforceError(PerenniaError):
    """Raised for Salesforce integration failures."""

    def __init__(self, message: str, sf_error_code: Optional[str] = None):
        self.sf_error_code = sf_error_code
        super().__init__(message, code="SALESFORCE_ERROR")


class TelephonyError(PerenniaError):
    """Raised for telephony provider (Telnyx/Vapi) failures."""

    def __init__(self, message: str, provider: Optional[str] = None):
        self.provider = provider
        super().__init__(message, code="TELEPHONY_ERROR")


# =============================================================================
# AI Agent Errors
# =============================================================================

class AgentToolError(PerenniaError):
    """Raised when an agent tool execution fails."""

    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(
            f"Tool '{tool_name}' failed: {message}",
            code="AGENT_TOOL_ERROR",
        )


class AgentTimeoutError(PerenniaError):
    """Raised when an agent exceeds its execution timeout."""

    def __init__(self, agent_name: str, timeout_seconds: int):
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Agent '{agent_name}' timed out after {timeout_seconds}s",
            code="AGENT_TIMEOUT",
        )


# =============================================================================
# Concurrency Errors
# =============================================================================

class ConflictError(PerenniaError):
    """Raised when an optimistic lock detects a concurrent modification.

    Defined here for module-level imports; the db_transaction module
    re-exports its own ConflictError that subclasses this.
    """

    def __init__(
        self,
        message: str = "Concurrent modification conflict",
        entity_type: Optional[str] = None,
        entity_id: Any = None,
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            message,
            code="OPTIMISTIC_LOCK_CONFLICT",
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )


# =============================================================================
# Scheduler / Appointment Errors
# =============================================================================

class SchedulerError(PerenniaError):
    """Base exception for all scheduler/appointment domain errors."""
    status_code: int = 500

    def __init__(self, message: str, details: Optional[dict] = None,
                 code: str = "SCHEDULER_ERROR", status_code: Optional[int] = None):
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message, code=code, details=details)


class AppointmentNotFoundError(SchedulerError):
    status_code = 404

    def __init__(self, appointment_id: Any):
        super().__init__(
            f"Appointment with id '{appointment_id}' not found",
            code="APPOINTMENT_NOT_FOUND",
        )


class AppointmentConflictError(SchedulerError):
    status_code = 409

    def __init__(self, message: str = "This time slot is no longer available",
                 conflicts: Optional[list] = None):
        super().__init__(message, code="APPOINTMENT_CONFLICT",
                         details={"conflicts": conflicts or []})


class SlotUnavailableError(SchedulerError):
    status_code = 409

    def __init__(self, message: str = "Requested slot is not available"):
        super().__init__(message, code="SLOT_UNAVAILABLE")


class DuplicateBookingError(SchedulerError):
    status_code = 409

    def __init__(self, attendee_email: str = ""):
        super().__init__(
            "A booking already exists for this attendee at the requested time",
            code="DUPLICATE_BOOKING",
            details={"attendee_email": attendee_email},
        )


class InvalidAppointmentStateError(SchedulerError):
    status_code = 422

    def __init__(self, from_status: str, to_status: str,
                 allowed: Optional[list] = None):
        super().__init__(
            f"Cannot transition appointment from '{from_status}' to '{to_status}'",
            code="INVALID_APPOINTMENT_STATE",
            details={"from": from_status, "to": to_status,
                      "allowed": allowed or []},
        )


class InvalidStateTransitionError(PerenniaError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status: str, to_status: str,
                 entity_type: str = "Appointment",
                 allowed_transitions: Optional[list] = None):
        self.from_status = from_status
        self.to_status = to_status
        self.entity_type = entity_type
        self.allowed_transitions = allowed_transitions or []
        super().__init__(
            f"Cannot transition {entity_type} from '{from_status}' to '{to_status}'",
            code="INVALID_STATE_TRANSITION",
            details={"from_status": from_status, "to_status": to_status,
                      "allowed_transitions": self.allowed_transitions},
        )


class BookingLinkNotFoundError(SchedulerError):
    status_code = 404

    def __init__(self, slug: str = ""):
        super().__init__(f"Booking link '{slug}' not found",
                         code="BOOKING_LINK_NOT_FOUND")


class BookingLinkExpiredError(SchedulerError):
    status_code = 410

    def __init__(self, slug: str = ""):
        super().__init__(f"Booking link '{slug}' is no longer available",
                         code="BOOKING_LINK_EXPIRED")


class CapacityExceededError(SchedulerError):
    status_code = 429

    def __init__(self, message: str = "Maximum appointment capacity reached"):
        super().__init__(message, code="CAPACITY_EXCEEDED")


class CalendarSyncError(SchedulerError):
    status_code = 502

    def __init__(self, message: str = "Calendar sync failed",
                 provider: Optional[str] = None):
        super().__init__(message, code="CALENDAR_SYNC_ERROR",
                         details={"provider": provider})


class SchedulerRateLimitError(SchedulerError):
    status_code = 429

    def __init__(self, retry_after: int = 60):
        super().__init__("Rate limit exceeded", code="SCHEDULER_RATE_LIMIT",
                         details={"retry_after": retry_after})


class SchedulerValidationError(SchedulerError):
    status_code = 422

    def __init__(self, message: str = "Validation error",
                 field: Optional[str] = None):
        super().__init__(message, code="SCHEDULER_VALIDATION",
                         details={"field": field})


class SchedulerPermissionError(SchedulerError):
    status_code = 403

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, code="SCHEDULER_PERMISSION")


class SchedulerConfigNotFoundError(SchedulerError):
    status_code = 404

    def __init__(self, message: str = "Scheduler configuration not found"):
        super().__init__(message, code="SCHEDULER_CONFIG_NOT_FOUND")


class OptimisticLockError(SchedulerError):
    status_code = 409

    def __init__(self, message: str = "Resource is being modified by another user"):
        super().__init__(message, code="OPTIMISTIC_LOCK_CONFLICT")


__all__ = [
    # Base
    'PerenniaError',
    # Entity not found
    'EntityNotFoundError',
    'LoanNotFoundError',
    'LeadNotFoundError',
    'UserNotFoundError',
    'DocumentNotFoundError',
    # Security
    'TenantIsolationError',
    'AuthenticationError',
    'AuthorizationError',
    # Compliance
    'ComplianceViolationError',
    'AuditImmutabilityError',
    'SLABreachError',
    # Data integrity
    'InvalidStageError',
    'InvalidStateTransitionError',
    'DuplicateEntityError',
    # Concurrency
    'ConflictError',
    'OptimisticLockError',
    # Integrations
    'SalesforceError',
    'TelephonyError',
    # AI
    'AgentToolError',
    'AgentTimeoutError',
    # Scheduler
    'SchedulerError',
    'AppointmentNotFoundError',
    'AppointmentConflictError',
    'SlotUnavailableError',
    'DuplicateBookingError',
    'InvalidAppointmentStateError',
    'BookingLinkNotFoundError',
    'BookingLinkExpiredError',
    'CapacityExceededError',
    'CalendarSyncError',
    'SchedulerRateLimitError',
    'SchedulerValidationError',
    'SchedulerPermissionError',
    'SchedulerConfigNotFoundError',
]
