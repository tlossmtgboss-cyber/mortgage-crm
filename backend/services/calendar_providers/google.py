"""
Google Calendar Provider

Implements the CalendarProvider interface using the existing GoogleCalendarClient
from integrations.google_calendar_service. Wraps the low-level HTTP client with
the standardized provider contract.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    BusyBlock,
    CalendarProvider,
    ExternalCalendarEvent,
    ProviderSyncResult,
    SyncStatus,
)

logger = logging.getLogger(__name__)


def _get_google_client():
    """Lazy import to avoid circular imports at module load."""
    from integrations.google_calendar_service import google_calendar_client
    return google_calendar_client


def _extract_appointment_fields(appointment: Any) -> Dict[str, Any]:
    """Extract scheduling fields from an Appointment ORM object or dict."""
    if isinstance(appointment, dict):
        return {
            "title": appointment.get("title", "Appointment"),
            "start": appointment.get("scheduled_start") or appointment.get("start"),
            "end": appointment.get("scheduled_end") or appointment.get("end"),
            "description": appointment.get("description", ""),
            "location": appointment.get("location", ""),
            "attendee_email": appointment.get("attendee_email"),
            "video_link": appointment.get("video_link"),
        }

    return {
        "title": getattr(appointment, "title", "Appointment"),
        "start": getattr(appointment, "scheduled_start", None),
        "end": getattr(appointment, "scheduled_end", None),
        "description": getattr(appointment, "description", "") or "",
        "location": getattr(appointment, "location", "") or "",
        "attendee_email": getattr(appointment, "attendee_email", None),
        "video_link": getattr(appointment, "video_link", None),
    }


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar provider using the Google Calendar v3 API."""

    @property
    def provider_name(self) -> str:
        return "google"

    async def create_event(
        self,
        appointment: Any,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        start_ms = time.monotonic()
        try:
            client = _get_google_client()
            access_token = await self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            fields = _extract_appointment_fields(appointment)
            attendees = [fields["attendee_email"]] if fields["attendee_email"] else None

            description = fields["description"]
            if fields["video_link"]:
                description += f"\n\nVideo Link: {fields['video_link']}"

            result = await client.create_event(
                access_token=access_token,
                summary=fields["title"],
                start_time=fields["start"],
                end_time=fields["end"],
                description=description or None,
                location=fields["location"] or None,
                attendees=attendees,
            )

            if result and result.get("id"):
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.SUCCESS,
                    external_id=result["id"],
                    link=result.get("htmlLink"),
                    duration_ms=int((time.monotonic() - start_ms) * 1000),
                )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error="Google Calendar API returned no event ID",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("GoogleCalendarProvider.create_event failed: %s", e)
            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

    async def update_event(
        self,
        external_id: str,
        appointment: Any,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        start_ms = time.monotonic()
        try:
            client = _get_google_client()
            access_token = await self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            fields = _extract_appointment_fields(appointment)
            updates: Dict[str, Any] = {
                "summary": fields["title"],
                "start": {"dateTime": fields["start"].isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": fields["end"].isoformat(), "timeZone": "UTC"},
            }
            if fields["description"]:
                updates["description"] = fields["description"]
            if fields["location"]:
                updates["location"] = fields["location"]
            if fields["attendee_email"]:
                updates["attendees"] = [{"email": fields["attendee_email"]}]

            result = await client.update_event(
                access_token=access_token,
                event_id=external_id,
                updates=updates,
            )

            if result is not None:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.SUCCESS,
                    external_id=external_id,
                    link=result.get("htmlLink") if isinstance(result, dict) else None,
                    duration_ms=int((time.monotonic() - start_ms) * 1000),
                )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error="Google Calendar API update returned None",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("GoogleCalendarProvider.update_event failed: %s", e)
            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

    async def delete_event(
        self,
        external_id: str,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        start_ms = time.monotonic()
        try:
            client = _get_google_client()
            access_token = await self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            success = await client.delete_event(
                access_token=access_token,
                event_id=external_id,
            )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.SUCCESS if success else SyncStatus.FAILED,
                external_id=external_id,
                error=None if success else "Google Calendar delete returned False",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("GoogleCalendarProvider.delete_event failed: %s", e)
            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error=str(e),
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

    async def get_busy_times(
        self,
        credentials: Dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> List[BusyBlock]:
        try:
            client = _get_google_client()
            access_token = await self._ensure_valid_token(credentials)
            if not access_token:
                logger.warning("GoogleCalendarProvider: no valid token for busy times")
                return []

            result = await client.list_events(
                access_token=access_token,
                time_min=start,
                time_max=end,
            )

            if not result or "items" not in result:
                return []

            busy_blocks: List[BusyBlock] = []
            for event in result["items"]:
                # Skip transparent (free) events
                if event.get("transparency") == "transparent":
                    continue

                event_start = self._parse_google_datetime(event.get("start", {}))
                event_end = self._parse_google_datetime(event.get("end", {}))

                if event_start and event_end:
                    busy_blocks.append(BusyBlock(
                        start=event_start,
                        end=event_end,
                        provider=self.provider_name,
                        title=event.get("summary"),
                        is_all_day="date" in event.get("start", {}),
                    ))

            return busy_blocks

        except Exception as e:
            logger.error("GoogleCalendarProvider.get_busy_times failed: %s", e)
            return []

    async def test_connection(
        self,
        credentials: Dict[str, Any],
    ) -> bool:
        try:
            client = _get_google_client()
            access_token = await self._ensure_valid_token(credentials)
            if not access_token:
                return False

            result = await client.get_calendar(access_token=access_token)
            return result is not None

        except Exception as e:
            logger.error("GoogleCalendarProvider.test_connection failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_valid_token(self, credentials: Dict[str, Any]) -> Optional[str]:
        """Return a valid access token, refreshing if expired."""
        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        expires_at_str = credentials.get("expires_at")

        if not access_token:
            return None

        # Check expiration if available
        if expires_at_str and refresh_token:
            try:
                if isinstance(expires_at_str, str):
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                else:
                    expires_at = expires_at_str

                if isinstance(expires_at, datetime) and expires_at <= datetime.now(timezone.utc):
                    client = _get_google_client()
                    refreshed = await client.refresh_access_token(refresh_token)
                    if refreshed and refreshed.get("access_token"):
                        return refreshed["access_token"]
                    return None
            except (ValueError, TypeError):
                pass  # Can't parse expiry; use existing token

        return access_token

    @staticmethod
    def _parse_google_datetime(dt_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse Google Calendar start/end dict into a datetime."""
        if not dt_dict:
            return None

        if "dateTime" in dt_dict:
            raw = dt_dict["dateTime"]
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        if "date" in dt_dict:
            try:
                return datetime.fromisoformat(dt_dict["date"] + "T00:00:00+00:00")
            except (ValueError, TypeError):
                return None

        return None
