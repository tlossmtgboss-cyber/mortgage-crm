"""
Telephony Provider Abstraction and Twilio Implementation

Provides a clean abstraction layer for telephony operations,
allowing easy provider switching in the future.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging
import os

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Lazy import Twilio to allow app to start without credentials
_twilio_client = None
_telnyx_client = None


def _get_twilio_client():
    """Lazy initialization of Twilio client"""
    global _twilio_client
    if _twilio_client is None:
        from twilio.rest import Client
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        if account_sid and auth_token:
            _twilio_client = Client(account_sid, auth_token)
            logger.info("Twilio client initialized")
        else:
            logger.warning("Twilio credentials not configured - telephony features disabled")
    return _twilio_client


def _get_telnyx_client():
    """Lazy initialization of Telnyx client"""
    global _telnyx_client
    if _telnyx_client is None:
        try:
            from telnyx import Telnyx
            api_key = os.getenv('TELNYX_API_KEY')
            if api_key:
                _telnyx_client = Telnyx(api_key=api_key)
                logger.info("Telnyx client initialized")
            else:
                logger.warning("Telnyx API key not configured - telephony features disabled")
        except ImportError:
            logger.warning("Telnyx SDK not installed - run: pip install telnyx")
    return _telnyx_client


class TelephonyError(Exception):
    """Custom exception for telephony operations"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


@dataclass
class CallResult:
    """Result of initiating a call"""
    success: bool
    call_sid: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class CallStatus:
    """Status of an active or completed call"""
    call_sid: str
    status: str
    duration: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    answered_by: Optional[str] = None


class TelephonyProvider(ABC):
    """Abstract base class for telephony providers"""

    @abstractmethod
    def place_call(
        self,
        to: str,
        from_: str,
        url: str,
        status_callback: str,
        timeout: int = 30
    ) -> CallResult:
        """
        Place an outbound call

        Args:
            to: The phone number to call (E.164 format)
            from_: The caller ID to display (must be verified)
            url: URL for TwiML instructions when call is answered
            status_callback: URL for call status updates
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
        """Start verification process for a caller ID"""
        pass

    @abstractmethod
    def list_verified_caller_ids(self) -> list:
        """List all verified caller IDs for the account"""
        pass


class TwilioProvider(TelephonyProvider):
    """Twilio implementation of telephony provider"""

    def __init__(self):
        self.client = _get_twilio_client()

    def _ensure_client(self):
        """Ensure Twilio client is available"""
        if not self.client:
            self.client = _get_twilio_client()
        if not self.client:
            raise TelephonyError(
                "Twilio client not initialized. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
                error_code="NOT_CONFIGURED"
            )

    def place_call(
        self,
        to: str = None,
        from_: str = None,
        url: str = None,
        status_callback: str = None,
        timeout: int = 30,
        record: bool = True,
        recording_status_callback: str = None,
        # Alternative parameter names
        to_number: str = None,
        from_number: str = None,
        callback_url: str = None,
        status_callback_url: str = None
    ) -> CallResult:
        """Place an outbound call via Twilio with optional recording"""
        # Support both naming conventions
        to = to or to_number
        from_ = from_ or from_number
        url = url or callback_url
        status_callback = status_callback or status_callback_url
        self._ensure_client()

        try:
            from twilio.base.exceptions import TwilioRestException

            # Build call parameters
            call_params = {
                "to": to,
                "from_": from_,
                "url": url,
                "status_callback": status_callback,
                "status_callback_event": ['initiated', 'ringing', 'answered', 'completed'],
                "status_callback_method": 'POST',
                "timeout": timeout,
                "record": record
            }

            # Add recording callback if recording is enabled
            if record and recording_status_callback:
                call_params["recording_status_callback"] = recording_status_callback
                call_params["recording_status_callback_event"] = ['completed']
                call_params["recording_status_callback_method"] = 'POST'

            call = self.client.calls.create(**call_params)

            logger.info(f"Call placed: {call.sid} from {from_} to {to}")

            return CallResult(
                success=True,
                call_sid=call.sid,
                status=call.status
            )

        except TwilioRestException as e:
            logger.error(f"Twilio error placing call to {to}: {e.code} - {e.msg}")
            return CallResult(
                success=False,
                error_message=e.msg,
                error_code=str(e.code)
            )
        except Exception as e:
            logger.error(f"Unexpected error placing call to {to}: {e}")
            return CallResult(
                success=False,
                error_message=str(e),
                error_code="UNKNOWN"
            )

    def get_call_status(self, call_sid: str) -> Optional[CallStatus]:
        """Get the current status of a call"""
        self._ensure_client()

        try:
            from twilio.base.exceptions import TwilioRestException

            call = self.client.calls(call_sid).fetch()

            return CallStatus(
                call_sid=call.sid,
                status=call.status,
                duration=int(call.duration) if call.duration else None,
                start_time=str(call.start_time) if call.start_time else None,
                end_time=str(call.end_time) if call.end_time else None,
                answered_by=call.answered_by
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
            from twilio.base.exceptions import TwilioRestException

            self.client.calls(call_sid).update(status='completed')
            logger.info(f"Call hung up: {call_sid}")
            return True

        except TwilioRestException as e:
            logger.error(f"Error hanging up call {call_sid}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error hanging up call: {e}")
            return False

    def verify_caller_id(self, phone_number: str, friendly_name: str) -> Dict[str, Any]:
        """Start verification process for a caller ID"""
        self._ensure_client()

        try:
            from twilio.base.exceptions import TwilioRestException

            validation_request = self.client.validation_requests.create(
                phone_number=phone_number,
                friendly_name=friendly_name
            )

            logger.info("Caller ID verification initiated")

            return {
                "success": True,
                "validation_code": validation_request.validation_code,
                "call_sid": validation_request.call_sid,
                "phone_number": validation_request.phone_number,
                "friendly_name": validation_request.friendly_name
            }

        except TwilioRestException as e:
            logger.error(f"Error verifying caller ID: {e.code} - {e.msg}")
            return {
                "success": False,
                "error": e.msg,
                "error_code": str(e.code)
            }

    def check_caller_id_verification(self, phone_number: str) -> Dict[str, Any]:
        """Check if a caller ID is verified"""
        self._ensure_client()

        try:
            from twilio.base.exceptions import TwilioRestException

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
            from twilio.base.exceptions import TwilioRestException

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


class TelnyxProvider(TelephonyProvider):
    """Telnyx implementation of telephony provider"""

    def __init__(self):
        self.client = _get_telnyx_client()
        self.connection_id = os.getenv('TELNYX_CONNECTION_ID')

    def _ensure_client(self):
        """Ensure Telnyx client is available"""
        if not self.client:
            self.client = _get_telnyx_client()
        if not self.client:
            raise TelephonyError(
                "Telnyx client not initialized. Check TELNYX_API_KEY.",
                error_code="NOT_CONFIGURED"
            )
        if not self.connection_id:
            raise TelephonyError(
                "Telnyx connection ID not configured. Check TELNYX_CONNECTION_ID.",
                error_code="NOT_CONFIGURED"
            )

    def place_call(
        self,
        to: str = None,
        from_: str = None,
        url: str = None,
        status_callback: str = None,
        timeout: int = 30,
        record: bool = True,
        recording_status_callback: str = None,
        # Alternative parameter names
        to_number: str = None,
        from_number: str = None,
        callback_url: str = None,
        status_callback_url: str = None,
        # AMD options
        machine_detection: str = None,
        machine_detection_timeout: int = 30,
        async_amd: bool = False,
        async_amd_callback: str = None,
    ) -> CallResult:
        """Place an outbound call via Telnyx with optional recording and AMD"""
        # Support both naming conventions
        to = to or to_number
        from_ = from_ or from_number
        url = url or callback_url
        status_callback = status_callback or status_callback_url
        self._ensure_client()

        try:
            # Build call parameters
            call_params = {
                "connection_id": self.connection_id,
                "to": to,
                "from_": from_,
                "webhook_url": url,
                "webhook_url_method": "POST",
                "timeout_secs": timeout,
            }

            # Add recording if enabled
            if record:
                call_params["record"] = "record-from-answer"
                if recording_status_callback:
                    call_params["recording_status_callback"] = recording_status_callback

            # Add AMD if configured
            if machine_detection:
                call_params["answering_machine_detection"] = "detect"
                call_params["answering_machine_detection_config"] = {
                    "total_analysis_time_millis": machine_detection_timeout * 1000,
                    "after_greeting_silence_millis": 800,
                    "between_words_silence_millis": 50,
                    "greeting_duration_millis": 3500,
                    "initial_silence_millis": 3500,
                    "maximum_number_of_words": 5,
                    "maximum_word_length_millis": 3500,
                    "silence_threshold": 256,
                }

            # Create the call
            call = self.client.calls.create(**call_params)

            logger.info(f"Telnyx call placed: {call.data.call_control_id} from {from_} to {to}")

            return CallResult(
                success=True,
                call_sid=call.data.call_control_id,  # Telnyx uses call_control_id
                status="initiated"
            )

        except Exception as e:
            logger.error(f"Telnyx error placing call to {to}: {e}")
            return CallResult(
                success=False,
                error_message=str(e),
                error_code="TELNYX_ERROR"
            )

    def get_call_status(self, call_sid: str) -> Optional[CallStatus]:
        """Get the current status of a call"""
        self._ensure_client()

        try:
            # Telnyx doesn't have a direct call status fetch - status comes via webhooks
            # For now, return a placeholder. In practice, status should be tracked in DB.
            logger.warning(f"Telnyx call status fetch not directly supported. Use webhooks.")
            return CallStatus(
                call_sid=call_sid,
                status="unknown",
                duration=None,
                start_time=None,
                end_time=None,
                answered_by=None
            )

        except Exception as e:
            logger.error(f"Error fetching Telnyx call status: {e}")
            return None

    def hangup_call(self, call_sid: str) -> bool:
        """Terminate an active call"""
        self._ensure_client()

        try:
            # Use Telnyx Call Control to hang up
            self.client.calls.hangup(call_control_id=call_sid)
            logger.info(f"Telnyx call hung up: {call_sid}")
            return True

        except Exception as e:
            logger.error(f"Error hanging up Telnyx call {call_sid}: {e}")
            return False

    def verify_caller_id(self, phone_number: str, friendly_name: str) -> Dict[str, Any]:
        """
        Start verification process for a caller ID.

        Note: Telnyx doesn't require caller ID verification for numbers you own.
        This is mainly for compatibility with the interface.
        """
        self._ensure_client()

        # Telnyx uses phone numbers directly from your account
        # No separate verification process needed for owned numbers
        logger.info("Telnyx caller ID check (verification not required for owned numbers)")

        return {
            "success": True,
            "message": "Telnyx does not require separate caller ID verification for owned numbers",
            "phone_number": phone_number,
            "friendly_name": friendly_name
        }

    def list_verified_caller_ids(self) -> list:
        """List all phone numbers available for the account"""
        self._ensure_client()

        try:
            # List phone numbers from the Telnyx account
            phone_numbers = self.client.phone_numbers.list()

            return [
                {
                    "sid": pn.data.id,
                    "phone_number": pn.data.phone_number,
                    "friendly_name": pn.data.phone_number  # Telnyx doesn't have friendly names
                }
                for pn in phone_numbers.data
            ]

        except Exception as e:
            logger.error(f"Error listing Telnyx phone numbers: {e}")
            return []


# Singleton instance
_provider_instance: Optional[TelephonyProvider] = None


def get_telephony_provider() -> TelephonyProvider:
    """
    Get the singleton telephony provider instance

    Returns the configured provider based on TELEPHONY_PROVIDER env var.
    Supports 'twilio' (default) and 'telnyx'.
    """
    global _provider_instance

    provider_type = os.getenv('TELEPHONY_PROVIDER', 'twilio').lower()

    if _provider_instance is None:
        if provider_type == 'telnyx':
            _provider_instance = TelnyxProvider()
            logger.info("Using Telnyx telephony provider")
        elif provider_type == 'twilio':
            _provider_instance = TwilioProvider()
            logger.info("Using Twilio telephony provider")
        else:
            raise ValueError(f"Unknown telephony provider: {provider_type}. Supported: twilio, telnyx")

    return _provider_instance


def reset_provider():
    """Reset the provider instance (useful for testing or switching providers)"""
    global _provider_instance
    _provider_instance = None
