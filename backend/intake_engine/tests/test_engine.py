"""
Intake Engine Tests
Tests for core engine functionality
"""

import pytest
from datetime import datetime

from ..runtime import (
    IntakeEngine,
    Session,
    Party,
    PartyType,
    SessionStatus,
    AnswerMeta,
    Flag,
    FlagCategory,
    FlagSeverity,
    HesitationBand,
    TruthBand,
)
from ..runtime.models import Signals, Scores, ScoreBreakdown
from ..runtime.storage import InMemoryStore, SessionStorage
from ..runtime.validation import ValidationEngine, ValidationResult
from ..runtime.hesitation import HesitationEngine, HesitationResult
from ..runtime.scoring import ScoringEngine, ScoringResult


class TestSession:
    """Tests for Session model"""

    def test_create_session(self):
        """Test session creation"""
        session = Session()
        assert session.session_id.startswith("S_")
        assert session.status == SessionStatus.ACTIVE
        assert session.current_section == "LANGUAGE"
        assert len(session.parties) == 0
        assert len(session.answers) == 0

    def test_add_party(self):
        """Test adding a party to session"""
        session = Session()
        party = session.add_party(PartyType.PRIMARY, "John Doe")

        assert len(session.parties) == 1
        assert party.party_type == PartyType.PRIMARY
        assert party.display_name == "John Doe"
        assert party.party_id in session.party_answers

    def test_set_answer_global(self):
        """Test setting a global answer"""
        session = Session()
        session.set_answer("Q_ID_0200", {"first": "John", "last": "Doe"})

        assert "Q_ID_0200" in session.answers
        assert session.answers["Q_ID_0200"]["first"] == "John"

    def test_set_answer_party_specific(self):
        """Test setting a party-specific answer"""
        session = Session()
        party = session.add_party(PartyType.PRIMARY)

        session.set_answer("Q_ID_0200", {"first": "John"}, party.party_id)

        assert "Q_ID_0200" not in session.answers
        assert "Q_ID_0200" in session.party_answers[party.party_id]

    def test_get_answer_with_party_fallback(self):
        """Test getting answer with party fallback"""
        session = Session()
        party = session.add_party(PartyType.PRIMARY)

        # Set global answer
        session.set_answer("Q_GLOBAL", "global_value")

        # Set party answer
        session.set_answer("Q_PARTY", "party_value", party.party_id)

        # Get global answer
        assert session.get_answer("Q_GLOBAL") == "global_value"
        assert session.get_answer("Q_GLOBAL", party.party_id) is None  # Party specific returns None

        # Get party answer
        assert session.get_answer("Q_PARTY", party.party_id) == "party_value"
        assert session.get_answer("Q_PARTY") is None  # Global returns None

    def test_add_flag(self):
        """Test adding a flag"""
        session = Session()
        flag = Flag(
            code="TEST_FLAG",
            category=FlagCategory.TRUTH,
            severity=FlagSeverity.WARN,
            message="Test flag",
        )
        session.add_flag(flag)

        assert len(session.flags) == 1
        assert session.has_flag("TEST_FLAG")

    def test_add_duplicate_flag(self):
        """Test that duplicate flags are not added"""
        session = Session()
        flag1 = Flag(code="TEST_FLAG", category=FlagCategory.TRUTH, severity=FlagSeverity.WARN)
        flag2 = Flag(code="TEST_FLAG", category=FlagCategory.TRUTH, severity=FlagSeverity.HIGH)

        session.add_flag(flag1)
        session.add_flag(flag2)

        assert len(session.flags) == 1  # Second flag not added

    def test_remove_flag(self):
        """Test removing a flag"""
        session = Session()
        flag = Flag(code="TEST_FLAG", category=FlagCategory.TRUTH, severity=FlagSeverity.WARN)
        session.add_flag(flag)
        session.remove_flag("TEST_FLAG")

        assert not session.has_flag("TEST_FLAG")
        assert len(session.flags) == 0

    def test_edit_history_tracking(self):
        """Test that edits are tracked"""
        session = Session()
        session.set_answer("Q_TEST", "original")
        session.set_answer("Q_TEST", "edited")

        assert len(session.edits_history) == 1
        assert session.edits_history[0].old_value == "original"
        assert session.edits_history[0].new_value == "edited"


class TestInMemoryStore:
    """Tests for in-memory storage"""

    def test_store_and_retrieve_session(self):
        """Test storing and retrieving a session"""
        store = InMemoryStore()
        session = Session()

        store.set_session(session)
        retrieved = store.get_session(session.session_id)

        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_delete_session(self):
        """Test deleting a session"""
        store = InMemoryStore()
        session = Session()

        store.set_session(session)
        store.delete_session(session.session_id)

        assert store.get_session(session.session_id) is None


class TestValidationEngine:
    """Tests for validation engine"""

    def test_required_field_validation(self):
        """Test required field validation"""
        engine = ValidationEngine({})
        session = Session()

        result = engine.validate_answer(
            "Q_TEST",
            None,
            session,
            {"required": True},
        )

        assert not result.valid
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "REQUIRED"

    def test_regex_validation(self):
        """Test regex validation"""
        engine = ValidationEngine({})
        session = Session()

        # Valid email
        result = engine.validate_answer(
            "Q_EMAIL",
            "test@example.com",
            session,
            {"validations": [{"type": "regex", "pattern": "email"}]},
        )
        assert result.valid

        # Invalid email
        result = engine.validate_answer(
            "Q_EMAIL",
            "not-an-email",
            session,
            {"validations": [{"type": "regex", "pattern": "email"}]},
        )
        assert not result.valid

    def test_min_max_validation(self):
        """Test min/max validation"""
        engine = ValidationEngine({})
        session = Session()

        # Valid range
        result = engine.validate_answer(
            "Q_NUM",
            50,
            session,
            {"validations": [
                {"type": "min", "value": 0},
                {"type": "max", "value": 100},
            ]},
        )
        assert result.valid

        # Below min
        result = engine.validate_answer(
            "Q_NUM",
            -5,
            session,
            {"validations": [{"type": "min", "value": 0}]},
        )
        assert not result.valid

        # Above max
        result = engine.validate_answer(
            "Q_NUM",
            150,
            session,
            {"validations": [{"type": "max", "value": 100}]},
        )
        assert not result.valid


class TestHesitationEngine:
    """Tests for hesitation detection"""

    def test_detect_hedge_phrases(self):
        """Test detection of hedge phrases"""
        config = {
            "signals": [
                {
                    "id": "SIG_HEDGE",
                    "type": "nlp",
                    "weight": 0.25,
                    "rule": {"contains_any": ["not sure", "i think", "maybe"]},
                }
            ],
            "outputs": {"hesitation_score": {"thresholds": {"mild": 0.35, "moderate": 0.55, "high": 0.75}}},
            "actions": {},
            "question_sensitivity": {},
            "false_positive_filters": [],
        }
        engine = HesitationEngine(config)

        hedges = engine.detect_hedges("I think it's around $50,000, not sure exactly")
        assert "i think" in hedges
        assert "not sure" in hedges

    def test_hesitation_score_from_timing(self):
        """Test hesitation detection from response timing"""
        config = {
            "signals": [
                {
                    "id": "SIG_LATENCY_LONG",
                    "type": "timing",
                    "weight": 0.15,
                    "rule": {"response_time_ms_gte": 18000},
                }
            ],
            "outputs": {"hesitation_score": {"thresholds": {"mild": 0.35, "moderate": 0.55, "high": 0.75}}},
            "actions": {},
            "question_sensitivity": {},
            "false_positive_filters": [],
            "latency_normalization": {"enabled": True},
        }
        engine = HesitationEngine(config)
        session = Session()

        # Fast response - no hesitation
        result = engine.analyze_response(
            "Q_TEST", "answer", 5000, 100, session
        )
        assert result.score < 0.15
        assert result.band == HesitationBand.NONE

        # Slow response - hesitation detected
        result = engine.analyze_response(
            "Q_TEST", "answer", 20000, 100, session
        )
        assert result.score >= 0.15
        assert len(result.signals_detected) > 0


class TestScoringEngine:
    """Tests for scoring engine"""

    def test_truth_score_computation(self):
        """Test truth score computation"""
        questions = {
            "Q_REQ_1": {"required": True},
            "Q_REQ_2": {"required": True},
            "Q_OPT_1": {"required": False},
        }
        truth_config = {
            "components": {
                "completeness": {"weight": 0.35},
                "internal_consistency": {"weight": 0.30},
                "evidence_alignment": {"weight": 0.25},
                "behavioral_confidence": {"weight": 0.10},
            },
            "penalties": [],
            "bonuses": [],
            "severity_mapping": {},
        }
        readiness_config = {
            "section_weights": {},
            "gating_rules": [],
        }

        engine = ScoringEngine(truth_config, readiness_config, questions)
        session = Session()

        # Empty session - low scores
        result = engine.compute_scores(session)
        assert result.truth_score < 50  # Low due to incomplete

        # Answer required questions
        session.set_answer("Q_REQ_1", "value1")
        session.set_answer("Q_REQ_2", "value2")

        result = engine.compute_scores(session)
        assert result.truth_score > 30  # Higher with answers

    def test_truth_band_mapping(self):
        """Test truth score to band mapping"""
        engine = ScoringEngine({
            "components": {},
            "penalties": [],
            "bonuses": [],
            "severity_mapping": {},
        }, {"section_weights": {}, "gating_rules": []}, {})

        assert engine._determine_truth_band(95) == TruthBand.GREEN
        assert engine._determine_truth_band(80) == TruthBand.LIGHT_GREEN
        assert engine._determine_truth_band(65) == TruthBand.YELLOW
        assert engine._determine_truth_band(45) == TruthBand.ORANGE
        assert engine._determine_truth_band(25) == TruthBand.RED


class TestIntegration:
    """Integration tests"""

    def test_full_intake_flow(self):
        """Test a complete intake flow"""
        # Create session
        session = Session()
        session.add_party(PartyType.PRIMARY, "Test Borrower")

        # Set some answers
        session.set_answer("Q_LANG", "en-US")
        session.set_answer("Q_ID_0200", {"first": "John", "last": "Doe"})
        session.set_answer("Q_ID_0201", "1990-01-15")
        session.set_answer("Q_PURP_0010", "Purchase")

        # Verify state
        assert session.get_answer("Q_LANG") == "en-US"
        assert session.get_answer("Q_ID_0200")["first"] == "John"
        assert len(session.parties) == 1

    def test_multi_party_intake(self):
        """Test intake with multiple parties"""
        session = Session()

        # Add primary borrower
        primary = session.add_party(PartyType.PRIMARY, "John Doe")

        # Add co-borrower
        co_borrower = session.add_party(PartyType.CO_BORROWER, "Jane Doe")

        # Set answers for each party
        session.set_answer("Q_ID_0200", {"first": "John"}, primary.party_id)
        session.set_answer("Q_ID_0200", {"first": "Jane"}, co_borrower.party_id)

        # Verify separation
        assert session.get_answer("Q_ID_0200", primary.party_id)["first"] == "John"
        assert session.get_answer("Q_ID_0200", co_borrower.party_id)["first"] == "Jane"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
