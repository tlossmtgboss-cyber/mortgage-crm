"""
Telephony Provider Abstraction — Telnyx Implementation

Provides a clean abstraction layer for telephony operations using Telnyx
as the sole provider.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER — protects against cascading failures from Telnyx API outages
# Pattern adapted from services/call_intelligence/llm_client.py (async → sync)
# =============================================================================

class TelephonyCircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation — requests pass through
    OPEN = "open"           # Provider down — requests fail fast
    HALF_OPEN = "half_open" # Testing recovery — limited requests allowed


class TelephonyCircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open (telephony provider unavailable)."""
    pass


class TelephonyCircuitBreaker:
    """
    Circuit breaker for telephony API calls.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: API is down, requests fail fast without calling API
    - HALF_OPEN: Testing if API recovered, limited requests allowed

    Uses threading.Lock for thread-safe synchronous operation.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = TelephonyCircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> TelephonyCircuitState:
        with self._lock:
            if self._state == TelephonyCircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = TelephonyCircuitState.HALF_OPEN
                    self._half_open_calls = 0
            return self._state

    def check(self):
        """Check if request is allowed. Raises TelephonyCircuitBreakerOpen if not."""
        current_state = self.state  # property acquires lock internally
        if current_state == TelephonyCircuitState.CLOSED:
            return
        elif current_state == TelephonyCircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return
            raise TelephonyCircuitBreakerOpen(
                f"Telephony circuit breaker HALF_OPEN: max test calls ({self.half_open_max_calls}) reached"
            )
        else:
            with self._lock:
                remaining = self.recovery_timeout - (time.monotonic() - self._last_failure_time)
            raise TelephonyCircuitBreakerOpen(
                f"Telephony circuit breaker is OPEN. Recovery in {remaining:.0f}s"
            )

    def record_success(self):
        """Record a successful API call."""
        with self._lock:
            if self._state == TelephonyCircuitState.HALF_OPEN:
                logger.info("Telephony circuit breaker: HALF_OPEN -> CLOSED (provider recovered)")
            self._state = TelephonyCircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0

    def record_failure(self):
        """Record a failed API call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                if self._state != TelephonyCircuitState.OPEN:
                    logger.warning(
                        f"Telephony circuit breaker OPENED after {self._failure_count} consecutive failures"
                    )
                self._state = TelephonyCircuitState.OPEN
                self._half_open_calls = 0


# Module-level singleton
_telephony_circuit_breaker = TelephonyCircuitBreaker()

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

# Lazy import Telnyx to allow app to start without credentials
_telnyx_client = None


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
            url: URL for TeXML instructions when call is answered
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

    @abstractmethod
    def check_caller_id_verification(self, phone_number: str) -> Dict[str, Any]:
        """Check verification status for a caller ID"""
        pass


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
        """Place an outbound call via Telnyx with optional recording and AMD.

        Includes circuit breaker protection and retry logic (max 2 retries with
        exponential backoff) for transient API errors.
        """
        # Support both naming conventions
        to = to or to_number
        from_ = from_ or from_number
        url = url or callback_url
        status_callback = status_callback or status_callback_url
        self._ensure_client()

        # Build call parameters (done once, reused across retries)
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

        # Retry loop with circuit breaker
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                # Check circuit breaker before making API call
                _telephony_circuit_breaker.check()

                call = self.client.calls.dial(**call_params)

                logger.info(f"Telnyx call placed: {call.data.call_control_id} from {from_} to {to}")

                _telephony_circuit_breaker.record_success()

                return CallResult(
                    success=True,
                    call_sid=call.data.call_control_id,
                    status="initiated"
                )

            except TelephonyCircuitBreakerOpen as e:
                logger.warning(f"Telephony circuit breaker blocked call to {to}: {e}")
                return CallResult(
                    success=False,
                    error_message=str(e),
                    error_code="CIRCUIT_BREAKER_OPEN"
                )

            except Exception as e:
                _telephony_circuit_breaker.record_failure()
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 4)  # 1s, 2s
                    logger.warning(
                        f"Telnyx call attempt {attempt + 1}/{max_retries + 1} failed for {to}: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                    continue

                logger.error(f"Telnyx error placing call to {to} after {max_retries + 1} attempts: {e}")
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
            logger.warning("Telnyx call status fetch not directly supported. Use webhooks.")
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
        For non-Telnyx numbers, real verification would happen through Telnyx's portal.
        Returns a validation_code so the UI flow can display it.
        """
        import random
        self._ensure_client()

        logger.info("Telnyx caller ID check (verification not required for owned numbers)")

        validation_code = str(random.randint(100000, 999999))

        return {
            "success": True,
            "message": "Telnyx does not require separate caller ID verification for owned numbers",
            "phone_number": phone_number,
            "friendly_name": friendly_name,
            "validation_code": validation_code
        }

    def list_verified_caller_ids(self) -> list:
        """List all phone numbers available for the account"""
        self._ensure_client()

        try:
            phone_numbers = self.client.phone_numbers.list()

            return [
                {
                    "sid": pn.id,
                    "phone_number": pn.phone_number,
                    "friendly_name": pn.phone_number
                }
                for pn in phone_numbers
            ]

        except Exception as e:
            logger.error(f"Error listing Telnyx phone numbers: {e}")
            return []

    def check_caller_id_verification(self, phone_number: str) -> Dict[str, Any]:
        """
        Check verification status for a caller ID.

        Telnyx doesn't have a dedicated "check verification status" API —
        verification state is tracked in our DB. This returns a positive
        result so the router endpoint can update the DB record accordingly.
        """
        return {
            "verified": True,
            "phone_number": phone_number,
            "friendly_name": phone_number
        }


# Singleton instance
_provider_instance: Optional[TelephonyProvider] = None


def get_telephony_provider() -> TelephonyProvider:
    """
    Get the singleton telephony provider instance.

    Always returns a TelnyxProvider.
    """
    global _provider_instance

    if _provider_instance is None:
        _provider_instance = TelnyxProvider()
        logger.info("Using Telnyx telephony provider")

    return _provider_instance


def reset_provider():
    """Reset the provider instance (useful for testing or switching providers)"""
    global _provider_instance
    _provider_instance = None
