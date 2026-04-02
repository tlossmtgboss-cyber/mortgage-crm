"""
Microsoft Graph API Service for User-Delegated Email and Calendar
==================================================================
This service handles operations that require user consent/delegation,
such as sending emails from a user's own mailbox or managing their calendar.

Uses stored OAuth tokens from the user_integrations table.

For app-only operations (shared mailboxes, tenant-wide), use:
    backend/integrations/microsoft_graph.py -> MicrosoftGraphClient
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging
import os
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class MicrosoftGraphSettings:
    """Microsoft Graph API settings from environment."""

    @property
    def client_id(self) -> str:
        return os.getenv("MICROSOFT_CLIENT_ID", "")

    @property
    def client_secret(self) -> str:
        return os.getenv("MICROSOFT_CLIENT_SECRET", "")

    @property
    def tenant_id(self) -> str:
        return os.getenv("MICROSOFT_TENANT_ID", "common")

    @property
    def redirect_uri(self) -> str:
        return os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback")


settings = MicrosoftGraphSettings()


# =============================================================================
# MODELS
# =============================================================================

class EmailParams(BaseModel):
    """Parameters for sending an email."""
    to: List[str]
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    subject: str
    body: str
    body_type: str = "html"  # "text" or "html"
    importance: str = "normal"  # "low", "normal", "high"
    save_to_sent: bool = True


class CalendarEventParams(BaseModel):
    """Parameters for creating a calendar event."""
    subject: str
    start: datetime
    end: datetime
    body: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    is_online_meeting: bool = False
    reminder_minutes: int = 15


class EmailResult(BaseModel):
    """Result of an email send operation."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


class CalendarResult(BaseModel):
    """Result of a calendar event creation."""
    success: bool
    event_id: Optional[str] = None
    web_link: Optional[str] = None
    teams_link: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# SERVICE CLASS
# =============================================================================

class MicrosoftGraphUserService:
    """
    Microsoft Graph API client for user-delegated operations.

    Uses stored OAuth tokens from UserIntegration table to send emails
    and create calendar events on behalf of a specific user.

    Usage:
        service = MicrosoftGraphUserService(user_id, db)
        result = await service.send_email(EmailParams(...))
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def __init__(self, user_id: int, db: Session):
        """
        Initialize service for a specific user.

        Args:
            user_id: The database ID of the user
            db: SQLAlchemy session
        """
        self.user_id = user_id
        self.db = db
        self.access_token: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Load and validate OAuth token for the user.

        Returns:
            True if successfully initialized with valid token
        """
        try:
            # Import here to avoid circular imports
            from sqlalchemy import text

            # Query user integration
            result = self.db.execute(text("""
                SELECT id, access_token, refresh_token, expires_at
                FROM user_integrations
                WHERE user_id = :user_id AND provider = 'microsoft'
                LIMIT 1
            """), {"user_id": self.user_id}).fetchone()

            if not result or not result.access_token:
                logger.warning(f"No Microsoft integration found for user {self.user_id}")
                return False

            # Check if token is expired (with 5 min buffer)
            now = datetime.now(timezone.utc)
            if result.expires_at and result.expires_at < now + timedelta(minutes=5):
                refreshed = await self._refresh_token(
                    integration_id=result.id,
                    refresh_token=result.refresh_token
                )
                if not refreshed:
                    return False
            else:
                self.access_token = result.access_token

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Microsoft Graph for user {self.user_id}: {e}")
            return False

    async def _refresh_token(self, integration_id: int, refresh_token: str) -> bool:
        """Refresh the OAuth access token."""
        if not refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            token_url = self.TOKEN_URL.format(tenant=settings.tenant_id)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={
                        "client_id": settings.client_id,
                        "client_secret": settings.client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "Mail.Send Mail.ReadWrite Calendars.ReadWrite User.Read offline_access",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Token refresh failed: {response.text}")
                    return False

                tokens = response.json()

                # Update stored tokens
                from sqlalchemy import text
                new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
                new_refresh = tokens.get("refresh_token", refresh_token)

                self.db.execute(text("""
                    UPDATE user_integrations
                    SET access_token = :access_token,
                        refresh_token = :refresh_token,
                        expires_at = :expires_at,
                        updated_at = :updated_at
                    WHERE id = :id
                """), {
                    "id": integration_id,
                    "access_token": tokens["access_token"],
                    "refresh_token": new_refresh,
                    "expires_at": new_expires_at,
                    "updated_at": datetime.now(timezone.utc),
                })
                self.db.commit()

                self.access_token = tokens["access_token"]
                return True

        except SQLAlchemyError as e:
            logger.error(f"Token refresh error: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for Graph API calls."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_email(self, params: EmailParams) -> EmailResult:
        """
        Send an email via Microsoft Graph API.

        Args:
            params: Email parameters including recipients, subject, body

        Returns:
            EmailResult with success status and any error message
        """
        if not self._initialized:
            if not await self.initialize():
                return EmailResult(
                    success=False,
                    error="Not authenticated with Microsoft. Please reconnect your Outlook account."
                )

        try:
            message: Dict[str, Any] = {
                "subject": params.subject,
                "body": {
                    "contentType": "HTML" if params.body_type == "html" else "Text",
                    "content": params.body,
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}} for email in params.to
                ],
                "importance": params.importance,
            }

            if params.cc:
                message["ccRecipients"] = [
                    {"emailAddress": {"address": email}} for email in params.cc
                ]

            if params.bcc:
                message["bccRecipients"] = [
                    {"emailAddress": {"address": email}} for email in params.bcc
                ]

            payload = {
                "message": message,
                "saveToSentItems": params.save_to_sent,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.GRAPH_BASE_URL}/me/sendMail",
                    json=payload,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 202:  # Accepted
                    logger.info(f"Email sent successfully to {params.to}")
                    return EmailResult(success=True)
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    logger.error(f"Send email failed: {error_msg}")
                    return EmailResult(success=False, error=error_msg)

        except httpx.TimeoutException:
            return EmailResult(success=False, error="Request timed out")
        except Exception as e:
            logger.error(f"Send email error: {e}")
            return EmailResult(success=False, error=str(e))

    async def create_calendar_event(self, params: CalendarEventParams) -> CalendarResult:
        """
        Create a calendar event via Microsoft Graph API.

        Args:
            params: Event parameters including subject, time, attendees

        Returns:
            CalendarResult with event ID and web link
        """
        if not self._initialized:
            if not await self.initialize():
                return CalendarResult(
                    success=False,
                    error="Not authenticated with Microsoft. Please reconnect your Outlook account."
                )

        try:
            event: Dict[str, Any] = {
                "subject": params.subject,
                "start": {
                    "dateTime": params.start.isoformat(),
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": params.end.isoformat(),
                    "timeZone": "UTC",
                },
                "reminderMinutesBeforeStart": params.reminder_minutes,
            }

            if params.body:
                event["body"] = {
                    "contentType": "HTML",
                    "content": params.body,
                }

            if params.location:
                event["location"] = {"displayName": params.location}

            if params.attendees:
                event["attendees"] = [
                    {
                        "emailAddress": {"address": email},
                        "type": "required",
                    }
                    for email in params.attendees
                ]

            if params.is_online_meeting:
                event["isOnlineMeeting"] = True
                event["onlineMeetingProvider"] = "teamsForBusiness"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.GRAPH_BASE_URL}/me/calendar/events",
                    json=event,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 201:  # Created
                    data = response.json()
                    logger.info(f"Calendar event created: {data.get('id')}")

                    teams_link = None
                    if params.is_online_meeting and "onlineMeeting" in data:
                        teams_link = data["onlineMeeting"].get("joinUrl")

                    return CalendarResult(
                        success=True,
                        event_id=data.get("id"),
                        web_link=data.get("webLink"),
                        teams_link=teams_link,
                    )
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    logger.error(f"Create event failed: {error_msg}")
                    return CalendarResult(success=False, error=error_msg)

        except httpx.TimeoutException:
            return CalendarResult(success=False, error="Request timed out")
        except Exception as e:
            logger.error(f"Create calendar event error: {e}")
            return CalendarResult(success=False, error=str(e))

    async def get_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get user's busy time slots within a date range.

        Returns:
            List of busy periods with start/end times
        """
        if not self._initialized:
            if not await self.initialize():
                return []

        try:
            async with httpx.AsyncClient() as client:
                # Get user's email first
                me_response = await client.get(
                    f"{self.GRAPH_BASE_URL}/me",
                    headers=self._get_headers(),
                    timeout=15.0,
                )

                if me_response.status_code != 200:
                    return []

                me_data = me_response.json()
                user_email = me_data.get("mail") or me_data.get("userPrincipalName")

                if not user_email:
                    return []

                # Get schedule
                response = await client.post(
                    f"{self.GRAPH_BASE_URL}/me/calendar/getSchedule",
                    json={
                        "schedules": [user_email],
                        "startTime": {
                            "dateTime": start_time.isoformat(),
                            "timeZone": "UTC",
                        },
                        "endTime": {
                            "dateTime": end_time.isoformat(),
                            "timeZone": "UTC",
                        },
                        "availabilityViewInterval": interval_minutes,
                    },
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                busy_slots = []

                for schedule in data.get("value", []):
                    for item in schedule.get("scheduleItems", []):
                        start_str = item["start"]["dateTime"]
                        end_str = item["end"]["dateTime"]

                        # Parse datetime strings
                        if start_str.endswith("Z"):
                            start_str = start_str.replace("Z", "+00:00")
                        if end_str.endswith("Z"):
                            end_str = end_str.replace("Z", "+00:00")

                        busy_slots.append({
                            "start": datetime.fromisoformat(start_str),
                            "end": datetime.fromisoformat(end_str),
                            "status": item.get("status", "busy"),
                        })

                return busy_slots

        except Exception as e:
            logger.error(f"Get availability error: {e}")
            return []


# =============================================================================
# CONVENIENCE FUNCTIONS FOR LANGGRAPH TOOLS
# =============================================================================

async def send_email_via_graph(
    user_id: int,
    to: List[str],
    subject: str,
    body: str,
    db: Session,
    cc: Optional[List[str]] = None,
    importance: str = "normal",
) -> EmailResult:
    """
    Convenience function to send an email via Microsoft Graph.

    Use this in your LangGraph tools for quick email sending.

    Args:
        user_id: Database ID of the sending user
        to: List of recipient email addresses
        subject: Email subject
        body: Email body (HTML)
        db: SQLAlchemy session
        cc: Optional CC recipients
        importance: "low", "normal", or "high"

    Returns:
        EmailResult with success status
    """
    service = MicrosoftGraphUserService(user_id, db)
    return await service.send_email(EmailParams(
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        importance=importance,
    ))


async def create_event_via_graph(
    user_id: int,
    subject: str,
    start: datetime,
    end: datetime,
    db: Session,
    attendees: Optional[List[str]] = None,
    location: Optional[str] = None,
    add_teams_link: bool = False,
    body: Optional[str] = None,
) -> CalendarResult:
    """
    Convenience function to create a calendar event via Microsoft Graph.

    Use this in your LangGraph tools for quick event creation.

    Args:
        user_id: Database ID of the user
        subject: Event title
        start: Start datetime
        end: End datetime
        db: SQLAlchemy session
        attendees: Optional list of attendee emails
        location: Optional location string
        add_teams_link: Whether to create a Teams meeting
        body: Optional event description

    Returns:
        CalendarResult with event ID and links
    """
    service = MicrosoftGraphUserService(user_id, db)
    return await service.create_calendar_event(CalendarEventParams(
        subject=subject,
        start=start,
        end=end,
        attendees=attendees,
        location=location,
        is_online_meeting=add_teams_link,
        body=body,
    ))


async def get_user_availability(
    user_id: int,
    start_time: datetime,
    end_time: datetime,
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Get a user's busy calendar slots.

    Args:
        user_id: Database ID of the user
        start_time: Start of range to check
        end_time: End of range to check
        db: SQLAlchemy session

    Returns:
        List of busy slots with start/end datetimes
    """
    service = MicrosoftGraphUserService(user_id, db)
    return await service.get_availability(start_time, end_time)
