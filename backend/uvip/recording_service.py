"""
UVIP Recording Service - Twilio Integration
Handles conference calls with automatic recording for video meetings
"""
import os
import logging
import asyncio
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial, Conference
from sqlalchemy.orm import Session

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)


class TwilioRecordingService:
    """
    Twilio-based recording service for UVIP meetings.
    Uses Twilio Conferences for multi-party recorded calls.
    """

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER", "")

        # Production domain for callbacks
        self.domain = os.getenv('PRODUCTION_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')

        # Initialize Twilio client
        self.client = None
        self.enabled = False

        if self.account_sid and self.auth_token:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                self.enabled = True
                logger.info("UVIP Recording Service initialized with Twilio")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
        else:
            logger.warning("Twilio credentials not configured for UVIP Recording")

    async def start_recorded_call(
        self,
        meeting_room_id: str,
        participant_phone: str,
        from_phone: Optional[str] = None,
        participant_name: str = "Participant"
    ) -> Optional[str]:
        """
        Start a Twilio call with recording and connect to meeting conference.

        Args:
            meeting_room_id: The unique meeting room code
            participant_phone: Phone number to call
            from_phone: Caller ID (defaults to system number)
            participant_name: Display name for the participant

        Returns:
            Call SID if successful, None otherwise
        """
        if not self.enabled:
            logger.error("Twilio not enabled")
            return None

        try:
            callback_url = f"https://{self.domain}/api/v1/meetings/twilio/connect/{meeting_room_id}"
            status_callback = f"https://{self.domain}/api/v1/meetings/twilio/call-status/{meeting_room_id}"

            call = self.client.calls.create(
                url=callback_url,
                to=participant_phone,
                from_=from_phone or self.from_number,
                record=True,  # Record the call
                recording_status_callback=f"https://{self.domain}/api/v1/meetings/twilio/recording-callback/{meeting_room_id}",
                recording_status_callback_event=["completed"],
                status_callback=status_callback,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                machine_detection="Enable",  # Detect voicemail
                machine_detection_timeout=5
            )

            logger.info(f"Started call to {mask_phone(participant_phone)} for meeting {meeting_room_id}, SID: {call.sid}")
            return call.sid

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
        Generate TwiML for connecting to a recorded conference.

        Args:
            meeting_room_id: Unique meeting room code
            participant_name: Label for this participant
            is_host: Whether this is the host (starts conference)

        Returns:
            TwiML string for conference connection
        """
        response = VoiceResponse()

        # Brief welcome message
        response.say(
            "Connecting you to the meeting. Please wait.",
            voice='Polly.Joanna'
        )

        # Create dial with conference
        dial = Dial()

        # Conference settings
        conference = dial.conference(
            meeting_room_id,
            start_conference_on_enter=is_host,  # Host starts it, others wait
            end_conference_on_exit=is_host,  # Host ending = conference ends
            record='record-from-start',  # Record entire conference
            recording_status_callback=f"https://{self.domain}/api/v1/meetings/twilio/recording-callback/{meeting_room_id}",
            recording_status_callback_event="completed",
            trim='trim-silence',
            participant_label=participant_name,
            beep=True,  # Beep when someone joins
            wait_url="http://twimlets.com/holdmusic?Bucket=com.twilio.music.classical",
            max_participants=10
        )

        response.append(dial)

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
        Generate TwiML for a participant joining an existing conference.
        """
        response = VoiceResponse()

        response.say(
            "Joining the meeting now.",
            voice='Polly.Joanna'
        )

        dial = Dial()
        dial.conference(
            meeting_room_id,
            start_conference_on_enter=False,  # Don't auto-start
            end_conference_on_exit=False,  # Participant leaving doesn't end it
            record='do-not-record',  # Main conference already recording
            participant_label=participant_name,
            beep=True
        )

        response.append(dial)

        return str(response)

    async def get_recording_url(self, recording_sid: str) -> Optional[str]:
        """
        Get the download URL for a completed recording.
        """
        if not self.enabled:
            return None

        try:
            recording = self.client.recordings(recording_sid).fetch()
            # Construct download URL with authentication
            recording_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Recordings/{recording_sid}.mp3"
            return recording_url
        except Exception as e:
            logger.error(f"Failed to get recording URL: {e}")
            return None

    async def download_recording(self, recording_sid: str) -> Optional[bytes]:
        """
        Download recording content from Twilio.
        """
        if not self.enabled:
            return None

        try:
            # Get recording URL
            recording_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Recordings/{recording_sid}.mp3"

            # Download with authentication
            response = requests.get(
                recording_url,
                auth=(self.account_sid, self.auth_token),
                stream=True
            )

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
        """
        if not self.enabled:
            return []

        try:
            # Find the conference by friendly name (meeting_room_id)
            conferences = self.client.conferences.list(
                friendly_name=meeting_room_id,
                status="in-progress",
                limit=1
            )

            if not conferences:
                return []

            conference = conferences[0]
            participants = conference.participants.list()

            return [
                {
                    "call_sid": p.call_sid,
                    "label": p.label,
                    "muted": p.muted,
                    "hold": p.hold,
                    "status": p.status
                }
                for p in participants
            ]

        except Exception as e:
            logger.error(f"Failed to get conference participants: {e}")
            return []

    async def mute_participant(self, meeting_room_id: str, call_sid: str, muted: bool = True) -> bool:
        """
        Mute or unmute a participant in the conference.
        """
        if not self.enabled:
            return False

        try:
            conferences = self.client.conferences.list(
                friendly_name=meeting_room_id,
                status="in-progress",
                limit=1
            )

            if not conferences:
                return False

            conference = conferences[0]
            participant = conference.participants(call_sid).update(muted=muted)

            return True

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
            conferences = self.client.conferences.list(
                friendly_name=meeting_room_id,
                status="in-progress",
                limit=1
            )

            if not conferences:
                return True  # Already ended

            conference = conferences[0]

            # Update conference status to completed
            self.client.conferences(conference.sid).update(status="completed")

            logger.info(f"Ended conference {meeting_room_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to end conference: {e}")
            return False

    async def get_recording_metadata(self, recording_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a recording.
        """
        if not self.enabled:
            return None

        try:
            recording = self.client.recordings(recording_sid).fetch()

            return {
                "sid": recording.sid,
                "duration": recording.duration,
                "channels": recording.channels,
                "source": recording.source,
                "status": recording.status,
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
                "price": recording.price,
                "error_code": recording.error_code
            }

        except Exception as e:
            logger.error(f"Failed to get recording metadata: {e}")
            return None


# Singleton instance
_recording_service: Optional[TwilioRecordingService] = None


def get_recording_service() -> TwilioRecordingService:
    """Get or create the recording service singleton."""
    global _recording_service
    if _recording_service is None:
        _recording_service = TwilioRecordingService()
    return _recording_service
