"""
Calendar Sync Orchestrator

Coordinates syncing appointments across all connected calendar providers.
Uses the CalendarProviderRegistry to discover available providers and the
CalendarEventMap model to track which external events map to which
internal appointments.

Usage:
    orchestrator = CalendarSyncOrchestrator()
    results = await orchestrator.sync_appointment(db, appointment, user)
    busy = await orchestrator.get_all_busy_times(db, user, start, end)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from services.calendar_providers import (
    CalendarProviderRegistry,
    ProviderSyncResult,
    SyncStatus,
)
from services.calendar_providers.base import BusyBlock

logger = logging.getLogger(__name__)


def _lazy_model():
    """Lazy import CalendarEventMap to avoid circular imports at module load."""
    from database.models.calendar_event_map import CalendarEventMap
    return CalendarEventMap


class CalendarSyncOrchestrator:
    """Coordinates syncing appointments across all connected calendar providers.

    The orchestrator is stateless -- all persistent state lives in the DB via
    CalendarEventMap rows. Provider instances come from the registry.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync_appointment(
        self,
        db: Session,
        appointment: Any,
        user: Any,
    ) -> List[ProviderSyncResult]:
        """Sync an appointment to all connected providers for the given user.

        For each provider the user has credentials for:
        - If no CalendarEventMap exists yet, create a new external event.
        - If a mapping already exists, update the external event.

        Returns a list of ProviderSyncResult (one per provider attempted).
        """
        CalendarEventMap = _lazy_model()
        results: List[ProviderSyncResult] = []

        org_id = self._get_org_id(appointment, user)
        appointment_id = self._get_appointment_id(appointment)

        for provider_name, credentials in self._get_user_providers(db, user):
            provider = CalendarProviderRegistry.get(provider_name)
            if not provider:
                logger.warning("Provider %r in user credentials but not registered", provider_name)
                continue

            # Check for existing mapping
            existing_map = (
                db.query(CalendarEventMap)
                .filter(
                    CalendarEventMap.appointment_id == appointment_id,
                    CalendarEventMap.provider == provider_name,
                )
                .first()
            )

            if existing_map and existing_map.sync_status != "deleted":
                # Update existing event
                result = await provider.update_event(
                    external_id=existing_map.external_id,
                    appointment=appointment,
                    credentials=credentials,
                )
                if result.success:
                    existing_map.synced_at = datetime.now(timezone.utc)
                    existing_map.sync_status = "synced"
                    existing_map.last_error = None
                    if result.link:
                        existing_map.external_link = result.link
                else:
                    existing_map.sync_status = "failed"
                    existing_map.last_error = result.error
                existing_map.updated_at = datetime.now(timezone.utc)
            else:
                # Create new event
                result = await provider.create_event(
                    appointment=appointment,
                    credentials=credentials,
                )
                if result.success and result.external_id:
                    if existing_map:
                        # Reuse the existing row (was marked deleted)
                        existing_map.external_id = result.external_id
                        existing_map.external_link = result.link
                        existing_map.sync_status = "synced"
                        existing_map.synced_at = datetime.now(timezone.utc)
                        existing_map.last_error = None
                        existing_map.updated_at = datetime.now(timezone.utc)
                    else:
                        new_map = CalendarEventMap(
                            organization_id=org_id,
                            appointment_id=appointment_id,
                            provider=provider_name,
                            external_id=result.external_id,
                            external_link=result.link,
                            sync_status="synced",
                            synced_at=datetime.now(timezone.utc),
                        )
                        db.add(new_map)
                elif not result.success and not existing_map:
                    # Record the failure so we can retry later
                    failed_map = CalendarEventMap(
                        organization_id=org_id,
                        appointment_id=appointment_id,
                        provider=provider_name,
                        external_id="",  # No external ID yet
                        sync_status="failed",
                        last_error=result.error,
                    )
                    db.add(failed_map)

            results.append(result)

        try:
            db.flush()
        except Exception as e:
            logger.error("Failed to flush CalendarEventMap changes: %s", e)

        return results

    async def delete_appointment_events(
        self,
        db: Session,
        appointment: Any,
        user: Any,
    ) -> List[ProviderSyncResult]:
        """Delete external events for a cancelled/deleted appointment.

        Iterates over all CalendarEventMap rows for the appointment and
        deletes the corresponding external events.
        """
        CalendarEventMap = _lazy_model()
        results: List[ProviderSyncResult] = []

        appointment_id = self._get_appointment_id(appointment)

        mappings = (
            db.query(CalendarEventMap)
            .filter(
                CalendarEventMap.appointment_id == appointment_id,
                CalendarEventMap.sync_status != "deleted",
            )
            .all()
        )

        for mapping in mappings:
            provider = CalendarProviderRegistry.get(mapping.provider)
            if not provider:
                logger.warning(
                    "Cannot delete external event: provider %r not registered",
                    mapping.provider,
                )
                continue

            _, credentials = self._get_credentials_for_provider(db, user, mapping.provider)
            if not credentials:
                logger.warning(
                    "No credentials for provider %r when deleting event",
                    mapping.provider,
                )
                continue

            result = await provider.delete_event(
                external_id=mapping.external_id,
                credentials=credentials,
            )

            if result.success:
                mapping.sync_status = "deleted"
                mapping.updated_at = datetime.now(timezone.utc)
                mapping.last_error = None
            else:
                mapping.sync_status = "failed"
                mapping.last_error = result.error
                mapping.updated_at = datetime.now(timezone.utc)

            results.append(result)

        try:
            db.flush()
        except Exception as e:
            logger.error("Failed to flush CalendarEventMap delete changes: %s", e)

        return results

    async def get_all_busy_times(
        self,
        db: Session,
        user: Any,
        start: datetime,
        end: datetime,
    ) -> List[BusyBlock]:
        """Aggregate busy times from all connected calendar providers.

        Returns a merged, sorted list of BusyBlock instances. Overlapping
        blocks from different providers are not merged -- the caller is
        responsible for deduplication if needed.
        """
        all_busy: List[BusyBlock] = []

        for provider_name, credentials in self._get_user_providers(db, user):
            provider = CalendarProviderRegistry.get(provider_name)
            if not provider:
                continue

            try:
                blocks = await provider.get_busy_times(
                    credentials=credentials,
                    start=start,
                    end=end,
                )
                all_busy.extend(blocks)
            except Exception as e:
                logger.error(
                    "Failed to get busy times from %s: %s",
                    provider_name,
                    e,
                )

        # Sort by start time
        all_busy.sort(key=lambda b: b.start)
        return all_busy

    async def get_sync_status(
        self,
        db: Session,
        appointment_id: int,
    ) -> List[Dict[str, Any]]:
        """Get sync status for all providers for a given appointment."""
        CalendarEventMap = _lazy_model()

        mappings = (
            db.query(CalendarEventMap)
            .filter(CalendarEventMap.appointment_id == appointment_id)
            .all()
        )

        return [
            {
                "provider": m.provider,
                "external_id": m.external_id,
                "external_link": m.external_link,
                "sync_status": m.sync_status,
                "synced_at": m.synced_at.isoformat() if m.synced_at else None,
                "last_error": m.last_error,
            }
            for m in mappings
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user_providers(
        self,
        db: Session,
        user: Any,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Get all calendar providers and credentials for a user.

        Checks three possible credential stores in order:
        1. user_integrations (microsoft_routes.py stores plaintext tokens here)
        2. integration_credentials (legacy table, some routes use it)
        3. microsoft_oauth_tokens (microsoft_oauth_routes.py stores encrypted tokens here)

        Returns list of (provider_name, credentials_dict) tuples.
        """
        from sqlalchemy import text as sa_text

        providers: List[Tuple[str, Dict[str, Any]]] = []
        user_id = getattr(user, "id", None)
        if not user_id:
            return providers

        # Map integration provider names to our calendar provider names
        provider_mapping = {
            "google_calendar": "google",
            "google": "google",
            "microsoft": "outlook",
            "outlook": "outlook",
            "outlook_calendar": "outlook",
            "outlook_email": "outlook",
        }

        # 1. Check user_integrations table (microsoft_routes.py stores tokens here)
        try:
            rows = db.execute(
                sa_text("""
                    SELECT provider, access_token, refresh_token, expires_at
                    FROM user_integrations
                    WHERE user_id = :user_id
                      AND access_token IS NOT NULL
                      AND provider IN ('google_calendar', 'google', 'microsoft', 'outlook',
                                       'outlook_calendar', 'outlook_email')
                """),
                {"user_id": user_id},
            ).fetchall()
        except Exception:
            rows = []

        for row in rows:
            cal_provider = provider_mapping.get(row[0])
            if cal_provider and CalendarProviderRegistry.is_registered(cal_provider):
                if not any(p[0] == cal_provider for p in providers):
                    providers.append((cal_provider, {
                        "access_token": row[1],
                        "refresh_token": row[2],
                        "expires_at": row[3].isoformat() if row[3] else None,
                    }))

        # 2. Check integration_credentials table (legacy)
        try:
            rows = db.execute(
                sa_text("""
                    SELECT provider, access_token, refresh_token, expires_at
                    FROM integration_credentials
                    WHERE user_id = :user_id
                      AND access_token IS NOT NULL
                      AND provider IN ('google_calendar', 'google', 'microsoft', 'outlook')
                """),
                {"user_id": user_id},
            ).fetchall()
        except Exception:
            rows = []

        for row in rows:
            cal_provider = provider_mapping.get(row[0])
            if cal_provider and CalendarProviderRegistry.is_registered(cal_provider):
                if not any(p[0] == cal_provider for p in providers):
                    providers.append((cal_provider, {
                        "access_token": row[1],
                        "refresh_token": row[2],
                        "expires_at": row[3].isoformat() if row[3] else None,
                    }))

        # 3. Check microsoft_oauth_tokens table (microsoft_oauth_routes.py stores encrypted tokens here)
        if not any(p[0] == "outlook" for p in providers):
            try:
                ms_row = db.execute(
                    sa_text("""
                        SELECT access_token, refresh_token, token_expires_at
                        FROM microsoft_oauth_tokens
                        WHERE user_id = :user_id
                          AND access_token IS NOT NULL
                        ORDER BY updated_at DESC NULLS LAST
                        LIMIT 1
                    """),
                    {"user_id": user_id},
                ).fetchone()

                if ms_row and CalendarProviderRegistry.is_registered("outlook"):
                    # Tokens in this table are encrypted — decrypt them
                    access_token = ms_row[0]
                    refresh_token = ms_row[1]
                    try:
                        from services.calendly_service import decrypt_token
                        access_token = decrypt_token(access_token)
                        if refresh_token:
                            refresh_token = decrypt_token(refresh_token)
                    except Exception:
                        logger.warning("Could not decrypt microsoft_oauth_tokens; using raw values")

                    providers.append(("outlook", {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": ms_row[2].isoformat() if ms_row[2] else None,
                    }))
            except Exception:
                pass  # Table may not exist yet

        return providers

    def _get_credentials_for_provider(
        self,
        db: Session,
        user: Any,
        provider_name: str,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Get credentials for a specific provider."""
        all_providers = self._get_user_providers(db, user)
        for name, creds in all_providers:
            if name == provider_name:
                return name, creds
        return None, None

    @staticmethod
    def _get_org_id(appointment: Any, user: Any) -> int:
        """Extract organization_id from appointment or user."""
        org_id = getattr(appointment, "organization_id", None)
        if org_id:
            return org_id
        org_id = getattr(user, "organization_id", None)
        if org_id:
            return org_id
        return 0

    @staticmethod
    def _get_appointment_id(appointment: Any) -> int:
        """Extract appointment ID."""
        if isinstance(appointment, dict):
            return appointment.get("id", 0)
        return getattr(appointment, "id", 0)
