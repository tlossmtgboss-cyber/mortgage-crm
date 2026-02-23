"""
Assets Audit Module

Handles borrower asset information including:
- Bank accounts (checking, savings)
- Investment accounts
- Retirement accounts
- Gift funds
- Down payment sources

URLA Section: 2a - Assets
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
    AssetsData,
    AssetData,
    GeneratedTask,
    TaskPriority,
    TaskAssignee,
)

logger = logging.getLogger(__name__)


class AssetsAuditModule(BaseAuditModule):
    """Audit module for borrower asset information."""

    MODULE_TYPE = AuditModuleType.ASSETS
    MODULE_VERSION = "1.0"

    def _setup_field_definitions(self) -> None:
        """Define asset fields for audit."""
        self._field_definitions = {
            "has_checking_account": FieldDefinition(
                name="has_checking_account",
                display_name="Checking Account",
                required=True,
                data_type="boolean",
                urla_section="2a",
                requires_documentation=True,
                document_types=["BANK_STATEMENTS"],
            ),
            "has_savings_account": FieldDefinition(
                name="has_savings_account",
                display_name="Savings Account",
                required=False,
                data_type="boolean",
                urla_section="2a",
                requires_documentation=True,
                document_types=["BANK_STATEMENTS"],
            ),
            "has_investment_account": FieldDefinition(
                name="has_investment_account",
                display_name="Investment Account",
                required=False,
                data_type="boolean",
                urla_section="2a",
                requires_documentation=True,
                document_types=["INVESTMENT_STATEMENTS"],
            ),
            "has_retirement_account": FieldDefinition(
                name="has_retirement_account",
                display_name="Retirement Account",
                required=False,
                data_type="boolean",
                urla_section="2a",
                requires_documentation=True,
                document_types=["RETIREMENT_STATEMENTS"],
            ),
            "total_liquid_assets": FieldDefinition(
                name="total_liquid_assets",
                display_name="Total Liquid Assets",
                required=True,
                data_type="decimal",
                urla_section="2a",
                borrower_instructions="Please provide the total balance of all your liquid assets (checking, savings, money market).",
            ),
            "down_payment_source": FieldDefinition(
                name="down_payment_source",
                display_name="Down Payment Source",
                required=True,
                data_type="string",
                urla_section="2a",
                borrower_instructions="Where will your down payment funds come from?",
            ),
            "down_payment_amount": FieldDefinition(
                name="down_payment_amount",
                display_name="Down Payment Amount",
                required=True,
                data_type="decimal",
                urla_section="2a",
            ),
        }

    def _extract_data(
        self,
        call_extractions: Dict[str, Any],
        existing_data: Dict[str, Any],
    ) -> AssetsData:
        """Extract and merge asset data."""
        data = AssetsData()
        data.assets = []

        # Extract bank accounts
        bank_accounts = call_extractions.get("bank_accounts") or []
        if isinstance(bank_accounts, dict):
            bank_accounts = [bank_accounts]

        for account in bank_accounts:
            asset = AssetData(
                asset_type=account.get("type", "CHECKING").upper(),
            )
            asset.institution_name = self.create_extracted_field(
                "institution",
                account.get("bank") or account.get("institution"),
                account.get("confidence", 80.0),
                "call_transcript"
            )
            asset.current_balance = self.create_extracted_field(
                "balance",
                self._parse_currency(account.get("balance")),
                account.get("balance_confidence", 75.0),
                "call_transcript"
            )
            asset.account_number_last4 = self.create_extracted_field(
                "account_last4",
                account.get("account_last4") or account.get("last4"),
                80.0,
                "call_transcript"
            )
            data.assets.append(asset)

        # Handle simple mentions like "I have a checking account at Chase with about 50k"
        checking_bank = call_extractions.get("checking_bank") or call_extractions.get("bank_name")
        checking_balance = call_extractions.get("checking_balance") or call_extractions.get("savings")
        if checking_bank or checking_balance:
            if not any(a.asset_type == "CHECKING" for a in data.assets):
                asset = AssetData(asset_type="CHECKING")
                asset.institution_name = self.create_extracted_field(
                    "institution",
                    checking_bank,
                    75.0,
                    "call_transcript"
                )
                asset.current_balance = self.create_extracted_field(
                    "balance",
                    self._parse_currency(checking_balance),
                    70.0,
                    "call_transcript"
                )
                data.assets.append(asset)

        # Extract investment/retirement accounts
        retirement_mentioned = call_extractions.get("has_retirement") or call_extractions.get("401k") or call_extractions.get("ira")
        if retirement_mentioned:
            retirement_balance = call_extractions.get("retirement_balance") or call_extractions.get("401k_balance")
            asset = AssetData(asset_type="RETIREMENT")
            asset.current_balance = self.create_extracted_field(
                "balance",
                self._parse_currency(retirement_balance),
                70.0,
                "call_transcript"
            )
            if retirement_balance:
                data.assets.append(asset)

        # Extract gift funds
        gift_amount = call_extractions.get("gift_amount") or call_extractions.get("gift_funds")
        if gift_amount:
            asset = AssetData(asset_type="GIFT", is_gift=True)
            asset.current_balance = self.create_extracted_field(
                "amount",
                self._parse_currency(gift_amount),
                80.0,
                "call_transcript"
            )
            asset.gift_donor_name = self.create_extracted_field(
                "donor",
                call_extractions.get("gift_donor") or call_extractions.get("gift_from"),
                70.0,
                "call_transcript"
            )
            asset.gift_donor_relationship = self.create_extracted_field(
                "relationship",
                call_extractions.get("gift_relationship"),
                70.0,
                "call_transcript"
            )
            data.assets.append(asset)

        # Calculate totals
        total_liquid = Decimal("0")
        total_retirement = Decimal("0")
        total_gift = Decimal("0")

        for asset in data.assets:
            if asset.current_balance and asset.current_balance.value:
                balance = Decimal(str(asset.current_balance.value))
                if asset.asset_type in ["CHECKING", "SAVINGS", "MONEY_MARKET"]:
                    total_liquid += balance
                elif asset.asset_type == "RETIREMENT":
                    total_retirement += balance
                elif asset.is_gift:
                    total_gift += balance

        data.total_liquid_assets = total_liquid
        data.total_retirement_assets = total_retirement
        data.total_gift_funds = total_gift

        # Down payment source
        data.down_payment_source = call_extractions.get("down_payment_source") or call_extractions.get("dp_source")
        data.down_payment_amount = self._parse_currency(
            call_extractions.get("down_payment_amount") or call_extractions.get("down_payment")
        )

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

    def _validate_data(self, data: AssetsData) -> Tuple[List[str], List[str]]:
        """Validate asset data."""
        issues = []
        warnings = []

        # Check for at least one asset account
        if not data.assets:
            issues.append("No asset accounts identified")

        # Check down payment source
        if not data.down_payment_source:
            warnings.append("Down payment source not identified")

        # Check if gift funds need verification
        if data.total_gift_funds > 0:
            gift_assets = [a for a in data.assets if a.is_gift]
            for gift in gift_assets:
                if not gift.gift_donor_name or not gift.gift_donor_name.value:
                    issues.append("Gift donor name required for gift funds")
                if not gift.gift_donor_relationship or not gift.gift_donor_relationship.value:
                    warnings.append("Gift donor relationship needed for gift letter")

        # Large deposit warning
        if data.total_liquid_assets > 100000:
            warnings.append("Large asset balances may require source documentation")

        return issues, warnings

    def _generate_tasks(
        self,
        data: AssetsData,
        field_stats: Dict[str, int],
        loan_id: Optional[int],
        borrower_type: str,
    ) -> List[GeneratedTask]:
        """Generate asset-specific tasks."""
        tasks = []

        # Bank statements for all accounts
        bank_accounts = [a for a in data.assets if a.asset_type in ["CHECKING", "SAVINGS", "MONEY_MARKET"]]
        if bank_accounts:
            tasks.append(GeneratedTask(
                title="Collect Bank Statements (2 Months)",
                description=f"Need 2 months of statements for {len(bank_accounts)} bank account(s).",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="BANK_STATEMENTS",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload the most recent 2 months of bank statements for all accounts. Statements must show your name, account number, and all pages.",
            ))

        # Retirement/investment statements
        retirement_accounts = [a for a in data.assets if a.asset_type in ["RETIREMENT", "401K", "IRA", "INVESTMENT"]]
        if retirement_accounts:
            tasks.append(GeneratedTask(
                title="Collect Retirement/Investment Statements",
                description="Need most recent quarterly statement for retirement and investment accounts.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.MEDIUM,
                module=self.MODULE_TYPE,
                required_document_type="RETIREMENT_STATEMENTS",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please upload your most recent quarterly statement for each retirement or investment account.",
            ))

        # Gift letter if gift funds
        gift_assets = [a for a in data.assets if a.is_gift]
        if gift_assets:
            tasks.append(GeneratedTask(
                title="Collect Gift Letter",
                description="Gift funds require a signed gift letter from donor.",
                task_type="COLLECT_DOCUMENT",
                assignee=TaskAssignee.BORROWER,
                priority=TaskPriority.HIGH,
                module=self.MODULE_TYPE,
                required_document_type="GIFT_LETTER",
                borrower_type=borrower_type,
                borrower_portal_visible=True,
                borrower_instructions="Please have your gift donor complete and sign the gift letter. The letter must confirm the gift does not need to be repaid.",
            ))

        return tasks
