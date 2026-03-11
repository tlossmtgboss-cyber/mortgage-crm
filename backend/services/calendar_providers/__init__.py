"""
Calendar Provider Registry

Central registry for all calendar provider implementations. Providers register
themselves here, and the sync orchestrator queries the registry to find which
providers are available for a given operation.

Usage:
    from services.calendar_providers import CalendarProviderRegistry

    # Register a provider (typically done at startup)
    CalendarProviderRegistry.register(GoogleCalendarProvider())
    CalendarProviderRegistry.register(OutlookCalendarProvider())

    # Look up at sync time
    provider = CalendarProviderRegistry.get("google")
    if provider:
        result = await provider.create_event(appointment, credentials)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .base import (
    BusyBlock,
    CalendarProvider,
    ExternalCalendarEvent,
    ProviderSyncResult,
    SyncDirection,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class CalendarProviderRegistry:
    """Thread-safe registry of CalendarProvider instances."""

    _providers: Dict[str, CalendarProvider] = {}

    @classmethod
    def register(cls, provider: CalendarProvider) -> None:
        """Register a calendar provider.

        If a provider with the same name is already registered, it is replaced
        and a warning is logged.
        """
        name = provider.provider_name
        if name in cls._providers:
            logger.warning(
                "Replacing existing calendar provider %r with %r",
                cls._providers[name],
                provider,
            )
        cls._providers[name] = provider
        logger.info("Registered calendar provider: %s", name)

    @classmethod
    def unregister(cls, name: str) -> bool:
        """Remove a provider by name. Returns True if it existed."""
        return cls._providers.pop(name, None) is not None

    @classmethod
    def get(cls, name: str) -> Optional[CalendarProvider]:
        """Get a provider by name, or None if not registered."""
        return cls._providers.get(name)

    @classmethod
    def get_all(cls) -> List[CalendarProvider]:
        """Return all registered providers."""
        return list(cls._providers.values())

    @classmethod
    def get_names(cls) -> List[str]:
        """Return names of all registered providers."""
        return list(cls._providers.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check whether a provider is registered."""
        return name in cls._providers

    @classmethod
    def clear(cls) -> None:
        """Remove all registered providers. Primarily for testing."""
        cls._providers.clear()

    @classmethod
    def count(cls) -> int:
        """Return the number of registered providers."""
        return len(cls._providers)


def register_default_providers() -> None:
    """Register the built-in Google and Outlook providers.

    Called during application startup. Providers that depend on external
    credentials being configured will still register -- they fail gracefully
    at call time if credentials are absent.
    """
    from .google import GoogleCalendarProvider
    from .outlook import OutlookCalendarProvider

    CalendarProviderRegistry.register(GoogleCalendarProvider())
    CalendarProviderRegistry.register(OutlookCalendarProvider())

    logger.info(
        "Default calendar providers registered: %s",
        CalendarProviderRegistry.get_names(),
    )


__all__ = [
    "CalendarProvider",
    "CalendarProviderRegistry",
    "ExternalCalendarEvent",
    "ProviderSyncResult",
    "BusyBlock",
    "SyncDirection",
    "SyncStatus",
    "register_default_providers",
]
