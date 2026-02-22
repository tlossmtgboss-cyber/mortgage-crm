"""
UVIP Recording Service - Telnyx Integration
Handles conference calls with automatic recording for video meetings.

Uses Telnyx. TeXML for voice responses and the
Telnyx telephony provider for call placement and conference management.
"""
import os
import logging
import asyncio
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from telephony.provider import get_telephony_provider, TelephonyError
from telephony.providers.telnyx.texml import TeXMLResponse
from sqlalchemy.orm import Session

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)


class TelnyxRecordingService:
    """
    Telnyx-based recording service for UVIP meetings.
    Uses Telnyx TeXML Conferences for multi-party recorded calls.
    """

    def __init__(self):
        self.from_number = os.getenv("TELNYX_PHONE_NUMBER", "")

        # Production domain for callbacks
        self.domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')

        # Initialize Telnyx provider
        self.provider = None
        self.enabled = False

        try:
            self.provider = get_telephony_provider()
            self.enabled = True
            logger.info("UVIP Recording Service initialized with Telnyx")
        except TelephonyError as e:
            logger.warning(f"Telnyx not configured for UVIP Recording: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Telnyx provider: {e}")

    async def start_recorded_call(
        self,
        meeting_room_id: str,
        participant_phone: str,
        from_phone: Optional[str] = None,
        participant_name: str = "Participant"
    ) -> Optional[str]:
        """
        Start a Telnyx call with recording and connect to meeting conference.

        Args:
            meeting_room_id: The unique meeting room code
            participant_phone: Phone number to call
            from_phone: Caller ID (defaults to system number)
            participant_name: Display name for the participant

        Returns:
            Call SID (call_control_id) if successful, None otherwise
        """
        if not self.enabled:
            logger.error("Telnyx not enabled")
            return None

        try:
            callback_url = f"https://{self.domain}/api/v1/meetings/telnyx/connect/{meeting_room_id}"
            status_callback = f"https://{self.domain}/api/v1/meetings/telnyx/call-status/{meeting_room_id}"
            recording_callback = f"https://{self.domain}/api/v1/meetings/telnyx/recording-callback/{meeting_room_id}"

            result = self.provider.place_call(
                to=participant_phone,
                from_=from_phone or self.from_number,
                url=callback_url,
                status_callback=status_callback,
                record=True,
                recording_status_callback=recording_callback,
                machine_detection="Enable",
                machine_detection_timeout=5
            )

            if result.success:
                logger.info(f"Started call to {mask_phone(participant_phone)} for meeting {meeting_room_id}, SID: {result.call_sid}")
                return result.call_sid
            else:
                logger.error(f"Failed to start recorded call: {result.error_message}")
                return None

        except Exception as e:
            logger.error(f"Failed to start recorded call: {e}")
            return None

    def get_conference_twiml(
        self,
        meeting_room_id: str,
        participant_name: str = "Participant",
        is_host: bool = False
    ) -> str:
        """
        Generate TeXML for connecting to a recorded conference.

        Args:
            meeting_room_id: Unique meeting room code
            participant_name: Label for this participant
            is_host: Whether this is the host (starts conference)

        Returns:
            TeXML string for conference connection
        """
        response = TeXMLResponse()

        # Brief welcome message
        response.say(
            "Connecting you to the meeting. Please wait.",
            voice='Polly.Joanna'
        )

        # Create conference via TeXML (TeXMLResponse.conference wraps in Dial automatically)
        response.conference(
            meeting_room_id,
            start_conference_on_enter=is_host,   # Host starts it, others wait
            end_conference_on_exit=is_host,       # Host ending = conference ends
            record='record-from-start',           # Record entire conference
            status_callback=f"https://{self.domain}/api/v1/meetings/telnyx/recording-callback/{meeting_room_id}",
            status_callback_event="completed",
            beep="true",
            max_participants=10
        )

        # Fallback if conference ends
        response.say(
            "The meeting has ended. Thank you for joining.",
            voice='Polly.Joanna'
        )

        return str(response)

    def get_join_conference_twiml(
        self,
        meeting_room_id: str,
        participant_name: str = "Participant"
    ) -> str:
        """
        Generate TeXML for a participant joining an existing conference.
        """
        response = TeXMLResponse()

        response.say(
            "Joining the meeting now.",
            voice='Polly.Joanna'
        )

        response.conference(
            meeting_room_id,
            start_conference_on_enter=False,  # Don't auto-start
            end_conference_on_exit=False,     # Participant leaving doesn't end it
            record='do-not-record',           # Main conference already recording
            beep="true"
        )

        return str(response)

    async def get_recording_url(self, recording_sid: str) -> Optional[str]:
        """
        Get the download URL for a completed recording.

        Note: Telnyx recording URLs are delivered via webhooks. This method
        returns a constructed URL; in practice, recording URLs should be
        stored in the DB when the webhook fires.
        """
        if not self.enabled:
            return None

        try:
            # Telnyx recordings are accessed via their API
            api_key = os.getenv("TELNYX_API_KEY", "")
            recording_url = f"https://api.telnyx.com/v2/recordings/{recording_sid}"
            logger.info(f"Recording URL requested for {recording_sid}")
            return recording_url
        except Exception as e:
            logger.error(f"Failed to get recording URL: {e}")
            return None

    async def download_recording(self, recording_sid: str) -> Optional[bytes]:
        """
        Download recording content from Telnyx.
        """
        if not self.enabled:
            return None

        try:
            api_key = os.getenv("TELNYX_API_KEY", "")
            # Fetch recording metadata to get download URL
            metadata_url = f"https://api.telnyx.com/v2/recordings/{recording_sid}"
            headers = {"Authorization": f"Bearer {api_key}"}

            meta_response = requests.get(metadata_url, headers=headers, timeout=10)
            if meta_response.status_code != 200:
                logger.error(f"Failed to fetch recording metadata: {meta_response.status_code}")
                return None

            meta = meta_response.json()
            download_url = meta.get("data", {}).get("download_urls", {}).get("mp3")
            if not download_url:
                download_url = meta.get("data", {}).get("download_urls", {}).get("wav")

            if not download_url:
                logger.error(f"No download URL found for recording {recording_sid}")
                return None

            # Download the recording
            response = requests.get(download_url, headers=headers, stream=True, timeout=30)

            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Failed to download recording: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Failed to download recording: {e}")
            return None

    async def get_conference_participants(self, meeting_room_id: str) -> list:
        """
        Get list of current participants in a conference.

        Note: Telnyx conference participant listing uses the Telnyx Conference API.
        Conference management is typically handled via webhooks and Call Control.
        """
        if not self.enabled:
            return []

        try:
            api_key = os.getenv("TELNYX_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"}

            # List conferences and find matching one
            conf_url = f"https://api.telnyx.com/v2/conferences?filter[name]={meeting_room_id}"
            resp = requests.get(conf_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return []

            conferences = resp.json().get("data", [])
            if not conferences:
                return []

            conf_id = conferences[0].get("id")
            # Get participants
            part_url = f"https://api.telnyx.com/v2/conferences/{conf_id}/participants"
            part_resp = requests.get(part_url, headers=headers, timeout=10)
            if part_resp.status_code != 200:
                return []

            participants = part_resp.json().get("data", [])
            return [
                {
                    "call_sid": p.get("call_control_id", ""),
                    "label": p.get("whisper_call_control_id", ""),
                    "muted": p.get("muted", False),
                    "hold": p.get("on_hold", False),
                    "status": p.get("status", "unknown")
                }
                for p in participants
            ]

        except Exception as e:
            logger.error(f"Failed to get conference participants: {e}")
            return []

    async def mute_participant(self, meeting_room_id: str, call_sid: str, muted: bool = True) -> bool:
        """
        Mute or unmute a participant in the conference.

        Uses Telnyx Call Control to mute/unmute via the call_control_id.
        """
        if not self.enabled:
            return False

        try:
            api_key = os.getenv("TELNYX_API_KEY", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            if muted:
                url = f"https://api.telnyx.com/v2/calls/{call_sid}/actions/mute"
            else:
                url = f"https://api.telnyx.com/v2/calls/{call_sid}/actions/unmute"

            resp = requests.post(url, headers=headers, json={}, timeout=10)
            if resp.status_code in (200, 202):
                return True

            logger.error(f"Failed to {'mute' if muted else 'unmute'} participant: {resp.status_code}")
            return False

        except Exception as e:
            logger.error(f"Failed to mute participant: {e}")
            return False

    async def end_conference(self, meeting_room_id: str) -> bool:
        """
        End an active conference and all participant calls.
        """
        if not self.enabled:
            return False

        try:
            api_key = os.getenv("TELNYX_API_KEY", "")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Find the conference
            conf_url = f"https://api.telnyx.com/v2/conferences?filter[name]={meeting_room_id}"
            resp = requests.get(conf_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return True  # Assume already ended

            conferences = resp.json().get("data", [])
            if not conferences:
                return True  # Already ended

            conf_id = conferences[0].get("id")

            # End the conference
            end_url = f"https://api.telnyx.com/v2/conferences/{conf_id}/actions/leave"
            end_resp = requests.post(end_url, headers=headers, json={"call_control_ids": ["all"]}, timeout=10)

            logger.info(f"Ended conference {meeting_room_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to end conference: {e}")
            return False

    async def get_recording_metadata(self, recording_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a recording from Telnyx.
        """
        if not self.enabled:
            return None

        try:
            api_key = os.getenv("TELNYX_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"}

            url = f"https://api.telnyx.com/v2/recordings/{recording_sid}"
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code != 200:
                logger.error(f"Failed to get recording metadata: {resp.status_code}")
                return None

            data = resp.json().get("data", {})

            return {
                "sid": data.get("id", recording_sid),
                "duration": data.get("duration_millis", 0) // 1000 if data.get("duration_millis") else None,
                "channels": data.get("channels", 1),
                "source": "telnyx",
                "status": data.get("status", "unknown"),
                "start_time": data.get("created_at"),
                "price": None,  # Telnyx pricing is separate
                "error_code": None
            }

        except Exception as e:
            logger.error(f"Failed to get recording metadata: {e}")
            return None


# Keep backward-compatible alias
TwilioRecordingService = TelnyxRecordingService

# Singleton instance
_recording_service: Optional[TelnyxRecordingService] = None


def get_recording_service() -> TelnyxRecordingService:
    """Get or create the recording service singleton."""
    global _recording_service
    if _recording_service is None:
        _recording_service = TelnyxRecordingService()
    return _recording_service
