"""
Abstract Calendar Provider Interface

Defines the contract that all calendar integrations (Google, Outlook, Salesforce,
Zoom, Apple Calendar, etc.) must implement. Decouples appointment sync logic from
any specific vendor API.

Usage:
    class MyCalendarProvider(CalendarProvider):
        @property
        def provider_name(self) -> str:
            return "my_calendar"
        ...
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class SyncDirection(str, enum.Enum):
    """Direction of a sync operation."""
    PUSH = "push"     # CRM -> external calendar
    PULL = "pull"     # external calendar -> CRM
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(str, enum.Enum):
    """Status of an individual sync operation."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CONFLICT = "conflict"


@dataclass
class ExternalCalendarEvent:
    """Normalized representation of a calendar event from any external provider."""
    external_id: str
    provider: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    link: Optional[str] = None
    description: Optional[str] = None
    is_all_day: bool = False
    timezone: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "external_id": self.external_id,
            "provider": self.provider,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "attendees": self.attendees,
            "link": self.link,
            "description": self.description,
            "is_all_day": self.is_all_day,
            "timezone": self.timezone,
        }


@dataclass
class BusyBlock:
    """A contiguous block of time where a user is busy."""
    start: datetime
    end: datetime
    provider: str
    title: Optional[str] = None
    is_all_day: bool = False


@dataclass
class ProviderSyncResult:
    """Result of a single provider sync operation."""
    provider: str
    status: SyncStatus
    external_id: Optional[str] = None
    link: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return self.status == SyncStatus.SUCCESS


class CalendarProvider(ABC):
    """
    Abstract interface for calendar integrations.

    Every external calendar system (Google Calendar, Outlook/Graph, Salesforce,
    Zoom Calendar, Apple Calendar, etc.) implements this interface so the
    sync orchestrator can work uniformly with any provider.

    Credential management is intentionally left to the caller -- providers
    receive opaque credential dicts whose structure is provider-specific.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g., 'google', 'outlook', 'salesforce').

        Must be stable -- it is stored in CalendarEventMap.provider and used
        as a registry key.
        """

    @abstractmethod
    async def create_event(
        self,
        appointment: Any,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        """Create an event in the external calendar.

        Args:
            appointment: The internal Appointment ORM object (or dict with
                         equivalent keys) to push to the external calendar.
            credentials: Provider-specific credential dict (access_token,
                         refresh_token, etc.).

        Returns:
            ProviderSyncResult with external_id populated on success.
        """

    @abstractmethod
    async def update_event(
        self,
        external_id: str,
        appointment: Any,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        """Update an existing event in the external calendar.

        Args:
            external_id: The provider-side event ID (stored in CalendarEventMap).
            appointment: Updated appointment data.
            credentials: Provider-specific credential dict.

        Returns:
            ProviderSyncResult indicating success or failure.
        """

    @abstractmethod
    async def delete_event(
        self,
        external_id: str,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        """Delete an event from the external calendar.

        Args:
            external_id: The provider-side event ID.
            credentials: Provider-specific credential dict.

        Returns:
            ProviderSyncResult indicating success or failure.
        """

    @abstractmethod
    async def get_busy_times(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[BusyBlock]:
        """Get busy time blocks from the external calendar.

        Used for availability checking when scheduling new appointments.

        Args:
            credentials: Provider-specific credential dict.
            start: Start of the query window.
            end: End of the query window.

        Returns:
            List of BusyBlock instances within the window.
        """

    @abstractmethod
    async def test_connection(
        self,
        credentials: Dict[str, Any],
    ) -> bool:
        """Test whether the provided credentials are valid.

        Returns:
            True if the credentials allow a successful API call, False otherwise.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name!r}>"
