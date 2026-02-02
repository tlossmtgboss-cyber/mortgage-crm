"""
Shared Regex Patterns for Extraction Agents

This module centralizes commonly used regex patterns to:
1. Avoid duplication across agents
2. Ensure consistency in extraction logic
3. Make pattern updates easier to maintain
"""

import re
from typing import List, Tuple

# =============================================================================
# CITIZENSHIP PATTERNS
# =============================================================================

# US Citizen detection patterns
US_CITIZEN_PATTERNS: List[str] = [
    r"\b(?:us|u\.s\.|american|united states)\s*citizen\b",
    r"\bborn (?:in|here in) (?:the\s+)?(?:us|u\.s\.|united states|america)\b",
    r"(?:i am|i'm|yes,?\s+i'm).*?(?:us|u\.s\.|american|united states)\s*citizen",
    r"(?:citizen|citizenship).*?(?:yes|us|u\.s\.|united states)",
]

# Pre-compiled for performance
US_CITIZEN_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in US_CITIZEN_PATTERNS]

# Permanent Resident detection patterns
PERMANENT_RESIDENT_PATTERNS: List[str] = [
    r"\b(?:permanent resident|green card|legal permanent resident|lpr)\b",
    r"(?:i have|i've got).*?green card",
    r"\blegal resident\b",
]

PERMANENT_RESIDENT_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in PERMANENT_RESIDENT_PATTERNS]

# Non-Permanent Resident (visa holders) patterns
NON_PERMANENT_RESIDENT_PATTERNS: List[str] = [
    r"\b(?:visa|work permit|h1b|h-1b|l1|l-1|ead|opt|f1|f-1|j1|j-1)\b",
    r"\b(?:work authorization|employment authorization)\b",
]

NON_PERMANENT_RESIDENT_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in NON_PERMANENT_RESIDENT_PATTERNS]


# =============================================================================
# MARITAL STATUS PATTERNS
# =============================================================================

MARITAL_STATUS_PATTERNS = {
    "MARRIED": [
        re.compile(r"\b(?:married|spouse|wife|husband)\b", re.IGNORECASE),
    ],
    "SINGLE": [
        re.compile(r"\b(?:single|unmarried|not married|never married)\b", re.IGNORECASE),
    ],
    "DIVORCED": [
        re.compile(r"\b(?:divorced|ex-wife|ex-husband|ex-spouse)\b", re.IGNORECASE),
    ],
    "SEPARATED": [
        re.compile(r"\bseparated\b", re.IGNORECASE),
    ],
    "WIDOWED": [
        re.compile(r"\b(?:widowed|widow|widower)\b", re.IGNORECASE),
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def match_citizenship(text: str) -> Tuple[str, float]:
    """
    Match citizenship status from text.

    Args:
        text: Text to search for citizenship indicators

    Returns:
        Tuple of (status, confidence) where status is one of:
        - "US_CITIZEN"
        - "PERMANENT_RESIDENT"
        - "NON_PERMANENT_RESIDENT"
        - None if no match
    """
    # Check US Citizen first (highest priority)
    for pattern in US_CITIZEN_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("US_CITIZEN", 85.0)

    # Check Permanent Resident
    for pattern in PERMANENT_RESIDENT_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("PERMANENT_RESIDENT", 80.0)

    # Check Non-Permanent Resident
    for pattern in NON_PERMANENT_RESIDENT_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("NON_PERMANENT_RESIDENT", 75.0)

    return (None, 0.0)


def match_marital_status(text: str) -> Tuple[str, float]:
    """
    Match marital status from text.

    Args:
        text: Text to search for marital status indicators

    Returns:
        Tuple of (status, confidence) where status is one of:
        - "MARRIED", "SINGLE", "DIVORCED", "SEPARATED", "WIDOWED"
        - None if no match
    """
    for status, patterns in MARITAL_STATUS_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                return (status, 75.0)

    return (None, 0.0)
