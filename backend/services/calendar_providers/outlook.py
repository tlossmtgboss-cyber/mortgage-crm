"""
Outlook Calendar Provider

Implements the CalendarProvider interface using the existing MicrosoftOutlookClient
from integrations.microsoft_outlook_service. Wraps the synchronous Graph API client
in async-compatible calls.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import (
    BusyBlock,
    CalendarProvider,
    ProviderSyncResult,
    SyncStatus,
)

logger = logging.getLogger(__name__)


def _get_outlook_client():
    """Lazy import to avoid circular imports at module load."""
    from integrations.microsoft_outlook_service import microsoft_outlook_client
    return microsoft_outlook_client


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


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the default executor.

    The existing MicrosoftOutlookClient uses synchronous requests; this
    wrapper prevents blocking the event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


class OutlookCalendarProvider(CalendarProvider):
    """Outlook/Microsoft 365 Calendar provider using Microsoft Graph API."""

    @property
    def provider_name(self) -> str:
        return "outlook"

    async def create_event(
        self,
        appointment: Any,
        credentials: Dict[str, Any],
    ) -> ProviderSyncResult:
        start_ms = time.monotonic()
        try:
            client = _get_outlook_client()
            access_token = self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            fields = _extract_appointment_fields(appointment)
            attendees = [fields["attendee_email"]] if fields["attendee_email"] else None

            body = fields["description"]
            if fields["video_link"]:
                body += f"<br/><br/><a href='{fields['video_link']}'>Join Video Call</a>"

            result = await _run_sync(
                client.create_event,
                access_token=access_token,
                subject=fields["title"],
                start_time=fields["start"],
                end_time=fields["end"],
                attendees=attendees,
                location=fields["location"] or None,
                body=body or None,
            )

            if result and result.get("id"):
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.SUCCESS,
                    external_id=result["id"],
                    link=result.get("webLink"),
                    duration_ms=int((time.monotonic() - start_ms) * 1000),
                )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error="Outlook API returned no event ID",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("OutlookCalendarProvider.create_event failed: %s", e)
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
            client = _get_outlook_client()
            access_token = self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            fields = _extract_appointment_fields(appointment)
            updates: Dict[str, Any] = {
                "subject": fields["title"],
                "start": {"dateTime": fields["start"].isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": fields["end"].isoformat(), "timeZone": "UTC"},
            }
            if fields["description"]:
                updates["body"] = {
                    "contentType": "HTML",
                    "content": fields["description"],
                }
            if fields["location"]:
                updates["location"] = {"displayName": fields["location"]}
            if fields["attendee_email"]:
                updates["attendees"] = [
                    {"emailAddress": {"address": fields["attendee_email"]}, "type": "required"}
                ]

            result = await _run_sync(
                client.update_event,
                access_token=access_token,
                event_id=external_id,
                updates=updates,
            )

            if result is not None:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.SUCCESS,
                    external_id=external_id,
                    link=result.get("webLink") if isinstance(result, dict) else None,
                    duration_ms=int((time.monotonic() - start_ms) * 1000),
                )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.FAILED,
                error="Outlook API update returned None",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("OutlookCalendarProvider.update_event failed: %s", e)
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
            client = _get_outlook_client()
            access_token = self._ensure_valid_token(credentials)
            if not access_token:
                return ProviderSyncResult(
                    provider=self.provider_name,
                    status=SyncStatus.FAILED,
                    error="Could not obtain valid access token",
                )

            success = await _run_sync(
                client.delete_event,
                access_token=access_token,
                event_id=external_id,
            )

            return ProviderSyncResult(
                provider=self.provider_name,
                status=SyncStatus.SUCCESS if success else SyncStatus.FAILED,
                external_id=external_id,
                error=None if success else "Outlook delete returned False",
                duration_ms=int((time.monotonic() - start_ms) * 1000),
            )

        except Exception as e:
            logger.error("OutlookCalendarProvider.delete_event failed: %s", e)
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
            client = _get_outlook_client()
            access_token = self._ensure_valid_token(credentials)
            if not access_token:
                logger.warning("OutlookCalendarProvider: no valid token for busy times")
                return []

            result = await _run_sync(
                client.list_events,
                access_token=access_token,
                start_time=start,
                end_time=end,
            )

            if not result or "value" not in result:
                return []

            busy_blocks: List[BusyBlock] = []
            for event in result["value"]:
                # Skip free/tentative events
                show_as = event.get("showAs", "busy")
                if show_as == "free":
                    continue

                event_start = self._parse_outlook_datetime(event.get("start", {}))
                event_end = self._parse_outlook_datetime(event.get("end", {}))

                if event_start and event_end:
                    busy_blocks.append(BusyBlock(
                        start=event_start,
                        end=event_end,
                        provider=self.provider_name,
                        title=event.get("subject"),
                        is_all_day=event.get("isAllDay", False),
                    ))

            return busy_blocks

        except Exception as e:
            logger.error("OutlookCalendarProvider.get_busy_times failed: %s", e)
            return []

    async def test_connection(
        self,
        credentials: Dict[str, Any],
    ) -> bool:
        try:
            client = _get_outlook_client()
            access_token = self._ensure_valid_token(credentials)
            if not access_token:
                return False

            result = await _run_sync(client.get_user_info, access_token=access_token)
            return result is not None

        except Exception as e:
            logger.error("OutlookCalendarProvider.test_connection failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_valid_token(self, credentials: Dict[str, Any]) -> Optional[str]:
        """Return a valid access token, refreshing synchronously if expired."""
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
                    client = _get_outlook_client()
                    refreshed = client.refresh_access_token(refresh_token)
                    if refreshed and refreshed.get("access_token"):
                        return refreshed["access_token"]
                    return None
            except (ValueError, TypeError):
                pass  # Can't parse expiry; use existing token

        return access_token

    @staticmethod
    def _parse_outlook_datetime(dt_dict: Dict[str, Any]) -> Optional[datetime]:
        """Parse Outlook start/end dict into a datetime."""
        if not dt_dict:
            return None

        raw = dt_dict.get("dateTime")
        if not raw:
            return None

        try:
            # Outlook datetimes may or may not include timezone info
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
