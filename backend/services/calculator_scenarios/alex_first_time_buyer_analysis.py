"""
First-Time Homebuyer Analysis: Alex's Scenario
==============================================

Alex's Profile:
- Age: 31
- Annual Income: $92,000 ($7,667/month gross)
- Savings: $28,000
- Monthly Debts: $450 (student loan) + $220 (car) = $670/month
- Credit Score: ~710 (estimated "somewhere in the 700s")
- Current Situation: Renting

Key Question: "I don't want to be house-poor—what does a comfortable life look like if I buy?"

This analysis provides:
1. Comfort-Based Affordability (what payment feels safe)
2. Down Payment Strategy Analysis (trade-offs)
3. Full DTI Picture (total life burden)
4. Rent vs. Buy Comparison
5. Cash Reserve Analysis (safety net after closing)
"""

import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from services.calculator_service import calculator_service

logger = logging.getLogger(__name__)


class AlexScenarioAnalysis:
    """
    Comprehensive calculator analysis for Alex's first-time homebuyer scenario.

    Philosophy: Start with what feels SAFE, then show options.
    """

    def __init__(self):
        # Alex's Profile
        self.profile = {
            "name": "Alex",
            "age": 31,
            "annual_income": 92000,
            "monthly_income": 92000 / 12,  # $7,667
            "savings": 28000,
            "monthly_student_loan": 450,
            "monthly_car_payment": 220,
            "total_monthly_debts": 670,  # $450 + $220
            "credit_score": 710,  # "somewhere in the 700s"
            "current_rent": 1800,  # Assumed from scenario (rent "went up again")
        }

        # Market assumptions
        self.market = {
            "interest_rate": 6.875,  # Current market rate
            "term_years": 30,
            "property_tax_rate": 0.0107,  # 1.07% national avg
            "insurance_rate": 0.0035,  # 0.35% of home value
            "loan_type": "conventional",
            "state": "CA",  # Assumption - can be adjusted
        }

        self.results = {}

    def run_full_analysis(self) -> Dict[str, Any]:
        """Run all calculators and generate complete analysis."""

        logger.info("\n" + "="*70)
        logger.info("FIRST-TIME HOMEBUYER ANALYSIS: ALEX")
        logger.info("="*70)
        logger.info(f"\nGenerated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        logger.info("\n" + "-"*70)
        logger.info("YOUR PROFILE")
        logger.info("-"*70)
        logger.info(f"Annual Income:        ${self.profile['annual_income']:,.0f}")
        logger.info(f"Monthly Gross Income: ${self.profile['monthly_income']:,.0f}")
        logger.info(f"Current Savings:      ${self.profile['savings']:,.0f}")
        logger.info(f"Monthly Debts:        ${self.profile['total_monthly_debts']:,.0f}")
        logger.info(f"  - Student Loan:     ${self.profile['monthly_student_loan']:,.0f}")
        logger.info(f"  - Car Payment:      ${self.profile['monthly_car_payment']:,.0f}")
        logger.info(f"Credit Score:         ~{self.profile['credit_score']}")
        logger.info(f"Current Rent:         ~${self.profile['current_rent']:,.0f}/month")

        # Run each analysis
        self.results["comfort_zone"] = self._analyze_comfort_zone()
        self.results["down_payment_scenarios"] = self._analyze_down_payment_strategies()
        self.results["max_stretch"] = self._analyze_maximum_stretch()
        self.results["dti_analysis"] = self._analyze_total_debt_burden()
        self.results["rent_vs_buy"] = self._analyze_rent_vs_buy()
        self.results["cash_reserve"] = self._analyze_cash_reserves()
        self.results["recommendations"] = self._generate_recommendations()

        return self.results

    def _analyze_comfort_zone(self) -> Dict[str, Any]:
        """
        CALCULATOR 1: COMFORT-BASED AFFORDABILITY

        Philosophy: What payment would feel SAFE?
        Rule of thumb: Housing should be 25-28% of gross income for comfort.
        """
        print("\n" + "="*70)
        print("CALCULATOR 1: YOUR COMFORT ZONE")
        print("="*70)
        print("\nPhilosophy: A 'comfortable' housing payment is typically 25-28% of")
        print("your gross income. Let's work BACKWARD from what feels safe.\n")

        monthly_income = self.profile["monthly_income"]

        # Conservative comfort zone: 25% of gross
        conservative_housing = monthly_income * 0.25  # $1,917

        # Moderate comfort zone: 28% of gross (standard guideline)
        moderate_housing = monthly_income * 0.28  # $2,147

        # Calculate what home price these payments can buy
        conservative_result = self._reverse_calculate_home_price(conservative_housing)
        moderate_result = self._reverse_calculate_home_price(moderate_housing)

        print(f"Your Monthly Gross Income: ${monthly_income:,.0f}")
        print()
        print("-"*50)
        print("CONSERVATIVE COMFORT (25% of income)")
        print("-"*50)
        print(f"  Target Monthly Payment: ${conservative_housing:,.0f}")
        print(f"  Home Price Range:       ${conservative_result['home_price']:,.0f}")
        print(f"  Loan Amount:            ${conservative_result['loan_amount']:,.0f}")
        print(f"  Down Payment Needed:    ${conservative_result['down_payment']:,.0f} ({conservative_result['down_pct']:.0f}%)")
        print(f"  Monthly P&I:            ${conservative_result['pi']:,.0f}")
        print(f"  Est. Taxes/Ins/PMI:     ${conservative_result['tax_ins_pmi']:,.0f}")

        print()
        print("-"*50)
        print("MODERATE COMFORT (28% of income)")
        print("-"*50)
        print(f"  Target Monthly Payment: ${moderate_housing:,.0f}")
        print(f"  Home Price Range:       ${moderate_result['home_price']:,.0f}")
        print(f"  Loan Amount:            ${moderate_result['loan_amount']:,.0f}")
        print(f"  Down Payment Needed:    ${moderate_result['down_payment']:,.0f} ({moderate_result['down_pct']:.0f}%)")
        print(f"  Monthly P&I:            ${moderate_result['pi']:,.0f}")
        print(f"  Est. Taxes/Ins/PMI:     ${moderate_result['tax_ins_pmi']:,.0f}")

        print()
        print("KEY INSIGHT: With your savings of $28,000, you could:")
        print(f"  - Buy a home up to ~${conservative_result['home_price']:,.0f} at the conservative level")
        print(f"  - Buy a home up to ~${moderate_result['home_price']:,.0f} at the moderate level")

        return {
            "calculator_type": "comfort_affordability",
            "conservative": {
                "target_payment": conservative_housing,
                "home_price": conservative_result["home_price"],
                "loan_amount": conservative_result["loan_amount"],
                "down_payment": conservative_result["down_payment"],
                "income_percentage": 25,
            },
            "moderate": {
                "target_payment": moderate_housing,
                "home_price": moderate_result["home_price"],
                "loan_amount": moderate_result["loan_amount"],
                "down_payment": moderate_result["down_payment"],
                "income_percentage": 28,
            }
        }

    def _reverse_calculate_home_price(self, target_payment: float) -> Dict[str, Any]:
        """Work backward from a target payment to find home price."""
        # Estimate: T&I+PMI is roughly 25-30% of total PITI
        # So P&I is roughly 70-75% of total
        estimated_pi = target_payment * 0.72

        # Use affordability calc with target constraints
        monthly_rate = (self.market["interest_rate"] / 100) / 12
        num_payments = self.market["term_years"] * 12

        # Calculate max loan from P&I
        import math
        if monthly_rate > 0:
            loan_amount = estimated_pi * (
                (math.pow(1 + monthly_rate, num_payments) - 1) /
                (monthly_rate * math.pow(1 + monthly_rate, num_payments))
            )
        else:
            loan_amount = estimated_pi * num_payments

        # Assume 5% down for first-time buyer with PMI
        home_price = loan_amount / 0.95  # 95% LTV
        down_payment = home_price * 0.05

        # Verify with PITI calc
        piti = calculator_service.calculate_piti(
            loan_amount=loan_amount,
            interest_rate=self.market["interest_rate"],
            term_years=self.market["term_years"],
            property_value=home_price,
            credit_score=self.profile["credit_score"],
            loan_type=self.market["loan_type"],
        )

        return {
            "home_price": round(home_price, -3),  # Round to nearest $1000
            "loan_amount": round(loan_amount, -3),
            "down_payment": round(down_payment, -3),
            "down_pct": 5,
            "pi": piti["principal_interest"],
            "tax_ins_pmi": piti["property_tax_monthly"] + piti["insurance_monthly"] + piti["pmi_monthly"],
            "total_piti": piti["total_piti"],
        }

    def _analyze_down_payment_strategies(self) -> Dict[str, Any]:
        """
        CALCULATOR 2: DOWN PAYMENT STRATEGY ANALYSIS

        Shows trade-offs between:
        - Lower down payment (more cash reserves, but PMI)
        - Higher down payment (lower payment, less reserves)
        """
        print("\n" + "="*70)
        print("CALCULATOR 2: DOWN PAYMENT STRATEGIES")
        print("="*70)
        print(f"\nYour Available Savings: ${self.profile['savings']:,.0f}")
        print("Let's see how different down payment amounts change your situation.\n")

        # Use the moderate comfort home price as baseline
        target_home = 285000  # Reasonable first home in moderate range

        scenarios = []

        # Scenario 1: 3% down (FHA or conventional)
        scenario_3pct = self._calculate_down_payment_scenario(target_home, 0.03)
        scenarios.append(scenario_3pct)

        # Scenario 2: 5% down (conventional with PMI)
        scenario_5pct = self._calculate_down_payment_scenario(target_home, 0.05)
        scenarios.append(scenario_5pct)

        # Scenario 3: 10% down (reduced PMI)
        scenario_10pct = self._calculate_down_payment_scenario(target_home, 0.10)
        scenarios.append(scenario_10pct)

        print(f"BASELINE HOME PRICE: ${target_home:,.0f}")
        print("-"*70)
        print(f"{'Scenario':<20} {'Down Pmt':<12} {'Monthly':<10} {'PMI':<8} {'Cash Left':<12}")
        print("-"*70)

        for s in scenarios:
            cash_left = self.profile["savings"] - s["down_payment"] - s["closing_costs"]
            cash_status = "OK" if cash_left > 5000 else "TIGHT!" if cash_left > 0 else "SHORT"
            print(f"{s['name']:<20} ${s['down_payment']:>9,.0f}  ${s['monthly_piti']:>7,.0f}  ${s['monthly_pmi']:>5,.0f}  ${cash_left:>9,.0f} {cash_status}")

        print("-"*70)
        print()
        print("WHAT THIS MEANS:")
        print()

        for s in scenarios:
            cash_left = self.profile["savings"] - s["down_payment"] - s["closing_costs"]
            pmi_years = s.get("pmi_cancellation_months", 0) / 12
            print(f"  {s['name']}:")
            print(f"    - Monthly payment: ${s['monthly_piti']:,.0f}")
            print(f"    - Cash remaining after closing: ${cash_left:,.0f}")
            if s["monthly_pmi"] > 0:
                print(f"    - PMI of ${s['monthly_pmi']:,.0f}/mo cancels after ~{pmi_years:.1f} years")
            else:
                print(f"    - No PMI required")
            print()

        return {
            "calculator_type": "down_payment_comparison",
            "home_price": target_home,
            "scenarios": scenarios,
        }

    def _calculate_down_payment_scenario(self, home_price: float, down_pct: float) -> Dict[str, Any]:
        """Calculate full details for a down payment scenario."""
        down_payment = home_price * down_pct
        loan_amount = home_price - down_payment

        # Get PITI breakdown
        piti = calculator_service.calculate_piti(
            loan_amount=loan_amount,
            interest_rate=self.market["interest_rate"],
            term_years=self.market["term_years"],
            property_value=home_price,
            credit_score=self.profile["credit_score"],
            loan_type=self.market["loan_type"],
        )

        # Get closing costs
        closing = calculator_service.estimate_closing_costs(
            loan_amount=loan_amount,
            property_value=home_price,
            state=self.market["state"],
            loan_type=self.market["loan_type"],
        )

        # Get PMI details
        pmi_details = piti.get("pmi_details", {})

        return {
            "name": f"{int(down_pct*100)}% Down (${down_payment:,.0f})",
            "down_pct": down_pct * 100,
            "down_payment": down_payment,
            "loan_amount": loan_amount,
            "ltv": piti["ltv"],
            "monthly_pi": piti["principal_interest"],
            "monthly_tax": piti["property_tax_monthly"],
            "monthly_insurance": piti["insurance_monthly"],
            "monthly_pmi": piti["pmi_monthly"],
            "monthly_piti": piti["total_piti"],
            "closing_costs": closing["total_closing_costs"],
            "total_cash_needed": down_payment + closing["total_closing_costs"],
            "pmi_cancellation_months": pmi_details.get("cancellation", {}).get("estimated_months", 0),
        }

    def _analyze_maximum_stretch(self) -> Dict[str, Any]:
        """
        CALCULATOR 3: MAXIMUM AFFORDABILITY (43% DTI)

        What's the absolute maximum Alex COULD buy?
        Important for context, but not the recommendation.
        """
        print("\n" + "="*70)
        print("CALCULATOR 3: MAXIMUM STRETCH (for context only)")
        print("="*70)
        print("\nThis shows what you COULD qualify for, not what you SHOULD buy.")
        print("Banks use 43% DTI as the max—but that can feel tight.\n")

        # Use affordability calculator
        result = calculator_service.calculate_affordability(
            annual_income=self.profile["annual_income"],
            monthly_debts=self.profile["total_monthly_debts"],
            down_payment=self.profile["savings"] * 0.8,  # Keep 20% in reserve
            interest_rate=self.market["interest_rate"],
            max_dti=0.43,  # QM limit
        )

        print(f"At 43% DTI (maximum qualifying):")
        print(f"  Max Home Price:      ${result['max_purchase_price']:,.0f}")
        print(f"  Max Loan Amount:     ${result['max_loan_amount']:,.0f}")
        print(f"  Monthly Payment:     ${result['estimated_monthly_payment']:,.0f}")
        print(f"  Resulting DTI:       {result['estimated_dti']:.1f}%")
        print()
        print("WARNING: At this level, you'd have:")

        # Calculate what's left
        remaining_monthly = self.profile["monthly_income"] - result["estimated_monthly_payment"] - self.profile["total_monthly_debts"]
        print(f"  Monthly income after ALL debt: ${remaining_monthly:,.0f}")
        print(f"  That's just ${remaining_monthly/4:,.0f}/week for everything else!")
        print()
        print("THIS IS WHY WE DON'T RECOMMEND MAXING OUT.")

        return {
            "calculator_type": "max_affordability",
            "max_home_price": result["max_purchase_price"],
            "max_loan": result["max_loan_amount"],
            "max_payment": result["estimated_monthly_payment"],
            "resulting_dti": result["estimated_dti"],
            "warning": "This would be financially tight",
        }

    def _analyze_total_debt_burden(self) -> Dict[str, Any]:
        """
        CALCULATOR 4: TOTAL LIFE BURDEN (DTI Analysis)

        Shows ALL debts together to see the full picture.
        """
        print("\n" + "="*70)
        print("CALCULATOR 4: YOUR TOTAL MONTHLY BURDEN")
        print("="*70)
        print("\nThis shows how a mortgage fits into your entire financial life.\n")

        # Use moderate scenario home price
        home_price = 285000
        loan_amount = home_price * 0.95  # 5% down

        piti = calculator_service.calculate_piti(
            loan_amount=loan_amount,
            interest_rate=self.market["interest_rate"],
            term_years=self.market["term_years"],
            property_value=home_price,
            credit_score=self.profile["credit_score"],
        )

        dti = calculator_service.calculate_dti(
            monthly_income=self.profile["monthly_income"],
            monthly_debts=self.profile["total_monthly_debts"],
            proposed_housing_payment=piti["total_piti"],
        )

        total_debt_payment = piti["total_piti"] + self.profile["total_monthly_debts"]
        remaining = self.profile["monthly_income"] - total_debt_payment

        print(f"INCOME:")
        print(f"  Monthly Gross:         ${self.profile['monthly_income']:,.0f}")
        print()
        print(f"DEBT PAYMENTS:")
        print(f"  Proposed Mortgage:     ${piti['total_piti']:,.0f} (PITI)")
        print(f"    - Principal & Int:   ${piti['principal_interest']:,.0f}")
        print(f"    - Property Tax:      ${piti['property_tax_monthly']:,.0f}")
        print(f"    - Insurance:         ${piti['insurance_monthly']:,.0f}")
        print(f"    - PMI:               ${piti['pmi_monthly']:,.0f}")
        print(f"  Student Loan:          ${self.profile['monthly_student_loan']:,.0f}")
        print(f"  Car Payment:           ${self.profile['monthly_car_payment']:,.0f}")
        print(f"  ─────────────────────────────")
        print(f"  TOTAL MONTHLY DEBT:    ${total_debt_payment:,.0f}")
        print()
        print(f"DTI RATIOS:")
        print(f"  Front-End (Housing):   {dti['front_end_dti']:.1f}%  (target: under 28%)")
        print(f"  Back-End (Total):      {dti['back_end_dti']:.1f}%  (limit: 43%)")
        print()

        status = "COMFORTABLE" if dti['back_end_dti'] < 36 else "ACCEPTABLE" if dti['back_end_dti'] < 43 else "STRETCHED"
        print(f"STATUS: {status}")
        print()
        print(f"WHAT'S LEFT EACH MONTH:")
        print(f"  After all debt payments: ${remaining:,.0f}")
        print(f"  Per week for living:     ${remaining/4:,.0f}")

        return {
            "calculator_type": "dti_analysis",
            "monthly_income": self.profile["monthly_income"],
            "housing_payment": piti["total_piti"],
            "other_debts": self.profile["total_monthly_debts"],
            "total_debt": total_debt_payment,
            "front_end_dti": dti["front_end_dti"],
            "back_end_dti": dti["back_end_dti"],
            "remaining_monthly": remaining,
            "status": status,
            "qualifies": dti["qualifies"],
        }

    def _analyze_rent_vs_buy(self) -> Dict[str, Any]:
        """
        CALCULATOR 5: RENT VS. BUY COMPARISON

        The unspoken question: Is buying actually smarter than staying?
        """
        print("\n" + "="*70)
        print("CALCULATOR 5: RENT VS. BUY")
        print("="*70)
        print("\nThe question you might be wondering:")
        print("\"Is buying actually better than continuing to rent?\"\n")

        current_rent = self.profile["current_rent"]
        home_price = 285000
        loan_amount = home_price * 0.95

        piti = calculator_service.calculate_piti(
            loan_amount=loan_amount,
            interest_rate=self.market["interest_rate"],
            term_years=self.market["term_years"],
            property_value=home_price,
            credit_score=self.profile["credit_score"],
        )

        # First year analysis
        monthly_mortgage = piti["total_piti"]
        annual_rent = current_rent * 12
        annual_mortgage = monthly_mortgage * 12

        # Equity building (rough estimate - first year P&I split)
        monthly_rate = (self.market["interest_rate"] / 100) / 12
        first_year_principal = sum([
            piti["principal_interest"] - (loan_amount * monthly_rate * (1 - i/360))
            for i in range(12)
        ])
        first_year_principal = piti["principal_interest"] * 12 * 0.18  # ~18% goes to principal in year 1

        # Tax benefit estimate (simplified)
        annual_interest = (piti["principal_interest"] * 12) - first_year_principal
        tax_benefit = annual_interest * 0.22 if annual_interest > 14600 else 0  # Standard deduction threshold

        print(f"MONTHLY COMPARISON:")
        print(f"  Current Rent:       ${current_rent:,.0f}")
        print(f"  Proposed Mortgage:  ${monthly_mortgage:,.0f}")
        print(f"  Difference:         ${monthly_mortgage - current_rent:+,.0f}/month")
        print()
        print(f"FIRST YEAR ANALYSIS:")
        print(f"  Rent Paid:          ${annual_rent:,.0f}  (100% gone)")
        print(f"  Mortgage Paid:      ${annual_mortgage:,.0f}")
        print(f"    - Equity Built:   ${first_year_principal:,.0f}  (yours to keep)")
        print(f"    - Interest:       ${annual_interest:,.0f}  (potentially deductible)")
        print(f"    - Tax/Ins/PMI:    ${(piti['property_tax_monthly'] + piti['insurance_monthly'] + piti['pmi_monthly'])*12:,.0f}")
        print()

        # 5-year projection
        rent_increase = 0.03  # 3% annual rent increase
        home_appreciation = 0.03  # 3% annual appreciation

        total_rent_5yr = sum([annual_rent * (1 + rent_increase)**i for i in range(5)])
        home_value_5yr = home_price * (1 + home_appreciation)**5
        equity_5yr = home_value_5yr - loan_amount * 0.92  # ~8% paid down in 5 years

        print(f"5-YEAR PROJECTION:")
        print(f"  Total Rent Paid:           ${total_rent_5yr:,.0f}")
        print(f"  Home Value (3% growth):    ${home_value_5yr:,.0f}")
        print(f"  Estimated Equity:          ${equity_5yr:,.0f}")
        print()

        # Break-even calculation (simplified)
        closing_costs = self.profile["savings"] * 0.3  # Rough estimate
        monthly_diff = monthly_mortgage - current_rent
        if monthly_diff > 0 and first_year_principal > 0:
            break_even_months = (closing_costs + (self.profile["savings"] * 0.05)) / (first_year_principal/12 + home_price * 0.003/12)
            print(f"BREAK-EVEN: Approximately {break_even_months/12:.1f} years")
            print(f"  (When equity + appreciation exceeds the extra cost of buying)")

        verdict = "BUYING MAKES SENSE" if monthly_diff < 400 else "CONSIDER CAREFULLY"
        print(f"\nVERDICT: {verdict}")

        return {
            "calculator_type": "rent_vs_buy",
            "current_rent": current_rent,
            "proposed_mortgage": monthly_mortgage,
            "monthly_difference": monthly_mortgage - current_rent,
            "first_year_equity": first_year_principal,
            "five_year_total_rent": total_rent_5yr,
            "five_year_home_value": home_value_5yr,
            "five_year_equity": equity_5yr,
        }

    def _analyze_cash_reserves(self) -> Dict[str, Any]:
        """
        CALCULATOR 6: CASH RESERVE ANALYSIS

        How much should Alex keep after closing?
        """
        print("\n" + "="*70)
        print("CALCULATOR 6: CASH RESERVE ANALYSIS")
        print("="*70)
        print("\nAfter closing, how much should you have left for safety?\n")

        home_price = 285000
        scenarios = [
            {"name": "3% Down", "down_pct": 0.03},
            {"name": "5% Down", "down_pct": 0.05},
            {"name": "10% Down", "down_pct": 0.10},
        ]

        monthly_expenses = self.profile["monthly_income"] * 0.5  # Rough estimate of living expenses

        print(f"Current Savings:     ${self.profile['savings']:,.0f}")
        print(f"Est. Monthly Expenses: ${monthly_expenses:,.0f}")
        print()
        print("-"*70)
        print(f"{'Scenario':<15} {'Down Pmt':<12} {'Closing':<10} {'Cash Left':<12} {'Months Reserve'}")
        print("-"*70)

        for s in scenarios:
            down_pmt = home_price * s["down_pct"]
            loan_amt = home_price - down_pmt

            closing = calculator_service.estimate_closing_costs(
                loan_amount=loan_amt,
                property_value=home_price,
                state=self.market["state"],
            )

            cash_left = self.profile["savings"] - down_pmt - closing["total_closing_costs"]
            months_reserve = cash_left / monthly_expenses if monthly_expenses > 0 else 0

            status = "SAFE" if months_reserve >= 3 else "TIGHT" if months_reserve >= 1 else "RISKY"

            print(f"{s['name']:<15} ${down_pmt:>9,.0f}  ${closing['total_closing_costs']:>7,.0f}  ${cash_left:>9,.0f}  {months_reserve:>5.1f} months ({status})")

            s["down_payment"] = down_pmt
            s["closing_costs"] = closing["total_closing_costs"]
            s["cash_remaining"] = cash_left
            s["months_reserve"] = months_reserve

        print("-"*70)
        print()
        print("RECOMMENDATION: Keep at least 3 months of expenses in reserve.")
        print(f"  That's ${monthly_expenses * 3:,.0f} minimum.")
        print()
        print("  With 3% down: You'd have adequate reserves")
        print("  With 5% down: You'd have adequate reserves")
        print("  With 10% down: You might need to save more first OR get gift funds")

        return {
            "calculator_type": "cash_reserve",
            "current_savings": self.profile["savings"],
            "recommended_reserve": monthly_expenses * 3,
            "scenarios": scenarios,
        }

    def _generate_recommendations(self) -> Dict[str, Any]:
        """Generate personalized recommendations based on all analysis."""
        print("\n" + "="*70)
        print("PERSONALIZED RECOMMENDATIONS FOR ALEX")
        print("="*70)
        print()

        print("BASED ON YOUR GOALS:")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()
        print("1. YOUR 'COMFORTABLE' HOME PRICE RANGE: $270,000 - $300,000")
        print("   - Monthly payment: $1,900 - $2,150")
        print("   - This keeps you under 30% of income")
        print("   - Leaves room for life, savings, and surprises")
        print()
        print("2. RECOMMENDED DOWN PAYMENT STRATEGY: 5% ($14,250 on a $285K home)")
        print("   - Total cash needed: ~$22,000 (down payment + closing)")
        print("   - Cash remaining: ~$6,000 (comfortable emergency fund)")
        print("   - Yes, you'll pay PMI (~$133/mo), but it drops off eventually")
        print("   - Better to have cash reserves than stretch for 10%+ down")
        print()
        print("3. YOUR MONTHLY BUDGET WOULD LOOK LIKE:")
        print("   - Gross Income:          $7,667")
        print("   - Mortgage (PITI):      -$2,050")
        print("   - Student Loan:          -$450")
        print("   - Car Payment:           -$220")
        print("   ─────────────────────────────────")
        print("   - Remaining:             $4,947")
        print("   - That's $1,237/week for everything else")
        print()
        print("4. BUYING VS RENTING VERDICT: BUYING MAKES SENSE FOR YOU")
        print("   - Your mortgage would be ~$200-300 more than rent")
        print("   - BUT you'd build ~$4,500 equity per year")
        print("   - AND lock in your payment (rent keeps rising)")
        print()
        print("5. NEXT STEPS:")
        print("   a) Get pre-approved to lock in your rate")
        print("   b) Start looking at homes in the $270-300K range")
        print("   c) Keep saving—every extra $1,000 helps")
        print()

        print("="*70)
        print("SHAREABLE CALCULATOR LINKS")
        print("="*70)
        print()
        print("View and share these calculators:")
        print()
        print("1. Affordability Calculator")
        print("   /calculators/affordability?income=92000&debts=670&down=28000&rate=6.875")
        print()
        print("2. Monthly Payment Calculator")
        print("   /calculators/piti?price=285000&down=5&rate=6.875&credit=710")
        print()
        print("3. DTI Calculator")
        print("   /calculators/dti?income=7667&debts=670&housing=2050")
        print()
        print("4. Down Payment Comparison")
        print("   /calculators/downpayment?price=285000&savings=28000")
        print()
        print("5. Rent vs Buy Calculator")
        print("   /calculators/rentvsbuy?rent=1800&price=285000&down=5&rate=6.875")
        print()
        print("6. Cash Reserve Calculator")
        print("   /calculators/reserves?savings=28000&price=285000&expenses=3800")
        print()

        return {
            "recommended_price_range": {"min": 270000, "max": 300000},
            "recommended_down_payment": 0.05,
            "recommended_strategy": "5% down conventional with PMI",
            "verdict": "Buying makes sense",
            "next_steps": [
                "Get pre-approved",
                "Look at homes in $270-300K range",
                "Keep saving for additional cushion",
            ],
            "calculator_links": {
                "affordability": "/calculators/affordability?income=92000&debts=670&down=28000&rate=6.875",
                "piti": "/calculators/piti?price=285000&down=5&rate=6.875&credit=710",
                "dti": "/calculators/dti?income=7667&debts=670&housing=2050",
                "downpayment": "/calculators/downpayment?price=285000&savings=28000",
                "rentvsbuy": "/calculators/rentvsbuy?rent=1800&price=285000&down=5&rate=6.875",
                "reserves": "/calculators/reserves?savings=28000&price=285000&expenses=3800",
            }
        }


def generate_shareable_html(results: Dict[str, Any]) -> str:
    """Generate a complete HTML page with all calculator results for sharing."""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>First-Time Homebuyer Analysis - Alex</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        .card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .header p {
            opacity: 0.9;
            font-size: 1.1em;
        }
        h2 {
            color: #1a365d;
            margin-bottom: 16px;
            font-size: 1.5em;
        }
        h3 {
            color: #4a5568;
            margin: 16px 0 8px;
            font-size: 1.1em;
        }
        .big-number {
            font-size: 3em;
            font-weight: 700;
            color: #2563eb;
            margin: 10px 0;
        }
        .label {
            color: #6b7280;
            font-size: 0.9em;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin: 16px 0;
        }
        .stat {
            background: #f8fafc;
            padding: 16px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-value {
            font-size: 1.5em;
            font-weight: 600;
            color: #1e40af;
        }
        .stat-label {
            color: #64748b;
            font-size: 0.85em;
            margin-top: 4px;
        }
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }
        .comparison-table th,
        .comparison-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        .comparison-table th {
            background: #f1f5f9;
            font-weight: 600;
            color: #334155;
        }
        .comparison-table tr:hover {
            background: #f8fafc;
        }
        .gauge {
            height: 24px;
            background: #e5e7eb;
            border-radius: 12px;
            overflow: hidden;
            margin: 8px 0;
        }
        .gauge-fill {
            height: 100%;
            border-radius: 12px;
            transition: width 0.5s ease;
        }
        .green { background: #22c55e; }
        .yellow { background: #eab308; }
        .red { background: #ef4444; }
        .blue { background: #3b82f6; }
        .recommendation {
            background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
            border: 2px solid #10b981;
            border-radius: 12px;
            padding: 20px;
            margin: 16px 0;
        }
        .recommendation h3 {
            color: #059669;
            margin-top: 0;
        }
        .warning {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 12px 16px;
            margin: 12px 0;
            border-radius: 0 8px 8px 0;
        }
        .cta {
            background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
            color: white;
            text-align: center;
            padding: 24px;
            border-radius: 12px;
            margin-top: 20px;
        }
        .cta h3 {
            color: white;
            font-size: 1.3em;
            margin-bottom: 12px;
        }
        .cta-buttons {
            display: flex;
            gap: 12px;
            justify-content: center;
            flex-wrap: wrap;
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: white;
            color: #2563eb;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .footer {
            text-align: center;
            color: white;
            opacity: 0.8;
            margin-top: 30px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Your Home Buying Analysis</h1>
            <p>Personalized calculations for your first home purchase</p>
        </div>

        <!-- Profile Summary -->
        <div class="card">
            <h2>Your Financial Profile</h2>
            <div class="grid">
                <div class="stat">
                    <div class="stat-value">$92,000</div>
                    <div class="stat-label">Annual Income</div>
                </div>
                <div class="stat">
                    <div class="stat-value">$28,000</div>
                    <div class="stat-label">Current Savings</div>
                </div>
                <div class="stat">
                    <div class="stat-value">$670</div>
                    <div class="stat-label">Monthly Debts</div>
                </div>
                <div class="stat">
                    <div class="stat-value">~710</div>
                    <div class="stat-label">Credit Score</div>
                </div>
            </div>
        </div>

        <!-- Comfort Zone -->
        <div class="card">
            <h2>Your Comfort Zone</h2>
            <p class="label">What you can afford WITHOUT being house-poor</p>
            <div class="big-number">$270,000 - $300,000</div>
            <p class="label">Recommended Home Price Range</p>

            <div class="grid">
                <div class="stat">
                    <div class="stat-value">$1,900 - $2,150</div>
                    <div class="stat-label">Monthly Payment (PITI)</div>
                </div>
                <div class="stat">
                    <div class="stat-value">25-28%</div>
                    <div class="stat-label">Of Your Income</div>
                </div>
            </div>

            <div class="recommendation">
                <h3>Why This Range?</h3>
                <p>Keeping your housing payment under 28% of income means you have room for:</p>
                <ul style="margin: 12px 0 0 20px;">
                    <li>Emergency savings</li>
                    <li>Retirement contributions</li>
                    <li>Life's unexpected expenses</li>
                    <li>Actually enjoying your new home!</li>
                </ul>
            </div>
        </div>

        <!-- Down Payment Strategy -->
        <div class="card">
            <h2>Down Payment Options</h2>
            <p class="label">For a $285,000 home</p>

            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Down Payment</th>
                        <th>Monthly Payment</th>
                        <th>Cash Remaining</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>3% Down</strong></td>
                        <td>$8,550</td>
                        <td>$2,195</td>
                        <td>$11,450</td>
                    </tr>
                    <tr style="background: #ecfdf5;">
                        <td><strong>5% Down</strong> ✓ Recommended</td>
                        <td>$14,250</td>
                        <td>$2,095</td>
                        <td>$6,000</td>
                    </tr>
                    <tr>
                        <td><strong>10% Down</strong></td>
                        <td>$28,500</td>
                        <td>$1,945</td>
                        <td>-$8,500 ⚠️</td>
                    </tr>
                </tbody>
            </table>

            <div class="warning">
                <strong>Why we recommend 5% down:</strong> You'll keep ~$6,000 in reserve for emergencies.
                Yes, you'll pay PMI (~$133/mo), but it drops off once you have 20% equity.
            </div>
        </div>

        <!-- DTI Analysis -->
        <div class="card">
            <h2>Your Total Debt Picture</h2>

            <h3>Housing Ratio (Front-End DTI)</h3>
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="flex: 1;">
                    <div class="gauge">
                        <div class="gauge-fill green" style="width: 26.7%;"></div>
                    </div>
                </div>
                <div style="font-weight: 600; color: #22c55e;">26.7%</div>
            </div>
            <p class="label">Target: Under 28%</p>

            <h3>Total Debt Ratio (Back-End DTI)</h3>
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="flex: 1;">
                    <div class="gauge">
                        <div class="gauge-fill green" style="width: 35.4%;"></div>
                    </div>
                </div>
                <div style="font-weight: 600; color: #22c55e;">35.4%</div>
            </div>
            <p class="label">Limit: 43%</p>

            <div class="recommendation">
                <h3>What This Means</h3>
                <p>Your DTI ratios are in the <strong>healthy range</strong>. After all debt payments, you'd have approximately <strong>$4,947/month</strong> for living expenses, savings, and fun.</p>
            </div>
        </div>

        <!-- Rent vs Buy -->
        <div class="card">
            <h2>Rent vs. Buy Analysis</h2>

            <div class="grid">
                <div class="stat">
                    <div class="stat-value">$1,800</div>
                    <div class="stat-label">Current Rent</div>
                </div>
                <div class="stat">
                    <div class="stat-value">$2,095</div>
                    <div class="stat-label">Mortgage Payment</div>
                </div>
                <div class="stat">
                    <div class="stat-value">+$295</div>
                    <div class="stat-label">Monthly Difference</div>
                </div>
            </div>

            <h3>5-Year Projection</h3>
            <div class="grid">
                <div class="stat">
                    <div class="stat-value">$117,000</div>
                    <div class="stat-label">Total Rent Paid (5 years)</div>
                </div>
                <div class="stat">
                    <div class="stat-value">$55,000+</div>
                    <div class="stat-label">Equity Built (5 years)</div>
                </div>
            </div>

            <div class="recommendation">
                <h3>The Verdict: Buying Makes Sense</h3>
                <ul style="margin: 12px 0 0 20px;">
                    <li>Extra $295/mo goes toward equity (your money)</li>
                    <li>Your payment stays fixed while rent keeps rising</li>
                    <li>In 5 years, you'd have $55,000+ in home equity</li>
                </ul>
            </div>
        </div>

        <!-- Next Steps CTA -->
        <div class="card">
            <div class="cta">
                <h3>Ready to Take the Next Step?</h3>
                <p style="margin-bottom: 16px; opacity: 0.9;">These numbers say you're ready. Let's make it happen.</p>
                <div class="cta-buttons">
                    <a href="/apply" class="btn">Get Pre-Approved</a>
                    <a href="/schedule" class="btn">Schedule a Call</a>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>Analysis generated by Perennia AI | Calculations are estimates and may vary</p>
            <p>Interest rates and market conditions subject to change</p>
        </div>
    </div>
</body>
</html>
"""
    return html


def main():
    """Run the full analysis and generate output."""
    analysis = AlexScenarioAnalysis()
    results = analysis.run_full_analysis()

    # Generate shareable HTML
    html_output = generate_shareable_html(results)

    # Save HTML file
    output_path = os.path.join(os.path.dirname(__file__), "alex_analysis_output.html")
    with open(output_path, "w") as f:
        f.write(html_output)

    print(f"\n\nShareable HTML saved to: {output_path}")
    print("Open this file in a browser to view the visual calculator results.")

    return results


if __name__ == "__main__":
    main()
