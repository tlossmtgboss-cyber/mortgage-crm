"""
Motivators Scoring Service

Implements 7-dimension Motivators scoring:
- Aesthetic: Beauty, balance, harmony
- Economic: ROI, practicality, results
- Individualistic: Independence, uniqueness
- Political: Control, influence, power
- Altruistic: Service, helping others
- Regulatory: Order, structure, tradition
- Theoretical: Knowledge, learning, truth
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class MotivatorDimension(str, Enum):
    AESTHETIC = "aesthetic"
    ECONOMIC = "economic"
    INDIVIDUALISTIC = "individualistic"
    POLITICAL = "political"
    ALTRUISTIC = "altruistic"
    REGULATORY = "regulatory"
    THEORETICAL = "theoretical"


@dataclass
class MotivatorScores:
    """7-dimension Motivator scores."""
    aesthetic: int
    economic: int
    individualistic: int
    political: int
    altruistic: int
    regulatory: int
    theoretical: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "aesthetic": self.aesthetic,
            "economic": self.economic,
            "individualistic": self.individualistic,
            "political": self.political,
            "altruistic": self.altruistic,
            "regulatory": self.regulatory,
            "theoretical": self.theoretical,
        }

    def get_ranking(self) -> Dict[str, int]:
        """Get ranking from highest (1) to lowest (7)."""
        scores = self.to_dict()
        sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return {dim: rank + 1 for rank, (dim, _) in enumerate(sorted_dims)}

    def get_top_motivators(self, n: int = 2) -> List[str]:
        """Get top N motivator dimensions."""
        scores = self.to_dict()
        sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [dim for dim, _ in sorted_dims[:n]]

    def get_lowest_motivator(self) -> str:
        """Get lowest motivator dimension."""
        scores = self.to_dict()
        return min(scores.items(), key=lambda x: x[1])[0]


@dataclass
class MotivatorResult:
    """Complete Motivator assessment result."""
    scores: MotivatorScores
    ranking: Dict[str, int]
    top_motivator: str
    second_motivator: str
    lowest_motivator: str


class MotivatorsService:
    """Service for scoring Motivators assessments."""

    # Dimension descriptions
    DIMENSION_INFO = {
        "aesthetic": {
            "name": "Aesthetic",
            "description": "Driven by beauty, balance, form, and harmony",
            "high_description": "You have a strong appreciation for beauty and creative expression. You're drawn to experiences that engage your senses and emotions, and you value design, aesthetics, and artistic endeavors.",
            "low_description": "Aesthetic considerations are less important to you than practical outcomes. You focus more on functionality and results than on form or artistic expression.",
            "keywords": ["beauty", "creativity", "harmony", "expression", "design", "art"],
        },
        "economic": {
            "name": "Economic",
            "description": "Driven by ROI, practicality, and tangible results",
            "high_description": "You are highly practical and focused on return on investment. You evaluate opportunities based on their potential for financial success and measurable outcomes.",
            "low_description": "You're less motivated by financial gain and more focused on other values. You may prioritize purpose, relationships, or knowledge over monetary rewards.",
            "keywords": ["practical", "results", "ROI", "efficiency", "wealth", "tangible"],
        },
        "individualistic": {
            "name": "Individualistic",
            "description": "Driven by independence, uniqueness, and personal distinction",
            "high_description": "You value standing out from the crowd and being recognized for your unique contributions. You prefer to carve your own path and are motivated by personal achievement.",
            "low_description": "You're comfortable being part of a team and don't need to stand out. You may prioritize collective success over individual recognition.",
            "keywords": ["independence", "uniqueness", "recognition", "distinction", "personal", "achievement"],
        },
        "political": {
            "name": "Political",
            "description": "Driven by control, influence, and positions of power",
            "high_description": "You are motivated by opportunities to lead and influence others. You enjoy positions of authority and are energized by building power and having control over your environment.",
            "low_description": "You're less interested in formal power or control. You may prefer collaborative approaches and don't seek leadership positions for their own sake.",
            "keywords": ["control", "influence", "power", "leadership", "authority", "position"],
        },
        "altruistic": {
            "name": "Altruistic",
            "description": "Driven by service to others and making a positive difference",
            "high_description": "Helping others succeed brings you deep satisfaction. You're motivated by opportunities to serve, support, and make a positive impact in people's lives.",
            "low_description": "While you care about others, helping isn't your primary motivator. You may focus more on personal goals or believe that people should help themselves.",
            "keywords": ["service", "helping", "support", "giving", "difference", "others"],
        },
        "regulatory": {
            "name": "Regulatory",
            "description": "Driven by order, structure, tradition, and established systems",
            "high_description": "You value following established rules and traditions. Structure and order are essential for you, and you believe in upholding standards and maintaining systems.",
            "low_description": "You're more flexible about rules and traditions. You may prefer to adapt approaches based on circumstances rather than follow rigid structures.",
            "keywords": ["order", "structure", "rules", "tradition", "standards", "systems"],
        },
        "theoretical": {
            "name": "Theoretical",
            "description": "Driven by knowledge, learning, and the pursuit of truth",
            "high_description": "You have a strong desire to understand how things work. Learning new concepts and discovering underlying principles brings you deep satisfaction.",
            "low_description": "You're more focused on practical application than theoretical understanding. You prefer learning that has immediate, tangible utility.",
            "keywords": ["knowledge", "learning", "understanding", "truth", "analysis", "discovery"],
        },
    }

    def __init__(self):
        pass

    def score_responses(
        self,
        responses: List[Dict],
        questions: List[Dict]
    ) -> MotivatorResult:
        """
        Score Motivator responses using Likert scale aggregation.

        Args:
            responses: List of response objects with {question_id, response_value}
            questions: List of question objects with {id, dimension_measured}

        Returns:
            MotivatorResult with scores and rankings
        """
        question_map = {q["id"]: q for q in questions}

        # Aggregate scores by dimension
        dimension_scores = {dim.value: [] for dim in MotivatorDimension}

        for response in responses:
            question = question_map.get(response.get("question_id"))
            if not question or question.get("question_section") != "motivator":
                continue

            dimension = question.get("dimension_measured")
            if dimension not in dimension_scores:
                continue

            # Get Likert value (1-7)
            response_value = response.get("response_value", {})
            value = response_value.get("value")
            if value is not None:
                dimension_scores[dimension].append(int(value))

        # Calculate average for each dimension and normalize to 0-100
        final_scores = {}
        for dim, values in dimension_scores.items():
            if values:
                avg = sum(values) / len(values)
                # Convert 1-7 scale to 0-100
                # 1 = 0, 4 = 50, 7 = 100
                normalized = int((avg - 1) / 6 * 100)
                final_scores[dim] = max(0, min(100, normalized))
            else:
                final_scores[dim] = 50  # Default to neutral

        scores = MotivatorScores(
            aesthetic=final_scores["aesthetic"],
            economic=final_scores["economic"],
            individualistic=final_scores["individualistic"],
            political=final_scores["political"],
            altruistic=final_scores["altruistic"],
            regulatory=final_scores["regulatory"],
            theoretical=final_scores["theoretical"],
        )

        ranking = scores.get_ranking()
        top_motivators = scores.get_top_motivators(2)

        return MotivatorResult(
            scores=scores,
            ranking=ranking,
            top_motivator=top_motivators[0] if top_motivators else "economic",
            second_motivator=top_motivators[1] if len(top_motivators) > 1 else "individualistic",
            lowest_motivator=scores.get_lowest_motivator(),
        )

    def get_dimension_description(
        self,
        dimension: str,
        score: int
    ) -> Dict[str, str]:
        """
        Get description for a motivator dimension based on score.

        Args:
            dimension: The dimension name
            score: Score 0-100

        Returns:
            Dict with name, description, and context
        """
        info = self.DIMENSION_INFO.get(dimension, {})
        is_high = score >= 60

        return {
            "name": info.get("name", dimension.title()),
            "description": info.get("description", ""),
            "context": info.get("high_description" if is_high else "low_description", ""),
            "keywords": info.get("keywords", []),
            "is_high": is_high,
            "score": score,
        }

    def get_motivator_insights(self, result: MotivatorResult) -> Dict:
        """
        Generate insights about motivator profile.

        Args:
            result: MotivatorResult from scoring

        Returns:
            Dict with insights for each dimension and overall summary
        """
        insights = {
            "top_motivators": [],
            "dimension_insights": {},
            "summary": "",
        }

        scores = result.scores.to_dict()

        # Add insights for each dimension
        for dim, score in scores.items():
            insights["dimension_insights"][dim] = self.get_dimension_description(dim, score)

        # Add top motivators with context
        for dim in [result.top_motivator, result.second_motivator]:
            info = self.DIMENSION_INFO.get(dim, {})
            insights["top_motivators"].append({
                "dimension": dim,
                "name": info.get("name", dim.title()),
                "description": info.get("high_description", ""),
                "score": scores.get(dim, 50),
            })

        # Generate summary
        top_name = self.DIMENSION_INFO.get(result.top_motivator, {}).get("name", "")
        second_name = self.DIMENSION_INFO.get(result.second_motivator, {}).get("name", "")
        insights["summary"] = (
            f"Your top motivator is {top_name}, followed by {second_name}. "
            f"This combination suggests you are driven by "
            f"{self._get_combination_description(result.top_motivator, result.second_motivator)}."
        )

        return insights

    def _get_combination_description(self, top: str, second: str) -> str:
        """Get description for top motivator combination."""
        combinations = {
            ("economic", "political"): "achieving practical results through positions of influence",
            ("economic", "individualistic"): "personal financial success and standing out through achievement",
            ("economic", "theoretical"): "understanding that leads to practical application and results",
            ("political", "economic"): "leveraging influence to create tangible outcomes",
            ("political", "individualistic"): "leading while maintaining your unique identity",
            ("individualistic", "economic"): "achieving personal distinction through practical success",
            ("individualistic", "political"): "gaining recognition and influence on your own terms",
            ("altruistic", "regulatory"): "helping others within established systems and structures",
            ("altruistic", "individualistic"): "making a unique personal impact on others' lives",
            ("theoretical", "individualistic"): "developing unique expertise and knowledge",
            ("theoretical", "economic"): "applying knowledge in practical, results-oriented ways",
            ("regulatory", "theoretical"): "understanding and upholding systems and principles",
            ("aesthetic", "individualistic"): "creative expression and personal artistic distinction",
            ("aesthetic", "theoretical"): "understanding the principles behind beauty and design",
        }

        key = (top, second)
        return combinations.get(key, f"a blend of {top} and {second} values")
