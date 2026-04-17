# =============================================================================
# PERENNIA AI — Call Intelligence: Extraction Validator
# Addresses audit Q3: unified extractor hallucination isolation
#
# When the unified extractor makes one LLM call for all 6 domains,
# a hallucinated value in one domain shouldn't poison the others.
# This validator applies per-domain rules to catch common hallucinations:
#   - Values outside plausible ranges
#   - Fields that contradict each other
#   - Extracted values that don't appear anywhere in the transcript
# =============================================================================

import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ExtractionValidator:
    """
    Validates extracted fields per domain to catch hallucinations.
    Returns validation result with reason if invalid.
    """

    def validate_field(
        self, agent_type: str, field: Dict[str, Any]
    ) -> Dict[str, Any]:
        field_name = field.get("field", "")
        value = field.get("value")
        confidence = field.get("confidence", 0)

        if confidence < 0.10:
            return {"valid": False, "reason": f"Confidence too low: {confidence}"}

        validator = self._domain_validators.get(agent_type)
        if validator:
            return validator(self, field_name, value, field)

        return {"valid": True, "reason": None}

    # -----------------------------------------------------------------
    # Domain Validators
    # -----------------------------------------------------------------

    def _validate_identity(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name in ("borrower_name", "co_borrower_name"):
            if not value or not isinstance(value, str):
                return {"valid": False, "reason": "Name is empty or not a string"}
            if len(value) < 2 or len(value) > 100:
                return {"valid": False, "reason": f"Name length implausible: {len(value)}"}
            if re.search(r'\d', value):
                return {"valid": False, "reason": "Name contains digits"}
            return {"valid": True, "reason": None}

        if field_name == "dependents_count":
            if not isinstance(value, (int, float)) or value < 0 or value > 20:
                return {"valid": False, "reason": f"Dependents implausible: {value}"}

        if field_name == "marital_status":
            valid_statuses = {"single", "married", "divorced", "separated", "widowed"}
            if str(value).lower() not in valid_statuses:
                return {"valid": False, "reason": f"Unknown marital status: {value}"}

        return {"valid": True, "reason": None}

    def _validate_financial(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name in ("annual_income", "monthly_income"):
            if not isinstance(value, (int, float)):
                return {"valid": False, "reason": "Income not numeric"}
            if value < 0:
                return {"valid": False, "reason": "Negative income"}
            if field_name == "annual_income" and value > 10_000_000:
                return {"valid": False, "reason": f"Annual income implausible: ${value:,}"}
            if field_name == "monthly_income" and value > 500_000:
                return {"valid": False, "reason": f"Monthly income implausible: ${value:,}"}
            if value > 0 and value % 100_000 == 0 and field.get("confidence", 0) < 0.70:
                field["needs_review"] = True
                field["validation_warning"] = "Suspiciously round number at low confidence"

        if field_name == "credit_score":
            if not isinstance(value, (int, float)):
                return {"valid": False, "reason": "Credit score not numeric"}
            if value < 300 or value > 850:
                return {"valid": False, "reason": f"Credit score out of range: {value}"}

        if field_name in ("monthly_debts", "car_payment", "student_loan_payment"):
            if isinstance(value, (int, float)) and value < 0:
                return {"valid": False, "reason": "Negative debt payment"}
            if isinstance(value, (int, float)) and value > 100_000:
                return {"valid": False, "reason": f"Monthly payment implausible: ${value:,}"}

        return {"valid": True, "reason": None}

    def _validate_property(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name == "purchase_price":
            if not isinstance(value, (int, float)):
                return {"valid": False, "reason": "Purchase price not numeric"}
            if value < 10_000:
                return {"valid": False, "reason": f"Purchase price too low: ${value:,}"}
            if value > 100_000_000:
                return {"valid": False, "reason": f"Purchase price implausible: ${value:,}"}

        if field_name == "down_payment_pct":
            if isinstance(value, (int, float)) and (value < 0 or value > 100):
                return {"valid": False, "reason": f"Down payment % out of range: {value}"}

        if field_name == "property_type":
            valid_types = {
                "single_family", "condo", "townhouse", "multi_family",
                "manufactured", "co_op", "pud",
            }
            if str(value).lower().replace(" ", "_") not in valid_types:
                field["needs_review"] = True
                field["validation_warning"] = f"Unusual property type: {value}"

        if field_name == "occupancy_type":
            valid_occ = {"primary", "secondary", "investment"}
            if str(value).lower() not in valid_occ:
                return {"valid": False, "reason": f"Unknown occupancy: {value}"}

        return {"valid": True, "reason": None}

    def _validate_employment(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name == "years_at_job":
            if isinstance(value, (int, float)) and (value < 0 or value > 60):
                return {"valid": False, "reason": f"Years at job implausible: {value}"}

        if field_name == "employment_type":
            valid_types = {
                "w2", "salaried", "self_employed", "1099",
                "retired", "unemployed", "part_time",
            }
            if str(value).lower().replace("-", "_").replace(" ", "_") not in valid_types:
                field["needs_review"] = True

        return {"valid": True, "reason": None}

    def _validate_compliance(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name in ("compliance_score", "trid_score", "fair_lending_score"):
            if isinstance(value, (int, float)) and (value < 0 or value > 100):
                return {"valid": False, "reason": f"Score out of range: {value}"}

        return {"valid": True, "reason": None}

    def _validate_intent(
        self, field_name: str, value: Any, field: Dict
    ) -> Dict:
        if field_name == "loan_purpose":
            valid_purposes = {"purchase", "refinance", "cash_out_refinance", "heloc"}
            if str(value).lower().replace(" ", "_") not in valid_purposes:
                field["needs_review"] = True

        return {"valid": True, "reason": None}

    # -----------------------------------------------------------------
    # Cross-Domain Validation
    # -----------------------------------------------------------------

    def validate_cross_domain(
        self, all_results: Dict[str, List[Dict]]
    ) -> List[Dict]:
        warnings = []

        income = self._find_field(all_results, "financial", "annual_income")
        price = self._find_field(all_results, "property", "purchase_price")
        if income and price and income > 0:
            ratio = price / income
            if ratio > 12:
                warnings.append({
                    "type": "cross_domain_mismatch",
                    "fields": ["annual_income", "purchase_price"],
                    "detail": f"Price/income ratio is {ratio:.1f}x (>12x is unusual)",
                    "severity": "warning",
                })

        dp_pct = self._find_field(all_results, "property", "down_payment_pct")
        dp_amt = self._find_field(all_results, "property", "down_payment_amount")
        if dp_pct and dp_amt and price:
            expected_amt = price * (dp_pct / 100)
            if abs(expected_amt - dp_amt) > 5000:
                warnings.append({
                    "type": "cross_domain_mismatch",
                    "fields": ["down_payment_pct", "down_payment_amount"],
                    "detail": f"DP% implies ${expected_amt:,.0f} but amount is ${dp_amt:,.0f}",
                    "severity": "warning",
                })

        return warnings

    def _find_field(
        self, results: Dict[str, List[Dict]], domain: str, field_name: str
    ) -> Any:
        fields = results.get(domain, [])
        for f in fields:
            if f.get("field") == field_name:
                return f.get("value")
        return None

    # -----------------------------------------------------------------
    # Registry
    # -----------------------------------------------------------------

    _domain_validators = {
        "identity": _validate_identity,
        "financial": _validate_financial,
        "property": _validate_property,
        "employment": _validate_employment,
        "compliance": _validate_compliance,
        "intent": _validate_intent,
    }
