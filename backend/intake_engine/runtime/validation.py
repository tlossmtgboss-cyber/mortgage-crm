"""
Validation Engine for Intake
Applies field-level and cross-field validation rules
"""

import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from .models import Session, Flag, FlagCategory, FlagSeverity


class ValidationResult:
    """Result of a validation check"""
    def __init__(self, valid: bool, errors: List[Dict] = None, warnings: List[Dict] = None):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []


class ValidationEngine:
    """Applies validation rules to answers"""

    # Common regex patterns
    PATTERNS = {
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "phone": r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$",
        "ssn": r"^\d{3}-?\d{2}-?\d{4}$",
        "ssn_last4": r"^\d{4}$",
        "zip": r"^\d{5}(-\d{4})?$",
        "currency": r"^\$?[\d,]+(\.\d{2})?$",
    }

    def __init__(self, validation_rules: Dict[str, Any]):
        self.rules = validation_rules
        self.field_rules = validation_rules.get("field_validations", {})
        self.cross_field_rules = validation_rules.get("cross_field_rules", [])

    def validate_answer(
        self,
        question_id: str,
        value: Any,
        session: Session,
        question_def: Dict[str, Any],
    ) -> ValidationResult:
        """Validate a single answer"""
        errors = []
        warnings = []

        # Skip validation for null/empty if not required
        if value is None or value == "":
            if question_def.get("required", False):
                errors.append({
                    "code": "REQUIRED",
                    "message": "This field is required",
                    "field": question_id,
                })
            return ValidationResult(len(errors) == 0, errors, warnings)

        # Get question validations
        validations = question_def.get("validations", [])

        for validation in validations:
            result = self._apply_validation(question_id, value, validation, session)
            if result:
                if result.get("severity") == "error":
                    errors.append(result)
                else:
                    warnings.append(result)

        # Apply field-specific rules from config
        if question_id in self.field_rules:
            field_rules = self.field_rules[question_id]
            for rule in field_rules.get("rules", []):
                result = self._apply_validation(question_id, value, rule, session)
                if result:
                    if result.get("severity") == "error":
                        errors.append(result)
                    else:
                        warnings.append(result)

        return ValidationResult(len(errors) == 0, errors, warnings)

    def _apply_validation(
        self,
        question_id: str,
        value: Any,
        validation: Dict[str, Any],
        session: Session,
    ) -> Optional[Dict]:
        """Apply a single validation rule"""
        rule_type = validation.get("type")

        if rule_type == "regex":
            pattern = validation.get("pattern")
            if pattern in self.PATTERNS:
                pattern = self.PATTERNS[pattern]
            if not re.match(pattern, str(value)):
                return {
                    "code": validation.get("error_code", "INVALID_FORMAT"),
                    "message": validation.get("message", "Invalid format"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "min":
            min_val = validation.get("value")
            if isinstance(value, (int, float)) and value < min_val:
                return {
                    "code": validation.get("error_code", "BELOW_MINIMUM"),
                    "message": validation.get("message", f"Value must be at least {min_val}"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "max":
            max_val = validation.get("value")
            if isinstance(value, (int, float)) and value > max_val:
                return {
                    "code": validation.get("error_code", "ABOVE_MAXIMUM"),
                    "message": validation.get("message", f"Value must be at most {max_val}"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "min_length":
            min_len = validation.get("value")
            if len(str(value)) < min_len:
                return {
                    "code": validation.get("error_code", "TOO_SHORT"),
                    "message": validation.get("message", f"Must be at least {min_len} characters"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "max_length":
            max_len = validation.get("value")
            if len(str(value)) > max_len:
                return {
                    "code": validation.get("error_code", "TOO_LONG"),
                    "message": validation.get("message", f"Must be at most {max_len} characters"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "enum":
            allowed = validation.get("values", [])
            if value not in allowed:
                return {
                    "code": validation.get("error_code", "INVALID_VALUE"),
                    "message": validation.get("message", "Invalid selection"),
                    "field": question_id,
                    "severity": validation.get("severity", "error"),
                }

        elif rule_type == "date_past":
            try:
                if isinstance(value, str):
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                elif isinstance(value, (datetime, date)):
                    dt = value
                else:
                    dt = None
                if dt and dt > datetime.now():
                    return {
                        "code": validation.get("error_code", "FUTURE_DATE"),
                        "message": validation.get("message", "Date must be in the past"),
                        "field": question_id,
                        "severity": validation.get("severity", "error"),
                    }
            except ValueError:
                return {
                    "code": "INVALID_DATE",
                    "message": "Invalid date format",
                    "field": question_id,
                    "severity": "error",
                }

        elif rule_type == "date_future":
            try:
                if isinstance(value, str):
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                elif isinstance(value, (datetime, date)):
                    dt = value
                else:
                    dt = None
                if dt and dt < datetime.now():
                    return {
                        "code": validation.get("error_code", "PAST_DATE"),
                        "message": validation.get("message", "Date must be in the future"),
                        "field": question_id,
                        "severity": validation.get("severity", "error"),
                    }
            except ValueError:
                return {
                    "code": "INVALID_DATE",
                    "message": "Invalid date format",
                    "field": question_id,
                    "severity": "error",
                }

        elif rule_type == "age_min":
            min_age = validation.get("value")
            try:
                if isinstance(value, str):
                    dob = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
                elif isinstance(value, datetime):
                    dob = value.date()
                elif isinstance(value, date):
                    dob = value
                else:
                    dob = None
                if dob:
                    today = date.today()
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    if age < min_age:
                        return {
                            "code": validation.get("error_code", "AGE_BELOW_MINIMUM"),
                            "message": validation.get("message", f"Must be at least {min_age} years old"),
                            "field": question_id,
                            "severity": validation.get("severity", "error"),
                        }
            except ValueError:
                pass

        return None

    def validate_cross_field(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> Tuple[List[Dict], List[Flag]]:
        """Run cross-field consistency validations"""
        inconsistencies = []
        flags = []

        for rule in self.cross_field_rules:
            result = self._check_cross_field_rule(rule, session, party_id)
            if result:
                inconsistencies.append(result)
                # Create flag if specified
                if rule.get("add_flag"):
                    flags.append(Flag(
                        code=rule["add_flag"],
                        category=FlagCategory.TRUTH,
                        severity=FlagSeverity(rule.get("severity", "warn")),
                        message=result.get("message"),
                        triggered_by=rule.get("id"),
                    ))

        return inconsistencies, flags

    def _check_cross_field_rule(
        self,
        rule: Dict[str, Any],
        session: Session,
        party_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """Check a single cross-field rule"""
        rule_id = rule.get("id")
        rule_type = rule.get("type")
        fields = rule.get("fields", [])

        # Get field values
        values = {}
        for field in fields:
            val = session.get_answer(field, party_id)
            values[field] = val

        # Skip if any required field is missing
        if any(v is None for v in values.values()):
            return None

        if rule_type == "dti_consistency":
            # Check income vs expenses ratio
            income = values.get(fields[0], 0) or 0
            housing = values.get(fields[1], 0) or 0
            debts = values.get(fields[2], 0) or 0

            if income > 0:
                dti = ((housing + debts) / income) * 100
                max_dti = rule.get("max_dti", 50)
                if dti > max_dti:
                    return {
                        "rule_id": rule_id,
                        "message": f"DTI of {dti:.1f}% exceeds typical limits",
                        "severity": rule.get("severity", "warn"),
                        "values": {"dti": dti, "income": income, "housing": housing, "debts": debts},
                    }

        elif rule_type == "address_occupancy_match":
            # Check if current address matches subject property for primary residence
            occupancy = values.get(fields[0])
            current_addr = values.get(fields[1])
            subject_addr = values.get(fields[2])

            if occupancy == "PrimaryResidence" and current_addr and subject_addr:
                # Simple check - in production would use address normalization
                if current_addr.lower() == subject_addr.lower():
                    return {
                        "rule_id": rule_id,
                        "message": "Current address matches subject property for purchase",
                        "severity": rule.get("severity", "info"),
                        "values": values,
                    }

        elif rule_type == "assets_vs_purchase":
            # Check if stated assets are sufficient for purchase
            purchase_price = values.get(fields[0], 0) or 0
            down_payment = values.get(fields[1], 0) or 0
            total_assets = sum(values.get(f, 0) or 0 for f in fields[2:])

            # Assets should cover at least down payment + reserves
            min_required = down_payment * 1.5  # Rough estimate
            if total_assets < min_required and purchase_price > 0:
                return {
                    "rule_id": rule_id,
                    "message": "Stated assets may be insufficient for transaction",
                    "severity": rule.get("severity", "warn"),
                    "values": {"assets": total_assets, "required": min_required},
                }

        elif rule_type == "employment_income_match":
            # Check if income aligns with employment type
            emp_type = values.get(fields[0])
            income = values.get(fields[1], 0) or 0
            years = values.get(fields[2], 0) or 0

            # Self-employed with high income but short history is a flag
            if emp_type == "SelfEmployed" and income > 150000 and years < 2:
                return {
                    "rule_id": rule_id,
                    "message": "High self-employment income with limited history",
                    "severity": rule.get("severity", "warn"),
                    "values": values,
                }

        elif rule_type == "investment_rent_required":
            # Investment property must have expected rent
            occupancy = values.get(fields[0])
            rent = values.get(fields[1], 0) or 0

            if occupancy == "Investment" and rent <= 0:
                return {
                    "rule_id": rule_id,
                    "message": "Investment property requires expected rental income",
                    "severity": rule.get("severity", "warn"),
                    "values": values,
                }

        elif rule_type == "compare":
            # Generic comparison rule
            op = rule.get("operator")
            field_a = values.get(fields[0])
            field_b = values.get(fields[1])

            if field_a is not None and field_b is not None:
                comparison_failed = False
                if op == "lte" and field_a > field_b:
                    comparison_failed = True
                elif op == "gte" and field_a < field_b:
                    comparison_failed = True
                elif op == "eq" and field_a != field_b:
                    comparison_failed = True
                elif op == "neq" and field_a == field_b:
                    comparison_failed = True

                if comparison_failed:
                    return {
                        "rule_id": rule_id,
                        "message": rule.get("message", "Fields do not satisfy constraint"),
                        "severity": rule.get("severity", "warn"),
                        "values": values,
                    }

        return None


def create_validation_engine(validation_rules: Dict[str, Any]) -> ValidationEngine:
    """Factory function to create validation engine"""
    return ValidationEngine(validation_rules)
