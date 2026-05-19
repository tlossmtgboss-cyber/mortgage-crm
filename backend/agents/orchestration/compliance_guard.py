"""
Compliance Guard — Pre-Response Regulatory Scanner

Scans outbound AI agent responses for red flags under:

- TRID  (Truth in Lending / RESPA Integrated Disclosure) — APR / closing date promises
- RESPA (Real Estate Settlement Procedures Act) — settlement service kickbacks language
- ECOA  (Equal Credit Opportunity Act) — prohibited basis (race, age, sex, marital, religion, national origin)
- TCPA  (Telephone Consumer Protection Act) — consent / opt-out red flags
- FDCPA (Fair Debt Collection Practices Act) — abusive / threat language

Two severity tiers:

- HARD BLOCK   -> passed=False, escalation_required=True
                  (caller must NOT send the response; must escalate to a human)
- SOFT WARN    -> passed=True,  escalation_required=False
                  (response can be sent, but the violation is recorded for review)

Implementation: simple regex / keyword matching only. No LLM call. This is
intentionally cheap and synchronous so it can run on every agent response
without latency cost. False positives are acceptable; false negatives are not
(for the hard-block tier).

For a richer, semantic compliance review, layer an LLM-based reviewer
on top of this guard's findings (e.g., when escalation_required=True).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Pattern

logger = logging.getLogger(__name__)


# ---------- HARD-BLOCK patterns -----------------------------------------

_HARD_BLOCK_PATTERNS: List[tuple[str, str, Pattern[str]]] = [
    # Promises of approval
    ("TRID/UDAAP", "guaranteed_approval",
     re.compile(r"\b(guarantee[ds]?\s+approval|definite(ly)?\s+approv(ed|al)|you('?re|\s+are)\s+approved|pre[-\s]?approved\s+guaranteed)\b", re.IGNORECASE)),
    ("TRID/UDAAP", "promise_of_terms",
     re.compile(r"\b(promise|guarantee[ds]?)\s+(you|to)\s+(the\s+)?(rate|loan|funding|approval|closing)\b", re.IGNORECASE)),

    # APR mentioned without subject-to-credit-approval qualifier
    # (caller checks both: APR present AND disclosure absent)
    # Handled separately below in validate_response()

    # ECOA prohibited basis used as reasoning
    ("ECOA", "prohibited_basis",
     re.compile(r"\bbecause\s+(you'?re|you\s+are|of\s+your)\s+(black|white|asian|hispanic|latino|african[\s-]american|"
                r"male|female|man|woman|old|young|elderly|"
                r"married|single|divorced|widowed|"
                r"christian|muslim|jewish|hindu|buddhist|catholic|"
                r"pregnant|disabled|foreign|immigrant)\b", re.IGNORECASE)),

    # FDCPA-style threats / abuse
    ("FDCPA", "threat_or_abuse",
     re.compile(r"\b(we will (sue|arrest|jail|garnish)|you will be (arrested|jailed|sued)|"
                r"call (your|the) (employer|family|neighbors)|we'll ruin your (credit|life))\b", re.IGNORECASE)),

    # RESPA — kickback / referral fee language
    ("RESPA", "kickback_language",
     re.compile(r"\b(kickback|referral\s+fee\s+for\s+sending|i'?ll\s+pay\s+you\s+to\s+refer)\b", re.IGNORECASE)),
]

# Specific APR detection (e.g. "APR of 6.5%" or "6.5% APR")
_APR_NUMERIC = re.compile(
    r"(APR\s+of\s+\d+(\.\d+)?\s*%|\d+(\.\d+)?\s*%\s*APR)",
    re.IGNORECASE,
)
_APR_DISCLOSURE = re.compile(
    r"(subject\s+to\s+credit\s+approval|rates?\s+may\s+change|not\s+a\s+commitment\s+to\s+lend|"
    r"actual\s+rate\s+may\s+vary|preliminary\s+(estimate|quote))",
    re.IGNORECASE,
)

# TCPA — auto-call / SMS without consent indicator
_TCPA_AUTOCALL = re.compile(
    r"\b(we'?ll?\s+(auto[-\s]?dial|robocall|text\s+you\s+(daily|automatically)))\b",
    re.IGNORECASE,
)

# ---------- SOFT WARN patterns ------------------------------------------

_SOFT_WARN_PATTERNS: List[tuple[str, str, Pattern[str]]] = [
    ("TRID", "best_rate_no_disclaimer",
     re.compile(r"\b(best|lowest|cheapest|unbeatable)\s+(rate|interest\s+rate|pricing)\b", re.IGNORECASE)),
    ("TRID", "closing_date_promise",
     re.compile(r"\b(will\s+close\s+(on|by)\s+\w+\s+\d|guarantee[d]?\s+closing\s+date|definitely\s+closing)\b", re.IGNORECASE)),
]

# Comparative disclaimer that neutralizes "best rate" warning
_COMPARATIVE_DISCLAIMER = re.compile(
    r"(among\s+lenders\s+we\s+surveyed|compared\s+to|based\s+on\s+(current|today'?s)\s+market|"
    r"rates?\s+vary|individual\s+rates?\s+may\s+differ)",
    re.IGNORECASE,
)

# Contingency language that neutralizes "closing date promise"
_CONTINGENCY_LANGUAGE = re.compile(
    r"(subject\s+to|contingent\s+(on|upon)|provided\s+that|barring\s+unforeseen|"
    r"assuming\s+all\s+conditions|target\s+closing)",
    re.IGNORECASE,
)


class ComplianceGuard:
    """
    Pre-response regulatory scanner. See module docstring for tier definitions.
    """

    def validate_response(self, text: str, agent_role: str, agent_id: Optional[str] = None) -> Dict:
        """
        Scan `text` for compliance red flags.

        Returns:
            {
                "passed":               bool,   # False if any hard-block matched
                "violations":           list,   # each item: {regulation, rule, severity, snippet}
                "escalation_required":  bool,   # True iff any hard-block matched
            }

        Side-effect: emits the result to the in-process ``governance_metrics``
        store for the per-agent governance dashboard. The metrics call is
        wrapped in try/except so a telemetry failure NEVER raises into the
        caller's response path.
        """
        if not text or not isinstance(text, str):
            result = {"passed": True, "violations": [], "escalation_required": False}
            self._emit_metrics(agent_id, agent_role, result)
            return result

        violations: List[Dict] = []
        escalation_required = False
        passed = True

        # Hard-block scan
        for reg, rule, pattern in _HARD_BLOCK_PATTERNS:
            m = pattern.search(text)
            if m:
                violations.append({
                    "regulation": reg,
                    "rule": rule,
                    "severity": "hard_block",
                    "snippet": m.group(0)[:200],
                    "agent_role": agent_role,
                })
                passed = False
                escalation_required = True

        # APR without disclosure — special composite check
        apr_match = _APR_NUMERIC.search(text)
        if apr_match and not _APR_DISCLOSURE.search(text):
            violations.append({
                "regulation": "TRID",
                "rule": "apr_without_disclosure",
                "severity": "hard_block",
                "snippet": apr_match.group(0)[:200],
                "agent_role": agent_role,
            })
            passed = False
            escalation_required = True

        # TCPA — auto-call without consent statement (treat as hard-block)
        tcpa_match = _TCPA_AUTOCALL.search(text)
        if tcpa_match:
            violations.append({
                "regulation": "TCPA",
                "rule": "autocall_without_consent",
                "severity": "hard_block",
                "snippet": tcpa_match.group(0)[:200],
                "agent_role": agent_role,
            })
            passed = False
            escalation_required = True

        # Soft-warn scan
        for reg, rule, pattern in _SOFT_WARN_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            if rule == "best_rate_no_disclaimer" and _COMPARATIVE_DISCLAIMER.search(text):
                continue
            if rule == "closing_date_promise" and _CONTINGENCY_LANGUAGE.search(text):
                continue
            violations.append({
                "regulation": reg,
                "rule": rule,
                "severity": "warn",
                "snippet": m.group(0)[:200],
                "agent_role": agent_role,
            })

        result = {
            "passed": passed,
            "violations": violations,
            "escalation_required": escalation_required,
        }
        self._emit_metrics(agent_id, agent_role, result)
        return result

    @staticmethod
    def _emit_metrics(agent_id: Optional[str], agent_role: str, result: Dict) -> None:
        """
        Forward a validate_response result to ``governance_metrics``.

        Lazy-import + try/except so a metrics failure never leaks into the
        caller's response path.
        """
        try:
            from agents.orchestration.governance_metrics import governance_metrics
            governance_metrics.record_compliance_event(
                agent_id=agent_id or agent_role or "unknown",
                agent_role=agent_role or "unknown",
                violation_count=len(result.get("violations", []) or []),
                violations=result.get("violations", []) or [],
                escalated=bool(result.get("escalation_required", False)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("compliance_guard metrics emit swallowed: %s", exc)


# Module-level singleton
compliance_guard = ComplianceGuard()
