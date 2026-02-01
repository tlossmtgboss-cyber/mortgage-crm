"""
Address Audit Module

Handles borrower address information including:
- Current address
- Previous addresses (2-year history)
- Mailing address
- Ownership/rental status

URLA Section: 1b - Current and Previous Addresses
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

from ..base import BaseAuditModule, FieldDefinition
from ..data_contracts import (
    AuditModuleType,
    FieldStatus,
    ExtractedField,
    AddressData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class AddressAuditModule(BaseAuditModule):
    """Audit module for borrower address information."""

    MODULE_TYPE = AuditModuleType.ADDRESS
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define address fields for audit."""
        self._field_definitions = {
            "street_line_1": FieldDefinition(
                name="street_line_1",
                display_name="Street Address",
                required=True,
                data_type="string",
                urla_section="1b",
                borrower_instructions="Please provide your current street address.",
            ),
            "street_line_2": FieldDefinition(
                name="street_line_2",
                display_name="Unit/Apt",
                required=False,
                data_type="string",
            ),
            "city": FieldDefinition(
                name="city",
                display_name="City",
                required=True,
                data_type="string",
                urla_section="1b",
            ),
            "state": FieldDefinition(
                name="state",
                display_name="State",
                required=True,
                data_type="string",
                urla_section="1b",
            ),
            "zip_code": FieldDefinition(
                name="zip_code",
                display_name="ZIP Code",
                required=True,
                data_type="string",
                urla_section="1b",
            ),
            "county": FieldDefinition(
                name="county",
                display_name="County",
                required=False,
                data_type="string",
            ),
            "ownership_status": FieldDefinition(
                name="ownership_status",
                display_name="Housing Status",
                required=True,
                data_type="enum",
                allowed_values=["OWN", "RENT", "LIVING_RENT_FREE"],
                urla_section="1b",
                borrower_instructions="Do you own, rent, or live rent-free at your current address?",
            ),
            "monthly_payment": FieldDefinition(
                name="monthly_payment",
                display_name="Monthly Housing Payment",
                required=True,
                data_type="decimal",
                urla_section="1b",
                borrower_instructions="What is your current monthly rent or mortgage payment?",
            ),
            "years_at_address": FieldDefinition(
                name="years_at_address",
                display_name="Years at Address",
                required=True,
                data_type="integer",
                urla_section="1b",
            ),
            "months_at_address": FieldDefinition(
                name="months_at_address",
                display_name="Months at Address",
                required=False,
                data_type="integer",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> AddressData:
        """Extract and merge address data."""
        data = AddressData()

        # Handle nested address structure from call
        current_address = call_extractions.get("current_address", {})
        if not current_address:
            current_address = call_extractions

        existing_address = existing_data.get("current_address", {})
        if not existing_address:
            existing_address = existing_data

        # Extract street address
        data.street_line_1 = self.merge_field(
            current_address.get("street") or current_address.get("street_line_1") or current_address.get("address"),
            existing_address.get("street") or existing_address.get("street_line_1"),
            "street_line_1",
            current_address.get("address_confidence", 85.0),
        )

        data.street_line_2 = self.merge_field(
            current_address.get("unit") or current_address.get("street_line_2") or current_address.get("apt"),
            existing_address.get("street_line_2") or existing_address.get("unit"),
            "street_line_2",
        )

        data.city = self.merge_field(
            current_address.get("city"),
            existing_address.get("city"),
            "city",
            current_address.get("city_confidence", 85.0),
        )

        data.state = self.merge_field(
            current_address.get("state"),
            existing_address.get("state"),
            "state",
            current_address.get("state_confidence", 90.0),
        )

        data.zip_code = self.merge_field(
            current_address.get("zip") or current_address.get("zip_code") or current_address.get("postal_code"),
            existing_address.get("zip") or existing_address.get("zip_code"),
            "zip_code",
            current_address.get("zip_confidence", 85.0),
        )

        data.county = self.merge_field(
            current_address.get("county"),
            existing_address.get("county"),
            "county",
        )

        # Residency details
        data.ownership_status = self.merge_field(
            call_extractions.get("ownership_status") or call_extractions.get("housing_status"),
            existing_data.get("ownership_status"),
            "ownership_status",
            call_extractions.get("ownership_confidence", 80.0),
        )

        data.monthly_payment = self.merge_field(
            call_extractions.get("monthly_payment") or call_extractions.get("rent") or call_extractions.get("mortgage_payment"),
            existing_data.get("monthly_payment"),
            "monthly_payment",
            call_extractions.get("payment_confidence", 80.0),
        )

        # Duration at address
        years = call_extractions.get("years_at_address") or call_extractions.get("years_living")
        months = call_extractions.get("months_at_address") or call_extractions.get("months_living")

        # Try to parse duration like "2 years 3 months"
        duration = call_extractions.get("time_at_address") or call_extractions.get("duration")
        if duration and not years:
            years, months = self._parse_duration(duration)

        data.years_at_address = self.merge_field(
            years,
            existing_data.get("years_at_address"),
            "years_at_address",
        )

        data.months_at_address = self.merge_field(
            months,
            existing_data.get("months_at_address"),
            "months_at_address",
        )

        data.move_in_date = self.merge_field(
            call_extractions.get("move_in_date"),
            existing_data.get("move_in_date"),
            "move_in_date",
        )

        return data

    def _parse_duration(self, duration_str: str) -> Tuple[Optional[int], Optional[int]]:
        """Parse duration string like '2 years 3 months' into years and months."""
        import re

        years = None
        months = None

        # Match patterns like "2 years", "3 months", "2 years 3 months"
        year_match = re.search(r'(\d+)\s*(?:year|yr)s?', str(duration_str), re.IGNORECASE)
        month_match = re.search(r'(\d+)\s*(?:month|mo)s?', str(duration_str), re.IGNORECASE)

        if year_match:
            years = int(year_match.group(1))
        if month_match:
            months = int(month_match.group(1))

        return years, months

    def _validate_data(self, data: AddressData) -> Tuple[List[str], List[str]]:
        """Validate address data."""
        issues = []
        warnings = []

        # Validate ZIP code
        if data.zip_code and data.zip_code.value:
            is_valid, error = self.validate_zip(data.zip_code.value)
            if not is_valid:
                issues.append(error)

        # Validate state
        valid_states = [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC", "PR", "VI", "GU", "AS", "MP"
        ]
        if data.state and data.state.value:
            state_val = str(data.state.value).upper().strip()
            if len(state_val) > 2:
                # Try to match state name to abbreviation
                state_names = {
                    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
                    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
                    "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
                    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
                    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME",
                    "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
                    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO",
                    "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
                    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
                    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
                    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
                    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
                    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
                    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
                    "WISCONSIN": "WI", "WYOMING": "WY"
                }
                if state_val not in state_names:
                    warnings.append(f"State '{data.state.value}' may need verification")
            elif state_val not in valid_states:
                issues.append(f"Invalid state code: {data.state.value}")

        # Check for 2-year address history
        if data.years_at_address and data.years_at_address.value:
            years = int(data.years_at_address.value)
            if years < 2:
                warnings.append("Less than 2 years at current address - previous address needed")

        # Validate monthly payment for renters
        if (data.ownership_status and data.ownership_status.value == "RENT"):
            if not data.monthly_payment or not data.monthly_payment.value:
                issues.append("Monthly rent payment required")
            elif float(data.monthly_payment.value) <= 0:
                issues.append("Monthly rent must be greater than $0")

        return issues, warnings

    def _generate_tasks(
        self,
        data: AddressData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate tasks including previous address check."""
        tasks = super()._generate_tasks(data, field_stats, loan_id, borrower_type)

        # Check if previous address is needed
        if data.years_at_address and data.years_at_address.value:
            years = int(data.years_at_address.value)
            if years < 2:
                tasks.append(GeneratedTask(
                    title="Collect Previous Address",
                    description="Borrower has been at current address less than 2 years. Need to collect previous address for complete 2-year history.",
                    task_type="COLLECT_INFO",
                    assignee=TaskAssignee.BORROWER,
                    priority=TaskPriority.MEDIUM,
                    module=self.MODULE_TYPE,
                    field_name="previous_address",
                    borrower_type=borrower_type,
                    borrower_portal_visible=True,
                    borrower_instructions="Please provide your previous address where you lived before your current residence.",
                ))

        return tasks
