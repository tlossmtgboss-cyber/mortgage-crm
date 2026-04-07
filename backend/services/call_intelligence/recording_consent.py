"""
Recording Consent Auto-Detection

Auto-detects whether a call requires two-party consent based on
the borrower's state. Defaults to two-party (safest option).

Two-party consent states (as of 2026):
CA, CT, DE, FL, IL, MD, MA, MT, NV, NH, PA, WA

Integration points:
    - ComplianceMonitorCallAgent: State-aware live recording consent checks
    - PostCallAutomationService: Post-call recording consent compliance audit
    - state_recording_rules_routes.py: DB-backed override (admin-configurable)
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# States requiring all-party (two-party) consent for recording.
# Source: RCFP reporter's recording guide, current as of 2026.
TWO_PARTY_STATES = {
    "CA", "CT", "DE", "FL", "IL", "MD", "MA", "MT", "NV", "NH", "PA", "WA",
}

# Phrases that indicate the LO announced recording consent.
# Checked against the first ~2 minutes of transcript.
_DISCLOSURE_PATTERNS = [
    re.compile(
        r"this\s+call\s+(?:is\s+being\s+|may\s+be\s+|will\s+be\s+)?(?:recorded|monitored)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:recording|monitor(?:ing)?)\s+this\s+(?:call|conversation)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:consent|agree)\s+to\s+(?:be(?:ing)?\s+)?record",
        re.IGNORECASE,
    ),
    re.compile(
        r"for\s+quality\s+(?:and\s+(?:training|compliance)\s+)?purposes",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:being\s+recorded|call\s+is\s+recorded)",
        re.IGNORECASE,
    ),
]

# Default disclosure text for two-party states
_DEFAULT_DISCLOSURE = (
    "This call may be recorded for quality assurance and compliance purposes. "
    "By continuing this call, you consent to being recorded."
)


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def requires_two_party_consent(state_code: Optional[str]) -> bool:
    """Check if a state requires two-party recording consent.

    Args:
        state_code: Two-letter US state code, or None.

    Returns:
        True if two-party consent is required, or if state is unknown
        (defaults to safest option).
    """
    if not state_code:
        return True  # Default to safest option
    return state_code.upper().strip() in TWO_PARTY_STATES


def get_recording_disclosure(state_code: Optional[str]) -> str:
    """Get the recording disclosure text for a state.

    Args:
        state_code: Two-letter US state code, or None.

    Returns:
        Disclosure text if two-party consent is needed, empty string otherwise.
    """
    if requires_two_party_consent(state_code):
        return _DEFAULT_DISCLOSURE
    return ""  # One-party state: caller is the consenting party


def detect_disclosure_in_transcript(
    transcript: str,
    max_seconds: float = 120.0,
    segments: Optional[List[dict]] = None,
) -> dict:
    """Scan a transcript for recording disclosure phrases.

    If ``segments`` are provided (list of dicts with ``text``, ``timestamp``,
    and optionally ``speaker``), only segments within the first
    ``max_seconds`` are searched and the match timestamp is returned.

    If only a plain ``transcript`` string is provided, a heuristic is used:
    the first ~20% of the text is treated as roughly the first 2 minutes.

    Args:
        transcript: Full call transcript text.
        max_seconds: Only consider the first N seconds of the call.
        segments: Optional speaker-attributed segments with timestamps.

    Returns:
        Dict with keys:
            - detected (bool): Whether a disclosure phrase was found.
            - phrase_matched (str | None): The matched text.
            - detected_at_seconds (float | None): Timestamp if available.
            - search_method (str): "segments" or "heuristic".
    """
    result = {
        "detected": False,
        "phrase_matched": None,
        "detected_at_seconds": None,
        "search_method": "heuristic",
    }

    # Prefer structured segments if available
    if segments:
        result["search_method"] = "segments"
        for seg in segments:
            ts = seg.get("timestamp", seg.get("elapsed_seconds", 0.0))
            if ts > max_seconds:
                break
            text = seg.get("text", "")
            for pattern in _DISCLOSURE_PATTERNS:
                match = pattern.search(text)
                if match:
                    result["detected"] = True
                    result["phrase_matched"] = match.group(0)
                    result["detected_at_seconds"] = ts
                    return result
        return result

    # Heuristic: scan first ~20% of transcript (roughly first 2 min of a
    # 10-minute call)
    if not transcript:
        return result

    scan_length = max(500, len(transcript) // 5)
    early_text = transcript[:scan_length]

    for pattern in _DISCLOSURE_PATTERNS:
        match = pattern.search(early_text)
        if match:
            result["detected"] = True
            result["phrase_matched"] = match.group(0)
            return result

    return result


def check_call_compliance(
    lead_state: Optional[str],
    recording_announced: bool,
) -> dict:
    """Check if a recorded call meets state consent requirements.

    Args:
        lead_state: Borrower's two-letter state code, or None.
        recording_announced: Whether the LO announced recording.

    Returns:
        Dict with compliance assessment:
            - state: The state code checked.
            - two_party_required: Whether two-party consent is needed.
            - recording_announced: Echo of the input flag.
            - compliant: True if the call meets requirements.
            - risk_level: "none", "medium", or "high".
            - recommendation: Actionable text if non-compliant, else None.
    """
    needs_consent = requires_two_party_consent(lead_state)
    compliant = not needs_consent or recording_announced

    if compliant:
        risk_level = "none"
        recommendation = None
    elif lead_state:
        risk_level = "high"
        recommendation = (
            f"Recording consent was not announced in two-party state "
            f"({lead_state.upper()}). This recording may not be legally usable."
        )
    else:
        # State unknown and no disclosure detected
        risk_level = "medium"
        recommendation = (
            "Borrower state is unknown and recording consent was not announced. "
            "Defaulting to two-party requirement. Verify state and re-assess."
        )

    return {
        "state": lead_state,
        "two_party_required": needs_consent,
        "recording_announced": recording_announced,
        "compliant": compliant,
        "risk_level": risk_level,
        "recommendation": recommendation,
    }


def assess_recording_compliance(
    transcript: str,
    lead_state: Optional[str] = None,
    segments: Optional[List[dict]] = None,
) -> dict:
    """Full recording consent compliance assessment for a completed call.

    Combines transcript scanning with state-based consent rules. This is the
    main entry point for post-call compliance checks.

    Args:
        transcript: Full call transcript.
        lead_state: Borrower's two-letter state code.
        segments: Optional structured transcript segments.

    Returns:
        Combined dict with disclosure detection and compliance assessment.
    """
    disclosure = detect_disclosure_in_transcript(
        transcript=transcript,
        segments=segments,
    )
    compliance = check_call_compliance(
        lead_state=lead_state,
        recording_announced=disclosure["detected"],
    )

    return {
        "disclosure_detection": disclosure,
        "compliance": compliance,
    }
