"""Tests for BriefingPreferences loading and merging."""
import pytest


class MockUser:
    """Minimal mock for User model."""
    def __init__(self, briefing_preferences=None):
        self.briefing_preferences = briefing_preferences


class TestLoadPreferences:
    """Test MorningBriefingService.load_preferences()."""

    def _load(self, raw_prefs=None):
        from services.morning_briefing_service import MorningBriefingService
        user = MockUser(briefing_preferences=raw_prefs)
        return MorningBriefingService.load_preferences(user)

    def test_null_returns_all_defaults(self):
        prefs = self._load(None)
        assert prefs.ai_tone == "balanced"
        assert prefs.sections["pipeline"] is True
        assert prefs.sections["at_risk"] is True
        assert prefs.sections["stale_leads"] is True
        assert prefs.sections["appointments"] is True
        assert prefs.sections["conditions"] is True
        assert prefs.sections["yesterday"] is True
        assert prefs.thresholds["at_risk_days"] == 10
        assert prefs.thresholds["stale_lead_days"] == 7
        assert prefs.thresholds["stale_lead_high_score_days"] == 3
        assert prefs.thresholds["lock_expiring_days"] == 3
        assert prefs.thresholds["max_at_risk_items"] == 10
        assert prefs.thresholds["max_stale_lead_items"] == 10

    def test_partial_sections_fills_defaults(self):
        prefs = self._load({"sections": {"pipeline": False}})
        assert prefs.sections["pipeline"] is False
        assert prefs.sections["at_risk"] is True
        assert prefs.thresholds["at_risk_days"] == 10

    def test_partial_thresholds_fills_defaults(self):
        prefs = self._load({"thresholds": {"at_risk_days": 20}})
        assert prefs.thresholds["at_risk_days"] == 20
        assert prefs.thresholds["stale_lead_days"] == 7

    def test_ai_tone_preserved(self):
        prefs = self._load({"ai_tone": "concise"})
        assert prefs.ai_tone == "concise"

    def test_ai_tone_invalid_falls_back(self):
        prefs = self._load({"ai_tone": "verbose"})
        assert prefs.ai_tone == "balanced"

    def test_full_override(self):
        full = {
            "sections": {
                "pipeline": False, "at_risk": False, "stale_leads": False,
                "appointments": True, "conditions": True, "yesterday": False,
            },
            "thresholds": {
                "at_risk_days": 5, "stale_lead_days": 14,
                "stale_lead_high_score_days": 7, "lock_expiring_days": 7,
                "max_at_risk_items": 5, "max_stale_lead_items": 5,
            },
            "ai_tone": "detailed",
        }
        prefs = self._load(full)
        assert prefs.sections["pipeline"] is False
        assert prefs.thresholds["at_risk_days"] == 5
        assert prefs.ai_tone == "detailed"

    def test_unknown_keys_ignored(self):
        prefs = self._load({"unknown_key": "whatever", "sections": {"fake": True}})
        assert prefs.ai_tone == "balanced"
        assert "fake" not in prefs.sections


class TestTonePrompts:
    """Test that AI tone selection produces different system prompts."""

    def _get_prompts(self):
        from services.morning_briefing_service import MorningBriefingService
        return {
            "concise": MorningBriefingService.TONE_PROMPTS["concise"],
            "balanced": MorningBriefingService.INDIVIDUAL_SYSTEM_PROMPT,
            "detailed": MorningBriefingService.TONE_PROMPTS["detailed"],
        }

    def test_concise_prompt_exists(self):
        prompts = self._get_prompts()
        assert "bullet" in prompts["concise"].lower()

    def test_detailed_prompt_exists(self):
        prompts = self._get_prompts()
        assert "paragraph" in prompts["detailed"].lower()

    def test_balanced_is_default_individual(self):
        prompts = self._get_prompts()
        assert "3 prioritized actions" in prompts["balanced"]

    def test_tone_prompts_are_modifiers(self):
        """Tone prompts should be appended to level prompts, not replace them."""
        prompts = self._get_prompts()
        assert not prompts["concise"].startswith("You are")
        assert not prompts["detailed"].startswith("You are")
