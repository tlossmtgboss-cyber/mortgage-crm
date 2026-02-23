"""
Income Audit Module

Handles borrower income information including:
- Base salary/wages
- Variable income (overtime, bonus, commission)
- Self-employment income
- Other income sources

URLA Section: 1d - Monthly Income
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
    IncomeData,
    IncomeSourceData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class IncomeAuditModule(BaseAuditModule):
    """Audit module for borrower income information."""

    MODULE_TYPE = AuditModuleType.INCOME
    MODULE_VERSION = "1.0"

    # Income types that require additional documentation
    VARIABLE_INCOME_TYPES = ["OVERTIME", "BONUS", "COMMISSION", "TIPS"]
    SELF_EMPLOYMENT_TYPES = ["SELF_EMPLOYMENT", "BUSINESS_INCOME", "SCHEDULE_C"]
    OTHER_INCOME_TYPES = ["RENTAL", "ALIMONY", "CHILD_SUPPORT", "PENSION", "SOCIAL_SECURITY", "DISABILITY"]

    def _setup_field_definitions(self) -> None:
        """Define income fields for audit."""
        self._field_definitions = {
            "base_monthly_income": FieldDefinition(
                name="base_monthly_income",
                display_name="Base Monthly Income",
                required=True,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["PAYSTUB", "W2"],
                borrower_instructions="Please provide your base monthly salary or hourly wage income.",
            ),
            "overtime_monthly": FieldDefinition(
                name="overtime_monthly",
                display_name="Overtime Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["PAYSTUB", "W2"],
            ),
            "bonus_monthly": FieldDefinition(
                name="bonus_monthly",
                display_name="Bonus Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["W2", "PAYSTUB"],
            ),
            "commission_monthly": FieldDefinition(
                name="commission_monthly",
                display_name="Commission Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["W2", "PAYSTUB", "TAX_RETURNS"],
            ),
            "self_employment_monthly": FieldDefinition(
                name="self_employment_monthly",
                display_name="Self-Employment Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["TAX_RETURNS", "PROFIT_LOSS"],
            ),
            "rental_monthly": FieldDefinition(
                name="rental_monthly",
                display_name="Rental Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
                requires_documentation=True,
                document_types=["TAX_RETURNS", "LEASE_AGREEMENT"],
            ),
            "other_monthly": FieldDefinition(
                name="other_monthly",
                display_name="Other Income",
                required=False,
                data_type="decimal",
                urla_section="1d",
            ),
            "total_monthly_income": FieldDefinition(
                name="total_monthly_income",
                display_name="Total Monthly Income",
                required=True,
                data_type="decimal",
                urla_section="1d",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> IncomeData:
        """Extract and merge income data."""
        data = IncomeData()
        data.income_sources = []

        # Extract base/salary income
        base_income = call_extractions.get("base_income") or call_extractions.get("salary") or call_extractions.get("monthly_salary")
        if base_income:
            source = IncomeSourceData(
                income_type="BASE",
                monthly_amount=self.create_extracted_field(
                    "base_monthly",
                    self._parse_currency(base_income),
                    call_extractions.get("base_confidence", 85.0),
                    "call_transcript"
                ),
                frequency="MONTHLY",
            )
            source.employer_or_source = self.create_extracted_field(
                "employer",
                call_extractions.get("employer"),
                80.0,
                "call_transcript"
            )
            data.income_sources.append(source)

        # Extract hourly wage if provided
        hourly_rate = call_extractions.get("hourly_rate") or call_extractions.get("hourly_wage")
        hours_per_week = call_extractions.get("hours_per_week") or 40
        if hourly_rate:
            monthly = float(hourly_rate) * float(hours_per_week) * 4.33  # Average weeks per month
            source = IncomeSourceData(
                income_type="BASE",
                monthly_amount=self.create_extracted_field(
                    "base_monthly",
                    Decimal(str(round(monthly, 2))),
                    call_extractions.get("hourly_confidence", 80.0),
                    "call_transcript"
                ),
                frequency="HOURLY",
            )
            data.income_sources.append(source)

        # Extract annual salary and convert to monthly
        annual_salary = call_extractions.get("annual_salary") or call_extractions.get("yearly_salary")
        if annual_salary and not base_income:
            monthly = float(self._parse_currency(annual_salary)) / 12
            source = IncomeSourceData(
                income_type="BASE",
                monthly_amount=self.create_extracted_field(
                    "base_monthly",
                    Decimal(str(round(monthly, 2))),
                    call_extractions.get("salary_confidence", 85.0),
                    "call_transcript"
                ),
                annual_amount=self.create_extracted_field(
                    "base_annual",
                    self._parse_currency(annual_salary),
                    call_extractions.get("salary_confidence", 85.0),
                    "call_transcript"
                ),
                frequency="ANNUAL",
            )
            data.income_sources.append(source)

        # Extract variable income types
        for income_type in ["overtime", "bonus", "commission"]:
            value = call_extractions.get(income_type) or call_extractions.get(f"{income_type}_income")
            if value:
                source = IncomeSourceData(
                    income_type=income_type.upper(),
                    monthly_amount=self.create_extracted_field(
                        f"{income_type}_monthly",
                        self._parse_currency(value),
                        call_extractions.get(f"{income_type}_confidence", 75.0),
                        "call_transcript"
                    ),
                    is_variable=True,
                )
                data.income_sources.append(source)

        # Extract self-employment income
        self_emp = call_extractions.get("self_employment_income") or call_extractions.get("business_income")
        if self_emp:
            source = IncomeSourceData(
                income_type="SELF_EMPLOYMENT",
                monthly_amount=self.create_extracted_field(
                    "self_emp_monthly",
                    self._parse_currency(self_emp),
                    call_extractions.get("self_emp_confidence", 70.0),
                    "call_transcript"
                ),
                documentation_type="TAX_RETURN",
            )
            data.income_sources.append(source)

        # Extract rental income
        rental = call_extractions.get("rental_income") or call_extractions.get("rent_income")
        if rental:
            source = IncomeSourceData(
                income_type="RENTAL",
                monthly_amount=self.create_extracted_field(
                    "rental_monthly",
                    self._parse_currency(rental),
                    call_extractions.get("rental_confidence", 75.0),
                    "call_transcript"
                ),
                documentation_type="TAX_RETURN",
            )
            data.income_sources.append(source)

        # Extract other income types
        for income_type in ["alimony", "child_support", "pension", "social_security", "disability"]:
            value = call_extractions.get(income_type) or call_extractions.get(f"{income_type}_income")
            if value:
                source = IncomeSourceData(
                    income_type=income_type.upper(),
                    monthly_amount=self.create_extracted_field(
                        f"{income_type}_monthly",
                        self._parse_currency(value),
                        75.0,
                        "call_transcript"
                    ),
                )
                data.income_sources.append(source)

        # Calculate total
        total_monthly = Decimal("0")
        for source in data.income_sources:
            if source.monthly_amount and source.monthly_amount.value:
                total_monthly += Decimal(str(source.monthly_amount.value))

        data.total_monthly_income = total_monthly
        data.total_annual_income = total_monthly * 12

        # Merge with existing data
        if existing_data.get("monthly_income"):
            existing_total = Decimal(str(existing_data["monthly_income"]))
            if total_monthly == 0:
                data.total_monthly_income = existing_total
                data.total_annual_income = existing_total * 12

        # Identify required documents
        data.required_documents = self._identify_required_documents(data.income_sources)

        return data

    def _parse_currency(self, value: Any) -> Decimal:
        """Parse currency value from various formats."""
        if value is None:
            return Decimal("0")

        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))

        # Remove currency symbols and commas
        import re
        cleaned = re.sub(r'[$,\s]', '', str(value))

        # Handle "k" suffix (e.g., "100k")
        if cleaned.lower().endswith('k'):
            return Decimal(cleaned[:-1]) * 1000

        try:
            return Decimal(cleaned)
        except (ValueError, TypeError, ArithmeticError):
            return Decimal("0")

    def _identify_required_documents(self, income_sources: List[IncomeSourceData]) -> List[str]:
        """Identify required documents based on income types."""
        required = set()

        for source in income_sources:
            income_type = source.income_type

            if income_type == "BASE":
                required.add("PAYSTUB")
                required.add("W2")

            elif income_type in self.VARIABLE_INCOME_TYPES:
                required.add("PAYSTUB")
                required.add("W2")
                # Variable income needs 2 years of W-2s
                source.years_history = 2

            elif income_type in self.SELF_EMPLOYMENT_TYPES:
                required.add("TAX_RETURNS_PERSONAL")
                required.add("TAX_RETURNS_BUSINESS")
                required.add("PROFIT_LOSS_YTD")

            elif income_type == "RENTAL":
                required.add("TAX_RETURNS_PERSONAL")
                required.add("LEASE_AGREEMENT")

            elif income_type in ["ALIMONY", "CHILD_SUPPORT"]:
                required.add("DIVORCE_DECREE")
                required.add("BANK_STATEMENTS")

            elif income_type in ["PENSION", "SOCIAL_SECURITY", "DISABILITY"]:
                required.add("AWARD_LETTER")

        return list(required)

    def _validate_data(self, data: IncomeData) -> Tuple[List[str], List[str]]:
        """Validate income data."""
        issues = []
        warnings = []

        # Check for at least one income source
        if not data.income_sources:
            issues.append("No income sources identified")
        elif data.total_monthly_income == 0:
            issues.append("Total monthly income is $0")

        # Check variable income history
        for source in data.income_sources:
            if source.is_variable:
                if not source.years_history or source.years_history < 2:
                    warnings.append(f"{source.income_type} income requires 2-year history for averaging")

        # Check self-employment
        for source in data.income_sources:
            if source.income_type in self.SELF_EMPLOYMENT_TYPES:
                warnings.append("Self-employment income requires 2-year tax return analysis")

        return issues, warnings

    def _generate_tasks(
        self,
        data: IncomeData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate income-specific tasks."""
        tasks = []

        # Base documentation
        has_base_income = any(s.income_type == "BASE" for s in data.income_sources)
        if has_base_income:
            tasks.append(GeneratedTask(
                title="Collect Recent Paystubs",
                description="Need most recent 30 days of paystubs for income verification.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="PAYSTUB",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload your most recent 30 days of paystubs (typically 2-4 paystubs depending on pay frequency).",
            ))

        # Variable income documentation
        has_variable = any(s.is_variable for s in data.income_sources)
        if has_variable:
            tasks.append(GeneratedTask(
                title="Collect W-2s (2 Years)",
                description="Variable income (overtime/bonus/commission) requires 2 years of W-2s for averaging.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="W2",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload your W-2 forms for the past 2 years to verify your variable income.",
            ))

        # Self-employment documentation
        has_self_emp = any(s.income_type in self.SELF_EMPLOYMENT_TYPES for s in data.income_sources)
        if has_self_emp:
            tasks.append(GeneratedTask(
                title="Collect Tax Returns (2 Years)",
                description="Self-employment requires 2 years of personal and business tax returns.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="TAX_RETURNS",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload your complete personal and business tax returns for the past 2 years, including all schedules.",
            ))

        # Rental income documentation
        has_rental = any(s.income_type == "RENTAL" for s in data.income_sources)
        if has_rental:
            tasks.append(GeneratedTask(
                title="Collect Lease Agreements",
                description="Rental income requires current lease agreements for all rental properties.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="LEASE_AGREEMENT",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload current signed lease agreements for each rental property.",
            ))

        return tasks
