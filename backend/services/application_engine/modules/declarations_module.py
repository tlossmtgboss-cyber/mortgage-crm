"""
Declarations Audit Module

Handles URLA declarations (yes/no questions) including:
- Property and transaction questions
- Financial questions
- Derogatory credit history

URLA Sections: J and K - Declarations
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, date

from ..base import BaseAuditModule, FieldDefinition
from ..data_contracts import (
    AuditModuleType,
    FieldStatus,
    ExtractedField,
    DeclarationData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class DeclarationsAuditModule(BaseAuditModule):
    """Audit module for URLA declarations."""

    MODULE_TYPE = AuditModuleType.DECLARATIONS
    MODULE_VERSION = "1.0"

    # Declarations that require explanation letters if "yes"
    REQUIRES_EXPLANATION = [
        "has_outstanding_judgments",
        "is_delinquent_federal_debt",
        "is_party_to_lawsuit",
        "has_conveyed_title_lieu",
        "has_preforeclosure_short_sale",
        "has_foreclosure",
        "has_bankruptcy",
        "is_co_signer",
    ]

    def _setup_field_definitions(self) -> None:
        """Define declaration fields for audit."""
        # Section J - About This Property and Your Money for This Loan
        self._field_definitions = {
            "will_occupy_as_primary": FieldDefinition(
                name="will_occupy_as_primary",
                display_name="Occupy as Primary Residence",
                required=True,
                data_type="boolean",
                urla_section="J",
                borrower_instructions="Will you occupy the property as your primary residence?",
            ),
            "has_ownership_interest_3yrs": FieldDefinition(
                name="has_ownership_interest_3yrs",
                display_name="Ownership Interest in Last 3 Years",
                required=True,
                data_type="boolean",
                urla_section="J",
                borrower_instructions="Have you had an ownership interest in a property in the last three years?",
            ),
            "has_family_relationship_seller": FieldDefinition(
                name="has_family_relationship_seller",
                display_name="Family Relationship with Seller",
                required=True,
                data_type="boolean",
                urla_section="J",
            ),
            "borrowing_money_for_transaction": FieldDefinition(
                name="borrowing_money_for_transaction",
                display_name="Borrowing Money for Down Payment",
                required=True,
                data_type="boolean",
                urla_section="J",
            ),
            "applying_for_other_mortgage": FieldDefinition(
                name="applying_for_other_mortgage",
                display_name="Applying for Other Mortgage",
                required=True,
                data_type="boolean",
                urla_section="J",
            ),
            "applying_for_other_credit": FieldDefinition(
                name="applying_for_other_credit",
                display_name="Applying for Other Credit",
                required=True,
                data_type="boolean",
                urla_section="J",
            ),
            "subject_to_lien": FieldDefinition(
                name="subject_to_lien",
                display_name="Subject Property Has Lien",
                required=True,
                data_type="boolean",
                urla_section="J",
            ),
            # Section K - About Your Finances
            "is_co_signer": FieldDefinition(
                name="is_co_signer",
                display_name="Co-signer on Other Debt",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Are you a co-signer or guarantor on any debt not listed above?",
            ),
            "has_outstanding_judgments": FieldDefinition(
                name="has_outstanding_judgments",
                display_name="Outstanding Judgments",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Are there any outstanding judgments against you?",
            ),
            "is_delinquent_federal_debt": FieldDefinition(
                name="is_delinquent_federal_debt",
                display_name="Delinquent on Federal Debt",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Are you presently delinquent on any federal debt or other government loan?",
            ),
            "is_party_to_lawsuit": FieldDefinition(
                name="is_party_to_lawsuit",
                display_name="Party to Lawsuit",
                required=True,
                data_type="boolean",
                urla_section="K",
            ),
            "has_conveyed_title_lieu": FieldDefinition(
                name="has_conveyed_title_lieu",
                display_name="Conveyed Title in Lieu of Foreclosure",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Have you conveyed title to any property in lieu of foreclosure in the past 7 years?",
            ),
            "has_preforeclosure_short_sale": FieldDefinition(
                name="has_preforeclosure_short_sale",
                display_name="Pre-foreclosure or Short Sale",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Have you completed a pre-foreclosure sale or short sale in the past 7 years?",
            ),
            "has_foreclosure": FieldDefinition(
                name="has_foreclosure",
                display_name="Foreclosure",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Have you had property foreclosed upon in the past 7 years?",
            ),
            "has_bankruptcy": FieldDefinition(
                name="has_bankruptcy",
                display_name="Bankruptcy",
                required=True,
                data_type="boolean",
                urla_section="K",
                borrower_instructions="Have you declared bankruptcy within the past 7 years?",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> DeclarationData:
        """Extract and merge declaration data."""
        data = DeclarationData()

        # Section J - Property/Transaction
        data.will_occupy_as_primary = self._extract_boolean_field(
            call_extractions, existing_data,
            ["will_occupy", "primary_residence", "will_live_there"],
            "will_occupy_as_primary"
        )

        data.has_ownership_interest_3yrs = self._extract_boolean_field(
            call_extractions, existing_data,
            ["owned_property", "prior_ownership", "ownership_interest"],
            "has_ownership_interest_3yrs"
        )

        data.has_family_relationship_seller = self._extract_boolean_field(
            call_extractions, existing_data,
            ["family_seller", "related_to_seller"],
            "has_family_relationship_seller"
        )

        data.borrowing_money_for_transaction = self._extract_boolean_field(
            call_extractions, existing_data,
            ["borrowing_down_payment", "borrowed_funds"],
            "borrowing_money_for_transaction"
        )

        data.applying_for_other_mortgage = self._extract_boolean_field(
            call_extractions, existing_data,
            ["other_mortgage", "applying_elsewhere"],
            "applying_for_other_mortgage"
        )

        data.applying_for_other_credit = self._extract_boolean_field(
            call_extractions, existing_data,
            ["other_credit", "new_credit"],
            "applying_for_other_credit"
        )

        data.subject_to_lien = self._extract_boolean_field(
            call_extractions, existing_data,
            ["has_lien", "property_lien"],
            "subject_to_lien"
        )

        # Section K - Finances
        data.is_co_signer = self._extract_boolean_field(
            call_extractions, existing_data,
            ["co_signer", "cosigned", "guarantor"],
            "is_co_signer"
        )

        data.has_outstanding_judgments = self._extract_boolean_field(
            call_extractions, existing_data,
            ["judgments", "outstanding_judgments"],
            "has_outstanding_judgments"
        )

        data.is_delinquent_federal_debt = self._extract_boolean_field(
            call_extractions, existing_data,
            ["federal_debt", "delinquent_federal", "government_loan"],
            "is_delinquent_federal_debt"
        )

        data.is_party_to_lawsuit = self._extract_boolean_field(
            call_extractions, existing_data,
            ["lawsuit", "litigation"],
            "is_party_to_lawsuit"
        )

        data.has_conveyed_title_lieu = self._extract_boolean_field(
            call_extractions, existing_data,
            ["deed_in_lieu", "title_lieu"],
            "has_conveyed_title_lieu"
        )

        data.has_preforeclosure_short_sale = self._extract_boolean_field(
            call_extractions, existing_data,
            ["short_sale", "preforeclosure"],
            "has_preforeclosure_short_sale"
        )

        data.has_foreclosure = self._extract_boolean_field(
            call_extractions, existing_data,
            ["foreclosure", "foreclosed"],
            "has_foreclosure"
        )

        data.has_bankruptcy = self._extract_boolean_field(
            call_extractions, existing_data,
            ["bankruptcy", "filed_bankruptcy", "bankrupt"],
            "has_bankruptcy"
        )

        # Bankruptcy details if yes
        if data.has_bankruptcy and data.has_bankruptcy.value:
            data.bankruptcy_chapter = call_extractions.get("bankruptcy_chapter")
            discharge_date = call_extractions.get("bankruptcy_discharge_date")
            if discharge_date:
                try:
                    from dateutil import parser
                    data.bankruptcy_discharge_date = parser.parse(str(discharge_date)).date()
                except (ValueError, TypeError):
                    pass

        # Collect explanation notes
        data.explanation_notes = {}
        for field_name in self.REQUIRES_EXPLANATION:
            field_value = getattr(data, field_name, None)
            if field_value and field_value.value:
                explanation_key = f"{field_name}_explanation"
                explanation = call_extractions.get(explanation_key) or call_extractions.get(f"{field_name}_notes")
                if explanation:
                    data.explanation_notes[field_name] = explanation

        return data

    def _extract_boolean_field(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
        call_keys: List[str],
        field_name: str,
    ) -> Optional[ExtractedField]:
        """Extract a boolean field checking multiple possible keys."""
        call_value = None
        confidence = 80.0

        for key in call_keys:
            if key in call_extractions:
                call_value = call_extractions[key]
                confidence = call_extractions.get(f"{key}_confidence", 80.0)
                break

        # Also check the exact field name
        if call_value is None and field_name in call_extractions:
            call_value = call_extractions[field_name]

        existing_value = existing_data.get(field_name)

        if call_value is None and existing_value is None:
            return None

        # Normalize boolean
        if call_value is not None:
            call_value = self._normalize_boolean(call_value)

        return self.merge_field(call_value, existing_value, field_name, confidence)

    def _normalize_boolean(self, value: Any) -> Optional[bool]:
        """Normalize various representations to boolean."""
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        value_str = str(value).lower().strip()

        if value_str in ["yes", "true", "1", "y"]:
            return True
        elif value_str in ["no", "false", "0", "n"]:
            return False

        return None

    def _validate_data(self, data: DeclarationData) -> Tuple[List[str], List[str]]:
        """Validate declaration data."""
        issues = []
        warnings = []

        # Check for "yes" answers that need explanation
        for field_name in self.REQUIRES_EXPLANATION:
            field_value = getattr(data, field_name, None)
            if field_value and field_value.value:
                if field_name not in data.explanation_notes:
                    warnings.append(f"{self._field_definitions[field_name].display_name}: explanation required")

        # Specific validations
        if data.has_bankruptcy and data.has_bankruptcy.value:
            if not data.bankruptcy_chapter:
                warnings.append("Bankruptcy chapter not specified")
            if not data.bankruptcy_discharge_date:
                warnings.append("Bankruptcy discharge date needed for seasoning calculation")
            else:
                # Check seasoning
                today = date.today()
                years_since = (today - data.bankruptcy_discharge_date).days / 365
                if years_since < 2:
                    issues.append("Bankruptcy discharge less than 2 years ago - may not meet seasoning requirements")
                elif years_since < 4:
                    warnings.append(f"Bankruptcy discharged {years_since:.1f} years ago - verify guideline requirements")

        if data.has_foreclosure and data.has_foreclosure.value:
            warnings.append("Foreclosure history - verify seasoning requirements (typically 3-7 years)")

        if data.has_preforeclosure_short_sale and data.has_preforeclosure_short_sale.value:
            warnings.append("Short sale history - verify seasoning requirements (typically 2-4 years)")

        return issues, warnings

    def _generate_tasks(
        self,
        data: DeclarationData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate declaration-specific tasks."""
        tasks = super()._generate_tasks(data, field_stats, loan_id, borrower_type)

        # Letter of Explanation tasks for "yes" answers
        for field_name in self.REQUIRES_EXPLANATION:
            field_value = getattr(data, field_name, None)
            if field_value and field_value.value and field_name not in data.explanation_notes:
                display_name = self._field_definitions[field_name].display_name
                tasks.append(GeneratedTask(
                    title=f"Letter of Explanation: {display_name}",
                    description=f"Borrower answered 'Yes' to {display_name}. Need signed letter of explanation.",
                    task_type="COLLECT_DOCUMENT",
                    assignee=TaskAssignee.BORROWER,
                    priority=TaskPriority.HIGH,
                    module=self.MODULE_TYPE,
                    field_name=field_name,
                    required_document_type="LETTER_OF_EXPLANATION",
                    borrower_type=borrower_type,
                    borrower_portal_visible=True,
                    borrower_instructions=f"Please provide a signed letter explaining the circumstances around: {display_name}",
                ))

        # Bankruptcy documentation
        if data.has_bankruptcy and data.has_bankruptcy.value:
            tasks.append(GeneratedTask(
                title="Collect Bankruptcy Documents",
                description="Need bankruptcy schedules and discharge papers.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="BANKRUPTCY_DISCHARGE",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide your bankruptcy discharge papers and schedules.",
            ))

        return tasks
