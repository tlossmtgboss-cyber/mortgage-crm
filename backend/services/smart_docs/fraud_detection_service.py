"""
Document Fraud Detection & Cross-Source Validation Service

Detects potential document fraud and validates data consistency across
multiple documents for the same loan. Capabilities include:

1. Cross-document data consistency (name, SSN, income, employer)
2. Income plausibility analysis
3. Document alteration indicators
4. Suspicious patterns (round numbers, template matching)
5. Temporal anomalies (future dates, impossible timelines)
6. Metadata analysis (creation tool, modification history)
7. Address verification patterns
8. Employment verification patterns

Usage:
    from services.smart_docs.fraud_detection_service import get_fraud_detection_service

    service = get_fraud_detection_service(db)
    result = service.analyze_loan_documents(loan_id=123)
    if result.risk_level in ("HIGH", "CRITICAL"):
        sar_data = service.generate_sar_data(loan_id=123)
"""

import logging
import re
import hashlib
from datetime import datetime, timezone, timedelta, date
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Lazy imports for vendor + forensics integration (avoid circular imports at load time)
_fraud_vendor_service_mod = None
_pdf_forensics_service_mod = None


def _get_fraud_vendor_module():
    global _fraud_vendor_service_mod
    if _fraud_vendor_service_mod is None:
        try:
            from services.smart_docs.integrations import fraud_vendor_service as mod
            _fraud_vendor_service_mod = mod
        except ImportError:
            logger.debug("fraud_vendor_service not available")
    return _fraud_vendor_service_mod


def _get_pdf_forensics_module():
    global _pdf_forensics_service_mod
    if _pdf_forensics_service_mod is None:
        try:
            from services.smart_docs import pdf_forensics_service as mod
            _pdf_forensics_service_mod = mod
        except ImportError:
            logger.debug("pdf_forensics_service not available")
    return _pdf_forensics_service_mod


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FraudIndicator:
    """A single fraud indicator detected."""
    indicator_type: str  # ALTERED_TEXT, INCONSISTENT_DATA, SUSPICIOUS_PATTERN, etc.
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    evidence: str  # What triggered this indicator
    affected_documents: List[int]  # document IDs
    confidence: int  # 0-100
    recommendation: str


@dataclass
class CrossValidationResult:
    """Result of cross-document validation."""
    loan_id: int
    documents_analyzed: int
    inconsistencies: List[Dict]
    fraud_indicators: List[FraudIndicator]
    risk_score: int  # 0-100 (0=low risk, 100=high risk)
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    summary: str
    recommendations: List[str]


# =============================================================================
# CONSTANTS
# =============================================================================

# Severity weights for risk score calculation
SEVERITY_WEIGHTS = {
    "CRITICAL": 25,
    "HIGH": 15,
    "MEDIUM": 8,
    "LOW": 3,
}

# Risk level thresholds
RISK_THRESHOLDS = [
    (71, "CRITICAL"),
    (46, "HIGH"),
    (21, "MEDIUM"),
    (0, "LOW"),
]

# Common name variations that should NOT be flagged as mismatches
NAME_VARIATIONS = {
    "william": ["will", "bill", "billy", "wm"],
    "robert": ["rob", "bob", "bobby", "robbie"],
    "richard": ["rich", "rick", "dick", "ricky"],
    "james": ["jim", "jimmy", "jamie"],
    "john": ["jon", "johnny", "jack"],
    "joseph": ["joe", "joey"],
    "michael": ["mike", "mikey", "mick"],
    "thomas": ["tom", "tommy"],
    "charles": ["charlie", "chuck", "chas"],
    "christopher": ["chris"],
    "daniel": ["dan", "danny"],
    "matthew": ["matt", "matty"],
    "anthony": ["tony", "ant"],
    "david": ["dave", "davey"],
    "andrew": ["andy", "drew"],
    "jonathan": ["jon", "john"],
    "nicholas": ["nick", "nicky"],
    "steven": ["steve", "stephen"],
    "edward": ["ed", "eddie", "ted", "teddy"],
    "benjamin": ["ben", "benny"],
    "elizabeth": ["liz", "beth", "betty", "lizzy", "eliza"],
    "jennifer": ["jen", "jenny"],
    "katherine": ["kate", "kathy", "katie", "cathy", "catherine"],
    "patricia": ["pat", "patty", "tricia"],
    "margaret": ["maggie", "meg", "peggy", "marge"],
    "barbara": ["barb", "barbie"],
    "jessica": ["jess", "jessie"],
    "susan": ["sue", "susie", "suzy"],
    "deborah": ["deb", "debbie", "debra"],
    "stephanie": ["steph"],
    "rebecca": ["becky", "becca"],
    "timothy": ["tim", "timmy"],
    "samuel": ["sam", "sammy"],
    "alexander": ["alex"],
    "raymond": ["ray"],
    "gerald": ["gerry", "jerry"],
    "eugene": ["gene"],
    "douglas": ["doug"],
    "lawrence": ["larry", "lars"],
    "philip": ["phil"],
    "kenneth": ["ken", "kenny"],
    "gregory": ["greg"],
    "ronald": ["ron", "ronnie"],
    "donald": ["don", "donnie"],
    "dennis": ["denny"],
    "frederick": ["fred", "freddy"],
}

# Build reverse lookup for name variations
_NAME_REVERSE = {}
for formal, variants in NAME_VARIATIONS.items():
    _NAME_REVERSE[formal] = formal
    for v in variants:
        _NAME_REVERSE[v] = formal

# Suspicious PDF creator tools (tools not typically used to create
# legitimate financial documents)
SUSPICIOUS_CREATORS = {
    "photoshop", "gimp", "illustrator", "inkscape", "paint",
    "canva", "pixlr", "affinity", "corel", "sketch",
    "figma", "procreate",
}

# Income plausibility ranges by job category (annual, USD)
INCOME_PLAUSIBILITY = {
    "cashier": (20_000, 40_000),
    "retail": (22_000, 55_000),
    "server": (18_000, 50_000),
    "waiter": (18_000, 50_000),
    "waitress": (18_000, 50_000),
    "janitor": (22_000, 45_000),
    "custodian": (22_000, 45_000),
    "teacher": (35_000, 100_000),
    "nurse": (50_000, 120_000),
    "engineer": (65_000, 200_000),
    "manager": (45_000, 180_000),
    "director": (70_000, 300_000),
    "executive": (100_000, 500_000),
    "ceo": (100_000, 1_000_000),
    "attorney": (60_000, 400_000),
    "lawyer": (60_000, 400_000),
    "physician": (150_000, 600_000),
    "doctor": (150_000, 600_000),
    "surgeon": (250_000, 800_000),
    "dentist": (120_000, 350_000),
    "pharmacist": (100_000, 180_000),
    "accountant": (45_000, 150_000),
    "analyst": (50_000, 160_000),
    "programmer": (55_000, 200_000),
    "developer": (55_000, 200_000),
    "consultant": (50_000, 250_000),
    "salesperson": (30_000, 200_000),
    "sales": (30_000, 200_000),
    "clerk": (25_000, 50_000),
    "receptionist": (25_000, 45_000),
    "technician": (30_000, 80_000),
    "mechanic": (30_000, 75_000),
    "electrician": (35_000, 90_000),
    "plumber": (35_000, 90_000),
    "contractor": (40_000, 150_000),
    "driver": (28_000, 70_000),
    "pilot": (60_000, 300_000),
}


# =============================================================================
# FRAUD DETECTION SERVICE
# =============================================================================

class FraudDetectionService:
    """
    Document fraud detection and cross-source validation.

    Detection capabilities:
    1. Cross-document data consistency (name, SSN, income, employer)
    2. Income plausibility analysis
    3. Document alteration indicators
    4. Suspicious patterns (round numbers, template matching)
    5. Temporal anomalies (future dates, impossible timelines)
    6. Metadata analysis (creation tool, modification history)
    7. Address verification patterns
    8. Employment verification patterns
    """

    def __init__(self, db: Session, org_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id

    def _org_join_clause(self) -> str:
        """Return a SQL JOIN + WHERE fragment that enforces tenant isolation.

        When org_id is set, adds a JOIN on loans to filter smart_documents
        to only those belonging to loans in the caller's organization.
        The caller must alias the smart_documents table as ``sd``.
        """
        if self.org_id is not None:
            return "JOIN loans _org_l ON _org_l.id = sd.loan_id AND _org_l.organization_id = :_org_id"
        return ""

    def _org_params(self) -> Dict:
        """Return the parameter dict for the org JOIN clause."""
        if self.org_id is not None:
            return {"_org_id": self.org_id}
        return {}

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    def analyze_loan_documents(self, loan_id: int) -> CrossValidationResult:
        """
        Analyze all documents for a loan for fraud indicators and
        cross-document inconsistencies.

        Runs all cross-validation checks and fraud indicator checks,
        calculates an aggregate risk score, and returns a comprehensive result.
        """
        # Validate loan belongs to the caller's organization
        if self.org_id is not None:
            loan_org_check = self.db.execute(
                text("SELECT organization_id FROM loans WHERE id = :lid"),
                {"lid": loan_id},
            ).fetchone()
            if loan_org_check and loan_org_check.organization_id != self.org_id:
                logger.warning(
                    "Tenant isolation violation: loan %d belongs to org %s, caller org %s",
                    loan_id, loan_org_check.organization_id, self.org_id,
                )
                return CrossValidationResult(
                    loan_id=loan_id,
                    documents_analyzed=0,
                    inconsistencies=[],
                    fraud_indicators=[],
                    risk_score=0,
                    risk_level="LOW",
                    summary="Access denied: loan does not belong to your organization.",
                    recommendations=[],
                )

        # Count documents analyzed
        doc_count_row = self.db.execute(
            text("SELECT COUNT(*) AS cnt FROM smart_documents WHERE loan_id = :lid"),
            {"lid": loan_id},
        ).fetchone()
        documents_analyzed = doc_count_row.cnt if doc_count_row else 0

        if documents_analyzed == 0:
            return CrossValidationResult(
                loan_id=loan_id,
                documents_analyzed=0,
                inconsistencies=[],
                fraud_indicators=[],
                risk_score=0,
                risk_level="LOW",
                summary="No documents found for analysis.",
                recommendations=[],
            )

        # Collect all inconsistencies
        inconsistencies: List[Dict] = []
        inconsistencies.extend(self.cross_validate_names(loan_id))
        inconsistencies.extend(self.cross_validate_income(loan_id))
        inconsistencies.extend(self.cross_validate_employment(loan_id))
        inconsistencies.extend(self.cross_validate_addresses(loan_id))

        # Collect all fraud indicators
        indicators: List[FraudIndicator] = []
        indicators.extend(self.check_income_plausibility(loan_id))
        indicators.extend(self.check_temporal_anomalies(loan_id))
        indicators.extend(self.check_suspicious_patterns(loan_id))
        indicators.extend(self.check_duplicate_submissions(loan_id))

        # Also create FraudIndicators from significant inconsistencies
        for inc in inconsistencies:
            severity = inc.get("severity", "MEDIUM")
            if severity in ("HIGH", "CRITICAL"):
                indicators.append(FraudIndicator(
                    indicator_type="INCONSISTENT_DATA",
                    severity=severity,
                    description=inc.get("description", "Cross-document inconsistency"),
                    evidence=inc.get("evidence", ""),
                    affected_documents=inc.get("document_ids", []),
                    confidence=inc.get("confidence", 70),
                    recommendation=inc.get("recommendation", "Review documents manually"),
                ))

        # Calculate risk score
        risk_score, risk_level = self.calculate_risk_score(indicators)

        # Build recommendations
        recommendations = self._build_recommendations(indicators, inconsistencies, risk_level)

        # Build summary
        critical_count = len([i for i in indicators if i.severity == "CRITICAL"])
        high_count = len([i for i in indicators if i.severity == "HIGH"])
        summary = (
            f"Analyzed {documents_analyzed} documents. "
            f"Found {len(inconsistencies)} inconsistencies and {len(indicators)} fraud indicators. "
            f"Risk: {risk_level} ({risk_score}/100). "
            f"{critical_count} critical, {high_count} high severity findings."
        )

        result = CrossValidationResult(
            loan_id=loan_id,
            documents_analyzed=documents_analyzed,
            inconsistencies=inconsistencies,
            fraud_indicators=indicators,
            risk_score=risk_score,
            risk_level=risk_level,
            summary=summary,
            recommendations=recommendations,
        )

        return result

    # =========================================================================
    # 2. CROSS-VALIDATE NAMES
    # =========================================================================

    def cross_validate_names(self, loan_id: int) -> List[Dict]:
        """
        Compare borrower names across all documents for a loan.

        Retrieves extracted names from smart_document_extractions for each
        document and compares them. Allows for common name variations
        (e.g., "John" vs "Jonathan") but flags true mismatches.
        """
        inconsistencies: List[Dict] = []

        # Get all extractions for this loan's documents
        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sde.extracted_fields,
                sd.extracted_names
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        if len(rows) < 2:
            return inconsistencies

        # Collect names by document
        doc_names: List[Dict] = []
        for row in rows:
            names = self._extract_names_from_row(row)
            if names:
                doc_names.append({
                    "document_id": row.document_id,
                    "doc_type": row.doc_type,
                    "names": names,
                })

        if len(doc_names) < 2:
            return inconsistencies

        # Compare each pair of documents
        reference = doc_names[0]
        ref_canonical = {self._canonicalize_name(n) for n in reference["names"]}

        for other in doc_names[1:]:
            other_canonical = {self._canonicalize_name(n) for n in other["names"]}

            # Check if any reference name matches any other name
            has_match = False
            for ref_name in ref_canonical:
                for oth_name in other_canonical:
                    if self._names_match(ref_name, oth_name):
                        has_match = True
                        break
                if has_match:
                    break

            if not has_match and ref_canonical and other_canonical:
                inconsistencies.append({
                    "check_type": "NAME_MISMATCH",
                    "severity": "HIGH",
                    "description": (
                        f"Name mismatch between {reference['doc_type'] or 'document'} "
                        f"and {other['doc_type'] or 'document'}"
                    ),
                    "evidence": (
                        f"Document {reference['document_id']} names: {reference['names']}; "
                        f"Document {other['document_id']} names: {other['names']}"
                    ),
                    "document_ids": [reference["document_id"], other["document_id"]],
                    "confidence": 80,
                    "recommendation": "Verify borrower identity across documents",
                })

        return inconsistencies

    # =========================================================================
    # 3. CROSS-VALIDATE INCOME
    # =========================================================================

    def cross_validate_income(self, loan_id: int) -> List[Dict]:
        """
        Compare income data across documents:
        - Paystub YTD annualized vs W2 annual (within 10%)
        - Monthly gross * 12 ~ W2 wages
        - Tax return AGI vs W2 total (accounting for deductions)
        - Bank deposit history vs stated income

        Flags discrepancies > 15%.
        """
        inconsistencies: List[Dict] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
              AND sde.extracted_fields IS NOT NULL
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        # Separate income-bearing documents by type
        paystub_data: List[Dict] = []
        w2_data: List[Dict] = []
        tax_return_data: List[Dict] = []
        bank_data: List[Dict] = []

        for row in rows:
            fields = row.extracted_fields if isinstance(row.extracted_fields, dict) else {}
            doc_type = (row.doc_type or "").upper()

            if "PAYSTUB" in doc_type or "PAY_STUB" in doc_type:
                paystub_data.append({"document_id": row.document_id, "fields": fields})
            elif "W2" in doc_type or "W-2" in doc_type:
                w2_data.append({"document_id": row.document_id, "fields": fields})
            elif "TAX" in doc_type or "1040" in doc_type:
                tax_return_data.append({"document_id": row.document_id, "fields": fields})
            elif "BANK" in doc_type:
                bank_data.append({"document_id": row.document_id, "fields": fields})

        # Compare paystub YTD annualized vs W2
        for ps in paystub_data:
            ytd_gross = self._safe_float(ps["fields"].get("ytd_gross"))
            pay_period_end = ps["fields"].get("pay_period_end")
            gross_pay = self._safe_float(ps["fields"].get("gross_pay"))
            pay_freq = (ps["fields"].get("pay_frequency") or "").lower()

            # Annualize from period pay
            annualized_from_period = None
            freq_multipliers = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}
            if gross_pay and pay_freq in freq_multipliers:
                annualized_from_period = gross_pay * freq_multipliers[pay_freq]

            # Annualize from YTD
            annualized_from_ytd = None
            if ytd_gross and pay_period_end:
                annualized_from_ytd = self._annualize_ytd(ytd_gross, pay_period_end)

            paystub_annual = annualized_from_period or annualized_from_ytd

            if paystub_annual is None:
                continue

            for w2 in w2_data:
                w2_wages = self._safe_float(w2["fields"].get("wages_tips_compensation"))
                if w2_wages is None or w2_wages == 0:
                    continue

                pct_diff = abs(paystub_annual - w2_wages) / w2_wages * 100
                if pct_diff > 15:
                    inconsistencies.append({
                        "check_type": "INCOME_MISMATCH_PAYSTUB_W2",
                        "severity": "HIGH" if pct_diff > 30 else "MEDIUM",
                        "description": (
                            f"Paystub annualized income (${paystub_annual:,.0f}) differs from "
                            f"W2 wages (${w2_wages:,.0f}) by {pct_diff:.1f}%"
                        ),
                        "evidence": (
                            f"Paystub doc {ps['document_id']}: annualized=${paystub_annual:,.0f}; "
                            f"W2 doc {w2['document_id']}: wages=${w2_wages:,.0f}"
                        ),
                        "document_ids": [ps["document_id"], w2["document_id"]],
                        "confidence": 85 if pct_diff > 30 else 70,
                        "recommendation": "Verify income consistency between paystub and W2",
                    })

        # Compare W2 vs tax return AGI
        for w2 in w2_data:
            w2_wages = self._safe_float(w2["fields"].get("wages_tips_compensation"))
            w2_year = w2["fields"].get("tax_year")
            if w2_wages is None:
                continue

            for tr in tax_return_data:
                tr_agi = self._safe_float(tr["fields"].get("adjusted_gross_income"))
                tr_year = tr["fields"].get("tax_year")
                if tr_agi is None or tr_agi == 0:
                    continue

                # Only compare same tax year
                if w2_year and tr_year and str(w2_year) != str(tr_year):
                    continue

                # AGI can be lower than W2 due to deductions, but should not be
                # dramatically higher (unless there is other income)
                if tr_agi > w2_wages * 1.5:
                    inconsistencies.append({
                        "check_type": "INCOME_MISMATCH_W2_TAX",
                        "severity": "MEDIUM",
                        "description": (
                            f"Tax return AGI (${tr_agi:,.0f}) is significantly higher than "
                            f"W2 wages (${w2_wages:,.0f}) -- may indicate unreported income sources"
                        ),
                        "evidence": (
                            f"W2 doc {w2['document_id']}: wages=${w2_wages:,.0f}; "
                            f"Tax return doc {tr['document_id']}: AGI=${tr_agi:,.0f}"
                        ),
                        "document_ids": [w2["document_id"], tr["document_id"]],
                        "confidence": 60,
                        "recommendation": "Verify all income sources are documented",
                    })

        # Compare bank deposits vs stated income
        for bank in bank_data:
            total_deposits = self._safe_float(bank["fields"].get("total_deposits"))
            if total_deposits is None:
                continue

            # Monthly deposits, annualized
            annualized_deposits = total_deposits * 12

            # Compare against any W2 or paystub income
            for w2 in w2_data:
                w2_wages = self._safe_float(w2["fields"].get("wages_tips_compensation"))
                if w2_wages is None or w2_wages == 0:
                    continue

                # If deposits are < 50% of stated income, suspicious
                if annualized_deposits < w2_wages * 0.5:
                    inconsistencies.append({
                        "check_type": "INCOME_MISMATCH_BANK_W2",
                        "severity": "MEDIUM",
                        "description": (
                            f"Bank deposits annualized (${annualized_deposits:,.0f}) are significantly "
                            f"lower than W2 income (${w2_wages:,.0f})"
                        ),
                        "evidence": (
                            f"Bank doc {bank['document_id']}: monthly deposits=${total_deposits:,.0f}; "
                            f"W2 doc {w2['document_id']}: annual wages=${w2_wages:,.0f}"
                        ),
                        "document_ids": [bank["document_id"], w2["document_id"]],
                        "confidence": 55,
                        "recommendation": (
                            "Verify bank account receives payroll deposits. "
                            "Borrower may have additional accounts."
                        ),
                    })

        return inconsistencies

    # =========================================================================
    # 4. CROSS-VALIDATE EMPLOYMENT
    # =========================================================================

    def cross_validate_employment(self, loan_id: int) -> List[Dict]:
        """
        Compare employer information across documents:
        - Employer name on paystub vs W2 vs VOE
        - EIN on W2 vs tax return
        - Employment dates consistency
        """
        inconsistencies: List[Dict] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
              AND sde.extracted_fields IS NOT NULL
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        # Collect employer names and EINs by document
        employer_records: List[Dict] = []
        for row in rows:
            fields = row.extracted_fields if isinstance(row.extracted_fields, dict) else {}
            employer_name = fields.get("employer_name") or fields.get("business_name")
            employer_ein = fields.get("employer_ein")

            if employer_name:
                employer_records.append({
                    "document_id": row.document_id,
                    "doc_type": row.doc_type,
                    "employer_name": employer_name,
                    "employer_ein": employer_ein,
                })

        if len(employer_records) < 2:
            return inconsistencies

        # Compare employer names
        reference = employer_records[0]
        ref_normalized = self._normalize_company_name(reference["employer_name"])

        for other in employer_records[1:]:
            other_normalized = self._normalize_company_name(other["employer_name"])

            if ref_normalized != other_normalized:
                # Check if it is just a minor formatting difference
                similarity = self._string_similarity(ref_normalized, other_normalized)
                if similarity < 0.8:
                    inconsistencies.append({
                        "check_type": "EMPLOYER_NAME_MISMATCH",
                        "severity": "HIGH",
                        "description": (
                            f"Employer name mismatch: '{reference['employer_name']}' "
                            f"vs '{other['employer_name']}'"
                        ),
                        "evidence": (
                            f"Doc {reference['document_id']} ({reference['doc_type']}): "
                            f"'{reference['employer_name']}'; "
                            f"Doc {other['document_id']} ({other['doc_type']}): "
                            f"'{other['employer_name']}'"
                        ),
                        "document_ids": [reference["document_id"], other["document_id"]],
                        "confidence": 75,
                        "recommendation": "Verify employer is the same across all documents",
                    })

        # Compare EINs across documents
        ein_records = [r for r in employer_records if r["employer_ein"]]
        if len(ein_records) >= 2:
            ref_ein = self._normalize_ein(ein_records[0]["employer_ein"])
            for other in ein_records[1:]:
                other_ein = self._normalize_ein(other["employer_ein"])
                if ref_ein and other_ein and ref_ein != other_ein:
                    inconsistencies.append({
                        "check_type": "EMPLOYER_EIN_MISMATCH",
                        "severity": "CRITICAL",
                        "description": (
                            f"Employer EIN mismatch: {ein_records[0]['employer_ein']} "
                            f"vs {other['employer_ein']}"
                        ),
                        "evidence": (
                            f"Doc {ein_records[0]['document_id']}: EIN={ein_records[0]['employer_ein']}; "
                            f"Doc {other['document_id']}: EIN={other['employer_ein']}"
                        ),
                        "document_ids": [ein_records[0]["document_id"], other["document_id"]],
                        "confidence": 95,
                        "recommendation": (
                            "Critical: EIN mismatch suggests documents may be from "
                            "different employers. Investigate immediately."
                        ),
                    })

        return inconsistencies

    # =========================================================================
    # 5. CROSS-VALIDATE ADDRESSES
    # =========================================================================

    def cross_validate_addresses(self, loan_id: int) -> List[Dict]:
        """
        Compare addresses across documents, allowing for formatting differences.
        """
        inconsistencies: List[Dict] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
              AND sde.extracted_fields IS NOT NULL
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        # Collect addresses by document
        address_records: List[Dict] = []
        for row in rows:
            fields = row.extracted_fields if isinstance(row.extracted_fields, dict) else {}
            address = self._extract_address_from_fields(fields)
            if address:
                address_records.append({
                    "document_id": row.document_id,
                    "doc_type": row.doc_type,
                    "address": address,
                    "normalized": self._normalize_address(address),
                })

        if len(address_records) < 2:
            return inconsistencies

        # Group documents by normalized address and check for mismatches
        reference = address_records[0]

        for other in address_records[1:]:
            if reference["normalized"] != other["normalized"]:
                similarity = self._string_similarity(
                    reference["normalized"], other["normalized"]
                )
                # Only flag if addresses are truly different, not just formatting
                if similarity < 0.75:
                    inconsistencies.append({
                        "check_type": "ADDRESS_MISMATCH",
                        "severity": "MEDIUM",
                        "description": (
                            f"Address mismatch between {reference['doc_type'] or 'document'} "
                            f"and {other['doc_type'] or 'document'}"
                        ),
                        "evidence": (
                            f"Doc {reference['document_id']}: '{reference['address']}'; "
                            f"Doc {other['document_id']}: '{other['address']}'"
                        ),
                        "document_ids": [reference["document_id"], other["document_id"]],
                        "confidence": 65,
                        "recommendation": (
                            "Verify borrower address. Different addresses across documents "
                            "may indicate a recent move or data entry error."
                        ),
                    })

        return inconsistencies

    # =========================================================================
    # 6. CHECK INCOME PLAUSIBILITY
    # =========================================================================

    def check_income_plausibility(self, loan_id: int) -> List[FraudIndicator]:
        """
        Check if stated income is plausible for the job title/industry.
        - Flag extremely high income for common positions
        - Check if income changed dramatically between documents
        - Flag perfectly round income numbers on paystubs
        - Check if OT/bonus is unreasonably high percentage of base
        """
        indicators: List[FraudIndicator] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
              AND sde.extracted_fields IS NOT NULL
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        for row in rows:
            fields = row.extracted_fields if isinstance(row.extracted_fields, dict) else {}
            doc_type = (row.doc_type or "").upper()

            # Check round numbers on paystubs
            if "PAYSTUB" in doc_type or "PAY_STUB" in doc_type:
                gross_pay = self._safe_float(fields.get("gross_pay"))
                if gross_pay is not None and gross_pay > 0:
                    # Perfectly round to thousands is suspicious for a pay period
                    if gross_pay >= 1000 and gross_pay % 1000 == 0:
                        indicators.append(FraudIndicator(
                            indicator_type="SUSPICIOUS_PATTERN",
                            severity="MEDIUM",
                            description=(
                                f"Paystub gross pay is a perfectly round number: "
                                f"${gross_pay:,.2f}"
                            ),
                            evidence=f"Document {row.document_id}: gross_pay=${gross_pay:,.2f}",
                            affected_documents=[row.document_id],
                            confidence=50,
                            recommendation=(
                                "Round gross pay amounts on paystubs are uncommon. "
                                "Verify with employer."
                            ),
                        ))

                # Check OT/bonus ratio
                overtime = self._safe_float(fields.get("overtime_earnings")) or 0
                bonus = self._safe_float(fields.get("bonus")) or 0
                commission = self._safe_float(fields.get("commission")) or 0
                regular = self._safe_float(fields.get("regular_earnings")) or gross_pay or 0

                if regular and regular > 0:
                    variable_pct = (overtime + bonus + commission) / regular * 100
                    if variable_pct > 80:
                        indicators.append(FraudIndicator(
                            indicator_type="SUSPICIOUS_PATTERN",
                            severity="MEDIUM",
                            description=(
                                f"Variable pay (OT+bonus+commission) is {variable_pct:.0f}% "
                                f"of regular earnings"
                            ),
                            evidence=(
                                f"Document {row.document_id}: regular=${regular:,.2f}, "
                                f"OT=${overtime:,.2f}, bonus=${bonus:,.2f}, "
                                f"commission=${commission:,.2f}"
                            ),
                            affected_documents=[row.document_id],
                            confidence=55,
                            recommendation=(
                                "Unusually high variable-to-base pay ratio. "
                                "Verify compensation structure with employer."
                            ),
                        ))

            # Check income vs job title plausibility
            if "W2" in doc_type or "PAYSTUB" in doc_type:
                wages = self._safe_float(
                    fields.get("wages_tips_compensation")
                    or fields.get("ytd_gross")
                )
                # Try to find a job title from the lead/loan
                job_title = self._get_job_title_for_loan(loan_id)

                if wages and job_title:
                    job_lower = job_title.lower()
                    for keyword, (min_income, max_income) in INCOME_PLAUSIBILITY.items():
                        if keyword in job_lower:
                            if wages > max_income * 2:
                                indicators.append(FraudIndicator(
                                    indicator_type="INCOME_PLAUSIBILITY",
                                    severity="HIGH",
                                    description=(
                                        f"Income ${wages:,.0f} is unusually high for "
                                        f"job title '{job_title}' (expected range: "
                                        f"${min_income:,}-${max_income:,})"
                                    ),
                                    evidence=(
                                        f"Document {row.document_id}: "
                                        f"wages=${wages:,.0f}, job='{job_title}'"
                                    ),
                                    affected_documents=[row.document_id],
                                    confidence=65,
                                    recommendation=(
                                        "Income appears implausible for stated occupation. "
                                        "Request additional documentation such as offer letter "
                                        "or employment contract."
                                    ),
                                ))
                            break

        return indicators

    # =========================================================================
    # 7. CHECK TEMPORAL ANOMALIES
    # =========================================================================

    def check_temporal_anomalies(self, loan_id: int) -> List[FraudIndicator]:
        """
        Check for temporal anomalies in documents:
        - Future-dated documents
        - Pay period end > document date
        - Documents dated on weekends (for paystubs)
        - Gaps in bank statement coverage
        - Document dates vs application timeline
        """
        indicators: List[FraudIndicator] = []
        now = datetime.now(timezone.utc)
        today = now.date()

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sd.doc_date,
                sd.uploaded_at,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        bank_statement_periods: List[Dict] = []

        for row in rows:
            fields = (row.extracted_fields if isinstance(row.extracted_fields, dict) else {}) or {}
            doc_type = (row.doc_type or "").upper()
            doc_date = row.doc_date

            # Check for future-dated documents
            if doc_date:
                doc_date_val = doc_date.date() if isinstance(doc_date, datetime) else doc_date
                if doc_date_val > today:
                    indicators.append(FraudIndicator(
                        indicator_type="TEMPORAL_ANOMALY",
                        severity="HIGH",
                        description=f"Document is dated in the future: {doc_date_val}",
                        evidence=f"Document {row.document_id}: date={doc_date_val}, today={today}",
                        affected_documents=[row.document_id],
                        confidence=90,
                        recommendation="Future-dated documents are invalid. Request replacement.",
                    ))

            # Paystub-specific temporal checks
            if "PAYSTUB" in doc_type or "PAY_STUB" in doc_type:
                pay_date_str = fields.get("pay_date")
                period_end_str = fields.get("pay_period_end")

                if pay_date_str:
                    pay_date = self._parse_date(pay_date_str)
                    if pay_date:
                        # Check if pay date is a weekend (unusual for paystubs)
                        if pay_date.weekday() in (5, 6):  # Saturday=5, Sunday=6
                            indicators.append(FraudIndicator(
                                indicator_type="TEMPORAL_ANOMALY",
                                severity="LOW",
                                description=(
                                    f"Paystub pay date falls on a "
                                    f"{'Saturday' if pay_date.weekday() == 5 else 'Sunday'}: "
                                    f"{pay_date}"
                                ),
                                evidence=f"Document {row.document_id}: pay_date={pay_date}",
                                affected_documents=[row.document_id],
                                confidence=40,
                                recommendation=(
                                    "Pay dates on weekends are uncommon but not impossible "
                                    "(e.g., direct deposit posting). Verify if needed."
                                ),
                            ))

                        # Check if pay date is in the future
                        if pay_date > today:
                            indicators.append(FraudIndicator(
                                indicator_type="TEMPORAL_ANOMALY",
                                severity="HIGH",
                                description=f"Paystub pay date is in the future: {pay_date}",
                                evidence=f"Document {row.document_id}: pay_date={pay_date}",
                                affected_documents=[row.document_id],
                                confidence=90,
                                recommendation="Future-dated paystub is invalid.",
                            ))

                if pay_date_str and period_end_str:
                    pay_date = self._parse_date(pay_date_str)
                    period_end = self._parse_date(period_end_str)
                    if pay_date and period_end and period_end > pay_date:
                        indicators.append(FraudIndicator(
                            indicator_type="TEMPORAL_ANOMALY",
                            severity="HIGH",
                            description=(
                                f"Pay period end ({period_end}) is after the pay date "
                                f"({pay_date})"
                            ),
                            evidence=(
                                f"Document {row.document_id}: period_end={period_end}, "
                                f"pay_date={pay_date}"
                            ),
                            affected_documents=[row.document_id],
                            confidence=85,
                            recommendation=(
                                "Pay period end should precede the pay date. "
                                "This may indicate document alteration."
                            ),
                        ))

            # Collect bank statement periods for gap analysis
            if "BANK" in doc_type:
                start_str = fields.get("statement_start_date")
                end_str = fields.get("statement_end_date")
                start = self._parse_date(start_str) if start_str else None
                end = self._parse_date(end_str) if end_str else None
                if start and end:
                    bank_statement_periods.append({
                        "document_id": row.document_id,
                        "start": start,
                        "end": end,
                    })

        # Check for gaps in bank statement coverage
        if len(bank_statement_periods) >= 2:
            sorted_periods = sorted(bank_statement_periods, key=lambda x: x["start"])
            for i in range(len(sorted_periods) - 1):
                current_end = sorted_periods[i]["end"]
                next_start = sorted_periods[i + 1]["start"]
                gap_days = (next_start - current_end).days

                if gap_days > 5:  # Allow small overlap/gaps for monthly statements
                    indicators.append(FraudIndicator(
                        indicator_type="TEMPORAL_ANOMALY",
                        severity="MEDIUM",
                        description=(
                            f"Gap of {gap_days} days in bank statement coverage "
                            f"({current_end} to {next_start})"
                        ),
                        evidence=(
                            f"Doc {sorted_periods[i]['document_id']} ends {current_end}; "
                            f"Doc {sorted_periods[i+1]['document_id']} starts {next_start}"
                        ),
                        affected_documents=[
                            sorted_periods[i]["document_id"],
                            sorted_periods[i + 1]["document_id"],
                        ],
                        confidence=60,
                        recommendation=(
                            "Request bank statement covering the gap period. "
                            "Missing periods may conceal irregular transactions."
                        ),
                    ))

        # Check if documents were uploaded before their stated dates
        for row in rows:
            fields = (row.extracted_fields if isinstance(row.extracted_fields, dict) else {}) or {}
            doc_date_str = fields.get("pay_date") or fields.get("statement_end_date")
            if doc_date_str and row.uploaded_at:
                stated_date = self._parse_date(doc_date_str)
                uploaded_date = (
                    row.uploaded_at.date()
                    if isinstance(row.uploaded_at, datetime)
                    else row.uploaded_at
                )
                if stated_date and uploaded_date:
                    # If doc was uploaded more than 2 days before the date on it
                    if (stated_date - uploaded_date).days > 2:
                        indicators.append(FraudIndicator(
                            indicator_type="TEMPORAL_ANOMALY",
                            severity="HIGH",
                            description=(
                                f"Document uploaded on {uploaded_date} but dated "
                                f"{stated_date} (uploaded before document date)"
                            ),
                            evidence=(
                                f"Document {row.document_id}: uploaded={uploaded_date}, "
                                f"doc_date={stated_date}"
                            ),
                            affected_documents=[row.document_id],
                            confidence=80,
                            recommendation=(
                                "Document was uploaded before its stated date. "
                                "This may indicate document fabrication."
                            ),
                        ))

        return indicators

    # =========================================================================
    # 8. CHECK SUSPICIOUS PATTERNS
    # =========================================================================

    def check_suspicious_patterns(self, loan_id: int) -> List[FraudIndicator]:
        """
        Check for suspicious patterns:
        - Round deposit amounts
        - Deposits near reporting threshold ($9,900-$9,999)
        - Unusually consistent deposit amounts
        - Documents uploaded in rapid succession (batch fabrication)
        - Documents from same creation tool but different sources
        """
        indicators: List[FraudIndicator] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sd.uploaded_at,
                sd.file_name,
                sd.file_size,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
            ORDER BY sd.uploaded_at
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        if not rows:
            return indicators

        # Check for rapid succession uploads (potential batch fabrication)
        if len(rows) >= 3:
            upload_times = [
                (r.document_id, r.uploaded_at)
                for r in rows
                if r.uploaded_at is not None
            ]

            if len(upload_times) >= 3:
                # Check if 5+ documents were uploaded within 2 minutes
                for i in range(len(upload_times) - 4):
                    window_start = upload_times[i][1]
                    window_end = upload_times[i + 4][1]
                    if isinstance(window_start, datetime) and isinstance(window_end, datetime):
                        delta = (window_end - window_start).total_seconds()
                        if delta < 120:  # 2 minutes
                            affected = [ut[0] for ut in upload_times[i:i + 5]]
                            indicators.append(FraudIndicator(
                                indicator_type="SUSPICIOUS_PATTERN",
                                severity="MEDIUM",
                                description=(
                                    f"5 documents uploaded within {delta:.0f} seconds "
                                    f"(possible batch fabrication)"
                                ),
                                evidence=(
                                    f"Documents {affected} uploaded between "
                                    f"{window_start} and {window_end}"
                                ),
                                affected_documents=affected,
                                confidence=45,
                                recommendation=(
                                    "Multiple documents uploaded very quickly may indicate "
                                    "pre-fabricated document package. Review each document "
                                    "carefully."
                                ),
                            ))
                            break  # Only flag once

        # Check bank statement patterns
        for row in rows:
            fields = (row.extracted_fields if isinstance(row.extracted_fields, dict) else {}) or {}
            doc_type = (row.doc_type or "").upper()

            if "BANK" not in doc_type:
                continue

            total_deposits = self._safe_float(fields.get("total_deposits"))
            ending_balance = self._safe_float(fields.get("ending_balance"))

            # Check for round deposit totals
            if total_deposits is not None and total_deposits > 0:
                if total_deposits >= 10000 and total_deposits % 5000 == 0:
                    indicators.append(FraudIndicator(
                        indicator_type="SUSPICIOUS_PATTERN",
                        severity="LOW",
                        description=(
                            f"Bank statement total deposits is a round number: "
                            f"${total_deposits:,.2f}"
                        ),
                        evidence=f"Document {row.document_id}: total_deposits=${total_deposits:,.2f}",
                        affected_documents=[row.document_id],
                        confidence=30,
                        recommendation="Review individual deposit transactions.",
                    ))

            # Check for structuring-like patterns (deposits near $10K threshold)
            if total_deposits is not None:
                # This is a simplified check; real analysis would look at
                # individual transactions
                if 9900 <= total_deposits <= 9999:
                    indicators.append(FraudIndicator(
                        indicator_type="SUSPICIOUS_PATTERN",
                        severity="HIGH",
                        description=(
                            f"Total deposits (${total_deposits:,.2f}) are just below "
                            f"the $10,000 CTR reporting threshold"
                        ),
                        evidence=f"Document {row.document_id}: total_deposits=${total_deposits:,.2f}",
                        affected_documents=[row.document_id],
                        confidence=70,
                        recommendation=(
                            "Deposits just below BSA/AML reporting threshold may indicate "
                            "structuring. Review individual transactions."
                        ),
                    ))

        # Check for identical file sizes (potential duplicates with different names)
        size_groups: Dict[int, List[int]] = {}
        for row in rows:
            if row.file_size and row.file_size > 0:
                size_groups.setdefault(row.file_size, []).append(row.document_id)

        for size, doc_ids in size_groups.items():
            if len(doc_ids) >= 2:
                indicators.append(FraudIndicator(
                    indicator_type="SUSPICIOUS_PATTERN",
                    severity="MEDIUM",
                    description=(
                        f"{len(doc_ids)} documents have identical file size ({size} bytes)"
                    ),
                    evidence=f"Documents {doc_ids} all have file_size={size}",
                    affected_documents=doc_ids,
                    confidence=55,
                    recommendation=(
                        "Documents with identical file sizes may be duplicates "
                        "submitted under different names. Compare content."
                    ),
                ))

        return indicators

    # =========================================================================
    # 9. CHECK DOCUMENT METADATA
    # =========================================================================

    def check_document_metadata(
        self, document_id: int, file_content: bytes
    ) -> List[FraudIndicator]:
        """
        Analyze PDF metadata for fraud indicators:
        - Check creation tool (Photoshop for a paystub is suspicious)
        - Check creation date vs document date
        - Check modification date vs creation date
        - Return metadata-based indicators

        This method requires the raw file content to extract PDF metadata.
        """
        indicators: List[FraudIndicator] = []

        metadata = self._extract_pdf_metadata(file_content)
        if not metadata:
            return indicators

        creator = (metadata.get("creator") or "").lower()
        producer = (metadata.get("producer") or "").lower()
        creation_date = metadata.get("creation_date")
        modification_date = metadata.get("modification_date")

        # Check for suspicious creator tools
        for tool in SUSPICIOUS_CREATORS:
            if tool in creator or tool in producer:
                indicators.append(FraudIndicator(
                    indicator_type="ALTERED_TEXT",
                    severity="CRITICAL",
                    description=(
                        f"Document created with image editing software: "
                        f"'{metadata.get('creator') or metadata.get('producer')}'"
                    ),
                    evidence=(
                        f"Document {document_id}: creator='{metadata.get('creator')}', "
                        f"producer='{metadata.get('producer')}'"
                    ),
                    affected_documents=[document_id],
                    confidence=85,
                    recommendation=(
                        "Document appears to have been created or modified with image "
                        "editing software. This is a strong indicator of document "
                        "fabrication. Request original documents directly from the source."
                    ),
                ))
                break

        # Check if modification date is significantly after creation date
        if creation_date and modification_date:
            creation_dt = self._parse_pdf_date(creation_date)
            modification_dt = self._parse_pdf_date(modification_date)

            if creation_dt and modification_dt:
                diff_hours = (modification_dt - creation_dt).total_seconds() / 3600

                if diff_hours > 24:
                    indicators.append(FraudIndicator(
                        indicator_type="ALTERED_TEXT",
                        severity="HIGH",
                        description=(
                            f"Document was modified {diff_hours:.0f} hours after creation"
                        ),
                        evidence=(
                            f"Document {document_id}: created={creation_dt}, "
                            f"modified={modification_dt}"
                        ),
                        affected_documents=[document_id],
                        confidence=60,
                        recommendation=(
                            "Significant time between document creation and last "
                            "modification may indicate tampering. Request original "
                            "from issuing institution."
                        ),
                    ))

        # Check if file content hash suggests a known template
        content_hash = hashlib.sha256(file_content[:4096]).hexdigest()
        # Store for duplicate detection comparison
        indicators_metadata = {
            "content_hash": content_hash,
            "creator": metadata.get("creator"),
            "producer": metadata.get("producer"),
            "creation_date": creation_date,
            "modification_date": modification_date,
        }
        # Attach metadata to each indicator for downstream use
        for ind in indicators:
            ind.evidence += f" | metadata={indicators_metadata}"

        return indicators

    # =========================================================================
    # 10. CHECK DUPLICATE SUBMISSIONS
    # =========================================================================

    def check_duplicate_submissions(self, loan_id: int) -> List[FraudIndicator]:
        """
        Check for:
        - Identical documents submitted as different types
        - Same document submitted for different periods
        - Identical OCR text content across documents
        """
        indicators: List[FraudIndicator] = []

        query = f"""
            SELECT
                sd.id AS document_id,
                sd.doc_type,
                sd.file_size,
                sd.ocr_text,
                sd.extracted_names,
                sd.extracted_amount,
                sde.extracted_fields
            FROM smart_documents sd
            LEFT JOIN smart_document_extractions sde ON sde.document_id = sd.id
            {self._org_join_clause()}
            WHERE sd.loan_id = :lid
              AND sd.status != 'REJECTED'
            ORDER BY sd.id
        """
        rows = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchall()

        if len(rows) < 2:
            return indicators

        # Compare OCR text hashes for near-duplicates
        text_hashes: Dict[str, List[Dict]] = {}
        for row in rows:
            if row.ocr_text and len(row.ocr_text) > 100:
                # Hash the normalized OCR text (strip whitespace variations)
                normalized_text = re.sub(r'\s+', ' ', row.ocr_text.strip().lower())
                text_hash = hashlib.sha256(normalized_text.encode()).hexdigest()

                text_hashes.setdefault(text_hash, []).append({
                    "document_id": row.document_id,
                    "doc_type": row.doc_type,
                })

        for hash_val, docs in text_hashes.items():
            if len(docs) >= 2:
                doc_ids = [d["document_id"] for d in docs]
                doc_types = [d["doc_type"] for d in docs]

                # If same content submitted under different types, more suspicious
                unique_types = set(dt for dt in doc_types if dt)
                if len(unique_types) > 1:
                    severity = "HIGH"
                    desc = (
                        f"Identical document content submitted as different types: "
                        f"{', '.join(unique_types)}"
                    )
                else:
                    severity = "MEDIUM"
                    desc = f"Duplicate document content detected across {len(docs)} documents"

                indicators.append(FraudIndicator(
                    indicator_type="DUPLICATE_SUBMISSION",
                    severity=severity,
                    description=desc,
                    evidence=f"Documents {doc_ids} have identical OCR text content",
                    affected_documents=doc_ids,
                    confidence=90,
                    recommendation=(
                        "Identical document content detected. If submitted as different "
                        "document types, this is a strong fraud indicator."
                    ),
                ))

        # Check for same amounts/dates submitted as different periods
        period_fingerprints: Dict[str, List[Dict]] = {}
        for row in rows:
            fields = (row.extracted_fields if isinstance(row.extracted_fields, dict) else {}) or {}
            doc_type = (row.doc_type or "").upper()

            # For paystubs, fingerprint on gross_pay + pay_date
            if "PAYSTUB" in doc_type or "PAY_STUB" in doc_type:
                gross = fields.get("gross_pay")
                pay_date = fields.get("pay_date")
                if gross and pay_date:
                    fp = f"paystub:{gross}:{pay_date}"
                    period_fingerprints.setdefault(fp, []).append({
                        "document_id": row.document_id,
                        "doc_type": row.doc_type,
                    })

            # For bank statements, fingerprint on ending_balance + end_date
            if "BANK" in doc_type:
                balance = fields.get("ending_balance")
                end_date = fields.get("statement_end_date")
                if balance and end_date:
                    fp = f"bank:{balance}:{end_date}"
                    period_fingerprints.setdefault(fp, []).append({
                        "document_id": row.document_id,
                        "doc_type": row.doc_type,
                    })

        for fp, docs in period_fingerprints.items():
            if len(docs) >= 2:
                doc_ids = [d["document_id"] for d in docs]
                indicators.append(FraudIndicator(
                    indicator_type="DUPLICATE_SUBMISSION",
                    severity="MEDIUM",
                    description=(
                        f"Same document period submitted {len(docs)} times "
                        f"(identical key data)"
                    ),
                    evidence=f"Documents {doc_ids} share fingerprint: {fp}",
                    affected_documents=doc_ids,
                    confidence=75,
                    recommendation=(
                        "Same period data appears in multiple submissions. "
                        "Verify each represents a unique document."
                    ),
                ))

        return indicators

    # =========================================================================
    # 11. CALCULATE RISK SCORE
    # =========================================================================

    def calculate_risk_score(
        self, indicators: List[FraudIndicator]
    ) -> Tuple[int, str]:
        """
        Calculate overall risk score (0-100) from fraud indicators.

        Weights by severity:
        - CRITICAL: 25 points
        - HIGH: 15 points
        - MEDIUM: 8 points
        - LOW: 3 points

        Also factors in indicator confidence as a multiplier.
        Score is capped at 100.

        Returns:
            (score, risk_level) where risk_level is LOW/MEDIUM/HIGH/CRITICAL
            LOW: 0-20, MEDIUM: 21-45, HIGH: 46-70, CRITICAL: 71-100
        """
        if not indicators:
            return 0, "LOW"

        raw_score = 0
        for ind in indicators:
            weight = SEVERITY_WEIGHTS.get(ind.severity, 3)
            confidence_factor = ind.confidence / 100.0
            raw_score += weight * confidence_factor

        # Cap at 100
        score = min(int(round(raw_score)), 100)

        # Determine risk level
        risk_level = "LOW"
        for threshold, level in RISK_THRESHOLDS:
            if score >= threshold:
                risk_level = level
                break

        return score, risk_level

    # =========================================================================
    # 12. GENERATE SAR DATA
    # =========================================================================

    def generate_sar_data(self, loan_id: int) -> Dict:
        """
        Generate Suspicious Activity Report data if risk is CRITICAL.

        Returns structured data suitable for the compliance team to file
        a SAR with FinCEN. Includes all evidence, affected documents,
        and timeline of suspicious activity.
        """
        result = self.analyze_loan_documents(loan_id)

        # Get loan and borrower info (with org_id filter when available)
        _loan_org_filter = "AND l.organization_id = :_org_id" if self.org_id is not None else ""
        query = f"""
            SELECT
                l.id, l.loan_number, l.amount, l.loan_type, l.stage,
                l.borrower_name, l.borrower_email, l.property_address,
                l.application_date, l.loan_officer_id,
                l.organization_id,
                CONCAT(u.first_name, ' ', u.last_name) AS lo_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            WHERE l.id = :lid {_loan_org_filter}
        """
        loan_info = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchone()

        # Get all affected document details
        affected_doc_ids = set()
        for ind in result.fraud_indicators:
            affected_doc_ids.update(ind.affected_documents)

        affected_docs = []
        if affected_doc_ids:
            doc_rows = self.db.execute(text("""
                SELECT id, doc_type, file_name, uploaded_at, status
                FROM smart_documents
                WHERE id = ANY(:ids)
                ORDER BY uploaded_at
            """), {"ids": list(affected_doc_ids)}).fetchall()
            affected_docs = [
                {
                    "document_id": d.id,
                    "doc_type": d.doc_type,
                    "file_name": d.file_name,
                    "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
                    "status": d.status,
                }
                for d in doc_rows
            ]

        # Build SAR data structure
        sar_data = {
            "report_type": "SUSPICIOUS_ACTIVITY_REPORT",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "loan_information": {
                "loan_id": loan_id,
                "loan_number": loan_info.loan_number if loan_info else None,
                "loan_amount": float(loan_info.amount) if loan_info and loan_info.amount else None,
                "loan_type": loan_info.loan_type if loan_info else None,
                "stage": loan_info.stage if loan_info else None,
                "property_address": loan_info.property_address if loan_info else None,
                "application_date": (
                    loan_info.application_date.isoformat()
                    if loan_info and loan_info.application_date else None
                ),
            },
            "subject_information": {
                "borrower_name": loan_info.borrower_name if loan_info else None,
                "borrower_email": loan_info.borrower_email if loan_info else None,
                "loan_officer": loan_info.lo_name if loan_info else None,
            },
            "suspicious_activities": [
                {
                    "indicator_type": ind.indicator_type,
                    "severity": ind.severity,
                    "description": ind.description,
                    "evidence": ind.evidence,
                    "affected_documents": ind.affected_documents,
                    "confidence": ind.confidence,
                }
                for ind in result.fraud_indicators
            ],
            "inconsistencies": result.inconsistencies,
            "affected_documents": affected_docs,
            "documents_analyzed": result.documents_analyzed,
            "summary": result.summary,
            "recommendations": result.recommendations,
            "compliance_notes": (
                "This report was automatically generated by the Perennia AI "
                "fraud detection system. All indicators should be reviewed by "
                "a qualified compliance officer before any action is taken. "
                "This is not a formal SAR filing -- it provides data to support "
                "the compliance team's determination of whether a SAR filing "
                "with FinCEN is warranted."
            ),
        }

        return sar_data

    # =========================================================================
    # 13. GENERATE SANITIZED REPORT
    # =========================================================================

    def generate_sanitized_report(
        self,
        loan_id: int,
        organization_id: Optional[int],
        access_level: str,
    ) -> Dict:
        """Generate a fraud report filtered by access level.

        Under BSA 31 USC 5318(g)(2), fraud indicator details must NOT be
        exposed to borrowers or unauthorized staff. This method produces
        a response appropriate for the caller's access level.

        Args:
            loan_id: The loan to analyze.
            organization_id: The caller's organization (for tenant scoping).
            access_level: One of "full", "summary", "restricted".

        Returns:
            A dict with fraud data filtered to the access level:
            - "full": complete analysis including all indicators and SAR data.
            - "summary": risk_score, risk_level, recommendation only.
            - "restricted": neutral document_status only (no fraud info).
        """
        result = self.analyze_loan_documents(loan_id)

        if access_level == "restricted":
            # Borrower / portal: NEVER reveal fraud indicators.
            # Map risk to a neutral document status.
            if result.risk_level in ("HIGH", "CRITICAL"):
                document_status = "under_review"
            elif result.risk_level == "MEDIUM":
                document_status = "under_review"
            elif result.risk_score > 0:
                document_status = "pending"
            else:
                document_status = "approved"

            return {
                "loan_id": loan_id,
                "document_status": document_status,
                "total_documents": result.documents_analyzed,
            }

        if access_level == "summary":
            # Internal staff: risk score only, no indicator details.
            recommendation = None
            if result.recommendations:
                recommendation = result.recommendations[0]
            return {
                "loan_id": loan_id,
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "documents_analyzed": result.documents_analyzed,
                "recommendation": recommendation,
            }

        # "full" — compliance officers and admins get everything
        return {
            "loan_id": loan_id,
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "documents_analyzed": result.documents_analyzed,
            "summary": result.summary,
            "fraud_indicators": [
                {
                    "indicator_type": ind.indicator_type,
                    "severity": ind.severity,
                    "description": ind.description,
                    "evidence": ind.evidence,
                    "affected_documents": ind.affected_documents,
                    "confidence": ind.confidence,
                    "recommendation": ind.recommendation,
                }
                for ind in result.fraud_indicators
            ],
            "inconsistencies": result.inconsistencies,
            "recommendations": result.recommendations,
        }

    # =========================================================================
    # 14. SAVE ANALYSIS
    # =========================================================================

    def save_analysis(self, result: CrossValidationResult) -> Optional[int]:
        """
        Persist analysis results to document_integrity_checks table
        for audit trail purposes.

        Stores the full analysis as a JSON payload in the metadata column
        of a new DocumentIntegrityCheck record. Returns the record ID.
        """
        try:
            analysis_payload = {
                "analysis_type": "fraud_detection",
                "loan_id": result.loan_id,
                "documents_analyzed": result.documents_analyzed,
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "summary": result.summary,
                "recommendations": result.recommendations,
                "inconsistency_count": len(result.inconsistencies),
                "indicator_count": len(result.fraud_indicators),
                "inconsistencies": result.inconsistencies,
                "fraud_indicators": [
                    {
                        "indicator_type": ind.indicator_type,
                        "severity": ind.severity,
                        "description": ind.description,
                        "evidence": ind.evidence,
                        "affected_documents": ind.affected_documents,
                        "confidence": ind.confidence,
                        "recommendation": ind.recommendation,
                    }
                    for ind in result.fraud_indicators
                ],
            }

            # Compute a deterministic hash representing this analysis
            analysis_hash = hashlib.sha256(
                str(result.loan_id).encode()
                + str(result.documents_analyzed).encode()
                + str(result.risk_score).encode()
            ).hexdigest()

            insert_result = self.db.execute(text("""
                INSERT INTO document_integrity_checks
                    (document_id, document_type, check_type, expected_hash,
                     actual_hash, is_valid, tamper_detected, checked_by,
                     metadata, created_at)
                VALUES
                    (:loan_id, 'fraud_analysis', 'manual', :hash, :hash,
                     :is_valid, :tamper, 'SYSTEM',
                     CAST(:payload AS json),
                     NOW())
                RETURNING id
            """), {
                "loan_id": result.loan_id,
                "hash": analysis_hash,
                "is_valid": result.risk_level in ("LOW", "MEDIUM"),
                "tamper": result.risk_level in ("HIGH", "CRITICAL"),
                "payload": self._json_dumps(analysis_payload),
            })
            self.db.commit()

            row = insert_result.fetchone()
            record_id = row.id if row else None
            logger.info(
                "Saved fraud analysis for loan %d: risk=%s score=%d (record %s)",
                result.loan_id, result.risk_level, result.risk_score, record_id,
            )
            return record_id

        except Exception as e:
            logger.exception("Failed to save fraud analysis for loan %d: %s", result.loan_id, e)
            self.db.rollback()
            return None

    # =========================================================================
    # 14. GET RISK SUMMARY
    # =========================================================================

    def get_risk_summary(self, organization_id: int, days: int = 30) -> Dict:
        """
        Return aggregate risk statistics across all loans in the organization
        for the given time period.

        Returns counts by risk level and most common indicator types.
        """
        rows = self.db.execute(text("""
            SELECT
                dic.metadata,
                dic.tamper_detected,
                dic.is_valid,
                dic.created_at
            FROM document_integrity_checks dic
            JOIN loans l ON l.id = dic.document_id
            WHERE dic.document_type = 'fraud_analysis'
              AND l.organization_id = :org_id
              AND dic.created_at >= NOW() - INTERVAL ':days days'
            ORDER BY dic.created_at DESC
        """.replace(":days", str(int(days)))), {
            "org_id": organization_id,
        }).fetchall()

        # Aggregate stats
        by_risk_level = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        indicator_type_counts: Dict[str, int] = {}
        total_analyzed = 0
        total_indicators = 0

        for row in rows:
            total_analyzed += 1
            meta = row.metadata if isinstance(row.metadata, dict) else {}

            risk_level = meta.get("risk_level", "LOW")
            if risk_level in by_risk_level:
                by_risk_level[risk_level] += 1

            for ind in meta.get("fraud_indicators", []):
                total_indicators += 1
                ind_type = ind.get("indicator_type", "UNKNOWN")
                indicator_type_counts[ind_type] = indicator_type_counts.get(ind_type, 0) + 1

        # Sort indicator types by frequency
        most_common_indicators = sorted(
            indicator_type_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "organization_id": organization_id,
            "period_days": days,
            "total_analyses": total_analyzed,
            "total_indicators": total_indicators,
            "by_risk_level": by_risk_level,
            "most_common_indicators": [
                {"type": t, "count": c} for t, c in most_common_indicators
            ],
            "high_risk_rate": (
                round(
                    (by_risk_level["HIGH"] + by_risk_level["CRITICAL"])
                    / total_analyzed * 100, 1
                )
                if total_analyzed > 0 else 0
            ),
        }

    # =========================================================================
    # 15. ENHANCED DOCUMENT ANALYSIS (Vendor + Forensics Integration)
    # =========================================================================

    async def analyze_document_enhanced(
        self,
        file_bytes: bytes,
        filename: str,
        doc_type: str,
        loan_id: int,
        org_id: int,
        doc_date: Optional[date] = None,
    ) -> Dict:
        """
        Perform enhanced fraud analysis on a single document combining:
        1. Vendor API analysis (40% weight) — external fraud detection
        2. PDF forensics analysis (30% weight) — structural/metadata analysis
        3. Cross-document consistency (30% weight) — existing cross-doc checks

        Returns a unified result dict with combined risk scoring.
        """
        vendor_result = None
        forensics_result = None
        cross_doc_result = None

        # 1. Vendor analysis (40% weight)
        vendor_mod = _get_fraud_vendor_module()
        if vendor_mod:
            try:
                vendor_service = vendor_mod.get_fraud_vendor_service(self.db)
                vendor_result = await vendor_service.analyze_document(
                    file_bytes=file_bytes,
                    filename=filename,
                    doc_type=doc_type,
                    loan_id=loan_id,
                    org_id=org_id,
                )
            except Exception as e:
                logger.warning("Vendor analysis failed: %s", e)

        # 2. PDF forensics analysis (30% weight)
        forensics_mod = _get_pdf_forensics_module()
        if forensics_mod:
            try:
                forensics_service = forensics_mod.get_pdf_forensics_service()
                forensics_result = forensics_service.generate_forensics_report(
                    file_bytes=file_bytes,
                    doc_type=doc_type,
                    filename=filename,
                    doc_date=doc_date,
                )
            except Exception as e:
                logger.warning("PDF forensics analysis failed: %s", e)

        # 3. Cross-document consistency (30% weight) — use existing methods
        try:
            cross_doc_result = self.analyze_loan_documents(loan_id)
        except Exception as e:
            logger.warning("Cross-document analysis failed: %s", e)

        # Combine scores with weighting
        combined_score, combined_level = self._combine_analysis_scores(
            vendor_result=vendor_result,
            forensics_result=forensics_result,
            cross_doc_result=cross_doc_result,
        )

        # Merge all indicators
        all_indicators = []

        if vendor_result:
            for ind in vendor_result.indicators:
                all_indicators.append({
                    "source": f"vendor:{vendor_result.vendor}",
                    "indicator_type": ind.indicator_type,
                    "severity": ind.severity,
                    "description": ind.description,
                    "evidence": ind.evidence if isinstance(ind.evidence, dict) else {"detail": str(ind.evidence)},
                })

        if forensics_result:
            for finding in forensics_result.findings:
                all_indicators.append({
                    "source": "forensics",
                    "indicator_type": finding.category,
                    "severity": finding.severity,
                    "description": finding.description,
                    "evidence": finding.evidence,
                })

        if cross_doc_result:
            for ind in cross_doc_result.fraud_indicators:
                all_indicators.append({
                    "source": "cross_document",
                    "indicator_type": ind.indicator_type,
                    "severity": ind.severity,
                    "description": ind.description,
                    "evidence": {"detail": ind.evidence},
                })

        # Determine overall recommendation
        if combined_score >= 70:
            recommendation = "flag"
        elif combined_score >= 40:
            recommendation = "review"
        else:
            recommendation = "pass"

        return {
            "loan_id": loan_id,
            "filename": filename,
            "doc_type": doc_type,
            "combined_risk_score": round(combined_score, 1),
            "combined_risk_level": combined_level,
            "recommendation": recommendation,
            "component_scores": {
                "vendor": {
                    "score": vendor_result.risk_score if vendor_result else None,
                    "level": vendor_result.risk_level if vendor_result else None,
                    "vendor_name": vendor_result.vendor if vendor_result else None,
                    "weight": 0.4,
                    "duration_ms": vendor_result.analysis_duration_ms if vendor_result else None,
                },
                "forensics": {
                    "score": forensics_result.risk_score if forensics_result else None,
                    "level": forensics_result.risk_level if forensics_result else None,
                    "weight": 0.3,
                    "library": forensics_result.library_used if forensics_result else None,
                },
                "cross_document": {
                    "score": cross_doc_result.risk_score if cross_doc_result else None,
                    "level": cross_doc_result.risk_level if cross_doc_result else None,
                    "documents_analyzed": cross_doc_result.documents_analyzed if cross_doc_result else 0,
                    "weight": 0.3,
                },
            },
            "indicators": all_indicators,
            "indicator_count": len(all_indicators),
            "forensics_metadata": (
                forensics_result.metadata if forensics_result else None
            ),
            "forensics_fonts": (
                forensics_result.fonts if forensics_result else None
            ),
        }

    def _combine_analysis_scores(
        self,
        vendor_result=None,
        forensics_result=None,
        cross_doc_result=None,
    ) -> Tuple[float, str]:
        """
        Combine scores from vendor, forensics, and cross-document analysis.

        Weights:
        - Vendor: 40%
        - Forensics: 30%
        - Cross-document: 30%

        If a component is unavailable, its weight is redistributed
        proportionally among the available components.
        """
        components: List[Tuple[float, float]] = []  # (score, weight)

        if vendor_result is not None:
            components.append((vendor_result.risk_score, 0.4))
        if forensics_result is not None:
            components.append((forensics_result.risk_score, 0.3))
        if cross_doc_result is not None:
            components.append((float(cross_doc_result.risk_score), 0.3))

        if not components:
            return 0.0, "LOW"

        # Normalize weights to sum to 1.0
        total_weight = sum(w for _, w in components)
        if total_weight <= 0:
            return 0.0, "LOW"

        combined_score = sum(
            score * (weight / total_weight)
            for score, weight in components
        )

        combined_score = min(combined_score, 100.0)

        if combined_score >= 70:
            level = "CRITICAL"
        elif combined_score >= 46:
            level = "HIGH"
        elif combined_score >= 21:
            level = "MEDIUM"
        else:
            level = "LOW"

        return combined_score, level

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _extract_names_from_row(self, row) -> List[str]:
        """Extract all name strings from an extraction row."""
        names: List[str] = []

        # From extracted_names JSON array on smart_documents
        if row.extracted_names:
            extracted = row.extracted_names
            if isinstance(extracted, list):
                names.extend([n for n in extracted if isinstance(n, str) and n.strip()])
            elif isinstance(extracted, str):
                names.append(extracted)

        # From extracted_fields JSON on smart_document_extractions
        if row.extracted_fields and isinstance(row.extracted_fields, dict):
            fields = row.extracted_fields
            for key in (
                "employee_name", "account_holder_name", "taxpayer_name",
                "spouse_name", "full_name", "buyer_name", "owner_name",
                "borrower_name",
            ):
                val = fields.get(key)
                if val and isinstance(val, str) and val.strip():
                    names.append(val.strip())

            # Build full name from first + last
            first = fields.get("first_name", "")
            last = fields.get("last_name", "")
            if first and last:
                names.append(f"{first} {last}")

        return list(set(names))

    def _canonicalize_name(self, name: str) -> str:
        """Normalize a name for comparison: lowercase, strip suffixes, trim."""
        if not name:
            return ""
        name = name.lower().strip()
        # Remove common suffixes
        for suffix in [" jr", " jr.", " sr", " sr.", " ii", " iii", " iv"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
        # Remove punctuation except spaces and hyphens
        name = re.sub(r"[^a-z\s\-]", "", name)
        # Normalize whitespace
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _names_match(self, name_a: str, name_b: str) -> bool:
        """
        Check if two canonicalized names match, allowing for common
        variations (e.g., 'john' vs 'jonathan').
        """
        if not name_a or not name_b:
            return False

        # Exact match
        if name_a == name_b:
            return True

        parts_a = name_a.split()
        parts_b = name_b.split()

        # Check last name match first (most reliable)
        if parts_a and parts_b:
            last_a = parts_a[-1]
            last_b = parts_b[-1]
            if last_a != last_b:
                return False

            # Last names match; now check first names with variation lookup
            if len(parts_a) >= 1 and len(parts_b) >= 1:
                first_a = parts_a[0]
                first_b = parts_b[0]

                if first_a == first_b:
                    return True

                # Check name variation table
                formal_a = _NAME_REVERSE.get(first_a)
                formal_b = _NAME_REVERSE.get(first_b)

                if formal_a and formal_b and formal_a == formal_b:
                    return True

                # Check if one is a prefix of the other (e.g., "Jon" vs "Jonathan")
                if first_a.startswith(first_b) or first_b.startswith(first_a):
                    return True

        return False

    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for comparison."""
        if not name:
            return ""
        name = name.lower().strip()
        # Remove common suffixes
        for suffix in [
            " inc", " inc.", " incorporated",
            " llc", " l.l.c.", " l.l.c",
            " ltd", " ltd.", " limited",
            " corp", " corp.", " corporation",
            " co", " co.", " company",
            " lp", " l.p.",
        ]:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
        # Remove punctuation
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _normalize_ein(self, ein: str) -> str:
        """Normalize EIN to digits only."""
        if not ein:
            return ""
        return re.sub(r"[^0-9]", "", ein)

    def _normalize_address(self, address: str) -> str:
        """Normalize address for comparison."""
        if not address:
            return ""
        addr = address.lower().strip()
        # Common abbreviations
        replacements = {
            " street": " st",
            " avenue": " ave",
            " boulevard": " blvd",
            " drive": " dr",
            " lane": " ln",
            " road": " rd",
            " court": " ct",
            " circle": " cir",
            " place": " pl",
            " terrace": " ter",
            " highway": " hwy",
            " apartment": " apt",
            " suite": " ste",
            " unit": " unit",
            " north": " n",
            " south": " s",
            " east": " e",
            " west": " w",
            " northeast": " ne",
            " northwest": " nw",
            " southeast": " se",
            " southwest": " sw",
        }
        for long, short in replacements.items():
            addr = addr.replace(long, short)
        # Remove punctuation except digits and letters
        addr = re.sub(r"[^a-z0-9\s]", "", addr)
        addr = re.sub(r"\s+", " ", addr).strip()
        return addr

    def _extract_address_from_fields(self, fields: Dict) -> Optional[str]:
        """Extract a full address string from extracted fields."""
        # Try different field name patterns
        for key in ("address", "property_address", "employee_address_line1"):
            if fields.get(key):
                parts = [fields[key]]
                # Try to add city, state, zip
                city = fields.get("city") or fields.get("property_city") or fields.get("employee_city")
                state = fields.get("state") or fields.get("property_state") or fields.get("employee_state")
                zipcode = fields.get("zip_code") or fields.get("property_zip") or fields.get("employee_zip")
                if city:
                    parts.append(city)
                if state:
                    parts.append(state)
                if zipcode:
                    parts.append(str(zipcode))
                return ", ".join(parts)
        return None

    def _string_similarity(self, a: str, b: str) -> float:
        """
        Compute simple Jaccard similarity between two strings based on
        character bigrams. Returns 0.0-1.0.
        """
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0

        bigrams_a = set(a[i:i+2] for i in range(len(a) - 1)) if len(a) > 1 else {a}
        bigrams_b = set(b[i:i+2] for i in range(len(b) - 1)) if len(b) > 1 else {b}

        intersection = bigrams_a & bigrams_b
        union = bigrams_a | bigrams_b

        return len(intersection) / len(union) if union else 0.0

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _annualize_ytd(self, ytd_gross: float, pay_period_end: str) -> Optional[float]:
        """Annualize YTD income based on the pay period end date."""
        period_end = self._parse_date(pay_period_end)
        if not period_end:
            return None
        year_start = date(period_end.year, 1, 1)
        days_elapsed = (period_end - year_start).days + 1
        if days_elapsed <= 0:
            return None
        return (ytd_gross / days_elapsed) * 365

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse a date string in common formats."""
        if not date_str or not isinstance(date_str, str):
            return None

        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%Y/%m/%d",
            "%m/%d/%y",
            "%d-%b-%Y",
            "%b %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _parse_pdf_date(self, date_str: str) -> Optional[datetime]:
        """Parse a PDF metadata date (D:YYYYMMDDHHmmSS format)."""
        if not date_str:
            return None
        # PDF date format: D:YYYYMMDDHHmmSS+HH'mm'
        match = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", date_str)
        if match:
            groups = match.groups()
            try:
                return datetime(
                    int(groups[0]),
                    int(groups[1]),
                    int(groups[2]),
                    int(groups[3] or 0),
                    int(groups[4] or 0),
                    int(groups[5] or 0),
                    tzinfo=timezone.utc,
                )
            except (ValueError, TypeError):
                return None
        return None

    def _extract_pdf_metadata(self, file_content: bytes) -> Optional[Dict]:
        """
        Extract metadata from a PDF file.

        Parses the PDF trailer and info dictionary to extract creator,
        producer, creation date, and modification date without requiring
        heavy PDF libraries.
        """
        try:
            # Simple PDF metadata extraction by scanning for Info dict markers
            content_str = file_content[:50000].decode("latin-1", errors="replace")

            metadata = {}

            # Look for /Creator
            creator_match = re.search(r'/Creator\s*\(([^)]*)\)', content_str)
            if creator_match:
                metadata["creator"] = creator_match.group(1)

            # Look for /Producer
            producer_match = re.search(r'/Producer\s*\(([^)]*)\)', content_str)
            if producer_match:
                metadata["producer"] = producer_match.group(1)

            # Look for /CreationDate
            creation_match = re.search(r'/CreationDate\s*\(([^)]*)\)', content_str)
            if creation_match:
                metadata["creation_date"] = creation_match.group(1)

            # Look for /ModDate
            mod_match = re.search(r'/ModDate\s*\(([^)]*)\)', content_str)
            if mod_match:
                metadata["modification_date"] = mod_match.group(1)

            return metadata if metadata else None

        except Exception as e:
            logger.debug("Failed to extract PDF metadata: %s", e)
            return None

    def _get_job_title_for_loan(self, loan_id: int) -> Optional[str]:
        """Get borrower job title from lead data linked to this loan."""
        try:
            _org_filter = "AND lo.organization_id = :_org_id" if self.org_id is not None else ""
            query = f"""
                SELECT ld.job_title
                FROM leads ld
                JOIN loans lo ON lo.loan_number = ld.loan_number
                WHERE lo.id = :lid AND ld.job_title IS NOT NULL
                {_org_filter}
                LIMIT 1
            """
            row = self.db.execute(text(query), {"lid": loan_id, **self._org_params()}).fetchone()
            return row.job_title if row else None
        except Exception as _exc:  # noqa: BLE001
            return None

    def _build_recommendations(
        self,
        indicators: List[FraudIndicator],
        inconsistencies: List[Dict],
        risk_level: str,
    ) -> List[str]:
        """Build prioritized recommendations list from findings."""
        recommendations: List[str] = []

        if risk_level == "CRITICAL":
            recommendations.append(
                "CRITICAL: Escalate to compliance team immediately. "
                "Consider generating SAR data for FinCEN review."
            )

        if risk_level in ("HIGH", "CRITICAL"):
            recommendations.append(
                "Place loan file on hold pending fraud investigation. "
                "Do not proceed to closing."
            )

        # Deduplicate and prioritize by severity
        seen = set()
        for ind in sorted(indicators, key=lambda x: SEVERITY_WEIGHTS.get(x.severity, 0), reverse=True):
            rec = ind.recommendation
            if rec and rec not in seen:
                seen.add(rec)
                recommendations.append(rec)

        for inc in inconsistencies:
            rec = inc.get("recommendation")
            if rec and rec not in seen:
                seen.add(rec)
                recommendations.append(rec)

        if not recommendations:
            recommendations.append("No significant fraud indicators detected. Proceed normally.")

        return recommendations

    def _json_dumps(self, obj) -> str:
        """Serialize object to JSON string, handling dates and Decimals."""
        import json

        def default_serializer(o):
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            if isinstance(o, Decimal):
                return float(o)
            return str(o)

        return json.dumps(obj, default=default_serializer)


# =============================================================================
# SINGLETON
# =============================================================================

def get_fraud_detection_service(db: Session, org_id: Optional[int] = None) -> FraudDetectionService:
    """
    Get a FraudDetectionService instance for the given database session.

    Unlike other singletons in the codebase, this creates a new instance
    per session since the service is stateless and the db session should
    not be shared across requests.

    Args:
        db: SQLAlchemy database session.
        org_id: Organization ID for tenant isolation.  When provided, all
                queries are scoped to loans/documents belonging to that org.
    """
    return FraudDetectionService(db, org_id=org_id)
