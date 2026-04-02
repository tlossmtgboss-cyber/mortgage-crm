"""
Borrower Confidence Engine Service

Core business logic for:
- Confidence scoring and assessment
- Loan scenario calculations
- Personalized recommendations
- Education content delivery

Based on the Borrower Confidence Manifesto.
"""

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class ReadinessLevel(str, Enum):
    NOT_READY = "not_ready"
    NEEDS_WORK = "needs_work"
    ALMOST_READY = "almost_ready"
    READY = "ready"
    HIGHLY_READY = "highly_ready"


class LoanProductType(str, Enum):
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    JUMBO = "jumbo"
    NON_QM = "non_qm"


# Confidence score thresholds
READINESS_THRESHOLDS = {
    "highly_ready": 85,
    "ready": 70,
    "almost_ready": 55,
    "needs_work": 40,
    "not_ready": 0
}

# Weight multipliers by category
CATEGORY_WEIGHTS = {
    "financial_readiness": 1.5,
    "credit_understanding": 1.3,
    "mortgage_knowledge": 0.8,
    "process_understanding": 0.5,
    "emotional_readiness": 0.7
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ConfidenceScore:
    overall_score: float
    category_scores: Dict[str, float]
    readiness_level: ReadinessLevel
    key_strengths: List[str]
    areas_for_improvement: List[str]
    recommended_actions: List[Dict[str, Any]]


@dataclass
class LoanScenario:
    id: Optional[int] = None
    session_id: str = ""
    loan_amount: Decimal = Decimal("0")
    purchase_price: Decimal = Decimal("0")
    down_payment: Decimal = Decimal("0")
    property_type: str = "single_family"
    occupancy_type: str = "primary"
    property_state: str = ""
    credit_score: int = 720
    is_baseline: bool = False


@dataclass
class LoanOption:
    product_type: str
    product_name: str
    interest_rate: Decimal
    apr: Decimal
    term_months: int = 360
    monthly_payment: Decimal = Decimal("0")
    monthly_pi: Decimal = Decimal("0")
    monthly_taxes: Decimal = Decimal("0")
    monthly_insurance: Decimal = Decimal("0")
    monthly_pmi: Decimal = Decimal("0")
    closing_costs: Decimal = Decimal("0")
    total_cash_to_close: Decimal = Decimal("0")
    total_interest_paid: Decimal = Decimal("0")
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    is_recommended: bool = False
    recommendation_reasons: List[str] = field(default_factory=list)


# =============================================================================
# CONFIDENCE ENGINE SERVICE
# =============================================================================

class ConfidenceEngineService:
    """Core service for borrower confidence assessment and recommendations."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # QUESTION MANAGEMENT
    # =========================================================================

    def get_questions_for_session(
        self,
        session_id: str,
        category: Optional[str] = None,
        include_answered: bool = False
    ) -> List[Dict[str, Any]]:
        """Get questions for a session, optionally filtered by category."""

        params = {"session_id": session_id}
        category_filter = ""
        if category:
            category_filter = "AND cq.category = :category"
            params["category"] = category

        answered_filter = ""
        if not include_answered:
            answered_filter = """
                AND cq.id NOT IN (
                    SELECT question_id FROM confidence_responses
                    WHERE session_id = :session_id
                )
            """

        sql = """
            SELECT cq.id, cq.code, cq.category, cq.subcategory,
                   cq.question_text, cq.question_type, cq.options,
                   cq.weight, cq.display_order, cq.dependencies,
                   cq.education_overlay_id
            FROM confidence_questions cq
            WHERE cq.is_active = true
        """
        if category_filter:
            sql += "            " + category_filter + "\n"
        if answered_filter:
            sql += "            " + answered_filter + "\n"
        sql += """            ORDER BY cq.display_order, cq.id
        """
        results = self.db.execute(text(sql), params).fetchall()

        questions = []
        for r in results:
            questions.append({
                "id": r[0],
                "code": r[1],
                "category": r[2],
                "subcategory": r[3],
                "question_text": r[4],
                "question_type": r[5],
                "options": r[6],
                "weight": float(r[7]) if r[7] else 1.0,
                "display_order": r[8],
                "dependencies": r[9],
                "education_overlay_id": r[10]
            })

        return questions

    def get_next_question(
        self,
        session_id: str,
        borrower_profile_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get the next unanswered question for adaptive flow."""

        # Get answered question codes for dependency checking
        answered = self.db.execute(text("""
            SELECT cq.code, cr.response_value
            FROM confidence_responses cr
            JOIN confidence_questions cq ON cq.id = cr.question_id
            WHERE cr.session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        answered_codes = {r[0]: r[1] for r in answered}

        # Get all unanswered questions
        questions = self.get_questions_for_session(session_id, include_answered=False)

        for q in questions:
            # Check dependencies
            if q.get("dependencies"):
                deps = q["dependencies"] if isinstance(q["dependencies"], list) else []
                all_deps_met = True

                for dep in deps:
                    dep_code = dep.get("question")
                    dep_values = dep.get("values", [])

                    if dep_code not in answered_codes:
                        all_deps_met = False
                        break

                    if dep_values:
                        answered_value = answered_codes.get(dep_code, {})
                        if isinstance(answered_value, dict):
                            answered_value = answered_value.get("value", "")
                        if answered_value not in dep_values:
                            all_deps_met = False
                            break

                if not all_deps_met:
                    continue

            # This question is ready to be answered
            return q

        return None

    # =========================================================================
    # RESPONSE HANDLING
    # =========================================================================

    def save_response(
        self,
        session_id: str,
        question_id: int,
        response_value: Dict[str, Any],
        confidence_level: int = 3,
        time_to_answer_ms: int = 0,
        borrower_profile_id: Optional[str] = None,
        application_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save a response to a confidence question."""

        import json

        # Check for existing response
        existing = self.db.execute(text("""
            SELECT id, revision_count FROM confidence_responses
            WHERE session_id = :session_id AND question_id = :question_id
        """), {"session_id": session_id, "question_id": question_id}).fetchone()

        now = datetime.now(timezone.utc)

        if existing:
            # Update existing
            self.db.execute(text("""
                UPDATE confidence_responses
                SET response_value = :response_value,
                    confidence_level = :confidence_level,
                    time_to_answer_ms = :time_to_answer_ms,
                    revision_count = revision_count + 1,
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "id": existing[0],
                "response_value": json.dumps(response_value),
                "confidence_level": confidence_level,
                "time_to_answer_ms": time_to_answer_ms,
                "updated_at": now
            })
            response_id = existing[0]
        else:
            # Insert new
            result = self.db.execute(text("""
                INSERT INTO confidence_responses (
                    session_id, borrower_profile_id, application_id,
                    question_id, response_value, confidence_level,
                    time_to_answer_ms, created_at, updated_at
                ) VALUES (
                    :session_id, :borrower_profile_id, :application_id,
                    :question_id, :response_value, :confidence_level,
                    :time_to_answer_ms, :created_at, :updated_at
                ) RETURNING id
            """), {
                "session_id": session_id,
                "borrower_profile_id": borrower_profile_id,
                "application_id": application_id,
                "question_id": question_id,
                "response_value": json.dumps(response_value),
                "confidence_level": confidence_level,
                "time_to_answer_ms": time_to_answer_ms,
                "created_at": now,
                "updated_at": now
            })
            response_id = result.fetchone()[0]

        self.db.commit()

        return {
            "response_id": response_id,
            "session_id": session_id,
            "question_id": question_id,
            "saved_at": now.isoformat()
        }

    # =========================================================================
    # CONFIDENCE SCORING
    # =========================================================================

    def calculate_confidence_score(
        self,
        session_id: str,
        borrower_profile_id: Optional[str] = None,
        application_id: Optional[str] = None
    ) -> ConfidenceScore:
        """Calculate overall confidence score from responses."""

        import json

        # Get all responses with question weights
        responses = self.db.execute(text("""
            SELECT cq.category, cq.weight, cr.response_value,
                   cr.confidence_level, cq.options
            FROM confidence_responses cr
            JOIN confidence_questions cq ON cq.id = cr.question_id
            WHERE cr.session_id = :session_id
        """), {"session_id": session_id}).fetchall()

        if not responses:
            return ConfidenceScore(
                overall_score=0,
                category_scores={},
                readiness_level=ReadinessLevel.NOT_READY,
                key_strengths=[],
                areas_for_improvement=["Complete the confidence assessment to get your score"],
                recommended_actions=[]
            )

        # Calculate scores by category
        category_totals = {}
        category_max = {}

        for r in responses:
            category = r[0]
            weight = float(r[1]) if r[1] else 1.0
            response_value = r[2] if isinstance(r[2], dict) else json.loads(r[2]) if r[2] else {}
            confidence = r[3] or 3
            # Options can be dict (for scale) or list (for single_choice/multiple_choice)
            options = r[4] if isinstance(r[4], (dict, list)) else json.loads(r[4]) if r[4] else {}

            # Calculate score from response
            score = self._calculate_response_score(response_value, options)

            # Apply category weight
            category_weight = CATEGORY_WEIGHTS.get(category, 1.0)
            weighted_score = score * weight * category_weight

            if category not in category_totals:
                category_totals[category] = 0
                category_max[category] = 0

            category_totals[category] += weighted_score
            category_max[category] += 5 * weight * category_weight  # Max possible

        # Calculate category percentages
        category_scores = {}
        for cat in category_totals:
            if category_max[cat] > 0:
                category_scores[cat] = round(
                    (category_totals[cat] / category_max[cat]) * 100, 1
                )
            else:
                category_scores[cat] = 0

        # Calculate overall score
        if category_scores:
            overall_score = sum(category_scores.values()) / len(category_scores)
        else:
            overall_score = 0

        # Determine readiness level
        readiness_level = self._determine_readiness_level(overall_score)

        # Identify strengths and areas for improvement
        strengths = []
        improvements = []
        for cat, score in category_scores.items():
            cat_name = cat.replace("_", " ").title()
            if score >= 70:
                strengths.append(f"Strong {cat_name}")
            elif score < 50:
                improvements.append(f"Improve {cat_name}")

        # Generate recommended actions
        actions = self._generate_recommended_actions(category_scores, responses)

        # Save score to database
        self._save_confidence_score(
            session_id, borrower_profile_id, application_id,
            overall_score, category_scores, readiness_level,
            strengths, improvements, actions
        )

        return ConfidenceScore(
            overall_score=round(overall_score, 1),
            category_scores=category_scores,
            readiness_level=readiness_level,
            key_strengths=strengths,
            areas_for_improvement=improvements,
            recommended_actions=actions
        )

    def _calculate_response_score(
        self,
        response_value: Dict,
        options: Dict
    ) -> float:
        """Calculate score from a single response."""

        value = response_value.get("value", response_value.get("score", 3))

        # Scale type questions (1-5)
        if isinstance(value, (int, float)):
            return float(value)

        # Choice questions - look up score from options
        if isinstance(options, list):
            for opt in options:
                if opt.get("value") == value:
                    return float(opt.get("score", 3))

        return 3.0  # Default middle score

    def _determine_readiness_level(self, score: float) -> ReadinessLevel:
        """Determine readiness level from score."""
        if score >= READINESS_THRESHOLDS["highly_ready"]:
            return ReadinessLevel.HIGHLY_READY
        elif score >= READINESS_THRESHOLDS["ready"]:
            return ReadinessLevel.READY
        elif score >= READINESS_THRESHOLDS["almost_ready"]:
            return ReadinessLevel.ALMOST_READY
        elif score >= READINESS_THRESHOLDS["needs_work"]:
            return ReadinessLevel.NEEDS_WORK
        else:
            return ReadinessLevel.NOT_READY

    def _generate_recommended_actions(
        self,
        category_scores: Dict[str, float],
        responses: List
    ) -> List[Dict[str, Any]]:
        """Generate personalized action recommendations."""

        actions = []
        priority = 1

        # Low financial readiness
        if category_scores.get("financial_readiness", 0) < 60:
            actions.append({
                "priority": priority,
                "category": "financial_readiness",
                "title": "Build Your Financial Foundation",
                "description": "Focus on building an emergency fund and tracking your monthly expenses",
                "action_type": "education",
                "lesson_code": "FINANCIAL_BASICS"
            })
            priority += 1

        # Low credit understanding
        if category_scores.get("credit_understanding", 0) < 60:
            actions.append({
                "priority": priority,
                "category": "credit_understanding",
                "title": "Check Your Credit Report",
                "description": "Review your credit report for accuracy and understand factors affecting your score",
                "action_type": "task",
                "external_link": "https://www.annualcreditreport.com"
            })
            priority += 1

        # Low mortgage knowledge
        if category_scores.get("mortgage_knowledge", 0) < 50:
            actions.append({
                "priority": priority,
                "category": "mortgage_knowledge",
                "title": "Learn Mortgage Basics",
                "description": "Understand different loan types, rates, and what affects your payment",
                "action_type": "education",
                "lesson_code": "MORTGAGE_101"
            })
            priority += 1

        # High overall score - ready for next step
        overall = sum(category_scores.values()) / len(category_scores) if category_scores else 0
        if overall >= 70:
            actions.append({
                "priority": 0,  # Top priority
                "category": "next_step",
                "title": "You're Ready! Let's Create Your Loan Scenarios",
                "description": "Based on your profile, you're ready to explore personalized loan options",
                "action_type": "navigation",
                "destination": "/decision-lab/scenarios"
            })

        return actions

    def _save_confidence_score(
        self,
        session_id: str,
        borrower_profile_id: Optional[str],
        application_id: Optional[str],
        overall_score: float,
        category_scores: Dict,
        readiness_level: ReadinessLevel,
        strengths: List[str],
        improvements: List[str],
        actions: List[Dict]
    ):
        """Save calculated score to database."""
        import json

        self.db.execute(text("""
            INSERT INTO confidence_scores (
                session_id, borrower_profile_id, application_id,
                overall_score, category_scores, readiness_level,
                key_strengths, areas_for_improvement, recommended_actions,
                calculated_at
            ) VALUES (
                :session_id, :borrower_profile_id, :application_id,
                :overall_score, :category_scores, :readiness_level,
                :key_strengths, :areas_for_improvement, :recommended_actions,
                :calculated_at
            )
        """), {
            "session_id": session_id,
            "borrower_profile_id": borrower_profile_id,
            "application_id": application_id,
            "overall_score": overall_score,
            "category_scores": json.dumps(category_scores),
            "readiness_level": readiness_level.value,
            "key_strengths": json.dumps(strengths),
            "areas_for_improvement": json.dumps(improvements),
            "recommended_actions": json.dumps(actions),
            "calculated_at": datetime.now(timezone.utc)
        })
        self.db.commit()

    # =========================================================================
    # EDUCATION CONTENT
    # =========================================================================

    def get_education_overlay(
        self,
        trigger_context: str
    ) -> Optional[Dict[str, Any]]:
        """Get education overlay for a given context."""

        result = self.db.execute(text("""
            SELECT id, code, title, content, content_type,
                   media_url, display_position, auto_dismiss_seconds
            FROM education_overlays
            WHERE trigger_context = :trigger_context
                AND is_active = true
            LIMIT 1
        """), {"trigger_context": trigger_context}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "code": result[1],
            "title": result[2],
            "content": result[3],
            "content_type": result[4],
            "media_url": result[5],
            "display_position": result[6],
            "auto_dismiss_seconds": result[7]
        }

    def track_education_view(
        self,
        borrower_profile_id: str,
        overlay_id: Optional[int] = None,
        lesson_id: Optional[int] = None
    ):
        """Track that a borrower viewed education content."""

        self.db.execute(text("""
            INSERT INTO education_progress (
                borrower_profile_id, lesson_id, overlay_id,
                status, created_at, updated_at
            ) VALUES (
                :borrower_profile_id, :lesson_id, :overlay_id,
                'viewed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) ON CONFLICT DO NOTHING
        """), {
            "borrower_profile_id": borrower_profile_id,
            "lesson_id": lesson_id,
            "overlay_id": overlay_id
        })
        self.db.commit()


# =============================================================================
# LOAN SCENARIO SERVICE
# =============================================================================

class LoanScenarioService:
    """Service for loan scenario calculations and comparisons."""

    # Standard assumptions
    PROPERTY_TAX_RATE = 0.0125  # 1.25% annually
    INSURANCE_RATE = 0.005  # 0.5% annually
    PMI_RATE = 0.01  # 1% annually when LTV > 80%

    def __init__(self, db: Session):
        self.db = db

    def create_scenario(
        self,
        session_id: str,
        loan_amount: Decimal,
        purchase_price: Decimal,
        down_payment: Decimal,
        property_type: str = "single_family",
        occupancy_type: str = "primary",
        property_state: str = "",
        credit_score: int = 720,
        borrower_profile_id: Optional[str] = None,
        application_id: Optional[str] = None,
        is_baseline: bool = False
    ) -> Dict[str, Any]:
        """Create a new loan scenario."""

        down_payment_percent = (down_payment / purchase_price * 100) if purchase_price > 0 else 0
        ltv = ((loan_amount / purchase_price) * 100) if purchase_price > 0 else 0

        result = self.db.execute(text("""
            INSERT INTO loan_scenarios (
                session_id, borrower_profile_id, application_id,
                scenario_type, loan_amount, purchase_price,
                down_payment, down_payment_percent,
                property_type, occupancy_type, property_state,
                credit_score, ltv_ratio, is_baseline,
                created_at, updated_at
            ) VALUES (
                :session_id, :borrower_profile_id, :application_id,
                :scenario_type, :loan_amount, :purchase_price,
                :down_payment, :down_payment_percent,
                :property_type, :occupancy_type, :property_state,
                :credit_score, :ltv_ratio, :is_baseline,
                :created_at, :updated_at
            ) RETURNING id
        """), {
            "session_id": session_id,
            "borrower_profile_id": borrower_profile_id,
            "application_id": application_id,
            "scenario_type": "purchase",
            "loan_amount": float(loan_amount),
            "purchase_price": float(purchase_price),
            "down_payment": float(down_payment),
            "down_payment_percent": float(down_payment_percent),
            "property_type": property_type,
            "occupancy_type": occupancy_type,
            "property_state": property_state,
            "credit_score": credit_score,
            "ltv_ratio": float(ltv),
            "is_baseline": is_baseline,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

        scenario_id = result.fetchone()[0]
        self.db.commit()

        return {
            "scenario_id": scenario_id,
            "session_id": session_id,
            "loan_amount": float(loan_amount),
            "purchase_price": float(purchase_price),
            "down_payment": float(down_payment),
            "down_payment_percent": round(float(down_payment_percent), 2),
            "ltv_ratio": round(float(ltv), 2)
        }

    def calculate_loan_options(
        self,
        scenario_id: int
    ) -> List[Dict[str, Any]]:
        """Calculate available loan options for a scenario."""

        # Get scenario details
        scenario = self.db.execute(text("""
            SELECT loan_amount, purchase_price, down_payment,
                   property_type, occupancy_type, credit_score, ltv_ratio
            FROM loan_scenarios
            WHERE id = :scenario_id
        """), {"scenario_id": scenario_id}).fetchone()

        if not scenario:
            return []

        loan_amount = Decimal(str(scenario[0]))
        purchase_price = Decimal(str(scenario[1]))
        credit_score = scenario[5]
        ltv = float(scenario[6])

        options = []

        # Generate options for different product types
        product_configs = self._get_eligible_products(credit_score, ltv)

        for config in product_configs:
            option = self._calculate_option(
                loan_amount, purchase_price, ltv, credit_score, config
            )
            if option:
                options.append(option)

        # Rank options first (sets is_recommended, rank, recommendation_reasons)
        options = self._rank_options(options)

        # Save to database after ranking so is_recommended is included
        for option in options:
            self._save_option(scenario_id, option)

        return options

    def _get_eligible_products(
        self,
        credit_score: int,
        ltv: float
    ) -> List[Dict[str, Any]]:
        """Get eligible loan products based on credit and LTV."""

        products = []

        # Conventional
        if credit_score >= 620:
            products.append({
                "type": "conventional",
                "name": "Conventional 30-Year Fixed",
                "base_rate": Decimal("6.875"),
                "term_months": 360,
                "min_credit": 620,
                "max_ltv": 97
            })
            products.append({
                "type": "conventional",
                "name": "Conventional 15-Year Fixed",
                "base_rate": Decimal("6.25"),
                "term_months": 180,
                "min_credit": 620,
                "max_ltv": 97
            })

        # FHA
        if credit_score >= 580 and ltv <= 96.5:
            products.append({
                "type": "fha",
                "name": "FHA 30-Year Fixed",
                "base_rate": Decimal("6.50"),
                "term_months": 360,
                "min_credit": 580,
                "max_ltv": 96.5
            })

        # VA (simplified - normally need eligibility check)
        if credit_score >= 620:
            products.append({
                "type": "va",
                "name": "VA 30-Year Fixed",
                "base_rate": Decimal("6.25"),
                "term_months": 360,
                "min_credit": 620,
                "max_ltv": 100
            })

        return products

    def _calculate_option(
        self,
        loan_amount: Decimal,
        purchase_price: Decimal,
        ltv: float,
        credit_score: int,
        config: Dict
    ) -> Optional[Dict[str, Any]]:
        """Calculate full payment details for a loan option."""

        # Rate adjustments based on credit score
        rate_adj = Decimal("0")
        if credit_score < 680:
            rate_adj = Decimal("0.50")
        elif credit_score < 720:
            rate_adj = Decimal("0.25")
        elif credit_score >= 760:
            rate_adj = Decimal("-0.125")

        rate = config["base_rate"] + rate_adj
        monthly_rate = rate / Decimal("100") / Decimal("12")
        term = config["term_months"]

        # Calculate P&I using amortization formula
        if monthly_rate > 0:
            monthly_pi = loan_amount * (
                monthly_rate * (1 + monthly_rate) ** term
            ) / ((1 + monthly_rate) ** term - 1)
        else:
            monthly_pi = loan_amount / term

        # Taxes & Insurance
        monthly_taxes = (purchase_price * Decimal(str(self.PROPERTY_TAX_RATE))) / 12
        monthly_insurance = (purchase_price * Decimal(str(self.INSURANCE_RATE))) / 12

        # PMI for conventional with LTV > 80%
        monthly_pmi = Decimal("0")
        if config["type"] == "conventional" and ltv > 80:
            monthly_pmi = (loan_amount * Decimal(str(self.PMI_RATE))) / 12
        elif config["type"] == "fha":
            monthly_pmi = (loan_amount * Decimal("0.0055")) / 12  # FHA MIP

        monthly_payment = monthly_pi + monthly_taxes + monthly_insurance + monthly_pmi

        # Closing costs estimate (2-5% of loan)
        closing_costs = loan_amount * Decimal("0.03")

        # Total interest over life of loan
        total_interest = (monthly_pi * term) - loan_amount

        # APR calculation (simplified)
        apr = rate + Decimal("0.15")  # Add approx impact of closing costs

        # Pros and cons
        pros, cons = self._get_pros_cons(config["type"], ltv, credit_score)

        return {
            "product_type": config["type"],
            "product_name": config["name"],
            "interest_rate": float(rate),
            "apr": float(apr),
            "term_months": term,
            "monthly_payment": float(round(monthly_payment, 2)),
            "monthly_pi": float(round(monthly_pi, 2)),
            "monthly_taxes": float(round(monthly_taxes, 2)),
            "monthly_insurance": float(round(monthly_insurance, 2)),
            "monthly_pmi": float(round(monthly_pmi, 2)),
            "closing_costs": float(round(closing_costs, 2)),
            "total_cash_to_close": float(round(closing_costs, 2)),
            "total_interest_paid": float(round(total_interest, 2)),
            "pros": pros,
            "cons": cons
        }

    def _get_pros_cons(
        self,
        product_type: str,
        ltv: float,
        credit_score: int
    ) -> Tuple[List[str], List[str]]:
        """Get pros and cons for a product type."""

        pros_cons = {
            "conventional": {
                "pros": [
                    "PMI can be removed at 80% LTV",
                    "More flexibility on property types",
                    "No upfront funding fee"
                ],
                "cons": [
                    "Stricter credit requirements" if credit_score < 680 else None,
                    "PMI required if LTV > 80%" if ltv > 80 else None
                ]
            },
            "fha": {
                "pros": [
                    "Lower credit requirements",
                    "Low down payment (3.5%)",
                    "Flexible debt-to-income ratios"
                ],
                "cons": [
                    "MIP for life of loan (if LTV > 90%)",
                    "Upfront MIP (1.75%)",
                    "Property must meet FHA standards"
                ]
            },
            "va": {
                "pros": [
                    "No down payment required",
                    "No PMI",
                    "Competitive rates",
                    "No prepayment penalty"
                ],
                "cons": [
                    "VA funding fee applies",
                    "Must be eligible veteran/service member",
                    "Property restrictions"
                ]
            }
        }

        product_info = pros_cons.get(product_type, {"pros": [], "cons": []})
        return (
            [p for p in product_info["pros"] if p],
            [c for c in product_info["cons"] if c]
        )

    def _save_option(self, scenario_id: int, option: Dict[str, Any]):
        """Save a calculated option to the database."""
        import json

        self.db.execute(text("""
            INSERT INTO loan_options (
                scenario_id, product_type, product_name,
                interest_rate, apr, term_months,
                monthly_payment, monthly_pi, monthly_taxes,
                monthly_insurance, monthly_pmi, closing_costs,
                total_cash_to_close, total_interest_paid,
                pros, cons, rank, is_recommended, recommendation_reasons,
                created_at
            ) VALUES (
                :scenario_id, :product_type, :product_name,
                :interest_rate, :apr, :term_months,
                :monthly_payment, :monthly_pi, :monthly_taxes,
                :monthly_insurance, :monthly_pmi, :closing_costs,
                :total_cash_to_close, :total_interest_paid,
                :pros, :cons, :rank, :is_recommended, :recommendation_reasons,
                :created_at
            )
        """), {
            "scenario_id": scenario_id,
            "product_type": option["product_type"],
            "product_name": option["product_name"],
            "interest_rate": option["interest_rate"],
            "apr": option["apr"],
            "term_months": option["term_months"],
            "monthly_payment": option["monthly_payment"],
            "monthly_pi": option["monthly_pi"],
            "monthly_taxes": option["monthly_taxes"],
            "monthly_insurance": option["monthly_insurance"],
            "monthly_pmi": option["monthly_pmi"],
            "closing_costs": option["closing_costs"],
            "total_cash_to_close": option["total_cash_to_close"],
            "total_interest_paid": option["total_interest_paid"],
            "pros": json.dumps(option["pros"]),
            "cons": json.dumps(option["cons"]),
            "rank": option.get("rank"),
            "is_recommended": option.get("is_recommended", False),
            "recommendation_reasons": json.dumps(option.get("recommendation_reasons")) if option.get("recommendation_reasons") else None,
            "created_at": datetime.now(timezone.utc)
        })
        self.db.commit()

    def _rank_options(self, options: List[Dict]) -> List[Dict]:
        """Rank options by overall value."""

        # Simple ranking by monthly payment
        sorted_options = sorted(options, key=lambda x: x["monthly_payment"])

        for i, opt in enumerate(sorted_options):
            opt["rank"] = i + 1
            if i == 0:
                opt["is_recommended"] = True
                opt["recommendation_reasons"] = ["Lowest monthly payment"]

        return sorted_options


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_confidence_engine(db: Session) -> ConfidenceEngineService:
    """Factory function to get confidence engine instance."""
    return ConfidenceEngineService(db)


def get_scenario_service(db: Session) -> LoanScenarioService:
    """Factory function to get scenario service instance."""
    return LoanScenarioService(db)
