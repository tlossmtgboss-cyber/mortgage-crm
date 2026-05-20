"""
UPL (Unauthorized Practice of Law) Rules Engine — Perennia AI

Multi-state rules engine that determines whether a mortgage loan originator
(MLO) action is permitted under the destination state's UPL statutes.
Returns structured restrictions, warnings, and required disclosures.

NOTE: This is a software check, not legal advice. The rules captured here
are conservative best-effort summaries of widely-cited statutes. When in
doubt the engine restricts the action. Consult counsel before deploying
to a new jurisdiction or relying on output for regulatory submissions.

Public surface:

    engine = UPLRulesEngine()
    engine.check("provide_legal_advice", "CA", context={...})
    engine.get_rule_set("NY")
    engine.list_states()

Versioning: every result includes ``state_rules_version`` so downstream
audit logs can pin the policy snapshot used at decision time.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


# ============================================================================
# CONSTANTS
# ============================================================================

STATE_RULES_VERSION = "2026-05-19-v1"

# Canonical action vocabulary the rules engine understands.
SUPPORTED_ACTIONS = (
    "provide_legal_advice",
    "prepare_legal_document",
    "give_tax_advice",
    "discuss_specific_attorney_referral",
    "interpret_contract_terms",
    "provide_disclosure_timing_guidance",
    "discuss_lien_priority",
    "negotiate_payoff_terms",
)

# Conservative default for any state not specifically modeled.
DEFAULT_RESTRICTIONS: List[str] = [
    "no_legal_advice",
    "no_tax_advice",
    "refer_to_attorney_for_interpretation",
]
DEFAULT_REQUIRED_DISCLOSURES: List[str] = ["non_attorney_role"]


def _default_rule(state_abbr: str) -> Dict[str, Any]:
    """Generate a conservative default rule set for an unmodeled state."""
    return {
        "restrictions": list(DEFAULT_RESTRICTIONS),
        "warnings": [
            f"{state_abbr}: state-specific UPL statute not modeled; using "
            "conservative defaults. Verify with state bar before action."
        ],
        "required_disclosures": list(DEFAULT_REQUIRED_DISCLOSURES),
        "regulatory_citations": [
            "Generic UPL prohibition — verify with state attorney general / bar."
        ],
        "last_updated": "2026-05-19",
        "modeled": False,
    }


# ============================================================================
# SPECIFIC STATE RULE SETS (high-touch jurisdictions)
# ============================================================================

_SPECIFIC_STATE_RULES: Dict[str, Dict[str, Any]] = {
    "CA": {
        "restrictions": [
            "no_legal_advice",
            "no_tax_advice",
            "no_document_preparation_for_third_parties",
            "refer_to_attorney_for_interpretation",
        ],
        "warnings": [
            "California Bus. & Prof. Code §6125 strictly prohibits unauthorized "
            "practice of law. MLOs must refer all legal questions to a licensed "
            "California attorney."
        ],
        "required_disclosures": [
            "non_attorney_role",
            "refer_to_attorney_for_legal_questions",
        ],
        "regulatory_citations": [
            "Cal. Bus. & Prof. Code §6125",
            "Cal. Bus. & Prof. Code §6126",
        ],
        "last_updated": "2026-05-19",
        "modeled": True,
    },
    "NY": {
        "restrictions": [
            "no_legal_advice",
            "no_tax_advice",
            "no_lien_priority_interpretation",
            "no_document_preparation_for_third_parties",
            "refer_to_attorney_for_interpretation",
        ],
        "warnings": [
            "New York Judiciary Law §484 is strictly enforced. MLOs may not "
            "discuss lien priority interpretation or any contract construction "
            "question. Closings in NY are typically conducted by attorneys."
        ],
        "required_disclosures": [
            "non_attorney_role",
            "written_attorney_referral_on_file",
        ],
        "regulatory_citations": [
            "N.Y. Judiciary Law §484",
            "N.Y. Judiciary Law §478",
        ],
        "last_updated": "2026-05-19",
        "modeled": True,
    },
    "TX": {
        "restrictions": [
            "no_legal_advice",
            "no_tax_advice",
            "restricted_to_documented_company_procedures",
            "refer_to_attorney_for_interpretation",
        ],
        "warnings": [
            "Texas attorneys may opine on contract terms; MLOs are restricted to "
            "delivering documented company procedures and standardized "
            "disclosures only."
        ],
        "required_disclosures": [
            "non_attorney_role",
            "trec_information_about_brokerage_services_for_residential",
        ],
        "regulatory_citations": [
            "Texas Gov't Code §81.101",
            "TREC Rule §535.148",
        ],
        "last_updated": "2026-05-19",
        "modeled": True,
    },
    "FL": {
        "restrictions": [
            "no_legal_advice",
            "no_tax_advice",
            "no_contract_term_interpretation",
            "refer_to_attorney_for_interpretation",
        ],
        "warnings": [
            "Florida Bar §10-2.1 prohibits non-attorneys from interpreting "
            "contract terms. MLOs must obtain a written client acknowledgement "
            "of their non-attorney role."
        ],
        "required_disclosures": [
            "non_attorney_role",
            "client_acknowledgement_of_non_attorney_role",
        ],
        "regulatory_citations": [
            "Fla. Bar Reg. §10-2.1",
            "Fla. Stat. §454.23",
        ],
        "last_updated": "2026-05-19",
        "modeled": True,
    },
    "IL": {
        "restrictions": [
            "no_legal_advice",
            "no_tax_advice",
            "no_payoff_negotiation_with_third_parties",
            "refer_to_attorney_for_interpretation",
        ],
        "warnings": [
            "Illinois Attorney Act §7 is strongly enforced. MLOs may NOT "
            "negotiate payoff terms with third-party lien holders; route to "
            "an Illinois attorney."
        ],
        "required_disclosures": [
            "non_attorney_role",
            "attorney_review_recommended_for_payoff_terms",
        ],
        "regulatory_citations": [
            "705 ILCS 205/1 (Attorney Act §1)",
            "705 ILCS 205/7 (Attorney Act §7)",
        ],
        "last_updated": "2026-05-19",
        "modeled": True,
    },
}


# Other US states/territories receive the conservative default unless
# specifically overridden above. Listing them explicitly makes coverage
# auditable.
_DEFAULT_STATES: List[str] = [
    "GA", "NC", "VA", "AZ", "CO", "WA", "OR", "MA", "PA", "OH",
    "MI", "NJ", "MD", "MN", "MO", "TN", "IN", "WI", "AL", "LA",
    "KY", "OK", "AR", "KS", "IA", "UT", "NV", "NM", "CT", "NH",
    "ME", "RI", "VT", "WV", "NE", "ID", "HI", "AK", "MT", "ND",
    "SD", "WY", "DC", "PR", "USVI",
]


# Action -> the restriction keys that block it (any match -> blocked).
_ACTION_BLOCKERS: Dict[str, List[str]] = {
    "provide_legal_advice": ["no_legal_advice"],
    "prepare_legal_document": [
        "no_document_preparation_for_third_parties",
        "no_legal_advice",
    ],
    "give_tax_advice": ["no_tax_advice"],
    "discuss_specific_attorney_referral": [
        # Listing a specific attorney by name can imply a fee/referral
        # relationship; restrict by default unless the org has a published
        # referral policy. Modeled states do not pre-allow this.
        "restricted_to_documented_company_procedures",
    ],
    "interpret_contract_terms": [
        "no_contract_term_interpretation",
        "refer_to_attorney_for_interpretation",
        "no_legal_advice",
    ],
    "provide_disclosure_timing_guidance": [
        # Disclosure timing guidance per CFPB rule is generally allowed; only
        # block in states that explicitly restrict it.
    ],
    "discuss_lien_priority": ["no_lien_priority_interpretation"],
    "negotiate_payoff_terms": ["no_payoff_negotiation_with_third_parties"],
}


def _normalize_state(state_abbr: Optional[str]) -> str:
    if not state_abbr:
        return ""
    return str(state_abbr).strip().upper()


# ============================================================================
# ENGINE
# ============================================================================

class UPLRulesEngine:
    """
    Multi-state UPL rules engine.

    NOTE: This is a software check, not legal advice. Conservative defaults
    apply to any state not explicitly modeled. Always consult counsel before
    relying on engine output for compliance attestations.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, Dict[str, Any]] = {}
        # Seed specific high-touch states
        for code, rule in _SPECIFIC_STATE_RULES.items():
            self._rules[code] = dict(rule)
        # Seed defaults for remaining states/territories
        for code in _DEFAULT_STATES:
            if code not in self._rules:
                self._rules[code] = _default_rule(code)

    # ------------------------------------------------------------------
    def list_states(self) -> List[str]:
        """Return sorted list of state/territory codes the engine knows."""
        return sorted(self._rules.keys())

    def get_rule_set(self, state_abbr: str) -> Dict[str, Any]:
        """
        Return the full rule set for a state. Unknown states receive the
        conservative default rule set.
        """
        code = _normalize_state(state_abbr)
        rule = self._rules.get(code)
        if rule is None:
            rule = _default_rule(code or "??")
        out = dict(rule)
        out["state"] = code
        out["state_rules_version"] = STATE_RULES_VERSION
        return out

    # ------------------------------------------------------------------
    def check(
        self,
        action: str,
        state_abbr: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check whether ``action`` is permitted in ``state_abbr``.

        Returns:
            {
                "allowed":              bool,
                "action":               str,
                "state":                str,
                "restrictions":         list[str],   # restriction keys for the state
                "warnings":             list[str],
                "required_disclosures": list[str],
                "regulatory_citations": list[str],
                "state_rules_version":  str,
            }
        """
        context = context or {}
        code = _normalize_state(state_abbr)
        rule = self.get_rule_set(code)

        if action not in SUPPORTED_ACTIONS:
            return {
                "allowed": False,
                "action": action,
                "state": code,
                "restrictions": list(rule["restrictions"]),
                "warnings": list(rule["warnings"]) + [
                    f"Unknown action '{action}'; rejecting conservatively."
                ],
                "required_disclosures": list(rule["required_disclosures"]),
                "regulatory_citations": list(rule["regulatory_citations"]),
                "state_rules_version": STATE_RULES_VERSION,
            }

        blockers = _ACTION_BLOCKERS.get(action, [])
        state_restrictions = set(rule["restrictions"])
        blocking_restrictions = [b for b in blockers if b in state_restrictions]

        # Allowed only if no blocker restriction is present in the state rule.
        allowed = len(blocking_restrictions) == 0

        warnings = list(rule["warnings"])
        if blocking_restrictions:
            warnings.append(
                f"Action '{action}' is blocked in {code} by: "
                f"{', '.join(blocking_restrictions)}."
            )

        return {
            "allowed": allowed,
            "action": action,
            "state": code,
            "restrictions": list(rule["restrictions"]),
            "warnings": warnings,
            "required_disclosures": list(rule["required_disclosures"]),
            "regulatory_citations": list(rule["regulatory_citations"]),
            "state_rules_version": STATE_RULES_VERSION,
            "blocking_restrictions": blocking_restrictions,
        }

    # ------------------------------------------------------------------
    def detect_action_in_text(self, text: str) -> List[str]:
        """
        Heuristic phrase-based scan that returns the list of UPL-relevant
        action keys a piece of text appears to touch. Used by the agent
        compliance guard for response screening.
        """
        if not text:
            return []
        t = text.lower()
        hits: List[str] = []
        phrase_map = {
            "provide_legal_advice": [
                "legal advice", "as your attorney", "legally you should",
                "i recommend you legally",
            ],
            "prepare_legal_document": [
                "i'll draft the", "i will draft your", "let me prepare the deed",
                "draft your contract", "draft a contract",
            ],
            "give_tax_advice": [
                "tax advice", "your tax liability", "deduct on your taxes",
                "your write-off",
            ],
            "discuss_specific_attorney_referral": [
                "use attorney ", "you should hire ", "go with attorney ",
            ],
            "interpret_contract_terms": [
                "what this clause means", "the contract requires you",
                "interpreting this clause", "this clause means",
            ],
            "discuss_lien_priority": [
                "lien priority", "your liens rank", "first lien position",
                "second lien stripping",
            ],
            "negotiate_payoff_terms": [
                "negotiate your payoff", "let me negotiate the payoff",
                "negotiate payoff terms",
            ],
            "provide_disclosure_timing_guidance": [
                "you must disclose", "disclosure timing", "regulation requires you to",
            ],
        }
        for action, phrases in phrase_map.items():
            if any(p in t for p in phrases):
                hits.append(action)
        return hits


# Module-level singleton (matches compliance_guard pattern)
upl_rules_engine = UPLRulesEngine()


__all__ = [
    "UPLRulesEngine",
    "upl_rules_engine",
    "STATE_RULES_VERSION",
    "SUPPORTED_ACTIONS",
    "DEFAULT_RESTRICTIONS",
    "DEFAULT_REQUIRED_DISCLOSURES",
]
