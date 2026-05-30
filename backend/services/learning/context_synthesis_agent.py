"""
Context Synthesis Agent — Continual Learning (Domain 8)

Takes a batch of AgentContextEvent records and extracts learnable patterns
via Claude, returning structured context updates with confidence scores.

If no ANTHROPIC_API_KEY is configured, falls back to a heuristic-only
extraction (pattern frequency + consistency scoring).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextSynthesisAgent:
    """Extracts durable learned preferences from raw context events.

    Usage:
        agent = ContextSynthesisAgent()
        result = await agent.synthesize(agent_id, events, clusters)
        # result = {
        #     "learned_preferences": {"tone": "formal", ...},
        #     "confidence": 0.87,
        #     "reasoning": "...",
        # }
    """

    MODEL = "claude-sonnet-4-6"
    MAX_EVENTS_IN_PROMPT = 50  # Trim to avoid token explosion
    MIN_CLUSTER_FREQUENCY = 2  # Ignore one-off events

    def __init__(self, anthropic_key: Optional[str] = None):
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize(
        self,
        agent_id: str,
        events: list,
        clusters: Optional[list] = None,
    ) -> dict:
        """Synthesize learned preferences from a batch of context events.

        Args:
            agent_id: The agent whose context is being consolidated.
            events: List of event dicts (from AgentContextEvent rows).
            clusters: Optional pre-computed _PatternCluster list.

        Returns:
            {learned_preferences: dict, confidence: float, reasoning: str}
        """
        if not events:
            return {"learned_preferences": {}, "confidence": 0.0, "reasoning": "No events"}

        # If clusters provided, filter to significant ones
        significant_clusters = []
        if clusters:
            significant_clusters = [
                c for c in clusters if c.frequency >= self.MIN_CLUSTER_FREQUENCY
            ]

        # Try LLM synthesis first; fall back to heuristic
        if self.anthropic_key:
            try:
                return await self._llm_synthesize(agent_id, events, significant_clusters)
            except Exception as e:
                logger.warning(
                    "LLM synthesis failed for agent %s, falling back to heuristic: %s",
                    agent_id, e,
                )

        return self._heuristic_synthesize(agent_id, events, significant_clusters)

    # ------------------------------------------------------------------
    # LLM-based synthesis
    # ------------------------------------------------------------------

    async def _llm_synthesize(
        self, agent_id: str, events: list, clusters: list
    ) -> dict:
        """Call Claude to extract patterns from events."""
        import anthropic

        prompt = self._build_synthesis_prompt(agent_id, events, clusters)

        client = anthropic.Anthropic(api_key=self.anthropic_key)
        response = client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an AI memory analyst for a mortgage CRM platform. "
                "Your job is to identify durable behavioral preferences from "
                "agent correction and feedback events. Return ONLY valid JSON."
            ),
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        return {
            "learned_preferences": parsed.get("learned_preferences", {}),
            "confidence": float(parsed.get("confidence", 0.0)),
            "reasoning": parsed.get("reasoning", ""),
        }

    def _build_synthesis_prompt(
        self, agent_id: str, events: list, clusters: list
    ) -> str:
        """Build the LLM prompt for context synthesis."""
        # Trim events to avoid token limits
        trimmed = events[: self.MAX_EVENTS_IN_PROMPT]

        cluster_summary = []
        for c in clusters:
            cluster_summary.append({
                "event_type": c.event_type,
                "context_key": c.context_key,
                "frequency": c.frequency,
                "consistency": round(c.consistency, 2),
                "sample_corrections": [
                    e.get("corrected_value") for e in c.events[:3]
                ],
                "sample_rationales": [
                    e.get("rationale") for e in c.events[:3] if e.get("rationale")
                ],
            })

        prompt = f"""Analyze the following agent interaction events and identify durable learned preferences.

Agent ID: {agent_id}
Total events in window: {len(events)}
Significant pattern clusters: {len(clusters)}

## Pattern Clusters
{json.dumps(cluster_summary, indent=2, default=str)}

## Raw Events (sample of {len(trimmed)})
{json.dumps(trimmed, indent=2, default=str)}

## Instructions
1. Identify patterns where the user consistently corrected or overrode the agent.
2. Identify outputs that were consistently approved (positive signal).
3. Ignore one-off corrections or ambiguous feedback.
4. For each pattern, produce a named preference with a concrete value.

Return JSON with this exact structure:
{{
  "learned_preferences": {{
    "<preference_key>": <preference_value>,
    ...
  }},
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation of what patterns you found>"
}}

Only include preferences where you have strong signal (repeated, consistent corrections).
If you find no durable patterns, return an empty learned_preferences dict with confidence 0.0."""

        return prompt

    # ------------------------------------------------------------------
    # Heuristic fallback (no LLM)
    # ------------------------------------------------------------------

    def _heuristic_synthesize(
        self, agent_id: str, events: list, clusters: list
    ) -> dict:
        """Extract preferences using frequency/consistency heuristics only.

        Used when ANTHROPIC_API_KEY is not configured or LLM call fails.
        """
        learned: Dict[str, Any] = {}
        total_consistency = 0.0
        considered = 0

        for cluster in clusters:
            if cluster.frequency < self.MIN_CLUSTER_FREQUENCY:
                continue
            if cluster.consistency < 0.6:
                continue

            # Take the most common corrected_value as the learned preference
            corrected_values = [
                e.get("corrected_value")
                for e in cluster.events
                if e.get("corrected_value") is not None
            ]
            if not corrected_values:
                continue

            # Most frequent value wins
            value_counts: Dict[str, int] = {}
            for v in corrected_values:
                key_str = json.dumps(v, sort_keys=True, default=str)
                value_counts[key_str] = value_counts.get(key_str, 0) + 1

            best_key = max(value_counts, key=value_counts.get)  # type: ignore[arg-type]
            best_value = json.loads(best_key)

            pref_key = f"{cluster.event_type}_{cluster.context_key}"
            learned[pref_key] = best_value
            total_consistency += cluster.consistency
            considered += 1

        confidence = (total_consistency / considered) if considered > 0 else 0.0

        reasoning_parts = []
        if considered > 0:
            reasoning_parts.append(
                f"Heuristic extraction found {considered} pattern(s) "
                f"from {len(events)} events"
            )
        else:
            reasoning_parts.append("No significant patterns detected via heuristic analysis")

        return {
            "learned_preferences": learned,
            "confidence": round(min(confidence, 1.0), 2),
            "reasoning": ". ".join(reasoning_parts),
        }
