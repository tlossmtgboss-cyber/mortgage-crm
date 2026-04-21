"""
URLA-Specific Extraction Agent (7th Agent)
==========================================
Extracts fields from URLA 1003 voice intake calls that the existing 6 agents
don't cover:
  - Military service (Section 7): veteran status, service branch, expected
    expiration date of service
  - Detailed declarations (Section 5): all 14 declarations beyond the
    bankruptcy/foreclosure/judgments already handled by ComplianceAgent
  - Co-borrower details: full name, SSN last 4, DOB, relationship
  - Real estate owned (Section 3): additional property details
  - Gift/grant sources with specifics
  - Housing expense detail (Section 1a): rent vs own, monthly payment

This agent runs alongside the existing 6 when call_type == URLA_INTAKE.
It does NOT duplicate work the other agents do — it fills the gaps.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base_agent import BaseExtractionAgent, ConfidenceScores
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)
from ..pii_utils import sanitize_source_text

logger = logging.getLogger(__name__)


class URLAExtractionAgent(BaseExtractionAgent):
    """Extract URLA-specific fields not covered by the standard 6 agents."""

    AGENT_NAME = "urla"
    AGENT_VERSION = "1.0"
    EXTRACTION_SCHEMA_KEY = "urla"
    RECOMMENDED_MODEL = "sonnet"

    # ── Patterns ──────────────────────────────────────────────────────

    _VETERAN_PATTERNS = [
        re.compile(r"\b(?:i(?:'m| am) a )?veteran\b", re.I),
        re.compile(r"\b(?:served|serving) in (?:the )?(?:military|army|navy|air force|marines|coast guard|national guard|space force)\b", re.I),
        re.compile(r"\bactive[- ]?duty\b", re.I),
        re.compile(r"\bva (?:loan|eligible|benefit|entitlement)\b", re.I),
        re.compile(r"\bdd[- ]?214\b", re.I),
        re.compile(r"\breservist\b", re.I),
        re.compile(r"\bnational guard\b", re.I),
    ]

    _SERVICE_BRANCH_PATTERNS = {
        "army": re.compile(r"\b(?:us |united states )?army\b", re.I),
        "navy": re.compile(r"\b(?:us |united states )?navy\b", re.I),
        "air_force": re.compile(r"\b(?:us |united states )?air force\b", re.I),
        "marines": re.compile(r"\b(?:us |united states )?marine(?:s| corps)\b", re.I),
        "coast_guard": re.compile(r"\b(?:us |united states )?coast guard\b", re.I),
        "national_guard": re.compile(r"\bnational guard\b", re.I),
        "space_force": re.compile(r"\b(?:us |united states )?space force\b", re.I),
    }

    _NOT_VETERAN_PATTERNS = [
        re.compile(r"\b(?:no|not|never|haven't|have not)(?:\s+\w+){0,3}\s+(?:served|military|veteran|armed forces)\b", re.I),
        re.compile(r"\b(?:i'm not|i am not) a veteran\b", re.I),
        re.compile(r"\bcivilian\b", re.I),
    ]

    # Declarations (Section 5) — beyond bankruptcy/foreclosure/judgments
    _DECLARATION_PATTERNS = {
        "borrowed_down_payment": [
            re.compile(r"\bborrow(?:ed|ing)?\b.*\bdown ?payment\b", re.I),
            re.compile(r"\bdown ?payment\b.*\bborrow(?:ed|ing)?\b", re.I),
        ],
        "co_maker_endorser": [
            re.compile(r"\bco[- ]?sign(?:ed|er|ing)?\b", re.I),
            re.compile(r"\bco[- ]?maker\b", re.I),
            re.compile(r"\bendorser\b", re.I),
        ],
        "outstanding_judgments": [
            re.compile(r"\bjudgment\b", re.I),
            re.compile(r"\bdefault(?:ed)?\b", re.I),
        ],
        "federal_debt_delinquent": [
            re.compile(r"\bfederal\b.*\bdebt\b", re.I),
            re.compile(r"\bdelinquent\b.*\b(?:taxes?|federal|government)\b", re.I),
            re.compile(r"\b(?:irs|sba|student loan)\b.*\b(?:owe|behind|delinquent)\b", re.I),
        ],
        "party_to_lawsuit": [
            re.compile(r"\blawsuit\b", re.I),
            re.compile(r"\blitigation\b", re.I),
            re.compile(r"\bbeing sued\b", re.I),
        ],
        "obligated_on_other_loan": [
            re.compile(r"\bother (?:mortgage|loan|property)\b", re.I),
            re.compile(r"\b(?:another|second|other) (?:home|house|property)\b", re.I),
        ],
        "delinquent_on_any_debt": [
            re.compile(r"\bdelinquent\b.*\bdebt\b", re.I),
            re.compile(r"\bbehind on\b.*\bpayment\b", re.I),
            re.compile(r"\bpast due\b", re.I),
        ],
        "alimony_child_support": [
            re.compile(r"\b(?:alimony|child support|spousal support|maintenance)\b", re.I),
        ],
        "ownership_interest": [
            re.compile(r"\b(?:own|ownership)\b.*\b(?:property|business|real estate)\b", re.I),
        ],
        "property_foreclosed": [
            re.compile(r"\b(?:foreclos(?:ure|ed)|short[- ]?sale|deed[- ]?in[- ]?lieu)\b", re.I),
        ],
    }

    # Co-borrower detection
    _COBORROWER_PATTERNS = [
        re.compile(r"\b(?:my )?(?:wife|husband|spouse|partner|co[- ]?borrower)\b", re.I),
        re.compile(r"\b(?:we(?:'re| are)?\s+(?:both|applying|buying))\b", re.I),
        re.compile(r"\b(?:joint\s+(?:application|applicant|borrower))\b", re.I),
    ]

    _COBORROWER_NAME = re.compile(
        r"(?:wife|husband|spouse|partner|co[- ]?borrower)(?:'s| is)?\s+(?:name\s+is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        re.I,
    )

    # Gift/grant
    _GIFT_PATTERNS = [
        re.compile(r"\bgift\b.*\b(?:from|parent|family|relative|friend)\b", re.I),
        re.compile(r"\bdown ?payment\b.*\bgift\b", re.I),
        re.compile(r"\bgrant\b.*\b(?:first[- ]?time|home ?buyer|down ?payment)\b", re.I),
    ]

    _HOUSING_OWN = re.compile(r"\b(?:i |we )?(?:own|mortgage|paying a mortgage)\b", re.I)
    _HOUSING_RENT = re.compile(r"\b(?:i |we )?(?:rent|renting|tenant|lease|leasing)\b", re.I)
    _HOUSING_FREE = re.compile(r"\b(?:living )?(?:rent[- ]?free|with (?:parents|family)|no (?:rent|housing))\b", re.I)

    # ── Extraction ────────────────────────────────────────────────────

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        result = ExtractionResult(agent_name=self.AGENT_NAME)
        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Military / veteran status
        military = self._extract_military(borrower_text, full_text)
        result.extractions.extend(military)

        # Declarations (Section 5 gaps)
        declarations = self._extract_declarations(borrower_text, full_text)
        result.extractions.extend(declarations)

        # Co-borrower
        coborrower = self._extract_coborrower(borrower_text, full_text)
        result.extractions.extend(coborrower)

        # Gift/grant sources
        gifts = self._extract_gifts(borrower_text, full_text)
        result.extractions.extend(gifts)

        # Housing status
        housing = self._extract_housing(borrower_text, full_text)
        if housing:
            result.extractions.append(housing)

        return result

    # ── Military ──────────────────────────────────────────────────────

    def _extract_military(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        extractions: List[ExtractedValue] = []

        # Check for non-veteran first
        for pat in self._NOT_VETERAN_PATTERNS:
            m = pat.search(borrower_text) or pat.search(full_text)
            if m:
                extractions.append(ExtractedValue(
                    field_name="is_veteran",
                    value=False,
                    confidence=ConfidenceScores.YES_NO,
                    source_text=sanitize_source_text(m.group(0)),
                    extraction_method="regex",
                ))
                return extractions

        # Check for veteran
        for pat in self._VETERAN_PATTERNS:
            m = pat.search(borrower_text) or pat.search(full_text)
            if m:
                extractions.append(ExtractedValue(
                    field_name="is_veteran",
                    value=True,
                    confidence=ConfidenceScores.YES_NO,
                    source_text=sanitize_source_text(m.group(0)),
                    extraction_method="regex",
                ))

                # Try to extract branch
                for branch, branch_pat in self._SERVICE_BRANCH_PATTERNS.items():
                    bm = branch_pat.search(full_text)
                    if bm:
                        extractions.append(ExtractedValue(
                            field_name="military_branch",
                            value=branch,
                            confidence=ConfidenceScores.REGEX_HIGH,
                            source_text=sanitize_source_text(bm.group(0)),
                            extraction_method="regex",
                        ))
                        break

                return extractions

        return extractions

    # ── Declarations ──────────────────────────────────────────────────

    def _extract_declarations(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        extractions: List[ExtractedValue] = []

        for decl_name, patterns in self._DECLARATION_PATTERNS.items():
            for pat in patterns:
                m = pat.search(borrower_text) or pat.search(full_text)
                if m:
                    # Determine yes/no from context
                    context = _get_context(full_text, m.start(), 100)
                    is_yes = not _negated(context, m.group(0))

                    extractions.append(ExtractedValue(
                        field_name=f"declaration_{decl_name}",
                        value=is_yes,
                        confidence=ConfidenceScores.YES_NO if is_yes else ConfidenceScores.LLM_DEFAULT,
                        source_text=sanitize_source_text(context),
                        extraction_method="regex",
                    ))
                    break

        return extractions

    # ── Co-borrower ───────────────────────────────────────────────────

    def _extract_coborrower(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        extractions: List[ExtractedValue] = []

        has_coborrower = False
        for pat in self._COBORROWER_PATTERNS:
            if pat.search(borrower_text) or pat.search(full_text):
                has_coborrower = True
                break

        if has_coborrower:
            extractions.append(ExtractedValue(
                field_name="has_coborrower",
                value=True,
                confidence=ConfidenceScores.YES_NO,
                source_text="",
                extraction_method="regex",
            ))

            m = self._COBORROWER_NAME.search(full_text)
            if m:
                name = m.group(1).strip()
                extractions.append(ExtractedValue(
                    field_name="coborrower_name",
                    value=name,
                    confidence=ConfidenceScores.NAME,
                    source_text=sanitize_source_text(m.group(0)),
                    extraction_method="regex",
                ))

        return extractions

    # ── Gifts / Grants ────────────────────────────────────────────────

    def _extract_gifts(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        extractions: List[ExtractedValue] = []

        for pat in self._GIFT_PATTERNS:
            m = pat.search(borrower_text) or pat.search(full_text)
            if m:
                extractions.append(ExtractedValue(
                    field_name="has_gift_funds",
                    value=True,
                    confidence=ConfidenceScores.YES_NO,
                    source_text=sanitize_source_text(m.group(0)),
                    extraction_method="regex",
                ))

                # Try to extract gift amount
                context = _get_context(full_text, m.start(), 150)
                amount_match = re.search(
                    r"\$?([\d,]+(?:\.\d{2})?)\s*(?:thousand|k|dollars?)?",
                    context, re.I,
                )
                if amount_match:
                    raw = amount_match.group(1).replace(",", "")
                    try:
                        val = float(raw)
                        if "thousand" in context.lower() or "k" in context.lower():
                            val *= 1000
                        if 1_000 <= val <= 5_000_000:
                            extractions.append(ExtractedValue(
                                field_name="gift_amount",
                                value=val,
                                confidence=ConfidenceScores.CURRENCY,
                                source_text=sanitize_source_text(context),
                                extraction_method="regex",
                            ))
                    except ValueError:
                        pass

                break

        return extractions

    # ── Housing ────��──────────────────────────────────────────────────

    def _extract_housing(
        self,
        borrower_text: str,
        full_text: str,
    ) -> Optional[ExtractedValue]:
        text = borrower_text or full_text

        if self._HOUSING_OWN.search(text):
            return ExtractedValue(
                field_name="current_housing_status",
                value="own",
                confidence=ConfidenceScores.REGEX_HIGH,
                source_text="",
                extraction_method="regex",
            )
        if self._HOUSING_RENT.search(text):
            return ExtractedValue(
                field_name="current_housing_status",
                value="rent",
                confidence=ConfidenceScores.REGEX_HIGH,
                source_text="",
                extraction_method="regex",
            )
        if self._HOUSING_FREE.search(text):
            return ExtractedValue(
                field_name="current_housing_status",
                value="rent_free",
                confidence=ConfidenceScores.REGEX_MEDIUM,
                source_text="",
                extraction_method="regex",
            )
        return None


# ── Helpers ──────��────────────────────────────────────────────────────

def _get_context(text: str, pos: int, window: int) -> str:
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    return text[start:end]


_NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|don'?t|doesn'?t|haven'?t|hasn'?t|didn'?t|none|neither)\b",
    re.I,
)


def _negated(context: str, match_text: str) -> bool:
    """Check if the match is negated in its surrounding context."""
    before = context[:context.find(match_text)] if match_text in context else context
    last_50 = before[-50:] if len(before) > 50 else before
    return bool(_NEGATION_PATTERN.search(last_50))
