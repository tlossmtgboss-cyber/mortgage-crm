"""
Meeting Link Service - Auto-generates video meeting links for appointments.

Supports multiple providers:
- Zoom: Creates meetings via Zoom API (requires OAuth connection)
- Microsoft Teams: Creates meetings via MS Graph (requires OAuth connection)
- Perennia Meet: Self-hosted fallback meeting room links (always available)

The service is designed to be called during appointment creation. When meeting_mode
is VIDEO, a meeting link is automatically generated and attached to the appointment.

Provider detection order:
1. If a specific provider is requested, use that provider.
2. Auto-detect: Check if the assigned user has Zoom connected, fall back to Perennia Meet.
"""

import hashlib
import logging
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from routes.scheduler.constants import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)


class MeetingLinkResult:
    """Result of meeting link creation."""

    def __init__(
        self,
        success: bool,
        provider: str,
        join_url: str = "",
        host_url: str = "",
        meeting_id: str = "",
        dial_in: str = "",
        password: str = "",
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.provider = provider
        self.join_url = join_url
        self.host_url = host_url
        self.meeting_id = meeting_id
        self.dial_in = dial_in
        self.password = password
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "provider": self.provider,
            "join_url": self.join_url,
            "host_url": self.host_url,
            "meeting_id": self.meeting_id,
            "dial_in": self.dial_in,
            "password": self.password,
            "error": self.error,
            "metadata": self.metadata,
        }


class MeetingLinkService:
    """Auto-generates video meeting links for appointments."""

    @staticmethod
    async def create_meeting_link(
        db: Session,
        appointment,
        provider: str = "auto",
        user_id: Optional[int] = None,
    ) -> MeetingLinkResult:
        """Create meeting link based on configured provider.

        Args:
            db: Database session for querying user integrations.
            appointment: The Appointment ORM object (must have id, title,
                scheduled_start, scheduled_end, duration_minutes, assigned_user_id).
            provider: Provider to use. "auto" detects the best available provider.
                Options: "auto", "zoom", "teams", "perennia".
            user_id: Override user ID for provider detection. Defaults to
                appointment.assigned_user_id.

        Returns:
            MeetingLinkResult with the generated link details.
        """
        effective_user_id = user_id or getattr(appointment, "assigned_user_id", None)

        if provider == "auto":
            provider = MeetingLinkService._detect_provider(db, effective_user_id)

        if provider == "zoom":
            result = await MeetingLinkService._create_zoom_meeting(
                db, appointment, effective_user_id
            )
            if result.success:
                return result
            # Fall through to Perennia Meet on Zoom failure
            logger.warning(
                f"Zoom meeting creation failed for appointment {appointment.id}, "
                f"falling back to Perennia Meet: {result.error}"
            )

        if provider == "teams":
            result = await MeetingLinkService._create_teams_meeting(
                db, appointment, effective_user_id
            )
            if result.success:
                return result
            logger.warning(
                f"Teams meeting creation failed for appointment {appointment.id}, "
                f"falling back to Perennia Meet: {result.error}"
            )

        # Default fallback: Perennia Meet
        return MeetingLinkService._generate_perennia_meet_link(appointment)

    @staticmethod
    def _detect_provider(db: Session, user_id: Optional[int]) -> str:
        """Detect the best available meeting provider for a user.

        Checks user_integrations table for connected Zoom or MS Graph (Teams).
        Falls back to "perennia" if no external provider is connected.
        """
        if not user_id:
            return "perennia"

        try:
            result = db.execute(
                text("""
                    SELECT provider, expires_at
                    FROM user_integrations
                    WHERE user_id = :user_id
                      AND provider IN ('zoom', 'microsoft')
                    ORDER BY
                        CASE provider WHEN 'zoom' THEN 1 WHEN 'microsoft' THEN 2 END
                """),
                {"user_id": user_id},
            )
            rows = result.fetchall()

            for row in rows:
                provider_name = row[0]
                expires_at = row[1]

                # Skip expired tokens (they may still be refreshable, but
                # prefer a non-expired option when available)
                if expires_at and isinstance(expires_at, datetime):
                    if expires_at < datetime.now(timezone.utc):
                        continue

                if provider_name == "zoom":
                    return "zoom"
                if provider_name == "microsoft":
                    return "teams"

            # Check even expired tokens as a second pass (refresh may work)
            for row in rows:
                provider_name = row[0]
                if provider_name == "zoom":
                    return "zoom"
                if provider_name == "microsoft":
                    return "teams"

        except Exception as e:
            logger.warning(f"Error detecting meeting provider for user {user_id}: {e}")

        return "perennia"

    @staticmethod
    async def _create_zoom_meeting(
        db: Session,
        appointment,
        user_id: Optional[int],
    ) -> MeetingLinkResult:
        """Create Zoom meeting via API.

        Retrieves the user's Zoom OAuth token from user_integrations,
        refreshes if expired, and creates a scheduled meeting.
        """
        if not user_id:
            return MeetingLinkResult(
                success=False, provider="zoom", error="No user ID for Zoom meeting"
            )

        try:
            from integrations.zoom_service import zoom_client

            if not zoom_client.enabled:
                return MeetingLinkResult(
                    success=False,
                    provider="zoom",
                    error="Zoom integration not configured (missing credentials)",
                )

            # Get the user's Zoom token
            result = db.execute(
                text("""
                    SELECT access_token, refresh_token, expires_at
                    FROM user_integrations
                    WHERE user_id = :user_id AND provider = 'zoom'
                """),
                {"user_id": user_id},
            )
            row = result.fetchone()

            if not row:
                return MeetingLinkResult(
                    success=False,
                    provider="zoom",
                    error="User has no Zoom connection",
                )

            access_token = row[0]
            refresh_token = row[1]
            expires_at = row[2]

            # Refresh token if expired
            if expires_at and isinstance(expires_at, datetime):
                if expires_at < datetime.now(timezone.utc) and refresh_token:
                    token_data = await zoom_client.async_refresh_access_token(
                        refresh_token
                    )
                    if token_data:
                        access_token = token_data["access_token"]
                        db.execute(
                            text("""
                                UPDATE user_integrations
                                SET access_token = :access_token,
                                    refresh_token = :refresh_token,
                                    expires_at = :expires_at,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE user_id = :user_id AND provider = 'zoom'
                            """),
                            {
                                "user_id": user_id,
                                "access_token": token_data.get("access_token"),
                                "refresh_token": token_data.get(
                                    "refresh_token", refresh_token
                                ),
                                "expires_at": token_data.get("expires_at"),
                            },
                        )
                        db.flush()
                    else:
                        return MeetingLinkResult(
                            success=False,
                            provider="zoom",
                            error="Failed to refresh expired Zoom token",
                        )

            # Create the Zoom meeting
            topic = getattr(appointment, "title", "Perennia AI Meeting") or "Meeting"
            start_time = getattr(appointment, "scheduled_start", datetime.now(timezone.utc))
            duration = getattr(appointment, "duration_minutes", 30) or 30
            tz = getattr(appointment, "timezone", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE

            meeting_data = await zoom_client.async_create_meeting(
                access_token=access_token,
                topic=topic,
                start_time=start_time,
                duration=duration,
                timezone=tz,
                agenda=getattr(appointment, "description", None),
            )

            if not meeting_data:
                return MeetingLinkResult(
                    success=False,
                    provider="zoom",
                    error="Zoom API returned no data",
                )

            join_url = meeting_data.get("join_url", "")
            start_url = meeting_data.get("start_url", "")
            meeting_id = str(meeting_data.get("id", ""))
            password = meeting_data.get("password", "")

            # Extract dial-in info if available
            dial_in = ""
            dial_numbers = meeting_data.get("settings", {}).get(
                "global_dial_in_numbers", []
            )
            if dial_numbers:
                us_numbers = [
                    n for n in dial_numbers if n.get("country") == "US"
                ]
                if us_numbers:
                    dial_in = us_numbers[0].get("number", "")
                elif dial_numbers:
                    dial_in = dial_numbers[0].get("number", "")

            return MeetingLinkResult(
                success=True,
                provider="zoom",
                join_url=join_url,
                host_url=start_url,
                meeting_id=meeting_id,
                password=password,
                dial_in=dial_in,
                metadata={
                    "zoom_meeting_id": meeting_id,
                    "zoom_host_id": meeting_data.get("host_id"),
                    "zoom_uuid": meeting_data.get("uuid"),
                },
            )

        except ImportError:
            return MeetingLinkResult(
                success=False,
                provider="zoom",
                error="Zoom service module not available",
            )
        except Exception as e:
            logger.exception(f"Error creating Zoom meeting: {e}")
            return MeetingLinkResult(
                success=False, provider="zoom", error=str(e)
            )

    @staticmethod
    async def _create_teams_meeting(
        db: Session,
        appointment,
        user_id: Optional[int],
    ) -> MeetingLinkResult:
        """Create Microsoft Teams meeting via MS Graph API.

        Uses the existing create_event_via_graph helper which can generate
        Teams meeting links.
        """
        if not user_id:
            return MeetingLinkResult(
                success=False, provider="teams", error="No user ID for Teams meeting"
            )

        try:
            from services.microsoft_graph import create_event_via_graph, CalendarResult

            topic = getattr(appointment, "title", "Perennia AI Meeting") or "Meeting"
            start_time = getattr(appointment, "scheduled_start", datetime.now(timezone.utc))
            end_time = getattr(
                appointment,
                "scheduled_end",
                start_time + timedelta(minutes=30),
            )
            attendee_email = getattr(appointment, "attendee_email", None)

            result: CalendarResult = await create_event_via_graph(
                user_id=user_id,
                subject=topic,
                start=start_time,
                end=end_time,
                db=db,
                attendees=[attendee_email] if attendee_email else None,
                add_teams_link=True,
                body=getattr(appointment, "description", "") or "",
            )

            if result.success and result.join_url:
                return MeetingLinkResult(
                    success=True,
                    provider="teams",
                    join_url=result.join_url,
                    meeting_id=result.event_id or "",
                    metadata={
                        "outlook_event_id": result.event_id,
                    },
                )

            return MeetingLinkResult(
                success=False,
                provider="teams",
                error=result.error or "Teams link not returned",
            )

        except ImportError:
            return MeetingLinkResult(
                success=False,
                provider="teams",
                error="Microsoft Graph service not available",
            )
        except Exception as e:
            logger.exception(f"Error creating Teams meeting: {e}")
            return MeetingLinkResult(
                success=False, provider="teams", error=str(e)
            )

    @staticmethod
    def _generate_perennia_meet_link(appointment) -> MeetingLinkResult:
        """Generate a Perennia-hosted meeting room link.

        Creates a deterministic but unpredictable room ID based on the
        appointment ID and scheduled start time. The room link points to
        the frontend /meet/{room_id} route which renders a lightweight
        meeting lobby page.
        """
        appt_id = getattr(appointment, "id", "unknown")
        start_str = str(getattr(appointment, "scheduled_start", ""))

        # Generate a short, URL-friendly room ID
        # Combine appointment ID with start time and a secret salt for uniqueness
        salt = os.getenv("SECRET_KEY", "")
        if not salt:
            logger.critical(
                "SECRET_KEY not set — cannot generate deterministic meeting room IDs securely"
            )
            raise RuntimeError(
                "SECRET_KEY environment variable must be set for meeting link generation"
            )
        hash_input = f"{appt_id}:{start_str}:{salt}"
        room_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:12]

        # Format as a readable room code: XXXX-XXXX-XXXX
        room_id = f"{room_hash[:4]}-{room_hash[4:8]}-{room_hash[8:12]}"

        base_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
        join_url = f"{base_url}/meet/{room_id}"

        return MeetingLinkResult(
            success=True,
            provider="perennia",
            join_url=join_url,
            meeting_id=room_id,
            metadata={
                "room_id": room_id,
                "appointment_id": appt_id,
            },
        )

    @staticmethod
    async def create_meeting_link_for_new_appointment(
        db: Session,
        appointment,
        provider: str = "auto",
    ) -> Optional[str]:
        """Convenience method for appointment creation flows.

        Creates a meeting link and updates the appointment's video_link field.
        Returns the join URL or None if creation failed.

        This is the primary integration point: call this after creating
        the appointment object but before committing.
        """
        result = await MeetingLinkService.create_meeting_link(
            db=db, appointment=appointment, provider=provider
        )

        if result.success:
            appointment.video_link = result.join_url

            # Store dial-in info if available
            if result.dial_in:
                existing_dial_in = getattr(appointment, "dial_in_info", None) or ""
                dial_info_parts = []
                if existing_dial_in:
                    dial_info_parts.append(existing_dial_in)
                dial_info_parts.append(
                    f"Provider: {result.provider}\n"
                    f"Dial-in: {result.dial_in}"
                )
                if result.password:
                    dial_info_parts.append(f"Meeting Password: {result.password}")
                appointment.dial_in_info = "\n".join(dial_info_parts)

            logger.info(
                f"Meeting link created for appointment {appointment.id}: "
                f"provider={result.provider}, url={result.join_url}"
            )
            return result.join_url

        logger.warning(
            f"Failed to create meeting link for appointment {appointment.id}: "
            f"{result.error}"
        )
        return None

    @staticmethod
    def get_meeting_info_for_room(room_id: str, db: Session) -> Optional[Dict[str, Any]]:
        """Look up appointment info for a Perennia Meet room ID.

        Searches for appointments whose video_link contains the given room_id.
        Returns appointment details needed for the meeting room page.
        """
        try:
            # Search for appointment with this room ID in the video_link
            result = db.execute(
                text("""
                    SELECT
                        sa.id,
                        sa.title,
                        sa.description,
                        sa.scheduled_start,
                        sa.scheduled_end,
                        sa.duration_minutes,
                        sa.meeting_mode,
                        sa.status,
                        sa.attendee_name,
                        sa.attendee_email,
                        sa.video_link,
                        sa.assigned_user_id,
                        sa.organization_id,
                        CONCAT(u.first_name, ' ', u.last_name) as host_name
                    FROM scheduler_appointments sa
                    LEFT JOIN users u ON u.id = sa.assigned_user_id
                    WHERE sa.video_link LIKE :pattern
                    ORDER BY sa.scheduled_start DESC
                    LIMIT 1
                """),
                {"pattern": f"%{room_id}%"},
            )
            row = result.fetchone()

            if not row:
                return None

            return {
                "appointment_id": row[0],
                "title": row[1],
                "description": row[2],
                "scheduled_start": row[3].isoformat() if row[3] else None,
                "scheduled_end": row[4].isoformat() if row[4] else None,
                "duration_minutes": row[5],
                "meeting_mode": row[6],
                "status": row[7],
                "attendee_name": row[8],
                "host_name": row[13],
                "video_link": row[10],
                "room_id": room_id,
            }

        except Exception as e:
            logger.error(f"Error looking up meeting room {room_id}: {e}")
            return None
