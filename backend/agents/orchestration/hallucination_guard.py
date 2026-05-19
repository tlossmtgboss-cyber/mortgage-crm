"""
Hallucination Guard — Lightweight Grounding Check

This is a CONSERVATIVE, regex-based grounding check for AI agent responses.
It is NOT a replacement for proper RAG-with-citations or a tool-call-grounded
output policy — it simply raises a flag when the response contains specific
numeric claims (currency, percentages, dates) that do not appear to be
supported by the data the agent had access to (`context_data`).

Approach:
    1. Extract numeric claims from response_text via regex:
         - currency       e.g. "$1,234.56", "$500k"
         - percentages    e.g. "6.5%", "30%"
         - dates          e.g. "2026-05-19", "May 19, 2026", "5/19/2026"
    2. Recursively walk context_data (dict/list/scalars) and collect every
       string/number value.
    3. For each claim, look for a token-level / substring match in the
       collected context values.  Normalize whitespace and casing.
    4. confidence = verified_count / total_claims (1.0 if no claims).

Limitations:
    - Will not catch fabricated qualitative statements ("approved by the
      underwriter") — only numeric/date claims are checked.
    - Pure substring match → "5%" inside "15%" counts as a match.  Acceptable
      trade-off for a flagging-only guardrail.
    - Date parsing is regex-based; relies on format overlap rather than
      semantic equality.

Use the result to (a) tag the response for human review, (b) lower trust
score in agent telemetry, or (c) route to a stricter LLM grounding check.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------- claim extraction patterns -----------------------------------

_CURRENCY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kKmMbB]?")
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")
_DATE_ISO_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_DATE_SLASH_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_DATE_LONG_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    re.IGNORECASE,
)


def _normalize(s: Any) -> str:
    return re.sub(r"\s+", "", str(s)).lower()


def _collect_context_values(node: Any, sink: Set[str], depth: int = 0) -> None:
    """Recursively flatten context_data into a set of normalized string values."""
    if depth > 12:  # safety guard against pathological nesting
        return
    if node is None:
        return
    if isinstance(node, (str, int, float, bool)):
        sink.add(_normalize(node))
        return
    if isinstance(node, dict):
        for v in node.values():
            _collect_context_values(v, sink, depth + 1)
        return
    if isinstance(node, (list, tuple, set)):
        for v in node:
            _collect_context_values(v, sink, depth + 1)
        return
    # fallback: stringify
    try:
        sink.add(_normalize(repr(node)))
    except Exception:
        pass


def _extract_claims(text: str) -> List[str]:
    claims: List[str] = []
    for rx in (_CURRENCY_RE, _PERCENT_RE, _DATE_ISO_RE, _DATE_SLASH_RE, _DATE_LONG_RE):
        claims.extend(rx.findall(text))
    # de-dup while preserving order
    seen: Set[str] = set()
    out: List[str] = []
    for c in claims:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


class HallucinationGuard:
    """Conservative numeric/date grounding check for agent responses."""

    def verify_claims(self, response_text: str, context_data: Optional[Dict]) -> Dict:
        """
        Check every numeric/date claim in `response_text` against `context_data`.

        Returns:
            {
                "verified":           bool,           # True if every claim was found
                "unverified_claims":  list[str],      # claims with no support
                "confidence":         float,          # verified / total (1.0 if zero claims)
            }
        """
        if not response_text or not isinstance(response_text, str):
            return {"verified": True, "unverified_claims": [], "confidence": 1.0}

        claims = _extract_claims(response_text)
        if not claims:
            return {"verified": True, "unverified_claims": [], "confidence": 1.0}

        context_values: Set[str] = set()
        if context_data is not None:
            _collect_context_values(context_data, context_values)

        unverified: List[str] = []
        verified_count = 0
        for claim in claims:
            norm = _normalize(claim)
            # consider a claim verified if its normalized form appears in any
            # normalized context value (substring match)
            found = False
            for cv in context_values:
                if norm and norm in cv:
                    found = True
                    break
            if found:
                verified_count += 1
            else:
                unverified.append(claim)

        total = len(claims)
        confidence = (verified_count / total) if total else 1.0
        return {
            "verified": len(unverified) == 0,
            "unverified_claims": unverified,
            "confidence": round(confidence, 4),
        }


# Module-level singleton
hallucination_guard = HallucinationGuard()
