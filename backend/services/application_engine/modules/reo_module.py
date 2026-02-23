"""
REO (Real Estate Owned) Audit Module

Handles borrower real estate ownership including:
- Primary residence
- Investment properties
- Second homes
- Properties being sold

URLA Section: 2c - Real Estate
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
    REOData,
    RealEstateData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class REOAuditModule(BaseAuditModule):
    """Audit module for real estate owned."""

    MODULE_TYPE = AuditModuleType.REO
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define REO fields for audit."""
        self._field_definitions = {
            "owns_real_estate": FieldDefinition(
                name="owns_real_estate",
                display_name="Owns Real Estate",
                required=True,
                data_type="boolean",
                urla_section="2c",
                borrower_instructions="Do you currently own any real estate properties?",
            ),
            "property_count": FieldDefinition(
                name="property_count",
                display_name="Number of Properties",
                required=False,
                data_type="integer",
                urla_section="2c",
            ),
            "owns_primary_residence": FieldDefinition(
                name="owns_primary_residence",
                display_name="Owns Primary Residence",
                required=False,
                data_type="boolean",
                urla_section="2c",
            ),
            "has_investment_property": FieldDefinition(
                name="has_investment_property",
                display_name="Has Investment Property",
                required=False,
                data_type="boolean",
                urla_section="2c",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> REOData:
        """Extract and merge REO data."""
        data = REOData()
        data.properties = []

        # Check if borrower owns real estate
        owns_real_estate = call_extractions.get("owns_real_estate") or call_extractions.get("owns_property")
        owns_current_home = call_extractions.get("owns_current_home") or call_extractions.get("homeowner")

        # Extract individual properties
        properties = call_extractions.get("properties") or call_extractions.get("real_estate") or []
        if isinstance(properties, dict):
            properties = [properties]

        for prop in properties:
            reo = RealEstateData()
            reo.property_address = self.create_extracted_field(
                "address",
                prop.get("address") or prop.get("property_address"),
                prop.get("confidence", 80.0),
                "call_transcript"
            )
            reo.property_type = self.create_extracted_field(
                "type",
                prop.get("type") or prop.get("property_type"),
                75.0,
                "call_transcript"
            )
            reo.current_value = self.create_extracted_field(
                "value",
                self._parse_currency(prop.get("value") or prop.get("worth")),
                70.0,
                "call_transcript"
            )
            reo.usage_type = self.create_extracted_field(
                "usage",
                prop.get("usage") or prop.get("use_type"),
                80.0,
                "call_transcript"
            )

            # Mortgage details
            has_mortgage = prop.get("has_mortgage", True)
            if has_mortgage:
                reo.has_mortgage = True
                reo.mortgage_balance = self.create_extracted_field(
                    "mortgage_balance",
                    self._parse_currency(prop.get("mortgage_balance") or prop.get("owed")),
                    70.0,
                    "call_transcript"
                )
                reo.mortgage_payment = self.create_extracted_field(
                    "payment",
                    self._parse_currency(prop.get("payment") or prop.get("mortgage_payment")),
                    75.0,
                    "call_transcript"
                )
                reo.lender_name = self.create_extracted_field(
                    "lender",
                    prop.get("lender") or prop.get("mortgage_company"),
                    70.0,
                    "call_transcript"
                )

            # Rental details
            if prop.get("is_rental") or prop.get("rented"):
                reo.is_rental = True
                reo.monthly_rent = self.create_extracted_field(
                    "rent",
                    self._parse_currency(prop.get("rent") or prop.get("rental_income")),
                    75.0,
                    "call_transcript"
                )

            # Disposition
            reo.will_be_sold = prop.get("selling", False) or prop.get("will_sell", False)
            reo.pending_sale = prop.get("pending_sale", False)
            reo.will_be_retained = not reo.will_be_sold

            data.properties.append(reo)

        # Handle current home ownership mention
        if owns_current_home and not data.properties:
            reo = RealEstateData()
            reo.usage_type = self.create_extracted_field("usage", "PRIMARY", 90.0, "call_transcript")

            current_value = call_extractions.get("home_value") or call_extractions.get("property_value")
            if current_value:
                reo.current_value = self.create_extracted_field(
                    "value",
                    self._parse_currency(current_value),
                    70.0,
                    "call_transcript"
                )

            mortgage_balance = call_extractions.get("mortgage_balance") or call_extractions.get("owed_on_home")
            if mortgage_balance:
                reo.has_mortgage = True
                reo.mortgage_balance = self.create_extracted_field(
                    "mortgage_balance",
                    self._parse_currency(mortgage_balance),
                    70.0,
                    "call_transcript"
                )

            mortgage_payment = call_extractions.get("current_mortgage") or call_extractions.get("mortgage_payment")
            if mortgage_payment:
                reo.mortgage_payment = self.create_extracted_field(
                    "payment",
                    self._parse_currency(mortgage_payment),
                    75.0,
                    "call_transcript"
                )

            # Check if selling current home
            selling = call_extractions.get("selling_home") or call_extractions.get("will_sell_current")
            reo.will_be_sold = selling or False
            reo.will_be_retained = not reo.will_be_sold

            data.properties.append(reo)

        # Handle rental property mentions
        has_rental = call_extractions.get("has_rental_property") or call_extractions.get("owns_rental")
        if has_rental and not any(p.is_rental for p in data.properties):
            reo = RealEstateData()
            reo.is_rental = True
            reo.usage_type = self.create_extracted_field("usage", "INVESTMENT", 85.0, "call_transcript")

            rental_income = call_extractions.get("rental_income") or call_extractions.get("rent_received")
            if rental_income:
                reo.monthly_rent = self.create_extracted_field(
                    "rent",
                    self._parse_currency(rental_income),
                    75.0,
                    "call_transcript"
                )

            data.properties.append(reo)

        # Calculate totals
        total_value = Decimal("0")
        total_mortgage = Decimal("0")
        total_payments = Decimal("0")
        total_rental = Decimal("0")

        for prop in data.properties:
            if prop.current_value and prop.current_value.value:
                total_value += Decimal(str(prop.current_value.value))
            if prop.mortgage_balance and prop.mortgage_balance.value:
                total_mortgage += Decimal(str(prop.mortgage_balance.value))
            if prop.mortgage_payment and prop.mortgage_payment.value:
                total_payments += Decimal(str(prop.mortgage_payment.value))
            if prop.monthly_rent and prop.monthly_rent.value:
                total_rental += Decimal(str(prop.monthly_rent.value))

        data.total_property_value = total_value
        data.total_mortgage_balance = total_mortgage
        data.total_monthly_payments = total_payments
        data.total_rental_income = total_rental

        return data

    def _parse_currency(self, value: Any) -> Decimal:
        """Parse currency value."""
        if value is None:
            return Decimal("0")

        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))

        import re
        cleaned = re.sub(r'[$,\s]', '', str(value))

        if cleaned.lower().endswith('k'):
            return Decimal(cleaned[:-1]) * 1000
        if cleaned.lower().endswith('m'):
            return Decimal(cleaned[:-1]) * 1000000

        try:
            return Decimal(cleaned)
        except (ValueError, TypeError, ArithmeticError):
            return Decimal("0")

    def _validate_data(self, data: REOData) -> Tuple[List[str], List[str]]:
        """Validate REO data."""
        issues = []
        warnings = []

        for prop in data.properties:
            # Rental income validation
            if prop.is_rental:
                if not prop.monthly_rent or not prop.monthly_rent.value:
                    warnings.append("Rental property identified but no rental income provided")

            # Property being sold
            if prop.will_be_sold:
                warnings.append("Property being sold - may need sales contract for net equity")

        # Multiple investment properties warning
        investment_count = len([p for p in data.properties if p.usage_type and p.usage_type.value == "INVESTMENT"])
        if investment_count >= 4:
            warnings.append(f"{investment_count} investment properties - verify financed property limits")

        return issues, warnings

    def _generate_tasks(
        self,
        data: REOData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate REO-specific tasks."""
        tasks = []

        # Mortgage statements for properties being retained
        retained_with_mortgage = [p for p in data.properties if p.will_be_retained and p.has_mortgage]
        if retained_with_mortgage:
            tasks.append(GeneratedTask(
                title="Collect Mortgage Statements",
                description=f"Need recent mortgage statements for {len(retained_with_mortgage)} retained property/properties.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="MORTGAGE_STATEMENT",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide the most recent mortgage statement for each property you own.",
            ))

        # Lease agreements for rental properties
        rental_properties = [p for p in data.properties if p.is_rental]
        if rental_properties:
            tasks.append(GeneratedTask(
                title="Collect Lease Agreements",
                description=f"Need current lease agreements for {len(rental_properties)} rental property/properties.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="LEASE_AGREEMENT",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide signed lease agreements for each rental property.",
            ))

        # Sales contract for properties being sold
        properties_for_sale = [p for p in data.properties if p.will_be_sold or p.pending_sale]
        if properties_for_sale:
            tasks.append(GeneratedTask(
                title="Collect Sales Contract",
                description="Need purchase contract for property being sold to verify net equity.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="PURCHASE_CONTRACT",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide the signed purchase contract for the property you are selling.",
            ))

        return tasks
