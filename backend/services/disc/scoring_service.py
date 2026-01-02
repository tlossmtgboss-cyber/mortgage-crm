"""
DISC Scoring Service

Implements DISC scoring algorithms including:
- Forced-choice response processing
- Ipsative normalization
- Adapted vs Natural style calculation
- Primary/Secondary type determination
- Calibration and consistency scoring
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import statistics


class DISCDimension(str, Enum):
    D = "D"  # Dominance
    I = "I"  # Influence
    S = "S"  # Steadiness
    C = "C"  # Conscientiousness


class QualityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class DISCScores:
    """Raw DISC dimension scores."""
    d: int
    i: int
    s: int
    c: int

    def to_dict(self) -> Dict[str, int]:
        return {"D": self.d, "I": self.i, "S": self.s, "C": self.c}

    def as_list(self) -> List[int]:
        return [self.d, self.i, self.s, self.c]


@dataclass
class DISCResult:
    """Complete DISC result with both styles."""
    adapted: DISCScores
    natural: DISCScores
    adapted_style: str
    natural_style: str
    combined_style: str
    calibration_score: float
    consistency_score: float
    response_time_score: float
    quality_tier: QualityTier
    quality_notes: Optional[str] = None


class DISCScoringService:
    """Service for scoring DISC assessments."""

    # Threshold for including secondary style (within X% of primary)
    SECONDARY_THRESHOLD = 0.70

    # Time thresholds for response quality (in milliseconds)
    MIN_RESPONSE_TIME_MS = 1500  # Too fast = not reading
    MAX_RESPONSE_TIME_MS = 60000  # Too slow = distracted

    def __init__(self):
        pass

    def score_responses(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> DISCResult:
        """
        Score a complete set of DISC responses.

        Args:
            responses: List of response objects with {question_id, response_value, response_time_ms}
            questions: List of question objects with {id, options, question_type}

        Returns:
            DISCResult with computed scores and styles
        """
        # Separate MOST and LEAST responses for adapted vs natural
        most_scores = {"D": 0, "I": 0, "S": 0, "C": 0}
        least_scores = {"D": 0, "I": 0, "S": 0, "C": 0}

        question_map = {q["id"]: q for q in questions}

        for response in responses:
            question = question_map.get(response.get("question_id"))
            if not question or question.get("question_section") != "disc":
                continue

            response_value = response.get("response_value", {})
            options = question.get("options", [])
            option_map = {opt["id"]: opt for opt in options}

            # Process MOST selection (contributes to Adapted style)
            most_id = response_value.get("most")
            if most_id and most_id in option_map:
                dimension = option_map[most_id].get("dimension")
                weight = option_map[most_id].get("weight", 1)
                if dimension in most_scores:
                    most_scores[dimension] += weight

            # Process LEAST selection (contributes to Natural style calculation)
            least_id = response_value.get("least")
            if least_id and least_id in option_map:
                dimension = option_map[least_id].get("dimension")
                weight = option_map[least_id].get("weight", 1)
                if dimension in least_scores:
                    least_scores[dimension] += weight

        # Normalize to 0-100 scale
        adapted_scores = self._normalize_scores(most_scores, len(responses))
        natural_scores = self._calculate_natural_from_least(most_scores, least_scores, len(responses))

        # Calculate quality metrics
        response_times = [r.get("response_time_ms", 5000) for r in responses]
        calibration = self._calculate_calibration_score(responses, questions)
        consistency = self._calculate_consistency_score(responses, questions)
        time_score = self._calculate_response_time_score(response_times)

        # Determine quality tier
        avg_quality = (calibration + consistency + time_score) / 3
        if avg_quality >= 0.8:
            quality_tier = QualityTier.HIGH
            quality_notes = None
        elif avg_quality >= 0.6:
            quality_tier = QualityTier.MEDIUM
            quality_notes = "Some responses may be inconsistent. Interpret with care."
        else:
            quality_tier = QualityTier.LOW
            quality_notes = "Assessment quality is low. Consider retaking for more accurate results."

        # Determine style codes
        adapted_style = self._determine_style(adapted_scores)
        natural_style = self._determine_style(natural_scores)
        combined_style = f"{adapted_style}/{natural_style}"

        return DISCResult(
            adapted=adapted_scores,
            natural=natural_scores,
            adapted_style=adapted_style,
            natural_style=natural_style,
            combined_style=combined_style,
            calibration_score=round(calibration, 2),
            consistency_score=round(consistency, 2),
            response_time_score=round(time_score, 2),
            quality_tier=quality_tier,
            quality_notes=quality_notes,
        )

    def _normalize_scores(self, raw_scores: Dict[str, int], num_questions: int) -> DISCScores:
        """Normalize raw scores to 0-100 scale using ipsative method."""
        total = sum(raw_scores.values())
        if total == 0:
            return DISCScores(d=50, i=50, s=50, c=50)

        # Ipsative: scale based on relative proportions
        max_possible = num_questions  # Max 1 point per question per dimension

        # Calculate percentages relative to total selections
        scores = {}
        for dim in ["D", "I", "S", "C"]:
            # Scale to 0-100 where 100 means all selections were this dimension
            scores[dim] = min(100, int((raw_scores[dim] / max(total, 1)) * 100 * 2))

        return DISCScores(
            d=scores["D"],
            i=scores["I"],
            s=scores["S"],
            c=scores["C"]
        )

    def _calculate_natural_from_least(
        self,
        most_scores: Dict[str, int],
        least_scores: Dict[str, int],
        num_questions: int
    ) -> DISCScores:
        """
        Calculate Natural style using inverse of LEAST selections.

        Natural style = What you naturally are when not adapting
        The things you pick as LEAST like you in a work context
        often indicate what you suppress from your natural self.
        """
        # Natural style is computed from what you DON'T pick as MOST
        # and inversely weighted by what you pick as LEAST
        natural_raw = {"D": 0, "I": 0, "S": 0, "C": 0}

        for dim in ["D", "I", "S", "C"]:
            # Start with inverse of most selections
            # Then add the least selections (what you reject = what's less natural at work)
            natural_raw[dim] = (num_questions - most_scores.get(dim, 0)) + least_scores.get(dim, 0)

        return self._normalize_scores(natural_raw, num_questions * 2)

    def _determine_style(self, scores: DISCScores) -> str:
        """
        Determine style code from scores.

        Returns style like "DI", "ISc", "C", etc.
        Primary dimension is uppercase, secondary lowercase if within threshold.
        """
        dims = [
            ("D", scores.d),
            ("I", scores.i),
            ("S", scores.s),
            ("C", scores.c)
        ]

        # Sort by score descending
        dims.sort(key=lambda x: x[1], reverse=True)

        primary = dims[0]
        secondary = dims[1]

        # Check if secondary is within threshold of primary
        if primary[1] > 0 and secondary[1] >= primary[1] * self.SECONDARY_THRESHOLD:
            return f"{primary[0]}{secondary[0].lower()}"
        else:
            return primary[0]

    def _calculate_calibration_score(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> float:
        """
        Calculate calibration score based on response patterns.

        Checks for:
        - Avoiding all same selections (e.g., always picking first option)
        - Proper distribution across dimensions
        """
        if not responses:
            return 0.5

        # Check for position bias (always picking same position)
        positions = []
        for response in responses:
            rv = response.get("response_value", {})
            most = rv.get("most", "")
            if most:
                # Extract position from option ID (e.g., "1a" -> "a")
                positions.append(most[-1] if len(most) > 0 else "")

        if positions:
            # Check how evenly distributed positions are
            position_counts = {}
            for p in positions:
                position_counts[p] = position_counts.get(p, 0) + 1

            # Ideal: each position selected ~25% of time
            expected = len(positions) / 4
            variance = sum((count - expected) ** 2 for count in position_counts.values())
            max_variance = (len(positions) - expected) ** 2 * 3 + expected ** 2
            position_score = 1 - min(1, variance / max(max_variance, 1))
        else:
            position_score = 0.5

        return position_score

    def _calculate_consistency_score(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> float:
        """
        Calculate consistency score.

        For now, checks that MOST and LEAST selections are different.
        Could be extended to check paired/calibration questions.
        """
        valid_responses = 0
        consistent_responses = 0

        for response in responses:
            rv = response.get("response_value", {})
            most = rv.get("most")
            least = rv.get("least")

            if most and least:
                valid_responses += 1
                if most != least:
                    consistent_responses += 1

        if valid_responses == 0:
            return 0.5

        return consistent_responses / valid_responses

    def _calculate_response_time_score(self, response_times: List[int]) -> float:
        """
        Calculate response time quality score.

        Penalizes responses that are too fast (not reading)
        or too slow (distracted).
        """
        if not response_times:
            return 0.5

        good_responses = 0
        for time_ms in response_times:
            if self.MIN_RESPONSE_TIME_MS <= time_ms <= self.MAX_RESPONSE_TIME_MS:
                good_responses += 1

        return good_responses / len(response_times)

    def get_style_description(self, style: str) -> Dict[str, str]:
        """Get description for a DISC style code."""
        descriptions = {
            "D": {
                "name": "Dominant",
                "short": "Results-oriented, direct, decisive",
                "description": "You are driven by results and prefer to take charge of situations. You value efficiency and getting things done quickly."
            },
            "Di": {
                "name": "Dominant-Influencer",
                "short": "Assertive, dynamic, competitive",
                "description": "You combine drive for results with enthusiasm and people skills. You're energetic and enjoy both winning and recognition."
            },
            "Dc": {
                "name": "Dominant-Conscientious",
                "short": "Determined, analytical, systematic",
                "description": "You combine ambition with attention to quality. You want to achieve results but ensure they meet high standards."
            },
            "I": {
                "name": "Influencer",
                "short": "Enthusiastic, optimistic, collaborative",
                "description": "You are people-oriented and energized by social interaction. You're persuasive and excel at motivating others."
            },
            "Id": {
                "name": "Influencer-Dominant",
                "short": "Charismatic, confident, inspiring",
                "description": "You combine people skills with drive. You're a natural leader who inspires others toward goals."
            },
            "Is": {
                "name": "Influencer-Steady",
                "short": "Warm, supportive, encouraging",
                "description": "You combine enthusiasm with patience. You build strong relationships and create harmonious environments."
            },
            "S": {
                "name": "Steady",
                "short": "Patient, reliable, team-oriented",
                "description": "You value stability and harmony. You're supportive, patient, and excel at creating consistent results."
            },
            "Si": {
                "name": "Steady-Influencer",
                "short": "Supportive, friendly, cooperative",
                "description": "You combine patience with warmth. You're a team player who builds consensus and supports others."
            },
            "Sc": {
                "name": "Steady-Conscientious",
                "short": "Reliable, thorough, methodical",
                "description": "You combine stability with attention to detail. You're dependable and produce consistent, quality work."
            },
            "C": {
                "name": "Conscientious",
                "short": "Analytical, precise, quality-focused",
                "description": "You value accuracy and quality. You're systematic, analytical, and prefer to thoroughly understand before acting."
            },
            "Cd": {
                "name": "Conscientious-Dominant",
                "short": "Exacting, driving, perfectionist",
                "description": "You combine quality standards with drive. You push for excellent results and hold high expectations."
            },
            "Cs": {
                "name": "Conscientious-Steady",
                "short": "Careful, patient, methodical",
                "description": "You combine analysis with patience. You thoroughly evaluate before acting and prefer stable processes."
            },
        }

        # Handle any style by finding the best match
        if style in descriptions:
            return descriptions[style]

        # Try primary only
        primary = style[0] if style else "S"
        return descriptions.get(primary, descriptions["S"])
