"""
Perennia AI — URLA Transcript PII Scrubber
==========================================
Two-layer scrubbing for SSN, DOB, and account numbers in voice transcripts.

Layer 1 (real-time): Called on every transcription segment as it arrives.
    Fast, pattern-based. Replaces obvious PII with redaction tokens.

Layer 2 (post-call): Called once after the session ends or at section
    transitions. More aggressive — contextual patterns that are too expensive
    or false-positive-prone for real-time use.

Scope is intentionally narrow: SSN, DOB, and financial account numbers.
Driver's license, passport, credit card numbers are NOT collected by the
URLA agent and are out of scope (per Block 2 design decision).
"""
from __future__ import annotations

import re
from typing import List, Optional

from .models import CallTranscriptEntry


# ── SSN patterns ─────────────────────────────────────────────────────

# Full SSN: 123-45-6789, 123 45 6789 (requires at least one separator
# to avoid matching ZIP+4, dollar amounts, and other 9-digit sequences)
_SSN_FULL = re.compile(
    r"(?<!\$)(?<!\d)\b(\d{3})[\s\-](\d{2})[\s\-](\d{4})\b(?!\d)"
)

# Spoken SSN: "one two three, four five, six seven eight nine" etc.
# Tolerates filler words (uh, um, and, like), punctuation, and pauses between digits
_DIGIT_WORD = r"(?:zero|one|two|three|four|five|six|seven|eight|nine)"
_SEP = r"(?:[\s,\-]+(?:(?:uh|um|and|like|pause)\s+)*)"
_SSN_SPOKEN_DIGITS = re.compile(
    rf"(?:{_DIGIT_WORD}{_SEP}){{8,9}}{_DIGIT_WORD}",
    re.IGNORECASE,
)

# Partial SSN in mid-stream: "my social is" followed by digits
_SSN_CONTEXT = re.compile(
    r"(?:social(?:\s+security)?(?:\s+number)?|s\s*s\s*n)\s+(?:is\s+)?(\d[\d\s\-]{6,10}\d)",
    re.IGNORECASE,
)

_SSN_REDACTED = "[SSN REDACTED]"


# ── DOB patterns ─────────────────────────────────────────────────────

# Numeric DOB: 01/15/1990, 1-15-1990, 01.15.1990
_DOB_NUMERIC = re.compile(
    r"\b(0?[1-9]|1[0-2])[\s/\-\.](0?[1-9]|[12]\d|3[01])[\s/\-\.](\d{4}|\d{2})\b"
)

# Contextual DOB: "born on", "date of birth is", "birthday is" followed by a date
_DOB_CONTEXT = re.compile(
    r"(?:born\s+(?:on\s+)?|date\s+of\s+birth\s+(?:is\s+)?|birthday\s+(?:is\s+)?|d\s*o\s*b\s+(?:is\s+)?)"
    r"([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{2,4}|\d{1,2}[\s/\-\.]\d{1,2}[\s/\-\.]\d{2,4})",
    re.IGNORECASE,
)

_DOB_REDACTED = "[DOB REDACTED]"


# ── Account number patterns ──────────────────────────────────────────

# Bank account numbers: typically 8-17 digits, often preceded by context
_ACCOUNT_CONTEXT = re.compile(
    r"(?:account\s+(?:number\s+)?(?:is\s+)?|routing\s+(?:number\s+)?(?:is\s+)?)"
    r"(\d[\d\s\-]{6,16}\d)",
    re.IGNORECASE,
)

# Bare long digit sequences (10+ digits) that look like account numbers
_LONG_DIGITS = re.compile(r"\b\d{10,17}\b")

_ACCOUNT_REDACTED = "[ACCOUNT REDACTED]"


# ── Layer 1: Real-time scrubber ──────────────────────────────────────

def scrub_realtime(text: str) -> str:
    """
    Fast pattern-based scrub for a single transcript segment.
    Called on every incoming STT segment before persistence.
    """
    # SSN — full numeric
    result = _SSN_FULL.sub(_SSN_REDACTED, text)

    # SSN — spoken digits ("one two three four five six seven eight nine")
    result = _SSN_SPOKEN_DIGITS.sub(_SSN_REDACTED, result)

    # SSN — contextual ("my social is 123 45 6789")
    result = _SSN_CONTEXT.sub(_SSN_REDACTED, result)

    # DOB numeric omitted from Layer 1 — too many false positives on
    # addresses and dollar amounts. Caught by Layer 2 post-call scrub.

    return result


# ── Layer 2: Post-call aggressive scrub ──────────────────────────────

# Sections where sensitive PII is expected
_PII_SENSITIVE_SECTIONS = {"SECTION_1A", "SECTION_2"}


def scrub_post_call(
    transcript: List[CallTranscriptEntry],
    current_section: Optional[str] = None,
) -> List[CallTranscriptEntry]:
    """
    Aggressive post-call scrub pass over the full transcript.

    Applies all Layer 1 patterns plus contextual patterns that are
    too false-positive-prone for real-time (DOB context, account context,
    bare long digit sequences in sensitive sections).
    """
    for entry in transcript:
        text = entry.text

        # Layer 1 patterns first
        text = scrub_realtime(text)

        # Numeric DOB (MM/DD/YYYY, MM-DD-YYYY) — too false-positive-prone
        # for Layer 1, but safe in the post-call pass
        text = _DOB_NUMERIC.sub(_DOB_REDACTED, text)

        # Contextual DOB ("born on January 15th, 1990")
        text = _DOB_CONTEXT.sub(_DOB_REDACTED, text)

        # Account numbers with context
        text = _ACCOUNT_CONTEXT.sub(_ACCOUNT_REDACTED, text)

        # Bare long digit sequences — only in PII-sensitive sections
        # to avoid false positives on addresses, loan amounts, etc.
        if current_section in _PII_SENSITIVE_SECTIONS:
            text = _LONG_DIGITS.sub(_ACCOUNT_REDACTED, text)

        entry.text = text

    return transcript
