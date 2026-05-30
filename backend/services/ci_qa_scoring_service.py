"""
Conversation Intelligence - QA Scoring Service

Hybrid scoring system combining:
- Rule-based automatic scoring with keyword detection
- LLM-powered scoring for nuanced evaluation
- Manual review and override capabilities

Features:
- Configurable rubrics with weighted categories
- Auto-fail for compliance violations
- Grade calculation (A-F)
- Improvement recommendations
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from decimal import Decimal
import re

import anthropic

from services.ci_transcription_service import TranscriptionResult, TranscriptionSegment
from services.ci_analysis_service import CallAnalysisResult

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RubricCriteria:
    """Individual criterion within a rubric."""
    points: int
    description: str
    keywords: Optional[List[str]] = None
    anti_keywords: Optional[List[str]] = None


@dataclass
class QARubric:
    """QA scoring rubric definition."""
    id: str
    name: str
    category: str
    max_points: int
    weight: float
    criteria: List[RubricCriteria]
    scoring_guide: str = ""
    auto_score_enabled: bool = True
    auto_score_keywords: Optional[Dict[str, Any]] = None
    required: bool = False
    is_auto_fail: bool = False


@dataclass
class RubricScore:
    """Score for a single rubric."""
    rubric_id: str
    rubric_name: str
    category: str
    score: float
    max_score: float
    percentage: float
    evidence_text: Optional[str] = None
    evidence_timestamps: Optional[List[Dict[str, int]]] = None
    auto_score: Optional[float] = None
    llm_score: Optional[float] = None
    evaluator_notes: Optional[str] = None
    improvement_suggestions: Optional[str] = None


@dataclass
class QAScorecard:
    """Complete QA scorecard for a call."""
    id: str = ""
    recording_id: str = ""

    # Scoring metadata
    scoring_method: str = "auto"  # auto, manual, hybrid
    scored_by: Optional[str] = None

    # Overall scores
    total_score: float = 0.0
    max_possible_score: float = 0.0
    percentage_score: float = 0.0
    grade: str = ""

    # Category breakdown
    category_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Individual scores
    rubric_scores: List[RubricScore] = field(default_factory=list)

    # Flags
    critical_failures: List[Dict[str, Any]] = field(default_factory=list)
    improvement_areas: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)

    # Status
    status: str = "pending"  # pending, in_review, completed, disputed

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["rubric_scores"] = [asdict(s) for s in self.rubric_scores]
        return result


# =============================================================================
# DEFAULT RUBRICS
# =============================================================================

DEFAULT_RUBRICS = [
    QARubric(
        id="greeting",
        name="Professional Greeting",
        category="greeting",
        max_points=10,
        weight=1.0,
        criteria=[
            RubricCriteria(3, "States company name", ["mortgage", "lending", "loan"]),
            RubricCriteria(3, "Provides full name", ["my name is", "this is"]),
            RubricCriteria(2, "Warm and welcoming tone"),
            RubricCriteria(2, "Offers assistance", ["how may i help", "how can i help", "assist"]),
        ],
        auto_score_keywords={"required": ["mortgage", "lending"], "bonus": ["thank you for calling"]}
    ),
    QARubric(
        id="discovery",
        name="Needs Discovery",
        category="discovery",
        max_points=10,
        weight=1.5,
        criteria=[
            RubricCriteria(4, "Identifies loan purpose", ["purchase", "refinance", "cash out"]),
            RubricCriteria(3, "Asks clarifying questions"),
            RubricCriteria(3, "Confirms understanding", ["so you", "let me make sure", "to confirm"]),
        ],
        auto_score_keywords={"required": ["purchase", "refinance"]}
    ),
    QARubric(
        id="presentation",
        name="Product Presentation",
        category="presentation",
        max_points=10,
        weight=1.5,
        criteria=[
            RubricCriteria(3, "Presents relevant options", ["conventional", "fha", "va"]),
            RubricCriteria(3, "Explains key differences"),
            RubricCriteria(2, "Uses clear language"),
            RubricCriteria(2, "Provides pros and cons"),
        ],
        auto_score_keywords={"required": ["rate", "loan"]}
    ),
    QARubric(
        id="closing",
        name="Clear Next Steps",
        category="closing",
        max_points=10,
        weight=1.5,
        criteria=[
            RubricCriteria(3, "Summarizes discussion"),
            RubricCriteria(3, "States next steps clearly", ["next step", "follow up", "i will"]),
            RubricCriteria(2, "Sets timeline expectations"),
            RubricCriteria(2, "Confirms contact info"),
        ],
        auto_score_keywords={"required": ["next step", "follow up"]}
    ),
    QARubric(
        id="nmls_compliance",
        name="NMLS Disclosure",
        category="compliance",
        max_points=10,
        weight=2.0,
        criteria=[
            RubricCriteria(10, "NMLS ID provided when appropriate", ["nmls", "license"]),
        ],
        is_auto_fail=True,
        required=True
    ),
    QARubric(
        id="rate_compliance",
        name="Rate Advertising Compliance",
        category="compliance",
        max_points=10,
        weight=2.0,
        criteria=[
            RubricCriteria(5, "No guaranteed rate claims"),
            RubricCriteria(5, "Rates qualified as estimates", ["subject to", "estimate", "may vary"]),
        ],
        auto_score_keywords={"prohibited": ["guarantee", "promise", "locked in"]}
    ),
]


# =============================================================================
# QA SCORING SERVICE
# =============================================================================

class QAScoringService:
    """
    Service for scoring calls against QA rubrics.

    Usage:
        service = QAScoringService()
        scorecard = await service.score_call(transcription, analysis)
    """

    def __init__(self, rubrics: Optional[List[QARubric]] = None):
        self.rubrics = rubrics or DEFAULT_RUBRICS
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    async def score_call(
        self,
        transcription: TranscriptionResult,
        analysis: Optional[CallAnalysisResult] = None,
        call_type: str = "inbound",
        use_llm: bool = True
    ) -> QAScorecard:
        """
        Score a call against all applicable rubrics.

        Args:
            transcription: Call transcription
            analysis: Optional call analysis for additional context
            call_type: Type of call (inbound, outbound)
            use_llm: Whether to use LLM for nuanced scoring

        Returns:
            QAScorecard with complete scoring
        """
        scorecard = QAScorecard(
            id=str(datetime.now().timestamp()),
            scoring_method="hybrid" if use_llm else "auto"
        )

        full_text = transcription.full_text.lower()
        rubric_scores = []

        for rubric in self.rubrics:
            # Check if rubric applies to this call type
            if call_type not in ["inbound", "outbound"]:
                continue

            # Auto-score based on keywords
            auto_score = self._auto_score_rubric(rubric, full_text, transcription.segments)

            # LLM scoring for more nuanced evaluation
            llm_score = None
            if use_llm and self.client:
                llm_score = await self._llm_score_rubric(rubric, transcription, analysis)

            # Combine scores
            if llm_score is not None:
                final_score = (auto_score * 0.4 + llm_score * 0.6)  # Weight LLM higher
            else:
                final_score = auto_score

            # Get evidence
            evidence = self._find_evidence(rubric, transcription)

            rubric_score = RubricScore(
                rubric_id=rubric.id,
                rubric_name=rubric.name,
                category=rubric.category,
                score=round(final_score, 2),
                max_score=rubric.max_points,
                percentage=round((final_score / rubric.max_points) * 100, 1) if rubric.max_points > 0 else 0,
                auto_score=auto_score,
                llm_score=llm_score,
                evidence_text=evidence.get("text"),
                evidence_timestamps=evidence.get("timestamps")
            )

            # Check for auto-fail
            if rubric.is_auto_fail and final_score < rubric.max_points * 0.5:
                scorecard.critical_failures.append({
                    "rubric": rubric.name,
                    "score": final_score,
                    "reason": f"Failed critical rubric: {rubric.name}"
                })

            rubric_scores.append(rubric_score)

        scorecard.rubric_scores = rubric_scores

        # Calculate totals
        self._calculate_totals(scorecard)

        # Identify strengths and improvements
        self._identify_strengths_and_improvements(scorecard)

        return scorecard

    def _auto_score_rubric(
        self,
        rubric: QARubric,
        full_text: str,
        segments: List[TranscriptionSegment]
    ) -> float:
        """Auto-score a rubric based on keywords and rules."""
        score = 0
        max_score = rubric.max_points

        # Score each criterion
        for criterion in rubric.criteria:
            criterion_met = False

            if criterion.keywords:
                # Check if any keyword is present
                for keyword in criterion.keywords:
                    if keyword.lower() in full_text:
                        criterion_met = True
                        break

            if criterion.anti_keywords:
                # Check for prohibited keywords
                for anti_kw in criterion.anti_keywords:
                    if anti_kw.lower() in full_text:
                        criterion_met = False
                        score -= criterion.points  # Penalty
                        break

            if criterion_met:
                score += criterion.points

        # Apply auto_score_keywords if present
        if rubric.auto_score_keywords:
            required = rubric.auto_score_keywords.get("required", [])
            bonus = rubric.auto_score_keywords.get("bonus", [])
            prohibited = rubric.auto_score_keywords.get("prohibited", [])

            # Required keywords
            required_found = sum(1 for kw in required if kw.lower() in full_text)
            if required and required_found == 0:
                score = max(0, score - max_score * 0.3)  # Penalty for missing required

            # Bonus keywords
            bonus_found = sum(1 for kw in bonus if kw.lower() in full_text)
            score += min(bonus_found * 0.5, max_score * 0.2)  # Cap bonus

            # Prohibited keywords
            prohibited_found = sum(1 for kw in prohibited if kw.lower() in full_text)
            if prohibited_found > 0:
                score = max(0, score - prohibited_found * 2)  # Penalty

        return max(0, min(score, max_score))

    async def _llm_score_rubric(
        self,
        rubric: QARubric,
        transcription: TranscriptionResult,
        analysis: Optional[CallAnalysisResult]
    ) -> Optional[float]:
        """Use LLM for nuanced rubric scoring."""
        if not self.client:
            return None

        # Prepare context
        transcript_preview = transcription.full_text[:2000]

        prompt = f"""Score this call transcript on the following rubric:

RUBRIC: {rubric.name}
CATEGORY: {rubric.category}
MAX POINTS: {rubric.max_points}

SCORING CRITERIA:
{json.dumps([{"points": c.points, "description": c.description} for c in rubric.criteria], indent=2)}

SCORING GUIDE:
{rubric.scoring_guide or "Score based on how well the agent met each criterion."}

TRANSCRIPT:
{transcript_preview}

Respond with JSON only:
{{"score": <number 0-{rubric.max_points}>, "reasoning": "<brief explanation>"}}"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].split("```")[0]
                if text.startswith("json"):
                    text = text[4:]

            data = json.loads(text)
            return float(data.get("score", 0))

        except Exception as e:
            logger.warning(f"LLM scoring failed for rubric {rubric.id}: {e}")
            return None

    def _find_evidence(
        self,
        rubric: QARubric,
        transcription: TranscriptionResult
    ) -> Dict[str, Any]:
        """Find evidence from transcript supporting the rubric score."""
        evidence = {"text": None, "timestamps": []}

        # Find segments with relevant keywords
        all_keywords = []
        for criterion in rubric.criteria:
            if criterion.keywords:
                all_keywords.extend(criterion.keywords)

        if rubric.auto_score_keywords:
            all_keywords.extend(rubric.auto_score_keywords.get("required", []))
            all_keywords.extend(rubric.auto_score_keywords.get("bonus", []))

        relevant_segments = []
        for seg in transcription.segments:
            text_lower = seg.text.lower()
            if any(kw.lower() in text_lower for kw in all_keywords):
                relevant_segments.append(seg)

        if relevant_segments:
            evidence["text"] = " ... ".join([s.text[:100] for s in relevant_segments[:3]])
            evidence["timestamps"] = [
                {"start_ms": s.start_time_ms, "end_ms": s.end_time_ms}
                for s in relevant_segments[:3]
            ]

        return evidence

    def _calculate_totals(self, scorecard: QAScorecard):
        """Calculate total scores and grade."""
        if not scorecard.rubric_scores:
            return

        # Calculate weighted totals
        total_weighted_score = 0
        total_weighted_max = 0
        category_scores = {}

        for rs in scorecard.rubric_scores:
            # Find rubric for weight
            rubric = next((r for r in self.rubrics if r.id == rs.rubric_id), None)
            weight = rubric.weight if rubric else 1.0

            total_weighted_score += rs.score * weight
            total_weighted_max += rs.max_score * weight

            # Category aggregation
            if rs.category not in category_scores:
                category_scores[rs.category] = {"score": 0, "max": 0}
            category_scores[rs.category]["score"] += rs.score * weight
            category_scores[rs.category]["max"] += rs.max_score * weight

        scorecard.total_score = round(total_weighted_score, 2)
        scorecard.max_possible_score = round(total_weighted_max, 2)

        if total_weighted_max > 0:
            scorecard.percentage_score = round(
                (total_weighted_score / total_weighted_max) * 100, 1
            )
        else:
            scorecard.percentage_score = 0

        # Calculate category percentages
        for cat, scores in category_scores.items():
            if scores["max"] > 0:
                scores["percentage"] = round((scores["score"] / scores["max"]) * 100, 1)
            else:
                scores["percentage"] = 0
        scorecard.category_scores = category_scores

        # Determine grade
        scorecard.grade = self._calculate_grade(scorecard)

    def _calculate_grade(self, scorecard: QAScorecard) -> str:
        """Calculate letter grade from percentage score."""
        # Check for critical failures
        if scorecard.critical_failures:
            return "F"

        pct = scorecard.percentage_score
        if pct >= 90:
            return "A"
        elif pct >= 80:
            return "B"
        elif pct >= 70:
            return "C"
        elif pct >= 60:
            return "D"
        else:
            return "F"

    def _identify_strengths_and_improvements(self, scorecard: QAScorecard):
        """Identify areas of strength and improvement."""
        strengths = []
        improvements = []

        for rs in scorecard.rubric_scores:
            if rs.percentage >= 80:
                strengths.append(f"{rs.rubric_name}: {rs.percentage}%")
            elif rs.percentage < 60:
                improvements.append(f"{rs.rubric_name}: needs improvement ({rs.percentage}%)")

        scorecard.strengths = strengths[:5]  # Top 5
        scorecard.improvement_areas = improvements[:5]  # Top 5

    def get_rubrics_by_category(self, category: str) -> List[QARubric]:
        """Get rubrics for a specific category."""
        return [r for r in self.rubrics if r.category == category]

    def get_compliance_rubrics(self) -> List[QARubric]:
        """Get all compliance-related rubrics."""
        return [r for r in self.rubrics if r.category == "compliance"]


# =============================================================================
# GRADE DISTRIBUTION CALCULATOR
# =============================================================================

class GradeDistributionCalculator:
    """Calculate grade distributions for reporting."""

    @staticmethod
    def calculate_distribution(scorecards: List[QAScorecard]) -> Dict[str, int]:
        """Calculate grade distribution from list of scorecards."""
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for sc in scorecards:
            if sc.grade in distribution:
                distribution[sc.grade] += 1
        return distribution

    @staticmethod
    def calculate_category_averages(scorecards: List[QAScorecard]) -> Dict[str, float]:
        """Calculate average scores by category."""
        category_totals = {}
        category_counts = {}

        for sc in scorecards:
            for cat, scores in sc.category_scores.items():
                if cat not in category_totals:
                    category_totals[cat] = 0
                    category_counts[cat] = 0
                category_totals[cat] += scores.get("percentage", 0)
                category_counts[cat] += 1

        return {
            cat: round(category_totals[cat] / category_counts[cat], 1)
            for cat in category_totals
            if category_counts[cat] > 0
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_qa_scoring_service(rubrics: Optional[List[QARubric]] = None) -> QAScoringService:
    """Get QA scoring service instance."""
    return QAScoringService(rubrics)


def load_rubrics_from_db(db_session) -> List[QARubric]:
    """Load rubrics from database."""
    # This would be implemented to load from ci_qa_rubrics table
    # For now, return default rubrics
    return DEFAULT_RUBRICS
