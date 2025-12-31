"""
Comparison Enhancements Service

Provides advanced analysis features for loan comparisons:
- Prepayment/early payoff analysis
- Tax impact calculations
- Batch comparisons (3+ estimates)
- Shareable links
- Comparison history management
"""

import json
import logging
import secrets
import uuid
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class PrepaymentScenario(BaseModel):
    """A single prepayment scenario"""
    extra_monthly: float = 0
    extra_yearly: float = 0
    one_time: float = 0


class PrepaymentResult(BaseModel):
    """Result of prepayment analysis"""
    scenario: PrepaymentScenario
    original_term_months: int
    new_term_months: int
    months_saved: int
    years_saved: float
    original_total_interest: float
    new_total_interest: float
    interest_saved: float
    original_payoff_date: str
    new_payoff_date: str
    amortization_preview: List[Dict] = []


class TaxImpactRequest(BaseModel):
    """Request for tax impact analysis"""
    filing_status: str = "single"  # single, married_filing_jointly, married_filing_separately, head_of_household
    annual_income: float
    state_tax_rate: float = 0  # As percentage, e.g., 5.0 for 5%
    property_tax_annual: float = 0
    other_itemized_deductions: float = 0


class TaxImpactResult(BaseModel):
    """Result of tax impact analysis"""
    filing_status: str
    marginal_tax_rate: float
    state_tax_rate: float
    standard_deduction: float
    year_1_mortgage_interest: float
    year_1_property_tax: float
    year_1_total_itemized: float
    itemize_benefit: bool
    tax_benefit_amount: float
    effective_monthly_savings: float
    lifetime_tax_savings: float
    yearly_breakdown: List[Dict] = []


class BatchComparisonResult(BaseModel):
    """Result of comparing 3+ estimates"""
    estimates: List[Dict]
    rankings: List[Dict]
    winner_index: int
    winner_label: str
    summary: str
    savings_vs_worst: float


class ComparisonHistoryItem(BaseModel):
    """A single comparison history entry"""
    id: str
    title: Optional[str]
    created_at: str
    is_saved: bool
    winner: Optional[str]
    savings_amount: Optional[float]
    estimate_a_summary: Dict
    estimate_b_summary: Dict
    share_token: Optional[str]


# ============================================================================
# CONSTANTS
# ============================================================================

# 2024 Federal Tax Brackets (simplified)
TAX_BRACKETS_SINGLE = [
    (11600, 0.10),
    (47150, 0.12),
    (100525, 0.22),
    (191950, 0.24),
    (243725, 0.32),
    (609350, 0.35),
    (float('inf'), 0.37),
]

TAX_BRACKETS_MARRIED = [
    (23200, 0.10),
    (94300, 0.12),
    (201050, 0.22),
    (383900, 0.24),
    (487450, 0.32),
    (731200, 0.35),
    (float('inf'), 0.37),
]

STANDARD_DEDUCTIONS = {
    "single": 14600,
    "married_filing_jointly": 29200,
    "married_filing_separately": 14600,
    "head_of_household": 21900,
}

# SALT deduction cap
SALT_CAP = 10000


# ============================================================================
# COMPARISON ENHANCEMENTS SERVICE
# ============================================================================

class ComparisonEnhancementsService:
    """Service for enhanced comparison features"""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # PREPAYMENT ANALYSIS
    # ========================================================================

    def calculate_prepayment_analysis(
        self,
        loan_amount: float,
        interest_rate: float,  # Annual rate as percentage (e.g., 6.5)
        loan_term_months: int,
        scenarios: List[PrepaymentScenario],
        start_date: Optional[date] = None,
    ) -> List[PrepaymentResult]:
        """
        Calculate prepayment impact for multiple scenarios.

        Args:
            loan_amount: Principal loan amount
            interest_rate: Annual interest rate as percentage
            loan_term_months: Original loan term in months
            scenarios: List of prepayment scenarios to analyze
            start_date: Loan start date (defaults to today)

        Returns:
            List of PrepaymentResult for each scenario
        """
        if start_date is None:
            start_date = date.today()

        monthly_rate = (interest_rate / 100) / 12

        # Calculate original monthly payment (P&I)
        if monthly_rate > 0:
            original_payment = loan_amount * (
                monthly_rate * (1 + monthly_rate) ** loan_term_months
            ) / ((1 + monthly_rate) ** loan_term_months - 1)
        else:
            original_payment = loan_amount / loan_term_months

        # Calculate original total interest
        original_total_interest = (original_payment * loan_term_months) - loan_amount
        original_payoff_date = start_date + relativedelta(months=loan_term_months)

        results = []

        for scenario in scenarios:
            # Simulate amortization with extra payments
            balance = loan_amount
            total_interest = 0
            month = 0
            amortization = []

            while balance > 0 and month < loan_term_months * 2:  # Safety limit
                month += 1

                # Calculate interest for this month
                interest_payment = balance * monthly_rate
                principal_payment = original_payment - interest_payment

                # Add extra payments
                extra = scenario.extra_monthly
                if scenario.extra_yearly > 0 and month % 12 == 0:
                    extra += scenario.extra_yearly
                if scenario.one_time > 0 and month == 1:
                    extra += scenario.one_time

                principal_payment += extra

                # Don't overpay
                if principal_payment > balance:
                    principal_payment = balance

                total_interest += interest_payment
                balance -= principal_payment

                # Store first 12 and last 3 months for preview
                if month <= 12 or balance <= 0 or (balance > 0 and balance - principal_payment <= 0):
                    amortization.append({
                        "month": month,
                        "payment": round(original_payment + extra, 2),
                        "principal": round(principal_payment, 2),
                        "interest": round(interest_payment, 2),
                        "balance": round(max(0, balance), 2),
                    })

            new_payoff_date = start_date + relativedelta(months=month)
            months_saved = loan_term_months - month
            interest_saved = original_total_interest - total_interest

            results.append(PrepaymentResult(
                scenario=scenario,
                original_term_months=loan_term_months,
                new_term_months=month,
                months_saved=months_saved,
                years_saved=round(months_saved / 12, 1),
                original_total_interest=round(original_total_interest, 2),
                new_total_interest=round(total_interest, 2),
                interest_saved=round(interest_saved, 2),
                original_payoff_date=original_payoff_date.isoformat(),
                new_payoff_date=new_payoff_date.isoformat(),
                amortization_preview=amortization[:12],  # First year only
            ))

        return results

    # ========================================================================
    # TAX IMPACT ANALYSIS
    # ========================================================================

    def calculate_tax_impact(
        self,
        loan_amount: float,
        interest_rate: float,  # Annual rate as percentage
        loan_term_months: int,
        tax_request: TaxImpactRequest,
    ) -> TaxImpactResult:
        """
        Calculate tax impact of mortgage interest deduction.

        Considers:
        - Federal marginal tax rate
        - State tax rate
        - Standard deduction comparison
        - SALT cap ($10,000)
        - Property tax deduction
        """
        monthly_rate = (interest_rate / 100) / 12

        # Calculate monthly payment
        if monthly_rate > 0:
            monthly_payment = loan_amount * (
                monthly_rate * (1 + monthly_rate) ** loan_term_months
            ) / ((1 + monthly_rate) ** loan_term_months - 1)
        else:
            monthly_payment = loan_amount / loan_term_months

        # Get marginal tax rate
        brackets = TAX_BRACKETS_MARRIED if "married" in tax_request.filing_status else TAX_BRACKETS_SINGLE
        marginal_rate = 0.22  # Default
        for threshold, rate in brackets:
            if tax_request.annual_income <= threshold:
                marginal_rate = rate
                break

        standard_deduction = STANDARD_DEDUCTIONS.get(tax_request.filing_status, 14600)

        # Calculate yearly interest and breakdown
        balance = loan_amount
        yearly_breakdown = []
        lifetime_savings = 0

        for year in range(1, (loan_term_months // 12) + 1):
            year_interest = 0

            for month in range(12):
                if balance <= 0:
                    break
                interest = balance * monthly_rate
                principal = monthly_payment - interest
                year_interest += interest
                balance -= principal

            # Property tax (capped by SALT)
            property_tax_deductible = min(
                tax_request.property_tax_annual + tax_request.state_tax_rate * tax_request.annual_income / 100,
                SALT_CAP
            )

            # Total itemized deductions
            total_itemized = year_interest + property_tax_deductible + tax_request.other_itemized_deductions

            # Benefit of itemizing vs standard deduction
            itemize_benefit = total_itemized > standard_deduction
            tax_benefit = 0

            if itemize_benefit:
                # Benefit is the difference times marginal rate
                tax_benefit = (total_itemized - standard_deduction) * marginal_rate
                # Add state tax benefit
                tax_benefit += year_interest * (tax_request.state_tax_rate / 100)

            lifetime_savings += tax_benefit

            yearly_breakdown.append({
                "year": year,
                "mortgage_interest": round(year_interest, 2),
                "property_tax": round(tax_request.property_tax_annual, 2),
                "total_itemized": round(total_itemized, 2),
                "itemize_benefit": itemize_benefit,
                "tax_savings": round(tax_benefit, 2),
            })

            if balance <= 0:
                break

        # Year 1 summary
        year_1 = yearly_breakdown[0] if yearly_breakdown else {}

        return TaxImpactResult(
            filing_status=tax_request.filing_status,
            marginal_tax_rate=round(marginal_rate * 100, 1),
            state_tax_rate=tax_request.state_tax_rate,
            standard_deduction=standard_deduction,
            year_1_mortgage_interest=year_1.get("mortgage_interest", 0),
            year_1_property_tax=tax_request.property_tax_annual,
            year_1_total_itemized=year_1.get("total_itemized", 0),
            itemize_benefit=year_1.get("itemize_benefit", False),
            tax_benefit_amount=year_1.get("tax_savings", 0),
            effective_monthly_savings=round(year_1.get("tax_savings", 0) / 12, 2),
            lifetime_tax_savings=round(lifetime_savings, 2),
            yearly_breakdown=yearly_breakdown[:10],  # First 10 years
        )

    # ========================================================================
    # BATCH COMPARISON (3+ ESTIMATES)
    # ========================================================================

    def compare_batch_estimates(
        self,
        estimates: List[Dict],
        labels: Optional[List[str]] = None,
    ) -> BatchComparisonResult:
        """
        Compare 3 or more estimates and rank them.

        Args:
            estimates: List of parsed estimate dictionaries
            labels: Optional labels for each estimate (e.g., lender names)

        Returns:
            BatchComparisonResult with rankings and winner
        """
        if len(estimates) < 2:
            raise ValueError("At least 2 estimates required for comparison")

        if labels is None:
            labels = [chr(65 + i) for i in range(len(estimates))]  # A, B, C, ...

        # Score each estimate (lower is better)
        scored = []
        for i, estimate in enumerate(estimates):
            score = 0
            metrics = {}

            # Cash to close (weight: 35%)
            cash = estimate.get("cash_to_close") or 0
            metrics["cash_to_close"] = cash
            score += cash * 0.35

            # Total closing costs (weight: 25%)
            closing = estimate.get("total_closing_costs") or 0
            metrics["total_closing_costs"] = closing
            score += closing * 0.25

            # APR (weight: 25%) - normalize to dollar impact
            apr = estimate.get("apr") or estimate.get("interest_rate") or 0
            loan_amount = estimate.get("loan_amount") or 300000
            apr_impact = loan_amount * (apr / 100)  # Rough annual cost
            metrics["apr"] = apr
            score += apr_impact * 0.25

            # Monthly payment (weight: 15%)
            monthly = estimate.get("monthly_principal_and_interest") or 0
            monthly_impact = monthly * 360  # 30-year total
            metrics["monthly_pi"] = monthly
            score += monthly_impact * 0.00015  # Normalize

            scored.append({
                "index": i,
                "label": labels[i],
                "score": score,
                "estimate": estimate,
                "metrics": metrics,
            })

        # Sort by score (lower is better)
        scored.sort(key=lambda x: x["score"])

        # Build rankings
        rankings = []
        for rank, item in enumerate(scored, 1):
            rankings.append({
                "rank": rank,
                "label": item["label"],
                "index": item["index"],
                "cash_to_close": item["metrics"]["cash_to_close"],
                "total_closing_costs": item["metrics"]["total_closing_costs"],
                "apr": item["metrics"]["apr"],
                "monthly_pi": item["metrics"]["monthly_pi"],
                "score": round(item["score"], 2),
            })

        winner = scored[0]
        worst = scored[-1]

        # Calculate savings vs worst option
        savings = 0
        if winner["metrics"]["cash_to_close"] and worst["metrics"]["cash_to_close"]:
            savings = worst["metrics"]["cash_to_close"] - winner["metrics"]["cash_to_close"]

        # Generate summary
        summary_parts = [f"{winner['label']} is the best option"]
        if savings > 0:
            summary_parts.append(f"saving ${savings:,.0f} at closing compared to {worst['label']}")
        if winner["metrics"]["apr"] and worst["metrics"]["apr"]:
            apr_diff = worst["metrics"]["apr"] - winner["metrics"]["apr"]
            if apr_diff > 0:
                summary_parts.append(f"with a {apr_diff:.3f}% lower APR")

        return BatchComparisonResult(
            estimates=[{"label": labels[i], **est} for i, est in enumerate(estimates)],
            rankings=rankings,
            winner_index=winner["index"],
            winner_label=winner["label"],
            summary=", ".join(summary_parts) + ".",
            savings_vs_worst=savings,
        )

    # ========================================================================
    # COMPARISON HISTORY
    # ========================================================================

    def get_comparison_history(
        self,
        user_id: int,
        limit: int = 20,
        saved_only: bool = False,
    ) -> List[ComparisonHistoryItem]:
        """Get user's comparison history"""
        params = {"user_id": user_id, "limit": limit}

        saved_filter = "AND ec.is_saved = true" if saved_only else ""

        rows = self.db.execute(text(f"""
            SELECT
                ec.id, ec.title, ec.created_at, ec.is_saved,
                ec.winner, ec.savings_amount, ec.share_token,
                ea.parsed_json as estimate_a,
                eb.parsed_json as estimate_b
            FROM estimate_comparisons ec
            LEFT JOIN estimate_parse_cache ea ON ea.doc_hash = ec.estimate_a_hash
            LEFT JOIN estimate_parse_cache eb ON eb.doc_hash = ec.estimate_b_hash
            WHERE ec.user_id = :user_id {saved_filter}
            ORDER BY ec.created_at DESC
            LIMIT :limit
        """), params).fetchall()

        history = []
        for row in rows:
            estimate_a = row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
            estimate_b = row[8] if isinstance(row[8], dict) else json.loads(row[8]) if row[8] else {}

            history.append(ComparisonHistoryItem(
                id=str(row[0]),
                title=row[1],
                created_at=row[2].isoformat() if row[2] else "",
                is_saved=row[3] or False,
                winner=row[4],
                savings_amount=float(row[5]) if row[5] else None,
                share_token=row[6],
                estimate_a_summary={
                    "loan_amount": estimate_a.get("loan_amount"),
                    "interest_rate": estimate_a.get("interest_rate"),
                    "lender_name": estimate_a.get("lender_name"),
                },
                estimate_b_summary={
                    "loan_amount": estimate_b.get("loan_amount"),
                    "interest_rate": estimate_b.get("interest_rate"),
                    "lender_name": estimate_b.get("lender_name"),
                },
            ))

        return history

    def save_comparison(
        self,
        comparison_id: str,
        user_id: int,
        title: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Mark a comparison as saved/favorite"""
        try:
            self.db.execute(text("""
                UPDATE estimate_comparisons
                SET is_saved = true, title = COALESCE(:title, title), notes = COALESCE(:notes, notes)
                WHERE id = :id AND user_id = :user_id
            """), {
                "id": comparison_id,
                "user_id": user_id,
                "title": title,
                "notes": notes,
            })
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save comparison: {e}")
            self.db.rollback()
            return False

    def unsave_comparison(self, comparison_id: str, user_id: int) -> bool:
        """Remove saved status from comparison"""
        try:
            self.db.execute(text("""
                UPDATE estimate_comparisons
                SET is_saved = false
                WHERE id = :id AND user_id = :user_id
            """), {"id": comparison_id, "user_id": user_id})
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to unsave comparison: {e}")
            self.db.rollback()
            return False

    # ========================================================================
    # SHAREABLE LINKS
    # ========================================================================

    def generate_share_token(self) -> str:
        """Generate a unique share token"""
        return secrets.token_urlsafe(16)[:24]

    def create_share_link(
        self,
        comparison_id: str,
        user_id: int,
    ) -> Optional[str]:
        """Create a shareable link for a comparison"""
        try:
            # Check if already has a share token
            existing = self.db.execute(text("""
                SELECT share_token FROM estimate_comparisons
                WHERE id = :id AND user_id = :user_id
            """), {"id": comparison_id, "user_id": user_id}).fetchone()

            if existing and existing[0]:
                return existing[0]

            # Generate new token
            token = self.generate_share_token()

            self.db.execute(text("""
                UPDATE estimate_comparisons
                SET share_token = :token, is_public = true
                WHERE id = :id AND user_id = :user_id
            """), {"id": comparison_id, "user_id": user_id, "token": token})
            self.db.commit()

            return token
        except Exception as e:
            logger.error(f"Failed to create share link: {e}")
            self.db.rollback()
            return None

    def get_shared_comparison(self, share_token: str) -> Optional[Dict]:
        """Get a comparison by its share token (public access)"""
        try:
            row = self.db.execute(text("""
                SELECT
                    ec.id, ec.title, ec.winner, ec.winner_reason, ec.savings_amount,
                    ec.created_at, ec.view_count,
                    ea.parsed_json as estimate_a,
                    eb.parsed_json as estimate_b
                FROM estimate_comparisons ec
                LEFT JOIN estimate_parse_cache ea ON ea.doc_hash = ec.estimate_a_hash
                LEFT JOIN estimate_parse_cache eb ON eb.doc_hash = ec.estimate_b_hash
                WHERE ec.share_token = :token AND ec.is_public = true
            """), {"token": share_token}).fetchone()

            if not row:
                return None

            # Update view count
            self.db.execute(text("""
                UPDATE estimate_comparisons
                SET view_count = view_count + 1, last_viewed_at = NOW()
                WHERE share_token = :token
            """), {"token": share_token})
            self.db.commit()

            estimate_a = row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
            estimate_b = row[8] if isinstance(row[8], dict) else json.loads(row[8]) if row[8] else {}

            return {
                "id": str(row[0]),
                "title": row[1],
                "winner": row[2],
                "winner_reason": row[3],
                "savings_amount": float(row[4]) if row[4] else None,
                "created_at": row[5].isoformat() if row[5] else None,
                "view_count": row[6] or 0,
                "estimate_a": estimate_a,
                "estimate_b": estimate_b,
            }
        except Exception as e:
            logger.error(f"Failed to get shared comparison: {e}")
            return None

    def revoke_share_link(self, comparison_id: str, user_id: int) -> bool:
        """Revoke a share link"""
        try:
            self.db.execute(text("""
                UPDATE estimate_comparisons
                SET share_token = NULL, is_public = false
                WHERE id = :id AND user_id = :user_id
            """), {"id": comparison_id, "user_id": user_id})
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to revoke share link: {e}")
            self.db.rollback()
            return False

    # ========================================================================
    # BATCH COMPARISON PERSISTENCE
    # ========================================================================

    def save_batch_comparison(
        self,
        user_id: Optional[int],
        session_id: str,
        estimate_hashes: List[str],
        labels: List[str],
        winner_index: int,
        title: Optional[str] = None,
    ) -> str:
        """Save a batch comparison to the database"""
        batch_id = str(uuid.uuid4())

        try:
            self.db.execute(text("""
                INSERT INTO batch_comparisons (id, user_id, session_id, title)
                VALUES (:id, :user_id, :session_id, :title)
            """), {
                "id": batch_id,
                "user_id": user_id,
                "session_id": session_id,
                "title": title,
            })

            for i, (hash_val, label) in enumerate(zip(estimate_hashes, labels)):
                self.db.execute(text("""
                    INSERT INTO batch_comparison_estimates
                    (batch_comparison_id, estimate_hash, label, display_order, is_winner)
                    VALUES (:batch_id, :hash, :label, :order, :is_winner)
                """), {
                    "batch_id": batch_id,
                    "hash": hash_val,
                    "label": label,
                    "order": i,
                    "is_winner": i == winner_index,
                })

            self.db.commit()
            return batch_id
        except Exception as e:
            logger.error(f"Failed to save batch comparison: {e}")
            self.db.rollback()
            raise
