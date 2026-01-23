"""
Asset Analyzer Module

Analyzes borrower assets for mortgage qualification per agency guidelines.
Key capabilities:
- Large deposit detection and sourcing
- Gift fund verification
- Asset seasoning requirements
- Funds-to-close calculation
- Reserve requirement verification

References:
- Fannie Mae Selling Guide B3-4 (Asset Assessment)
- Freddie Mac Guide Chapter 5400 (Asset Assessment)
- FHA 4000.1 II.A.4.d (Assets)
- VA Pamphlet 26-7 Chapter 4 (Assets)
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


class AssetType(str, Enum):
    """Types of assets for qualification."""
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    CD = "certificate_of_deposit"
    STOCKS = "stocks"
    BONDS = "bonds"
    MUTUAL_FUNDS = "mutual_funds"
    RETIREMENT_401K = "retirement_401k"
    RETIREMENT_IRA = "retirement_ira"
    RETIREMENT_OTHER = "retirement_other"
    GIFT = "gift"
    GRANT = "grant"
    EMPLOYER_ASSISTANCE = "employer_assistance"
    REAL_ESTATE_EQUITY = "real_estate_equity"
    BUSINESS_ASSETS = "business_assets"
    TRUST = "trust"
    CASH_VALUE_LIFE = "cash_value_life_insurance"
    PROCEEDS_SALE = "proceeds_from_sale"
    OTHER = "other"


class AssetStatus(str, Enum):
    """Status of asset verification."""
    VERIFIED = "verified"
    NEEDS_DOCUMENTATION = "needs_documentation"
    NEEDS_SOURCING = "needs_sourcing"
    INELIGIBLE = "ineligible"
    PARTIALLY_ELIGIBLE = "partially_eligible"


@dataclass
class LargeDeposit:
    """Represents a large deposit requiring sourcing."""
    date: str
    amount: Decimal
    description: str
    account: str
    is_sourced: bool = False
    source_explanation: str = ""
    source_documentation: str = ""
    is_acceptable: bool = False


@dataclass
class AssetItem:
    """Individual asset with verification details."""
    asset_type: AssetType
    institution: str
    account_last_4: str
    current_balance: Decimal
    eligible_amount: Decimal
    status: AssetStatus
    documentation_status: str  # complete, partial, missing
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    large_deposits: List[LargeDeposit] = field(default_factory=list)
    guideline_reference: str = ""
    notes: str = ""
    # For retirement accounts
    vested_amount: Optional[Decimal] = None
    discount_rate: Optional[Decimal] = None


@dataclass
class AssetResult:
    """Complete asset analysis result."""
    total_liquid_assets: Decimal
    total_eligible_for_closing: Decimal
    total_eligible_for_reserves: Decimal
    asset_items: List[AssetItem]
    funds_to_close: Dict[str, Decimal]
    reserves_available: Dict[str, Any]
    is_sufficient: bool
    shortfall_amount: Decimal
    issues: List[str]
    warnings: List[str]
    conditions_needed: List[Dict[str, Any]]
    large_deposits_unsourced: List[LargeDeposit]


class AssetAnalyzer:
    """
    Analyzes borrower assets per agency guidelines.

    Key principles:
    1. Large deposits must be sourced (> 50% of monthly income for Conv, > $200 for FHA)
    2. Gift funds require proper documentation
    3. Retirement assets discounted (usually 60-70% of vested)
    4. Assets must be verified within 120 days of closing
    5. Reserve requirements vary by property type
    """

    # Retirement account discount rates by program
    RETIREMENT_DISCOUNT = {
        "conventional": Decimal("0.60"),  # 60% of vested balance
        "fha": Decimal("0.60"),
        "va": Decimal("1.00"),  # VA allows 100%
        "usda": Decimal("0.60"),
    }

    # Reserve requirements by property type (months of PITIA)
    RESERVE_REQUIREMENTS = {
        "conventional": {
            "primary_1_unit": 0,
            "primary_2_4_unit": 2,
            "second_home": 2,
            "investment": 6,
            "with_high_dti": 6,  # If DTI > 45%
        },
        "fha": {
            "1_2_unit": 0,
            "3_4_unit": 3,
        },
        "va": {
            "all": 0,  # VA doesn't require reserves
        },
        "usda": {
            "all": 0,
        },
    }

    def __init__(
        self,
        loan_program: str = "conventional",
        monthly_qualifying_income: Decimal = Decimal("0"),
    ):
        """Initialize analyzer."""
        self.loan_program = loan_program.lower()
        self.monthly_income = monthly_qualifying_income
        self.retirement_discount = self.RETIREMENT_DISCOUNT.get(
            self.loan_program, Decimal("0.60")
        )

    def analyze_all_assets(
        self,
        assets_data: List[Dict[str, Any]],
        funds_needed: Dict[str, Decimal],
        property_type: str = "primary_1_unit",
        monthly_pitia: Decimal = Decimal("0"),
        dti_ratio: Decimal = Decimal("0"),
    ) -> AssetResult:
        """
        Analyze all borrower assets.

        Args:
            assets_data: List of asset account dictionaries
            funds_needed: Dict with 'down_payment', 'closing_costs', 'prepaid'
            property_type: Property type for reserve requirements
            monthly_pitia: Monthly payment for reserve calculation
            dti_ratio: DTI ratio (may affect reserve requirements)

        Returns:
            AssetResult with complete analysis
        """
        analyzed_assets = []
        all_large_deposits = []
        all_issues = []
        all_warnings = []
        conditions_needed = []

        total_liquid = Decimal("0")
        total_eligible_closing = Decimal("0")
        total_eligible_reserves = Decimal("0")

        for asset in assets_data:
            analyzed = self._analyze_asset(asset)
            analyzed_assets.append(analyzed)

            # Accumulate totals
            if analyzed.status != AssetStatus.INELIGIBLE:
                if analyzed.asset_type in [
                    AssetType.CHECKING, AssetType.SAVINGS,
                    AssetType.MONEY_MARKET, AssetType.CD,
                ]:
                    total_liquid += analyzed.eligible_amount
                    total_eligible_closing += analyzed.eligible_amount
                    total_eligible_reserves += analyzed.eligible_amount
                elif analyzed.asset_type in [
                    AssetType.STOCKS, AssetType.BONDS, AssetType.MUTUAL_FUNDS,
                ]:
                    total_liquid += analyzed.eligible_amount
                    total_eligible_closing += analyzed.eligible_amount
                    total_eligible_reserves += analyzed.eligible_amount
                elif analyzed.asset_type in [
                    AssetType.RETIREMENT_401K, AssetType.RETIREMENT_IRA,
                    AssetType.RETIREMENT_OTHER,
                ]:
                    # Retirement can be used for reserves, closing with conditions
                    total_eligible_reserves += analyzed.eligible_amount
                    # For closing, need evidence of ability to withdraw
                    if asset.get("can_withdraw"):
                        total_eligible_closing += analyzed.eligible_amount
                elif analyzed.asset_type == AssetType.GIFT:
                    total_eligible_closing += analyzed.eligible_amount
                    # Gift cannot be used for reserves

            # Collect large deposits
            all_large_deposits.extend(analyzed.large_deposits)

            # Collect issues/warnings
            all_issues.extend(analyzed.issues)
            all_warnings.extend(analyzed.warnings)

            # Generate conditions
            if analyzed.status == AssetStatus.NEEDS_DOCUMENTATION:
                conditions_needed.append({
                    "type": "prior_to_docs",
                    "category": "assets",
                    "title": f"Asset Documentation - {analyzed.institution}",
                    "description": f"Provide 2 months complete bank statements for {analyzed.institution} account ending in {analyzed.account_last_4}",
                    "guideline": analyzed.guideline_reference,
                })
            elif analyzed.status == AssetStatus.NEEDS_SOURCING:
                conditions_needed.append({
                    "type": "prior_to_docs",
                    "category": "assets",
                    "title": f"Large Deposit Sourcing - {analyzed.institution}",
                    "description": f"Provide documentation sourcing large deposits in {analyzed.institution} account ending in {analyzed.account_last_4}",
                    "guideline": "Fannie Mae B3-4.2-02",
                })

        # Calculate funds to close
        down_payment = funds_needed.get("down_payment", Decimal("0"))
        closing_costs = funds_needed.get("closing_costs", Decimal("0"))
        prepaids = funds_needed.get("prepaids", Decimal("0"))
        total_needed = down_payment + closing_costs + prepaids

        # Calculate reserve requirement
        reserves_required = self._calculate_reserves_required(
            property_type, monthly_pitia, dti_ratio
        )

        # Check sufficiency
        funds_after_closing = total_eligible_closing - total_needed
        is_sufficient = (
            total_eligible_closing >= total_needed and
            total_eligible_reserves >= reserves_required
        )

        shortfall = max(Decimal("0"), total_needed - total_eligible_closing)

        # Collect unsourced large deposits
        unsourced_deposits = [
            d for d in all_large_deposits
            if not d.is_sourced
        ]

        if unsourced_deposits:
            all_issues.append(
                f"{len(unsourced_deposits)} large deposit(s) require sourcing documentation"
            )

        return AssetResult(
            total_liquid_assets=total_liquid,
            total_eligible_for_closing=total_eligible_closing,
            total_eligible_for_reserves=total_eligible_reserves,
            asset_items=analyzed_assets,
            funds_to_close={
                "down_payment": down_payment,
                "closing_costs": closing_costs,
                "prepaids": prepaids,
                "total_needed": total_needed,
                "total_available": total_eligible_closing,
                "surplus_deficit": total_eligible_closing - total_needed,
            },
            reserves_available={
                "months_required": reserves_required / monthly_pitia if monthly_pitia > 0 else 0,
                "amount_required": reserves_required,
                "amount_available": total_eligible_reserves,
                "meets_requirement": total_eligible_reserves >= reserves_required,
            },
            is_sufficient=is_sufficient,
            shortfall_amount=shortfall,
            issues=all_issues,
            warnings=all_warnings,
            conditions_needed=conditions_needed,
            large_deposits_unsourced=unsourced_deposits,
        )

    def _analyze_asset(self, asset: Dict[str, Any]) -> AssetItem:
        """Analyze a single asset account."""
        asset_type_str = asset.get("type", "checking").lower()
        asset_type_map = {
            "checking": AssetType.CHECKING,
            "savings": AssetType.SAVINGS,
            "money_market": AssetType.MONEY_MARKET,
            "cd": AssetType.CD,
            "certificate_of_deposit": AssetType.CD,
            "stocks": AssetType.STOCKS,
            "bonds": AssetType.BONDS,
            "mutual_funds": AssetType.MUTUAL_FUNDS,
            "401k": AssetType.RETIREMENT_401K,
            "ira": AssetType.RETIREMENT_IRA,
            "retirement": AssetType.RETIREMENT_OTHER,
            "gift": AssetType.GIFT,
            "grant": AssetType.GRANT,
        }
        asset_type = asset_type_map.get(asset_type_str, AssetType.OTHER)

        institution = asset.get("institution", "Unknown")
        account_last_4 = asset.get("account_last_4", "XXXX")
        current_balance = Decimal(str(asset.get("balance", 0)))

        issues = []
        warnings = []
        doc_status = "complete"
        status = AssetStatus.VERIFIED
        large_deposits = []

        # Handle retirement accounts - apply discount
        if asset_type in [
            AssetType.RETIREMENT_401K, AssetType.RETIREMENT_IRA,
            AssetType.RETIREMENT_OTHER
        ]:
            vested = Decimal(str(asset.get("vested_balance", current_balance)))
            eligible = (vested * self.retirement_discount).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # Check if withdrawal is allowed
            if not asset.get("can_withdraw"):
                warnings.append(
                    "Retirement funds require evidence of ability to withdraw "
                    "(hardship, loan provision, or age eligibility)"
                )

            return AssetItem(
                asset_type=asset_type,
                institution=institution,
                account_last_4=account_last_4,
                current_balance=current_balance,
                eligible_amount=eligible,
                status=status,
                documentation_status=doc_status,
                issues=issues,
                warnings=warnings,
                guideline_reference="Fannie Mae B3-4.3-01",
                vested_amount=vested,
                discount_rate=self.retirement_discount,
                notes=f"Discounted to {float(self.retirement_discount)*100:.0f}% of vested",
            )

        # Handle gift funds
        if asset_type == AssetType.GIFT:
            return self._analyze_gift(asset)

        # Check for bank statement documentation
        if not asset.get("has_statements"):
            issues.append("2 months complete bank statements required")
            doc_status = "missing"
            status = AssetStatus.NEEDS_DOCUMENTATION

        # Check for large deposits
        if asset.get("deposits"):
            large_deposits = self._check_large_deposits(
                asset.get("deposits", []),
                institution,
            )
            if any(not d.is_sourced for d in large_deposits):
                status = AssetStatus.NEEDS_SOURCING

        # Statement seasoning check
        statement_date = asset.get("statement_date")
        if statement_date:
            days_old = (date.today() - datetime.strptime(statement_date, "%Y-%m-%d").date()).days
            if days_old > 120:
                issues.append("Bank statements are more than 120 days old - need updated statements")
                doc_status = "partial"
                status = AssetStatus.NEEDS_DOCUMENTATION
            elif days_old > 60:
                warnings.append("Bank statements are over 60 days old - may need update before closing")

        return AssetItem(
            asset_type=asset_type,
            institution=institution,
            account_last_4=account_last_4,
            current_balance=current_balance,
            eligible_amount=current_balance,
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            large_deposits=large_deposits,
            guideline_reference="Fannie Mae B3-4.2-01",
        )

    def _analyze_gift(self, gift: Dict[str, Any]) -> AssetItem:
        """
        Analyze gift funds.

        Per Fannie Mae B3-4.3-04:
        - Gift must be from eligible donor (family member, fiance, domestic partner)
        - Signed gift letter required
        - Donor bank statements showing ability to give
        - Evidence of transfer (wire, check, deposit)
        - No repayment expected
        """
        donor = gift.get("donor_name", "Donor")
        relationship = gift.get("donor_relationship", "Unknown")
        amount = Decimal(str(gift.get("amount", 0)))

        issues = []
        warnings = []
        doc_status = "complete"
        status = AssetStatus.VERIFIED

        # Check eligible donor relationship
        eligible_relationships = [
            "parent", "grandparent", "sibling", "child", "aunt", "uncle",
            "spouse", "fiance", "domestic_partner", "family"
        ]
        if relationship.lower() not in eligible_relationships:
            issues.append(
                f"Donor relationship '{relationship}' may not be eligible. "
                "Gift must be from family member, fiance, or domestic partner."
            )
            status = AssetStatus.NEEDS_DOCUMENTATION

        # Check gift letter
        if not gift.get("has_gift_letter"):
            issues.append("Signed gift letter required")
            doc_status = "partial"
            status = AssetStatus.NEEDS_DOCUMENTATION

        # Check donor bank statements
        if not gift.get("has_donor_statements"):
            issues.append("Donor bank statements showing ability to gift required")
            doc_status = "partial"
            status = AssetStatus.NEEDS_DOCUMENTATION

        # Check transfer documentation
        if not gift.get("has_transfer_proof"):
            issues.append("Proof of gift transfer (wire confirmation, check copy, deposit slip) required")
            doc_status = "partial"
            status = AssetStatus.NEEDS_DOCUMENTATION

        # Check if deposited
        if not gift.get("is_deposited"):
            warnings.append("Gift funds should be deposited to borrower account before closing")

        return AssetItem(
            asset_type=AssetType.GIFT,
            institution=f"Gift from {donor}",
            account_last_4="GIFT",
            current_balance=amount,
            eligible_amount=amount if status == AssetStatus.VERIFIED else Decimal("0"),
            status=status,
            documentation_status=doc_status,
            issues=issues,
            warnings=warnings,
            guideline_reference="Fannie Mae B3-4.3-04",
            notes=f"Relationship: {relationship}",
        )

    def _check_large_deposits(
        self,
        deposits: List[Dict[str, Any]],
        account_name: str,
    ) -> List[LargeDeposit]:
        """
        Check for large deposits requiring sourcing.

        Per Fannie Mae B3-4.2-02:
        - Large deposit = exceeds 50% of qualifying monthly income
        - Must identify source and paper trail
        - Acceptable sources: payroll, sale of asset, tax refund, gift, etc.
        """
        large_deposits = []
        threshold = self.monthly_income * Decimal("0.50")

        # FHA uses $200 threshold if income-based is lower
        if self.loan_program == "fha":
            threshold = max(threshold, Decimal("200"))

        for dep in deposits:
            amount = Decimal(str(dep.get("amount", 0)))
            if amount > threshold:
                large_deposit = LargeDeposit(
                    date=dep.get("date", "Unknown"),
                    amount=amount,
                    description=dep.get("description", "Deposit"),
                    account=account_name,
                    is_sourced=dep.get("is_sourced", False),
                    source_explanation=dep.get("source_explanation", ""),
                    source_documentation=dep.get("source_documentation", ""),
                    is_acceptable=dep.get("is_acceptable", False),
                )
                large_deposits.append(large_deposit)

        return large_deposits

    def _calculate_reserves_required(
        self,
        property_type: str,
        monthly_pitia: Decimal,
        dti_ratio: Decimal,
    ) -> Decimal:
        """Calculate reserve requirement based on property type and DTI."""
        reserves = self.RESERVE_REQUIREMENTS.get(self.loan_program, {})

        # Get months required
        months_required = 0

        if self.loan_program == "conventional":
            months_required = reserves.get(property_type, 0)
            # Add reserves if high DTI
            if dti_ratio > Decimal("45") and months_required < 6:
                months_required = reserves.get("with_high_dti", months_required)
        elif self.loan_program == "fha":
            if property_type in ["primary_3_4_unit", "3_4_unit"]:
                months_required = 3
        # VA and USDA typically don't require reserves

        return monthly_pitia * months_required

    def calculate_funds_to_close(
        self,
        purchase_price: Decimal,
        loan_amount: Decimal,
        estimated_closing_costs: Decimal,
        estimated_prepaids: Decimal,
        seller_credits: Decimal = Decimal("0"),
        lender_credits: Decimal = Decimal("0"),
    ) -> Dict[str, Decimal]:
        """
        Calculate total funds needed to close.

        Returns breakdown of:
        - Down payment
        - Closing costs (net of credits)
        - Prepaids
        - Total cash to close
        """
        down_payment = purchase_price - loan_amount

        net_closing_costs = max(
            Decimal("0"),
            estimated_closing_costs - seller_credits - lender_credits
        )

        total_needed = down_payment + net_closing_costs + estimated_prepaids

        return {
            "purchase_price": purchase_price,
            "loan_amount": loan_amount,
            "down_payment": down_payment,
            "down_payment_percent": (down_payment / purchase_price * 100).quantize(Decimal("0.01")),
            "gross_closing_costs": estimated_closing_costs,
            "seller_credits": seller_credits,
            "lender_credits": lender_credits,
            "net_closing_costs": net_closing_costs,
            "prepaids_escrows": estimated_prepaids,
            "total_cash_to_close": total_needed,
        }
