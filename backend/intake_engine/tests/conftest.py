"""
Pytest configuration and fixtures for intake engine tests
"""

import pytest
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@pytest.fixture
def sample_session():
    """Create a sample session for testing"""
    from ..runtime import Session, PartyType

    session = Session(
        loan_id="L_TEST_123",
        mode="intake_prequal",
        locale="en-US",
    )
    session.add_party(PartyType.PRIMARY, "Test Borrower")
    return session


@pytest.fixture
def sample_questions():
    """Sample question definitions"""
    return {
        "Q_LANG": {
            "question_id": "Q_LANG",
            "prompt_key": "Q_LANG",
            "urla_section": "LANGUAGE",
            "answer_types": ["single_select"],
            "required": True,
            "options": [
                {"value": "en-US", "label": "English"},
                {"value": "es-US", "label": "Spanish"},
            ],
        },
        "Q_ID_0200": {
            "question_id": "Q_ID_0200",
            "prompt_key": "Q_ID_0200",
            "urla_section": "IDENTITY",
            "urla_payload_path": "borrowers[].personal.name",
            "answer_types": ["name"],
            "required": True,
            "party_aware": True,
        },
        "Q_ID_0201": {
            "question_id": "Q_ID_0201",
            "prompt_key": "Q_ID_0201",
            "urla_section": "IDENTITY",
            "urla_payload_path": "borrowers[].personal.dateOfBirth",
            "answer_types": ["date"],
            "required": True,
            "party_aware": True,
            "validations": [
                {"type": "date_past"},
                {"type": "age_min", "value": 18},
            ],
        },
        "Q_PURP_0010": {
            "question_id": "Q_PURP_0010",
            "prompt_key": "Q_PURP_0010",
            "urla_section": "PURPOSE_AND_GOALS",
            "urla_payload_path": "loan.loanPurpose",
            "answer_types": ["single_select"],
            "required": True,
            "options": [
                {"value": "Purchase", "label": "Buy a home"},
                {"value": "Refinance", "label": "Refinance"},
            ],
        },
        "Q_INC_0303": {
            "question_id": "Q_INC_0303",
            "prompt_key": "Q_INC_0303",
            "urla_section": "EMPLOYMENT_INCOME",
            "urla_payload_path": "borrowers[].income.monthlyGrossIncome",
            "answer_types": ["currency"],
            "required": True,
            "party_aware": True,
            "validations": [
                {"type": "min", "value": 0},
            ],
        },
    }


@pytest.fixture
def sample_validation_rules():
    """Sample validation rules configuration"""
    return {
        "field_validations": {
            "Q_ID_0204": {
                "rules": [
                    {"type": "regex", "pattern": "email", "error_code": "INVALID_EMAIL"},
                ],
            },
        },
        "cross_field_rules": [
            {
                "id": "RULE_DTI_CHECK",
                "type": "dti_consistency",
                "fields": ["Q_INC_0303", "Q_LIA_0500", "Q_LIA_0501"],
                "max_dti": 50,
                "severity": "warn",
                "add_flag": "FLAG_DTI_EXCEEDS_TYPICAL",
            },
        ],
    }


@pytest.fixture
def sample_hesitation_config():
    """Sample hesitation detection configuration"""
    return {
        "signals": [
            {
                "id": "SIG_LATENCY_LONG",
                "type": "timing",
                "weight": 0.15,
                "rule": {"response_time_ms_gte": 18000},
            },
            {
                "id": "SIG_HEDGE_LANGUAGE",
                "type": "nlp",
                "weight": 0.25,
                "rule": {"contains_any": ["not sure", "i think", "maybe", "around"]},
            },
            {
                "id": "SIG_REVISION_MULTIPLE",
                "type": "behavior",
                "weight": 0.20,
                "rule": {"edits_count_gte": 2, "within_seconds": 30},
            },
        ],
        "outputs": {
            "hesitation_score": {
                "range": [0.0, 1.0],
                "thresholds": {
                    "none": 0.0,
                    "mild": 0.35,
                    "moderate": 0.55,
                    "high": 0.75,
                },
            },
        },
        "actions": {
            "when_moderate": [
                {"add_flag": "FLAG_NEEDS_GENTLE_VERIFICATION"},
                {"lower_confidence": 0.2},
            ],
            "when_high": [
                {"add_flag": "FLAG_TRUTH_RISK_HIGH"},
                {"lower_confidence": 0.4},
                {"coaching_overlay": "COACH_TRUTH_RECOVERY"},
            ],
        },
        "question_sensitivity": {
            "high_sensitivity": {
                "questions": ["Q_INC_0303", "Q_AST_0401"],
                "threshold_adjustment": 0.1,
            },
            "low_sensitivity": {
                "questions": ["Q_ID_0200", "Q_ID_0201"],
                "threshold_adjustment": -0.15,
            },
        },
        "false_positive_filters": [],
        "latency_normalization": {"enabled": True},
    }


@pytest.fixture
def sample_truth_config():
    """Sample truth score configuration"""
    return {
        "components": {
            "completeness": {"weight": 0.35},
            "internal_consistency": {"weight": 0.30},
            "evidence_alignment": {"weight": 0.25},
            "behavioral_confidence": {"weight": 0.10},
        },
        "penalties": [
            {
                "id": "PEN_HIGH_HESITATION",
                "when": {"condition": "session.scores.hesitation_score >= 0.75"},
                "deduct": 10,
                "severity": "high",
            },
        ],
        "bonuses": [
            {
                "id": "BON_NO_HESITATION",
                "when": {"condition": "session.scores.hesitation_score < 0.20"},
                "add": 5,
            },
        ],
        "severity_mapping": {},
    }


@pytest.fixture
def sample_readiness_config():
    """Sample readiness score configuration"""
    return {
        "section_weights": {
            "IDENTITY": {"weight": 0.15, "required_fields": ["Q_ID_0200", "Q_ID_0201"]},
            "EMPLOYMENT_INCOME": {"weight": 0.25, "required_fields": ["Q_INC_0303"]},
            "PURPOSE_AND_GOALS": {"weight": 0.20, "required_fields": ["Q_PURP_0010"]},
        },
        "gating_rules": [
            {
                "type": "consent_required",
                "condition": {"consent_key": "credit_authorization"},
                "cap_readiness_at": 40,
            },
        ],
    }
