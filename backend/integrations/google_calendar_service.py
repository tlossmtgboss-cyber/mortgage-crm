"""
Google Calendar OAuth Integration
Handles OAuth authentication and calendar operations for Google Calendar
"""
import asyncio
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import httpx
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Google Calendar API scopes
CALENDAR_SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

# Transient HTTP status codes worth retrying
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
_MAX_RETRIES = 1
_RETRY_DELAY_SECONDS = 2.0
_REQUEST_TIMEOUT = 30.0


class GoogleCalendarClient:
    """Google Calendar API client for OAuth and calendar operations"""

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "GOOGLE_CALENDAR_REDIRECT_URI",
            "https://app.perenniaai.com/api/v1/google-calendar/callback"
        )

        self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.api_base_url = "https://www.googleapis.com/calendar/v3"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info("Google Calendar API initialized successfully")
        else:
            logger.warning("Google Calendar API credentials not configured")

    def get_authorization_url(self, state: str = None) -> str:
        """Generate Google OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute an HTTP request with retry logic for transient failures.

        Retries up to _MAX_RETRIES times on 5xx status codes and timeouts.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await client.request(method, url, **kwargs)

                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                    logger.warning(
                        "Google Calendar API returned %d on attempt %d, retrying in %.1fs",
                        response.status_code, attempt + 1, _RETRY_DELAY_SECONDS,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exception = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Google Calendar API %s on attempt %d, retrying in %.1fs",
                        type(exc).__name__, attempt + 1, _RETRY_DELAY_SECONDS,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                raise

        # Should not reach here, but satisfy type checker
        raise last_exception  # type: ignore[misc]

    async def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code"
            }

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await self._request_with_retry(
                    client,
                    "POST",
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully exchanged code for Google Calendar access token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
                "scope": token_data.get("scope"),
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Google Calendar token exchange HTTP error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None

    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh an expired access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token"
            }

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await self._request_with_retry(
                    client,
                    "POST",
                    self.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed Google Calendar access token")

            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": refresh_token,  # Google doesn't always return new refresh token
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
            }

        except Exception as e:
            logger.error(f"Error refreshing Google Calendar access token: {e}")
            return None

    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user info from Google"""
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await self._request_with_retry(
                    client,
                    "GET",
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        data: Dict = None,
        params: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated API request"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_base_url}{endpoint}"

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await self._request_with_retry(
                    client,
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                )
                response.raise_for_status()

            return response.json() if response.text else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"Google Calendar API error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Google Calendar request error: {e}")
            return None

    # Calendar operations
    async def list_calendars(self, access_token: str) -> Optional[Dict[str, Any]]:
        """List all calendars for the user"""
        return await self._make_request("GET", "/users/me/calendarList", access_token)

    async def get_calendar(self, access_token: str, calendar_id: str = "primary") -> Optional[Dict[str, Any]]:
        """Get a specific calendar"""
        return await self._make_request("GET", f"/calendars/{calendar_id}", access_token)

    async def list_events(
        self,
        access_token: str,
        calendar_id: str = "primary",
        time_min: datetime = None,
        time_max: datetime = None,
        max_results: int = 100
    ) -> Optional[Dict[str, Any]]:
        """List events from a calendar"""
        params = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime"
        }

        if time_min:
            params["timeMin"] = time_min.isoformat() + "Z"
        if time_max:
            params["timeMax"] = time_max.isoformat() + "Z"

        return await self._make_request(
            "GET",
            f"/calendars/{calendar_id}/events",
            access_token,
            params=params
        )

    async def create_event(
        self,
        access_token: str,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str = None,
        location: str = None,
        attendees: List[str] = None,
        calendar_id: str = "primary"
    ) -> Optional[Dict[str, Any]]:
        """Create a new calendar event"""
        event_data = {
            "summary": summary,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC"
            }
        }

        if description:
            event_data["description"] = description
        if location:
            event_data["location"] = location
        if attendees:
            event_data["attendees"] = [{"email": email} for email in attendees]

        return await self._make_request(
            "POST",
            f"/calendars/{calendar_id}/events",
            access_token,
            data=event_data
        )

    async def update_event(
        self,
        access_token: str,
        event_id: str,
        updates: Dict[str, Any],
        calendar_id: str = "primary"
    ) -> Optional[Dict[str, Any]]:
        """Update an existing event"""
        return await self._make_request(
            "PATCH",
            f"/calendars/{calendar_id}/events/{event_id}",
            access_token,
            data=updates
        )

    async def delete_event(
        self,
        access_token: str,
        event_id: str,
        calendar_id: str = "primary"
    ) -> bool:
        """Delete an event"""
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            url = f"{self.api_base_url}/calendars/{calendar_id}/events/{event_id}"

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await self._request_with_retry(
                    client,
                    "DELETE",
                    url,
                    headers=headers,
                )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return False


# Global instance
google_calendar_client = GoogleCalendarClient()
