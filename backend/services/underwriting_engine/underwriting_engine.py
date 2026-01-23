"""
Main Underwriting Engine
Orchestrates all underwriting components for comprehensive loan analysis.
This is the primary interface for automated underwriting decisions.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging

from .income_calculator import IncomeCalculator, IncomeResult
from .asset_analyzer import AssetAnalyzer, AssetResult
from .credit_analyzer import CreditAnalyzer, CreditResult
from .condition_generator import (
    ConditionGenerator, ConditionClearing, Condition,
    ConditionType, ConditionStatus, generate_loan_conditions
)
from .eligibility_engine import (
    EligibilityEngine, EligibilityResult, LoanScenario,
    LoanPurpose, PropertyType, OccupancyType, Agency
)
from .loan_engineering import (
    LoanDataValidator, ValidationResult, validate_loan_file
)

logger = logging.getLogger(__name__)


class UnderwritingDecision(str, Enum):
    """Underwriting decision outcomes."""
    APPROVE = "approve"
    APPROVE_ELIGIBLE = "approve_eligible"  # Approved but conditions must be met
    REFER = "refer"  # Refer to human underwriter
    SUSPEND = "suspend"  # Missing information
    DENY = "deny"
    COUNTER = "counter"  # Approve at different terms


class RiskLevel(str, Enum):
    """Risk classification levels."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class UnderwritingFinding:
    """A finding from the underwriting analysis."""
    category: str
    severity: str  # info, warning, error, critical
    message: str
    details: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None


@dataclass
class UnderwritingResult:
    """Complete underwriting analysis result."""
    loan_id: str
    decision: UnderwritingDecision
    risk_level: RiskLevel
    confidence_score: float  # 0-100
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    # Component results
    income_result: Optional[Dict[str, Any]] = None
    asset_result: Optional[Dict[str, Any]] = None
    credit_result: Optional[Dict[str, Any]] = None
    eligibility_result: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None

    # Conditions
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    conditions_by_type: Dict[str, int] = field(default_factory=dict)

    # Findings
    findings: List[UnderwritingFinding] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)

    # Calculated metrics
    qualifying_income: Optional[float] = None
    calculated_dti: Optional[float] = None
    calculated_ltv: Optional[float] = None
    reserves_months: Optional[int] = None

    # Approval terms (if approved)
    approved_loan_amount: Optional[float] = None
    approved_rate: Optional[float] = None
    approved_program: Optional[str] = None

    # Denial reasons (if denied)
    denial_reasons: List[str] = field(default_factory=list)

    # Refer reasons (if referred)
    refer_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "loan_id": self.loan_id,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "confidence_score": self.confidence_score,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "qualifying_income": self.qualifying_income,
            "calculated_dti": self.calculated_dti,
            "calculated_ltv": self.calculated_ltv,
            "reserves_months": self.reserves_months,
            "conditions_count": len(self.conditions),
            "conditions_by_type": self.conditions_by_type,
            "critical_issues": self.critical_issues,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "recommendation": f.recommendation,
                }
                for f in self.findings
            ],
            "approved_program": self.approved_program,
            "denial_reasons": self.denial_reasons,
            "refer_reasons": self.refer_reasons,
            "income_summary": self._summarize_income(),
            "asset_summary": self._summarize_assets(),
            "credit_summary": self._summarize_credit(),
        }

    def _summarize_income(self) -> Optional[Dict[str, Any]]:
        """Summarize income analysis."""
        if not self.income_result:
            return None
        return {
            "total_qualifying": self.income_result.get("total_qualifying_income"),
            "sources": len(self.income_result.get("income_sources", [])),
            "stable": self.income_result.get("income_stability", {}).get("is_stable"),
        }

    def _summarize_assets(self) -> Optional[Dict[str, Any]]:
        """Summarize asset analysis."""
        if not self.asset_result:
            return None
        return {
            "total_verified": self.asset_result.get("total_verified_assets"),
            "funds_to_close_met": self.asset_result.get("funds_to_close_met"),
            "reserves_met": self.asset_result.get("reserves_met"),
        }

    def _summarize_credit(self) -> Optional[Dict[str, Any]]:
        """Summarize credit analysis."""
        if not self.credit_result:
            return None
        return {
            "score": self.credit_result.get("credit_score"),
            "dti": self.credit_result.get("dti_ratio"),
            "credit_grade": self.credit_result.get("credit_grade"),
        }


class UnderwritingEngine:
    """
    Main underwriting engine that orchestrates all analysis components.
    Provides comprehensive automated underwriting decisions.
    """

    # Decision thresholds
    APPROVE_THRESHOLD = 80
    REFER_THRESHOLD = 50

    # Risk weights for different factors
    RISK_WEIGHTS = {
        "credit_score": 0.25,
        "dti_ratio": 0.20,
        "ltv": 0.15,
        "income_stability": 0.15,
        "asset_adequacy": 0.10,
        "property_risk": 0.10,
        "compliance": 0.05,
    }

    def __init__(self):
        self.income_calculator = IncomeCalculator()
        self.asset_analyzer = AssetAnalyzer()
        self.credit_analyzer = CreditAnalyzer()
        self.eligibility_engine = EligibilityEngine()
        self.condition_generator = ConditionGenerator()
        self.condition_clearing = ConditionClearing()
        self.data_validator = LoanDataValidator()

    def analyze_loan(
        self,
        loan_data: Dict[str, Any],
        income_data: Optional[Dict[str, Any]] = None,
        asset_data: Optional[Dict[str, Any]] = None,
        credit_data: Optional[Dict[str, Any]] = None,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> UnderwritingResult:
        """
        Perform comprehensive loan underwriting analysis.

        Args:
            loan_data: Core loan information
            income_data: Income documentation data
            asset_data: Asset documentation data
            credit_data: Credit report data
            documents: List of available documents

        Returns:
            UnderwritingResult with decision and all analysis
        """
        loan_id = loan_data.get("loan_id") or loan_data.get("id") or "unknown"

        result = UnderwritingResult(
            loan_id=loan_id,
            decision=UnderwritingDecision.REFER,
            risk_level=RiskLevel.MODERATE,
            confidence_score=0,
        )

        try:
            # Step 1: Data validation
            validation = self._validate_data(loan_data)
            result.validation_result = validation

            if validation.get("is_valid") is False:
                if validation.get("counts", {}).get("errors", 0) > 5:
                    result.decision = UnderwritingDecision.SUSPEND
                    result.refer_reasons.append("Loan file has significant data issues")
                    result.findings.append(UnderwritingFinding(
                        category="data_quality",
                        severity="error",
                        message=f"Data validation failed with {validation.get('counts', {}).get('errors', 0)} errors",
                        recommendation="Review and correct data issues before proceeding",
                    ))

            # Step 2: Income analysis
            if income_data:
                income_result = self._analyze_income(income_data, loan_data)
                result.income_result = income_result
                result.qualifying_income = income_result.get("total_qualifying_income")

                if not income_result.get("income_stability", {}).get("is_stable", True):
                    result.findings.append(UnderwritingFinding(
                        category="income",
                        severity="warning",
                        message="Income stability concerns identified",
                        details=income_result.get("income_stability"),
                        recommendation="Review income trend and document any explanations",
                    ))

            # Step 3: Asset analysis
            if asset_data:
                asset_result = self._analyze_assets(asset_data, loan_data)
                result.asset_result = asset_result
                result.reserves_months = asset_result.get("reserves_months")

                if not asset_result.get("funds_to_close_met"):
                    result.critical_issues.append("Insufficient funds to close")
                    result.findings.append(UnderwritingFinding(
                        category="assets",
                        severity="critical",
                        message=f"Asset shortfall: ${asset_result.get('shortfall_amount', 0):,.0f}",
                        recommendation="Obtain additional asset documentation or gift funds",
                    ))

            # Step 4: Credit analysis
            if credit_data:
                credit_result = self._analyze_credit(credit_data, loan_data)
                result.credit_result = credit_result
                result.calculated_dti = credit_result.get("dti_ratio")

                # Update DTI with qualifying income if available
                if result.qualifying_income and result.qualifying_income > 0:
                    monthly_debt = credit_result.get("total_monthly_debt", 0)
                    proposed_payment = loan_data.get("proposed_monthly_payment", 0)
                    total_debt = monthly_debt + proposed_payment
                    result.calculated_dti = (total_debt / result.qualifying_income) * 100

                if credit_result.get("credit_grade") in ["D", "F"]:
                    result.findings.append(UnderwritingFinding(
                        category="credit",
                        severity="critical",
                        message=f"Credit grade {credit_result.get('credit_grade')} indicates high risk",
                        recommendation="Review credit history and consider credit-focused programs",
                    ))

            # Step 5: Calculate LTV
            loan_amount = float(loan_data.get("loan_amount", 0))
            property_value = float(loan_data.get("property_value", 0) or loan_data.get("appraisal_value", 0))
            if property_value > 0:
                result.calculated_ltv = (loan_amount / property_value) * 100

            # Step 6: Eligibility check
            eligibility = self._check_eligibility(loan_data, result)
            result.eligibility_result = eligibility

            if eligibility.get("recommendation"):
                result.approved_program = eligibility.get("recommendation")

            # Step 7: Generate conditions
            conditions = self._generate_conditions(
                loan_data, result.income_result, result.asset_result, result.credit_result
            )
            result.conditions = [self._condition_to_dict(c) for c in conditions]
            result.conditions_by_type = self._count_conditions_by_type(conditions)

            # Step 8: Risk assessment
            risk_level, risk_score = self._assess_risk(result)
            result.risk_level = risk_level

            # Step 9: Make decision
            decision, confidence = self._make_decision(result, risk_score)
            result.decision = decision
            result.confidence_score = confidence

            # Step 10: Set approval/denial details
            self._finalize_result(result, loan_data)

        except Exception as e:
            logger.exception(f"Underwriting analysis failed for loan {loan_id}")
            result.decision = UnderwritingDecision.REFER
            result.refer_reasons.append(f"Analysis error: {str(e)}")
            result.confidence_score = 0

        return result

    def _validate_data(self, loan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate loan data."""
        status = loan_data.get("status", "application")
        return validate_loan_file(loan_data, status, include_fraud_check=True)

    def _analyze_income(
        self,
        income_data: Dict[str, Any],
        loan_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze borrower income."""
        # Transform income_sources format to the format expected by IncomeCalculator
        # The calculator expects: employment, self_employment, rental, other_income
        borrower_income = {}

        income_sources = income_data.get("income_sources", [])
        employment_list = []
        self_employment_list = []
        rental_list = []
        other_income = []

        for source in income_sources:
            source_type = source.get("type", "w2_salary")

            if source_type in ["w2_salary", "salary", "hourly"]:
                employment_list.append({
                    "employer_name": source.get("employer_name", "Employer"),
                    "base_salary": source.get("base_salary", 0),
                    "pay_frequency": source.get("pay_frequency", "monthly"),
                    "ytd_gross": source.get("ytd_earnings", 0),
                    "w2_prior_year": source.get("prior_year_w2", 0),
                    "w2_two_years_ago": source.get("two_years_ago_w2"),
                    "start_date": source.get("start_date"),
                    "overtime": source.get("overtime", {}),
                    "bonus": source.get("bonus", {}),
                    "commission": source.get("commission", {}),
                })
            elif source_type == "self_employed":
                self_employment_list.append({
                    "business_name": source.get("business_name", "Business"),
                    "business_type": source.get("business_type", "sole_proprietor"),
                    "ownership_percentage": source.get("ownership_pct", 100),
                    "schedule_c": source.get("schedule_c_current", {}),
                    "schedule_c_prior": source.get("schedule_c_prior", {}),
                })
            elif source_type == "rental":
                rental_list.extend(source.get("properties", []))
            else:
                other_income.append(source)

        if employment_list:
            borrower_income["employment"] = employment_list
        if self_employment_list:
            borrower_income["self_employment"] = self_employment_list
        if rental_list:
            borrower_income["rental_income"] = rental_list
        if other_income:
            borrower_income["other_income"] = other_income

        # Calculate income using the engine
        try:
            calc_result = self.income_calculator.calculate_all_income(borrower_income)

            analyzed_sources = []
            for item in calc_result.borrower_items:
                analyzed_sources.append({
                    "type": item.income_type.value,
                    "source_name": item.source_name,
                    "qualifying_income": float(item.qualifying_monthly),
                    "gross_income": float(item.gross_monthly),
                    "usable": item.status.value in ["calculated", "verified"],
                    "documentation_status": item.documentation_status,
                    "issues": item.issues,
                    "warnings": item.warnings,
                })

            total_income = calc_result.total_qualifying_monthly

            # Determine income stability
            stability = self._assess_income_stability(income_data)

            return {
                "total_qualifying_income": float(total_income),
                "total_gross_income": float(calc_result.total_gross_monthly),
                "income_sources": analyzed_sources,
                "source_count": len(analyzed_sources),
                "income_stability": stability,
                "is_complete": calc_result.is_complete,
                "conditions_needed": calc_result.conditions_needed,
                "issues": calc_result.issues,
                "warnings": calc_result.warnings,
            }
        except Exception as e:
            logger.warning(f"Income calculation error: {e}")
            # Fallback to simple calculation
            total = 0
            for source in income_sources:
                if source.get("base_salary"):
                    total += source.get("base_salary", 0) / 12
                elif source.get("monthly_income"):
                    total += source.get("monthly_income", 0)

            return {
                "total_qualifying_income": total,
                "income_sources": income_sources,
                "source_count": len(income_sources),
                "income_stability": self._assess_income_stability(income_data),
                "calculation_method": "fallback",
            }

    def _assess_income_stability(self, income_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess income stability."""
        is_stable = True
        concerns = []

        # Check for declining income
        current_income = income_data.get("current_annual_income", 0)
        prior_income = income_data.get("prior_year_income", 0)

        if prior_income > 0 and current_income < prior_income * 0.9:
            is_stable = False
            decline_pct = (prior_income - current_income) / prior_income * 100
            concerns.append(f"Income declined {decline_pct:.0f}% from prior year")

        # Check employment length
        months_employed = income_data.get("months_at_current_employer", 0)
        if months_employed < 24:
            concerns.append(f"Less than 2 years at current employer ({months_employed} months)")

        # Check for employment gaps
        if income_data.get("has_employment_gap"):
            concerns.append("Employment gap in recent history")
            is_stable = False

        return {
            "is_stable": is_stable,
            "concerns": concerns,
            "months_at_employer": months_employed,
        }

    def _analyze_assets(
        self,
        asset_data: Dict[str, Any],
        loan_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze borrower assets."""
        # Combine checking/savings accounts with retirement accounts
        all_accounts = asset_data.get("accounts", [])
        all_accounts.extend(asset_data.get("retirement_accounts", []))

        # Calculate funds needed for closing
        loan_amount = Decimal(str(loan_data.get("loan_amount", 0)))
        property_value = Decimal(str(loan_data.get("property_value", 0)))
        closing_costs = Decimal(str(loan_data.get("estimated_closing_costs", 0)))
        prepaid_items = Decimal(str(loan_data.get("prepaid_items", 0)))

        # Calculate down payment
        down_payment = property_value - loan_amount if property_value > loan_amount else Decimal("0")

        funds_needed = {
            "down_payment": down_payment,
            "closing_costs": closing_costs,
            "prepaid": prepaid_items,
        }

        monthly_pitia = Decimal(str(loan_data.get("proposed_monthly_payment", 0)))
        property_type = loan_data.get("property_type", "primary_1_unit")
        dti_ratio = Decimal(str(loan_data.get("dti_ratio", 0) or 0))

        try:
            analysis = self.asset_analyzer.analyze_all_assets(
                assets_data=all_accounts,
                funds_needed=funds_needed,
                property_type=property_type,
                monthly_pitia=monthly_pitia,
                dti_ratio=dti_ratio,
            )

            return {
                "total_verified_assets": float(analysis.total_liquid_assets),
                "liquid_assets": float(analysis.total_liquid_assets),
                "eligible_for_closing": float(analysis.total_eligible_for_closing),
                "eligible_for_reserves": float(analysis.total_eligible_for_reserves),
                "funds_to_close_met": analysis.is_sufficient,
                "reserves_met": analysis.reserves_available.get("is_met", False) if isinstance(analysis.reserves_available, dict) else False,
                "reserves_months": analysis.reserves_available.get("months", 0) if isinstance(analysis.reserves_available, dict) else 0,
                "shortfall_amount": float(analysis.shortfall_amount),
                "large_deposits": [
                    {
                        "amount": float(d.amount),
                        "date": d.date.isoformat() if d.date else None,
                        "description": d.description,
                        "documented": d.is_documented,
                        "source": d.source,
                    }
                    for d in analysis.large_deposits_unsourced
                ],
                "issues": analysis.issues,
                "warnings": analysis.warnings,
                "conditions_needed": analysis.conditions_needed,
            }
        except Exception as e:
            logger.warning(f"Asset analysis error: {e}")
            # Fallback calculation
            total_assets = sum(
                float(a.get("balance", 0)) for a in all_accounts
            )
            total_needed = float(down_payment + closing_costs + prepaid_items)

            return {
                "total_verified_assets": total_assets,
                "liquid_assets": total_assets,
                "funds_to_close_met": total_assets >= total_needed,
                "reserves_met": True,
                "reserves_months": 2,
                "shortfall_amount": max(0, total_needed - total_assets),
                "large_deposits": [],
                "issues": [],
                "calculation_method": "fallback",
            }

    def _analyze_credit(
        self,
        credit_data: Dict[str, Any],
        loan_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze borrower credit."""
        # The credit analyzer expects credit_data in this format:
        # {
        #   "scores": {"equifax": X, "experian": Y, "transunion": Z},
        #   "tradelines": [...],
        #   "events": [...],  # bankruptcy, foreclosure, etc.
        # }

        # Transform input to expected format if needed
        formatted_credit_data = {}

        credit_score = credit_data.get("credit_score", 0)
        if credit_score:
            # If we only have a single score, use it for all bureaus
            formatted_credit_data["scores"] = credit_data.get("scores", {
                "equifax": credit_score,
                "experian": credit_score,
                "transunion": credit_score,
            })
        else:
            formatted_credit_data["scores"] = credit_data.get("scores", {})

        formatted_credit_data["tradelines"] = credit_data.get("tradelines", [])
        formatted_credit_data["events"] = credit_data.get("events", [])

        housing_expense = Decimal(str(loan_data.get("proposed_monthly_payment", 0)))
        monthly_income = Decimal(str(loan_data.get("monthly_income", 0)))

        try:
            analysis = self.credit_analyzer.analyze_credit(
                credit_data=formatted_credit_data,
                housing_expense=housing_expense,
                monthly_income=monthly_income,
            )

            return {
                "credit_score": analysis.representative_score,
                "middle_score": analysis.middle_score,
                "credit_grade": analysis.credit_grade,
                "total_monthly_debt": float(analysis.total_monthly_debt),
                "dti_ratio": float(analysis.dti_back_end),
                "dti_front_end": float(analysis.dti_front_end),
                "housing_expense": float(analysis.housing_expense),
                "program_eligibility": analysis.program_eligibility,
                "open_accounts": len([t for t in analysis.tradelines if t.status == "open"]),
                "derogatory_count": len([e for e in analysis.credit_events if e.is_derogatory]),
                "credit_events": [
                    {
                        "type": e.event_type,
                        "date": e.event_date.isoformat() if e.event_date else None,
                        "is_derogatory": e.is_derogatory,
                        "waiting_period_remaining": e.waiting_period_remaining,
                    }
                    for e in analysis.credit_events
                ],
                "issues": analysis.issues,
                "warnings": analysis.warnings,
                "conditions_needed": analysis.conditions_needed,
            }
        except Exception as e:
            logger.warning(f"Credit analysis error: {e}")
            # Fallback basic analysis
            return {
                "credit_score": credit_score,
                "credit_grade": "C" if credit_score >= 620 else "D" if credit_score >= 580 else "F",
                "total_monthly_debt": 0,
                "dti_ratio": 0,
                "dti_front_end": 0,
                "open_accounts": len(credit_data.get("tradelines", [])),
                "derogatory_count": 0,
                "issues": [],
                "calculation_method": "fallback",
            }

    def _check_eligibility(
        self,
        loan_data: Dict[str, Any],
        result: UnderwritingResult,
    ) -> Dict[str, Any]:
        """Check loan program eligibility."""
        # Build scenario from loan data and analysis results
        from .eligibility_engine import check_loan_eligibility

        return check_loan_eligibility(
            loan_amount=float(loan_data.get("loan_amount", 0)),
            property_value=float(loan_data.get("property_value", 0)),
            credit_score=int(result.credit_result.get("credit_score", 0)) if result.credit_result else 620,
            dti_ratio=float(result.calculated_dti or loan_data.get("dti_ratio", 45)),
            loan_purpose=loan_data.get("loan_purpose", "purchase"),
            property_type=loan_data.get("property_type", "sfr"),
            occupancy=loan_data.get("occupancy_type", "primary"),
            property_state=loan_data.get("property_state", "CA"),
            property_county=loan_data.get("property_county", ""),
            is_veteran=loan_data.get("is_veteran", False),
            num_units=loan_data.get("num_units", 1),
        )

    def _generate_conditions(
        self,
        loan_data: Dict[str, Any],
        income_result: Optional[Dict[str, Any]],
        asset_result: Optional[Dict[str, Any]],
        credit_result: Optional[Dict[str, Any]],
    ) -> List[Condition]:
        """Generate underwriting conditions."""
        return generate_loan_conditions(
            loan_data=loan_data,
            income_result=income_result,
            asset_result=asset_result,
            credit_result=credit_result,
        )

    def _condition_to_dict(self, condition: Condition) -> Dict[str, Any]:
        """Convert condition to dictionary."""
        return {
            "id": condition.id,
            "type": condition.condition_type.value,
            "category": condition.category.value,
            "priority": condition.priority.value,
            "title": condition.title,
            "description": condition.description,
            "clearing_instructions": condition.clearing_instructions,
            "acceptable_documents": condition.acceptable_documents,
            "status": condition.status.value,
        }

    def _count_conditions_by_type(self, conditions: List[Condition]) -> Dict[str, int]:
        """Count conditions by type."""
        counts = {}
        for cond in conditions:
            cond_type = cond.condition_type.value
            counts[cond_type] = counts.get(cond_type, 0) + 1
        return counts

    def _assess_risk(self, result: UnderwritingResult) -> Tuple[RiskLevel, float]:
        """Assess overall risk level."""
        risk_scores = {}

        # Credit score risk
        credit_score = 0
        if result.credit_result:
            credit_score = result.credit_result.get("credit_score", 0)

        if credit_score >= 760:
            risk_scores["credit_score"] = 100
        elif credit_score >= 740:
            risk_scores["credit_score"] = 85
        elif credit_score >= 700:
            risk_scores["credit_score"] = 70
        elif credit_score >= 660:
            risk_scores["credit_score"] = 55
        elif credit_score >= 620:
            risk_scores["credit_score"] = 40
        else:
            risk_scores["credit_score"] = 20

        # DTI risk
        dti = result.calculated_dti or 50
        if dti <= 36:
            risk_scores["dti_ratio"] = 100
        elif dti <= 43:
            risk_scores["dti_ratio"] = 80
        elif dti <= 45:
            risk_scores["dti_ratio"] = 65
        elif dti <= 50:
            risk_scores["dti_ratio"] = 45
        else:
            risk_scores["dti_ratio"] = 25

        # LTV risk
        ltv = result.calculated_ltv or 80
        if ltv <= 60:
            risk_scores["ltv"] = 100
        elif ltv <= 80:
            risk_scores["ltv"] = 85
        elif ltv <= 90:
            risk_scores["ltv"] = 65
        elif ltv <= 95:
            risk_scores["ltv"] = 45
        else:
            risk_scores["ltv"] = 30

        # Income stability risk
        if result.income_result:
            is_stable = result.income_result.get("income_stability", {}).get("is_stable", True)
            risk_scores["income_stability"] = 90 if is_stable else 50
        else:
            risk_scores["income_stability"] = 70

        # Asset adequacy risk
        if result.asset_result:
            funds_met = result.asset_result.get("funds_to_close_met", False)
            reserves_met = result.asset_result.get("reserves_met", False)
            if funds_met and reserves_met:
                risk_scores["asset_adequacy"] = 100
            elif funds_met:
                risk_scores["asset_adequacy"] = 70
            else:
                risk_scores["asset_adequacy"] = 30
        else:
            risk_scores["asset_adequacy"] = 60

        # Property risk (simplified)
        risk_scores["property_risk"] = 80  # Would be based on appraisal/property data

        # Compliance risk
        if result.validation_result:
            fraud_alerts = result.validation_result.get("counts", {}).get("fraud_alerts", 0)
            if fraud_alerts == 0:
                risk_scores["compliance"] = 100
            elif fraud_alerts == 1:
                risk_scores["compliance"] = 60
            else:
                risk_scores["compliance"] = 30
        else:
            risk_scores["compliance"] = 80

        # Calculate weighted score
        weighted_score = sum(
            risk_scores.get(factor, 50) * weight
            for factor, weight in self.RISK_WEIGHTS.items()
        )

        # Determine risk level
        if weighted_score >= 80:
            risk_level = RiskLevel.LOW
        elif weighted_score >= 60:
            risk_level = RiskLevel.MODERATE
        elif weighted_score >= 40:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.VERY_HIGH

        return risk_level, weighted_score

    def _make_decision(
        self,
        result: UnderwritingResult,
        risk_score: float,
    ) -> Tuple[UnderwritingDecision, float]:
        """Make underwriting decision based on analysis."""
        confidence = risk_score

        # Check for critical issues that force denial
        if result.critical_issues:
            return UnderwritingDecision.DENY, min(confidence, 70)

        # Check for fraud alerts
        fraud_alerts = 0
        if result.validation_result:
            fraud_alerts = result.validation_result.get("counts", {}).get("fraud_alerts", 0)

        if fraud_alerts > 0:
            return UnderwritingDecision.REFER, min(confidence, 50)

        # Check eligibility
        eligible_programs = []
        if result.eligibility_result:
            for prog in result.eligibility_result.get("programs", []):
                if prog.get("eligible"):
                    eligible_programs.append(prog)

        if not eligible_programs:
            # No eligible programs - check if close
            if result.eligibility_result:
                all_issues = []
                for prog in result.eligibility_result.get("programs", []):
                    all_issues.extend(prog.get("issues", []))

                if len(all_issues) <= 2:
                    # Close to eligible - counter offer possible
                    return UnderwritingDecision.COUNTER, min(confidence, 60)

            return UnderwritingDecision.DENY, min(confidence, 75)

        # Check risk level
        if result.risk_level == RiskLevel.VERY_HIGH:
            return UnderwritingDecision.REFER, min(confidence, 40)

        if result.risk_level == RiskLevel.HIGH:
            return UnderwritingDecision.REFER, min(confidence, 55)

        # Check DTI
        dti = result.calculated_dti or 0
        if dti > 50:
            return UnderwritingDecision.REFER, min(confidence, 50)

        # Check credit score
        credit_score = 0
        if result.credit_result:
            credit_score = result.credit_result.get("credit_score", 0)

        if credit_score < 620:
            return UnderwritingDecision.REFER, min(confidence, 45)

        # Determine approval level
        if risk_score >= self.APPROVE_THRESHOLD:
            if len(result.conditions) == 0:
                return UnderwritingDecision.APPROVE, confidence
            return UnderwritingDecision.APPROVE_ELIGIBLE, confidence
        elif risk_score >= self.REFER_THRESHOLD:
            return UnderwritingDecision.APPROVE_ELIGIBLE, confidence
        else:
            return UnderwritingDecision.REFER, confidence

    def _finalize_result(
        self,
        result: UnderwritingResult,
        loan_data: Dict[str, Any],
    ):
        """Finalize result with approval/denial details."""
        if result.decision in [UnderwritingDecision.APPROVE, UnderwritingDecision.APPROVE_ELIGIBLE]:
            result.approved_loan_amount = float(loan_data.get("loan_amount", 0))
            result.approved_rate = loan_data.get("interest_rate")

        elif result.decision == UnderwritingDecision.DENY:
            # Add denial reasons
            if result.critical_issues:
                result.denial_reasons.extend(result.critical_issues)

            if result.eligibility_result:
                for prog in result.eligibility_result.get("programs", []):
                    if not prog.get("eligible"):
                        result.denial_reasons.extend(prog.get("issues", [])[:3])

            # Add credit/DTI based reasons
            if result.credit_result:
                credit_score = result.credit_result.get("credit_score", 0)
                if credit_score < 500:
                    result.denial_reasons.append(f"Credit score {credit_score} does not meet minimum requirements")

            dti = result.calculated_dti or 0
            if dti > 60:
                result.denial_reasons.append(f"Debt-to-income ratio {dti:.1f}% exceeds program limits")

        elif result.decision == UnderwritingDecision.REFER:
            # Add refer reasons
            if result.risk_level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
                result.refer_reasons.append(f"Risk level ({result.risk_level.value}) requires manual review")

            if result.validation_result:
                fraud_alerts = result.validation_result.get("counts", {}).get("fraud_alerts", 0)
                if fraud_alerts > 0:
                    result.refer_reasons.append("Potential fraud indicators detected")

            for finding in result.findings:
                if finding.severity in ["critical", "error"]:
                    result.refer_reasons.append(finding.message)


def underwrite_loan(
    loan_data: Dict[str, Any],
    income_data: Optional[Dict[str, Any]] = None,
    asset_data: Optional[Dict[str, Any]] = None,
    credit_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience function for loan underwriting.

    Args:
        loan_data: Core loan information
        income_data: Income documentation data
        asset_data: Asset documentation data
        credit_data: Credit report data

    Returns:
        Dictionary with underwriting decision and analysis
    """
    engine = UnderwritingEngine()
    result = engine.analyze_loan(loan_data, income_data, asset_data, credit_data)
    return result.to_dict()
