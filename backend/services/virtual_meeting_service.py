"""
Virtual Meeting Service - Provider-agnostic meeting management.

Provides an abstract MeetingProvider interface with concrete implementations
for Zoom (REST API with OAuth2), Google Meet (via Calendar API), and
Microsoft Teams (via MS Graph). A MeetingProviderFactory selects the
appropriate provider based on configuration.

Integration point: called from scheduler appointment routes to auto-attach
meeting links when meeting_type/meeting_mode indicates a video appointment.

Providers:
  - ZoomMeetingProvider:    Zoom REST API (OAuth2 tokens per user)
  - GoogleMeetProvider:     Google Calendar API (conferenceData)
  - TeamsMeetingProvider:   MS Graph onlineMeetings
  - PerenniaMeetProvider:   Self-hosted fallback (always available)

Usage:
    from services.virtual_meeting_service import MeetingProviderFactory

    provider = MeetingProviderFactory.get_provider("zoom", db, user_id, org_id)
    result = await provider.create_meeting(details)
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class MeetingProviderType(str, Enum):
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    TEAMS = "teams"
    PERENNIA = "perennia"
    MANUAL = "manual"


@dataclass
class MeetingDetails:
    """Input details for creating a virtual meeting."""
    title: str
    scheduled_start: datetime
    scheduled_end: datetime
    duration_minutes: int = 30
    description: str = ""
    timezone: str = DEFAULT_TIMEZONE
    attendee_emails: List[str] = field(default_factory=list)
    attendee_name: str = ""
    appointment_id: Optional[int] = None
    organization_id: Optional[int] = None


@dataclass
class MeetingResult:
    """Result of a meeting provider operation."""
    success: bool
    provider: str
    join_url: str = ""
    host_url: str = ""
    meeting_id: str = ""
    passcode: str = ""
    dial_in_numbers: List[Dict[str, str]] = field(default_factory=list)
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "provider": self.provider,
            "join_url": self.join_url,
            "host_url": self.host_url,
            "meeting_id": self.meeting_id,
            "passcode": self.passcode,
            "dial_in_numbers": self.dial_in_numbers,
            "error": self.error,
            "metadata": self.metadata,
        }

    @staticmethod
    def failure(provider: str, error: str) -> "MeetingResult":
        return MeetingResult(success=False, provider=provider, error=error)


# =============================================================================
# ABSTRACT PROVIDER INTERFACE
# =============================================================================

class MeetingProvider(ABC):
    """Abstract base class for virtual meeting providers."""

    provider_type: MeetingProviderType

    def __init__(self, db: Session, user_id: Optional[int] = None, org_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        self.org_id = org_id

    @abstractmethod
    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Create a new virtual meeting and return join details."""
        ...

    @abstractmethod
    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Update an existing meeting's time/details."""
        ...

    @abstractmethod
    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Delete/cancel a virtual meeting."""
        ...

    @abstractmethod
    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Get the join URL for an existing meeting."""
        ...

    @abstractmethod
    async def test_connection(self) -> MeetingResult:
        """Test connectivity to the meeting provider."""
        ...

    def _get_user_token(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth token from user_integrations table."""
        if not self.user_id:
            return None
        try:
            result = self.db.execute(
                text("""
                    SELECT access_token, refresh_token, expires_at
                    FROM user_integrations
                    WHERE user_id = :user_id AND provider = :provider
                """),
                {"user_id": self.user_id, "provider": provider_name},
            )
            row = result.fetchone()
            if row:
                return {
                    "access_token": row[0],
                    "refresh_token": row[1],
                    "expires_at": row[2],
                }
        except Exception as e:
            logger.warning(f"Error fetching {provider_name} token for user {self.user_id}: {e}")
        return None


# =============================================================================
# ZOOM PROVIDER
# =============================================================================

class ZoomMeetingProvider(MeetingProvider):
    """Zoom meeting provider using Zoom REST API with OAuth2."""

    provider_type = MeetingProviderType.ZOOM

    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Create a Zoom meeting."""
        token_data = self._get_user_token("zoom")
        if not token_data:
            return MeetingResult.failure("zoom", "No Zoom OAuth connection for user")

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at")

        # Refresh token if expired
        if expires_at and isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
            access_token = await self._refresh_token(refresh_token)
            if not access_token:
                return MeetingResult.failure("zoom", "Failed to refresh expired Zoom token")

        try:
            from integrations.zoom_service import zoom_client

            if not zoom_client.enabled:
                return MeetingResult.failure("zoom", "Zoom integration not configured (missing credentials)")

            meeting_data = await zoom_client.async_create_meeting(
                access_token=access_token,
                topic=details.title,
                start_time=details.scheduled_start,
                duration=details.duration_minutes,
                timezone=details.timezone,
                agenda=details.description or None,
            )

            if not meeting_data:
                return MeetingResult.failure("zoom", "Zoom API returned no data")

            # Extract dial-in numbers
            dial_in_numbers = []
            raw_dial_numbers = meeting_data.get("settings", {}).get("global_dial_in_numbers", [])
            for num in raw_dial_numbers:
                dial_in_numbers.append({
                    "number": num.get("number", ""),
                    "country": num.get("country", ""),
                    "country_name": num.get("country_name", ""),
                })

            return MeetingResult(
                success=True,
                provider="zoom",
                join_url=meeting_data.get("join_url", ""),
                host_url=meeting_data.get("start_url", ""),
                meeting_id=str(meeting_data.get("id", "")),
                passcode=meeting_data.get("password", ""),
                dial_in_numbers=dial_in_numbers,
                metadata={
                    "zoom_meeting_id": str(meeting_data.get("id", "")),
                    "zoom_host_id": meeting_data.get("host_id"),
                    "zoom_uuid": meeting_data.get("uuid"),
                },
            )
        except ImportError:
            return MeetingResult.failure("zoom", "Zoom service module not available")
        except Exception as e:
            logger.exception(f"Error creating Zoom meeting: {e}")
            return MeetingResult.failure("zoom", str(e))

    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Update an existing Zoom meeting."""
        token_data = self._get_user_token("zoom")
        if not token_data:
            return MeetingResult.failure("zoom", "No Zoom OAuth connection for user")

        try:
            from integrations.zoom_service import zoom_client

            if not zoom_client.enabled:
                return MeetingResult.failure("zoom", "Zoom integration not configured")

            access_token = token_data["access_token"]
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://api.zoom.us/v2/meetings/{meeting_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "topic": details.title,
                        "start_time": details.scheduled_start.strftime("%Y-%m-%dT%H:%M:%S"),
                        "duration": details.duration_minutes,
                        "timezone": details.timezone,
                    },
                )
                if response.status_code == 204:
                    return MeetingResult(
                        success=True,
                        provider="zoom",
                        meeting_id=meeting_id,
                        metadata={"updated": True},
                    )
                return MeetingResult.failure("zoom", f"Zoom update returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error updating Zoom meeting {meeting_id}: {e}")
            return MeetingResult.failure("zoom", str(e))

    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Delete a Zoom meeting."""
        token_data = self._get_user_token("zoom")
        if not token_data:
            return MeetingResult.failure("zoom", "No Zoom OAuth connection for user")

        try:
            from integrations.zoom_service import zoom_client

            if not zoom_client.enabled:
                return MeetingResult.failure("zoom", "Zoom integration not configured")

            access_token = token_data["access_token"]
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"https://api.zoom.us/v2/meetings/{meeting_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code in (200, 204):
                    return MeetingResult(
                        success=True,
                        provider="zoom",
                        meeting_id=meeting_id,
                        metadata={"deleted": True},
                    )
                return MeetingResult.failure("zoom", f"Zoom delete returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error deleting Zoom meeting {meeting_id}: {e}")
            return MeetingResult.failure("zoom", str(e))

    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Get join URL for existing Zoom meeting."""
        token_data = self._get_user_token("zoom")
        if not token_data:
            return None

        try:
            from integrations.zoom_service import zoom_client

            if not zoom_client.enabled:
                return None

            access_token = token_data["access_token"]
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"https://api.zoom.us/v2/meetings/{meeting_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("join_url")
        except Exception as e:
            logger.warning(f"Error getting Zoom join URL for {meeting_id}: {e}")
        return None

    async def test_connection(self) -> MeetingResult:
        """Test Zoom connectivity by checking user info."""
        token_data = self._get_user_token("zoom")
        if not token_data:
            return MeetingResult.failure("zoom", "No Zoom OAuth connection for user")

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://api.zoom.us/v2/users/me",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code == 200:
                    user_data = response.json()
                    return MeetingResult(
                        success=True,
                        provider="zoom",
                        metadata={
                            "user_email": user_data.get("email"),
                            "account_type": user_data.get("type"),
                        },
                    )
                return MeetingResult.failure("zoom", f"Zoom API returned status {response.status_code}")
        except Exception as e:
            return MeetingResult.failure("zoom", str(e))

    async def _refresh_token(self, refresh_token: Optional[str]) -> Optional[str]:
        """Refresh an expired Zoom token."""
        if not refresh_token:
            return None
        try:
            from integrations.zoom_service import zoom_client
            token_data = await zoom_client.async_refresh_access_token(refresh_token)
            if token_data:
                new_access_token = token_data.get("access_token")
                self.db.execute(
                    text("""
                        UPDATE user_integrations
                        SET access_token = :access_token,
                            refresh_token = :refresh_token,
                            expires_at = :expires_at,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id AND provider = 'zoom'
                    """),
                    {
                        "user_id": self.user_id,
                        "access_token": new_access_token,
                        "refresh_token": token_data.get("refresh_token", refresh_token),
                        "expires_at": token_data.get("expires_at"),
                    },
                )
                self.db.flush()
                return new_access_token
        except Exception as e:
            logger.warning(f"Failed to refresh Zoom token for user {self.user_id}: {e}")
        return None


# =============================================================================
# GOOGLE MEET PROVIDER
# =============================================================================

class GoogleMeetProvider(MeetingProvider):
    """Google Meet provider using Google Calendar API conferenceData."""

    provider_type = MeetingProviderType.GOOGLE_MEET

    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Create a Google Meet meeting via Calendar API."""
        token_data = self._get_user_token("google")
        if not token_data:
            return MeetingResult.failure("google_meet", "No Google OAuth connection for user")

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at")

        # Refresh token if expired
        if expires_at and isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
            access_token = await self._refresh_google_token(refresh_token)
            if not access_token:
                return MeetingResult.failure("google_meet", "Failed to refresh expired Google token")

        try:
            import httpx

            # Build calendar event with conferenceData for Google Meet
            event_body = {
                "summary": details.title,
                "description": details.description,
                "start": {
                    "dateTime": details.scheduled_start.isoformat(),
                    "timeZone": details.timezone,
                },
                "end": {
                    "dateTime": details.scheduled_end.isoformat(),
                    "timeZone": details.timezone,
                },
                "conferenceData": {
                    "createRequest": {
                        "requestId": secrets.token_hex(8),
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                },
            }

            # Add attendees if provided
            if details.attendee_emails:
                event_body["attendees"] = [
                    {"email": email} for email in details.attendee_emails
                ]

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                    "?conferenceDataVersion=1",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=event_body,
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    conference_data = data.get("conferenceData", {})
                    entry_points = conference_data.get("entryPoints", [])

                    join_url = ""
                    dial_in_numbers = []
                    for ep in entry_points:
                        if ep.get("entryPointType") == "video":
                            join_url = ep.get("uri", "")
                        elif ep.get("entryPointType") == "phone":
                            dial_in_numbers.append({
                                "number": ep.get("uri", "").replace("tel:", ""),
                                "country": ep.get("regionCode", ""),
                                "pin": ep.get("pin", ""),
                            })

                    meeting_id = conference_data.get("conferenceId", data.get("id", ""))

                    return MeetingResult(
                        success=True,
                        provider="google_meet",
                        join_url=join_url,
                        meeting_id=meeting_id,
                        dial_in_numbers=dial_in_numbers,
                        metadata={
                            "calendar_event_id": data.get("id"),
                            "html_link": data.get("htmlLink"),
                        },
                    )

                error_msg = f"Google Calendar API returned status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception as _exc:  # noqa: BLE001
                    pass
                return MeetingResult.failure("google_meet", error_msg)

        except Exception as e:
            logger.exception(f"Error creating Google Meet meeting: {e}")
            return MeetingResult.failure("google_meet", str(e))

    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Update an existing Google Calendar event."""
        token_data = self._get_user_token("google")
        if not token_data:
            return MeetingResult.failure("google_meet", "No Google OAuth connection")

        try:
            import httpx

            event_body = {
                "summary": details.title,
                "description": details.description,
                "start": {
                    "dateTime": details.scheduled_start.isoformat(),
                    "timeZone": details.timezone,
                },
                "end": {
                    "dateTime": details.scheduled_end.isoformat(),
                    "timeZone": details.timezone,
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{meeting_id}"
                    "?conferenceDataVersion=1",
                    headers={
                        "Authorization": f"Bearer {token_data['access_token']}",
                        "Content-Type": "application/json",
                    },
                    json=event_body,
                )
                if response.status_code == 200:
                    return MeetingResult(
                        success=True,
                        provider="google_meet",
                        meeting_id=meeting_id,
                        metadata={"updated": True},
                    )
                return MeetingResult.failure("google_meet", f"Update returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error updating Google Meet {meeting_id}: {e}")
            return MeetingResult.failure("google_meet", str(e))

    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Delete a Google Calendar event (which removes the Meet link)."""
        token_data = self._get_user_token("google")
        if not token_data:
            return MeetingResult.failure("google_meet", "No Google OAuth connection")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{meeting_id}",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code in (200, 204):
                    return MeetingResult(
                        success=True,
                        provider="google_meet",
                        meeting_id=meeting_id,
                        metadata={"deleted": True},
                    )
                return MeetingResult.failure("google_meet", f"Delete returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error deleting Google Meet {meeting_id}: {e}")
            return MeetingResult.failure("google_meet", str(e))

    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Get join URL from Google Calendar event."""
        token_data = self._get_user_token("google")
        if not token_data:
            return None

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{meeting_id}",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    conference_data = data.get("conferenceData", {})
                    for ep in conference_data.get("entryPoints", []):
                        if ep.get("entryPointType") == "video":
                            return ep.get("uri")
        except Exception as e:
            logger.warning(f"Error fetching Google Meet URL for {meeting_id}: {e}")
        return None

    async def test_connection(self) -> MeetingResult:
        """Test Google Calendar API connectivity."""
        token_data = self._get_user_token("google")
        if not token_data:
            return MeetingResult.failure("google_meet", "No Google OAuth connection for user")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code == 200:
                    cal_data = response.json()
                    return MeetingResult(
                        success=True,
                        provider="google_meet",
                        metadata={
                            "calendar_id": cal_data.get("id"),
                            "summary": cal_data.get("summary"),
                            "timezone": cal_data.get("timeZone"),
                        },
                    )
                return MeetingResult.failure("google_meet", f"Calendar API returned {response.status_code}")
        except Exception as e:
            return MeetingResult.failure("google_meet", str(e))

    async def _refresh_google_token(self, refresh_token: Optional[str]) -> Optional[str]:
        """Refresh expired Google OAuth token."""
        if not refresh_token:
            return None
        try:
            import httpx

            client_id = os.getenv("GOOGLE_CLIENT_ID", "")
            client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
            if not client_id or not client_secret:
                return None

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if response.status_code == 200:
                    token_data = response.json()
                    new_access_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    self.db.execute(
                        text("""
                            UPDATE user_integrations
                            SET access_token = :access_token,
                                expires_at = :expires_at,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id AND provider = 'google'
                        """),
                        {
                            "user_id": self.user_id,
                            "access_token": new_access_token,
                            "expires_at": new_expires_at,
                        },
                    )
                    self.db.flush()
                    return new_access_token
        except Exception as e:
            logger.warning(f"Failed to refresh Google token for user {self.user_id}: {e}")
        return None


# =============================================================================
# TEAMS PROVIDER
# =============================================================================

class TeamsMeetingProvider(MeetingProvider):
    """Microsoft Teams meeting provider using MS Graph API."""

    provider_type = MeetingProviderType.TEAMS

    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Create a Teams meeting via MS Graph."""
        try:
            from services.microsoft_graph import create_event_via_graph, CalendarResult

            result: CalendarResult = await create_event_via_graph(
                user_id=self.user_id,
                subject=details.title,
                start=details.scheduled_start,
                end=details.scheduled_end,
                db=self.db,
                attendees=details.attendee_emails if details.attendee_emails else None,
                add_teams_link=True,
                body=details.description or "",
            )

            if result.success and result.join_url:
                return MeetingResult(
                    success=True,
                    provider="teams",
                    join_url=result.join_url,
                    meeting_id=result.event_id or "",
                    metadata={
                        "outlook_event_id": result.event_id,
                    },
                )

            return MeetingResult.failure("teams", result.error or "Teams meeting creation failed")

        except ImportError:
            return MeetingResult.failure("teams", "Microsoft Graph service not available")
        except Exception as e:
            logger.exception(f"Error creating Teams meeting: {e}")
            return MeetingResult.failure("teams", str(e))

    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Update a Teams meeting via MS Graph."""
        token_data = self._get_user_token("microsoft")
        if not token_data:
            return MeetingResult.failure("teams", "No Microsoft OAuth connection")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}",
                    headers={
                        "Authorization": f"Bearer {token_data['access_token']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "subject": details.title,
                        "body": {"contentType": "text", "content": details.description},
                        "start": {
                            "dateTime": details.scheduled_start.isoformat(),
                            "timeZone": details.timezone,
                        },
                        "end": {
                            "dateTime": details.scheduled_end.isoformat(),
                            "timeZone": details.timezone,
                        },
                    },
                )
                if response.status_code == 200:
                    return MeetingResult(
                        success=True,
                        provider="teams",
                        meeting_id=meeting_id,
                        metadata={"updated": True},
                    )
                return MeetingResult.failure("teams", f"Update returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error updating Teams meeting {meeting_id}: {e}")
            return MeetingResult.failure("teams", str(e))

    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Delete a Teams meeting via MS Graph."""
        token_data = self._get_user_token("microsoft")
        if not token_data:
            return MeetingResult.failure("teams", "No Microsoft OAuth connection")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code in (200, 204):
                    return MeetingResult(
                        success=True,
                        provider="teams",
                        meeting_id=meeting_id,
                        metadata={"deleted": True},
                    )
                return MeetingResult.failure("teams", f"Delete returned status {response.status_code}")
        except Exception as e:
            logger.exception(f"Error deleting Teams meeting {meeting_id}: {e}")
            return MeetingResult.failure("teams", str(e))

    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Get join URL for a Teams meeting."""
        token_data = self._get_user_token("microsoft")
        if not token_data:
            return None

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://graph.microsoft.com/v1.0/me/events/{meeting_id}",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                    params={"$select": "onlineMeeting"},
                )
                if response.status_code == 200:
                    data = response.json()
                    online_meeting = data.get("onlineMeeting", {})
                    return online_meeting.get("joinUrl")
        except Exception as e:
            logger.warning(f"Error fetching Teams join URL for {meeting_id}: {e}")
        return None

    async def test_connection(self) -> MeetingResult:
        """Test MS Graph connectivity."""
        token_data = self._get_user_token("microsoft")
        if not token_data:
            return MeetingResult.failure("teams", "No Microsoft OAuth connection for user")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                if response.status_code == 200:
                    user_data = response.json()
                    return MeetingResult(
                        success=True,
                        provider="teams",
                        metadata={
                            "user_email": user_data.get("mail") or user_data.get("userPrincipalName"),
                            "display_name": user_data.get("displayName"),
                        },
                    )
                return MeetingResult.failure("teams", f"Graph API returned {response.status_code}")
        except Exception as e:
            return MeetingResult.failure("teams", str(e))


# =============================================================================
# PERENNIA MEET PROVIDER (self-hosted fallback)
# =============================================================================

class PerenniaMeetProvider(MeetingProvider):
    """Self-hosted Perennia Meet fallback provider. Always available."""

    provider_type = MeetingProviderType.PERENNIA

    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Generate a Perennia Meet room link."""
        salt = os.getenv("SECRET_KEY", "")
        if not salt:
            logger.critical(
                "SECRET_KEY not set — cannot generate deterministic meeting room IDs securely"
            )
            raise RuntimeError(
                "SECRET_KEY environment variable must be set for meeting link generation"
            )
        appt_id = details.appointment_id or secrets.token_hex(4)
        hash_input = f"{appt_id}:{details.scheduled_start.isoformat()}:{salt}"
        room_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]
        room_id = f"{room_hash[:4]}-{room_hash[4:8]}-{room_hash[8:12]}"

        base_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        join_url = f"{base_url}/meet/{room_id}"

        return MeetingResult(
            success=True,
            provider="perennia",
            join_url=join_url,
            meeting_id=room_id,
            metadata={
                "room_id": room_id,
                "appointment_id": str(appt_id),
            },
        )

    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Perennia Meet rooms are stateless -- update is a no-op."""
        return MeetingResult(
            success=True,
            provider="perennia",
            meeting_id=meeting_id,
            metadata={"updated": True, "note": "Perennia Meet rooms are stateless"},
        )

    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Perennia Meet rooms are ephemeral -- delete is a no-op."""
        return MeetingResult(
            success=True,
            provider="perennia",
            meeting_id=meeting_id,
            metadata={"deleted": True, "note": "Perennia Meet rooms are ephemeral"},
        )

    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Reconstruct join URL from room ID."""
        base_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        return f"{base_url}/meet/{meeting_id}"

    async def test_connection(self) -> MeetingResult:
        """Perennia Meet is always available."""
        return MeetingResult(
            success=True,
            provider="perennia",
            metadata={"status": "always_available"},
        )


# =============================================================================
# MANUAL PROVIDER (user-supplied link)
# =============================================================================

class ManualMeetingProvider(MeetingProvider):
    """Manual meeting provider for user-supplied external links.

    Used when the user provides their own meeting URL (e.g., a personal Zoom
    link, a Google Meet link they created outside of Perennia, a Webex link,
    etc.). The provider stores the link but does not manage the meeting lifecycle
    on the remote platform.
    """

    provider_type = MeetingProviderType.MANUAL

    def __init__(
        self,
        db: Session,
        user_id: Optional[int] = None,
        org_id: Optional[int] = None,
        manual_url: str = "",
    ):
        super().__init__(db=db, user_id=user_id, org_id=org_id)
        self.manual_url = manual_url

    async def create_meeting(self, details: MeetingDetails) -> MeetingResult:
        """Store a manually-supplied meeting link.

        The URL should be set via the `manual_url` constructor parameter or
        passed as `details.description` when no explicit URL is provided.
        """
        url = self.manual_url
        if not url:
            return MeetingResult.failure("manual", "No meeting URL provided")

        return MeetingResult(
            success=True,
            provider="manual",
            join_url=url,
            meeting_id="manual",
            metadata={"source": "user_supplied"},
        )

    async def update_meeting(self, meeting_id: str, details: MeetingDetails) -> MeetingResult:
        """Manual meetings are not managed -- update is a no-op."""
        return MeetingResult(
            success=True,
            provider="manual",
            meeting_id=meeting_id,
            metadata={"updated": True, "note": "Manual meetings are not managed by Perennia"},
        )

    async def delete_meeting(self, meeting_id: str) -> MeetingResult:
        """Manual meetings are not managed -- delete clears local reference only."""
        return MeetingResult(
            success=True,
            provider="manual",
            meeting_id=meeting_id,
            metadata={"deleted": True, "note": "Link removed locally; external meeting unchanged"},
        )

    async def get_join_url(self, meeting_id: str) -> Optional[str]:
        """Return the stored manual URL."""
        return self.manual_url or None

    async def test_connection(self) -> MeetingResult:
        """Manual provider is always available."""
        return MeetingResult(
            success=True,
            provider="manual",
            metadata={"status": "always_available", "note": "Manual links do not require connectivity"},
        )


# =============================================================================
# PROVIDER FACTORY
# =============================================================================

class MeetingProviderFactory:
    """Factory to get the appropriate meeting provider by type."""

    _providers = {
        "zoom": ZoomMeetingProvider,
        "google_meet": GoogleMeetProvider,
        "teams": TeamsMeetingProvider,
        "perennia": PerenniaMeetProvider,
        "manual": ManualMeetingProvider,
    }

    @classmethod
    def get_provider(
        cls,
        provider_type: str,
        db: Session,
        user_id: Optional[int] = None,
        org_id: Optional[int] = None,
    ) -> MeetingProvider:
        """Get a meeting provider instance by type.

        Args:
            provider_type: One of "zoom", "google_meet", "teams", "perennia", or "auto".
            db: SQLAlchemy session.
            user_id: User ID for OAuth token retrieval.
            org_id: Organization ID for tenant scoping.

        Returns:
            MeetingProvider instance.

        Raises:
            ValueError: If provider_type is unknown.
        """
        if provider_type == "auto":
            provider_type = cls._detect_best_provider(db, user_id)

        provider_class = cls._providers.get(provider_type)
        if provider_class is None:
            raise ValueError(
                f"Unknown meeting provider: '{provider_type}'. "
                f"Available: {', '.join(cls._providers.keys())}"
            )

        return provider_class(db=db, user_id=user_id, org_id=org_id)

    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Return list of available provider type names."""
        return list(cls._providers.keys())

    @classmethod
    def _detect_best_provider(cls, db: Session, user_id: Optional[int]) -> str:
        """Auto-detect the best available provider for a user.

        Priority: Zoom > Google > Teams > Perennia
        """
        if not user_id:
            return "perennia"

        try:
            result = db.execute(
                text("""
                    SELECT provider
                    FROM user_integrations
                    WHERE user_id = :user_id
                      AND provider IN ('zoom', 'google', 'microsoft')
                    ORDER BY
                        CASE provider
                            WHEN 'zoom' THEN 1
                            WHEN 'google' THEN 2
                            WHEN 'microsoft' THEN 3
                        END
                """),
                {"user_id": user_id},
            )
            rows = result.fetchall()

            for row in rows:
                provider_name = row[0]
                if provider_name == "zoom":
                    return "zoom"
                if provider_name == "google":
                    return "google_meet"
                if provider_name == "microsoft":
                    return "teams"

        except Exception as e:
            logger.warning(f"Error detecting meeting provider for user {user_id}: {e}")

        return "perennia"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def create_meeting_for_appointment(
    db: Session,
    appointment,
    provider: str = "auto",
    user_id: Optional[int] = None,
    org_id: Optional[int] = None,
) -> MeetingResult:
    """Convenience function to create a meeting and attach it to an appointment.

    This is the primary integration point for appointment creation flows.
    Creates the meeting, then updates the appointment's video_link, dial_in_info,
    and metadata fields.

    Args:
        db: Database session.
        appointment: Appointment ORM object (must have id, title, scheduled_start, etc.).
        provider: Provider name or "auto".
        user_id: Override user ID.
        org_id: Override organization ID.

    Returns:
        MeetingResult with the full meeting details.
    """
    effective_user_id = user_id or getattr(appointment, "assigned_user_id", None)
    effective_org_id = org_id or getattr(appointment, "organization_id", None)

    meeting_provider = MeetingProviderFactory.get_provider(
        provider, db, effective_user_id, effective_org_id
    )

    details = MeetingDetails(
        title=getattr(appointment, "title", "Meeting") or "Meeting",
        scheduled_start=getattr(appointment, "scheduled_start", datetime.now(timezone.utc)),
        scheduled_end=getattr(
            appointment,
            "scheduled_end",
            getattr(appointment, "scheduled_start", datetime.now(timezone.utc)) + timedelta(minutes=30),
        ),
        duration_minutes=getattr(appointment, "duration_minutes", 30) or 30,
        description=getattr(appointment, "description", "") or "",
        timezone=getattr(appointment, "timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE,
        attendee_emails=(
            [getattr(appointment, "attendee_email", "")]
            if getattr(appointment, "attendee_email", None)
            else []
        ),
        attendee_name=getattr(appointment, "attendee_name", "") or "",
        appointment_id=getattr(appointment, "id", None),
        organization_id=effective_org_id,
    )

    result = await meeting_provider.create_meeting(details)

    # If primary provider fails, fall back to Perennia Meet
    if not result.success and provider != "perennia":
        logger.warning(
            f"Primary provider '{provider}' failed for appointment {details.appointment_id}: "
            f"{result.error}. Falling back to Perennia Meet."
        )
        fallback = PerenniaMeetProvider(db=db, user_id=effective_user_id, org_id=effective_org_id)
        result = await fallback.create_meeting(details)

    # Attach meeting details to the appointment ORM object
    if result.success:
        appointment.video_link = result.join_url

        dial_parts = []
        if result.dial_in_numbers:
            for num in result.dial_in_numbers:
                dial_parts.append(f"Dial-in: {num.get('number', '')}")
        if result.passcode:
            dial_parts.append(f"Passcode: {result.passcode}")
        if dial_parts:
            existing_dial = getattr(appointment, "dial_in_info", None) or ""
            if existing_dial:
                dial_parts.insert(0, existing_dial)
            appointment.dial_in_info = "\n".join(dial_parts)

        logger.info(
            f"Meeting attached to appointment {details.appointment_id}: "
            f"provider={result.provider}, url={result.join_url}"
        )

    return result


# =============================================================================
# PROVIDER SETTINGS PERSISTENCE
# =============================================================================

@dataclass
class MeetingProviderSettings:
    """Per-user meeting provider preferences."""
    user_id: int
    organization_id: int
    default_provider: str = "auto"
    auto_create_for_video: bool = True
    default_meeting_duration: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "default_provider": self.default_provider,
            "auto_create_for_video": self.auto_create_for_video,
            "default_meeting_duration": self.default_meeting_duration,
        }


def get_meeting_provider_settings(
    db: Session,
    user_id: int,
    org_id: int,
) -> MeetingProviderSettings:
    """Retrieve meeting provider settings for a user.

    Settings are stored in the user_settings JSON column on the users table.
    Falls back to defaults if not configured.
    """
    try:
        result = db.execute(
            text("""
                SELECT user_settings
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if row and row[0]:
            settings_json = row[0]
            if isinstance(settings_json, str):
                import json
                settings_json = json.loads(settings_json)
            meeting_settings = settings_json.get("meeting_provider", {})
            return MeetingProviderSettings(
                user_id=user_id,
                organization_id=org_id,
                default_provider=meeting_settings.get("default_provider", "auto"),
                auto_create_for_video=meeting_settings.get("auto_create_for_video", True),
                default_meeting_duration=meeting_settings.get("default_meeting_duration", 30),
            )
    except Exception as e:
        logger.warning(f"Error reading meeting provider settings for user {user_id}: {e}")

    return MeetingProviderSettings(user_id=user_id, organization_id=org_id)


def save_meeting_provider_settings(
    db: Session,
    user_id: int,
    org_id: int,
    default_provider: Optional[str] = None,
    auto_create_for_video: Optional[bool] = None,
    default_meeting_duration: Optional[int] = None,
) -> MeetingProviderSettings:
    """Save meeting provider settings for a user.

    Merges with existing user_settings JSON to avoid overwriting other settings.
    """
    # Read current settings
    current = get_meeting_provider_settings(db, user_id, org_id)

    if default_provider is not None:
        valid = MeetingProviderFactory.get_available_providers() + ["auto"]
        if default_provider not in valid:
            raise ValueError(
                f"Invalid provider '{default_provider}'. Valid: {', '.join(valid)}"
            )
        current.default_provider = default_provider
    if auto_create_for_video is not None:
        current.auto_create_for_video = auto_create_for_video
    if default_meeting_duration is not None:
        current.default_meeting_duration = max(5, min(default_meeting_duration, 480))

    try:
        import json

        # Read existing user_settings
        result = db.execute(
            text("SELECT user_settings FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        existing_settings = {}
        if row and row[0]:
            if isinstance(row[0], str):
                existing_settings = json.loads(row[0])
            elif isinstance(row[0], dict):
                existing_settings = row[0]

        existing_settings["meeting_provider"] = {
            "default_provider": current.default_provider,
            "auto_create_for_video": current.auto_create_for_video,
            "default_meeting_duration": current.default_meeting_duration,
        }

        db.execute(
            text("""
                UPDATE users
                SET user_settings = :settings
                WHERE id = :user_id
            """),
            {"user_id": user_id, "settings": json.dumps(existing_settings)},
        )
        db.flush()

        logger.info(
            f"Meeting provider settings saved for user {user_id}: "
            f"provider={current.default_provider}"
        )

    except Exception as e:
        logger.exception(f"Error saving meeting provider settings for user {user_id}: {e}")
        raise

    return current
