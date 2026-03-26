"""
Voice session telemetry — structured logging for voice session metrics.

Provides a lightweight VoiceSessionTelemetry class that tracks events
during a voice session and emits a structured summary when the session ends.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VoiceSessionTelemetry:
    """Tracks telemetry for a single voice session.

    Usage:
        telemetry = VoiceSessionTelemetry(session_id="abc", user_id=42, org_id=1)
        telemetry.record_event("connected", {"model": "gpt-4o-realtime"})
        telemetry.record_event("transcript", {"text": "hello", "is_final": True})
        telemetry.record_event("action", {"action": "send_sms", "status": "success"})
        telemetry.end_session("user_disconnect")
    """

    def __init__(
        self,
        session_id: str,
        user_id: Optional[int] = None,
        org_id: Optional[int] = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.org_id = org_id
        self.start_time = time.monotonic()
        self.start_timestamp = time.time()
        self.events: List[Dict[str, Any]] = []
        self._ended = False

    def record_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record a timestamped event during the session.

        Args:
            event_type: Short identifier for the event (e.g. "connected",
                        "transcript", "action", "error").
            data: Optional dict with event-specific payload.
        """
        self.events.append({
            "event_type": event_type,
            "timestamp": time.time(),
            "elapsed_seconds": round(time.monotonic() - self.start_time, 3),
            "data": data or {},
        })

    def end_session(self, reason: str = "normal") -> Dict[str, Any]:
        """End the session, calculate duration, and log a structured summary.

        Args:
            reason: Why the session ended (e.g. "user_disconnect", "error",
                    "timeout", "normal").

        Returns:
            The summary dict that was logged.
        """
        if self._ended:
            return self.to_dict()

        self._ended = True
        duration = round(time.monotonic() - self.start_time, 3)

        summary = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "start_timestamp": self.start_timestamp,
            "duration_seconds": duration,
            "end_reason": reason,
            "event_count": len(self.events),
            "event_types": self._event_type_counts(),
        }

        logger.info(
            "Voice session ended: session_id=%s user_id=%s duration=%.1fs events=%d reason=%s",
            self.session_id,
            self.user_id,
            duration,
            len(self.events),
            reason,
            extra={"voice_session_summary": summary},
        )

        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Return full telemetry data as a dict."""
        duration = round(time.monotonic() - self.start_time, 3)
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "start_timestamp": self.start_timestamp,
            "duration_seconds": duration,
            "ended": self._ended,
            "event_count": len(self.events),
            "event_types": self._event_type_counts(),
            "events": self.events,
        }

    def _event_type_counts(self) -> Dict[str, int]:
        """Count events by type."""
        counts: Dict[str, int] = {}
        for event in self.events:
            et = event["event_type"]
            counts[et] = counts.get(et, 0) + 1
        return counts
