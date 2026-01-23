"""
Credit Analyzer Module

Analyzes credit history and calculates debt-to-income ratios per agency guidelines.
Key capabilities:
- Credit score analysis and program eligibility
- Tradeline evaluation
- Derogatory credit event handling (BK, FC, SS)
- DTI calculation with proper debt inclusion
- Credit history pattern detection

References:
- Fannie Mae Selling Guide B3-5 (Credit Assessment)
- Freddie Mac Guide Chapter 5500 (Credit Evaluation)
- FHA 4000.1 II.A.5 (Credit Requirements)
- VA Pamphlet 26-7 Chapter 4 (Credit Standards)
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import logging

logger = logging.getLogger(__name__)


class CreditEventType(str, Enum):
    """Types of derogatory credit events."""
    BANKRUPTCY_CH7 = "bankruptcy_chapter_7"
    BANKRUPTCY_CH13 = "bankruptcy_chapter_13"
    FORECLOSURE = "foreclosure"
    SHORT_SALE = "short_sale"
    DEED_IN_LIEU = "deed_in_lieu"
    CHARGE_OFF = "charge_off"
    COLLECTION = "collection"
    JUDGMENT = "judgment"
    TAX_LIEN = "tax_lien"
    LATE_PAYMENT = "late_payment"


class TradelineStatus(str, Enum):
    """Status of credit tradeline."""
    CURRENT = "current"
    LATE_30 = "30_days_late"
    LATE_60 = "60_days_late"
    LATE_90 = "90_days_late"
    LATE_120_PLUS = "120_plus_days_late"
    COLLECTION = "collection"
    CHARGE_OFF = "charge_off"
    CLOSED = "closed"


@dataclass
class CreditEvent:
    """Derogatory credit event with waiting period analysis."""
    event_type: CreditEventType
    event_date: str
    discharge_date: Optional[str]
    months_since_event: int
    waiting_period_months: Dict[str, int]  # By loan program
    is_eligible: Dict[str, bool]  # By loan program
    description: str
    documentation_needed: List[str]


@dataclass
class Tradeline:
    """Individual credit tradeline."""
    creditor: str
    account_type: str  # installment, revolving, mortgage, etc.
    high_credit: Decimal
    current_balance: Decimal
    monthly_payment: Decimal
    status: TradelineStatus
    months_remaining: Optional[int]
    late_history: Dict[str, int]  # 30, 60, 90, 120 counts
    is_excluded_from_dti: bool = False
    exclusion_reason: str = ""


@dataclass
class CreditResult:
    """Complete credit analysis result."""
    representative_score: int
    middle_score: int
    scores_by_bureau: Dict[str, int]
    program_eligibility: Dict[str, Dict[str, Any]]
    credit_events: List[CreditEvent]
    tradelines: List[Tradeline]
    total_monthly_debt: Decimal
    housing_expense: Decimal
    dti_front_end: Decimal
    dti_back_end: Decimal
    credit_grade: str  # A, B, C, D, F
    issues: List[str]
    warnings: List[str]
    conditions_needed: List[Dict[str, Any]]
    credit_summary: Dict[str, Any]


class CreditAnalyzer:
    """
    Analyzes credit and calculates DTI per agency guidelines.

    Key principles:
    1. Use representative credit score (middle score or lower of 2)
    2. Apply waiting periods for derogatory events
    3. Include all applicable debts in DTI
    4. Account for debts with < 10 months remaining
    5. Consider authorized user accounts appropriately
    """

    # Minimum credit scores by program
    MIN_CREDIT_SCORES = {
        "conventional": {
            "standard": 620,
            "high_balance": 680,
            "investment": 640,
            "manual_uw": 620,
        },
        "fha": {
            "3.5_down": 580,
            "10_down": 500,
            "streamline": 500,  # No minimum for streamline
        },
        "va": {
            "standard": 620,  # Lender overlay
            "manual_uw": 580,
        },
        "usda": {
            "gus": 640,
            "manual_uw": 640,
        },
    }

    # Maximum DTI by program
    MAX_DTI = {
        "conventional": {
            "standard": Decimal("45"),
            "with_aus_approval": Decimal("50"),
            "manual_uw": Decimal("36"),
        },
        "fha": {
            "standard": Decimal("43"),
            "with_compensating": Decimal("56.99"),
            "total_scorecard": Decimal("56.99"),
        },
        "va": {
            "standard": Decimal("41"),
            "with_residual": Decimal("50"),
        },
        "usda": {
            "standard": Decimal("41"),
            "with_gus": Decimal("44"),
        },
    }

    # Waiting periods for credit events (in months)
    WAITING_PERIODS = {
        CreditEventType.BANKRUPTCY_CH7: {
            "conventional": 48,  # 4 years
            "fha": 24,  # 2 years
            "va": 24,
            "usda": 36,
        },
        CreditEventType.BANKRUPTCY_CH13: {
            "conventional": 24,  # 2 years from discharge
            "fha": 12,  # 1 year with court approval
            "va": 12,
            "usda": 12,
        },
        CreditEventType.FORECLOSURE: {
            "conventional": 84,  # 7 years
            "fha": 36,  # 3 years
            "va": 24,
            "usda": 36,
        },
        CreditEventType.SHORT_SALE: {
            "conventional": 48,  # 4 years (2 with extenuating)
            "fha": 36,
            "va": 24,
            "usda": 36,
        },
        CreditEventType.DEED_IN_LIEU: {
            "conventional": 48,
            "fha": 36,
            "va": 24,
            "usda": 36,
        },
    }

    def __init__(self, loan_program: str = "conventional"):
        """Initialize analyzer."""
        self.loan_program = loan_program.lower()

    def analyze_credit(
        self,
        credit_data: Dict[str, Any],
        housing_expense: Decimal,
        monthly_income: Decimal,
    ) -> CreditResult:
        """
        Perform complete credit analysis.

        Args:
            credit_data: Credit report data including scores, tradelines, events
            housing_expense: Proposed monthly housing payment (PITIA)
            monthly_income: Qualifying monthly income

        Returns:
            CreditResult with complete analysis
        """
        # Extract and analyze scores
        scores = self._analyze_scores(credit_data.get("scores", {}))

        # Analyze credit events
        events = self._analyze_credit_events(credit_data.get("events", []))

        # Analyze tradelines and calculate DTI components
        tradelines, total_debt = self._analyze_tradelines(
            credit_data.get("tradelines", [])
        )

        # Calculate DTI ratios
        dti_front = Decimal("0")
        dti_back = Decimal("0")
        if monthly_income > 0:
            dti_front = (housing_expense / monthly_income * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            dti_back = ((housing_expense + total_debt) / monthly_income * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Determine program eligibility
        eligibility = self._determine_eligibility(
            scores["representative"],
            dti_back,
            events,
        )

        # Assess credit grade
        credit_grade = self._calculate_credit_grade(
            scores["representative"],
            tradelines,
            events,
        )

        # Compile issues, warnings, conditions
        issues = []
        warnings = []
        conditions = []

        # Score-related issues
        min_score = self.MIN_CREDIT_SCORES.get(self.loan_program, {}).get("standard", 620)
        if scores["representative"] < min_score:
            issues.append(
                f"Credit score {scores['representative']} is below {self.loan_program} "
                f"minimum of {min_score}"
            )

        # DTI issues
        max_dti = self.MAX_DTI.get(self.loan_program, {}).get("standard", Decimal("43"))
        if dti_back > max_dti:
            issues.append(
                f"DTI of {dti_back}% exceeds {self.loan_program} maximum of {max_dti}%"
            )
        elif dti_back > Decimal("43"):
            warnings.append(
                f"DTI of {dti_back}% may require compensating factors or AUS approval"
            )

        # Credit event issues
        for event in events:
            if not event.is_eligible.get(self.loan_program, False):
                issues.append(
                    f"{event.event_type.value}: {event.months_since_event} months since event, "
                    f"waiting period is {event.waiting_period_months.get(self.loan_program, 'N/A')} months"
                )
                conditions.extend([
                    {
                        "type": "prior_to_approval",
                        "category": "credit",
                        "title": f"Credit Event Documentation - {event.event_type.value}",
                        "description": doc,
                        "guideline": "Fannie Mae B3-5.3",
                    }
                    for doc in event.documentation_needed
                ])

        # Late payment warnings
        recent_lates = sum(
            tl.late_history.get("12_months", 0)
            for tl in tradelines
        )
        if recent_lates > 0:
            warnings.append(
                f"{recent_lates} late payment(s) in past 12 months - letter of explanation required"
            )
            conditions.append({
                "type": "prior_to_approval",
                "category": "credit",
                "title": "Letter of Explanation - Late Payments",
                "description": "Provide signed LOE explaining recent late payments",
                "guideline": "Fannie Mae B3-5.3-09",
            })

        return CreditResult(
            representative_score=scores["representative"],
            middle_score=scores["middle"],
            scores_by_bureau=scores["by_bureau"],
            program_eligibility=eligibility,
            credit_events=events,
            tradelines=tradelines,
            total_monthly_debt=total_debt,
            housing_expense=housing_expense,
            dti_front_end=dti_front,
            dti_back_end=dti_back,
            credit_grade=credit_grade,
            issues=issues,
            warnings=warnings,
            conditions_needed=conditions,
            credit_summary={
                "score": scores["representative"],
                "dti": float(dti_back),
                "tradeline_count": len(tradelines),
                "derogatory_count": len(events),
                "grade": credit_grade,
            }
        )

    def _analyze_scores(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze credit scores and determine representative score.

        Per Fannie Mae B3-5.1-01:
        - Use middle score if 3 bureaus
        - Use lower score if 2 bureaus
        - For multiple borrowers, use lower of representative scores
        """
        equifax = scores_data.get("equifax", 0)
        experian = scores_data.get("experian", 0)
        transunion = scores_data.get("transunion", 0)

        valid_scores = [s for s in [equifax, experian, transunion] if s > 0]

        if len(valid_scores) == 3:
            valid_scores.sort()
            middle = valid_scores[1]
            representative = middle
        elif len(valid_scores) == 2:
            representative = min(valid_scores)
            middle = representative
        elif len(valid_scores) == 1:
            representative = valid_scores[0]
            middle = representative
        else:
            representative = 0
            middle = 0

        return {
            "representative": representative,
            "middle": middle,
            "by_bureau": {
                "equifax": equifax,
                "experian": experian,
                "transunion": transunion,
            },
            "valid_bureaus": len(valid_scores),
        }

    def _analyze_credit_events(
        self,
        events_data: List[Dict[str, Any]],
    ) -> List[CreditEvent]:
        """Analyze derogatory credit events and waiting periods."""
        events = []
        today = date.today()

        for event_data in events_data:
            event_type_str = event_data.get("type", "").lower().replace(" ", "_")
            try:
                event_type = CreditEventType(event_type_str)
            except ValueError:
                continue

            event_date_str = event_data.get("event_date", "")
            discharge_date_str = event_data.get("discharge_date")

            # Calculate months since event
            try:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                months_since = (today.year - event_date.year) * 12 + (today.month - event_date.month)
            except (ValueError, TypeError):
                months_since = 0

            # Get waiting periods for all programs
            waiting_periods = self.WAITING_PERIODS.get(event_type, {})

            # Determine eligibility for each program
            is_eligible = {}
            for program, wait_months in waiting_periods.items():
                is_eligible[program] = months_since >= wait_months

            # Documentation needed
            docs_needed = []
            if event_type in [CreditEventType.BANKRUPTCY_CH7, CreditEventType.BANKRUPTCY_CH13]:
                docs_needed = [
                    "Bankruptcy discharge papers",
                    "Bankruptcy schedules",
                    "Letter of explanation",
                ]
            elif event_type == CreditEventType.FORECLOSURE:
                docs_needed = [
                    "Final foreclosure/transfer documents",
                    "Letter of explanation",
                ]
            elif event_type in [CreditEventType.SHORT_SALE, CreditEventType.DEED_IN_LIEU]:
                docs_needed = [
                    "Settlement statement/HUD-1",
                    "Letter of explanation",
                ]

            events.append(CreditEvent(
                event_type=event_type,
                event_date=event_date_str,
                discharge_date=discharge_date_str,
                months_since_event=months_since,
                waiting_period_months=waiting_periods,
                is_eligible=is_eligible,
                description=event_data.get("description", ""),
                documentation_needed=docs_needed,
            ))

        return events

    def _analyze_tradelines(
        self,
        tradelines_data: List[Dict[str, Any]],
    ) -> Tuple[List[Tradeline], Decimal]:
        """
        Analyze credit tradelines and calculate total monthly debt.

        Per Fannie Mae B3-6-01:
        - Include all installment debts
        - Include minimum payment on revolving
        - May exclude debts with < 10 months remaining
        - Include alimony, child support
        - Include negative rental cash flow
        """
        tradelines = []
        total_monthly = Decimal("0")

        for tl_data in tradelines_data:
            creditor = tl_data.get("creditor", "Unknown")
            account_type = tl_data.get("account_type", "installment").lower()
            high_credit = Decimal(str(tl_data.get("high_credit", 0)))
            balance = Decimal(str(tl_data.get("balance", 0)))
            payment = Decimal(str(tl_data.get("payment", 0)))
            months_remaining = tl_data.get("months_remaining")

            # Determine status
            status_str = tl_data.get("status", "current").lower()
            status_map = {
                "current": TradelineStatus.CURRENT,
                "30": TradelineStatus.LATE_30,
                "60": TradelineStatus.LATE_60,
                "90": TradelineStatus.LATE_90,
                "120": TradelineStatus.LATE_120_PLUS,
                "collection": TradelineStatus.COLLECTION,
                "charge_off": TradelineStatus.CHARGE_OFF,
                "closed": TradelineStatus.CLOSED,
            }
            status = status_map.get(status_str, TradelineStatus.CURRENT)

            # Late history
            late_history = {
                "30": tl_data.get("late_30_count", 0),
                "60": tl_data.get("late_60_count", 0),
                "90": tl_data.get("late_90_count", 0),
                "120": tl_data.get("late_120_count", 0),
                "12_months": tl_data.get("lates_12_months", 0),
            }

            # Determine if excluded from DTI
            is_excluded = False
            exclusion_reason = ""

            # Can exclude installment debts with < 10 months remaining
            if account_type == "installment" and months_remaining and months_remaining < 10:
                is_excluded = True
                exclusion_reason = f"Less than 10 payments remaining ({months_remaining} months)"

            # Authorized user accounts - can exclude if primary payer is on loan
            if tl_data.get("is_authorized_user") and tl_data.get("primary_payer_on_loan"):
                is_excluded = True
                exclusion_reason = "Authorized user - primary payer is on loan"

            # Closed accounts with zero balance
            if status == TradelineStatus.CLOSED and balance == 0:
                is_excluded = True
                exclusion_reason = "Closed with zero balance"

            tradeline = Tradeline(
                creditor=creditor,
                account_type=account_type,
                high_credit=high_credit,
                current_balance=balance,
                monthly_payment=payment,
                status=status,
                months_remaining=months_remaining,
                late_history=late_history,
                is_excluded_from_dti=is_excluded,
                exclusion_reason=exclusion_reason,
            )
            tradelines.append(tradeline)

            # Add to total debt if not excluded
            if not is_excluded and payment > 0:
                total_monthly += payment

        return tradelines, total_monthly

    def _determine_eligibility(
        self,
        credit_score: int,
        dti: Decimal,
        events: List[CreditEvent],
    ) -> Dict[str, Dict[str, Any]]:
        """Determine eligibility for each loan program."""
        eligibility = {}

        for program in ["conventional", "fha", "va", "usda"]:
            min_scores = self.MIN_CREDIT_SCORES.get(program, {})
            max_dtis = self.MAX_DTI.get(program, {})

            # Check score
            min_score = min_scores.get("standard", 620)
            score_eligible = credit_score >= min_score

            # Check DTI
            max_dti = max_dtis.get("with_aus_approval", max_dtis.get("standard", Decimal("43")))
            dti_eligible = dti <= max_dti

            # Check events
            events_eligible = all(
                event.is_eligible.get(program, False)
                for event in events
            )

            eligibility[program] = {
                "score_eligible": score_eligible,
                "score_required": min_score,
                "dti_eligible": dti_eligible,
                "max_dti": float(max_dti),
                "events_eligible": events_eligible,
                "overall_eligible": score_eligible and dti_eligible and events_eligible,
            }

        return eligibility

    def _calculate_credit_grade(
        self,
        credit_score: int,
        tradelines: List[Tradeline],
        events: List[CreditEvent],
    ) -> str:
        """
        Calculate overall credit grade.

        A: 740+ score, no derogatory, no recent lates
        B: 700-739 score, minor derogs, few lates
        C: 660-699 score, some derogs
        D: 620-659 score, multiple derogs
        F: <620 score or major unresolved derogs
        """
        # Start with score-based grade
        if credit_score >= 740:
            grade_points = 4
        elif credit_score >= 700:
            grade_points = 3
        elif credit_score >= 660:
            grade_points = 2
        elif credit_score >= 620:
            grade_points = 1
        else:
            return "F"

        # Deduct for derogatory events
        for event in events:
            if event.event_type in [CreditEventType.BANKRUPTCY_CH7, CreditEventType.FORECLOSURE]:
                grade_points -= 2
            elif event.event_type in [CreditEventType.BANKRUPTCY_CH13, CreditEventType.SHORT_SALE]:
                grade_points -= 1
            elif event.event_type in [CreditEventType.CHARGE_OFF, CreditEventType.COLLECTION]:
                grade_points -= 0.5

        # Deduct for recent lates
        recent_lates = sum(tl.late_history.get("12_months", 0) for tl in tradelines)
        if recent_lates >= 3:
            grade_points -= 1
        elif recent_lates >= 1:
            grade_points -= 0.5

        # Convert points to grade
        if grade_points >= 3.5:
            return "A"
        elif grade_points >= 2.5:
            return "B"
        elif grade_points >= 1.5:
            return "C"
        elif grade_points >= 0.5:
            return "D"
        else:
            return "F"

    def calculate_dti(
        self,
        monthly_income: Decimal,
        housing_payment: Decimal,
        other_debts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate front-end and back-end DTI ratios.

        Args:
            monthly_income: Total qualifying monthly income
            housing_payment: Proposed PITIA (Principal, Interest, Taxes, Insurance, HOA)
            other_debts: List of monthly debt payments

        Returns:
            Dict with DTI calculations
        """
        total_other_debt = sum(
            Decimal(str(d.get("payment", 0)))
            for d in other_debts
            if not d.get("is_excluded", False)
        )

        if monthly_income <= 0:
            return {
                "front_end_dti": Decimal("0"),
                "back_end_dti": Decimal("0"),
                "housing_payment": housing_payment,
                "other_debt": total_other_debt,
                "total_debt": housing_payment + total_other_debt,
                "monthly_income": monthly_income,
                "error": "Income must be greater than zero",
            }

        front_end = (housing_payment / monthly_income * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        back_end = ((housing_payment + total_other_debt) / monthly_income * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "front_end_dti": front_end,
            "back_end_dti": back_end,
            "housing_payment": housing_payment,
            "other_debt": total_other_debt,
            "total_debt": housing_payment + total_other_debt,
            "monthly_income": monthly_income,
        }
