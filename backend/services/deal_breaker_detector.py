"""NLP-based deal breaker detection from call/SMS conversation transcripts."""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class DetectedFlag:
    category: str
    pattern_matched: str
    snippet: str  # surrounding text
    confidence: float  # 0.0 - 1.0
    deal_breaker_name: str


DETECTION_PATTERNS = {
    "credit": {
        "bankruptcy": {
            "patterns": [
                r"\b(bankrupt(?:cy)?|chapter\s*(?:7|13|11)|filed\s+(?:for\s+)?bankruptcy)\b",
            ],
            "deal_breaker_name": "recent_bankruptcy",
            "confidence": 0.85,
        },
        "foreclosure": {
            "patterns": [
                r"\b(foreclos(?:ure|ed)|short\s+sale|deed\s+in\s+lieu)\b",
            ],
            "deal_breaker_name": "recent_foreclosure",
            "confidence": 0.85,
        },
        "collections": {
            "patterns": [
                r"\b(collections?|charge[d\s-]*off|judgment|tax\s+lien)\b",
            ],
            "deal_breaker_name": "collections_issues",
            "confidence": 0.6,
        },
        "low_credit": {
            "patterns": [
                r"\b(bad\s+credit|poor\s+credit|credit\s+(?:is\s+)?(?:very\s+)?(?:low|bad|poor|terrible))\b",
                r"\bcredit\s+(?:score\s+)?(?:is\s+)?(?:around\s+)?[34]\d{2}\b",
            ],
            "deal_breaker_name": "credit_below_minimum",
            "confidence": 0.7,
        },
    },
    "income": {
        "no_income": {
            "patterns": [
                r"\b(no\s+(?:current\s+)?income|unemployed|not\s+(?:currently\s+)?(?:working|employed)|between\s+jobs)\b",
            ],
            "deal_breaker_name": "no_verifiable_income",
            "confidence": 0.75,
        },
        "self_employed_new": {
            "patterns": [
                r"\b(just\s+started\s+(?:my\s+)?(?:own\s+)?business|self[- ]employed\s+(?:for\s+)?(?:less\s+than|under)\s+(?:a\s+year|6\s+months|one\s+year))\b",
            ],
            "deal_breaker_name": "self_employed_under_2yr",
            "confidence": 0.7,
        },
        "cash_income": {
            "patterns": [
                r"\b(paid\s+(?:in\s+)?cash|under\s+the\s+table|cash\s+(?:only\s+)?(?:income|job)|no\s+(?:tax\s+)?(?:returns?|w[- ]?2s?))\b",
            ],
            "deal_breaker_name": "no_verifiable_income",
            "confidence": 0.7,
        },
    },
    "citizenship": {
        "no_ssn": {
            "patterns": [
                r"\b(no\s+(?:social|ssn|social\s+security)|don'?t\s+have\s+(?:a\s+)?(?:social|ssn)|undocumented|no\s+(?:legal\s+)?status|itin\s+only)\b",
            ],
            "deal_breaker_name": "non_resident_alien",
            "confidence": 0.8,
        },
    },
    "property": {
        "mobile_home": {
            "patterns": [
                r"\b(mobile\s+home|manufactured\s+home|trailer|modular\s+(?:home|house))\b",
            ],
            "deal_breaker_name": "manufactured_home_restrictions",
            "confidence": 0.65,
        },
    },
}

# Pre-compile all patterns
_compiled_patterns = {}
for category, subcats in DETECTION_PATTERNS.items():
    for subcat, config in subcats.items():
        _compiled_patterns[(category, subcat)] = {
            "regexes": [re.compile(p, re.IGNORECASE) for p in config["patterns"]],
            "deal_breaker_name": config["deal_breaker_name"],
            "confidence": config["confidence"],
        }


def detect_from_conversation(transcript: str) -> List[DetectedFlag]:
    """Detect deal breaker signals from a conversation transcript."""
    if not transcript:
        return []

    flags = []
    transcript_lower = transcript.lower()

    for (category, subcat), config in _compiled_patterns.items():
        for regex in config["regexes"]:
            for match in regex.finditer(transcript_lower):
                start = max(0, match.start() - 50)
                end = min(len(transcript), match.end() + 50)
                snippet = transcript[start:end].strip()

                flags.append(DetectedFlag(
                    category=category,
                    pattern_matched=match.group(0),
                    snippet=f"...{snippet}...",
                    confidence=config["confidence"],
                    deal_breaker_name=config["deal_breaker_name"],
                ))
                break  # one match per sub-category is enough

    # Deduplicate by deal_breaker_name, keeping highest confidence
    seen = {}
    for flag in flags:
        if flag.deal_breaker_name not in seen or flag.confidence > seen[flag.deal_breaker_name].confidence:
            seen[flag.deal_breaker_name] = flag

    return sorted(seen.values(), key=lambda f: f.confidence, reverse=True)
