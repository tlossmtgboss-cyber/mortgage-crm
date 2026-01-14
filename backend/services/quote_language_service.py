"""
Quote Language Preset Selection Service

Provides deterministic selection of compliant language snippets for the AI agent.
Ensures the agent never "freestyles" promises and stays compliant across:
- range_only: When we can quote an indicative rate range
- ballpark: When we don't have enough detail to quote
- no_quote: When we cannot/should not quote numbers

Selection is server-side for consistency across LLM calls.
"""

import json
import os
import random
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QuotePolicy(str, Enum):
    """Quote policy buckets for language selection."""
    RANGE_ONLY = "range_only"
    BALLPARK = "ballpark"
    NO_QUOTE = "no_quote"


@dataclass
class LanguageSelection:
    """Selected language snippets for a call."""
    policy_bucket: QuotePolicy
    opener: str
    range_phrase: Optional[str] = None
    close: str = ""
    value_prop: Optional[str] = None
    disclaimer: str = ""
    transition_phrase: Optional[str] = None
    rate_range_text: Optional[str] = None
    duration_minutes: int = 15


@dataclass
class RateQuoteInput:
    """Input parameters for language selection."""
    eligible: Optional[bool] = None  # True, False, or None (unknown)
    quote_policy: Optional[str] = None  # "range_only" or "no_quote"
    goal: Optional[str] = None  # rate_term_refi_review, annual_mortgage_review, etc.
    segment: Optional[str] = None  # arm_safety_review, equity_strategy_review, etc.
    rate_range_text: Optional[str] = None  # "6.25% - 6.75%"
    compliance_language: Optional[str] = None  # Override from rate engine
    state: Optional[str] = None  # State code for state-specific disclaimers
    duration_minutes: int = 15


class QuoteLanguageService:
    """
    Service for selecting compliant language presets.

    Usage:
        service = QuoteLanguageService()
        selection = service.select_language(RateQuoteInput(
            eligible=True,
            quote_policy="range_only",
            goal="rate_term_refi_review",
            rate_range_text="6.25% - 6.75%"
        ))
    """

    def __init__(self, config_path: str = None):
        """Load language presets from config file."""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                "quote_language_presets.json"
            )

        self.presets = self._load_presets(config_path)
        self._seed = None  # Optional seed for reproducible selections

    def _load_presets(self, config_path: str) -> Dict:
        """Load presets from JSON config."""
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Quote language presets not found at {config_path}")
            return self._get_default_presets()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in quote language presets: {e}")
            return self._get_default_presets()

    def _get_default_presets(self) -> Dict:
        """Fallback presets if config file is missing."""
        return {
            "rules": {
                "range_only": {
                    "opener": ["Based on what we know, I can share an estimated range."],
                    "range_phrase": ["Something like {rate_range_text} depending on specifics."],
                    "close": ["Want to set up a quick {duration}-minute review?"]
                },
                "ballpark": {
                    "opener": ["I don't have enough detail to quote a range yet."],
                    "close": ["A quick {duration}-minute review would give you real numbers."]
                },
                "no_quote": {
                    "opener": ["I can't responsibly quote numbers without more details."],
                    "close": ["A {duration}-minute review would clarify things."]
                }
            },
            "goal_overrides": {},
            "segment_overrides": {},
            "disclaimer_templates": {
                "default": "This is an estimate, not a commitment to lend.",
                "short": "Estimate only — final terms depend on review."
            },
            "transition_phrases": {
                "to_booking": ["Sound like something worth exploring?"]
            }
        }

    def set_seed(self, seed: int):
        """Set random seed for reproducible selections (useful for testing)."""
        self._seed = seed

    def _random_choice(self, items: List[str]) -> str:
        """Select random item, using seed if set."""
        if not items:
            return ""
        if self._seed is not None:
            random.seed(self._seed)
        return random.choice(items)

    def determine_policy_bucket(self, input_data: RateQuoteInput) -> QuotePolicy:
        """
        Determine which policy bucket to use based on inputs.

        Logic:
        - If quote_policy == range_only AND eligible == true -> range_only
        - If eligible == unknown -> ballpark
        - Else -> no_quote
        """
        if input_data.quote_policy == "range_only" and input_data.eligible is True:
            return QuotePolicy.RANGE_ONLY
        elif input_data.eligible is None:  # unknown
            return QuotePolicy.BALLPARK
        else:
            return QuotePolicy.NO_QUOTE

    def select_language(self, input_data: RateQuoteInput) -> LanguageSelection:
        """
        Select compliant language snippets based on inputs.

        Returns a LanguageSelection with all needed phrases for the call.
        """
        # Determine policy bucket
        policy_bucket = self.determine_policy_bucket(input_data)
        rules = self.presets.get("rules", {})
        bucket_rules = rules.get(policy_bucket.value, {})

        # Select opener
        opener_options = bucket_rules.get("opener", [])
        opener = self._random_choice(opener_options)

        # Select range phrase (only for range_only)
        range_phrase = None
        if policy_bucket == QuotePolicy.RANGE_ONLY:
            range_options = bucket_rules.get("range_phrase", [])
            range_phrase = self._random_choice(range_options)
            # Substitute rate range text
            if range_phrase and input_data.rate_range_text:
                range_phrase = range_phrase.replace(
                    "{rate_range_text}",
                    input_data.rate_range_text
                )

        # Select close
        close_options = bucket_rules.get("close", [])
        close = self._random_choice(close_options)
        # Substitute duration
        if close:
            close = close.replace("{duration}", str(input_data.duration_minutes))

        # Get value prop from goal or segment overrides
        value_prop = None
        goal_overrides = self.presets.get("goal_overrides", {})
        segment_overrides = self.presets.get("segment_overrides", {})

        if input_data.goal and input_data.goal in goal_overrides:
            vp_options = goal_overrides[input_data.goal].get("value_prop", [])
            value_prop = self._random_choice(vp_options)

        if input_data.segment and input_data.segment in segment_overrides:
            # Segment override takes precedence if present
            vp_options = segment_overrides[input_data.segment].get("value_prop", [])
            segment_vp = self._random_choice(vp_options)
            if segment_vp:
                value_prop = segment_vp

        # Select disclaimer
        disclaimer_templates = self.presets.get("disclaimer_templates", {})

        # Use compliance language from rate engine if provided
        if input_data.compliance_language:
            disclaimer = input_data.compliance_language
        # Check for state-specific disclaimer
        elif input_data.state and "state_specific" in disclaimer_templates:
            state_disclaimers = disclaimer_templates["state_specific"]
            disclaimer = state_disclaimers.get(
                input_data.state,
                disclaimer_templates.get("default", "")
            )
        else:
            disclaimer = disclaimer_templates.get("default", "")

        # Select transition phrase
        transition_phrases = self.presets.get("transition_phrases", {})
        to_booking = transition_phrases.get("to_booking", [])
        transition = self._random_choice(to_booking)

        return LanguageSelection(
            policy_bucket=policy_bucket,
            opener=opener,
            range_phrase=range_phrase,
            close=close,
            value_prop=value_prop,
            disclaimer=disclaimer,
            transition_phrase=transition,
            rate_range_text=input_data.rate_range_text,
            duration_minutes=input_data.duration_minutes
        )

    def get_objection_response(
        self,
        objection_type: str,
        duration_minutes: int = 15
    ) -> Optional[str]:
        """
        Get a compliant response for common objections.

        Args:
            objection_type: One of "too_busy", "not_interested", "need_to_think"
            duration_minutes: Duration to substitute in response
        """
        transition_phrases = self.presets.get("transition_phrases", {})
        objection_handling = transition_phrases.get("objection_handling", {})

        responses = objection_handling.get(objection_type, [])
        if not responses:
            return None

        response = self._random_choice(responses)
        if response:
            response = response.replace("{duration}", str(duration_minutes))

        return response

    def get_compliance_checklist(self) -> Dict[str, List[str]]:
        """Get compliance notes for agent reference."""
        return self.presets.get("compliance_notes", {
            "never_say": [],
            "always_include": [],
            "rate_context": ""
        })

    def format_for_agent_context(self, selection: LanguageSelection) -> Dict[str, Any]:
        """
        Format selection for inclusion in agent context/prompt.

        Returns a dict ready to be included in RateQuoteResponse or agent context.
        """
        return {
            "policy_bucket": selection.policy_bucket.value,
            "approved_language": {
                "opener": selection.opener,
                "range_phrase": selection.range_phrase,
                "value_prop": selection.value_prop,
                "close": selection.close,
                "transition": selection.transition_phrase
            },
            "disclaimer": selection.disclaimer,
            "duration_minutes": selection.duration_minutes,
            "compliance_notes": self.get_compliance_checklist()
        }


# Global service instance
_quote_language_service = None


def get_quote_language_service() -> QuoteLanguageService:
    """Get or create the global quote language service instance."""
    global _quote_language_service
    if _quote_language_service is None:
        _quote_language_service = QuoteLanguageService()
    return _quote_language_service


# Convenience function for direct use
def select_quote_language(
    eligible: Optional[bool] = None,
    quote_policy: Optional[str] = None,
    goal: Optional[str] = None,
    segment: Optional[str] = None,
    rate_range_text: Optional[str] = None,
    compliance_language: Optional[str] = None,
    state: Optional[str] = None,
    duration_minutes: int = 15
) -> Dict[str, Any]:
    """
    Convenience function to select quote language.

    Returns a dict ready to include in API responses or agent context.

    Example:
        language = select_quote_language(
            eligible=True,
            quote_policy="range_only",
            goal="rate_term_refi_review",
            rate_range_text="6.25% - 6.75%"
        )
    """
    service = get_quote_language_service()
    input_data = RateQuoteInput(
        eligible=eligible,
        quote_policy=quote_policy,
        goal=goal,
        segment=segment,
        rate_range_text=rate_range_text,
        compliance_language=compliance_language,
        state=state,
        duration_minutes=duration_minutes
    )
    selection = service.select_language(input_data)
    return service.format_for_agent_context(selection)
