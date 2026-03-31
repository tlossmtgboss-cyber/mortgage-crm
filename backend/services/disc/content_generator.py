"""
DISC + Motivators AI Content Generator

Uses Claude to generate personalized content:
- General characteristics narrative
- Word sketch behavioral matrix
- Communication tips (DO/DON'T)
- Wants and needs
- Strengths
- Stress behaviors
- Areas for improvement
- 12 integrated style relationships
- Motivator dimension insights
"""

import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
import anthropic

from .scoring_service import DISCScores, DISCResult
from .motivators_service import MotivatorScores, MotivatorResult
from .wheel_calculator import WheelPosition


@dataclass
class GeneratedContent:
    """AI-generated content for DISC report."""
    characteristics: str
    word_sketch: Dict[str, List[str]]
    communication_tips: Dict[str, List[str]]
    wants_and_needs: Dict[str, List[str]]
    strengths: List[str]
    stress_behaviors: List[str]
    areas_for_improvement: List[str]
    integrated_styles: List[Dict]


class DISCContentGenerator:
    """
    Service for generating AI-powered DISC + Motivators content.

    Uses Claude to create personalized narratives based on assessment results.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.model = "claude-sonnet-4-20250514"

    async def generate_all_content(
        self,
        disc_result: DISCResult,
        motivator_result: MotivatorResult,
        wheel_position: WheelPosition,
        candidate_name: str = "the candidate"
    ) -> GeneratedContent:
        """
        Generate all AI content for the report.

        Args:
            disc_result: Computed DISC scores
            motivator_result: Computed Motivator scores
            wheel_position: Wheel position data
            candidate_name: Name for personalization

        Returns:
            GeneratedContent with all generated sections
        """
        # Build context for Claude
        context = self._build_context(disc_result, motivator_result, wheel_position)

        # Generate each section
        characteristics = await self._generate_characteristics(context, candidate_name)
        word_sketch = await self._generate_word_sketch(context)
        communication_tips = await self._generate_communication_tips(context)
        wants_needs = await self._generate_wants_and_needs(context)
        strengths = await self._generate_strengths(context)
        stress = await self._generate_stress_behaviors(context)
        improvements = await self._generate_improvements(context)
        integrated = await self._generate_integrated_styles(context)

        return GeneratedContent(
            characteristics=characteristics,
            word_sketch=word_sketch,
            communication_tips=communication_tips,
            wants_and_needs=wants_needs,
            strengths=strengths,
            stress_behaviors=stress,
            areas_for_improvement=improvements,
            integrated_styles=integrated,
        )

    def _build_context(
        self,
        disc_result: DISCResult,
        motivator_result: MotivatorResult,
        wheel_position: WheelPosition
    ) -> Dict:
        """Build context object for prompts."""
        return {
            "adapted_style": disc_result.adapted_style,
            "natural_style": disc_result.natural_style,
            "combined_style": disc_result.combined_style,
            "adapted_scores": disc_result.adapted.to_dict(),
            "natural_scores": disc_result.natural.to_dict(),
            "wheel_zone": wheel_position.zone_name,
            "top_motivator": motivator_result.top_motivator,
            "second_motivator": motivator_result.second_motivator,
            "lowest_motivator": motivator_result.lowest_motivator,
            "motivator_scores": motivator_result.scores.to_dict(),
            "quality_tier": disc_result.quality_tier.value,
        }

    async def _generate_characteristics(self, context: Dict, name: str) -> str:
        """Generate general characteristics narrative."""
        prompt = f"""Based on this DISC and Motivators profile, write a 2-3 paragraph characteristics narrative.

DISC Profile:
- Adapted Style: {context['adapted_style']} (work behavior)
- Natural Style: {context['natural_style']} (natural tendencies)
- Adapted Scores: D={context['adapted_scores']['D']}, I={context['adapted_scores']['I']}, S={context['adapted_scores']['S']}, C={context['adapted_scores']['C']}
- Wheel Zone: {context['wheel_zone']}

Motivators:
- Top Motivator: {context['top_motivator']}
- Second Motivator: {context['second_motivator']}
- Motivator Scores: {json.dumps(context['motivator_scores'])}

Write in second person ("You are..."). Focus on:
1. Core behavioral tendencies
2. How they approach work and relationships
3. What drives and motivates them
4. Their communication style

Be specific and actionable. Avoid generic statements. Write professionally but warmly."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text

    async def _generate_word_sketch(self, context: Dict) -> Dict[str, List[str]]:
        """Generate word sketch behavioral matrix."""
        prompt = f"""Create a DISC Word Sketch matrix based on this profile:

Adapted Style: {context['adapted_style']}
Natural Style: {context['natural_style']}
Scores: D={context['adapted_scores']['D']}, I={context['adapted_scores']['I']}, S={context['adapted_scores']['S']}, C={context['adapted_scores']['C']}

Return a JSON object with 4 keys (D, I, S, C), each containing an array of 5-7 behavioral descriptor words that apply to this person for that dimension.

For HIGH dimensions (score > 60), use STRONG descriptors.
For LOW dimensions (score < 40), use OPPOSITE/ABSENCE descriptors.
For MEDIUM dimensions (40-60), use MODERATE descriptors.

Example format:
{{"D": ["decisive", "direct", "results-focused"], "I": ["friendly", "talkative"], "S": ["patient", "steady"], "C": ["analytical", "precise"]}}

Return ONLY the JSON object, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {"D": [], "I": [], "S": [], "C": []}

    async def _generate_communication_tips(self, context: Dict) -> Dict[str, List[str]]:
        """Generate DO and DON'T communication tips."""
        prompt = f"""Create communication tips for someone with this DISC profile:

Style: {context['combined_style']}
Wheel Zone: {context['wheel_zone']}
Top Motivator: {context['top_motivator']}

Return a JSON object with two keys: "do" and "dont", each containing an array of 5-7 specific, actionable tips.

Focus on:
- How others should communicate WITH this person
- What approaches work best
- What to avoid

Example format:
{{"do": ["Be direct and get to the point", "Focus on results"], "dont": ["Don't ramble or waste their time", "Don't be overly emotional"]}}

Return ONLY the JSON object."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {"do": [], "dont": []}

    async def _generate_wants_and_needs(self, context: Dict) -> Dict[str, List[str]]:
        """Generate wants and needs lists."""
        prompt = f"""Based on this DISC and Motivator profile, identify wants and needs:

Style: {context['combined_style']}
Top Motivators: {context['top_motivator']}, {context['second_motivator']}
Wheel Zone: {context['wheel_zone']}

Return a JSON object with two keys: "wants" and "needs", each containing 4-6 items.

Wants = What they desire, seek out, are drawn to
Needs = What they require to function well, be productive, stay engaged

Example:
{{"wants": ["Recognition for achievements", "Variety and excitement"], "needs": ["Clear expectations", "Autonomy"]}}

Return ONLY the JSON object."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return {"wants": [], "needs": []}

    async def _generate_strengths(self, context: Dict) -> List[str]:
        """Generate list of strengths."""
        prompt = f"""List 6-8 key strengths for someone with this profile:

DISC Style: {context['combined_style']}
Wheel Zone: {context['wheel_zone']}
Top Motivators: {context['top_motivator']}, {context['second_motivator']}

Return a JSON array of strength statements. Each should be specific and actionable.

Example: ["Decisive under pressure", "Builds rapport quickly", "Consistent follow-through"]

Return ONLY the JSON array."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []

    async def _generate_stress_behaviors(self, context: Dict) -> List[str]:
        """Generate stress behavior patterns."""
        prompt = f"""Describe 4-6 behaviors this person may exhibit under stress:

DISC Style: {context['combined_style']}
Wheel Zone: {context['wheel_zone']}
Lowest Motivator: {context['lowest_motivator']}

Return a JSON array of stress behavior descriptions. Be specific about observable behaviors.

Example: ["May become overly controlling", "Withdraws and becomes quiet", "Gets impatient with details"]

Return ONLY the JSON array."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []

    async def _generate_improvements(self, context: Dict) -> List[str]:
        """Generate areas for improvement."""
        prompt = f"""Suggest 4-6 areas for growth for someone with this profile:

DISC Style: {context['combined_style']}
Low Dimensions: {self._get_low_dimensions(context['adapted_scores'])}
Lowest Motivator: {context['lowest_motivator']}

Return a JSON array of growth areas. Frame positively as development opportunities.

Example: ["Develop more patience with slower-paced team members", "Practice active listening"]

Return ONLY the JSON array."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []

    async def _generate_integrated_styles(self, context: Dict) -> List[Dict]:
        """Generate 12 integrated style relationships."""
        prompt = f"""For this DISC style ({context['combined_style']}), describe how they interact with each of the 12 DISC styles.

Return a JSON array with 12 objects, each containing:
- "style": The style code (D, Di, Dc, I, Id, Is, S, Si, Sc, C, Cd, Cs)
- "compatibility": "high", "moderate", or "challenging"
- "tips": Array of 2-3 specific interaction tips

Example:
[{{"style": "D", "compatibility": "high", "tips": ["Focus on results", "Be direct"]}}, ...]

Return ONLY the JSON array with all 12 styles."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []

    def _get_low_dimensions(self, scores: Dict[str, int]) -> str:
        """Get dimensions with low scores."""
        low = [dim for dim, score in scores.items() if score < 40]
        return ", ".join(low) if low else "None significantly low"

    # Synchronous versions for non-async contexts
    def generate_characteristics_sync(self, context: Dict, name: str) -> str:
        """Synchronous version of generate_characteristics.

        Safe to call from both sync and async contexts.
        """
        import asyncio
        import concurrent.futures

        coro = self._generate_characteristics(context, name)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def generate_all_content_sync(
        self,
        disc_result: DISCResult,
        motivator_result: MotivatorResult,
        wheel_position: WheelPosition,
        candidate_name: str = "the candidate"
    ) -> GeneratedContent:
        """Synchronous version of generate_all_content.

        Safe to call from both sync and async contexts.
        """
        import asyncio
        import concurrent.futures

        coro = self.generate_all_content(
            disc_result, motivator_result, wheel_position, candidate_name
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)
