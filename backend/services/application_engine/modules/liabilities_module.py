"""
Liabilities Audit Module

Handles borrower liability information including:
- Mortgages
- Installment loans (auto, student, personal)
- Revolving debt (credit cards)
- Other liabilities

URLA Section: 2b - Liabilities
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
    LiabilitiesData,
    LiabilityData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class LiabilitiesAuditModule(BaseAuditModule):
    """Audit module for borrower liability information."""

    MODULE_TYPE = AuditModuleType.LIABILITIES
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define liability fields for audit."""
        self._field_definitions = {
            "has_mortgage": FieldDefinition(
                name="has_mortgage",
                display_name="Current Mortgage",
                required=False,
                data_type="boolean",
                urla_section="2b",
            ),
            "has_auto_loan": FieldDefinition(
                name="has_auto_loan",
                display_name="Auto Loan",
                required=False,
                data_type="boolean",
                urla_section="2b",
            ),
            "has_student_loans": FieldDefinition(
                name="has_student_loans",
                display_name="Student Loans",
                required=False,
                data_type="boolean",
                urla_section="2b",
            ),
            "has_credit_cards": FieldDefinition(
                name="has_credit_cards",
                display_name="Credit Cards",
                required=False,
                data_type="boolean",
                urla_section="2b",
            ),
            "total_monthly_payments": FieldDefinition(
                name="total_monthly_payments",
                display_name="Total Monthly Debt Payments",
                required=True,
                data_type="decimal",
                urla_section="2b",
                borrower_instructions="What is your total monthly debt payment (including credit cards, auto loans, student loans)?",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> LiabilitiesData:
        """Extract and merge liability data."""
        data = LiabilitiesData()
        data.liabilities = []

        # Extract individual liabilities from call
        liabilities = call_extractions.get("liabilities") or call_extractions.get("debts") or []
        if isinstance(liabilities, dict):
            liabilities = [liabilities]

        for liability in liabilities:
            lib = LiabilityData(
                liability_type=liability.get("type", "OTHER").upper(),
            )
            lib.creditor_name = self.create_extracted_field(
                "creditor",
                liability.get("creditor") or liability.get("lender") or liability.get("name"),
                liability.get("confidence", 75.0),
                "call_transcript"
            )
            lib.current_balance = self.create_extracted_field(
                "balance",
                self._parse_currency(liability.get("balance") or liability.get("owed")),
                liability.get("balance_confidence", 70.0),
                "call_transcript"
            )
            lib.monthly_payment = self.create_extracted_field(
                "payment",
                self._parse_currency(liability.get("payment") or liability.get("monthly_payment")),
                liability.get("payment_confidence", 75.0),
                "call_transcript"
            )
            lib.will_be_paid_off = liability.get("paying_off", False)
            lib.paid_by_closing = liability.get("pay_at_closing", False)
            data.liabilities.append(lib)

        # Handle common liability mentions
        # Auto loan
        auto_payment = call_extractions.get("car_payment") or call_extractions.get("auto_payment")
        if auto_payment:
            if not any(l.liability_type == "AUTO" for l in data.liabilities):
                lib = LiabilityData(liability_type="AUTO")
                lib.monthly_payment = self.create_extracted_field(
                    "payment",
                    self._parse_currency(auto_payment),
                    75.0,
                    "call_transcript"
                )
                lib.current_balance = self.create_extracted_field(
                    "balance",
                    self._parse_currency(call_extractions.get("auto_balance") or call_extractions.get("car_balance")),
                    70.0,
                    "call_transcript"
                )
                data.liabilities.append(lib)

        # Student loans
        student_payment = call_extractions.get("student_loan_payment") or call_extractions.get("student_loans")
        if student_payment:
            if not any(l.liability_type == "STUDENT_LOAN" for l in data.liabilities):
                lib = LiabilityData(liability_type="STUDENT_LOAN")
                lib.monthly_payment = self.create_extracted_field(
                    "payment",
                    self._parse_currency(student_payment),
                    75.0,
                    "call_transcript"
                )
                lib.current_balance = self.create_extracted_field(
                    "balance",
                    self._parse_currency(call_extractions.get("student_balance")),
                    70.0,
                    "call_transcript"
                )
                data.liabilities.append(lib)

        # Credit cards (total)
        cc_payment = call_extractions.get("credit_card_payments") or call_extractions.get("cc_payment")
        if cc_payment:
            if not any(l.liability_type == "REVOLVING" for l in data.liabilities):
                lib = LiabilityData(liability_type="REVOLVING")
                lib.creditor_name = self.create_extracted_field("creditor", "Credit Cards (Combined)", 80.0, "call_transcript")
                lib.monthly_payment = self.create_extracted_field(
                    "payment",
                    self._parse_currency(cc_payment),
                    75.0,
                    "call_transcript"
                )
                lib.current_balance = self.create_extracted_field(
                    "balance",
                    self._parse_currency(call_extractions.get("cc_balance") or call_extractions.get("credit_card_balance")),
                    70.0,
                    "call_transcript"
                )
                data.liabilities.append(lib)

        # Current mortgage
        current_mortgage = call_extractions.get("current_mortgage") or call_extractions.get("mortgage_payment")
        if current_mortgage:
            lib = LiabilityData(liability_type="MORTGAGE")
            lib.monthly_payment = self.create_extracted_field(
                "payment",
                self._parse_currency(current_mortgage),
                80.0,
                "call_transcript"
            )
            lib.current_balance = self.create_extracted_field(
                "balance",
                self._parse_currency(call_extractions.get("mortgage_balance")),
                75.0,
                "call_transcript"
            )
            lib.property_address = call_extractions.get("property_address")
            lib.is_subject_property = call_extractions.get("is_subject_property", False)
            data.liabilities.append(lib)

        # Payoffs at closing
        payoff_debts = call_extractions.get("paying_off") or call_extractions.get("payoffs") or []
        if isinstance(payoff_debts, str):
            payoff_debts = [payoff_debts]
        data.payoffs_at_closing = payoff_debts

        # Calculate totals
        total_payments = Decimal("0")
        total_balances = Decimal("0")
        total_payoff = Decimal("0")

        for lib in data.liabilities:
            if lib.monthly_payment and lib.monthly_payment.value:
                if not lib.paid_by_closing:  # Don't count if paying off at closing
                    total_payments += Decimal(str(lib.monthly_payment.value))

            if lib.current_balance and lib.current_balance.value:
                balance = Decimal(str(lib.current_balance.value))
                total_balances += balance
                if lib.paid_by_closing:
                    total_payoff += balance

        data.total_monthly_payments = total_payments
        data.total_balances = total_balances
        data.total_payoff_amount = total_payoff

        # Merge with existing data
        if existing_data.get("total_monthly_debt"):
            existing_total = Decimal(str(existing_data["total_monthly_debt"]))
            if total_payments == 0:
                data.total_monthly_payments = existing_total

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

        try:
            return Decimal(cleaned)
        except (ValueError, TypeError, ArithmeticError):
            return Decimal("0")

    def _validate_data(self, data: LiabilitiesData) -> Tuple[List[str], List[str]]:
        """Validate liability data."""
        issues = []
        warnings = []

        # Verify credit report will capture details
        if not data.liabilities:
            warnings.append("No liabilities disclosed - credit report will verify")

        # Check for payoff feasibility
        if data.total_payoff_amount > 0:
            warnings.append(f"Payoffs at closing: ${data.total_payoff_amount:,.2f} - verify sufficient funds")

        # Large debt warning
        if data.total_monthly_payments > 3000:
            warnings.append("High monthly debt obligations may impact DTI")

        return issues, warnings

    def _generate_tasks(
        self,
        data: LiabilitiesData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate liability-specific tasks."""
        tasks = []

        # Payoff letters for debts being paid at closing
        payoff_liabilities = [l for l in data.liabilities if l.paid_by_closing]
        if payoff_liabilities:
            for lib in payoff_liabilities:
                creditor = lib.creditor_name.value if lib.creditor_name else "Unknown"
                tasks.append(GeneratedTask(
                    title=f"Obtain Payoff Letter: {creditor}",
                    description=f"Need payoff letter for {lib.liability_type} debt that will be paid at closing.",
                    task_type="COLLECT_DOCUMENT",
                    assignee=TaskAssignee.PA,
                    priority=TaskPriority.MEDIUM,
                    module=self.MODULE_TYPE,
                    required_document_type="PAYOFF_LETTER",
                    borrower_type=borrower_type,
                    borrower_portal_visible=False,
                ))

        # Student loan documentation
        student_loans = [l for l in data.liabilities if l.liability_type == "STUDENT_LOAN"]
        if student_loans:
            # Check if IBR/IDR plan
            tasks.append(GeneratedTask(
                title="Verify Student Loan Payment Plan",
                description="If student loans are on Income-Based Repayment (IBR), need documentation of payment amount.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="STUDENT_LOAN_STATEMENT",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="If your student loans are on an income-based repayment plan, please provide documentation showing your monthly payment amount.",
            ))

        # Alimony/child support verification
        support_liabilities = [l for l in data.liabilities if l.liability_type in ["ALIMONY", "CHILD_SUPPORT"]]
        if support_liabilities:
            tasks.append(GeneratedTask(
                title="Collect Divorce Decree/Support Order",
                description="Need divorce decree or court order showing support obligation.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="DIVORCE_DECREE",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please provide your divorce decree or court order showing your alimony/child support obligation.",
            ))

        return tasks
