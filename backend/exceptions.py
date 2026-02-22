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
    """Raised for telephony provider (Twilio/Telnyx/Vapi) failures."""

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
    'SLABreachError',
    # Data integrity
    'InvalidStageError',
    'DuplicateEntityError',
    # Integrations
    'SalesforceError',
    'TelephonyError',
    # AI
    'AgentToolError',
    'AgentTimeoutError',
]
