"""IVR fallback service — graceful switch from natural language to DTMF when speech fails."""
import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class IVRSession:
    call_id: str
    nl_attempts: int = 0
    last_confidence: float = 1.0
    silence_seconds: float = 0.0
    mode: str = "natural_language"  # natural_language or dtmf


DTMF_MENU = {
    "1": {"label": "I'm looking to purchase a home", "route": "purchase_qualification"},
    "2": {"label": "I want to refinance my current mortgage", "route": "refi_qualification"},
    "3": {"label": "I have a question about my existing loan", "route": "servicing"},
    "4": {"label": "I need to speak with my loan officer", "route": "lo_transfer"},
    "5": {"label": "I'd like to schedule an appointment", "route": "scheduling"},
    "0": {"label": "Speak with a representative", "route": "operator"},
}

# Thresholds for switching to DTMF
MAX_NL_FAILURES = 2
MIN_CONFIDENCE = 0.3
MAX_SILENCE_SECONDS = 10.0


class IVRFallbackService:
    """Manages fallback from natural language IVR to DTMF."""

    def __init__(self):
        self._sessions: Dict[str, IVRSession] = {}

    def get_or_create_session(self, call_id: str) -> IVRSession:
        if call_id not in self._sessions:
            self._sessions[call_id] = IVRSession(call_id=call_id)
        return self._sessions[call_id]

    def record_nl_failure(self, call_id: str, confidence: float = 0.0,
                          silence_seconds: float = 0.0):
        """Record a natural language processing failure."""
        session = self.get_or_create_session(call_id)
        session.nl_attempts += 1
        session.last_confidence = confidence
        session.silence_seconds = silence_seconds

    def should_fallback(self, call_id: str) -> bool:
        """Determine if we should switch from NL to DTMF."""
        session = self.get_or_create_session(call_id)

        if session.mode == "dtmf":
            return True
        if session.nl_attempts >= MAX_NL_FAILURES:
            logger.info(f"Call {call_id}: Switching to DTMF after {session.nl_attempts} NL failures")
            return True
        if session.last_confidence < MIN_CONFIDENCE and session.nl_attempts >= 1:
            logger.info(f"Call {call_id}: Low confidence ({session.last_confidence}), switching to DTMF")
            return True
        if session.silence_seconds > MAX_SILENCE_SECONDS:
            logger.info(f"Call {call_id}: {session.silence_seconds}s silence, switching to DTMF")
            return True
        return False

    def activate_dtmf(self, call_id: str):
        """Switch session to DTMF mode."""
        session = self.get_or_create_session(call_id)
        session.mode = "dtmf"

    def build_fallback_prompt(self) -> str:
        """Generate TTS-friendly DTMF menu prompt."""
        lines = ["I'm sorry, I'm having trouble understanding. Let me give you some options."]
        for digit, option in sorted(DTMF_MENU.items()):
            if digit == "0":
                continue
            lines.append(f"Press {digit} for: {option['label']}.")
        lines.append("Or press 0 to speak with a representative.")
        return " ".join(lines)

    def handle_dtmf_input(self, digit: str) -> Dict:
        """Route based on DTMF digit pressed."""
        option = DTMF_MENU.get(digit)
        if not option:
            return {
                "valid": False,
                "message": "I didn't recognize that option. Please try again.",
                "retry": True,
            }
        return {
            "valid": True,
            "label": option["label"],
            "route": option["route"],
            "message": f"Great, I'll connect you for: {option['label']}.",
        }

    def cleanup_session(self, call_id: str):
        """Clean up session after call ends."""
        self._sessions.pop(call_id, None)


_service = None


def get_ivr_fallback_service() -> IVRFallbackService:
    global _service
    if _service is None:
        _service = IVRFallbackService()
    return _service
