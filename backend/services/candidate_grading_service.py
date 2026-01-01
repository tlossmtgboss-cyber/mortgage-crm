"""
Candidate Grading Service
Comprehensive LO candidate assessment and grading calculations.

Scoring Categories (weights):
- Production: 45% (volume, units, consistency, growth)
- DISC Personality: 20% (LO-optimized: I=40%, D=30%, S=15%, C=15%)
- Character: 15% (integrity, coachability, resilience, work ethic)
- Skills: 10% (technical, product knowledge, market expertise)
- Culture Fit: 10% (values alignment, team compatibility)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from dataclasses import dataclass, field
import logging
import json

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Category weights
WEIGHT_PRODUCTION = 0.45
WEIGHT_DISC = 0.20
WEIGHT_CHARACTER = 0.15
WEIGHT_SKILLS = 0.10
WEIGHT_CULTURE_FIT = 0.10

# DISC weights for LO role fit (Influence-heavy for relationship building)
DISC_WEIGHT_D = 0.30  # Dominance - drive to close deals
DISC_WEIGHT_I = 0.40  # Influence - relationship building (most important for LO)
DISC_WEIGHT_S = 0.15  # Steadiness - process follow-through
DISC_WEIGHT_C = 0.15  # Conscientiousness - compliance/detail

# Grade thresholds
GRADE_THRESHOLDS = [
    (95, 'A+'), (90, 'A'), (85, 'A-'),
    (80, 'B+'), (75, 'B'), (70, 'B-'),
    (65, 'C+'), (60, 'C'), (55, 'C-'),
    (50, 'D'), (0, 'F')
]

# Production tier benchmarks
VOLUME_TIERS = [
    (100_000_000, 100),  # $100M+ = 100
    (75_000_000, 95),    # $75M+ = 95
    (50_000_000, 85),    # $50M+ = 85
    (25_000_000, 70),    # $25M+ = 70
    (10_000_000, 55),    # $10M+ = 55
    (5_000_000, 40),     # $5M+ = 40
    (0, 25),             # Below $5M = 25
]

UNITS_TIERS = [
    (200, 100),  # 200+ units = 100
    (150, 95),   # 150+ = 95
    (100, 85),   # 100+ = 85
    (75, 75),    # 75+ = 75
    (50, 65),    # 50+ = 65
    (25, 50),    # 25+ = 50
    (0, 30),     # Below 25 = 30
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class GradeResult:
    """Result of a grade calculation."""
    score: float
    grade: str
    color: str = ""

    def __post_init__(self):
        self.color = self._get_color()

    def _get_color(self) -> str:
        if self.grade.startswith('A'):
            return '#10b981'  # Green
        elif self.grade.startswith('B'):
            return '#84cc16'  # Yellow-green
        elif self.grade.startswith('C'):
            return '#f59e0b'  # Orange
        elif self.grade == 'D':
            return '#ef4444'  # Red
        return '#dc2626'  # Dark red (F)


@dataclass
class ProductionScoreResult:
    """Production score calculation result."""
    score: float
    grade: str
    breakdown: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DISCResult:
    """DISC assessment result."""
    composite_score: float
    grade: str
    primary_style: str
    secondary_style: str
    raw_scores: Dict[str, int] = field(default_factory=dict)


@dataclass
class AssessmentSummary:
    """Summary of a candidate assessment."""
    id: int
    candidate_id: int
    overall_score: float
    overall_grade: str
    production_score: Optional[float]
    disc_composite_score: Optional[float]
    character_score: Optional[float]
    skills_score: Optional[float]
    culture_fit_score: Optional[float]
    assessment_status: str
    assessed_at: datetime
    strengths: List[str]
    weaknesses: List[str]


# =============================================================================
# SERVICE CLASS
# =============================================================================

class CandidateGradingService:
    """
    Service for calculating and managing candidate grades.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # GRADE CALCULATION UTILITIES
    # =========================================================================

    @staticmethod
    def get_grade_from_score(score: float) -> str:
        """Convert numeric score to letter grade."""
        if score is None:
            return 'N/A'
        for threshold, grade in GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return 'F'

    @staticmethod
    def get_grade_color(grade: str) -> str:
        """Get color for grade display."""
        if grade.startswith('A'):
            return '#10b981'
        elif grade.startswith('B'):
            return '#84cc16'
        elif grade.startswith('C'):
            return '#f59e0b'
        elif grade == 'D':
            return '#ef4444'
        return '#dc2626'

    @staticmethod
    def get_tier_score(value: float, tiers: List[Tuple[float, int]]) -> int:
        """Get score based on tier thresholds."""
        if value is None:
            return 0
        for threshold, score in tiers:
            if value >= threshold:
                return score
        return tiers[-1][1]

    # =========================================================================
    # PRODUCTION SCORE (45% weight)
    # =========================================================================

    async def calculate_production_score(
        self,
        candidate_id: int,
        annual_volume: Optional[float] = None,
        annual_units: Optional[int] = None,
        production_history: Optional[Dict] = None
    ) -> ProductionScoreResult:
        """
        Calculate production score from volume, units, consistency, growth.

        Components:
        - Annual Volume Score (35% of production)
        - Annual Units Score (25% of production)
        - Consistency Score (20% of production)
        - Growth Trend Score (20% of production)
        """
        # Get candidate production data if not provided
        if annual_volume is None or annual_units is None:
            query = text("""
                SELECT annual_volume, annual_units, production_history
                FROM mm_candidates
                WHERE id = :candidate_id
            """)
            result = self.db.execute(query, {"candidate_id": candidate_id}).fetchone()
            if result:
                annual_volume = float(result.annual_volume or 0)
                annual_units = int(result.annual_units or 0)
                production_history = result.production_history or {}

        annual_volume = annual_volume or 0
        annual_units = annual_units or 0
        production_history = production_history or {}

        # Calculate component scores
        volume_score = self.get_tier_score(annual_volume, VOLUME_TIERS)
        units_score = self.get_tier_score(annual_units, UNITS_TIERS)
        consistency_score = self._calculate_consistency_score(production_history)
        growth_score = self._calculate_growth_score(production_history)

        # Weighted combination
        total_score = (
            volume_score * 0.35 +
            units_score * 0.25 +
            consistency_score * 0.20 +
            growth_score * 0.20
        )

        breakdown = {
            "annual_volume": annual_volume,
            "annual_volume_score": volume_score,
            "annual_units": annual_units,
            "annual_units_score": units_score,
            "consistency_score": consistency_score,
            "growth_trend_score": growth_score,
            "weights": {
                "volume": 0.35,
                "units": 0.25,
                "consistency": 0.20,
                "growth": 0.20
            }
        }

        return ProductionScoreResult(
            score=round(total_score, 1),
            grade=self.get_grade_from_score(total_score),
            breakdown=breakdown
        )

    def _calculate_consistency_score(self, production_history: Dict) -> float:
        """Calculate consistency score from year-over-year variance."""
        if not production_history or not isinstance(production_history, dict):
            return 50  # Default neutral score

        # Extract annual volumes from history
        years_data = production_history.get('years', [])
        if len(years_data) < 2:
            return 60  # Not enough data, slightly above neutral

        volumes = [y.get('volume', 0) for y in years_data if y.get('volume')]
        if len(volumes) < 2:
            return 60

        # Calculate coefficient of variation (lower = more consistent)
        avg = sum(volumes) / len(volumes)
        if avg == 0:
            return 50

        variance = sum((v - avg) ** 2 for v in volumes) / len(volumes)
        std_dev = variance ** 0.5
        cv = std_dev / avg

        # Convert to score (lower CV = higher score)
        # CV of 0 = 100, CV of 0.5 = 50, CV of 1+ = 20
        if cv <= 0.1:
            return 100
        elif cv <= 0.2:
            return 90
        elif cv <= 0.3:
            return 75
        elif cv <= 0.5:
            return 60
        elif cv <= 0.75:
            return 40
        return 25

    def _calculate_growth_score(self, production_history: Dict) -> float:
        """Calculate growth trend score from year-over-year changes."""
        if not production_history or not isinstance(production_history, dict):
            return 50  # Default neutral score

        years_data = production_history.get('years', [])
        if len(years_data) < 2:
            return 60

        # Sort by year and calculate YoY growth
        sorted_years = sorted(years_data, key=lambda x: x.get('year', 0))
        growths = []

        for i in range(1, len(sorted_years)):
            prev_vol = sorted_years[i-1].get('volume', 0)
            curr_vol = sorted_years[i].get('volume', 0)
            if prev_vol > 0:
                growth = (curr_vol - prev_vol) / prev_vol
                growths.append(growth)

        if not growths:
            return 60

        avg_growth = sum(growths) / len(growths)

        # Convert to score
        if avg_growth >= 0.20:  # 20%+ growth
            return 100
        elif avg_growth >= 0.10:  # 10-20% growth
            return 90
        elif avg_growth >= 0.05:  # 5-10% growth
            return 80
        elif avg_growth >= 0:  # 0-5% growth
            return 70
        elif avg_growth >= -0.10:  # 0-10% decline
            return 50
        elif avg_growth >= -0.20:  # 10-20% decline
            return 35
        return 20  # >20% decline

    # =========================================================================
    # DISC SCORE (20% weight)
    # =========================================================================

    def calculate_disc_composite(
        self,
        d: int,
        i: int,
        s: int,
        c: int
    ) -> DISCResult:
        """
        Calculate DISC composite for LO role fit.

        LO-optimized weights:
        - I (Influence): 40% - Critical for relationship building
        - D (Dominance): 30% - Drive to close deals
        - S (Steadiness): 15% - Process follow-through
        - C (Conscientiousness): 15% - Compliance/detail
        """
        d = max(0, min(100, d or 0))
        i = max(0, min(100, i or 0))
        s = max(0, min(100, s or 0))
        c = max(0, min(100, c or 0))

        composite = (
            i * DISC_WEIGHT_I +
            d * DISC_WEIGHT_D +
            s * DISC_WEIGHT_S +
            c * DISC_WEIGHT_C
        )

        # Determine primary and secondary styles
        scores = {'D': d, 'I': i, 'S': s, 'C': c}
        sorted_styles = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        return DISCResult(
            composite_score=round(composite, 1),
            grade=self.get_grade_from_score(composite),
            primary_style=sorted_styles[0][0],
            secondary_style=sorted_styles[1][0],
            raw_scores=scores
        )

    # =========================================================================
    # CHARACTER SCORE (15% weight)
    # =========================================================================

    def calculate_character_score(self, breakdown: Dict[str, Any]) -> GradeResult:
        """
        Calculate character score from component ratings.

        Components (equal weight):
        - Integrity: Honesty, ethics, trustworthiness
        - Coachability: Willingness to learn and accept feedback
        - Resilience: Handling rejection and setbacks
        - Work Ethic: Dedication and effort
        """
        integrity = breakdown.get('integrity_score', 0) or 0
        coachability = breakdown.get('coachability_score', 0) or 0
        resilience = breakdown.get('resilience_score', 0) or 0
        work_ethic = breakdown.get('work_ethic_score', 0) or 0

        # Equal weighting
        score = (integrity + coachability + resilience + work_ethic) / 4

        return GradeResult(
            score=round(score, 1),
            grade=self.get_grade_from_score(score)
        )

    # =========================================================================
    # SKILLS SCORE (10% weight)
    # =========================================================================

    def calculate_skills_score(self, breakdown: Dict[str, Any]) -> GradeResult:
        """
        Calculate skills score from component ratings.

        Components (equal weight):
        - Technical: Loan origination systems, CRM, etc.
        - Product Knowledge: Loan products, guidelines
        - Market Expertise: Local market understanding
        - Technology Proficiency: Digital tools adoption
        """
        technical = breakdown.get('technical_score', 0) or 0
        product_knowledge = breakdown.get('product_knowledge_score', 0) or 0
        market_expertise = breakdown.get('market_expertise_score', 0) or 0
        technology = breakdown.get('technology_proficiency_score', 0) or 0

        score = (technical + product_knowledge + market_expertise + technology) / 4

        return GradeResult(
            score=round(score, 1),
            grade=self.get_grade_from_score(score)
        )

    # =========================================================================
    # CULTURE FIT SCORE (10% weight)
    # =========================================================================

    def calculate_culture_fit_score(self, breakdown: Dict[str, Any]) -> GradeResult:
        """
        Calculate culture fit score from component ratings.

        Components (equal weight):
        - Values Alignment: Match with company values
        - Team Compatibility: Ability to work with existing team
        - Communication Style: Fits company culture
        - Growth Mindset: Desire for improvement
        """
        values = breakdown.get('values_alignment_score', 0) or 0
        team = breakdown.get('team_compatibility_score', 0) or 0
        communication = breakdown.get('communication_style_score', 0) or 0
        growth = breakdown.get('growth_mindset_score', 0) or 0

        score = (values + team + communication + growth) / 4

        return GradeResult(
            score=round(score, 1),
            grade=self.get_grade_from_score(score)
        )

    # =========================================================================
    # OVERALL GRADE CALCULATION
    # =========================================================================

    def calculate_overall_grade(
        self,
        production_score: Optional[float],
        disc_score: Optional[float],
        character_score: Optional[float],
        skills_score: Optional[float],
        culture_fit_score: Optional[float]
    ) -> GradeResult:
        """
        Calculate weighted overall grade.

        Formula:
        Overall = (Production * 0.45) + (DISC * 0.20) + (Character * 0.15)
                  + (Skills * 0.10) + (Culture * 0.10)
        """
        production = production_score or 0
        disc = disc_score or 0
        character = character_score or 0
        skills = skills_score or 0
        culture = culture_fit_score or 0

        overall = (
            production * WEIGHT_PRODUCTION +
            disc * WEIGHT_DISC +
            character * WEIGHT_CHARACTER +
            skills * WEIGHT_SKILLS +
            culture * WEIGHT_CULTURE_FIT
        )

        return GradeResult(
            score=round(overall, 1),
            grade=self.get_grade_from_score(overall)
        )

    # =========================================================================
    # ASSESSMENT CRUD OPERATIONS
    # =========================================================================

    async def create_assessment(
        self,
        candidate_id: int,
        organization_id: Optional[int],
        assessed_by: int,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new assessment for a candidate."""

        # Calculate all component scores
        production_result = None
        if data.get('production_breakdown'):
            production_result = await self.calculate_production_score(
                candidate_id,
                data['production_breakdown'].get('annual_volume'),
                data['production_breakdown'].get('annual_units'),
                data['production_breakdown'].get('production_history')
            )

        disc_result = None
        if all(k in data for k in ['disc_d_score', 'disc_i_score', 'disc_s_score', 'disc_c_score']):
            disc_result = self.calculate_disc_composite(
                data['disc_d_score'],
                data['disc_i_score'],
                data['disc_s_score'],
                data['disc_c_score']
            )

        character_result = self.calculate_character_score(
            data.get('character_breakdown', {})
        )

        skills_result = self.calculate_skills_score(
            data.get('skills_breakdown', {})
        )

        culture_result = self.calculate_culture_fit_score(
            data.get('culture_fit_breakdown', {})
        )

        # Calculate overall
        overall_result = self.calculate_overall_grade(
            production_result.score if production_result else data.get('production_score'),
            disc_result.composite_score if disc_result else data.get('disc_composite_score'),
            character_result.score if data.get('character_breakdown') else data.get('character_score'),
            skills_result.score if data.get('skills_breakdown') else data.get('skills_score'),
            culture_result.score if data.get('culture_fit_breakdown') else data.get('culture_fit_score')
        )

        # Insert assessment
        insert_query = text("""
            INSERT INTO mm_candidate_assessments (
                organization_id, candidate_id, assessed_by, assessment_status,
                production_score, production_grade, production_breakdown,
                disc_d_score, disc_i_score, disc_s_score, disc_c_score,
                disc_primary_style, disc_secondary_style, disc_composite_score, disc_grade,
                disc_notes, disc_assessment_source,
                character_score, character_grade, character_breakdown,
                skills_score, skills_grade, skills_breakdown,
                culture_fit_score, culture_fit_grade, culture_fit_breakdown,
                overall_score, overall_grade,
                strengths, weaknesses, recruiter_notes, recruiter_recommendation
            ) VALUES (
                :org_id, :candidate_id, :assessed_by, :status,
                :production_score, :production_grade, :production_breakdown,
                :disc_d, :disc_i, :disc_s, :disc_c,
                :disc_primary, :disc_secondary, :disc_composite, :disc_grade,
                :disc_notes, :disc_source,
                :character_score, :character_grade, :character_breakdown,
                :skills_score, :skills_grade, :skills_breakdown,
                :culture_score, :culture_grade, :culture_breakdown,
                :overall_score, :overall_grade,
                :strengths, :weaknesses, :notes, :recommendation
            )
            RETURNING id, assessed_at
        """)

        result = self.db.execute(insert_query, {
            "org_id": organization_id,
            "candidate_id": candidate_id,
            "assessed_by": assessed_by,
            "status": data.get('assessment_status', 'draft'),
            "production_score": production_result.score if production_result else data.get('production_score'),
            "production_grade": production_result.grade if production_result else self.get_grade_from_score(data.get('production_score')),
            "production_breakdown": json.dumps(production_result.breakdown if production_result else data.get('production_breakdown', {})),
            "disc_d": data.get('disc_d_score', 0),
            "disc_i": data.get('disc_i_score', 0),
            "disc_s": data.get('disc_s_score', 0),
            "disc_c": data.get('disc_c_score', 0),
            "disc_primary": disc_result.primary_style if disc_result else data.get('disc_primary_style'),
            "disc_secondary": disc_result.secondary_style if disc_result else data.get('disc_secondary_style'),
            "disc_composite": disc_result.composite_score if disc_result else data.get('disc_composite_score'),
            "disc_grade": disc_result.grade if disc_result else self.get_grade_from_score(data.get('disc_composite_score')),
            "disc_notes": data.get('disc_notes'),
            "disc_source": data.get('disc_assessment_source', 'manual'),
            "character_score": character_result.score if data.get('character_breakdown') else data.get('character_score'),
            "character_grade": character_result.grade if data.get('character_breakdown') else self.get_grade_from_score(data.get('character_score')),
            "character_breakdown": json.dumps(data.get('character_breakdown', {})),
            "skills_score": skills_result.score if data.get('skills_breakdown') else data.get('skills_score'),
            "skills_grade": skills_result.grade if data.get('skills_breakdown') else self.get_grade_from_score(data.get('skills_score')),
            "skills_breakdown": json.dumps(data.get('skills_breakdown', {})),
            "culture_score": culture_result.score if data.get('culture_fit_breakdown') else data.get('culture_fit_score'),
            "culture_grade": culture_result.grade if data.get('culture_fit_breakdown') else self.get_grade_from_score(data.get('culture_fit_score')),
            "culture_breakdown": json.dumps(data.get('culture_fit_breakdown', {})),
            "overall_score": overall_result.score,
            "overall_grade": overall_result.grade,
            "strengths": data.get('strengths', []),
            "weaknesses": data.get('weaknesses', []),
            "notes": data.get('recruiter_notes'),
            "recommendation": data.get('recruiter_recommendation')
        }).fetchone()

        assessment_id = result.id

        # Update candidate with current assessment
        self.db.execute(text("""
            UPDATE mm_candidates
            SET current_assessment_id = :assessment_id,
                current_grade = :grade,
                grade_updated_at = CURRENT_TIMESTAMP,
                disc_primary_style = :disc_primary
            WHERE id = :candidate_id
        """), {
            "assessment_id": assessment_id,
            "grade": overall_result.grade,
            "disc_primary": disc_result.primary_style if disc_result else data.get('disc_primary_style'),
            "candidate_id": candidate_id
        })

        # Create history entry
        await self._create_history_entry(
            candidate_id=candidate_id,
            assessment_id=assessment_id,
            organization_id=organization_id,
            change_type='initial',
            changed_by=assessed_by,
            scores={
                'production': production_result.score if production_result else data.get('production_score'),
                'disc': disc_result.composite_score if disc_result else data.get('disc_composite_score'),
                'character': character_result.score if data.get('character_breakdown') else data.get('character_score'),
                'skills': skills_result.score if data.get('skills_breakdown') else data.get('skills_score'),
                'culture': culture_result.score if data.get('culture_fit_breakdown') else data.get('culture_fit_score'),
                'overall': overall_result.score,
                'overall_grade': overall_result.grade
            }
        )

        self.db.commit()

        return {
            "id": assessment_id,
            "candidate_id": candidate_id,
            "overall_score": overall_result.score,
            "overall_grade": overall_result.grade,
            "assessed_at": result.assessed_at.isoformat() if result.assessed_at else None,
            "message": "Assessment created successfully"
        }

    async def get_assessment(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        """Get the current assessment for a candidate."""
        query = text("""
            SELECT
                a.*,
                u.name as assessor_name
            FROM mm_candidate_assessments a
            LEFT JOIN users u ON u.id = a.assessed_by
            WHERE a.candidate_id = :candidate_id
            ORDER BY a.assessed_at DESC
            LIMIT 1
        """)

        result = self.db.execute(query, {"candidate_id": candidate_id}).fetchone()

        if not result:
            return None

        return {
            "id": result.id,
            "candidate_id": result.candidate_id,
            "assessment_status": result.assessment_status,
            "assessed_at": result.assessed_at.isoformat() if result.assessed_at else None,
            "assessor_name": result.assessor_name,
            "production": {
                "score": result.production_score,
                "grade": result.production_grade,
                "breakdown": result.production_breakdown or {},
                "weight": WEIGHT_PRODUCTION
            },
            "disc": {
                "d_score": result.disc_d_score,
                "i_score": result.disc_i_score,
                "s_score": result.disc_s_score,
                "c_score": result.disc_c_score,
                "primary_style": result.disc_primary_style,
                "secondary_style": result.disc_secondary_style,
                "composite_score": result.disc_composite_score,
                "grade": result.disc_grade,
                "notes": result.disc_notes,
                "source": result.disc_assessment_source,
                "weight": WEIGHT_DISC
            },
            "character": {
                "score": result.character_score,
                "grade": result.character_grade,
                "breakdown": result.character_breakdown or {},
                "weight": WEIGHT_CHARACTER
            },
            "skills": {
                "score": result.skills_score,
                "grade": result.skills_grade,
                "breakdown": result.skills_breakdown or {},
                "weight": WEIGHT_SKILLS
            },
            "culture_fit": {
                "score": result.culture_fit_score,
                "grade": result.culture_fit_grade,
                "breakdown": result.culture_fit_breakdown or {},
                "weight": WEIGHT_CULTURE_FIT
            },
            "overall": {
                "score": result.overall_score,
                "grade": result.overall_grade,
                "color": self.get_grade_color(result.overall_grade or 'F')
            },
            "strengths": result.strengths or [],
            "weaknesses": result.weaknesses or [],
            "recruiter_notes": result.recruiter_notes,
            "recruiter_recommendation": result.recruiter_recommendation,
            "ai_analysis": {
                "run_at": result.ai_analysis_run_at.isoformat() if result.ai_analysis_run_at else None,
                "confidence_score": result.ai_confidence_score,
                "raw_analysis": result.ai_raw_analysis or {}
            },
            "override": {
                "overridden": result.scores_overridden,
                "reason": result.override_reason,
                "original_scores": result.original_scores
            }
        }

    async def update_assessment(
        self,
        assessment_id: int,
        data: Dict[str, Any],
        updated_by: int
    ) -> Dict[str, Any]:
        """Update an existing assessment."""
        # Get current assessment
        current = self.db.execute(text("""
            SELECT * FROM mm_candidate_assessments WHERE id = :id
        """), {"id": assessment_id}).fetchone()

        if not current:
            raise ValueError(f"Assessment {assessment_id} not found")

        # Recalculate scores if breakdowns provided
        production_score = data.get('production_score', current.production_score)
        disc_composite = data.get('disc_composite_score', current.disc_composite_score)
        character_score = data.get('character_score', current.character_score)
        skills_score = data.get('skills_score', current.skills_score)
        culture_score = data.get('culture_fit_score', current.culture_fit_score)

        # Recalculate DISC if individual scores provided
        if any(k in data for k in ['disc_d_score', 'disc_i_score', 'disc_s_score', 'disc_c_score']):
            disc_result = self.calculate_disc_composite(
                data.get('disc_d_score', current.disc_d_score),
                data.get('disc_i_score', current.disc_i_score),
                data.get('disc_s_score', current.disc_s_score),
                data.get('disc_c_score', current.disc_c_score)
            )
            disc_composite = disc_result.composite_score
            data['disc_primary_style'] = disc_result.primary_style
            data['disc_secondary_style'] = disc_result.secondary_style
            data['disc_grade'] = disc_result.grade

        # Recalculate character if breakdown provided
        if 'character_breakdown' in data:
            char_result = self.calculate_character_score(data['character_breakdown'])
            character_score = char_result.score
            data['character_grade'] = char_result.grade

        # Recalculate skills if breakdown provided
        if 'skills_breakdown' in data:
            skills_result = self.calculate_skills_score(data['skills_breakdown'])
            skills_score = skills_result.score
            data['skills_grade'] = skills_result.grade

        # Recalculate culture if breakdown provided
        if 'culture_fit_breakdown' in data:
            culture_result = self.calculate_culture_fit_score(data['culture_fit_breakdown'])
            culture_score = culture_result.score
            data['culture_fit_grade'] = culture_result.grade

        # Calculate new overall
        overall_result = self.calculate_overall_grade(
            production_score, disc_composite, character_score, skills_score, culture_score
        )

        # Build update query dynamically
        updates = []
        params = {"id": assessment_id}

        field_mappings = {
            'production_score': 'production_score',
            'production_grade': 'production_grade',
            'production_breakdown': 'production_breakdown',
            'disc_d_score': 'disc_d_score',
            'disc_i_score': 'disc_i_score',
            'disc_s_score': 'disc_s_score',
            'disc_c_score': 'disc_c_score',
            'disc_primary_style': 'disc_primary_style',
            'disc_secondary_style': 'disc_secondary_style',
            'disc_composite_score': 'disc_composite_score',
            'disc_grade': 'disc_grade',
            'disc_notes': 'disc_notes',
            'character_score': 'character_score',
            'character_grade': 'character_grade',
            'character_breakdown': 'character_breakdown',
            'skills_score': 'skills_score',
            'skills_grade': 'skills_grade',
            'skills_breakdown': 'skills_breakdown',
            'culture_fit_score': 'culture_fit_score',
            'culture_fit_grade': 'culture_fit_grade',
            'culture_fit_breakdown': 'culture_fit_breakdown',
            'strengths': 'strengths',
            'weaknesses': 'weaknesses',
            'recruiter_notes': 'recruiter_notes',
            'recruiter_recommendation': 'recruiter_recommendation',
            'assessment_status': 'assessment_status'
        }

        for key, col in field_mappings.items():
            if key in data:
                value = data[key]
                if isinstance(value, dict):
                    value = json.dumps(value)
                updates.append(f"{col} = :{key}")
                params[key] = value

        # Always update overall score
        updates.extend([
            "overall_score = :overall_score",
            "overall_grade = :overall_grade",
            "updated_at = CURRENT_TIMESTAMP"
        ])
        params["overall_score"] = overall_result.score
        params["overall_grade"] = overall_result.grade

        if updates:
            update_sql = f"UPDATE mm_candidate_assessments SET {', '.join(updates)} WHERE id = :id"
            self.db.execute(text(update_sql), params)

        # Update candidate
        self.db.execute(text("""
            UPDATE mm_candidates
            SET current_grade = :grade,
                grade_updated_at = CURRENT_TIMESTAMP,
                disc_primary_style = :disc_primary
            WHERE id = :candidate_id
        """), {
            "grade": overall_result.grade,
            "disc_primary": data.get('disc_primary_style', current.disc_primary_style),
            "candidate_id": current.candidate_id
        })

        # Create history entry
        await self._create_history_entry(
            candidate_id=current.candidate_id,
            assessment_id=assessment_id,
            organization_id=current.organization_id,
            change_type='update',
            changed_by=updated_by,
            scores={
                'production': production_score,
                'disc': disc_composite,
                'character': character_score,
                'skills': skills_score,
                'culture': culture_score,
                'overall': overall_result.score,
                'overall_grade': overall_result.grade
            }
        )

        self.db.commit()

        return {
            "id": assessment_id,
            "overall_score": overall_result.score,
            "overall_grade": overall_result.grade,
            "message": "Assessment updated successfully"
        }

    async def get_assessment_history(self, candidate_id: int) -> List[Dict[str, Any]]:
        """Get assessment history for a candidate."""
        query = text("""
            SELECT
                h.*,
                u.first_name || ' ' || u.last_name as changed_by_name
            FROM mm_assessment_history h
            LEFT JOIN users u ON u.id = h.changed_by
            WHERE h.candidate_id = :candidate_id
            ORDER BY h.snapshot_at DESC
        """)

        results = self.db.execute(query, {"candidate_id": candidate_id}).fetchall()

        return [
            {
                "id": r.id,
                "snapshot_at": r.snapshot_at.isoformat() if r.snapshot_at else None,
                "production_score": r.production_score,
                "disc_composite_score": r.disc_composite_score,
                "character_score": r.character_score,
                "skills_score": r.skills_score,
                "culture_fit_score": r.culture_fit_score,
                "overall_score": r.overall_score,
                "overall_grade": r.overall_grade,
                "change_type": r.change_type,
                "changed_by_name": r.changed_by_name,
                "change_notes": r.change_notes
            }
            for r in results
        ]

    async def _create_history_entry(
        self,
        candidate_id: int,
        assessment_id: int,
        organization_id: Optional[int],
        change_type: str,
        changed_by: int,
        scores: Dict[str, Any],
        notes: str = None
    ):
        """Create a history entry for assessment changes."""
        self.db.execute(text("""
            INSERT INTO mm_assessment_history (
                organization_id, candidate_id, assessment_id,
                production_score, disc_composite_score, character_score,
                skills_score, culture_fit_score, overall_score, overall_grade,
                change_type, changed_by, change_notes, full_snapshot
            ) VALUES (
                :org_id, :candidate_id, :assessment_id,
                :production, :disc, :character,
                :skills, :culture, :overall, :grade,
                :change_type, :changed_by, :notes, :snapshot
            )
        """), {
            "org_id": organization_id,
            "candidate_id": candidate_id,
            "assessment_id": assessment_id,
            "production": scores.get('production'),
            "disc": scores.get('disc'),
            "character": scores.get('character'),
            "skills": scores.get('skills'),
            "culture": scores.get('culture'),
            "overall": scores.get('overall'),
            "grade": scores.get('overall_grade'),
            "change_type": change_type,
            "changed_by": changed_by,
            "notes": notes,
            "snapshot": json.dumps(scores)
        })

    # =========================================================================
    # OVERRIDE MANAGEMENT
    # =========================================================================

    async def override_scores(
        self,
        assessment_id: int,
        override_by: int,
        override_reason: str,
        new_scores: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Override AI-suggested scores with manual values."""
        # Get current assessment
        current = self.db.execute(text("""
            SELECT * FROM mm_candidate_assessments WHERE id = :id
        """), {"id": assessment_id}).fetchone()

        if not current:
            raise ValueError(f"Assessment {assessment_id} not found")

        # Store original scores
        original_scores = {
            "production_score": current.production_score,
            "disc_composite_score": current.disc_composite_score,
            "character_score": current.character_score,
            "skills_score": current.skills_score,
            "culture_fit_score": current.culture_fit_score,
            "overall_score": current.overall_score,
            "overall_grade": current.overall_grade
        }

        # Update with new scores
        new_scores['original_scores'] = original_scores
        result = await self.update_assessment(assessment_id, new_scores, override_by)

        # Mark as overridden
        self.db.execute(text("""
            UPDATE mm_candidate_assessments
            SET scores_overridden = true,
                override_reason = :reason,
                override_by = :by,
                override_at = CURRENT_TIMESTAMP,
                original_scores = :original
            WHERE id = :id
        """), {
            "id": assessment_id,
            "reason": override_reason,
            "by": override_by,
            "original": json.dumps(original_scores)
        })

        self.db.commit()

        return {
            "id": assessment_id,
            "message": "Scores overridden successfully",
            "original_scores": original_scores,
            "new_overall_score": result['overall_score'],
            "new_overall_grade": result['overall_grade']
        }
