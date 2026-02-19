"""
Abstract LOS Client Interface

Defines the contract that all LOS integrations must implement,
along with shared data types for field mappings, sync status,
and configuration.

Enterprise Readiness: Check 7.1 (LOS Integration Framework)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class LOSSyncStatus(str, Enum):
    """Status of a sync operation between CRM and LOS."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL = "partial"          # Some fields synced, some failed
    CONFLICT = "conflict"        # Data conflicts detected
    FAILED = "failed"
    SKIPPED = "skipped"          # No changes to sync


class LOSSyncDirection(str, Enum):
    """Direction of a sync operation."""
    PUSH = "push"    # CRM -> LOS
    PULL = "pull"    # LOS -> CRM
    BIDIRECTIONAL = "bidirectional"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LOSConfig:
    """Configuration for a LOS integration instance."""
    provider: str                         # "encompass", "byte", etc.
    instance_id: str                      # LOS instance/site identifier
    client_id: str                        # OAuth client ID
    client_secret: str                    # OAuth client secret
    api_key: Optional[str] = None         # Optional API key
    base_url: Optional[str] = None        # Override base URL
    webhook_secret: Optional[str] = None  # Secret for webhook verification
    timeout_seconds: int = 30
    max_retries: int = 3
    enabled: bool = True

    # Sync configuration
    auto_push: bool = False               # Auto-push changes to LOS
    auto_pull: bool = False               # Auto-pull changes from LOS
    conflict_resolution: str = "crm_wins"  # crm_wins, los_wins, manual
    sync_interval_minutes: int = 15


@dataclass
class LOSFieldMapping:
    """Mapping between a CRM field and a LOS field."""
    crm_field: str           # Field name in our Loan model
    los_field: str           # Field path in LOS (e.g., "borrowerPair.borrower.firstName")
    direction: str = "bidirectional"  # push, pull, bidirectional
    transform: Optional[str] = None   # Optional transformation name
    required: bool = False
    los_field_id: Optional[str] = None  # Encompass canonical field ID


@dataclass
class LOSSyncResult:
    """Result of a sync operation."""
    status: LOSSyncStatus
    direction: LOSSyncDirection
    loan_id: int                          # CRM loan ID
    los_loan_id: Optional[str] = None     # LOS loan GUID
    fields_synced: int = 0
    fields_skipped: int = 0
    fields_failed: int = 0
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "direction": self.direction.value,
            "loan_id": self.loan_id,
            "los_loan_id": self.los_loan_id,
            "fields_synced": self.fields_synced,
            "fields_skipped": self.fields_skipped,
            "fields_failed": self.fields_failed,
            "conflicts": self.conflicts,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "details": self.details,
        }


@dataclass
class LOSLoanData:
    """Normalized loan data from a LOS system."""
    los_loan_id: str                      # LOS-native loan identifier (GUID)
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    borrower_email: Optional[str] = None
    loan_amount: Optional[float] = None
    loan_type: Optional[str] = None
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    rate: Optional[float] = None
    stage: Optional[str] = None
    closing_date: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Abstract Base Client
# =============================================================================

class BaseLOSClient(ABC):
    """Abstract base class for all LOS client implementations.

    Subclasses must implement all abstract methods to provide
    a complete integration with a specific LOS platform.
    """

    def __init__(self, config: LOSConfig):
        self.config = config
        self._authenticated = False
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid authentication token."""
        if not self._authenticated or not self._token:
            return False
        if self._token_expires_at and datetime.now(timezone.utc) >= self._token_expires_at:
            return False
        return True

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the LOS API.

        Returns:
            True if authentication succeeded
        """
        ...

    @abstractmethod
    async def push_loan(self, loan_data: Dict[str, Any]) -> LOSSyncResult:
        """Push loan data from CRM to LOS.

        Creates a new loan in the LOS if it does not exist,
        or updates an existing loan.

        Args:
            loan_data: Dict of CRM loan fields to push

        Returns:
            LOSSyncResult with status and details
        """
        ...

    @abstractmethod
    async def pull_loan(self, los_loan_id: str) -> LOSLoanData:
        """Pull loan data from LOS to CRM.

        Args:
            los_loan_id: The LOS-native loan identifier

        Returns:
            LOSLoanData with normalized loan fields
        """
        ...

    @abstractmethod
    async def get_loan_status(self, los_loan_id: str) -> Dict[str, Any]:
        """Get the current status/milestone of a loan in the LOS.

        Args:
            los_loan_id: The LOS-native loan identifier

        Returns:
            Dict with status, milestone, and last-modified info
        """
        ...

    @abstractmethod
    async def search_loans(
        self,
        filters: Dict[str, Any],
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Search for loans in the LOS pipeline.

        Args:
            filters: Search criteria (loan_number, borrower_name, etc.)
            limit: Max results to return

        Returns:
            List of loan summary dicts
        """
        ...

    @abstractmethod
    async def get_loan_documents(self, los_loan_id: str) -> List[Dict[str, Any]]:
        """Get list of documents attached to a loan in the LOS.

        Args:
            los_loan_id: The LOS-native loan identifier

        Returns:
            List of document metadata dicts
        """
        ...

    async def ensure_authenticated(self) -> None:
        """Ensure the client is authenticated, re-authenticating if needed."""
        if not self.is_authenticated:
            success = await self.authenticate()
            if not success:
                from .error_handler import LOSError
                raise LOSError("Authentication failed", code="AUTH_FAILED")

    async def health_check(self) -> Dict[str, Any]:
        """Check connectivity and authentication with the LOS.

        Returns:
            Dict with health status, latency, and auth status
        """
        import time
        start = time.monotonic()
        try:
            await self.ensure_authenticated()
            latency_ms = (time.monotonic() - start) * 1000
            return {
                "status": "healthy",
                "provider": self.config.provider,
                "instance_id": self.config.instance_id,
                "authenticated": True,
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return {
                "status": "unhealthy",
                "provider": self.config.provider,
                "instance_id": self.config.instance_id,
                "authenticated": False,
                "latency_ms": round(latency_ms, 1),
                "error": str(e),
            }
