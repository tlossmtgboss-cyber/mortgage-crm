"""
Employment Audit Module

Handles borrower employment information including:
- Current employment
- Previous employment (2-year history)
- Self-employment details
- Employment verification requirements

URLA Section: 1c - Employment and Income
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from decimal import Decimal

from ..base import BaseAuditModule, FieldDefinition
from ..data_contracts import (
    AuditModuleType,
    FieldStatus,
    ExtractedField,
    EmploymentData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class EmploymentAuditModule(BaseAuditModule):
    """Audit module for borrower employment information."""

    MODULE_TYPE = AuditModuleType.EMPLOYMENT
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define employment fields for audit."""
        self._field_definitions = {
            "employer_name": FieldDefinition(
                name="employer_name",
                display_name="Employer Name",
                required=True,
                data_type="string",
                urla_section="1c",
                borrower_instructions="Please provide your current employer's name.",
            ),
            "employer_address": FieldDefinition(
                name="employer_address",
                display_name="Employer Address",
                required=True,
                data_type="string",
                urla_section="1c",
            ),
            "employer_phone": FieldDefinition(
                name="employer_phone",
                display_name="Employer Phone",
                required=True,
                data_type="string",
                urla_section="1c",
                borrower_instructions="Please provide your employer's HR or main phone number for verification.",
            ),
            "position_title": FieldDefinition(
                name="position_title",
                display_name="Job Title/Position",
                required=True,
                data_type="string",
                urla_section="1c",
            ),
            "employment_status": FieldDefinition(
                name="employment_status",
                display_name="Employment Status",
                required=True,
                data_type="enum",
                allowed_values=["EMPLOYED", "SELF_EMPLOYED", "RETIRED", "NOT_EMPLOYED", "OTHER"],
                urla_section="1c",
            ),
            "start_date": FieldDefinition(
                name="start_date",
                display_name="Start Date",
                required=True,
                data_type="date",
                urla_section="1c",
                borrower_instructions="When did you start working at your current employer?",
            ),
            "years_employed": FieldDefinition(
                name="years_employed",
                display_name="Years at Current Employer",
                required=False,
                data_type="integer",
            ),
            "months_employed": FieldDefinition(
                name="months_employed",
                display_name="Months at Current Employer",
                required=False,
                data_type="integer",
            ),
            "is_self_employed": FieldDefinition(
                name="is_self_employed",
                display_name="Self-Employed",
                required=False,
                data_type="boolean",
            ),
            "business_name": FieldDefinition(
                name="business_name",
                display_name="Business Name",
                required=False,  # Required if self-employed
                data_type="string",
            ),
            "ownership_percentage": FieldDefinition(
                name="ownership_percentage",
                display_name="Ownership Percentage",
                required=False,  # Required if self-employed
                data_type="decimal",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> EmploymentData:
        """Extract and merge employment data."""
        data = EmploymentData()

        # Handle current employment
        current_employment = call_extractions.get("current_employment", {})
        if not current_employment:
            current_employment = call_extractions

        existing_employment = existing_data.get("current_employment", {})
        if not existing_employment:
            existing_employment = existing_data

        data.employer_name = self.merge_field(
            current_employment.get("employer") or current_employment.get("employer_name") or current_employment.get("company"),
            existing_employment.get("employer") or existing_employment.get("current_employer"),
            "employer_name",
            current_employment.get("employer_confidence", 85.0),
        )

        data.employer_address = self.merge_field(
            current_employment.get("employer_address") or current_employment.get("work_address"),
            existing_employment.get("employer_address"),
            "employer_address",
        )

        data.employer_phone = self.merge_field(
            current_employment.get("employer_phone") or current_employment.get("work_phone") or current_employment.get("hr_phone"),
            existing_employment.get("employer_phone"),
            "employer_phone",
        )

        data.position_title = self.merge_field(
            current_employment.get("title") or current_employment.get("position") or current_employment.get("job_title"),
            existing_employment.get("position_title") or existing_employment.get("title"),
            "position_title",
            current_employment.get("title_confidence", 85.0),
        )

        # Determine employment status
        status = current_employment.get("employment_status") or current_employment.get("status")
        is_self = current_employment.get("is_self_employed") or current_employment.get("self_employed")

        if is_self:
            status = "SELF_EMPLOYED"
            data.is_self_employed = True

        data.employment_status = self.merge_field(
            status,
            existing_employment.get("employment_status"),
            "employment_status",
        )

        data.start_date = self.merge_field(
            current_employment.get("start_date") or current_employment.get("hire_date"),
            existing_employment.get("start_date"),
            "start_date",
        )

        # Duration parsing
        years = current_employment.get("years_employed") or current_employment.get("years")
        months = current_employment.get("months_employed") or current_employment.get("months")
        duration = current_employment.get("time_employed") or current_employment.get("duration")

        if duration and not years:
            years, months = self._parse_duration(duration)

        data.years_employed = self.merge_field(years, existing_employment.get("years_employed"), "years_employed")
        data.months_employed = self.merge_field(months, existing_employment.get("months_employed"), "months_employed")

        # Self-employment specific
        if data.is_self_employed:
            data.business_name = self.merge_field(
                current_employment.get("business_name"),
                existing_employment.get("business_name"),
                "business_name",
            )
            data.business_type = self.merge_field(
                current_employment.get("business_type") or current_employment.get("entity_type"),
                existing_employment.get("business_type"),
                "business_type",
            )
            data.ownership_percentage = self.merge_field(
                current_employment.get("ownership") or current_employment.get("ownership_percentage"),
                existing_employment.get("ownership_percentage"),
                "ownership_percentage",
            )
            data.business_phone = self.merge_field(
                current_employment.get("business_phone"),
                existing_employment.get("business_phone"),
                "business_phone",
            )

        return data

    def _parse_duration(self, duration_str: str) -> Tuple[Optional[int], Optional[int]]:
        """Parse duration string."""
        import re

        years = None
        months = None

        year_match = re.search(r'(\d+)\s*(?:year|yr)s?', str(duration_str), re.IGNORECASE)
        month_match = re.search(r'(\d+)\s*(?:month|mo)s?', str(duration_str), re.IGNORECASE)

        if year_match:
            years = int(year_match.group(1))
        if month_match:
            months = int(month_match.group(1))

        return years, months

    def _validate_data(self, data: EmploymentData) -> Tuple[List[str], List[str]]:
        """Validate employment data."""
        issues = []
        warnings = []

        # Validate phone
        if data.employer_phone and data.employer_phone.value:
            is_valid, error = self.validate_phone(data.employer_phone.value)
            if not is_valid:
                warnings.append(f"Employer phone: {error}")

        # Check for 2-year employment history
        total_months = 0
        if data.years_employed and data.years_employed.value:
            total_months += int(data.years_employed.value) * 12
        if data.months_employed and data.months_employed.value:
            total_months += int(data.months_employed.value)

        if total_months > 0 and total_months < 24:
            warnings.append("Less than 2 years at current employer - previous employment needed")

        # Self-employment validation
        if data.is_self_employed:
            if not data.business_name or not data.business_name.value:
                issues.append("Business name required for self-employment")

            if data.ownership_percentage and data.ownership_percentage.value:
                ownership = float(data.ownership_percentage.value)
                if ownership < 25:
                    warnings.append("Ownership under 25% may have different income calculation requirements")
                elif ownership == 100:
                    pass  # Standard self-employment
            else:
                warnings.append("Ownership percentage needed for self-employment income calculation")

        # Employment gap check
        if data.employment_status and data.employment_status.value == "NOT_EMPLOYED":
            warnings.append("Currently not employed - verify income source")

        return issues, warnings

    def _generate_tasks(
        self,
        data: EmploymentData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate employment-specific tasks."""
        tasks = super()._generate_tasks(data, field_stats, loan_id, borrower_type)

        # Self-employment document requirements
        if data.is_self_employed:
            tasks.append(GeneratedTask(
                title="Collect Business Tax Returns",
                description="Self-employed borrower requires 2 years of business tax returns.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="BUSINESS_TAX_RETURNS",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload your business tax returns for the past 2 years.",
            ))
            tasks.append(GeneratedTask(
                title="Collect YTD Profit & Loss",
                description="Year-to-date profit and loss statement needed for self-employment income.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="PROFIT_LOSS",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide a year-to-date profit and loss statement for your business.",
            ))

        # Check if previous employment needed
        total_months = 0
        if data.years_employed and data.years_employed.value:
            total_months += int(data.years_employed.value) * 12
        if data.months_employed and data.months_employed.value:
            total_months += int(data.months_employed.value)

        if 0 < total_months < 24:
            tasks.append(GeneratedTask(
                title="Collect Previous Employment",
                description=f"Current employment is {total_months} months. Need previous employment to complete 2-year history.",
                task_type="COLLECT_INFO",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                field_name="previous_employment",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide information about your previous employer to complete the 2-year employment history.",
            ))

        return tasks
