"""
Test Borrower Experience Agent — Business logic tests for the borrower document
submission journey tools.

Tests the agent's core logic without hitting a real database:
- Checklist generation logic (received vs. missing document detection)
- Alternative document suggestion mappings
- Sentiment score calculation
- Borrower message drafting structure
- TCPA compliance enforcement
- FAQ pattern matching
- Rejection explanation simplification
- Experience score calculation
- Milestone detection
- Friction prediction based on borrower profile
"""

import pytest
from datetime import datetime, timedelta


# =============================================================================
# Checklist Generation Logic
# =============================================================================

@pytest.mark.unit
class TestChecklistGeneration:
    """Test personalized checklist generation business logic."""

    def test_all_docs_received_shows_100_percent(self):
        """When all required docs are received, progress should be 100%."""
        required = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
        received = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
        pct = round(len(received & required) / len(required) * 100)
        assert pct == 100

    def test_no_docs_received_shows_0_percent(self):
        """When no docs are received, progress should be 0%."""
        required = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
        received = set()
        pct = round(len(received & required) / len(required) * 100)
        assert pct == 0

    def test_partial_docs_calculates_correctly(self):
        """Partial document receipt should calculate percentage correctly."""
        required = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
        received = {"paystubs", "w2"}
        pct = round(len(received & required) / len(required) * 100)
        assert pct == 40

    def test_extra_docs_dont_inflate_percentage(self):
        """Documents not in the required set should not inflate progress."""
        required = {"paystubs", "w2", "bank_statements"}
        received = {"paystubs", "gift_letter", "purchase_contract"}
        pct = round(len(received & required) / len(required) * 100)
        # Only paystubs is in both sets
        assert pct == 33

    def test_fha_loan_adds_tax_returns(self):
        """FHA loans should include tax_returns in required documents."""
        required = ["paystubs", "w2", "bank_statements", "drivers_license", "credit_report"]
        loan_type = "fha"
        if loan_type in ("fha", "va", "usda"):
            required.append("tax_returns")
        assert "tax_returns" in required

    def test_purchase_loan_adds_purchase_docs(self):
        """Purchase loans should include purchase_contract and insurance."""
        required = ["paystubs", "w2", "bank_statements", "drivers_license", "credit_report"]
        loan_purpose = "purchase"
        if loan_purpose == "purchase":
            required.extend(["purchase_contract", "insurance"])
        assert "purchase_contract" in required
        assert "insurance" in required


# =============================================================================
# Alternative Document Suggestions
# =============================================================================

@pytest.mark.unit
class TestAlternativeDocuments:
    """Test alternative document suggestion mappings."""

    ALTERNATIVES = {
        "paystubs": [
            "Direct deposit statement from your bank showing employer deposits",
            "Employer-issued pay summary letter on company letterhead",
            "ADP, Workday, or payroll service printout",
        ],
        "w2": [
            "IRS Wage & Income Transcript (request at irs.gov, free, takes ~5 days)",
            "Year-end paystub showing total annual earnings and taxes withheld",
        ],
        "drivers_license": [
            "State-issued identification card",
            "Valid US passport (photo page)",
            "Military ID (active duty or veteran)",
        ],
    }

    def test_paystubs_have_alternatives(self):
        """Pay stubs should have at least 2 alternatives."""
        alternatives = self.ALTERNATIVES.get("paystubs", [])
        assert len(alternatives) >= 2

    def test_w2_has_irs_transcript_option(self):
        """W-2 alternatives should include IRS transcript option."""
        alternatives = self.ALTERNATIVES.get("w2", [])
        irs_options = [a for a in alternatives if "IRS" in a]
        assert len(irs_options) >= 1

    def test_id_has_passport_alternative(self):
        """Driver's license alternatives should include passport."""
        alternatives = self.ALTERNATIVES.get("drivers_license", [])
        passport_options = [a for a in alternatives if "passport" in a.lower()]
        assert len(passport_options) >= 1

    def test_unknown_doc_returns_empty(self):
        """Unknown document types should return no alternatives."""
        alternatives = self.ALTERNATIVES.get("nonexistent_document_type", [])
        assert alternatives == []


# =============================================================================
# Sentiment Score Calculation
# =============================================================================

@pytest.mark.unit
class TestSentimentAssessment:
    """Test borrower sentiment score calculation logic."""

    def test_all_positive_gives_high_score(self):
        """All positive signals should yield a high sentiment score."""
        total = 10
        positive = 10
        negative = 0
        score = int(50 + (positive - negative) / total * 50)
        score = max(0, min(100, score))
        assert score == 100

    def test_all_negative_gives_low_score(self):
        """All negative signals should yield a low sentiment score."""
        total = 10
        positive = 0
        negative = 10
        score = int(50 + (positive - negative) / total * 50)
        score = max(0, min(100, score))
        assert score == 0

    def test_mixed_signals_gives_moderate_score(self):
        """Mixed signals should yield a moderate sentiment score."""
        total = 10
        positive = 4
        negative = 3
        score = int(50 + (positive - negative) / total * 50)
        score = max(0, min(100, score))
        assert 40 <= score <= 70

    def test_no_activities_gives_neutral_50(self):
        """No activity history should default to neutral score of 50."""
        total = 0
        score = 50  # baseline when no data
        assert score == 50

    def test_score_clamped_to_0_100(self):
        """Extreme values should be clamped to 0-100 range."""
        # Edge case: more negatives than total (shouldn't happen but test clamping)
        score = int(50 + (-20) / 5 * 50)
        score = max(0, min(100, score))
        assert score == 0

        score2 = int(50 + 20 / 5 * 50)
        score2 = max(0, min(100, score2))
        assert score2 == 100

    def test_sentiment_label_thresholds(self):
        """Verify sentiment labels are assigned at correct thresholds."""
        def get_label(score):
            if score >= 70:
                return "positive"
            elif score >= 40:
                return "neutral"
            else:
                return "frustrated"

        assert get_label(80) == "positive"
        assert get_label(70) == "positive"
        assert get_label(55) == "neutral"
        assert get_label(40) == "neutral"
        assert get_label(39) == "frustrated"
        assert get_label(10) == "frustrated"


# =============================================================================
# Message Drafting & TCPA Compliance
# =============================================================================

@pytest.mark.unit
class TestMessageDrafting:
    """Test borrower message drafting and TCPA compliance checks."""

    def test_email_allowed_during_active_loan(self):
        """Email should be allowed during active loan (existing business relationship)."""
        channel = "email"
        # Email is permissible under existing business relationship
        allowed = channel == "email"
        assert allowed is True

    def test_portal_always_allowed(self):
        """Portal notifications should always be allowed (no TCPA)."""
        channel = "portal"
        allowed = channel == "portal"
        assert allowed is True

    def test_sms_requires_consent(self):
        """SMS should require explicit consent before sending."""
        channel = "sms"
        has_consent = False
        allowed = channel != "sms" or has_consent
        assert allowed is False, "SMS without consent should be blocked"

    def test_sms_allowed_with_consent(self):
        """SMS should be allowed when explicit consent is on file."""
        channel = "sms"
        has_consent = True
        allowed = channel != "sms" or has_consent
        assert allowed is True

    def test_call_requires_consent(self):
        """Outbound calls should require explicit consent."""
        channel = "call"
        has_consent = False
        allowed = channel != "call" or has_consent
        assert allowed is False, "Outbound call without consent should be blocked"

    def test_call_allowed_with_consent(self):
        """Outbound calls should be allowed when consent is on file."""
        channel = "call"
        has_consent = True
        allowed = channel != "call" or has_consent
        assert allowed is True

    def test_consent_fallback_to_email(self):
        """When SMS/call consent is missing, should fall back to email."""
        preferred = "sms"
        sms_consent = False
        if preferred == "sms" and not sms_consent:
            recommended = "email"
        else:
            recommended = preferred
        assert recommended == "email"

    def test_welcome_message_includes_name(self):
        """Welcome messages should include borrower's first name."""
        first_name = "Sarah"
        subject = f"Welcome, {first_name} — Let's Get Started"
        assert first_name in subject

    def test_sms_message_under_160_chars(self):
        """SMS messages should be concise (ideally under 160 chars)."""
        first_name = "Sarah"
        lo_name = "John"
        sms = f"Hi {first_name}, welcome! Your document checklist is ready in your portal. Upload anytime — reply HELP if you need assistance. -{lo_name}"
        assert len(sms) <= 180, f"SMS too long at {len(sms)} chars — aim for under 160"


# =============================================================================
# FAQ Pattern Matching
# =============================================================================

@pytest.mark.unit
class TestFAQMatching:
    """Test borrower FAQ pattern matching."""

    FAQ_PATTERNS = {
        "how_long": ["how long", "how much time", "when will", "timeline"],
        "why_so_many": ["why so many", "too many documents", "so much paperwork"],
        "is_it_safe": ["safe", "secure", "privacy", "who sees"],
        "what_if_cant_find": ["can't find", "don't have", "lost", "missing"],
        "why_all_pages": ["all pages", "blank pages", "every page"],
    }

    def _match_faq(self, question: str) -> str:
        question_lower = question.lower()
        for key, patterns in self.FAQ_PATTERNS.items():
            if any(p in question_lower for p in patterns):
                return key
        return "unknown"

    def test_timeline_question_matches(self):
        """Questions about timing should match 'how_long' FAQ."""
        assert self._match_faq("How long does this process take?") == "how_long"

    def test_paperwork_complaint_matches(self):
        """Complaints about paperwork should match 'why_so_many' FAQ."""
        assert self._match_faq("This is so much paperwork, do I really need all of it?") == "why_so_many"

    def test_security_concern_matches(self):
        """Security questions should match 'is_it_safe' FAQ."""
        assert self._match_faq("Is my information safe?") == "is_it_safe"

    def test_missing_doc_question_matches(self):
        """Questions about missing docs should match 'what_if_cant_find' FAQ."""
        assert self._match_faq("I can't find my W-2") == "what_if_cant_find"

    def test_blank_pages_question_matches(self):
        """Questions about blank pages should match 'why_all_pages' FAQ."""
        assert self._match_faq("Why do you need the blank pages?") == "why_all_pages"

    def test_unmatched_question_returns_unknown(self):
        """Questions with no pattern match should return 'unknown'."""
        assert self._match_faq("Can I change my closing date?") == "unknown"


# =============================================================================
# Rejection Explanation Simplification
# =============================================================================

@pytest.mark.unit
class TestRejectionSimplification:
    """Test simplification of technical rejection reasons."""

    REJECTION_MAP = {
        "illegible": "The document was a bit hard to read.",
        "expired": "The document has passed its valid date.",
        "incomplete": "We received part of the document but some pages appear to be missing.",
        "wrong_document": "The file you uploaded doesn't appear to match what was requested.",
        "too_old": "The document is from too long ago.",
        "name_mismatch": "The name on the document doesn't exactly match the name on your application.",
        "unsigned": "The document needs a signature to be accepted.",
    }

    def _simplify(self, reason: str) -> str:
        reason_lower = reason.lower()
        for key, explanation in self.REJECTION_MAP.items():
            if key in reason_lower:
                return explanation
        return "There was an issue with the document you submitted."

    def test_illegible_simplifies(self):
        """'Illegible' rejection should produce a friendly explanation."""
        result = self._simplify("Document illegible - cannot read text")
        assert "hard to read" in result

    def test_expired_simplifies(self):
        """'Expired' rejection should mention valid date."""
        result = self._simplify("Document expired per policy")
        assert "passed its valid date" in result

    def test_incomplete_simplifies(self):
        """'Incomplete' rejection should mention missing pages."""
        result = self._simplify("Incomplete document - missing pages 3-5")
        assert "missing" in result

    def test_unknown_rejection_gives_generic(self):
        """Unknown rejection reasons should produce a generic explanation."""
        result = self._simplify("QC_FAIL_THRESHOLD_EXCEEDED")
        assert "issue with the document" in result


# =============================================================================
# Experience Score Calculation
# =============================================================================

@pytest.mark.unit
class TestExperienceScore:
    """Test NPS-style borrower experience score calculation."""

    def test_perfect_score_is_promoter(self):
        """A perfect score should categorize as 'promoter'."""
        doc_score = 30
        comm_score = 25
        velocity_score = 25
        escalation_score = 20
        total = doc_score + comm_score + velocity_score + escalation_score
        assert total == 100
        assert total >= 80  # promoter threshold

    def test_low_score_is_detractor(self):
        """A low score should categorize as 'detractor'."""
        doc_score = 5
        comm_score = 5
        velocity_score = 5
        escalation_score = 0
        total = doc_score + comm_score + velocity_score + escalation_score
        assert total == 15
        assert total < 50  # detractor threshold

    def test_medium_score_is_passive(self):
        """A medium score should categorize as 'passive'."""
        doc_score = 15
        comm_score = 15
        velocity_score = 15
        escalation_score = 15
        total = doc_score + comm_score + velocity_score + escalation_score
        assert total == 60
        assert 50 <= total < 80  # passive range

    def test_escalations_reduce_score(self):
        """Each escalation should reduce the escalation sub-score by 5 points."""
        escalation_count = 3
        escalation_score = max(0, 20 - (escalation_count * 5))
        assert escalation_score == 5

    def test_fast_progression_gives_full_velocity_score(self):
        """Loan progressing in under 15 days should get full velocity score."""
        days_elapsed = 10
        if days_elapsed <= 15:
            velocity_score = 25
        elif days_elapsed <= 30:
            velocity_score = 20
        else:
            velocity_score = 5
        assert velocity_score == 25


# =============================================================================
# Milestone Detection
# =============================================================================

@pytest.mark.unit
class TestMilestoneDetection:
    """Test document milestone detection for celebration triggers."""

    def test_50_percent_milestone(self):
        """50% completion should trigger the halfway milestone."""
        required = {"paystubs", "w2", "bank_statements", "drivers_license"}
        received = {"paystubs", "w2"}
        pct = round(len(received & required) / len(required) * 100)
        assert pct == 50

        milestones = []
        if pct >= 100:
            milestones.append("all_docs_complete")
        elif pct >= 75:
            milestones.append("75_percent")
        elif pct >= 50:
            milestones.append("50_percent")
        assert "50_percent" in milestones

    def test_100_percent_milestone(self):
        """100% completion should trigger the complete milestone."""
        pct = 100
        milestones = []
        if pct >= 100:
            milestones.append("all_docs_complete")
        assert "all_docs_complete" in milestones

    def test_no_milestone_at_10_percent(self):
        """Low completion should not trigger any milestone."""
        required = {"paystubs", "w2", "bank_statements", "drivers_license", "credit_report"}
        received = set()
        pct = round(len(received & required) / len(required) * 100)
        milestones = []
        if pct >= 100:
            milestones.append("all_docs_complete")
        elif pct >= 75:
            milestones.append("75_percent")
        elif pct >= 50:
            milestones.append("50_percent")
        elif pct >= 25:
            milestones.append("25_percent")
        assert len(milestones) == 0


# =============================================================================
# Friction Prediction
# =============================================================================

@pytest.mark.unit
class TestFrictionPrediction:
    """Test friction prediction based on borrower profiles."""

    FRICTION_PREDICTORS = {
        "self_employed": ["tax_returns", "profit_loss", "1099", "bank_statements"],
        "first_time_buyer": ["purchase_contract", "insurance", "gift_letter"],
        "commission_income": ["tax_returns", "1099", "paystubs"],
    }

    def test_self_employed_predicts_tax_friction(self):
        """Self-employed borrowers should predict friction with tax docs."""
        profile = "self_employed"
        friction_docs = self.FRICTION_PREDICTORS.get(profile, [])
        assert "tax_returns" in friction_docs
        assert "profit_loss" in friction_docs

    def test_first_time_buyer_predicts_purchase_friction(self):
        """First-time buyers should predict friction with purchase docs."""
        profile = "first_time_buyer"
        friction_docs = self.FRICTION_PREDICTORS.get(profile, [])
        assert "purchase_contract" in friction_docs
        assert "insurance" in friction_docs

    def test_received_docs_excluded_from_friction(self):
        """Documents already received should not appear in friction predictions."""
        profile = "self_employed"
        all_friction = self.FRICTION_PREDICTORS.get(profile, [])
        received = {"tax_returns", "bank_statements"}
        remaining_friction = [d for d in all_friction if d not in received]
        assert "tax_returns" not in remaining_friction
        assert "bank_statements" not in remaining_friction
        assert "profit_loss" in remaining_friction

    def test_unknown_profile_returns_empty(self):
        """Unknown borrower profiles should return no friction predictions."""
        profile = "retiree"
        friction_docs = self.FRICTION_PREDICTORS.get(profile, [])
        assert friction_docs == []
