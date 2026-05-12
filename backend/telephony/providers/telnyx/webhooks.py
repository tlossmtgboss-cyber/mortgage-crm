"""
Telnyx Webhook Handlers

Parses and validates Telnyx webhook events for:
- Call Control events (initiated, ringing, answered, hangup)
- AMD (Answering Machine Detection) events
- SMS events (sent, delivered, failed)
"""

import hmac
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class TelnyxEventType(str, Enum):
    """Telnyx webhook event types"""
    # Call events
    CALL_INITIATED = "call.initiated"
    CALL_RINGING = "call.ringing"
    CALL_ANSWERED = "call.answered"
    CALL_HANGUP = "call.hangup"
    CALL_BRIDGED = "call.bridged"
    CALL_SPEAK_STARTED = "call.speak.started"
    CALL_SPEAK_ENDED = "call.speak.ended"
    CALL_PLAYBACK_STARTED = "call.playback.started"
    CALL_PLAYBACK_ENDED = "call.playback.ended"
    CALL_GATHER_ENDED = "call.gather.ended"
    CALL_RECORDING_SAVED = "call.recording.saved"

    # AMD events
    CALL_MACHINE_DETECTION_ENDED = "call.machine.detection.ended"
    CALL_MACHINE_GREETING_ENDED = "call.machine.greeting.ended"
    CALL_MACHINE_PREMIUM_DETECTION_ENDED = "call.machine.premium.detection.ended"
    CALL_MACHINE_PREMIUM_GREETING_ENDED = "call.machine.premium.greeting.ended"

    # SMS events
    MESSAGE_SENT = "message.sent"
    MESSAGE_FINALIZED = "message.finalized"
    MESSAGE_RECEIVED = "message.received"


@dataclass
class TelnyxWebhookEvent:
    """Base class for all Telnyx webhook events"""
    event_type: str
    id: str
    occurred_at: datetime
    record_type: str
    payload: Dict[str, Any]

    @property
    def call_control_id(self) -> Optional[str]:
        """Get call control ID if this is a call event"""
        return self.payload.get("call_control_id")

    @property
    def call_leg_id(self) -> Optional[str]:
        """Get call leg ID if this is a call event"""
        return self.payload.get("call_leg_id")

    @property
    def connection_id(self) -> Optional[str]:
        """Get connection ID"""
        return self.payload.get("connection_id")


@dataclass
class TelnyxCallEvent:
    """Call-specific webhook event"""
    event_type: str
    id: str
    occurred_at: datetime
    record_type: str
    payload: Dict[str, Any]
    call_control_id: str
    call_leg_id: str
    call_session_id: str
    from_number: str
    to_number: str
    direction: str  # "incoming" or "outgoing" (Call Control uses these values)
    state: str

    @classmethod
    def from_webhook(cls, event: TelnyxWebhookEvent) -> "TelnyxCallEvent":
        """Create from base webhook event"""
        payload = event.payload
        return cls(
            event_type=event.event_type,
            id=event.id,
            occurred_at=event.occurred_at,
            record_type=event.record_type,
            payload=payload,
            call_control_id=payload.get("call_control_id", ""),
            call_leg_id=payload.get("call_leg_id", ""),
            call_session_id=payload.get("call_session_id", ""),
            from_number=payload.get("from", ""),
            to_number=payload.get("to", ""),
            direction=payload.get("direction", ""),
            state=payload.get("state", ""),
        )

    @property
    def is_answered(self) -> bool:
        return self.event_type == TelnyxEventType.CALL_ANSWERED

    @property
    def is_hangup(self) -> bool:
        return self.event_type == TelnyxEventType.CALL_HANGUP

    @property
    def hangup_cause(self) -> Optional[str]:
        """Get hangup cause if this is a hangup event"""
        if self.is_hangup:
            return self.payload.get("hangup_cause")
        return None

    @property
    def hangup_source(self) -> Optional[str]:
        """Get hangup source (who hung up)"""
        if self.is_hangup:
            return self.payload.get("hangup_source")
        return None


@dataclass
class TelnyxAMDEvent:
    """AMD (Answering Machine Detection) event"""
    event_type: str
    id: str
    occurred_at: datetime
    record_type: str
    payload: Dict[str, Any]
    call_control_id: str
    result: str  # "human", "machine", "not_sure", "unknown"

    @classmethod
    def from_webhook(cls, event: TelnyxWebhookEvent) -> "TelnyxAMDEvent":
        """Create from base webhook event"""
        payload = event.payload
        return cls(
            event_type=event.event_type,
            id=event.id,
            occurred_at=event.occurred_at,
            record_type=event.record_type,
            payload=payload,
            call_control_id=payload.get("call_control_id", ""),
            result=payload.get("result", "unknown"),
        )

    @property
    def is_human(self) -> bool:
        return self.result == "human"

    @property
    def is_machine(self) -> bool:
        return self.result == "machine"

    @property
    def is_voicemail(self) -> bool:
        """Alias for is_machine"""
        return self.is_machine

    def to_legacy_format(self) -> str:
        """Convert to legacy (TwiML-compatible) AnsweredBy format"""
        mapping = {
            "human": "human",
            "machine": "machine_end_beep",
            "not_sure": "unknown",
            "unknown": "unknown",
        }
        return mapping.get(self.result, "unknown")

    # Backward-compatible alias
    to_twilio_format = to_legacy_format


@dataclass
class TelnyxSMSEvent:
    """SMS-specific webhook event"""
    event_type: str
    id: str
    occurred_at: datetime
    record_type: str
    payload: Dict[str, Any]
    message_id: str
    from_number: str
    to_number: str
    text: str
    direction: str  # "inbound" or "outbound"
    status: str

    @classmethod
    def from_webhook(cls, event: TelnyxWebhookEvent) -> "TelnyxSMSEvent":
        """Create from base webhook event"""
        payload = event.payload

        # Handle different payload structures
        from_info = payload.get("from", {})
        to_info = payload.get("to", [{}])

        from_number = from_info.get("phone_number", "") if isinstance(from_info, dict) else str(from_info)
        to_number = to_info[0].get("phone_number", "") if isinstance(to_info, list) and to_info else str(to_info)

        return cls(
            event_type=event.event_type,
            id=event.id,
            occurred_at=event.occurred_at,
            record_type=event.record_type,
            payload=payload,
            message_id=payload.get("id", ""),
            from_number=from_number,
            to_number=to_number,
            text=payload.get("text", ""),
            direction=payload.get("direction", ""),
            status=payload.get("to", [{}])[0].get("status", "") if isinstance(payload.get("to"), list) else "",
        )

    @property
    def is_inbound(self) -> bool:
        return self.direction == "inbound"

    @property
    def is_delivered(self) -> bool:
        return self.status == "delivered"

    @property
    def is_failed(self) -> bool:
        return self.status in ["sending_failed", "delivery_failed"]


def validate_telnyx_webhook(
    payload: bytes,
    signature: str,
    timestamp: str,
    public_key: str = None,
) -> bool:
    """
    Validate Telnyx webhook signature.

    Telnyx uses Ed25519 signatures for webhook validation.

    Args:
        payload: Raw request body bytes
        signature: The telnyx-signature-ed25519 header value
        timestamp: The telnyx-timestamp header value
        public_key: The Telnyx public key (from portal or API)

    Returns:
        True if signature is valid, False otherwise
    """
    if not public_key:
        logger.warning("Telnyx webhook REJECTED - no public key configured")
        return False

    try:
        # Telnyx uses Ed25519 for signature verification
        # The signed payload is: timestamp + "." + payload
        import nacl.signing
        import nacl.encoding

        signed_payload = f"{timestamp}.".encode() + payload

        # Decode the signature and public key from base64
        signature_bytes = nacl.encoding.Base64Encoder.decode(signature)
        public_key_bytes = nacl.encoding.Base64Encoder.decode(public_key)

        # Create verify key and verify
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        verify_key.verify(signed_payload, signature_bytes)

        return True

    except ImportError:
        logger.error("PyNaCl not installed - webhook validation REJECTED. Install with: pip install pynacl")
        return False
    except Exception as e:
        logger.error(f"Telnyx webhook validation failed: {e}")
        return False


def parse_telnyx_webhook(
    data: Dict[str, Any]
) -> Union[TelnyxCallEvent, TelnyxAMDEvent, TelnyxSMSEvent, TelnyxWebhookEvent]:
    """
    Parse a Telnyx webhook payload into the appropriate event type.

    Args:
        data: The parsed JSON webhook payload

    Returns:
        Appropriate event type based on the event_type field
    """
    # Extract event data from Telnyx format
    event_data = data.get("data", data)

    # Parse timestamp
    occurred_at_str = event_data.get("occurred_at", "")
    try:
        if occurred_at_str:
            # Handle ISO format with Z suffix
            occurred_at_str = occurred_at_str.replace("Z", "+00:00")
            occurred_at = datetime.fromisoformat(occurred_at_str)
        else:
            occurred_at = datetime.now(timezone.utc)
    except ValueError:
        occurred_at = datetime.now(timezone.utc)

    # Create base event
    base_event = TelnyxWebhookEvent(
        event_type=event_data.get("event_type", ""),
        id=event_data.get("id", ""),
        occurred_at=occurred_at,
        record_type=event_data.get("record_type", ""),
        payload=event_data.get("payload", {}),
    )

    event_type = base_event.event_type

    # Route to appropriate event class
    if event_type in [
        TelnyxEventType.CALL_MACHINE_DETECTION_ENDED,
        TelnyxEventType.CALL_MACHINE_GREETING_ENDED,
        TelnyxEventType.CALL_MACHINE_PREMIUM_DETECTION_ENDED,
        TelnyxEventType.CALL_MACHINE_PREMIUM_GREETING_ENDED,
    ]:
        return TelnyxAMDEvent.from_webhook(base_event)

    elif event_type in [
        TelnyxEventType.MESSAGE_SENT,
        TelnyxEventType.MESSAGE_FINALIZED,
        TelnyxEventType.MESSAGE_RECEIVED,
    ]:
        return TelnyxSMSEvent.from_webhook(base_event)

    elif event_type.startswith("call."):
        return TelnyxCallEvent.from_webhook(base_event)

    else:
        # Return base event for unknown types
        logger.info(f"Unknown Telnyx event type: {event_type}")
        return base_event


def map_telnyx_status_to_legacy(telnyx_event: TelnyxCallEvent) -> str:
    """
    Map Telnyx call event to equivalent legacy (TwiML) call status.

    This helps with backward compatibility during provider migration.

    Args:
        telnyx_event: A Telnyx call event

    Returns:
        Equivalent legacy call status string
    """
    event_type = telnyx_event.event_type

    mapping = {
        TelnyxEventType.CALL_INITIATED: "initiated",
        TelnyxEventType.CALL_RINGING: "ringing",
        TelnyxEventType.CALL_ANSWERED: "in-progress",
        TelnyxEventType.CALL_HANGUP: "completed",
        TelnyxEventType.CALL_BRIDGED: "in-progress",
    }

    status = mapping.get(event_type, "unknown")

    # Check for specific hangup causes that map to different statuses
    if telnyx_event.is_hangup:
        hangup_cause = telnyx_event.hangup_cause
        if hangup_cause in ["call_rejected", "user_busy"]:
            status = "busy"
        elif hangup_cause in ["originator_cancel", "timeout"]:
            status = "no-answer"
        elif hangup_cause in ["unallocated_number", "invalid_number_format"]:
            status = "failed"

    return status


def map_telnyx_amd_to_legacy(amd_event: TelnyxAMDEvent) -> Dict[str, str]:
    """
    Map Telnyx AMD result to legacy (TwiML-compatible) format.

    Args:
        amd_event: A Telnyx AMD event

    Returns:
        Dict with legacy-compatible AMD fields
    """
    result = amd_event.result

    # Map to legacy AnsweredBy values
    answered_by_map = {
        "human": "human",
        "machine": "machine_end_beep",
        "not_sure": "unknown",
        "unknown": "unknown",
    }

    return {
        "AnsweredBy": answered_by_map.get(result, "unknown"),
        "MachineDetectionDuration": str(amd_event.payload.get("detection_duration_millis", 0)),
    }


# Backward-compatible aliases
map_telnyx_status_to_twilio = map_telnyx_status_to_legacy
map_telnyx_amd_to_twilio = map_telnyx_amd_to_legacy
