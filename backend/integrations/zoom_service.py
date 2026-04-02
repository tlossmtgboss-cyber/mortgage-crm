"""
Zoom OAuth Integration
Handles OAuth authentication and meeting operations for Zoom
"""
import os
import logging
import base64
import time
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Zoom OAuth scopes
ZOOM_SCOPES = [
    "meeting:read",
    "meeting:write",
    "user:read",
    "recording:read",
]


class ZoomClient:
    """Zoom API client for OAuth and meeting operations"""

    def __init__(self):
        self.client_id = os.getenv("ZOOM_CLIENT_ID", "")
        self.client_secret = os.getenv("ZOOM_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "ZOOM_REDIRECT_URI",
            "https://app.perenniaai.com/api/v1/zoom/callback"
        )

        self.auth_url = "https://zoom.us/oauth/authorize"
        self.token_url = "https://zoom.us/oauth/token"
        self.api_base_url = "https://api.zoom.us/v2"

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info("Zoom API initialized successfully")
        else:
            logger.warning("Zoom API credentials not configured")

    def _get_basic_auth_header(self) -> str:
        """Get Base64 encoded client credentials for Basic auth"""
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()

    def get_authorization_url(self, state: str = None) -> str:
        """Generate Zoom OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={
                    "Authorization": f"Basic {self._get_basic_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully exchanged code for Zoom access token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "bearer"),
                "scope": token_data.get("scope"),
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"Zoom token exchange HTTP error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh an expired access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={
                    "Authorization": f"Basic {self._get_basic_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed Zoom access token")

            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "bearer"),
            }

        except Exception as e:
            logger.error(f"Error refreshing Zoom access token: {e}")
            return None

    def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get current user info from Zoom"""
        return self._make_request("GET", "/users/me", access_token)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        data: Dict = None,
        params: Dict = None,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated API request with retry and backoff."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"{self.api_base_url}{endpoint}"
        backoff_delays = [2, 4, 8]  # seconds

        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=30
                )

                # Success
                if response.ok:
                    return response.json() if response.text else {}

                # Rate limited - respect Retry-After header
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", backoff_delays[min(attempt, len(backoff_delays) - 1)]))
                    logger.warning(f"Zoom API rate limited, retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue

                # Server errors - retry with backoff
                if response.status_code in (502, 503, 504):
                    delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                    logger.warning(f"Zoom API server error {response.status_code}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue

                # Client errors (4xx except 429) - don't retry
                response.raise_for_status()

            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                    logger.warning(f"Zoom API connection error, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                logger.error(f"Zoom API connection failed after {max_retries} attempts")
                return None

            except requests.exceptions.HTTPError as e:
                logger.error(f"Zoom API error: {e.response.text if e.response else str(e)}")
                return None

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                    logger.warning(f"Zoom API timeout, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                logger.error(f"Zoom API timed out after {max_retries} attempts")
                return None

            except Exception as e:
                logger.error(f"Zoom request error: {e}")
                return None

        logger.error(f"Zoom API request failed after {max_retries} retries: {method} {endpoint}")
        return None

    # Meeting operations
    def list_meetings(
        self,
        access_token: str,
        user_id: str = "me",
        meeting_type: str = "scheduled"
    ) -> Optional[Dict[str, Any]]:
        """List meetings for a user"""
        params = {"type": meeting_type}
        return self._make_request(
            "GET",
            f"/users/{user_id}/meetings",
            access_token,
            params=params
        )

    def get_meeting(
        self,
        access_token: str,
        meeting_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific meeting"""
        return self._make_request("GET", f"/meetings/{meeting_id}", access_token)

    def create_meeting(
        self,
        access_token: str,
        topic: str,
        start_time: datetime,
        duration: int = 60,
        timezone: str = "UTC",
        agenda: str = None,
        user_id: str = "me"
    ) -> Optional[Dict[str, Any]]:
        """Create a new Zoom meeting"""
        meeting_data = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration": duration,
            "timezone": timezone,
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": True,
                "audio": "both",
                "auto_recording": "none"
            }
        }

        if agenda:
            meeting_data["agenda"] = agenda

        return self._make_request(
            "POST",
            f"/users/{user_id}/meetings",
            access_token,
            data=meeting_data
        )

    def update_meeting(
        self,
        access_token: str,
        meeting_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing meeting"""
        return self._make_request(
            "PATCH",
            f"/meetings/{meeting_id}",
            access_token,
            data=updates
        )

    def delete_meeting(
        self,
        access_token: str,
        meeting_id: str
    ) -> bool:
        """Delete a meeting"""
        try:
            response = requests.delete(
                f"{self.api_base_url}/meetings/{meeting_id}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Error deleting meeting: {e}")
            return False

    def list_recordings(
        self,
        access_token: str,
        user_id: str = "me",
        from_date: datetime = None,
        to_date: datetime = None
    ) -> Optional[Dict[str, Any]]:
        """List cloud recordings"""
        params = {}
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d")
        if to_date:
            params["to"] = to_date.strftime("%Y-%m-%d")

        return self._make_request(
            "GET",
            f"/users/{user_id}/recordings",
            access_token,
            params=params
        )

    # ========================================================================
    # ASYNC WRAPPERS (avoid blocking event loop with time.sleep in retries)
    # ========================================================================

    async def async_create_meeting(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for create_meeting - runs in thread pool to avoid blocking."""
        return await asyncio.to_thread(self.create_meeting, *args, **kwargs)

    async def async_update_meeting(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for update_meeting."""
        return await asyncio.to_thread(self.update_meeting, *args, **kwargs)

    async def async_delete_meeting(self, *args, **kwargs) -> bool:
        """Async wrapper for delete_meeting."""
        return await asyncio.to_thread(self.delete_meeting, *args, **kwargs)

    async def async_list_meetings(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for list_meetings."""
        return await asyncio.to_thread(self.list_meetings, *args, **kwargs)

    async def async_get_meeting(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for get_meeting."""
        return await asyncio.to_thread(self.get_meeting, *args, **kwargs)

    async def async_list_recordings(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for list_recordings."""
        return await asyncio.to_thread(self.list_recordings, *args, **kwargs)

    async def async_get_user_info(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for get_user_info."""
        return await asyncio.to_thread(self.get_user_info, *args, **kwargs)

    async def async_exchange_code_for_token(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for exchange_code_for_token."""
        return await asyncio.to_thread(self.exchange_code_for_token, *args, **kwargs)

    async def async_refresh_access_token(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Async wrapper for refresh_access_token."""
        return await asyncio.to_thread(self.refresh_access_token, *args, **kwargs)


# Global instance
zoom_client = ZoomClient()
