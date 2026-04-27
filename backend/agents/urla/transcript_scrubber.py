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


# ── Spoken-date DOB patterns (Layer 2 only) ─────────────────────────

_MONTH_NAMES = (
    r"(?:january|february|march|april|may|june|july|august|september|october"
    r"|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
)

_ORDINAL_DAY = (
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth"
    r"|seventeenth|eighteenth|nineteenth|twentieth"
    r"|twenty[\s\-]?first|twenty[\s\-]?second|twenty[\s\-]?third"
    r"|twenty[\s\-]?fourth|twenty[\s\-]?fifth|twenty[\s\-]?sixth"
    r"|twenty[\s\-]?seventh|twenty[\s\-]?eighth|twenty[\s\-]?ninth"
    r"|thirtieth|thirty[\s\-]?first)"
)

_SPOKEN_YEAR = (
    r"(?:(?:nineteen|twenty)\s+(?:oh\s+)?"
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen"
    r"|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy"
    r"|eighty|ninety)"
    r"(?:\s+(?:one|two|three|four|five|six|seven|eight|nine))?)"
)

_DOB_TRIGGER = (
    r"(?:born\s+(?:on\s+)?"
    r"|date\s+of\s+birth\s+(?:is\s+)?"
    r"|birthday\s+(?:is\s+)?"
    r"|d\s*o\s*b\s+(?:is\s+)?)"
)

# Spoken month name + ordinal day + spoken year:
#   "born on June twelfth nineteen eighty-five"
_DOB_SPOKEN_ORDINAL = re.compile(
    rf"{_DOB_TRIGGER}"
    rf"({_MONTH_NAMES}\s+{_ORDINAL_DAY}\s*,?\s*{_SPOKEN_YEAR})",
    re.IGNORECASE,
)

# Spoken numeric month-day-year using word-digits:
#   "birthday is six twelve eighty-five"
_SPOKEN_NUM = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen"
    r"|eighteen|nineteen|twenty|twenty[\s\-]?one|twenty[\s\-]?two"
    r"|twenty[\s\-]?three|twenty[\s\-]?four|twenty[\s\-]?five"
    r"|twenty[\s\-]?six|twenty[\s\-]?seven|twenty[\s\-]?eight"
    r"|twenty[\s\-]?nine|thirty|thirty[\s\-]?one)"
)
_DOB_SPOKEN_NUMERIC = re.compile(
    rf"{_DOB_TRIGGER}"
    rf"({_SPOKEN_NUM}\s+{_SPOKEN_NUM}\s+{_SPOKEN_YEAR})",
    re.IGNORECASE,
)

# Spoken month name + numeric day + numeric/spoken year:
#   "born on June 12th 1985", "d o b is March 3rd nineteen ninety"
_DOB_SPOKEN_MIXED = re.compile(
    rf"{_DOB_TRIGGER}"
    rf"({_MONTH_NAMES}\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s*(?:\d{{2,4}}|{_SPOKEN_YEAR}))",
    re.IGNORECASE,
)


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

# Monetary context preceding a digit sequence — used to prevent false
# positives where a spoken dollar amount (e.g. "property value 1234567890")
# would otherwise be redacted as an account number.
_MONETARY_CONTEXT = re.compile(
    r"(?:\$|dollar|worth|value|balance|amount|price|income|salary|rent|payment)\s*$",
    re.IGNORECASE,
)


def _account_or_skip(match: re.Match) -> str:
    """Replace with redaction token unless preceded by monetary context."""
    start = match.start()
    prefix = match.string[max(0, start - 30):start]
    if _MONETARY_CONTEXT.search(prefix):
        return match.group(0)  # keep original — it's a dollar amount
    return _ACCOUNT_REDACTED


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
_PII_SENSITIVE_SECTIONS = {"SECTION_1A", "SECTION_2", "SECTION_3", "SECTION_4A", "SECTION_4B"}


def scrub_post_call(
    transcript: List[CallTranscriptEntry],
    current_section: Optional[str] = None,
) -> List[CallTranscriptEntry]:
    """
    Aggressive post-call scrub pass over the full transcript.

    Applies all Layer 1 patterns plus contextual patterns that are
    too false-positive-prone for real-time (DOB context, spoken-date DOB,
    account context, bare long digit sequences in sensitive sections).

    NOTE: This function **mutates** ``entry.text`` on each
    :class:`CallTranscriptEntry` in *transcript* in place for efficiency.
    The same list is returned so callers can use it fluently, but the
    original objects are modified.  Pass a deep copy if you need to
    preserve the original transcript.
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

        # Spoken-date DOB — only in Layer 2 (too complex for real-time).
        # Requires DOB context trigger to minimize false positives.
        text = _DOB_SPOKEN_ORDINAL.sub(_DOB_REDACTED, text)
        text = _DOB_SPOKEN_NUMERIC.sub(_DOB_REDACTED, text)
        text = _DOB_SPOKEN_MIXED.sub(_DOB_REDACTED, text)

        # Account numbers with context
        text = _ACCOUNT_CONTEXT.sub(_ACCOUNT_REDACTED, text)

        # Bare long digit sequences — only in PII-sensitive sections
        # to avoid false positives on addresses, loan amounts, etc.
        if current_section in _PII_SENSITIVE_SECTIONS:
            text = _LONG_DIGITS.sub(_account_or_skip, text)

        entry.text = text

    return transcript
