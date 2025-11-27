"""
Telephony Provider Interface and Twilio Implementation
Abstracts telephony operations for easy provider switching
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone

from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)


@dataclass
class CallResult:
    """Result of initiating a call"""
    success: bool
    call_sid: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class CallStatus:
    """Status of an active or completed call"""
    call_sid: str
    status: str  # queued, ringing, in-progress, completed, busy, no-answer, canceled, failed
    duration: Optional[int] = None
    answered_by: Optional[str] = None
    end_time: Optional[datetime] = None


class TelephonyProvider(ABC):
    """Abstract base class for telephony providers"""

    @abstractmethod
    def place_call(
        self,
        to_number: str,
        from_number: str,
        callback_url: str,
        status_callback_url: str,
        timeout: int = 30
    ) -> CallResult:
        """
        Place an outbound call

        Args:
            to_number: The phone number to call (E.164 format)
            from_number: The caller ID to display (must be verified)
            callback_url: URL for TwiML instructions when call is answered
            status_callback_url: URL for call status updates
            timeout: Seconds to wait for answer before giving up

        Returns:
            CallResult with success status and call SID or error
        """
        pass

    @abstractmethod
    def get_call_status(self, call_sid: str) -> Optional[CallStatus]:
        """Get the current status of a call"""
        pass

    @abstractmethod
    def hangup_call(self, call_sid: str) -> bool:
        """Terminate an active call"""
        pass

    @abstractmethod
    def verify_caller_id(self, phone_number: str, friendly_name: str) -> Dict[str, Any]:
        """
        Start verification process for a caller ID

        Returns:
            Dict with verification_sid and status
        """
        pass

    @abstractmethod
    def check_caller_id_verification(self, verification_sid: str) -> Dict[str, Any]:
        """Check status of caller ID verification"""
        pass


class TwilioProvider(TelephonyProvider):
    """Twilio implementation of TelephonyProvider"""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.client = None

        if self.account_sid and self.auth_token:
            try:
                self.client = TwilioClient(self.account_sid, self.auth_token)
                logger.info("Twilio client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
        else:
            logger.warning("Twilio credentials not configured - telephony features disabled")

    def _ensure_client(self):
        """Ensure Twilio client is available"""
        if not self.client:
            raise RuntimeError("Twilio client not initialized. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")

    def place_call(
        self,
        to_number: str,
        from_number: str,
        callback_url: str,
        status_callback_url: str,
        timeout: int = 30
    ) -> CallResult:
        """Place an outbound call via Twilio"""
        self._ensure_client()

        try:
            call = self.client.calls.create(
                to=to_number,
                from_=from_number,
                url=callback_url,
                status_callback=status_callback_url,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                timeout=timeout
            )

            logger.info(f"Call initiated: {call.sid} to {to_number}")
            return CallResult(success=True, call_sid=call.sid)

        except TwilioRestException as e:
            logger.error(f"Twilio error placing call to {to_number}: {e.code} - {e.msg}")
            return CallResult(
                success=False,
                error_message=e.msg,
                error_code=str(e.code)
            )
        except Exception as e:
            logger.error(f"Unexpected error placing call to {to_number}: {e}")
            return CallResult(
                success=False,
                error_message=str(e),
                error_code="UNKNOWN"
            )

    def get_call_status(self, call_sid: str) -> Optional[CallStatus]:
        """Get the current status of a call"""
        self._ensure_client()

        try:
            call = self.client.calls(call_sid).fetch()
            return CallStatus(
                call_sid=call.sid,
                status=call.status,
                duration=int(call.duration) if call.duration else None,
                answered_by=call.answered_by,
                end_time=call.end_time
            )
        except TwilioRestException as e:
            logger.error(f"Error fetching call status for {call_sid}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching call status: {e}")
            return None

    def hangup_call(self, call_sid: str) -> bool:
        """Terminate an active call"""
        self._ensure_client()

        try:
            call = self.client.calls(call_sid).update(status='completed')
            logger.info(f"Call {call_sid} terminated")
            return True
        except TwilioRestException as e:
            logger.error(f"Error terminating call {call_sid}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error terminating call: {e}")
            return False

    def verify_caller_id(self, phone_number: str, friendly_name: str) -> Dict[str, Any]:
        """Start verification process for a caller ID"""
        self._ensure_client()

        try:
            validation_request = self.client.validation_requests.create(
                phone_number=phone_number,
                friendly_name=friendly_name
            )
            return {
                "success": True,
                "validation_code": validation_request.validation_code,
                "call_sid": validation_request.call_sid,
                "phone_number": validation_request.phone_number,
                "friendly_name": validation_request.friendly_name
            }
        except TwilioRestException as e:
            logger.error(f"Error starting caller ID verification: {e}")
            return {
                "success": False,
                "error": e.msg,
                "error_code": str(e.code)
            }

    def check_caller_id_verification(self, phone_number: str) -> Dict[str, Any]:
        """Check if a caller ID is verified"""
        self._ensure_client()

        try:
            # List outgoing caller IDs matching this number
            caller_ids = self.client.outgoing_caller_ids.list(phone_number=phone_number)

            if caller_ids:
                caller_id = caller_ids[0]
                return {
                    "verified": True,
                    "sid": caller_id.sid,
                    "phone_number": caller_id.phone_number,
                    "friendly_name": caller_id.friendly_name
                }
            else:
                return {
                    "verified": False,
                    "phone_number": phone_number
                }
        except TwilioRestException as e:
            logger.error(f"Error checking caller ID verification: {e}")
            return {
                "verified": False,
                "error": e.msg
            }

    def list_verified_caller_ids(self) -> list:
        """List all verified caller IDs for the account"""
        self._ensure_client()

        try:
            caller_ids = self.client.outgoing_caller_ids.list()
            return [
                {
                    "sid": cid.sid,
                    "phone_number": cid.phone_number,
                    "friendly_name": cid.friendly_name
                }
                for cid in caller_ids
            ]
        except TwilioRestException as e:
            logger.error(f"Error listing caller IDs: {e}")
            return []


# Singleton instance
_provider_instance: Optional[TwilioProvider] = None


def get_telephony_provider() -> TwilioProvider:
    """Get the singleton telephony provider instance"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = TwilioProvider()
    return _provider_instance
