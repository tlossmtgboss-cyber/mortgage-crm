"""
W2/Paystub Cross-Validation Service

Performs deep consistency checks between W2 and paystub documents for the
same borrower to detect discrepancies, data entry errors, and potential
fraud indicators. Validates income figures, employer/employee identity,
tax withholdings, deductions, and temporal consistency.

Integrates with:
    - smart_documents / smart_document_extractions for extracted field data
    - fraud_detection_service for shared name-matching utilities
    - income_calculator_service for pay-frequency multipliers

Usage:
    from services.smart_docs.w2_paystub_cross_validator import (
        get_w2_paystub_cross_validator,
        W2PaystubCrossValidator,
    )

    validator = get_w2_paystub_cross_validator(db)
    result = validator.validate(loan_id=42, borrower_id=7)
    if result.confidence_score < 60:
        # Flag for manual review
        ...
"""

import logging
import re
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# Pay-frequency annualization multipliers (must match income_calculator_service)
PAY_FREQUENCY_MULTIPLIERS: Dict[str, int] = {
    "WEEKLY": 52,
    "BIWEEKLY": 26,
    "SEMIMONTHLY": 24,
    "MONTHLY": 12,
}

# 2025/2026 tax year constants
SOCIAL_SECURITY_WAGE_BASE: Dict[int, Decimal] = {
    2023: Decimal("160200"),
    2024: Decimal("168600"),
    2025: Decimal("176100"),
    2026: Decimal("176100"),  # placeholder until IRS publishes
}

SOCIAL_SECURITY_RATE = Decimal("0.062")
MEDICARE_RATE = Decimal("0.0145")
ADDITIONAL_MEDICARE_THRESHOLD = Decimal("200000")
ADDITIONAL_MEDICARE_RATE = Decimal("0.009")

# Tolerance thresholds for proportional comparisons
INCOME_TOLERANCE_PCT = Decimal("5")     # 5% variance allowed
WITHHOLDING_TOLERANCE_PCT = Decimal("8")  # 8% variance (withholding can shift mid-year)
WAGE_TOLERANCE_PCT = Decimal("3")       # 3% for SS/Medicare wage bases

# Overtime multiplier (standard FLSA)
STANDARD_OT_MULTIPLIER = Decimal("1.5")

# Deduction reasonableness bounds (annual)
MAX_401K_CONTRIBUTION_UNDER_50 = Decimal("23500")  # 2025 limit
MAX_401K_CONTRIBUTION_OVER_50 = Decimal("31000")   # 2025 limit with catch-up
MAX_HEALTH_INSURANCE_ANNUAL = Decimal("30000")      # family plan upper bound
MIN_HEALTH_INSURANCE_ANNUAL = Decimal("600")        # minimal single plan

# Severity weights for confidence score deductions
CHECK_WEIGHTS: Dict[str, int] = {
    "CRITICAL": 20,
    "HIGH": 12,
    "MEDIUM": 6,
    "LOW": 2,
    "INFO": 0,
}


# =============================================================================
# ENUMS
# =============================================================================

class CheckSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CheckCategory(str, Enum):
    INCOME_CONSISTENCY = "INCOME_CONSISTENCY"
    EMPLOYER_VERIFICATION = "EMPLOYER_VERIFICATION"
    EMPLOYEE_VERIFICATION = "EMPLOYEE_VERIFICATION"
    PAY_RATE_ANALYSIS = "PAY_RATE_ANALYSIS"
    DEDUCTION_ANALYSIS = "DEDUCTION_ANALYSIS"
    TEMPORAL_CONSISTENCY = "TEMPORAL_CONSISTENCY"
    ANOMALY_DETECTION = "ANOMALY_DETECTION"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ValidationCheck:
    """A single cross-validation check result."""
    check_id: str
    category: CheckCategory
    description: str
    passed: bool
    severity: CheckSeverity
    details: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    variance_pct: Optional[float] = None
    weight: int = 0

    def __post_init__(self):
        if self.weight == 0:
            self.weight = CHECK_WEIGHTS.get(self.severity.value, 0)


@dataclass
class DocumentPair:
    """A matched W2 and paystub pair for cross-validation."""
    w2_doc_id: int
    paystub_doc_id: int
    w2_fields: Dict[str, Any]
    paystub_fields: Dict[str, Any]
    w2_confidence: float
    paystub_confidence: float
    employer_name: Optional[str] = None
    tax_year: Optional[int] = None


@dataclass
class CrossValidationResult:
    """Complete result of W2/paystub cross-validation."""
    loan_id: int
    borrower_id: Optional[int]
    document_pairs_analyzed: int
    checks: List[ValidationCheck]
    confidence_score: int  # 0-100 (100 = fully consistent)
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    summary: str
    category_scores: Dict[str, int]  # score per category
    recommendations: List[str]
    w2_doc_ids: List[int]
    paystub_doc_ids: List[int]

    @property
    def passed_checks(self) -> List[ValidationCheck]:
        return [c for c in self.checks if c.passed]

    @property
    def failed_checks(self) -> List[ValidationCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def critical_failures(self) -> List[ValidationCheck]:
        return [c for c in self.checks if not c.passed and c.severity == CheckSeverity.CRITICAL]


# =============================================================================
# NAME MATCHING UTILITIES
# =============================================================================

# Common name variations (subset; full list in fraud_detection_service)
_NAME_VARIATIONS: Dict[str, List[str]] = {
    "william": ["will", "bill", "billy", "wm"],
    "robert": ["rob", "bob", "bobby", "robbie"],
    "richard": ["rich", "rick", "dick"],
    "james": ["jim", "jimmy", "jamie"],
    "john": ["jon", "johnny", "jack"],
    "joseph": ["joe", "joey"],
    "michael": ["mike", "mikey"],
    "thomas": ["tom", "tommy"],
    "charles": ["charlie", "chuck"],
    "christopher": ["chris"],
    "daniel": ["dan", "danny"],
    "matthew": ["matt"],
    "anthony": ["tony"],
    "david": ["dave"],
    "andrew": ["andy", "drew"],
    "nicholas": ["nick"],
    "steven": ["steve", "stephen"],
    "edward": ["ed", "eddie", "ted"],
    "benjamin": ["ben"],
    "elizabeth": ["liz", "beth", "betty", "lizzy", "eliza"],
    "jennifer": ["jen", "jenny"],
    "katherine": ["kate", "kathy", "katie", "cathy", "catherine"],
    "patricia": ["pat", "patty", "tricia"],
    "margaret": ["maggie", "meg", "peggy"],
    "jessica": ["jess", "jessie"],
    "susan": ["sue", "susie"],
    "deborah": ["deb", "debbie", "debra"],
    "rebecca": ["becky", "becca"],
    "timothy": ["tim"],
    "samuel": ["sam"],
    "alexander": ["alex"],
    "gregory": ["greg"],
    "kenneth": ["ken", "kenny"],
    "ronald": ["ron", "ronnie"],
    "donald": ["don", "donnie"],
    "frederick": ["fred", "freddy"],
    "lawrence": ["larry"],
}

_NAME_REVERSE: Dict[str, str] = {}
for _formal, _variants in _NAME_VARIATIONS.items():
    _NAME_REVERSE[_formal] = _formal
    for _v in _variants:
        _NAME_REVERSE[_v] = _formal


def _normalize_name(name: Optional[str]) -> str:
    """Normalize a name for comparison: lowercase, strip suffixes, punctuation."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in (" jr", " jr.", " sr", " sr.", " ii", " iii", " iv"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    # Remove punctuation
    name = re.sub(r"[^a-z\s]", "", name)
    return " ".join(name.split())


def _names_match(name_a: Optional[str], name_b: Optional[str]) -> Tuple[bool, str]:
    """
    Compare two names allowing for common variations.

    Returns:
        (match, detail) where detail explains the comparison outcome.
    """
    if not name_a or not name_b:
        return False, "One or both names missing"

    norm_a = _normalize_name(name_a)
    norm_b = _normalize_name(name_b)

    if norm_a == norm_b:
        return True, "Exact match"

    parts_a = norm_a.split()
    parts_b = norm_b.split()

    # Last name must match
    if parts_a and parts_b and parts_a[-1] != parts_b[-1]:
        return False, f"Last name mismatch: '{parts_a[-1]}' vs '{parts_b[-1]}'"

    # Check first name variations
    if parts_a and parts_b:
        first_a = _NAME_REVERSE.get(parts_a[0], parts_a[0])
        first_b = _NAME_REVERSE.get(parts_b[0], parts_b[0])
        if first_a == first_b:
            return True, "First name variation match"

    # Check if one is initial of the other (e.g., "J" vs "James")
    if parts_a and parts_b:
        if len(parts_a[0]) == 1 and parts_b[0].startswith(parts_a[0]):
            return True, "Initial matches first name"
        if len(parts_b[0]) == 1 and parts_a[0].startswith(parts_b[0]):
            return True, "Initial matches first name"

    return False, f"Name mismatch: '{name_a}' vs '{name_b}'"


def _normalize_employer_name(name: Optional[str]) -> str:
    """Normalize employer name for comparison: remove Inc/LLC/Corp suffixes, punctuation."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common business suffixes
    for suffix in (
        " inc", " inc.", " incorporated",
        " llc", " l.l.c.", " l.l.c",
        " corp", " corp.", " corporation",
        " co", " co.", " company",
        " ltd", " ltd.", " limited",
        " lp", " l.p.",
        " plc", " p.l.c.",
        " dba", " d/b/a",
    ):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return " ".join(name.split())


def _fuzzy_employer_match(name_a: Optional[str], name_b: Optional[str]) -> Tuple[bool, float]:
    """
    Fuzzy-match two employer names.

    Returns:
        (match, similarity_ratio) where similarity_ratio is 0.0-1.0.
    """
    norm_a = _normalize_employer_name(name_a)
    norm_b = _normalize_employer_name(name_b)

    if not norm_a or not norm_b:
        return False, 0.0

    if norm_a == norm_b:
        return True, 1.0

    # Token-based similarity: how many words overlap
    tokens_a = set(norm_a.split())
    tokens_b = set(norm_b.split())
    if not tokens_a or not tokens_b:
        return False, 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)

    # Also check if one contains the other
    if norm_a in norm_b or norm_b in norm_a:
        containment_ratio = min(len(norm_a), len(norm_b)) / max(len(norm_a), len(norm_b))
        jaccard = max(jaccard, containment_ratio)

    return jaccard >= 0.6, jaccard


# =============================================================================
# NUMERIC UTILITIES
# =============================================================================

def _to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        if not cleaned or cleaned == "-":
            return ZERO
        return Decimal(cleaned).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return ZERO


def _pct_variance(expected: Decimal, actual: Decimal) -> Optional[Decimal]:
    """Calculate percentage variance: ((actual - expected) / expected) * 100."""
    if expected == ZERO:
        return None
    return ((actual - expected) / expected * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _is_round_number(value: Decimal, threshold: Decimal = Decimal("100")) -> bool:
    """Check if a monetary value is suspiciously round (divisible by threshold)."""
    if value <= ZERO:
        return False
    return value % threshold == ZERO


def _format_currency(amount: Decimal) -> str:
    """Format a Decimal as currency string."""
    return f"${float(amount):,.2f}"


# =============================================================================
# W2/PAYSTUB CROSS-VALIDATION SERVICE
# =============================================================================

class W2PaystubCrossValidator:
    """
    Cross-validates W2 and paystub documents for income consistency,
    employer/employee identity verification, withholding accuracy,
    deduction reasonableness, temporal consistency, and anomaly detection.

    Produces a confidence score (0-100) with detailed check-level breakdown.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    def validate(
        self,
        loan_id: int,
        borrower_id: Optional[int] = None,
    ) -> CrossValidationResult:
        """
        Run all W2/paystub cross-validation checks for a loan and borrower.

        Loads W2 and paystub documents, pairs them by employer, and runs
        comprehensive checks across each pair.

        Args:
            loan_id: The loan to validate.
            borrower_id: Optional borrower filter. If None, validates all
                         borrowers on the loan.

        Returns:
            CrossValidationResult with confidence score and detailed findings.
        """
        w2_docs, paystub_docs = self._load_documents(loan_id, borrower_id)

        if not w2_docs and not paystub_docs:
            return CrossValidationResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                document_pairs_analyzed=0,
                checks=[],
                confidence_score=0,
                risk_level="LOW",
                summary="No W2 or paystub documents found for cross-validation.",
                category_scores={},
                recommendations=["Upload W2 and paystub documents to enable cross-validation."],
                w2_doc_ids=[],
                paystub_doc_ids=[],
            )

        if not w2_docs:
            return CrossValidationResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                document_pairs_analyzed=0,
                checks=[],
                confidence_score=50,
                risk_level="MEDIUM",
                summary="No W2 documents found. Cannot cross-validate against paystubs.",
                category_scores={},
                recommendations=["Upload W2 documents for the most recent tax year."],
                w2_doc_ids=[],
                paystub_doc_ids=[d["doc_id"] for d in paystub_docs],
            )

        if not paystub_docs:
            return CrossValidationResult(
                loan_id=loan_id,
                borrower_id=borrower_id,
                document_pairs_analyzed=0,
                checks=[],
                confidence_score=50,
                risk_level="MEDIUM",
                summary="No paystub documents found. Cannot cross-validate against W2.",
                category_scores={},
                recommendations=["Upload recent paystubs (within 30 days)."],
                w2_doc_ids=[d["doc_id"] for d in w2_docs],
                paystub_doc_ids=[],
            )

        # Pair documents by employer
        pairs = self._pair_documents(w2_docs, paystub_docs)

        all_checks: List[ValidationCheck] = []

        for pair in pairs:
            all_checks.extend(self._run_income_consistency_checks(pair))
            all_checks.extend(self._run_employer_verification_checks(pair))
            all_checks.extend(self._run_employee_verification_checks(pair))
            all_checks.extend(self._run_pay_rate_analysis(pair))
            all_checks.extend(self._run_deduction_analysis(pair))
            all_checks.extend(self._run_temporal_consistency_checks(pair))
            all_checks.extend(self._run_anomaly_detection(pair))

        # Calculate scores
        confidence_score, category_scores = self._calculate_confidence_score(all_checks)
        risk_level = self._determine_risk_level(confidence_score, all_checks)
        recommendations = self._build_recommendations(all_checks, risk_level)
        summary = self._build_summary(len(pairs), all_checks, confidence_score, risk_level)

        return CrossValidationResult(
            loan_id=loan_id,
            borrower_id=borrower_id,
            document_pairs_analyzed=len(pairs),
            checks=all_checks,
            confidence_score=confidence_score,
            risk_level=risk_level,
            summary=summary,
            category_scores=category_scores,
            recommendations=recommendations,
            w2_doc_ids=[d["doc_id"] for d in w2_docs],
            paystub_doc_ids=[d["doc_id"] for d in paystub_docs],
        )

    # =========================================================================
    # 2. DOCUMENT LOADING AND PAIRING
    # =========================================================================

    def _load_documents(
        self,
        loan_id: int,
        borrower_id: Optional[int],
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Load W2 and paystub documents with their extracted fields from
        smart_documents and smart_document_extractions.

        Returns:
            (w2_docs, paystub_docs) each as list of dicts with keys:
            doc_id, doc_type, extracted_fields, overall_confidence, uploaded_at.
        """
        params: Dict[str, Any] = {"loan_id": loan_id}
        borrower_filter = ""
        if borrower_id is not None:
            borrower_filter = "AND sd.borrower_id = :borrower_id"
            params["borrower_id"] = borrower_id

        cross_val_query = (
            "SELECT"
            " sd.id AS doc_id,"
            " sd.doc_type,"
            " sd.uploaded_at,"
            " sde.extracted_fields,"
            " sde.confidence_scores,"
            " sde.overall_confidence"
            " FROM smart_documents sd"
            " LEFT JOIN smart_document_extractions sde"
            "     ON sde.document_id = sd.id"
            " WHERE sd.loan_id = :loan_id"
            "   AND sd.doc_type IN ('W2', 'PAYSTUB')"
            "   AND sd.status != 'REJECTED'"
            "   " + borrower_filter
            + " ORDER BY sd.doc_type, sd.uploaded_at DESC"
        )
        rows = self.db.execute(text(cross_val_query), params).fetchall()

        w2_docs: List[Dict] = []
        paystub_docs: List[Dict] = []

        for row in rows:
            extracted = row.extracted_fields if row.extracted_fields else {}
            if isinstance(extracted, str):
                import json
                try:
                    extracted = json.loads(extracted)
                except (ValueError, TypeError):
                    extracted = {}

            doc = {
                "doc_id": row.doc_id,
                "doc_type": row.doc_type,
                "extracted_fields": extracted,
                "overall_confidence": row.overall_confidence or 50,
                "uploaded_at": row.uploaded_at,
                "confidence_scores": row.confidence_scores if row.confidence_scores else {},
            }

            if row.doc_type == "W2":
                w2_docs.append(doc)
            elif row.doc_type == "PAYSTUB":
                paystub_docs.append(doc)

        return w2_docs, paystub_docs

    def _pair_documents(
        self,
        w2_docs: List[Dict],
        paystub_docs: List[Dict],
    ) -> List[DocumentPair]:
        """
        Pair W2 and paystub documents by employer name.

        If no employer match is found, pairs are created by position (first W2
        with first paystub). Multiple paystubs may pair with the same W2
        (e.g., multiple pay periods from the same employer).
        """
        pairs: List[DocumentPair] = []
        used_paystub_ids: set = set()

        for w2 in w2_docs:
            w2_fields = w2["extracted_fields"]
            w2_employer = w2_fields.get("employer_name", "")
            w2_tax_year = w2_fields.get("tax_year")

            best_paystub = None
            best_similarity = 0.0

            for ps in paystub_docs:
                if ps["doc_id"] in used_paystub_ids:
                    continue
                ps_employer = ps["extracted_fields"].get("employer_name", "")
                match, similarity = _fuzzy_employer_match(w2_employer, ps_employer)
                if match and similarity > best_similarity:
                    best_similarity = similarity
                    best_paystub = ps

            # Fallback: use first unmatched paystub
            if best_paystub is None:
                for ps in paystub_docs:
                    if ps["doc_id"] not in used_paystub_ids:
                        best_paystub = ps
                        break

            if best_paystub is not None:
                used_paystub_ids.add(best_paystub["doc_id"])
                pairs.append(DocumentPair(
                    w2_doc_id=w2["doc_id"],
                    paystub_doc_id=best_paystub["doc_id"],
                    w2_fields=w2_fields,
                    paystub_fields=best_paystub["extracted_fields"],
                    w2_confidence=w2["overall_confidence"],
                    paystub_confidence=best_paystub["overall_confidence"],
                    employer_name=w2_employer or best_paystub["extracted_fields"].get("employer_name"),
                    tax_year=int(w2_tax_year) if w2_tax_year else None,
                ))

        return pairs

    # =========================================================================
    # 3. INCOME CONSISTENCY CHECKS
    # =========================================================================

    def _run_income_consistency_checks(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Compare income figures between W2 and paystub:
        - YTD gross vs W2 Box 1 (proportional)
        - Projected annual income from paystub vs W2
        - Federal withholding YTD vs W2 Box 2 (proportional)
        - Social Security wages (W2 Box 3)
        - Medicare wages (W2 Box 5)
        - State withholding comparison
        """
        checks: List[ValidationCheck] = []
        w2 = pair.w2_fields
        ps = pair.paystub_fields

        # --- YTD Gross vs W2 Box 1 (wages_tips_compensation) ---
        ytd_gross = _to_decimal(ps.get("ytd_gross_pay") or ps.get("ytd_gross_earnings"))
        w2_box1 = _to_decimal(w2.get("wages_tips_compensation"))
        proportion = self._calculate_ytd_proportion(ps)

        if ytd_gross > ZERO and w2_box1 > ZERO and proportion is not None and proportion > ZERO:
            expected_ytd = (w2_box1 * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_ytd, ytd_gross)

            passed = variance is not None and abs(variance) <= INCOME_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else (
                CheckSeverity.HIGH if variance is not None and abs(variance) > Decimal("15") else CheckSeverity.MEDIUM
            )

            checks.append(ValidationCheck(
                check_id="INC_YTD_VS_W2_BOX1",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="Paystub YTD gross vs W2 Box 1 (proportional to pay period)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD gross {_format_currency(ytd_gross)} vs expected "
                    f"{_format_currency(expected_ytd)} ({float(proportion)*100:.0f}% of W2 "
                    f"{_format_currency(w2_box1)})"
                ),
                expected_value=_format_currency(expected_ytd),
                actual_value=_format_currency(ytd_gross),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- Projected annual from paystub vs W2 ---
        gross_pay = _to_decimal(ps.get("gross_pay"))
        pay_freq = (ps.get("pay_frequency") or "").upper()
        multiplier = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq)

        if gross_pay > ZERO and multiplier and w2_box1 > ZERO:
            projected_annual = (gross_pay * Decimal(multiplier)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(w2_box1, projected_annual)

            passed = variance is not None and abs(variance) <= INCOME_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else (
                CheckSeverity.HIGH if variance is not None and abs(variance) > Decimal("20") else CheckSeverity.MEDIUM
            )

            checks.append(ValidationCheck(
                check_id="INC_PROJECTED_VS_W2",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="Projected annual income from paystub vs W2 Box 1",
                passed=passed,
                severity=severity,
                details=(
                    f"Projected annual {_format_currency(projected_annual)} "
                    f"({_format_currency(gross_pay)} x {multiplier} {pay_freq}) vs "
                    f"W2 {_format_currency(w2_box1)}"
                ),
                expected_value=_format_currency(w2_box1),
                actual_value=_format_currency(projected_annual),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- Federal withholding YTD vs W2 Box 2 ---
        ytd_fed_tax = _to_decimal(ps.get("ytd_federal_tax") or ps.get("ytd_federal_withholding"))
        w2_box2 = _to_decimal(w2.get("federal_income_tax_withheld"))

        if ytd_fed_tax > ZERO and w2_box2 > ZERO and proportion is not None and proportion > ZERO:
            expected_fed = (w2_box2 * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_fed, ytd_fed_tax)

            passed = variance is not None and abs(variance) <= WITHHOLDING_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else (
                CheckSeverity.HIGH if variance is not None and abs(variance) > Decimal("20") else CheckSeverity.MEDIUM
            )

            checks.append(ValidationCheck(
                check_id="INC_FED_WITHHOLDING",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="Federal withholding YTD vs W2 Box 2 (proportional)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD federal tax {_format_currency(ytd_fed_tax)} vs expected "
                    f"{_format_currency(expected_fed)} from W2 {_format_currency(w2_box2)}"
                ),
                expected_value=_format_currency(expected_fed),
                actual_value=_format_currency(ytd_fed_tax),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- Social Security wages (W2 Box 3 vs paystub YTD) ---
        ytd_ss_wages = _to_decimal(ps.get("ytd_social_security_wages") or ps.get("ytd_ss_wages"))
        w2_box3 = _to_decimal(w2.get("social_security_wages"))

        if ytd_ss_wages > ZERO and w2_box3 > ZERO and proportion is not None and proportion > ZERO:
            expected_ss = (w2_box3 * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            # Cap at SS wage base
            tax_year = pair.tax_year or date.today().year
            ss_cap = SOCIAL_SECURITY_WAGE_BASE.get(tax_year, Decimal("176100"))
            expected_ss = min(expected_ss, ss_cap)

            variance = _pct_variance(expected_ss, ytd_ss_wages)
            passed = variance is not None and abs(variance) <= WAGE_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else CheckSeverity.MEDIUM

            checks.append(ValidationCheck(
                check_id="INC_SS_WAGES",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="Social Security wages: paystub YTD vs W2 Box 3 (proportional)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD SS wages {_format_currency(ytd_ss_wages)} vs expected "
                    f"{_format_currency(expected_ss)} from W2 {_format_currency(w2_box3)}"
                ),
                expected_value=_format_currency(expected_ss),
                actual_value=_format_currency(ytd_ss_wages),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- Medicare wages (W2 Box 5 vs paystub YTD) ---
        ytd_medicare_wages = _to_decimal(ps.get("ytd_medicare_wages"))
        w2_box5 = _to_decimal(w2.get("medicare_wages_tips"))

        if ytd_medicare_wages > ZERO and w2_box5 > ZERO and proportion is not None and proportion > ZERO:
            expected_med = (w2_box5 * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_med, ytd_medicare_wages)
            passed = variance is not None and abs(variance) <= WAGE_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else CheckSeverity.MEDIUM

            checks.append(ValidationCheck(
                check_id="INC_MEDICARE_WAGES",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="Medicare wages: paystub YTD vs W2 Box 5 (proportional)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD Medicare wages {_format_currency(ytd_medicare_wages)} vs expected "
                    f"{_format_currency(expected_med)} from W2 {_format_currency(w2_box5)}"
                ),
                expected_value=_format_currency(expected_med),
                actual_value=_format_currency(ytd_medicare_wages),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- State withholding comparison ---
        ytd_state_tax = _to_decimal(ps.get("ytd_state_tax") or ps.get("ytd_state_withholding"))
        w2_state_tax = _to_decimal(w2.get("state_income_tax"))

        if ytd_state_tax > ZERO and w2_state_tax > ZERO and proportion is not None and proportion > ZERO:
            expected_state = (w2_state_tax * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_state, ytd_state_tax)
            passed = variance is not None and abs(variance) <= WITHHOLDING_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else CheckSeverity.LOW

            checks.append(ValidationCheck(
                check_id="INC_STATE_WITHHOLDING",
                category=CheckCategory.INCOME_CONSISTENCY,
                description="State withholding YTD vs W2 state income tax (proportional)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD state tax {_format_currency(ytd_state_tax)} vs expected "
                    f"{_format_currency(expected_state)} from W2 {_format_currency(w2_state_tax)}"
                ),
                expected_value=_format_currency(expected_state),
                actual_value=_format_currency(ytd_state_tax),
                variance_pct=float(variance) if variance is not None else None,
            ))

        return checks

    def _calculate_ytd_proportion(self, paystub_fields: Dict[str, Any]) -> Optional[Decimal]:
        """
        Calculate the proportion of the year elapsed based on the paystub's
        pay period end date.

        Returns a Decimal between 0 and 1, or None if the date is unavailable.
        """
        pay_period_end = paystub_fields.get("pay_period_end") or paystub_fields.get("pay_date")
        if not pay_period_end:
            return None

        try:
            if isinstance(pay_period_end, str):
                period_end = datetime.strptime(pay_period_end, "%Y-%m-%d").date()
            elif isinstance(pay_period_end, datetime):
                period_end = pay_period_end.date()
            elif isinstance(pay_period_end, date):
                period_end = pay_period_end
            else:
                return None
        except (ValueError, TypeError):
            return None

        year_start = date(period_end.year, 1, 1)
        year_end = date(period_end.year, 12, 31)
        total_days = (year_end - year_start).days + 1
        elapsed_days = (period_end - year_start).days + 1

        return (Decimal(elapsed_days) / Decimal(total_days)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

    # =========================================================================
    # 4. EMPLOYER VERIFICATION CHECKS
    # =========================================================================

    def _run_employer_verification_checks(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Verify employer identity consistency between W2 and paystub:
        - Employer name exact and fuzzy match
        - EIN consistency (W2 Box b)
        - Employer address consistency
        - State employer ID match
        """
        checks: List[ValidationCheck] = []
        w2 = pair.w2_fields
        ps = pair.paystub_fields

        # --- Employer name ---
        w2_employer = w2.get("employer_name", "")
        ps_employer = ps.get("employer_name", "")

        if w2_employer and ps_employer:
            exact_match = _normalize_employer_name(w2_employer) == _normalize_employer_name(ps_employer)
            fuzzy_match, similarity = _fuzzy_employer_match(w2_employer, ps_employer)

            if exact_match:
                checks.append(ValidationCheck(
                    check_id="EMP_NAME_EXACT",
                    category=CheckCategory.EMPLOYER_VERIFICATION,
                    description="Employer name exact match between W2 and paystub",
                    passed=True,
                    severity=CheckSeverity.INFO,
                    details=f"Employer name matches: '{w2_employer}'",
                ))
            elif fuzzy_match:
                checks.append(ValidationCheck(
                    check_id="EMP_NAME_FUZZY",
                    category=CheckCategory.EMPLOYER_VERIFICATION,
                    description="Employer name fuzzy match between W2 and paystub",
                    passed=True,
                    severity=CheckSeverity.LOW,
                    details=(
                        f"Employer names similar ({similarity:.0%}): "
                        f"W2 '{w2_employer}' vs paystub '{ps_employer}'"
                    ),
                ))
            else:
                checks.append(ValidationCheck(
                    check_id="EMP_NAME_MISMATCH",
                    category=CheckCategory.EMPLOYER_VERIFICATION,
                    description="Employer name mismatch between W2 and paystub",
                    passed=False,
                    severity=CheckSeverity.CRITICAL,
                    details=(
                        f"W2 employer '{w2_employer}' does not match "
                        f"paystub employer '{ps_employer}' (similarity {similarity:.0%})"
                    ),
                    expected_value=w2_employer,
                    actual_value=ps_employer,
                ))
        elif not w2_employer and not ps_employer:
            checks.append(ValidationCheck(
                check_id="EMP_NAME_MISSING",
                category=CheckCategory.EMPLOYER_VERIFICATION,
                description="Employer name missing from both W2 and paystub",
                passed=False,
                severity=CheckSeverity.HIGH,
                details="No employer name extracted from either document",
            ))

        # --- EIN (W2 Box b) ---
        w2_ein = (w2.get("employer_ein") or w2.get("ein") or "").replace("-", "").strip()
        ps_ein = (ps.get("employer_ein") or ps.get("ein") or "").replace("-", "").strip()

        if w2_ein and ps_ein:
            ein_match = w2_ein == ps_ein
            checks.append(ValidationCheck(
                check_id="EMP_EIN_MATCH",
                category=CheckCategory.EMPLOYER_VERIFICATION,
                description="Employer EIN consistency (W2 Box b vs paystub)",
                passed=ein_match,
                severity=CheckSeverity.INFO if ein_match else CheckSeverity.CRITICAL,
                details=(
                    f"EIN match: {w2_ein}" if ein_match else
                    f"EIN mismatch: W2 '{w2_ein}' vs paystub '{ps_ein}'"
                ),
                expected_value=w2_ein,
                actual_value=ps_ein,
            ))
        elif w2_ein and not ps_ein:
            checks.append(ValidationCheck(
                check_id="EMP_EIN_PAYSTUB_MISSING",
                category=CheckCategory.EMPLOYER_VERIFICATION,
                description="Employer EIN present on W2 but not on paystub",
                passed=True,
                severity=CheckSeverity.INFO,
                details=f"W2 EIN {w2_ein}; paystub EIN not available (normal for paystubs)",
            ))

        # --- Employer address ---
        w2_addr = _normalize_address(w2.get("employer_address"))
        ps_addr = _normalize_address(ps.get("employer_address"))

        if w2_addr and ps_addr:
            addr_match = w2_addr == ps_addr or w2_addr in ps_addr or ps_addr in w2_addr
            checks.append(ValidationCheck(
                check_id="EMP_ADDRESS_MATCH",
                category=CheckCategory.EMPLOYER_VERIFICATION,
                description="Employer address consistency between W2 and paystub",
                passed=addr_match,
                severity=CheckSeverity.INFO if addr_match else CheckSeverity.LOW,
                details=(
                    "Employer addresses consistent" if addr_match else
                    f"Address difference: W2 '{w2.get('employer_address')}' vs "
                    f"paystub '{ps.get('employer_address')}'"
                ),
            ))

        # --- State employer ID ---
        w2_state_id = (w2.get("state_employer_id") or "").strip()
        ps_state_id = (ps.get("state_employer_id") or "").strip()

        if w2_state_id and ps_state_id:
            state_id_match = w2_state_id == ps_state_id
            checks.append(ValidationCheck(
                check_id="EMP_STATE_ID_MATCH",
                category=CheckCategory.EMPLOYER_VERIFICATION,
                description="State employer ID consistency",
                passed=state_id_match,
                severity=CheckSeverity.INFO if state_id_match else CheckSeverity.MEDIUM,
                details=(
                    f"State employer ID matches: {w2_state_id}" if state_id_match else
                    f"State employer ID mismatch: W2 '{w2_state_id}' vs paystub '{ps_state_id}'"
                ),
                expected_value=w2_state_id,
                actual_value=ps_state_id,
            ))

        return checks

    # =========================================================================
    # 5. EMPLOYEE VERIFICATION CHECKS
    # =========================================================================

    def _run_employee_verification_checks(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Verify employee identity consistency:
        - Employee name match
        - SSN last 4 consistency (if visible)
        - Address consistency
        """
        checks: List[ValidationCheck] = []
        w2 = pair.w2_fields
        ps = pair.paystub_fields

        # --- Employee name ---
        w2_name = w2.get("employee_name") or ""
        ps_name = ps.get("employee_name") or ""

        if w2_name and ps_name:
            match, detail = _names_match(w2_name, ps_name)
            checks.append(ValidationCheck(
                check_id="EE_NAME_MATCH",
                category=CheckCategory.EMPLOYEE_VERIFICATION,
                description="Employee name consistency between W2 and paystub",
                passed=match,
                severity=CheckSeverity.INFO if match else CheckSeverity.CRITICAL,
                details=(
                    f"Employee name consistent: {detail}" if match else
                    f"Employee name mismatch: W2 '{w2_name}' vs paystub '{ps_name}' ({detail})"
                ),
                expected_value=w2_name,
                actual_value=ps_name,
            ))
        elif not w2_name and not ps_name:
            checks.append(ValidationCheck(
                check_id="EE_NAME_MISSING",
                category=CheckCategory.EMPLOYEE_VERIFICATION,
                description="Employee name missing from both documents",
                passed=False,
                severity=CheckSeverity.HIGH,
                details="No employee name extracted from either W2 or paystub",
            ))

        # --- SSN last 4 ---
        w2_ssn = (w2.get("ssn_last4") or w2.get("employee_ssn_last4") or "").strip()
        ps_ssn = (ps.get("ssn_last4") or ps.get("employee_ssn_last4") or "").strip()

        # Normalize to last 4 digits only
        if w2_ssn and len(w2_ssn) > 4:
            w2_ssn = w2_ssn[-4:]
        if ps_ssn and len(ps_ssn) > 4:
            ps_ssn = ps_ssn[-4:]

        if w2_ssn and ps_ssn:
            ssn_match = w2_ssn == ps_ssn
            checks.append(ValidationCheck(
                check_id="EE_SSN_MATCH",
                category=CheckCategory.EMPLOYEE_VERIFICATION,
                description="SSN last 4 digits consistency between W2 and paystub",
                passed=ssn_match,
                severity=CheckSeverity.INFO if ssn_match else CheckSeverity.CRITICAL,
                details=(
                    f"SSN last 4 match: ***-**-{w2_ssn}" if ssn_match else
                    f"SSN last 4 MISMATCH: W2 '***-**-{w2_ssn}' vs paystub '***-**-{ps_ssn}'"
                ),
            ))

        # --- Employee address ---
        w2_addr = _normalize_address(w2.get("employee_address"))
        ps_addr = _normalize_address(ps.get("employee_address"))

        if w2_addr and ps_addr:
            addr_match = w2_addr == ps_addr or w2_addr in ps_addr or ps_addr in w2_addr
            checks.append(ValidationCheck(
                check_id="EE_ADDRESS_MATCH",
                category=CheckCategory.EMPLOYEE_VERIFICATION,
                description="Employee address consistency between W2 and paystub",
                passed=addr_match,
                severity=CheckSeverity.INFO if addr_match else CheckSeverity.LOW,
                details=(
                    "Employee addresses consistent" if addr_match else
                    f"Address difference: W2 '{w2.get('employee_address')}' vs "
                    f"paystub '{ps.get('employee_address')}'"
                ),
            ))

        return checks

    # =========================================================================
    # 6. PAY RATE ANALYSIS
    # =========================================================================

    def _run_pay_rate_analysis(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Analyze pay rate consistency:
        - Hourly rate * hours = gross check
        - Salary / pay periods = per-period check
        - OT rate = 1.5x regular (verify)
        - Commission percentage consistency
        """
        checks: List[ValidationCheck] = []
        ps = pair.paystub_fields

        gross_pay = _to_decimal(ps.get("gross_pay"))
        regular_hours = _to_decimal(ps.get("regular_hours"))
        hourly_rate = _to_decimal(ps.get("hourly_rate") or ps.get("pay_rate"))
        ot_hours = _to_decimal(ps.get("overtime_hours") or ps.get("ot_hours"))
        ot_rate = _to_decimal(ps.get("overtime_rate") or ps.get("ot_rate"))
        ot_pay = _to_decimal(ps.get("overtime_pay") or ps.get("ot_pay"))
        regular_pay = _to_decimal(ps.get("regular_pay") or ps.get("regular_earnings"))

        # --- Hourly rate * hours = gross check ---
        if hourly_rate > ZERO and regular_hours > ZERO:
            expected_regular = (hourly_rate * regular_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            expected_ot = ZERO

            if ot_hours > ZERO:
                effective_ot_rate = ot_rate if ot_rate > ZERO else (hourly_rate * STANDARD_OT_MULTIPLIER)
                expected_ot = (effective_ot_rate * ot_hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            expected_gross = expected_regular + expected_ot
            variance = _pct_variance(expected_gross, gross_pay)

            # Allow small tolerance for rounding, other earnings
            passed = variance is not None and abs(variance) <= Decimal("3")
            severity = CheckSeverity.INFO if passed else CheckSeverity.MEDIUM

            checks.append(ValidationCheck(
                check_id="PAY_RATE_CALC",
                category=CheckCategory.PAY_RATE_ANALYSIS,
                description="Hourly rate x hours = gross pay verification",
                passed=passed,
                severity=severity,
                details=(
                    f"Rate {_format_currency(hourly_rate)}/hr x {regular_hours} hrs = "
                    f"{_format_currency(expected_regular)} regular"
                    f"{f' + {_format_currency(expected_ot)} OT' if expected_ot > ZERO else ''}"
                    f" = {_format_currency(expected_gross)} expected vs "
                    f"{_format_currency(gross_pay)} actual"
                ),
                expected_value=_format_currency(expected_gross),
                actual_value=_format_currency(gross_pay),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- Salary / pay periods = per-period check ---
        w2_box1 = _to_decimal(pair.w2_fields.get("wages_tips_compensation"))
        pay_freq = (ps.get("pay_frequency") or "").upper()
        multiplier = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq)

        if w2_box1 > ZERO and multiplier and gross_pay > ZERO:
            expected_per_period = (w2_box1 / Decimal(multiplier)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_per_period, gross_pay)

            passed = variance is not None and abs(variance) <= INCOME_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else CheckSeverity.MEDIUM

            checks.append(ValidationCheck(
                check_id="PAY_SALARY_PERIOD",
                category=CheckCategory.PAY_RATE_ANALYSIS,
                description="W2 annual / pay periods = per-period gross check",
                passed=passed,
                severity=severity,
                details=(
                    f"W2 {_format_currency(w2_box1)} / {multiplier} periods = "
                    f"{_format_currency(expected_per_period)} expected vs "
                    f"{_format_currency(gross_pay)} actual per period"
                ),
                expected_value=_format_currency(expected_per_period),
                actual_value=_format_currency(gross_pay),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- OT rate = 1.5x regular verification ---
        if ot_rate > ZERO and hourly_rate > ZERO:
            expected_ot_rate = (hourly_rate * STANDARD_OT_MULTIPLIER).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            ot_match = ot_rate == expected_ot_rate

            # Allow some tolerance (double-time, custom OT agreements)
            ot_multiplier_actual = (ot_rate / hourly_rate).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            reasonable = ot_multiplier_actual >= Decimal("1.4") and ot_multiplier_actual <= Decimal("2.5")

            checks.append(ValidationCheck(
                check_id="PAY_OT_RATE",
                category=CheckCategory.PAY_RATE_ANALYSIS,
                description="Overtime rate is 1.5x regular rate (FLSA standard)",
                passed=ot_match or reasonable,
                severity=CheckSeverity.INFO if (ot_match or reasonable) else CheckSeverity.MEDIUM,
                details=(
                    f"OT rate {_format_currency(ot_rate)} = {float(ot_multiplier_actual):.2f}x "
                    f"regular rate {_format_currency(hourly_rate)} "
                    f"(expected 1.5x = {_format_currency(expected_ot_rate)})"
                ),
            ))

        # --- Commission percentage consistency ---
        commission_pay = _to_decimal(ps.get("commission") or ps.get("commission_pay"))
        ytd_commission = _to_decimal(ps.get("ytd_commission"))
        ytd_gross_for_comm = _to_decimal(ps.get("ytd_gross_pay") or ps.get("ytd_gross_earnings"))

        if commission_pay > ZERO and gross_pay > ZERO:
            comm_pct_current = (commission_pay / gross_pay * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if ytd_commission > ZERO and ytd_gross_for_comm > ZERO:
                comm_pct_ytd = (ytd_commission / ytd_gross_for_comm * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                variance = abs(comm_pct_current - comm_pct_ytd)

                passed = variance <= Decimal("10")
                checks.append(ValidationCheck(
                    check_id="PAY_COMMISSION_PCT",
                    category=CheckCategory.PAY_RATE_ANALYSIS,
                    description="Commission percentage consistency: current period vs YTD",
                    passed=passed,
                    severity=CheckSeverity.INFO if passed else CheckSeverity.LOW,
                    details=(
                        f"Current period commission {float(comm_pct_current):.1f}% of gross vs "
                        f"YTD {float(comm_pct_ytd):.1f}% (variance {float(variance):.1f}%)"
                    ),
                ))

        return checks

    # =========================================================================
    # 7. DEDUCTION ANALYSIS
    # =========================================================================

    def _run_deduction_analysis(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Analyze deductions for reasonableness and consistency:
        - 401k contributions match
        - Health insurance deductions reasonable
        - Garnishments/liens flagged
        - Pre-tax vs post-tax categorization
        """
        checks: List[ValidationCheck] = []
        w2 = pair.w2_fields
        ps = pair.paystub_fields
        proportion = self._calculate_ytd_proportion(ps)

        # --- 401k / retirement contributions ---
        ytd_401k = _to_decimal(ps.get("ytd_401k") or ps.get("ytd_retirement"))
        w2_box12_d = _to_decimal(w2.get("box_12d") or w2.get("retirement_plan_contributions"))

        if ytd_401k > ZERO and w2_box12_d > ZERO and proportion is not None and proportion > ZERO:
            expected_401k = (w2_box12_d * proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            variance = _pct_variance(expected_401k, ytd_401k)

            passed = variance is not None and abs(variance) <= WITHHOLDING_TOLERANCE_PCT
            severity = CheckSeverity.INFO if passed else CheckSeverity.LOW

            checks.append(ValidationCheck(
                check_id="DED_401K_MATCH",
                category=CheckCategory.DEDUCTION_ANALYSIS,
                description="401k/retirement YTD contributions vs W2 Box 12d (proportional)",
                passed=passed,
                severity=severity,
                details=(
                    f"Paystub YTD 401k {_format_currency(ytd_401k)} vs expected "
                    f"{_format_currency(expected_401k)} from W2 {_format_currency(w2_box12_d)}"
                ),
                expected_value=_format_currency(expected_401k),
                actual_value=_format_currency(ytd_401k),
                variance_pct=float(variance) if variance is not None else None,
            ))

        # --- 401k contribution limit check ---
        if ytd_401k > ZERO and proportion is not None and proportion > ZERO:
            projected_annual_401k = (ytd_401k / proportion).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            max_401k = MAX_401K_CONTRIBUTION_OVER_50  # conservative upper bound

            if projected_annual_401k > max_401k:
                checks.append(ValidationCheck(
                    check_id="DED_401K_LIMIT",
                    category=CheckCategory.DEDUCTION_ANALYSIS,
                    description="401k contributions exceeding annual limit",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=(
                        f"Projected annual 401k {_format_currency(projected_annual_401k)} "
                        f"exceeds max limit {_format_currency(max_401k)}"
                    ),
                ))

        # --- Health insurance reasonableness ---
        health_deduction = _to_decimal(ps.get("health_insurance") or ps.get("medical_deduction"))
        ytd_health = _to_decimal(ps.get("ytd_health_insurance") or ps.get("ytd_medical"))

        if health_deduction > ZERO:
            pay_freq = (ps.get("pay_frequency") or "MONTHLY").upper()
            multiplier = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq, 12)
            projected_annual_health = (health_deduction * Decimal(multiplier)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            reasonable = MIN_HEALTH_INSURANCE_ANNUAL <= projected_annual_health <= MAX_HEALTH_INSURANCE_ANNUAL
            checks.append(ValidationCheck(
                check_id="DED_HEALTH_REASONABLE",
                category=CheckCategory.DEDUCTION_ANALYSIS,
                description="Health insurance deduction reasonableness",
                passed=reasonable,
                severity=CheckSeverity.INFO if reasonable else CheckSeverity.LOW,
                details=(
                    f"Projected annual health insurance {_format_currency(projected_annual_health)} "
                    f"({'within' if reasonable else 'outside'} "
                    f"{_format_currency(MIN_HEALTH_INSURANCE_ANNUAL)}-"
                    f"{_format_currency(MAX_HEALTH_INSURANCE_ANNUAL)} range)"
                ),
            ))

        # --- Garnishments / liens flagged ---
        garnishment = _to_decimal(ps.get("garnishment") or ps.get("garnishments"))
        child_support = _to_decimal(ps.get("child_support"))
        tax_levy = _to_decimal(ps.get("tax_levy"))

        garnishment_total = garnishment + child_support + tax_levy
        if garnishment_total > ZERO:
            checks.append(ValidationCheck(
                check_id="DED_GARNISHMENT_FLAG",
                category=CheckCategory.DEDUCTION_ANALYSIS,
                description="Garnishments, liens, or child support present on paystub",
                passed=True,  # Not a failure, but important for underwriting
                severity=CheckSeverity.MEDIUM,
                details=(
                    f"Garnishment/lien deductions detected: {_format_currency(garnishment_total)} per period"
                    f"{f' (garnishment: {_format_currency(garnishment)})' if garnishment > ZERO else ''}"
                    f"{f' (child support: {_format_currency(child_support)})' if child_support > ZERO else ''}"
                    f"{f' (tax levy: {_format_currency(tax_levy)})' if tax_levy > ZERO else ''}"
                ),
            ))

        # --- FICA deductions present ---
        ss_deduction = _to_decimal(ps.get("social_security_tax") or ps.get("fica_ss"))
        medicare_deduction = _to_decimal(ps.get("medicare_tax") or ps.get("fica_medicare"))
        fed_tax_deduction = _to_decimal(ps.get("federal_tax") or ps.get("federal_withholding"))

        missing_std_deductions = []
        if fed_tax_deduction <= ZERO:
            missing_std_deductions.append("federal withholding")
        if ss_deduction <= ZERO:
            missing_std_deductions.append("Social Security (FICA)")
        if medicare_deduction <= ZERO:
            missing_std_deductions.append("Medicare")

        if missing_std_deductions:
            checks.append(ValidationCheck(
                check_id="DED_STANDARD_MISSING",
                category=CheckCategory.DEDUCTION_ANALYSIS,
                description="Standard payroll deductions missing from paystub",
                passed=False,
                severity=CheckSeverity.HIGH,
                details=f"Missing standard deductions: {', '.join(missing_std_deductions)}",
            ))
        else:
            checks.append(ValidationCheck(
                check_id="DED_STANDARD_PRESENT",
                category=CheckCategory.DEDUCTION_ANALYSIS,
                description="Standard payroll deductions (federal, FICA, Medicare) present",
                passed=True,
                severity=CheckSeverity.INFO,
                details="All standard payroll tax deductions present",
            ))

        # --- Pre-tax vs post-tax categorization ---
        pre_tax_total = ytd_401k + ytd_health  # typically pre-tax
        net_pay = _to_decimal(ps.get("net_pay"))
        total_deductions = _to_decimal(ps.get("total_deductions"))

        if net_pay > ZERO and gross_pay_from_ps(ps) > ZERO:
            gross = gross_pay_from_ps(ps)
            implied_deductions = gross - net_pay
            if total_deductions > ZERO:
                ded_match = abs(implied_deductions - total_deductions) <= Decimal("1.00")
                checks.append(ValidationCheck(
                    check_id="DED_TOTAL_RECONCILE",
                    category=CheckCategory.DEDUCTION_ANALYSIS,
                    description="Total deductions reconcile: gross - net = total deductions",
                    passed=ded_match,
                    severity=CheckSeverity.INFO if ded_match else CheckSeverity.MEDIUM,
                    details=(
                        f"Gross {_format_currency(gross)} - Net {_format_currency(net_pay)} = "
                        f"{_format_currency(implied_deductions)} implied deductions vs "
                        f"{_format_currency(total_deductions)} reported total"
                    ),
                ))

        return checks

    # =========================================================================
    # 8. TEMPORAL CONSISTENCY CHECKS
    # =========================================================================

    def _run_temporal_consistency_checks(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Verify temporal consistency:
        - Pay period dates within W2 tax year
        - Hire date on paystub vs employment start
        - YTD accumulation logical
        - Pay frequency consistent
        """
        checks: List[ValidationCheck] = []
        w2 = pair.w2_fields
        ps = pair.paystub_fields

        tax_year = pair.tax_year or date.today().year

        # --- Pay period within W2 tax year ---
        pay_date_str = ps.get("pay_date") or ps.get("pay_period_end")
        if pay_date_str:
            try:
                pay_date = _parse_date(pay_date_str)
                if pay_date:
                    in_year = pay_date.year == tax_year
                    # Allow current year paystubs to validate against prior year W2
                    near_year = abs(pay_date.year - tax_year) <= 1

                    checks.append(ValidationCheck(
                        check_id="TEMP_PAY_PERIOD_YEAR",
                        category=CheckCategory.TEMPORAL_CONSISTENCY,
                        description="Pay period date falls within or near W2 tax year",
                        passed=near_year,
                        severity=CheckSeverity.INFO if in_year else (
                            CheckSeverity.LOW if near_year else CheckSeverity.HIGH
                        ),
                        details=(
                            f"Paystub pay date {pay_date.isoformat()} "
                            f"{'is within' if in_year else 'is near' if near_year else 'does not match'} "
                            f"W2 tax year {tax_year}"
                        ),
                    ))
            except (ValueError, TypeError):
                pass

        # --- Pay period start < pay period end ---
        period_start_str = ps.get("pay_period_start")
        period_end_str = ps.get("pay_period_end")

        if period_start_str and period_end_str:
            period_start = _parse_date(period_start_str)
            period_end = _parse_date(period_end_str)

            if period_start and period_end:
                valid_order = period_start < period_end
                period_length = (period_end - period_start).days

                checks.append(ValidationCheck(
                    check_id="TEMP_PERIOD_ORDER",
                    category=CheckCategory.TEMPORAL_CONSISTENCY,
                    description="Pay period start date precedes end date",
                    passed=valid_order,
                    severity=CheckSeverity.INFO if valid_order else CheckSeverity.CRITICAL,
                    details=(
                        f"Pay period {period_start.isoformat()} to {period_end.isoformat()} "
                        f"({period_length} days)"
                    ),
                ))

                # --- Pay frequency consistent with period length ---
                pay_freq = (ps.get("pay_frequency") or "").upper()
                expected_ranges = {
                    "WEEKLY": (5, 9),
                    "BIWEEKLY": (12, 16),
                    "SEMIMONTHLY": (13, 17),
                    "MONTHLY": (28, 32),
                }

                if pay_freq in expected_ranges:
                    low, high = expected_ranges[pay_freq]
                    freq_consistent = low <= period_length <= high

                    checks.append(ValidationCheck(
                        check_id="TEMP_FREQ_CONSISTENT",
                        category=CheckCategory.TEMPORAL_CONSISTENCY,
                        description="Pay frequency consistent with pay period length",
                        passed=freq_consistent,
                        severity=CheckSeverity.INFO if freq_consistent else CheckSeverity.MEDIUM,
                        details=(
                            f"Pay frequency {pay_freq}: period length {period_length} days "
                            f"({'within' if freq_consistent else 'outside'} "
                            f"expected {low}-{high} days)"
                        ),
                    ))

        # --- YTD accumulation logical ---
        gross_pay = _to_decimal(ps.get("gross_pay"))
        ytd_gross = _to_decimal(ps.get("ytd_gross_pay") or ps.get("ytd_gross_earnings"))

        if gross_pay > ZERO and ytd_gross > ZERO:
            # YTD must be >= current period gross
            ytd_gte_current = ytd_gross >= gross_pay

            checks.append(ValidationCheck(
                check_id="TEMP_YTD_GTE_CURRENT",
                category=CheckCategory.TEMPORAL_CONSISTENCY,
                description="YTD gross >= current period gross",
                passed=ytd_gte_current,
                severity=CheckSeverity.INFO if ytd_gte_current else CheckSeverity.HIGH,
                details=(
                    f"YTD gross {_format_currency(ytd_gross)} "
                    f"{'>=  ' if ytd_gte_current else '< '} "
                    f"current period {_format_currency(gross_pay)}"
                ),
            ))

            # Implied pay periods elapsed
            if gross_pay > ZERO:
                implied_periods = (ytd_gross / gross_pay).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                pay_freq = (ps.get("pay_frequency") or "").upper()
                max_periods = PAY_FREQUENCY_MULTIPLIERS.get(pay_freq, 52)

                reasonable = Decimal("1") <= implied_periods <= Decimal(str(max_periods))
                checks.append(ValidationCheck(
                    check_id="TEMP_YTD_PERIODS",
                    category=CheckCategory.TEMPORAL_CONSISTENCY,
                    description="YTD implies a reasonable number of pay periods elapsed",
                    passed=bool(reasonable),
                    severity=CheckSeverity.INFO if reasonable else CheckSeverity.HIGH,
                    details=(
                        f"YTD / current gross implies ~{float(implied_periods):.1f} periods "
                        f"(max {max_periods} for {pay_freq or 'unknown frequency'})"
                    ),
                ))

        # --- Hire date vs employment start ---
        hire_date_str = ps.get("hire_date") or ps.get("employment_start_date")
        if hire_date_str:
            hire_date = _parse_date(hire_date_str)
            if hire_date:
                # Hire date should not be in the future
                future_hire = hire_date > date.today()
                checks.append(ValidationCheck(
                    check_id="TEMP_HIRE_DATE",
                    category=CheckCategory.TEMPORAL_CONSISTENCY,
                    description="Hire date is not in the future",
                    passed=not future_hire,
                    severity=CheckSeverity.INFO if not future_hire else CheckSeverity.CRITICAL,
                    details=(
                        f"Hire date {hire_date.isoformat()}"
                        f"{' is in the future' if future_hire else ''}"
                    ),
                ))

        return checks

    # =========================================================================
    # 9. ANOMALY DETECTION
    # =========================================================================

    def _run_anomaly_detection(self, pair: DocumentPair) -> List[ValidationCheck]:
        """
        Detect anomalous patterns that may indicate fraud:
        - Round number paystubs (red flag)
        - Unusual deduction patterns
        - YTD doesn't accumulate logically
        - Missing standard deductions (FICA, Medicare)
        """
        checks: List[ValidationCheck] = []
        ps = pair.paystub_fields

        gross_pay = _to_decimal(ps.get("gross_pay"))
        net_pay = _to_decimal(ps.get("net_pay"))

        # --- Round number gross pay (red flag) ---
        if gross_pay > ZERO:
            is_round_1000 = _is_round_number(gross_pay, Decimal("1000"))
            is_round_500 = _is_round_number(gross_pay, Decimal("500"))

            if is_round_1000:
                checks.append(ValidationCheck(
                    check_id="ANOM_ROUND_GROSS_1000",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="Gross pay is a round $1,000 multiple (potential fabrication indicator)",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=f"Gross pay {_format_currency(gross_pay)} is an exact multiple of $1,000",
                ))
            elif is_round_500:
                checks.append(ValidationCheck(
                    check_id="ANOM_ROUND_GROSS_500",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="Gross pay is a round $500 multiple",
                    passed=True,
                    severity=CheckSeverity.LOW,
                    details=f"Gross pay {_format_currency(gross_pay)} is a $500 multiple (minor flag)",
                ))

        # --- Round number net pay ---
        if net_pay > ZERO:
            if _is_round_number(net_pay, Decimal("1000")):
                checks.append(ValidationCheck(
                    check_id="ANOM_ROUND_NET",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="Net pay is a round $1,000 multiple (unusual after deductions)",
                    passed=False,
                    severity=CheckSeverity.HIGH,
                    details=(
                        f"Net pay {_format_currency(net_pay)} is an exact $1,000 multiple. "
                        "This is unusual because payroll deductions rarely produce round net amounts."
                    ),
                ))

        # --- YTD gross is round multiple of current gross ---
        ytd_gross = _to_decimal(ps.get("ytd_gross_pay") or ps.get("ytd_gross_earnings"))

        if ytd_gross > ZERO and gross_pay > ZERO:
            ratio = ytd_gross / gross_pay
            # Check if ratio is suspiciously exact (within 0.001 of a whole number)
            rounded_ratio = ratio.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            deviation = abs(ratio - rounded_ratio)

            if deviation < Decimal("0.001") and ratio > Decimal("1"):
                # Perfectly even multiple: could indicate fabrication
                checks.append(ValidationCheck(
                    check_id="ANOM_YTD_EXACT_MULTIPLE",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="YTD gross is an exact multiple of current period gross",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=(
                        f"YTD {_format_currency(ytd_gross)} = exactly {int(rounded_ratio)}x "
                        f"current period {_format_currency(gross_pay)}. "
                        "Real payroll often has minor variations period to period."
                    ),
                ))

        # --- Deduction ratio anomaly ---
        if gross_pay > ZERO and net_pay > ZERO:
            deduction_ratio = ((gross_pay - net_pay) / gross_pay * 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            # Typical deduction ratio is 20-40%; outside 10-55% is suspicious
            if deduction_ratio < Decimal("10"):
                checks.append(ValidationCheck(
                    check_id="ANOM_LOW_DEDUCTIONS",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="Unusually low deduction ratio (< 10% of gross)",
                    passed=False,
                    severity=CheckSeverity.HIGH,
                    details=(
                        f"Only {float(deduction_ratio):.1f}% of gross pay "
                        f"({_format_currency(gross_pay)}) deducted. "
                        "This may indicate missing withholdings or a fabricated paystub."
                    ),
                ))
            elif deduction_ratio > Decimal("55"):
                checks.append(ValidationCheck(
                    check_id="ANOM_HIGH_DEDUCTIONS",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="Unusually high deduction ratio (> 55% of gross)",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=(
                        f"{float(deduction_ratio):.1f}% of gross pay "
                        f"({_format_currency(gross_pay)}) deducted. "
                        "Review for excessive garnishments or data entry errors."
                    ),
                ))

        # --- Identical current and YTD amounts (on a non-first pay period) ---
        if gross_pay > ZERO and ytd_gross > ZERO:
            proportion = self._calculate_ytd_proportion(ps)
            if proportion is not None and proportion > Decimal("0.10"):
                # If we are past January and YTD == current, suspicious
                if gross_pay == ytd_gross:
                    checks.append(ValidationCheck(
                        check_id="ANOM_YTD_EQUALS_CURRENT",
                        category=CheckCategory.ANOMALY_DETECTION,
                        description="YTD gross equals current period gross late in the year",
                        passed=False,
                        severity=CheckSeverity.HIGH,
                        details=(
                            f"YTD gross {_format_currency(ytd_gross)} equals current period "
                            f"{_format_currency(gross_pay)} but pay date indicates "
                            f"{float(proportion)*100:.0f}% of the year has elapsed"
                        ),
                    ))

        # --- W2 Box 1 vs Box 3 vs Box 5 internal consistency ---
        w2 = pair.w2_fields
        w2_box1 = _to_decimal(w2.get("wages_tips_compensation"))
        w2_box3 = _to_decimal(w2.get("social_security_wages"))
        w2_box5 = _to_decimal(w2.get("medicare_wages_tips"))

        if w2_box1 > ZERO and w2_box5 > ZERO:
            # Medicare wages (Box 5) should be >= Box 1 (includes pre-tax deductions)
            # But Box 5 is often close to or slightly above Box 1
            box5_variance = _pct_variance(w2_box1, w2_box5)
            if box5_variance is not None and box5_variance < Decimal("-10"):
                checks.append(ValidationCheck(
                    check_id="ANOM_W2_BOX5_LOW",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="W2 Medicare wages (Box 5) significantly lower than Box 1",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=(
                        f"Box 5 (Medicare wages) {_format_currency(w2_box5)} is "
                        f"{float(abs(box5_variance)):.1f}% below Box 1 "
                        f"{_format_currency(w2_box1)}"
                    ),
                ))

        if w2_box1 > ZERO and w2_box3 > ZERO:
            tax_year = pair.tax_year or date.today().year
            ss_cap = SOCIAL_SECURITY_WAGE_BASE.get(tax_year, Decimal("176100"))
            expected_box3 = min(w2_box1, ss_cap)
            box3_variance = _pct_variance(expected_box3, w2_box3)

            if box3_variance is not None and abs(box3_variance) > Decimal("5"):
                checks.append(ValidationCheck(
                    check_id="ANOM_W2_BOX3_VARIANCE",
                    category=CheckCategory.ANOMALY_DETECTION,
                    description="W2 SS wages (Box 3) inconsistent with Box 1 and SS wage base",
                    passed=False,
                    severity=CheckSeverity.MEDIUM,
                    details=(
                        f"Box 3 {_format_currency(w2_box3)} vs expected "
                        f"{_format_currency(expected_box3)} (min of Box 1 and "
                        f"SS cap {_format_currency(ss_cap)})"
                    ),
                ))

        return checks

    # =========================================================================
    # 10. SCORING AND RESULT BUILDING
    # =========================================================================

    def _calculate_confidence_score(
        self,
        checks: List[ValidationCheck],
    ) -> Tuple[int, Dict[str, int]]:
        """
        Calculate overall confidence score (0-100) from check results.

        Starts at 100 and deducts points for each failed check based on
        severity weight. Also calculates per-category scores.

        Returns:
            (overall_score, {category: score})
        """
        if not checks:
            return 0, {}

        overall = 100
        category_totals: Dict[str, Dict[str, int]] = {}

        for check in checks:
            cat_name = check.category.value
            if cat_name not in category_totals:
                category_totals[cat_name] = {"score": 100, "checks": 0, "deductions": 0}

            category_totals[cat_name]["checks"] += 1

            if not check.passed:
                deduction = check.weight
                overall = max(0, overall - deduction)
                category_totals[cat_name]["deductions"] += deduction

        category_scores = {}
        for cat_name, data in category_totals.items():
            category_scores[cat_name] = max(0, data["score"] - data["deductions"])

        return max(0, min(100, overall)), category_scores

    def _determine_risk_level(
        self,
        confidence_score: int,
        checks: List[ValidationCheck],
    ) -> str:
        """
        Determine risk level from confidence score and critical findings.

        A single CRITICAL failure can escalate risk regardless of overall score.
        """
        critical_failures = [c for c in checks if not c.passed and c.severity == CheckSeverity.CRITICAL]
        high_failures = [c for c in checks if not c.passed and c.severity == CheckSeverity.HIGH]

        # Critical failures always escalate
        if len(critical_failures) >= 2:
            return "CRITICAL"
        if critical_failures:
            return "HIGH"

        # Score-based thresholds
        if confidence_score >= 85:
            return "LOW"
        if confidence_score >= 65:
            return "MEDIUM" if not high_failures else "HIGH"
        if confidence_score >= 40:
            return "HIGH"
        return "CRITICAL"

    def _build_recommendations(
        self,
        checks: List[ValidationCheck],
        risk_level: str,
    ) -> List[str]:
        """Build actionable recommendations from check results."""
        recommendations: List[str] = []
        seen_recs: set = set()

        def _add(rec: str) -> None:
            if rec not in seen_recs:
                seen_recs.add(rec)
                recommendations.append(rec)

        failed = [c for c in checks if not c.passed]

        for check in failed:
            if check.category == CheckCategory.INCOME_CONSISTENCY:
                if check.severity in (CheckSeverity.CRITICAL, CheckSeverity.HIGH):
                    _add("Verify income figures with employer via verbal VOE.")
                else:
                    _add("Review income discrepancy and confirm with borrower.")

            elif check.category == CheckCategory.EMPLOYER_VERIFICATION:
                if check.check_id == "EMP_NAME_MISMATCH":
                    _add("Employer name mismatch: obtain letter of explanation or verify DBA/name change.")
                if check.check_id == "EMP_EIN_MATCH":
                    _add("EIN mismatch indicates different legal entities. Obtain clarification.")

            elif check.category == CheckCategory.EMPLOYEE_VERIFICATION:
                if check.check_id == "EE_SSN_MATCH":
                    _add("SSN mismatch is a critical fraud indicator. Escalate to compliance immediately.")
                if check.check_id == "EE_NAME_MATCH":
                    _add("Employee name mismatch: request government-issued ID for verification.")

            elif check.category == CheckCategory.DEDUCTION_ANALYSIS:
                if check.check_id == "DED_STANDARD_MISSING":
                    _add("Missing standard payroll deductions (FICA/Medicare). Verify document authenticity.")
                if check.check_id == "DED_GARNISHMENT_FLAG":
                    _add("Garnishment/child support detected. Factor into DTI and review court orders.")

            elif check.category == CheckCategory.ANOMALY_DETECTION:
                if "ROUND" in check.check_id:
                    _add("Round-number amounts detected. Cross-reference with bank deposit records.")
                if check.check_id == "ANOM_LOW_DEDUCTIONS":
                    _add("Unusually low deductions suggest potential fabrication. Request bank statements for corroboration.")

            elif check.category == CheckCategory.TEMPORAL_CONSISTENCY:
                if check.severity in (CheckSeverity.CRITICAL, CheckSeverity.HIGH):
                    _add("Temporal inconsistency detected. Verify dates against employment verification.")

        if risk_level in ("HIGH", "CRITICAL"):
            _add("Escalate to compliance/fraud team for manual review before proceeding.")

        if not recommendations:
            _add("All cross-validation checks passed. Documents appear consistent.")

        return recommendations

    def _build_summary(
        self,
        pairs_count: int,
        checks: List[ValidationCheck],
        confidence_score: int,
        risk_level: str,
    ) -> str:
        """Build a human-readable summary of the validation results."""
        total = len(checks)
        passed = len([c for c in checks if c.passed])
        failed = len([c for c in checks if not c.passed])
        critical = len([c for c in checks if not c.passed and c.severity == CheckSeverity.CRITICAL])
        high = len([c for c in checks if not c.passed and c.severity == CheckSeverity.HIGH])

        parts = [
            f"Cross-validated {pairs_count} W2/paystub pair(s) with {total} checks.",
            f"{passed} passed, {failed} failed.",
        ]

        if critical or high:
            parts.append(f"{critical} critical and {high} high severity failures.")

        parts.append(f"Confidence: {confidence_score}/100 ({risk_level} risk).")

        return " ".join(parts)


# =============================================================================
# HELPER FUNCTIONS (module-level)
# =============================================================================

def _normalize_address(addr: Optional[str]) -> str:
    """Normalize an address for comparison."""
    if not addr:
        return ""
    addr = addr.lower().strip()
    # Standardize common abbreviations
    replacements = {
        " street": " st",
        " avenue": " ave",
        " boulevard": " blvd",
        " drive": " dr",
        " lane": " ln",
        " road": " rd",
        " court": " ct",
        " place": " pl",
        " suite": " ste",
        " apartment": " apt",
        " north": " n",
        " south": " s",
        " east": " e",
        " west": " w",
    }
    for full, abbrev in replacements.items():
        addr = addr.replace(full, abbrev)
    # Remove punctuation except numbers and letters
    addr = re.sub(r"[^a-z0-9\s]", "", addr)
    return " ".join(addr.split())


def _parse_date(value: Any) -> Optional[date]:
    """Safely parse a date from various formats."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def gross_pay_from_ps(ps: Dict[str, Any]) -> Decimal:
    """Extract gross pay from paystub fields (helper to reduce repetition)."""
    return _to_decimal(ps.get("gross_pay"))


# =============================================================================
# FACTORY / SINGLETON
# =============================================================================

def get_w2_paystub_cross_validator(db: Session) -> W2PaystubCrossValidator:
    """
    Get a W2PaystubCrossValidator instance for the given database session.

    Creates a new instance per session since the service is stateless and
    the db session should not be shared across requests.
    """
    return W2PaystubCrossValidator(db)
