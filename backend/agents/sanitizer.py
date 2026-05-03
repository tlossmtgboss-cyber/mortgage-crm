"""
Input sanitization for LLM context injection.

Prevents prompt injection attacks via tool output data (gathered_data),
memory context, active entity data, and user messages before they reach
the LLM system prompt boundary.
"""

import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts|context)", re.I),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"(system|admin|assistant)\s*:\s*", re.I),
    re.compile(r"\[(SYSTEM|INST|ADMIN)\]", re.I),
    re.compile(r"<\s*/?\s*(system|s|instruction)\s*>", re.I),
    re.compile(r"new\s+instructions?\s*:", re.I),
    re.compile(r"override\s+(all\s+)?rules", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"forget\s+(everything|all|your)\b", re.I),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\b", re.I),
    re.compile(r"act\s+as\s+if\b", re.I),
    re.compile(r"your\s+new\s+role\s+is\b", re.I),
    re.compile(r"respond\s+only\s+to\s+the\s+following\b", re.I),
    re.compile(r"(do\s+not|don'?t)\s+follow\s+(your|the|any)\s+(rules|instructions|guidelines)", re.I),
    re.compile(r"\bDAN\b.*\bjailbreak", re.I),
    re.compile(r"developer\s+mode\s+(enabled|on|activated)", re.I),
]

_ZERO_WIDTH_CHARS = re.compile(
    '[​‌‍‎‏﻿⁠⁡⁢⁣⁤­͏᠎؜]'
)

_REPLACEMENT = "[FILTERED]"
_MAX_VALUE_LENGTH = 5000


def _normalize(text: str) -> str:
    """Normalize Unicode to catch homoglyph and zero-width bypasses."""
    text = _ZERO_WIDTH_CHARS.sub(' ', text)
    return unicodedata.normalize('NFKD', text)


def sanitize_for_llm(data: Any, _depth: int = 0) -> Any:
    """Recursively sanitize data values before LLM context injection.

    Normalizes Unicode (NFKD), strips zero-width characters, neutralizes
    prompt injection patterns, and truncates excessively long values.
    Logs when injection patterns are detected.
    """
    if _depth > 10:
        return str(data)[:200] if data else data

    if isinstance(data, str):
        result = _normalize(data)
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(result):
                result = pattern.sub(_REPLACEMENT, result)
                logger.warning(f"[SANITIZER] Prompt injection pattern detected and filtered: {pattern.pattern[:60]}")
        if len(result) > _MAX_VALUE_LENGTH:
            result = result[:_MAX_VALUE_LENGTH] + "...[truncated]"
        return result

    if isinstance(data, dict):
        return {k: sanitize_for_llm(v, _depth + 1) for k, v in data.items()}

    if isinstance(data, (list, tuple)):
        return [sanitize_for_llm(item, _depth + 1) for item in data]

    return data


def strip_boundary_markers(text: str) -> str:
    """Strip LLM boundary markers from user input to prevent marker injection."""
    return (text
            .replace("[USER_INPUT_START]", "")
            .replace("[USER_INPUT_END]", "")
            .replace("[SYSTEM]", "")
            .replace("[/SYSTEM]", "")
            .replace("[INST]", "")
            .replace("[/INST]", ""))
