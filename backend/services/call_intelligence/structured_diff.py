"""
Structured Data Diff Comparator
===============================
Compares structured data captured by the URLA voice agent (@function_tool saves)
against independent transcript extractions from the CI pipeline.

Agreement → auto-approve, write-through to BytePro.
Disagreement → review queue with both versions side-by-side.

This is the compliance moat: two independent extraction paths cross-check
each other, catching hallucinations, mishears, late corrections, and
off-script disclosures that neither approach catches alone.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from .data_contracts import (
    CallIntelligenceResponse,
    ExtractedValue,
    ExtractionResult,
    ReviewQueueItem,
)

logger = logging.getLogger(__name__)


# ── Tolerance thresholds ──────────────────────────────────────────────

CURRENCY_TOLERANCE_PCT = 0.01       # 1% tolerance for dollar amounts
DATE_TOLERANCE_DAYS = 0             # Exact match for dates
STRING_SIMILARITY_THRESHOLD = 0.85  # Levenshtein ratio for fuzzy string match
AUTO_APPROVE_CONFIDENCE = 90.0      # Default min extraction confidence for auto-approve
LOW_CONFIDENCE_AGREEMENT_THRESHOLD = 75.0  # Below this, agreement still routes to review

# Per-field confidence thresholds for URLA critical fields.
# These fields cause real downstream pain if wrong (BytePro rejects,
# compliance flags, LO has to redo intake) so they need higher confidence.
CRITICAL_FIELD_THRESHOLDS: Dict[str, float] = {
    "ssn_last_four": 95.0,
    "date_of_birth": 95.0,
    "annual_salary": 93.0,
    "monthly_salary": 93.0,
    "purchase_price": 95.0,
    "street_address": 93.0,
    "city": 90.0,
    "state": 90.0,
    "zip_code": 93.0,
    "first_name": 92.0,
    "last_name": 92.0,
    "has_bankruptcy": 93.0,
    "has_foreclosure": 93.0,
    "citizenship_status": 93.0,
}


# ── Field mapping: CI extraction field → URLA captured_structured_data key ──

FIELD_MAP: Dict[str, str] = {
    # Identity → Section 1a
    "first_name": "borrower.first_name",
    "last_name": "borrower.last_name",
    "middle_name": "borrower.middle_name",
    "suffix": "borrower.suffix",
    "ssn_last_four": "borrower.ssn_last_four",
    "date_of_birth": "borrower.date_of_birth",
    "email": "borrower.email",
    "phone": "borrower.phone",
    "marital_status": "borrower.marital_status",
    "citizenship_status": "borrower.citizenship_status",

    # Property → Section 4a
    "street_address": "section_4.subject_property_address.street",
    "city": "section_4.subject_property_address.city",
    "state": "section_4.subject_property_address.state",
    "zip_code": "section_4.subject_property_address.zip_code",
    "purchase_price": "section_4.property_value",
    "property_type": "section_4.property_type",

    # Employment → Section 1b
    "employer_name": "borrower.employer_name",
    "job_title": "borrower.position",
    "employment_type": "borrower.employment_type",
    "is_self_employed": "borrower.self_employed",
    "years_at_job": "borrower.years_at_job",

    # Financial → Section 1b / 2
    "annual_salary": "borrower.monthly_income_total",
    "monthly_salary": "borrower.monthly_income",

    # Compliance → Section 5
    "has_bankruptcy": "section_5.bankruptcy",
    "has_foreclosure": "section_5.foreclosure",
    "has_judgments": "section_5.outstanding_judgments",
    "will_occupy_as_primary": "section_4.occupancy",

    # Intent → Section 4a
    "loan_purpose": "section_4.loan_purpose",
    "loan_type_preference": "section_4.loan_type",
}

# Reverse map for looking up extraction field from captured key
_REVERSE_MAP: Dict[str, str] = {v: k for k, v in FIELD_MAP.items()}


@dataclass
class FieldAgreement:
    """Both extraction and captured data agree on this field."""
    field_name: str
    domain: str
    captured_value: Any
    extracted_value: Any
    extraction_confidence: float


@dataclass
class FieldDisagreement:
    """Extraction and captured data disagree — routes to review queue."""
    field_name: str
    domain: str
    captured_value: Any
    extracted_value: Any
    extraction_confidence: float
    source_text: str = ""
    reason: str = "unknown"


@dataclass
class ExtractionOnly:
    """Transcript extraction found something the agent didn't capture."""
    field_name: str
    domain: str
    extracted_value: Any
    extraction_confidence: float
    source_text: str = ""


@dataclass
class LowConfidenceAgreement:
    """Both paths agree but extraction confidence is too low to auto-approve.
    Both paths can be wrong the same way (e.g. Deepgram mistranscribes a number,
    LLM extracts the mistranscription, agent also saved the mistranscription)."""
    field_name: str
    domain: str
    captured_value: Any
    extracted_value: Any
    extraction_confidence: float


@dataclass
class DiffReport:
    """Full comparison report between captured and extracted data."""
    call_id: str
    agreements: List[FieldAgreement] = field(default_factory=list)
    disagreements: List[FieldDisagreement] = field(default_factory=list)
    extraction_only: List[ExtractionOnly] = field(default_factory=list)
    captured_only: List[str] = field(default_factory=list)
    low_confidence_agreements: List[LowConfidenceAgreement] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def agreement_rate(self) -> float:
        total = len(self.agreements) + len(self.disagreements)
        return (len(self.agreements) / total * 100) if total > 0 else 0.0

    @property
    def needs_review(self) -> bool:
        return (
            len(self.disagreements) > 0
            or len(self.extraction_only) > 0
            or len(self.low_confidence_agreements) > 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "agreement_count": len(self.agreements),
            "disagreement_count": len(self.disagreements),
            "extraction_only_count": len(self.extraction_only),
            "captured_only_count": len(self.captured_only),
            "low_confidence_agreement_count": len(self.low_confidence_agreements),
            "agreement_rate": round(self.agreement_rate, 1),
            "needs_review": self.needs_review,
            "agreements": [
                {"field": a.field_name, "domain": a.domain, "value": _safe_str(a.captured_value)}
                for a in self.agreements
            ],
            "disagreements": [
                {
                    "field": d.field_name, "domain": d.domain,
                    "captured": _safe_str(d.captured_value),
                    "extracted": _safe_str(d.extracted_value),
                    "confidence": d.extraction_confidence,
                    "reason": d.reason,
                }
                for d in self.disagreements
            ],
            "low_confidence_agreements": [
                {
                    "field": a.field_name, "domain": a.domain,
                    "value": _safe_str(a.captured_value),
                    "confidence": a.extraction_confidence,
                }
                for a in self.low_confidence_agreements
            ],
            "extraction_only": [
                {
                    "field": e.field_name, "domain": e.domain,
                    "value": _safe_str(e.extracted_value),
                    "confidence": e.extraction_confidence,
                }
                for e in self.extraction_only
            ],
            "captured_only": self.captured_only,
            "created_at": self.created_at.isoformat(),
        }


class StructuredDiffComparator:
    """
    Compare extraction results against URLA captured structured data.

    Usage:
        comparator = StructuredDiffComparator()
        diff = comparator.compare(
            call_id="call-123",
            captured=flatten_urla_application(app),
            response=ci_response,
        )
        review_items = comparator.to_review_queue_items(diff, loan_id=456)
    """

    def __init__(
        self,
        field_map: Optional[Dict[str, str]] = None,
        auto_approve_confidence: float = AUTO_APPROVE_CONFIDENCE,
    ):
        self.field_map = field_map or FIELD_MAP
        self.auto_approve_confidence = auto_approve_confidence

    def compare(
        self,
        call_id: str,
        captured: Dict[str, Any],
        response: CallIntelligenceResponse,
    ) -> DiffReport:
        """
        Run full comparison.

        Args:
            call_id: The call identifier
            captured: Flattened URLA application data (dot-notation keys)
            response: CI pipeline extraction results

        Returns:
            DiffReport with agreements, disagreements, extraction-only, captured-only
        """
        report = DiffReport(call_id=call_id)

        # Build lookup of all extractions by field name
        extracted = self._collect_extractions(response)

        # Track which captured fields have been compared
        compared_captured_keys: set = set()

        for ext_field, ext_value in extracted.items():
            captured_key = self.field_map.get(ext_field)

            if captured_key and captured_key in captured:
                compared_captured_keys.add(captured_key)
                cap_val = captured[captured_key]
                domain = self._domain_for_field(ext_field)
                confidence = ext_value.confidence

                if self._values_match(cap_val, ext_value.value, ext_field):
                    # Both paths agree — but check confidence before auto-approving.
                    # Per-field threshold for critical URLA fields that cause downstream
                    # pain if wrong (BytePro rejects, compliance flags, redo intake).
                    field_threshold = CRITICAL_FIELD_THRESHOLDS.get(
                        ext_field, self.auto_approve_confidence
                    )
                    if confidence < LOW_CONFIDENCE_AGREEMENT_THRESHOLD:
                        # Both paths can be wrong the same way (Deepgram mistranscribes
                        # a number, LLM extracts it verbatim, agent also saved it).
                        report.low_confidence_agreements.append(LowConfidenceAgreement(
                            field_name=ext_field,
                            domain=domain,
                            captured_value=cap_val,
                            extracted_value=ext_value.value,
                            extraction_confidence=confidence,
                        ))
                    elif confidence < field_threshold:
                        # Agrees but below the per-field threshold — still review
                        report.low_confidence_agreements.append(LowConfidenceAgreement(
                            field_name=ext_field,
                            domain=domain,
                            captured_value=cap_val,
                            extracted_value=ext_value.value,
                            extraction_confidence=confidence,
                        ))
                    else:
                        report.agreements.append(FieldAgreement(
                            field_name=ext_field,
                            domain=domain,
                            captured_value=cap_val,
                            extracted_value=ext_value.value,
                            extraction_confidence=confidence,
                        ))
                else:
                    reason = self._classify_disagreement(
                        cap_val, ext_value.value, ext_field, confidence,
                    )
                    report.disagreements.append(FieldDisagreement(
                        field_name=ext_field,
                        domain=domain,
                        captured_value=cap_val,
                        extracted_value=ext_value.value,
                        extraction_confidence=confidence,
                        source_text=ext_value.source_text,
                        reason=reason,
                    ))
            elif ext_field in self.field_map:
                # Extraction found a value but URLA agent didn't capture it
                report.extraction_only.append(ExtractionOnly(
                    field_name=ext_field,
                    domain=self._domain_for_field(ext_field),
                    extracted_value=ext_value.value,
                    extraction_confidence=ext_value.confidence,
                    source_text=ext_value.source_text,
                ))

        # Find captured fields with no corresponding extraction
        for cap_key, cap_val in captured.items():
            if cap_key not in compared_captured_keys and cap_val is not None:
                if cap_key in _REVERSE_MAP:
                    report.captured_only.append(cap_key)

        logger.info(
            "Structured diff complete for %s: %d agree, %d disagree, "
            "%d low-conf agree, %d extraction-only, %d captured-only "
            "(%.1f%% agreement)",
            call_id,
            len(report.agreements),
            len(report.disagreements),
            len(report.low_confidence_agreements),
            len(report.extraction_only),
            len(report.captured_only),
            report.agreement_rate,
        )
        return report

    def to_review_queue_items(
        self,
        diff: DiffReport,
        loan_id: Optional[int] = None,
    ) -> List[ReviewQueueItem]:
        """
        Convert disagreements and extraction-only findings into ReviewQueueItems
        for the existing human review queue.
        """
        items: List[ReviewQueueItem] = []

        for d in diff.disagreements:
            items.append(ReviewQueueItem(
                review_id=str(uuid.uuid4()),
                call_id=diff.call_id,
                loan_id=loan_id,
                extraction_type=d.domain,
                field_name=d.field_name,
                extracted_value=d.extracted_value,
                confidence_score=d.extraction_confidence,
                source_text=d.source_text,
                captured_value=d.captured_value,
                disagreement_reason=d.reason,
            ))

        for e in diff.extraction_only:
            items.append(ReviewQueueItem(
                review_id=str(uuid.uuid4()),
                call_id=diff.call_id,
                loan_id=loan_id,
                extraction_type=e.domain,
                field_name=e.field_name,
                extracted_value=e.extracted_value,
                confidence_score=e.extraction_confidence,
                source_text=e.source_text,
                disagreement_reason="extraction_only",
            ))

        for a in diff.low_confidence_agreements:
            items.append(ReviewQueueItem(
                review_id=str(uuid.uuid4()),
                call_id=diff.call_id,
                loan_id=loan_id,
                extraction_type=a.domain,
                field_name=a.field_name,
                extracted_value=a.extracted_value,
                confidence_score=a.extraction_confidence,
                source_text="",
                captured_value=a.captured_value,
                disagreement_reason="low_confidence_agreement",
            ))

        return items

    # ── Internal ──────────────────────────────────────────────────────

    def _collect_extractions(
        self,
        response: CallIntelligenceResponse,
    ) -> Dict[str, ExtractedValue]:
        """Flatten all agent results into a single field→ExtractedValue map."""
        result: Dict[str, ExtractedValue] = {}
        for agent_result in response.agent_results:
            for ext in agent_result.extractions:
                if ext.value is not None and ext.field_name not in result:
                    result[ext.field_name] = ext
        return result

    def _values_match(self, captured: Any, extracted: Any, field_name: str) -> bool:
        """Compare two values with type-aware tolerance."""
        if captured is None and extracted is None:
            return True
        if captured is None or extracted is None:
            return False

        # Normalize to strings for comparison
        cap_str = str(captured).strip().lower()
        ext_str = str(extracted).strip().lower()

        if cap_str == ext_str:
            return True

        # Currency/numeric: tolerance-based comparison
        if self._is_currency_field(field_name):
            return self._currency_match(captured, extracted)

        # Boolean fields
        if isinstance(captured, bool) or isinstance(extracted, bool):
            return self._bool_match(captured, extracted)

        # Fuzzy string match for names, addresses
        if self._is_string_field(field_name):
            return _levenshtein_ratio(cap_str, ext_str) >= STRING_SIMILARITY_THRESHOLD

        return cap_str == ext_str

    def _currency_match(self, a: Any, b: Any) -> bool:
        try:
            da = Decimal(str(a).replace(",", "").replace("$", ""))
            db = Decimal(str(b).replace(",", "").replace("$", ""))
            if da == 0 and db == 0:
                return True
            if da == 0 or db == 0:
                return False
            ratio = abs(da - db) / max(abs(da), abs(db))
            return ratio <= Decimal(str(CURRENCY_TOLERANCE_PCT))
        except (InvalidOperation, ValueError, ZeroDivisionError):
            return str(a).strip() == str(b).strip()

    def _bool_match(self, a: Any, b: Any) -> bool:
        truthy = {"true", "yes", "1", "y"}
        falsy = {"false", "no", "0", "n"}
        a_str = str(a).strip().lower()
        b_str = str(b).strip().lower()
        a_bool = a_str in truthy
        b_bool = b_str in truthy
        if a_str in truthy or a_str in falsy:
            if b_str in truthy or b_str in falsy:
                return a_bool == b_bool
        return a_str == b_str

    def _classify_disagreement(
        self,
        captured: Any,
        extracted: Any,
        field_name: str,
        confidence: float,
    ) -> str:
        """Classify the likely cause of a disagreement."""
        if confidence < 70:
            return "low_confidence"

        if self._is_currency_field(field_name):
            try:
                dc = Decimal(str(captured).replace(",", "").replace("$", ""))
                de = Decimal(str(extracted).replace(",", "").replace("$", ""))
                ratio = abs(dc - de) / max(abs(dc), abs(de)) if max(abs(dc), abs(de)) > 0 else 0
                if ratio >= Decimal("0.5"):
                    return "hallucination"
                return "mishear"
            except (InvalidOperation, ValueError):
                pass

        if self._is_string_field(field_name):
            ratio = _levenshtein_ratio(
                str(captured).lower(), str(extracted).lower()
            )
            if ratio > 0.6:
                return "mishear"
            return "late_correction"

        return "late_correction"

    @staticmethod
    def _is_currency_field(field_name: str) -> bool:
        return any(k in field_name for k in (
            "salary", "income", "payment", "price", "balance",
            "amount", "rate", "value", "loan_amount",
        ))

    @staticmethod
    def _is_string_field(field_name: str) -> bool:
        return any(k in field_name for k in (
            "name", "address", "street", "city", "employer",
            "title", "job", "position",
        ))

    @staticmethod
    def _domain_for_field(field_name: str) -> str:
        """Map extraction field name to CI domain."""
        identity_fields = {
            "first_name", "last_name", "middle_name", "suffix",
            "ssn_last_four", "date_of_birth", "email", "phone",
            "marital_status", "citizenship_status",
        }
        property_fields = {
            "street_address", "city", "state", "zip_code",
            "purchase_price", "property_type",
        }
        employment_fields = {
            "employer_name", "job_title", "employment_type",
            "is_self_employed", "years_at_job",
        }
        financial_fields = {
            "annual_salary", "monthly_salary", "hourly_rate",
            "bonus_income", "commission_income",
        }
        compliance_fields = {
            "has_bankruptcy", "has_foreclosure", "has_judgments",
            "will_occupy_as_primary",
        }
        if field_name in identity_fields:
            return "identity"
        if field_name in property_fields:
            return "property"
        if field_name in employment_fields:
            return "employment"
        if field_name in financial_fields:
            return "financial"
        if field_name in compliance_fields:
            return "compliance"
        return "intent"


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val)


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Quick Levenshtein similarity ratio (0.0-1.0)."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    max_len = max(len1, len2)

    # Optimized for short strings (names, addresses)
    if max_len > 200:
        return 1.0 if s1 == s2 else 0.0

    # Wagner-Fischer algorithm
    prev = list(range(len2 + 1))
    for i in range(1, len1 + 1):
        curr = [i] + [0] * len2
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr

    distance = prev[len2]
    return 1.0 - (distance / max_len)
