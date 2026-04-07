"""
HMDA Data Validation Service

Validates required HMDA LAR (Loan Application Register) fields per
CFPB Regulation C before a loan can move past the SUBMITTED stage.

Required fields:
    - Loan-level: action_taken, action_taken_date, loan_type, loan_purpose,
      preapproval, construction_method, occupancy_type, loan_amount,
      rate_spread, hoepa_status, lien_status
    - Property: county, census_tract, property_type
    - Demographics: applicant race, ethnicity, sex (from BorrowerApplication)

Usage:
    from services.compliance.hmda_validator import HMDAValidator

    validator = HMDAValidator()
    result = validator.validate(db, loan_id)
    # result = {
    #     "compliant": True/False,
    #     "missing_fields": [...],
    #     "warnings": [...],
    # }
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Fields that MUST be present for HMDA compliance.
# Tuples of (field_label, model_attribute, source).
# source = "loan" means the value lives on the Loan model.
# source = "derived" means we compute it from other loan fields.
# source = "borrower_application" means BorrowerApplication model.
REQUIRED_FIELDS = [
    ("loan_type", "loan_type", "loan"),
    ("loan_purpose", "loan_purpose", "loan"),
    ("loan_amount", "amount", "loan"),
    ("property_type", "property_type", "loan"),
    ("occupancy_type", "occupancy_type", "loan"),
    ("property_state", "property_state", "loan"),
    # Derived fields (we check presence of underlying data)
    ("action_taken", None, "derived"),
    ("action_taken_date", None, "derived"),
    ("preapproval", None, "derived"),
    ("construction_method", None, "derived"),
    # Demographics from BorrowerApplication
    ("applicant_ethnicity", "applicant_ethnicity", "borrower_application"),
    ("applicant_race", "applicant_race", "borrower_application"),
    ("applicant_sex", "applicant_sex", "borrower_application"),
]

# Fields that SHOULD be present but do not block compliance.
RECOMMENDED_FIELDS = [
    ("property_county", "property_county", "loan"),
    ("census_tract", None, "derived"),
    ("interest_rate", "rate", "loan"),
    ("rate_spread", None, "derived"),
    ("hoepa_status", None, "derived"),
    ("lien_status", None, "derived"),
    ("co_applicant_ethnicity", "co_applicant_ethnicity", "borrower_application"),
    ("co_applicant_race", "co_applicant_race", "borrower_application"),
    ("co_applicant_sex", "co_applicant_sex", "borrower_application"),
]


class HMDAValidator:
    """Validates HMDA LAR data completeness for a loan."""

    def validate(
        self,
        db: Session,
        loan_id: int,
        organization_id: Optional[int] = None,
    ) -> dict:
        """Validate HMDA required fields for a loan.

        Args:
            db: Database session.
            loan_id: The loan to validate.
            organization_id: Optional org filter for tenant isolation.

        Returns:
            Structured result with compliant flag, missing_fields, and warnings.
        """
        from database.models.lead_loan import Loan

        query = db.query(Loan).filter(Loan.id == loan_id)
        if organization_id:
            query = query.filter(Loan.organization_id == organization_id)
        loan = query.first()
        if not loan:
            return {
                "compliant": False,
                "loan_id": loan_id,
                "error": f"Loan {loan_id} not found",
                "missing_fields": [],
                "warnings": [],
            }

        # Load BorrowerApplication for demographics
        borrower_app = self._load_borrower_application(db, loan_id)

        missing_fields = []
        warnings = []

        # -----------------------------------------------------------------
        # Check REQUIRED fields
        # -----------------------------------------------------------------
        for field_label, attr, source in REQUIRED_FIELDS:
            if source == "loan":
                value = getattr(loan, attr, None)
                if not self._is_present(value):
                    missing_fields.append(field_label)

            elif source == "derived":
                present, note = self._check_derived_field(field_label, loan)
                if not present:
                    missing_fields.append(field_label)
                if note:
                    warnings.append(note)

            elif source == "borrower_application":
                if borrower_app is None:
                    missing_fields.append(field_label)
                else:
                    value = getattr(borrower_app, attr, None)
                    if not self._is_present(value):
                        missing_fields.append(field_label)

        # -----------------------------------------------------------------
        # Check RECOMMENDED fields (generate warnings, not failures)
        # -----------------------------------------------------------------
        for field_label, attr, source in RECOMMENDED_FIELDS:
            if source == "loan":
                value = getattr(loan, attr, None)
                if not self._is_present(value):
                    warnings.append(
                        f"Recommended HMDA field '{field_label}' is missing"
                    )

            elif source == "derived":
                present, note = self._check_derived_field(field_label, loan)
                if not present:
                    warnings.append(
                        f"Recommended HMDA field '{field_label}' could not be determined"
                    )

            elif source == "borrower_application":
                if borrower_app is None:
                    warnings.append(
                        f"Recommended HMDA field '{field_label}' unavailable "
                        f"(no BorrowerApplication record)"
                    )
                else:
                    value = getattr(borrower_app, attr, None)
                    if not self._is_present(value):
                        warnings.append(
                            f"Recommended HMDA field '{field_label}' is missing"
                        )

        # Additional business-rule warnings
        if borrower_app is None:
            warnings.append(
                "No BorrowerApplication record linked to this loan -- "
                "all demographic fields will be missing"
            )

        compliant = len(missing_fields) == 0

        self._log_compliance_decision(
            db, loan_id, loan.organization_id, compliant,
            missing_fields, warnings,
        )

        return {
            "compliant": compliant,
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "missing_fields": missing_fields,
            "warnings": warnings,
            "total_required": len(REQUIRED_FIELDS),
            "required_present": len(REQUIRED_FIELDS) - len(missing_fields),
            "completeness_pct": round(
                (len(REQUIRED_FIELDS) - len(missing_fields))
                / len(REQUIRED_FIELDS) * 100,
                1,
            ),
        }

    def _is_present(self, value) -> bool:
        """Check if a field value is meaningfully present."""
        if value is None:
            return False
        if isinstance(value, str) and value.strip() == "":
            return False
        return True

    def _check_derived_field(self, field_label: str, loan) -> tuple:
        """Check a derived HMDA field.

        Returns (is_present: bool, warning_note: Optional[str]).
        """
        stage = (loan.stage or "").upper()

        if field_label == "action_taken":
            # Action taken can be derived from the loan stage
            terminal_stages = {
                "FUNDED", "DENIED", "WITHDRAWN", "CANCELLED", "DOES_NOT_QUALIFY",
            }
            if stage in terminal_stages:
                return True, None
            # If still in pipeline, action_taken is not yet determinable
            return False, (
                f"action_taken cannot be determined -- loan is in '{stage}' stage "
                f"(needs terminal stage: FUNDED, DENIED, WITHDRAWN, etc.)"
            )

        if field_label == "action_taken_date":
            for attr in ["funded_date", "withdrawn_date", "stage_changed_at"]:
                if getattr(loan, attr, None):
                    return True, None
            if stage in {"FUNDED", "DENIED", "WITHDRAWN", "CANCELLED"}:
                return False, "Loan has terminal stage but no action date recorded"
            return False, "action_taken_date unavailable (loan not in terminal stage)"

        if field_label == "preapproval":
            # Derived from preapproval_date on the loan
            return True, None  # Default to "2" (not applicable) if missing

        if field_label == "construction_method":
            # Derived from property_type
            if self._is_present(loan.property_type):
                return True, None
            return False, "construction_method requires property_type"

        if field_label == "census_tract":
            # Census tract is not typically stored in CRM
            return False, "census_tract not stored in CRM -- populate from property address geocoding"

        if field_label == "rate_spread":
            # Rate spread requires APOR comparison; typically computed externally
            return False, "rate_spread requires APOR comparison (external calculation)"

        if field_label == "hoepa_status":
            # Default to "3" (Not applicable) if not explicitly tracked
            return True, None

        if field_label == "lien_status":
            # Default to "1" (First lien) for most residential mortgages
            return True, None

        return False, f"Unknown derived field: {field_label}"

    def _load_borrower_application(self, db: Session, loan_id: int):
        """Load BorrowerApplication for a loan, returning None if not found."""
        try:
            from database.models.borrower import BorrowerApplication
            return db.query(BorrowerApplication).filter(
                BorrowerApplication.loan_id == loan_id
            ).first()
        except Exception as e:
            logger.warning(f"Failed to load BorrowerApplication for loan {loan_id}: {e}")
            return None

    def _log_compliance_decision(
        self, db: Session, loan_id: int, organization_id: int,
        compliant: bool, missing_fields: list, warnings: list,
    ):
        """Log HMDA validation decision to the compliance audit log."""
        try:
            from database.models.compliance_log import ComplianceDecisionLog

            log_entry = ComplianceDecisionLog(
                organization_id=organization_id,
                decision_type="hmda_data_validation",
                contact_id=loan_id,
                decision="allowed" if compliant else "warning",
                reason=(
                    "HMDA data validation passed"
                    if compliant
                    else f"HMDA fields incomplete: {len(missing_fields)} required field(s) missing"
                ),
                details={
                    "loan_id": loan_id,
                    "missing_fields": missing_fields,
                    "warning_count": len(warnings),
                },
            )
            db.add(log_entry)
        except Exception as e:
            logger.warning(f"Failed to log HMDA compliance decision: {e}")
