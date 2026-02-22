"""
Webhook Integration for Call Intelligence Service

Provides webhook-based integration for:
- Receiving call recordings and transcripts from external systems
- Sending processing results back to external systems via callbacks
- Async processing with status notifications

Supported Integrations:
- Telnyx (recordings + status callbacks)
- Vonage/Nexmo
- Custom CRM systems
- Any system that can send/receive HTTP webhooks

Usage:
    from services.call_intelligence.webhooks import (
        WebhookHandler,
        WebhookConfig,
        register_callback,
    )

    # Create handler
    handler = WebhookHandler(processor, config)

    # Process incoming webhook
    result = await handler.handle_webhook(
        provider="telnyx",
        payload=request_data,
        callback_url="https://crm.example.com/webhook/callback"
    )

    # Or use with FastAPI
    @app.post("/webhooks/telnyx/recording")
    async def telnyx_recording_webhook(request: Request):
        return await handler.handle_telnyx_webhook(request)
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
import uuid
import aiohttp

if TYPE_CHECKING:
    from .processor import CallIntelligenceProcessor

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class WebhookProvider(str, Enum):
    """Supported webhook providers."""
    TELNYX = "telnyx"
    VONAGE = "vonage"
    AMAZON_CONNECT = "amazon_connect"
    CUSTOM = "custom"


class WebhookEventType(str, Enum):
    """Types of webhook events."""
    # Inbound events (received)
    RECORDING_COMPLETED = "recording_completed"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    CALL_ENDED = "call_ended"

    # Outbound events (sent)
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    EXTRACTION_COMPLETED = "extraction_completed"
    LEAD_CREATED = "lead_created"
    PREQUAL_COMPLETED = "prequal_completed"


class CallbackStatus(str, Enum):
    """Status of a callback attempt."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class WebhookConfig:
    """Configuration for webhook handling."""
    # Signature verification
    verify_signatures: bool = True
    telnyx_api_key: Optional[str] = None
    vonage_api_secret: Optional[str] = None
    custom_secret_key: Optional[str] = None

    # Callback settings
    callback_timeout_seconds: int = 30
    callback_max_retries: int = 3
    callback_retry_delay_seconds: int = 5

    # Processing settings
    async_processing: bool = True  # Process in background
    include_raw_transcript: bool = False  # Include transcript in callbacks

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        """Create config from environment variables."""
        return cls(
            verify_signatures=os.getenv("WEBHOOK_VERIFY_SIGNATURES", "true").lower() == "true",
            telnyx_api_key=os.getenv("TELNYX_API_KEY"),
            vonage_api_secret=os.getenv("VONAGE_API_SECRET"),
            custom_secret_key=os.getenv("WEBHOOK_SECRET_KEY"),
            callback_timeout_seconds=int(os.getenv("WEBHOOK_CALLBACK_TIMEOUT", "30")),
            callback_max_retries=int(os.getenv("WEBHOOK_CALLBACK_RETRIES", "3")),
        )


@dataclass
class CallbackRegistration:
    """Registration for a callback URL."""
    callback_id: str
    callback_url: str
    events: List[WebhookEventType]
    headers: Dict[str, str] = field(default_factory=dict)
    secret_key: Optional[str] = None  # For signing callbacks
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "callback_id": self.callback_id,
            "callback_url": self.callback_url,
            "events": [e.value for e in self.events],
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class CallbackAttempt:
    """Record of a callback attempt."""
    attempt_id: str
    callback_id: str
    event_type: WebhookEventType
    payload: Dict[str, Any]
    status: CallbackStatus = CallbackStatus.PENDING
    attempt_number: int = 1
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    duration_ms: int = 0


@dataclass
class WebhookResult:
    """Result of webhook processing."""
    success: bool
    webhook_id: str
    call_id: Optional[str] = None
    provider: Optional[WebhookProvider] = None
    event_type: Optional[WebhookEventType] = None
    message: str = ""
    processing_id: Optional[str] = None  # For async processing
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "webhook_id": self.webhook_id,
            "call_id": self.call_id,
            "provider": self.provider.value if self.provider else None,
            "event_type": self.event_type.value if self.event_type else None,
            "message": self.message,
            "processing_id": self.processing_id,
            "errors": self.errors,
        }


# =============================================================================
# Webhook Handler
# =============================================================================

class WebhookHandler:
    """
    Handles incoming webhooks and outgoing callbacks.

    Usage:
        handler = WebhookHandler(processor, config)

        # Handle incoming webhook
        result = await handler.handle_webhook("telnyx", payload)

        # Register callback for results
        handler.register_callback(
            url="https://crm.example.com/callback",
            events=[WebhookEventType.PROCESSING_COMPLETED]
        )
    """

    def __init__(
        self,
        processor: Optional["CallIntelligenceProcessor"] = None,
        config: Optional[WebhookConfig] = None,
    ):
        """
        Initialize webhook handler.

        Args:
            processor: CallIntelligenceProcessor for processing transcripts
            config: Webhook configuration
        """
        self.processor = processor
        self.config = config or WebhookConfig.from_env()

        # Callback registrations by callback_id
        self._callbacks: Dict[str, CallbackRegistration] = {}

        # Processing jobs by processing_id
        self._processing_jobs: Dict[str, Dict[str, Any]] = {}

        # Callback attempt history (for debugging)
        self._callback_history: List[CallbackAttempt] = []

    def register_callback(
        self,
        callback_url: str,
        events: Optional[List[WebhookEventType]] = None,
        headers: Optional[Dict[str, str]] = None,
        secret_key: Optional[str] = None,
        expires_in_hours: Optional[int] = None,
    ) -> CallbackRegistration:
        """
        Register a callback URL to receive events.

        Args:
            callback_url: URL to send events to
            events: List of events to receive (default: all)
            headers: Custom headers to include in callbacks
            secret_key: Key for signing callback payloads
            expires_in_hours: Hours until registration expires

        Returns:
            CallbackRegistration with callback_id
        """
        callback_id = str(uuid.uuid4())[:8].upper()

        if events is None:
            events = [
                WebhookEventType.PROCESSING_COMPLETED,
                WebhookEventType.PROCESSING_FAILED,
            ]

        expires_at = None
        if expires_in_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

        registration = CallbackRegistration(
            callback_id=callback_id,
            callback_url=callback_url,
            events=events,
            headers=headers or {},
            secret_key=secret_key,
            expires_at=expires_at,
        )

        self._callbacks[callback_id] = registration
        logger.info(f"Registered callback {callback_id} for {len(events)} events")

        return registration

    def unregister_callback(self, callback_id: str) -> bool:
        """Unregister a callback."""
        if callback_id in self._callbacks:
            del self._callbacks[callback_id]
            logger.info(f"Unregistered callback {callback_id}")
            return True
        return False

    async def handle_webhook(
        self,
        provider: str,
        payload: Dict[str, Any],
        callback_url: Optional[str] = None,
        callback_headers: Optional[Dict[str, str]] = None,
    ) -> WebhookResult:
        """
        Handle an incoming webhook.

        Args:
            provider: Webhook provider (telnyx, vonage, custom)
            payload: Webhook payload data
            callback_url: Optional one-time callback URL for results
            callback_headers: Optional headers for callback

        Returns:
            WebhookResult with processing status
        """
        webhook_id = str(uuid.uuid4())[:8].upper()
        logger.info(f"Handling webhook {webhook_id} from {provider}")

        try:
            # Parse based on provider
            provider_enum = WebhookProvider(provider.lower())

            if provider_enum == WebhookProvider.TELNYX:
                call_data = self._parse_telnyx_webhook(payload)
            elif provider_enum == WebhookProvider.VONAGE:
                call_data = self._parse_vonage_webhook(payload)
            else:
                call_data = self._parse_custom_webhook(payload)

            call_id = call_data.get("call_id")
            if not call_id:
                return WebhookResult(
                    success=False,
                    webhook_id=webhook_id,
                    provider=provider_enum,
                    errors=["No call_id found in webhook payload"],
                )

            # Register one-time callback if provided
            callback_id = None
            if callback_url:
                registration = self.register_callback(
                    callback_url=callback_url,
                    headers=callback_headers,
                    expires_in_hours=24,
                )
                callback_id = registration.callback_id

            # Process asynchronously or synchronously
            if self.config.async_processing:
                processing_id = await self._start_async_processing(
                    call_id=call_id,
                    call_data=call_data,
                    webhook_id=webhook_id,
                    callback_id=callback_id,
                )

                return WebhookResult(
                    success=True,
                    webhook_id=webhook_id,
                    call_id=call_id,
                    provider=provider_enum,
                    event_type=WebhookEventType.RECORDING_COMPLETED,
                    message="Processing started asynchronously",
                    processing_id=processing_id,
                )
            else:
                # Synchronous processing
                result = await self._process_call(call_id, call_data)

                # Send callbacks
                await self._send_callbacks(
                    WebhookEventType.PROCESSING_COMPLETED,
                    {
                        "call_id": call_id,
                        "webhook_id": webhook_id,
                        "result": result,
                    },
                    callback_id=callback_id,
                )

                return WebhookResult(
                    success=True,
                    webhook_id=webhook_id,
                    call_id=call_id,
                    provider=provider_enum,
                    event_type=WebhookEventType.PROCESSING_COMPLETED,
                    message="Processing completed",
                )

        except Exception as e:
            logger.exception(f"Webhook {webhook_id} failed: {e}")
            return WebhookResult(
                success=False,
                webhook_id=webhook_id,
                errors=[str(e)],
            )

    async def handle_telnyx_recording(
        self,
        payload: Dict[str, Any],
        callback_url: Optional[str] = None,
    ) -> WebhookResult:
        """
        Handle Telnyx recording completed webhook.

        This is called when Telnyx finishes recording a call.
        """
        # Verify signature if configured
        # (In production, this would use request.headers and request.url)

        return await self.handle_webhook(
            provider="telnyx",
            payload=payload,
            callback_url=callback_url,
        )

    async def handle_vonage_recording(
        self,
        payload: Dict[str, Any],
        callback_url: Optional[str] = None,
    ) -> WebhookResult:
        """Handle Vonage recording completed webhook."""
        return await self.handle_webhook(
            provider="vonage",
            payload=payload,
            callback_url=callback_url,
        )

    def get_processing_status(self, processing_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an async processing job."""
        return self._processing_jobs.get(processing_id)

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _parse_telnyx_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Telnyx webhook payload."""
        return {
            "call_id": payload.get("CallSid") or payload.get("call_control_id"),
            "recording_url": payload.get("RecordingUrl") or payload.get("recording_url"),
            "recording_sid": payload.get("RecordingSid") or payload.get("recording_id"),
            "duration": int(payload.get("RecordingDuration", 0) or payload.get("duration", 0)),
            "from_number": payload.get("From") or payload.get("from"),
            "to_number": payload.get("To") or payload.get("to"),
            "direction": payload.get("Direction") or payload.get("direction"),
            "provider": "telnyx",
        }

    def _parse_vonage_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Vonage webhook payload."""
        return {
            "call_id": payload.get("conversation_uuid") or payload.get("uuid"),
            "recording_url": payload.get("recording_url"),
            "duration": int(payload.get("duration", 0)),
            "from_number": payload.get("from"),
            "to_number": payload.get("to"),
            "direction": payload.get("direction"),
            "provider": "vonage",
        }

    def _parse_custom_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse custom webhook payload."""
        return {
            "call_id": payload.get("call_id"),
            "recording_url": payload.get("recording_url"),
            "transcript": payload.get("transcript"),
            "duration": payload.get("duration", 0),
            "from_number": payload.get("from"),
            "to_number": payload.get("to"),
            "metadata": payload.get("metadata", {}),
            "provider": "custom",
        }

    async def _start_async_processing(
        self,
        call_id: str,
        call_data: Dict[str, Any],
        webhook_id: str,
        callback_id: Optional[str] = None,
    ) -> str:
        """Start async processing and return processing ID."""
        processing_id = str(uuid.uuid4())[:12].upper()

        self._processing_jobs[processing_id] = {
            "status": "processing",
            "call_id": call_id,
            "webhook_id": webhook_id,
            "started_at": datetime.utcnow().isoformat(),
            "callback_id": callback_id,
        }

        # Start processing in background
        asyncio.create_task(
            self._async_process_and_callback(
                processing_id=processing_id,
                call_id=call_id,
                call_data=call_data,
                callback_id=callback_id,
            )
        )

        return processing_id

    async def _async_process_and_callback(
        self,
        processing_id: str,
        call_id: str,
        call_data: Dict[str, Any],
        callback_id: Optional[str] = None,
    ) -> None:
        """Process call and send callbacks."""
        try:
            # Send processing started callback
            await self._send_callbacks(
                WebhookEventType.PROCESSING_STARTED,
                {
                    "processing_id": processing_id,
                    "call_id": call_id,
                    "started_at": datetime.utcnow().isoformat(),
                },
                callback_id=callback_id,
            )

            # Process the call
            result = await self._process_call(call_id, call_data)

            # Update job status
            self._processing_jobs[processing_id].update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "result_summary": {
                    "total_extractions": result.get("total_extractions", 0),
                    "high_confidence": result.get("high_confidence_count", 0),
                },
            })

            # Send completion callback
            await self._send_callbacks(
                WebhookEventType.PROCESSING_COMPLETED,
                {
                    "processing_id": processing_id,
                    "call_id": call_id,
                    "result": result,
                    "completed_at": datetime.utcnow().isoformat(),
                },
                callback_id=callback_id,
            )

        except Exception as e:
            logger.exception(f"Async processing {processing_id} failed: {e}")

            self._processing_jobs[processing_id].update({
                "status": "failed",
                "error": "Internal server error",
                "failed_at": datetime.utcnow().isoformat(),
            })

            # Send failure callback
            await self._send_callbacks(
                WebhookEventType.PROCESSING_FAILED,
                {
                    "processing_id": processing_id,
                    "call_id": call_id,
                    "error": "Internal server error",
                    "failed_at": datetime.utcnow().isoformat(),
                },
                callback_id=callback_id,
            )

    async def _process_call(
        self,
        call_id: str,
        call_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a call through the intelligence pipeline."""
        if not self.processor:
            logger.warning("No processor configured - returning mock result")
            return {
                "call_id": call_id,
                "success": True,
                "total_extractions": 0,
                "high_confidence_count": 0,
                "message": "No processor configured",
            }

        # Import here to avoid circular imports
        from .data_contracts import CallIntelligenceRequest

        transcript = call_data.get("transcript", "")

        # If we have a recording URL but no transcript, we'd need to transcribe
        # For now, assume transcript is provided or we return empty result
        if not transcript and call_data.get("recording_url"):
            logger.info(f"Recording URL provided but no transcript - transcription required")
            return {
                "call_id": call_id,
                "success": False,
                "error": "Transcription required but not implemented",
                "recording_url": call_data.get("recording_url"),
            }

        request = CallIntelligenceRequest(
            call_id=call_id,
            transcript=transcript,
        )

        response = await self.processor.process_transcript(request)
        return response.to_dict()

    async def _send_callbacks(
        self,
        event_type: WebhookEventType,
        payload: Dict[str, Any],
        callback_id: Optional[str] = None,
    ) -> None:
        """Send callbacks to registered URLs."""
        # Find relevant callbacks
        callbacks_to_send = []

        # Specific callback if provided
        if callback_id and callback_id in self._callbacks:
            callback = self._callbacks[callback_id]
            if callback.active and event_type in callback.events:
                callbacks_to_send.append(callback)

        # All registered callbacks for this event
        for callback in self._callbacks.values():
            if callback.callback_id == callback_id:
                continue  # Already handled above
            if callback.active and event_type in callback.events:
                # Check expiration
                if callback.expires_at and datetime.utcnow() > callback.expires_at:
                    callback.active = False
                    continue
                callbacks_to_send.append(callback)

        # Send callbacks
        for callback in callbacks_to_send:
            await self._send_single_callback(callback, event_type, payload)

    async def _send_single_callback(
        self,
        callback: CallbackRegistration,
        event_type: WebhookEventType,
        payload: Dict[str, Any],
    ) -> CallbackAttempt:
        """Send a single callback with retries."""
        attempt_id = str(uuid.uuid4())[:8].upper()

        full_payload = {
            "event_type": event_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "callback_id": callback.callback_id,
            **payload,
        }

        # Sign payload if secret key configured
        if callback.secret_key:
            signature = self._sign_payload(full_payload, callback.secret_key)
            callback.headers["X-Webhook-Signature"] = signature

        callback.headers["Content-Type"] = "application/json"

        attempt = CallbackAttempt(
            attempt_id=attempt_id,
            callback_id=callback.callback_id,
            event_type=event_type,
            payload=full_payload,
        )

        for retry in range(self.config.callback_max_retries):
            attempt.attempt_number = retry + 1

            try:
                start_time = time.time()

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        callback.callback_url,
                        json=full_payload,
                        headers=callback.headers,
                        timeout=aiohttp.ClientTimeout(total=self.config.callback_timeout_seconds),
                    ) as response:
                        attempt.response_code = response.status
                        attempt.response_body = await response.text()
                        attempt.duration_ms = int((time.time() - start_time) * 1000)
                        attempt.sent_at = datetime.utcnow()

                        if response.status < 400:
                            attempt.status = CallbackStatus.DELIVERED
                            logger.info(
                                f"Callback {attempt_id} delivered to {callback.callback_url} "
                                f"(status={response.status})"
                            )
                            break
                        else:
                            attempt.status = CallbackStatus.RETRYING
                            logger.warning(
                                f"Callback {attempt_id} got status {response.status}, retrying..."
                            )

            except asyncio.TimeoutError:
                attempt.error = "Request timed out"
                attempt.status = CallbackStatus.RETRYING
                logger.warning(f"Callback {attempt_id} timed out, retrying...")

            except Exception as e:
                attempt.error = str(e)
                attempt.status = CallbackStatus.RETRYING
                logger.warning(f"Callback {attempt_id} failed: {e}, retrying...")

            # Wait before retry
            if retry < self.config.callback_max_retries - 1:
                await asyncio.sleep(self.config.callback_retry_delay_seconds * (retry + 1))

        # Final status
        if attempt.status == CallbackStatus.RETRYING:
            attempt.status = CallbackStatus.FAILED
            logger.error(f"Callback {attempt_id} failed after {self.config.callback_max_retries} attempts")

        self._callback_history.append(attempt)
        return attempt

    def _sign_payload(self, payload: Dict[str, Any], secret_key: str) -> str:
        """Sign payload with HMAC-SHA256."""
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.new(
            secret_key.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def verify_telnyx_signature(
        self,
        signature: str,
        url: str,
        params: Dict[str, str],
    ) -> bool:
        """Verify Telnyx request signature."""
        if not self.config.telnyx_api_key:
            return True  # Skip verification if no key

        # Telnyx signature validation logic
        # Build the string to sign
        s = url
        for key in sorted(params.keys()):
            s += key + params[key]

        expected = hmac.new(
            self.config.telnyx_api_key.encode(),
            s.encode(),
            hashlib.sha1
        ).digest()

        import base64
        expected_b64 = base64.b64encode(expected).decode()

        return hmac.compare_digest(signature, expected_b64)


# =============================================================================
# Factory Functions
# =============================================================================

def create_webhook_handler(
    processor: Optional["CallIntelligenceProcessor"] = None,
    config: Optional[WebhookConfig] = None,
) -> WebhookHandler:
    """Create a webhook handler instance."""
    return WebhookHandler(processor, config)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "WebhookHandler",
    "WebhookConfig",
    "WebhookProvider",
    "WebhookEventType",
    "WebhookResult",
    "CallbackRegistration",
    "CallbackStatus",
    "create_webhook_handler",
]
