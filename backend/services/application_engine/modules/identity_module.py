"""
Identity Audit Module

Handles borrower identity verification including:
- Name, SSN, DOB
- Contact information
- Citizenship status
- Military status
- HMDA demographics

URLA Section: 1a - Personal Information
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from ..base import BaseAuditModule, FieldDefinition, ValidationRule
from ..data_contracts import (
    AuditModuleType,
    FieldStatus,
    ExtractedField,
    IdentityData,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class IdentityAuditModule(BaseAuditModule):
    """Audit module for borrower identity information."""

    MODULE_TYPE = AuditModuleType.IDENTITY
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define identity fields for audit."""
        self._field_definitions = {
            "first_name": FieldDefinition(
                name="first_name",
                display_name="First Name",
                required=True,
                data_type="string",
                urla_section="1a",
                urla_field_id="1a.1",
                borrower_instructions="Please provide your legal first name as it appears on your government ID.",
            ),
            "last_name": FieldDefinition(
                name="last_name",
                display_name="Last Name",
                required=True,
                data_type="string",
                urla_section="1a",
                urla_field_id="1a.3",
                borrower_instructions="Please provide your legal last name as it appears on your government ID.",
            ),
            "middle_name": FieldDefinition(
                name="middle_name",
                display_name="Middle Name",
                required=False,
                data_type="string",
                urla_section="1a",
                urla_field_id="1a.2",
            ),
            "suffix": FieldDefinition(
                name="suffix",
                display_name="Suffix",
                required=False,
                data_type="string",
                allowed_values=["Jr.", "Sr.", "II", "III", "IV"],
            ),
            "date_of_birth": FieldDefinition(
                name="date_of_birth",
                display_name="Date of Birth",
                required=True,
                data_type="date",
                urla_section="1a",
                urla_field_id="1a.5",
                requires_documentation=True,
                document_types=["DRIVERS_LICENSE", "PASSPORT", "BIRTH_CERTIFICATE"],
                borrower_instructions="Please provide your date of birth for identity verification.",
            ),
            "ssn": FieldDefinition(
                name="ssn",
                display_name="Social Security Number",
                required=True,
                data_type="string",
                urla_section="1a",
                urla_field_id="1a.6",
                requires_documentation=True,
                document_types=["SSN_CARD", "TAX_RETURN"],
                borrower_instructions="Your SSN is required for credit verification. Only the last 4 digits are stored.",
            ),
            "email": FieldDefinition(
                name="email",
                display_name="Email Address",
                required=True,
                data_type="string",
                urla_section="1a",
                borrower_instructions="Please provide a valid email address for loan communications.",
            ),
            "phone_primary": FieldDefinition(
                name="phone_primary",
                display_name="Primary Phone",
                required=True,
                data_type="string",
                urla_section="1a",
                borrower_instructions="Please provide your primary contact phone number.",
            ),
            "phone_secondary": FieldDefinition(
                name="phone_secondary",
                display_name="Secondary Phone",
                required=False,
                data_type="string",
            ),
            "citizenship_status": FieldDefinition(
                name="citizenship_status",
                display_name="Citizenship Status",
                required=True,
                data_type="enum",
                allowed_values=["US_CITIZEN", "PERMANENT_RESIDENT", "NON_PERMANENT_RESIDENT"],
                urla_section="1a",
                urla_field_id="1a.7",
                borrower_instructions="Please confirm your citizenship or residency status.",
            ),
            "marital_status": FieldDefinition(
                name="marital_status",
                display_name="Marital Status",
                required=True,
                data_type="enum",
                allowed_values=["SINGLE", "MARRIED", "SEPARATED", "DIVORCED", "WIDOWED"],
                urla_section="1a",
            ),
            "military_status": FieldDefinition(
                name="military_status",
                display_name="Military Service",
                required=False,
                data_type="enum",
                allowed_values=["NONE", "ACTIVE_DUTY", "VETERAN", "RESERVE_NATIONAL_GUARD", "SURVIVING_SPOUSE"],
                urla_section="1a",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> IdentityData:
        """Extract and merge identity data."""
        data = IdentityData()

        # Extract each field
        data.first_name = self.merge_field(
            call_extractions.get("first_name"),
            existing_data.get("first_name"),
            "first_name",
            call_extractions.get("first_name_confidence", 85.0),
        )

        data.last_name = self.merge_field(
            call_extractions.get("last_name"),
            existing_data.get("last_name"),
            "last_name",
            call_extractions.get("last_name_confidence", 85.0),
        )

        data.middle_name = self.merge_field(
            call_extractions.get("middle_name"),
            existing_data.get("middle_name"),
            "middle_name",
            call_extractions.get("middle_name_confidence", 80.0),
        )

        data.suffix = self.merge_field(
            call_extractions.get("suffix"),
            existing_data.get("suffix"),
            "suffix",
        )

        data.date_of_birth = self.merge_field(
            call_extractions.get("date_of_birth"),
            existing_data.get("date_of_birth"),
            "date_of_birth",
            call_extractions.get("dob_confidence", 80.0),
        )

        data.ssn = self.merge_field(
            call_extractions.get("ssn"),
            existing_data.get("ssn"),
            "ssn",
            call_extractions.get("ssn_confidence", 90.0),
        )

        data.email = self.merge_field(
            call_extractions.get("email"),
            existing_data.get("email"),
            "email",
            call_extractions.get("email_confidence", 85.0),
        )

        data.phone_primary = self.merge_field(
            call_extractions.get("phone") or call_extractions.get("phone_primary"),
            existing_data.get("phone") or existing_data.get("phone_primary"),
            "phone_primary",
            call_extractions.get("phone_confidence", 85.0),
        )

        data.phone_secondary = self.merge_field(
            call_extractions.get("phone_secondary"),
            existing_data.get("phone_secondary"),
            "phone_secondary",
        )

        data.citizenship_status = self.merge_field(
            call_extractions.get("citizenship_status") or call_extractions.get("citizenship"),
            existing_data.get("citizenship_status"),
            "citizenship_status",
            call_extractions.get("citizenship_confidence", 80.0),
        )

        data.marital_status = self.merge_field(
            call_extractions.get("marital_status"),
            existing_data.get("marital_status"),
            "marital_status",
            call_extractions.get("marital_confidence", 80.0),
        )

        data.military_status = self.merge_field(
            call_extractions.get("military_status") or call_extractions.get("military"),
            existing_data.get("military_status"),
            "military_status",
        )

        # HMDA demographics (optional)
        data.ethnicity = self.merge_field(
            call_extractions.get("ethnicity"),
            existing_data.get("ethnicity"),
            "ethnicity",
        )

        data.race = self.merge_field(
            call_extractions.get("race"),
            existing_data.get("race"),
            "race",
        )

        data.sex = self.merge_field(
            call_extractions.get("sex"),
            existing_data.get("sex"),
            "sex",
        )

        return data

    def _validate_data(self, data: IdentityData) -> Tuple[List[str], List[str]]:
        """Validate identity data."""
        issues = []
        warnings = []

        # Validate email
        if data.email and data.email.value:
            is_valid, error = self.validate_email(data.email.value)
            if not is_valid:
                issues.append(error)

        # Validate phone
        if data.phone_primary and data.phone_primary.value:
            is_valid, error = self.validate_phone(data.phone_primary.value)
            if not is_valid:
                warnings.append(error)

        # Validate SSN
        if data.ssn and data.ssn.value:
            is_valid, error = self.validate_ssn(data.ssn.value)
            if not is_valid:
                issues.append(error)

        # Validate DOB
        if data.date_of_birth and data.date_of_birth.value:
            is_valid, error = self.validate_date(data.date_of_birth.value)
            if not is_valid:
                issues.append(error)
            else:
                # Check age is reasonable (18-100)
                try:
                    from dateutil import parser
                    from datetime import date
                    dob = parser.parse(str(data.date_of_birth.value)).date()
                    age = (date.today() - dob).days // 365
                    if age < 18:
                        issues.append("Borrower appears to be under 18 years old")
                    elif age > 100:
                        warnings.append("Please verify date of birth - age appears over 100")
                except (ValueError, TypeError):
                    pass

        # Validate citizenship for non-permanent residents
        if (data.citizenship_status and
            data.citizenship_status.value == "NON_PERMANENT_RESIDENT"):
            if not data.visa_type or not data.visa_type.value:
                warnings.append("Visa type required for non-permanent residents")

        return issues, warnings
