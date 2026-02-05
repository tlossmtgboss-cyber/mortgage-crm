"""
Shared Regex Patterns for Extraction Agents

This module centralizes commonly used regex patterns to:
1. Avoid duplication across agents
2. Ensure consistency in extraction logic
3. Make pattern updates easier to maintain

Note on confidence scores:
    The helper functions (match_citizenship, match_marital_status) return
    category-based default confidence scores, NOT computed scores based on
    match quality. These scores represent the baseline confidence for each
    category of match:
    - US_CITIZEN: 85.0 (highest - most commonly stated clearly)
    - PERMANENT_RESIDENT: 80.0 (often explicit documentation mention)
    - NON_PERMANENT_RESIDENT: 75.0 (visa types can be ambiguous)
    - MARITAL_STATUS: 75.0 (generally clear statements)
"""

import re
from typing import List, Optional, Tuple


# =============================================================================
# CONFIDENCE SCORE DEFAULTS (Category-based, not computed)
# =============================================================================
# These are default scores for each citizenship/marital category.
# They represent typical confidence levels, not actual match quality.

CITIZENSHIP_CONFIDENCE_US_CITIZEN = 85.0
CITIZENSHIP_CONFIDENCE_PERMANENT_RESIDENT = 80.0
CITIZENSHIP_CONFIDENCE_NON_PERMANENT_RESIDENT = 75.0
MARITAL_STATUS_CONFIDENCE_DEFAULT = 75.0

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

def match_citizenship(text: str) -> Tuple[Optional[str], float]:
    """
    Match citizenship status from text.

    Args:
        text: Text to search for citizenship indicators

    Returns:
        Tuple of (status, category_confidence) where:
        - status: "US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT", or None
        - category_confidence: Default confidence score for the matched category
          (see module docstring for explanation of category-based scoring)
    """
    # Check US Citizen first (highest priority)
    for pattern in US_CITIZEN_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("US_CITIZEN", CITIZENSHIP_CONFIDENCE_US_CITIZEN)

    # Check Permanent Resident
    for pattern in PERMANENT_RESIDENT_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("PERMANENT_RESIDENT", CITIZENSHIP_CONFIDENCE_PERMANENT_RESIDENT)

    # Check Non-Permanent Resident
    for pattern in NON_PERMANENT_RESIDENT_PATTERNS_COMPILED:
        if pattern.search(text):
            return ("NON_PERMANENT_RESIDENT", CITIZENSHIP_CONFIDENCE_NON_PERMANENT_RESIDENT)

    return (None, 0.0)


def match_marital_status(text: str) -> Tuple[Optional[str], float]:
    """
    Match marital status from text.

    Args:
        text: Text to search for marital status indicators

    Returns:
        Tuple of (status, category_confidence) where:
        - status: "MARRIED", "SINGLE", "DIVORCED", "SEPARATED", "WIDOWED", or None
        - category_confidence: Default confidence score for marital status matches
          (see module docstring for explanation of category-based scoring)
    """
    for status, patterns in MARITAL_STATUS_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                return (status, MARITAL_STATUS_CONFIDENCE_DEFAULT)

    return (None, 0.0)
