"""
PII Audit Logging Service

Provides audit logging for access to Personally Identifiable Information (PII)
and other sensitive data to comply with GLBA, GDPR, and CCPA requirements.

Usage:
    from services.pii_audit_service import pii_audit, PIIField

    # Log PII access
    pii_audit.log_access(
        user_id=current_user.id,
        entity_type="lead",
        entity_id=lead_id,
        fields_accessed=[PIIField.CREDIT_SCORE, PIIField.SSN],
        reason="Viewing lead details",
        request_id=request_id
    )
"""

import logging
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
import os

logger = logging.getLogger(__name__)


class PIIField(str, Enum):
    """Enumeration of PII fields that require audit logging."""
    # Identity
    SSN = "ssn"
    SSN_LAST_4 = "ssn_last_4"
    DATE_OF_BIRTH = "date_of_birth"
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"

    # Financial
    CREDIT_SCORE = "credit_score"
    BANK_ACCOUNT = "bank_account"
    ROUTING_NUMBER = "routing_number"
    INCOME = "income"
    TAX_RETURN = "tax_return"
    FINANCIAL_STATEMENT = "financial_statement"

    # Contact
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"

    # Employment
    EMPLOYER = "employer"
    SALARY = "salary"

    # HMDA Demographics (ECOA protected)
    HMDA_ETHNICITY = "hmda_ethnicity"
    HMDA_RACE = "hmda_race"
    HMDA_SEX = "hmda_sex"

    # Other
    FULL_NAME = "full_name"
    MEDICAL = "medical"


class PIIAccessType(str, Enum):
    """Type of PII access."""
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    SEARCH = "search"


@dataclass
class PIIAuditEntry:
    """Represents a single PII audit log entry."""
    timestamp: str
    user_id: Optional[int]
    user_email: Optional[str]
    ip_address: Optional[str]
    entity_type: str
    entity_id: str
    access_type: PIIAccessType
    fields_accessed: List[str]
    reason: Optional[str]
    request_id: Optional[str]
    session_id: Optional[str]
    organization_id: Optional[str]
    success: bool
    metadata: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string for logging."""
        return json.dumps(self.to_dict(), default=str)


class PIIAuditService:
    """
    Service for logging access to PII/sensitive data.

    Provides:
    - Structured audit logging for compliance
    - Integration with database and file-based logging
    - Query capabilities for compliance reporting
    """

    def __init__(self):
        self._db_enabled = False
        self._file_logging_enabled = True
        self._audit_logger = logging.getLogger("pii_audit")

        # Configure dedicated PII audit logger
        self._configure_file_logging()

    def _configure_file_logging(self):
        """Configure file-based PII audit logging."""
        log_dir = os.getenv("PII_AUDIT_LOG_DIR", "logs/pii_audit")
        os.makedirs(log_dir, exist_ok=True)

        # Create rotating file handler
        try:
            from logging.handlers import RotatingFileHandler
            handler = RotatingFileHandler(
                os.path.join(log_dir, "pii_access.log"),
                maxBytes=50 * 1024 * 1024,  # 50MB
                backupCount=90,  # Keep 90 days of logs
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            self._audit_logger.addHandler(handler)
            self._audit_logger.setLevel(logging.INFO)
            # Don't propagate to root logger
            self._audit_logger.propagate = False
            logger.info(f"PII audit logging configured: {log_dir}")
        except Exception as e:
            logger.warning(f"Could not configure PII file logging: {e}")
            self._file_logging_enabled = False

    def initialize_db(self, session_factory):
        """
        Initialize database storage for audit logs.

        Args:
            session_factory: SQLAlchemy session factory
        """
        self._session_factory = session_factory
        self._db_enabled = True
        logger.info("PII audit database logging enabled")

    def log_access(
        self,
        entity_type: str,
        entity_id: str,
        fields_accessed: List[PIIField],
        access_type: PIIAccessType = PIIAccessType.READ,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PIIAuditEntry:
        """
        Log access to PII fields.

        Args:
            entity_type: Type of entity (e.g., "lead", "loan", "contact")
            entity_id: ID of the entity being accessed
            fields_accessed: List of PII fields accessed
            access_type: Type of access (read, write, delete, etc.)
            user_id: ID of user accessing the data
            user_email: Email of user accessing the data
            ip_address: IP address of the request
            reason: Business reason for access
            request_id: Unique request identifier
            session_id: User session identifier
            organization_id: Tenant/organization ID
            success: Whether the access was successful
            metadata: Additional context

        Returns:
            The audit entry that was logged
        """
        entry = PIIAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            entity_type=entity_type,
            entity_id=str(entity_id),
            access_type=access_type,
            fields_accessed=[f.value if isinstance(f, PIIField) else f for f in fields_accessed],
            reason=reason,
            request_id=request_id,
            session_id=session_id,
            organization_id=str(organization_id) if organization_id else None,
            success=success,
            metadata=metadata,
        )

        # Log to file
        if self._file_logging_enabled:
            self._audit_logger.info(entry.to_json())

        # Log to database if enabled
        if self._db_enabled:
            self._log_to_db(entry)

        # Also log to standard logger at DEBUG level for development
        logger.debug(
            f"PII_ACCESS: user={user_id} entity={entity_type}/{entity_id} "
            f"fields={entry.fields_accessed} type={access_type.value}"
        )

        return entry

    def _log_to_db(self, entry: PIIAuditEntry):
        """Store audit entry in database."""
        try:
            from models.pii_audit_log import PIIAuditLog
            session = self._session_factory()
            try:
                log = PIIAuditLog(
                    timestamp=datetime.fromisoformat(entry.timestamp),
                    user_id=entry.user_id,
                    user_email=entry.user_email,
                    ip_address=entry.ip_address,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    access_type=entry.access_type.value,
                    fields_accessed=entry.fields_accessed,
                    reason=entry.reason,
                    request_id=entry.request_id,
                    session_id=entry.session_id,
                    organization_id=entry.organization_id,
                    success=entry.success,
                    meta_data=entry.metadata,
                )
                session.add(log)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to store PII audit in DB: {e}")
            finally:
                session.close()
        except ImportError:
            # Model not yet created
            pass

    def log_bulk_access(
        self,
        entity_type: str,
        entity_ids: List[str],
        fields_accessed: List[PIIField],
        **kwargs
    ):
        """Log bulk access to multiple entities."""
        for entity_id in entity_ids:
            self.log_access(
                entity_type=entity_type,
                entity_id=entity_id,
                fields_accessed=fields_accessed,
                **kwargs
            )

    def log_export(
        self,
        entity_type: str,
        entity_ids: List[str],
        fields_exported: List[PIIField],
        export_format: str,
        **kwargs
    ):
        """Log data export containing PII."""
        self.log_access(
            entity_type=entity_type,
            entity_id=",".join(str(id) for id in entity_ids[:10]),  # Truncate for log
            fields_accessed=fields_exported,
            access_type=PIIAccessType.EXPORT,
            metadata={
                "export_format": export_format,
                "record_count": len(entity_ids),
                **(kwargs.get("metadata") or {}),
            },
            **{k: v for k, v in kwargs.items() if k != "metadata"}
        )

    def log_search(
        self,
        entity_type: str,
        search_fields: List[PIIField],
        result_count: int,
        **kwargs
    ):
        """Log search query involving PII fields."""
        self.log_access(
            entity_type=entity_type,
            entity_id="search",
            fields_accessed=search_fields,
            access_type=PIIAccessType.SEARCH,
            metadata={
                "result_count": result_count,
                **(kwargs.get("metadata") or {}),
            },
            **{k: v for k, v in kwargs.items() if k != "metadata"}
        )


# Global PII audit service instance
pii_audit = PIIAuditService()


# Decorator for automatic PII access logging
def audit_pii_access(
    entity_type: str,
    entity_id_param: str = "id",
    fields: List[PIIField] = None,
    access_type: PIIAccessType = PIIAccessType.READ,
):
    """
    Decorator to automatically log PII access for route handlers.

    Usage:
        @router.get("/leads/{lead_id}")
        @audit_pii_access("lead", "lead_id", [PIIField.CREDIT_SCORE])
        async def get_lead(lead_id: str, current_user: User = Depends(get_current_user)):
            ...
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract entity ID from kwargs
            entity_id = kwargs.get(entity_id_param, "unknown")

            # Try to get user info from kwargs
            user_id = None
            user_email = None
            if "current_user" in kwargs:
                user = kwargs["current_user"]
                user_id = getattr(user, "id", None)
                user_email = getattr(user, "email", None)

            # Try to get request info
            request_id = None
            ip_address = None
            if "request" in kwargs:
                request = kwargs["request"]
                request_id = getattr(request.state, "request_id", None)
                ip_address = request.client.host if request.client else None

            # Log the access
            pii_audit.log_access(
                entity_type=entity_type,
                entity_id=str(entity_id),
                fields_accessed=fields or [],
                access_type=access_type,
                user_id=user_id,
                user_email=user_email,
                ip_address=ip_address,
                request_id=request_id,
            )

            # Execute the actual function
            return await func(*args, **kwargs)

        return wrapper
    return decorator
