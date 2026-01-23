"""
Loan Engineering System
Validates loan file data, detects inconsistencies, and ensures data quality.
Key capabilities:
- Data completeness validation
- Cross-field consistency checks
- Document-to-application matching
- Fraud indicator detection
- Data normalization and cleaning
- Error/warning classification
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import re
import logging

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Severity levels for validation findings."""
    ERROR = "error"  # Must be resolved
    WARNING = "warning"  # Should be reviewed
    INFO = "info"  # Informational only
    FRAUD_ALERT = "fraud_alert"  # Potential fraud indicator


class ValidationCategory(str, Enum):
    """Categories of validation."""
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    COMPLIANCE = "compliance"
    FRAUD_DETECTION = "fraud_detection"
    DATA_QUALITY = "data_quality"


@dataclass
class ValidationFinding:
    """A single validation finding."""
    field: str
    message: str
    severity: ValidationSeverity
    category: ValidationCategory
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None
    resolution_hint: Optional[str] = None
    related_fields: List[str] = field(default_factory=list)
    confidence_score: float = 1.0  # 0-1 confidence in finding


@dataclass
class ValidationResult:
    """Result of loan file validation."""
    is_valid: bool
    loan_id: Optional[str] = None
    validation_timestamp: datetime = field(default_factory=datetime.now)
    findings: List[ValidationFinding] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    fraud_alert_count: int = 0
    completeness_score: float = 0.0  # 0-100
    data_quality_score: float = 0.0  # 0-100
    overall_score: float = 0.0  # 0-100

    def add_finding(self, finding: ValidationFinding):
        """Add a finding and update counts."""
        self.findings.append(finding)
        if finding.severity == ValidationSeverity.ERROR:
            self.error_count += 1
        elif finding.severity == ValidationSeverity.WARNING:
            self.warning_count += 1
        elif finding.severity == ValidationSeverity.FRAUD_ALERT:
            self.fraud_alert_count += 1

    def get_findings_by_severity(self, severity: ValidationSeverity) -> List[ValidationFinding]:
        """Get findings filtered by severity."""
        return [f for f in self.findings if f.severity == severity]

    def get_findings_by_category(self, category: ValidationCategory) -> List[ValidationFinding]:
        """Get findings filtered by category."""
        return [f for f in self.findings if f.category == category]


class LoanDataValidator:
    """
    Validates loan file data for completeness, consistency, and accuracy.
    """

    # Required fields by loan status
    REQUIRED_FIELDS_BY_STATUS = {
        "application": [
            "borrower_first_name", "borrower_last_name", "borrower_ssn",
            "property_address", "loan_amount", "property_value",
            "loan_purpose", "loan_type", "occupancy_type",
        ],
        "processing": [
            "borrower_first_name", "borrower_last_name", "borrower_ssn",
            "property_address", "loan_amount", "property_value",
            "loan_purpose", "loan_type", "occupancy_type",
            "employer_name", "employment_start_date", "monthly_income",
        ],
        "underwriting": [
            "borrower_first_name", "borrower_last_name", "borrower_ssn",
            "property_address", "loan_amount", "property_value",
            "loan_purpose", "loan_type", "occupancy_type",
            "employer_name", "employment_start_date", "monthly_income",
            "credit_score", "dti_ratio", "ltv",
        ],
        "approval": [
            "borrower_first_name", "borrower_last_name", "borrower_ssn",
            "property_address", "loan_amount", "property_value",
            "loan_purpose", "loan_type", "occupancy_type",
            "employer_name", "employment_start_date", "monthly_income",
            "credit_score", "dti_ratio", "ltv", "interest_rate",
            "appraisal_value",
        ],
    }

    # Field validation rules
    FIELD_RULES = {
        "borrower_ssn": {
            "pattern": r"^\d{3}-?\d{2}-?\d{4}$",
            "message": "SSN must be 9 digits",
        },
        "email": {
            "pattern": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
            "message": "Invalid email format",
        },
        "phone": {
            "pattern": r"^[\d\-\(\)\s]{10,}$",
            "message": "Phone must have at least 10 digits",
        },
        "zip_code": {
            "pattern": r"^\d{5}(-\d{4})?$",
            "message": "ZIP code must be 5 or 9 digits",
        },
        "credit_score": {
            "min": 300,
            "max": 850,
            "message": "Credit score must be between 300 and 850",
        },
        "loan_amount": {
            "min": 1000,
            "max": 50000000,
            "message": "Loan amount out of valid range",
        },
        "interest_rate": {
            "min": 0.5,
            "max": 20.0,
            "message": "Interest rate out of valid range",
        },
        "ltv": {
            "min": 1,
            "max": 105,  # Some programs allow 105%
            "message": "LTV out of valid range",
        },
        "dti_ratio": {
            "min": 0,
            "max": 100,
            "message": "DTI ratio out of valid range",
        },
    }

    # Consistency rules (field pairs that should match or relate)
    CONSISTENCY_RULES = [
        {
            "name": "loan_amount_vs_property_value",
            "fields": ["loan_amount", "property_value"],
            "check": lambda data: data.get("loan_amount", 0) <= data.get("property_value", 0) * 1.05,
            "message": "Loan amount exceeds property value (LTV > 105%)",
        },
        {
            "name": "ltv_calculation",
            "fields": ["ltv", "loan_amount", "property_value"],
            "check": lambda data: abs(
                (data.get("loan_amount", 0) / max(data.get("property_value", 1), 1) * 100) -
                data.get("ltv", 0)
            ) < 1 if data.get("ltv") else True,
            "message": "LTV doesn't match loan amount / property value calculation",
        },
        {
            "name": "appraisal_vs_purchase",
            "fields": ["appraisal_value", "property_value"],
            "check": lambda data: (
                data.get("appraisal_value") is None or
                abs(data.get("appraisal_value", 0) - data.get("property_value", 0)) /
                max(data.get("property_value", 1), 1) < 0.15
            ),
            "message": "Appraisal value differs significantly from purchase price (>15%)",
        },
        {
            "name": "employment_date_logic",
            "fields": ["employment_start_date", "borrower_dob"],
            "check": lambda data: (
                data.get("employment_start_date") is None or
                data.get("borrower_dob") is None or
                data.get("employment_start_date") > data.get("borrower_dob") + timedelta(days=16*365)
            ),
            "message": "Employment start date suggests working before age 16",
        },
        {
            "name": "closing_date_logic",
            "fields": ["expected_close_date", "application_date"],
            "check": lambda data: (
                data.get("expected_close_date") is None or
                data.get("application_date") is None or
                data.get("expected_close_date") > data.get("application_date")
            ),
            "message": "Expected close date is before application date",
        },
        {
            "name": "income_vs_dti",
            "fields": ["monthly_income", "dti_ratio", "monthly_debt_payment"],
            "check": lambda data: (
                data.get("monthly_income") is None or
                data.get("dti_ratio") is None or
                data.get("monthly_debt_payment") is None or
                abs(
                    (data.get("monthly_debt_payment", 0) / max(data.get("monthly_income", 1), 1) * 100) -
                    data.get("dti_ratio", 0)
                ) < 5
            ),
            "message": "DTI ratio doesn't match debt/income calculation",
        },
    ]

    def __init__(self):
        self.fraud_detector = FraudIndicatorDetector()

    def validate(
        self,
        loan_data: Dict[str, Any],
        loan_status: str = "application",
        include_fraud_check: bool = True,
    ) -> ValidationResult:
        """
        Perform comprehensive validation on loan data.

        Args:
            loan_data: Dictionary of loan file data
            loan_status: Current status (determines required fields)
            include_fraud_check: Whether to run fraud detection

        Returns:
            ValidationResult with all findings
        """
        result = ValidationResult(
            is_valid=True,  # Will be set to False if errors found
            loan_id=loan_data.get("loan_id") or loan_data.get("id"),
        )

        # Check completeness
        self._check_completeness(loan_data, loan_status, result)

        # Check field formats and ranges
        self._check_field_validity(loan_data, result)

        # Check consistency between fields
        self._check_consistency(loan_data, result)

        # Check data quality
        self._check_data_quality(loan_data, result)

        # Fraud detection
        if include_fraud_check:
            fraud_findings = self.fraud_detector.analyze(loan_data)
            for finding in fraud_findings:
                result.add_finding(finding)

        # Calculate scores
        self._calculate_scores(loan_data, loan_status, result)

        # Determine overall validity
        result.is_valid = result.error_count == 0 and result.fraud_alert_count == 0

        return result

    def _check_completeness(
        self,
        loan_data: Dict[str, Any],
        loan_status: str,
        result: ValidationResult,
    ):
        """Check if all required fields are present."""
        required_fields = self.REQUIRED_FIELDS_BY_STATUS.get(
            loan_status,
            self.REQUIRED_FIELDS_BY_STATUS["application"]
        )

        missing_fields = []
        for field_name in required_fields:
            value = loan_data.get(field_name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing_fields.append(field_name)
                result.add_finding(ValidationFinding(
                    field=field_name,
                    message=f"Required field '{field_name}' is missing",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.COMPLETENESS,
                    resolution_hint=f"Provide value for {field_name}",
                ))

        # Calculate completeness score
        total_fields = len(required_fields)
        present_fields = total_fields - len(missing_fields)
        result.completeness_score = (present_fields / total_fields * 100) if total_fields > 0 else 100

    def _check_field_validity(
        self,
        loan_data: Dict[str, Any],
        result: ValidationResult,
    ):
        """Check field formats and value ranges."""
        for field_name, rules in self.FIELD_RULES.items():
            value = loan_data.get(field_name)
            if value is None:
                continue

            # Pattern check
            if "pattern" in rules and isinstance(value, str):
                if not re.match(rules["pattern"], value):
                    result.add_finding(ValidationFinding(
                        field=field_name,
                        message=rules["message"],
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.ACCURACY,
                        actual_value=value,
                        resolution_hint=f"Correct the format of {field_name}",
                    ))

            # Range check
            if "min" in rules or "max" in rules:
                try:
                    num_value = float(value)
                    if "min" in rules and num_value < rules["min"]:
                        result.add_finding(ValidationFinding(
                            field=field_name,
                            message=f"{field_name} below minimum ({rules['min']})",
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.ACCURACY,
                            expected_value=f">= {rules['min']}",
                            actual_value=num_value,
                        ))
                    if "max" in rules and num_value > rules["max"]:
                        result.add_finding(ValidationFinding(
                            field=field_name,
                            message=f"{field_name} above maximum ({rules['max']})",
                            severity=ValidationSeverity.ERROR,
                            category=ValidationCategory.ACCURACY,
                            expected_value=f"<= {rules['max']}",
                            actual_value=num_value,
                        ))
                except (ValueError, TypeError):
                    result.add_finding(ValidationFinding(
                        field=field_name,
                        message=f"{field_name} is not a valid number",
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.ACCURACY,
                        actual_value=value,
                    ))

    def _check_consistency(
        self,
        loan_data: Dict[str, Any],
        result: ValidationResult,
    ):
        """Check consistency between related fields."""
        for rule in self.CONSISTENCY_RULES:
            # Check if all required fields are present
            all_present = all(
                loan_data.get(f) is not None
                for f in rule["fields"]
            )

            if all_present:
                try:
                    if not rule["check"](loan_data):
                        result.add_finding(ValidationFinding(
                            field=rule["fields"][0],
                            message=rule["message"],
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.CONSISTENCY,
                            related_fields=rule["fields"],
                            resolution_hint="Review and correct the related values",
                        ))
                except Exception as e:
                    logger.warning(f"Consistency check '{rule['name']}' failed: {e}")

    def _check_data_quality(
        self,
        loan_data: Dict[str, Any],
        result: ValidationResult,
    ):
        """Check for data quality issues."""
        # Check for placeholder data
        placeholder_patterns = [
            (r"^test", "Test data detected"),
            (r"^sample", "Sample data detected"),
            (r"^xxx", "Placeholder data detected"),
            (r"^tbd$", "TBD placeholder detected"),
            (r"^n/a$", "N/A placeholder detected"),
        ]

        for field_name, value in loan_data.items():
            if isinstance(value, str):
                value_lower = value.lower().strip()
                for pattern, message in placeholder_patterns:
                    if re.match(pattern, value_lower):
                        result.add_finding(ValidationFinding(
                            field=field_name,
                            message=f"{message} in {field_name}",
                            severity=ValidationSeverity.WARNING,
                            category=ValidationCategory.DATA_QUALITY,
                            actual_value=value,
                        ))
                        break

        # Check for duplicate data that shouldn't be duplicate
        if loan_data.get("borrower_first_name") == loan_data.get("borrower_last_name"):
            result.add_finding(ValidationFinding(
                field="borrower_name",
                message="First name and last name are identical",
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.DATA_QUALITY,
                related_fields=["borrower_first_name", "borrower_last_name"],
            ))

        # Check for reasonable dates
        self._check_date_quality(loan_data, result)

    def _check_date_quality(
        self,
        loan_data: Dict[str, Any],
        result: ValidationResult,
    ):
        """Check date fields for quality issues."""
        date_fields = [
            "application_date", "expected_close_date", "borrower_dob",
            "employment_start_date", "lock_date", "lock_expiration_date",
        ]

        today = date.today()
        min_reasonable_date = date(1900, 1, 1)
        max_reasonable_date = today + timedelta(days=365)

        for field_name in date_fields:
            value = loan_data.get(field_name)
            if value is None:
                continue

            # Convert to date if datetime
            if isinstance(value, datetime):
                value = value.date()
            elif isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                except ValueError:
                    result.add_finding(ValidationFinding(
                        field=field_name,
                        message=f"Invalid date format in {field_name}",
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.DATA_QUALITY,
                        actual_value=loan_data.get(field_name),
                    ))
                    continue

            if not isinstance(value, date):
                continue

            if value < min_reasonable_date:
                result.add_finding(ValidationFinding(
                    field=field_name,
                    message=f"{field_name} is unreasonably old",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.DATA_QUALITY,
                    actual_value=str(value),
                ))

            if value > max_reasonable_date:
                result.add_finding(ValidationFinding(
                    field=field_name,
                    message=f"{field_name} is more than 1 year in the future",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.DATA_QUALITY,
                    actual_value=str(value),
                ))

    def _calculate_scores(
        self,
        loan_data: Dict[str, Any],
        loan_status: str,
        result: ValidationResult,
    ):
        """Calculate quality and overall scores."""
        # Data quality score based on findings
        quality_issues = len([
            f for f in result.findings
            if f.category == ValidationCategory.DATA_QUALITY
        ])
        result.data_quality_score = max(0, 100 - quality_issues * 10)

        # Overall score
        error_penalty = result.error_count * 20
        warning_penalty = result.warning_count * 5
        fraud_penalty = result.fraud_alert_count * 30

        base_score = (result.completeness_score + result.data_quality_score) / 2
        result.overall_score = max(0, base_score - error_penalty - warning_penalty - fraud_penalty)


class FraudIndicatorDetector:
    """
    Detects potential fraud indicators in loan file data.
    Based on common mortgage fraud patterns.
    """

    def analyze(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """
        Analyze loan data for fraud indicators.

        Returns list of fraud-related findings.
        """
        findings = []

        # Income fraud indicators
        findings.extend(self._check_income_fraud(loan_data))

        # Asset fraud indicators
        findings.extend(self._check_asset_fraud(loan_data))

        # Property fraud indicators
        findings.extend(self._check_property_fraud(loan_data))

        # Identity fraud indicators
        findings.extend(self._check_identity_fraud(loan_data))

        # Occupancy fraud indicators
        findings.extend(self._check_occupancy_fraud(loan_data))

        return findings

    def _check_income_fraud(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """Check for income fraud indicators."""
        findings = []

        monthly_income = loan_data.get("monthly_income", 0)
        stated_income = loan_data.get("stated_income", 0)
        verified_income = loan_data.get("verified_income", 0)

        # Check for significant income variance
        if stated_income and verified_income:
            variance = abs(stated_income - verified_income) / max(stated_income, 1) * 100
            if variance > 25:
                findings.append(ValidationFinding(
                    field="income",
                    message=f"Stated income differs from verified income by {variance:.0f}%",
                    severity=ValidationSeverity.FRAUD_ALERT,
                    category=ValidationCategory.FRAUD_DETECTION,
                    expected_value=stated_income,
                    actual_value=verified_income,
                    confidence_score=min(variance / 50, 1.0),
                ))

        # Check for income that seems too high for occupation
        occupation = loan_data.get("occupation", "").lower()
        if monthly_income > 50000:  # $600k+ annual
            typical_high_income_jobs = [
                "ceo", "doctor", "surgeon", "attorney", "partner",
                "executive", "president", "director", "physician",
            ]
            if not any(job in occupation for job in typical_high_income_jobs):
                findings.append(ValidationFinding(
                    field="monthly_income",
                    message="Very high income for stated occupation",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FRAUD_DETECTION,
                    related_fields=["occupation", "monthly_income"],
                    resolution_hint="Verify income documentation matches stated occupation",
                ))

        # Check employment length vs income
        years_employed = loan_data.get("years_at_employer", 0)
        if years_employed < 1 and monthly_income > 20000:
            findings.append(ValidationFinding(
                field="employment",
                message="High income with less than 1 year at employer",
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.FRAUD_DETECTION,
                related_fields=["years_at_employer", "monthly_income"],
            ))

        return findings

    def _check_asset_fraud(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """Check for asset fraud indicators."""
        findings = []

        total_assets = loan_data.get("total_assets", 0)
        liquid_assets = loan_data.get("liquid_assets", 0)
        monthly_income = loan_data.get("monthly_income", 0)

        # Assets inconsistent with income
        if liquid_assets > monthly_income * 36:  # 3 years of income in liquid assets
            annual_income = monthly_income * 12
            if annual_income > 0 and annual_income < 200000:  # Not a high earner
                findings.append(ValidationFinding(
                    field="liquid_assets",
                    message="Liquid assets seem high relative to income",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FRAUD_DETECTION,
                    related_fields=["liquid_assets", "monthly_income"],
                    resolution_hint="Verify source of funds documentation",
                ))

        # Large recent deposits pattern
        large_deposits = loan_data.get("large_deposits", [])
        if isinstance(large_deposits, list) and len(large_deposits) > 3:
            findings.append(ValidationFinding(
                field="large_deposits",
                message=f"Multiple large deposits ({len(large_deposits)}) require documentation",
                severity=ValidationSeverity.WARNING,
                category=ValidationCategory.FRAUD_DETECTION,
                resolution_hint="Obtain source documentation for all large deposits",
            ))

        return findings

    def _check_property_fraud(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """Check for property fraud indicators."""
        findings = []

        property_value = loan_data.get("property_value", 0)
        appraisal_value = loan_data.get("appraisal_value", 0)
        prior_sale_price = loan_data.get("prior_sale_price", 0)
        prior_sale_date = loan_data.get("prior_sale_date")

        # Rapid appreciation (property flip indicators)
        if prior_sale_price and prior_sale_date and property_value:
            if isinstance(prior_sale_date, str):
                try:
                    prior_sale_date = datetime.fromisoformat(prior_sale_date.replace('Z', '+00:00')).date()
                except ValueError:
                    prior_sale_date = None

            if prior_sale_date:
                months_since_sale = (date.today().year - prior_sale_date.year) * 12 + \
                                   (date.today().month - prior_sale_date.month)

                if months_since_sale < 6 and months_since_sale > 0:
                    appreciation = (property_value - prior_sale_price) / prior_sale_price * 100
                    if appreciation > 20:
                        findings.append(ValidationFinding(
                            field="property_value",
                            message=f"Property value increased {appreciation:.0f}% in {months_since_sale} months",
                            severity=ValidationSeverity.FRAUD_ALERT,
                            category=ValidationCategory.FRAUD_DETECTION,
                            related_fields=["property_value", "prior_sale_price", "prior_sale_date"],
                            resolution_hint="Review for potential property flipping scheme",
                            confidence_score=min(appreciation / 50, 1.0),
                        ))

        # Appraisal variance
        if appraisal_value and property_value:
            variance = abs(appraisal_value - property_value) / property_value * 100
            if variance > 10:
                findings.append(ValidationFinding(
                    field="appraisal_value",
                    message=f"Appraisal differs from contract price by {variance:.0f}%",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FRAUD_DETECTION,
                    expected_value=property_value,
                    actual_value=appraisal_value,
                ))

        return findings

    def _check_identity_fraud(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """Check for identity fraud indicators."""
        findings = []

        ssn = loan_data.get("borrower_ssn", "")
        dob = loan_data.get("borrower_dob")

        # SSN validation
        if ssn:
            # Remove formatting
            ssn_clean = re.sub(r'[^0-9]', '', ssn)

            # Check for invalid SSN patterns
            if len(ssn_clean) == 9:
                # Area number 000, 666, or 900-999
                area = int(ssn_clean[:3])
                if area == 0 or area == 666 or area >= 900:
                    findings.append(ValidationFinding(
                        field="borrower_ssn",
                        message="SSN area number is invalid",
                        severity=ValidationSeverity.FRAUD_ALERT,
                        category=ValidationCategory.FRAUD_DETECTION,
                    ))

                # Check for sequential or repeating patterns
                if ssn_clean in ["123456789", "987654321"] or len(set(ssn_clean)) == 1:
                    findings.append(ValidationFinding(
                        field="borrower_ssn",
                        message="SSN appears to be a placeholder pattern",
                        severity=ValidationSeverity.FRAUD_ALERT,
                        category=ValidationCategory.FRAUD_DETECTION,
                    ))

        # Age reasonableness
        if dob:
            if isinstance(dob, str):
                try:
                    dob = datetime.fromisoformat(dob.replace('Z', '+00:00')).date()
                except ValueError:
                    dob = None

            if dob:
                age = (date.today() - dob).days / 365.25
                if age < 18:
                    findings.append(ValidationFinding(
                        field="borrower_dob",
                        message="Borrower appears to be under 18",
                        severity=ValidationSeverity.FRAUD_ALERT,
                        category=ValidationCategory.FRAUD_DETECTION,
                    ))
                elif age > 100:
                    findings.append(ValidationFinding(
                        field="borrower_dob",
                        message="Borrower age exceeds 100 years",
                        severity=ValidationSeverity.WARNING,
                        category=ValidationCategory.FRAUD_DETECTION,
                        resolution_hint="Verify date of birth documentation",
                    ))

        return findings

    def _check_occupancy_fraud(self, loan_data: Dict[str, Any]) -> List[ValidationFinding]:
        """Check for occupancy fraud indicators."""
        findings = []

        occupancy_type = loan_data.get("occupancy_type", "").lower()
        current_address = loan_data.get("current_address", "").lower()
        property_address = loan_data.get("property_address", "").lower()
        distance_to_work = loan_data.get("distance_to_work_miles")
        other_properties_owned = loan_data.get("other_properties_owned", 0)

        # Primary residence claimed but indicators suggest otherwise
        if occupancy_type == "primary":
            # Already owns other property in same area
            if other_properties_owned > 0:
                findings.append(ValidationFinding(
                    field="occupancy_type",
                    message="Claims primary residence but owns other properties",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FRAUD_DETECTION,
                    resolution_hint="Verify intent to occupy and disposition of other properties",
                ))

            # Long distance from employment
            if distance_to_work and distance_to_work > 100:
                findings.append(ValidationFinding(
                    field="occupancy_type",
                    message=f"Primary residence {distance_to_work} miles from employment",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.FRAUD_DETECTION,
                    resolution_hint="Verify borrower's plan for occupancy with this commute",
                ))

        return findings


class DocumentMatcher:
    """
    Matches document data against application data to verify consistency.
    """

    def match_paystub(
        self,
        paystub_data: Dict[str, Any],
        application_data: Dict[str, Any],
    ) -> List[ValidationFinding]:
        """Match paystub data against application."""
        findings = []

        # Employer name match
        app_employer = (application_data.get("employer_name") or "").lower()
        doc_employer = (paystub_data.get("employer_name") or "").lower()

        if app_employer and doc_employer:
            if not self._fuzzy_match(app_employer, doc_employer, threshold=0.8):
                findings.append(ValidationFinding(
                    field="employer_name",
                    message="Paystub employer doesn't match application",
                    severity=ValidationSeverity.ERROR,
                    category=ValidationCategory.CONSISTENCY,
                    expected_value=application_data.get("employer_name"),
                    actual_value=paystub_data.get("employer_name"),
                ))

        # Income comparison
        app_income = application_data.get("monthly_income", 0)
        ytd_earnings = paystub_data.get("ytd_earnings", 0)
        pay_period_end = paystub_data.get("pay_period_end")

        if ytd_earnings and pay_period_end:
            if isinstance(pay_period_end, str):
                try:
                    pay_period_end = datetime.fromisoformat(pay_period_end.replace('Z', '+00:00')).date()
                except ValueError:
                    pay_period_end = None

            if pay_period_end:
                months_elapsed = pay_period_end.month + (pay_period_end.day / 30)
                annualized = (ytd_earnings / months_elapsed) * 12 if months_elapsed > 0 else 0
                monthly_calculated = annualized / 12

                variance = abs(monthly_calculated - app_income) / max(app_income, 1) * 100

                if variance > 15:
                    findings.append(ValidationFinding(
                        field="monthly_income",
                        message=f"Income on paystub differs from application by {variance:.0f}%",
                        severity=ValidationSeverity.WARNING if variance < 25 else ValidationSeverity.ERROR,
                        category=ValidationCategory.CONSISTENCY,
                        expected_value=app_income,
                        actual_value=round(monthly_calculated, 2),
                    ))

        return findings

    def match_bank_statement(
        self,
        statement_data: Dict[str, Any],
        application_data: Dict[str, Any],
    ) -> List[ValidationFinding]:
        """Match bank statement data against application."""
        findings = []

        # Account holder name
        app_name = f"{application_data.get('borrower_first_name', '')} {application_data.get('borrower_last_name', '')}".lower()
        stmt_name = (statement_data.get("account_holder_name") or "").lower()

        if app_name.strip() and stmt_name:
            if not self._fuzzy_match(app_name, stmt_name, threshold=0.7):
                findings.append(ValidationFinding(
                    field="account_holder_name",
                    message="Bank statement name doesn't match borrower",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.CONSISTENCY,
                    expected_value=app_name,
                    actual_value=stmt_name,
                ))

        # Ending balance vs stated assets
        ending_balance = statement_data.get("ending_balance", 0)
        stated_balance = application_data.get("checking_balance", 0)

        if ending_balance and stated_balance:
            variance = abs(ending_balance - stated_balance) / max(stated_balance, 1) * 100
            if variance > 20:
                findings.append(ValidationFinding(
                    field="account_balance",
                    message=f"Bank balance differs from application by {variance:.0f}%",
                    severity=ValidationSeverity.WARNING,
                    category=ValidationCategory.CONSISTENCY,
                    expected_value=stated_balance,
                    actual_value=ending_balance,
                ))

        return findings

    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.8) -> bool:
        """Simple fuzzy string matching."""
        # Normalize strings
        s1 = set(str1.lower().split())
        s2 = set(str2.lower().split())

        if not s1 or not s2:
            return False

        # Jaccard similarity
        intersection = len(s1 & s2)
        union = len(s1 | s2)

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold


def validate_loan_file(
    loan_data: Dict[str, Any],
    loan_status: str = "application",
    include_fraud_check: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to validate a loan file.

    Args:
        loan_data: Dictionary of loan file data
        loan_status: Current loan status
        include_fraud_check: Whether to include fraud detection

    Returns:
        Dictionary with validation results
    """
    validator = LoanDataValidator()
    result = validator.validate(loan_data, loan_status, include_fraud_check)

    return {
        "is_valid": result.is_valid,
        "loan_id": result.loan_id,
        "validation_timestamp": result.validation_timestamp.isoformat(),
        "scores": {
            "completeness": round(result.completeness_score, 1),
            "data_quality": round(result.data_quality_score, 1),
            "overall": round(result.overall_score, 1),
        },
        "counts": {
            "errors": result.error_count,
            "warnings": result.warning_count,
            "fraud_alerts": result.fraud_alert_count,
        },
        "findings": [
            {
                "field": f.field,
                "message": f.message,
                "severity": f.severity.value,
                "category": f.category.value,
                "resolution_hint": f.resolution_hint,
            }
            for f in result.findings
        ],
        "errors": [
            {"field": f.field, "message": f.message}
            for f in result.get_findings_by_severity(ValidationSeverity.ERROR)
        ],
        "fraud_alerts": [
            {"field": f.field, "message": f.message, "confidence": f.confidence_score}
            for f in result.get_findings_by_severity(ValidationSeverity.FRAUD_ALERT)
        ],
    }
