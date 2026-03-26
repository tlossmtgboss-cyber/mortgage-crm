"""
Tests for compound intent detection in the intent router.

Covers:
- Compound intent detection: multi-action commands correctly classified as "compound"
- Single intent isolation: single-action commands must NOT trigger compound
- Edge cases: same-action-type combos, mixed case, extra whitespace
- Pattern ordering: compound patterns must precede individual patterns in INTENT_PATTERNS
"""

import pytest
import re
from typing import List, Tuple

from agents.intent_router import (
    Intent,
    INTENT_PATTERNS,
    classify_intent_fast,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fast_intent(query: str) -> str:
    """Return the intent string from classify_intent_fast, or 'none' if unmatched."""
    intent, _confidence, _pattern = classify_intent_fast(query)
    return intent or "none"


def _pattern_order() -> List[str]:
    """Return the key order of INTENT_PATTERNS as a list."""
    return list(INTENT_PATTERNS.keys())


# ---------------------------------------------------------------------------
# 1. Compound intent detection
# ---------------------------------------------------------------------------

class TestCompoundIntentDetection:
    """Multi-action commands should all classify as 'compound'."""

    @pytest.mark.unit
    def test_text_and_schedule(self):
        result = fast_intent("send a text to Phil George and schedule a time to speak")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_text_and_book_meeting(self):
        result = fast_intent("text John and book a meeting on my calendar")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_email_docs_then_schedule_followup(self):
        result = fast_intent("email Sarah the docs and then schedule a follow-up call")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_sms_and_create_task(self):
        # "send SMS ... and also ... schedule" -- but this says "create a task" not schedule
        # The compound patterns require the second action to be schedule/book/set up/arrange/calendar
        # or the first to be schedule and second to be send/text/message/sms/email.
        # "create a task" doesn't match compound patterns, so this tests whether the patterns
        # are specific enough. Let's test a variant that does match:
        result = fast_intent("send SMS to the borrower and also set up a time to review their file")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_message_and_schedule_appointment(self):
        result = fast_intent("message Phil and schedule an appointment")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_sms_then_book_call(self):
        result = fast_intent("sms Phil then book a call with him")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_schedule_then_send_email(self):
        """Compound also works when schedule comes first."""
        result = fast_intent("schedule a meeting and then send an email confirmation")
        assert result == "compound", f"Expected 'compound', got '{result}'"

    @pytest.mark.unit
    def test_call_and_schedule(self):
        result = fast_intent("call the borrower and then schedule a follow-up on the calendar")
        assert result == "compound", f"Expected 'compound', got '{result}'"


# ---------------------------------------------------------------------------
# 2. Single intents should NOT trigger compound
# ---------------------------------------------------------------------------

class TestSingleIntentNotCompound:
    """Single-action commands must classify as their own intent, not compound."""

    @pytest.mark.unit
    def test_send_text_only(self):
        """A plain text/sms command with no second action should not be compound."""
        result = fast_intent("send a text to Phil George")
        assert result != "compound", f"Single SMS classified as compound"

    @pytest.mark.unit
    def test_schedule_meeting_only(self):
        result = fast_intent("schedule a meeting with Phil")
        assert result != "compound", f"Single schedule classified as compound"
        assert result == "schedule", f"Expected 'schedule', got '{result}'"

    @pytest.mark.unit
    def test_check_pipeline(self):
        result = fast_intent("check my pipeline")
        assert result != "compound", f"Pipeline query classified as compound"
        assert result == "pipeline", f"Expected 'pipeline', got '{result}'"

    @pytest.mark.unit
    def test_email_only(self):
        result = fast_intent("email Sarah the docs")
        assert result != "compound", f"Single email classified as compound"

    @pytest.mark.unit
    def test_book_appointment_only(self):
        result = fast_intent("book an appointment for tomorrow")
        assert result != "compound", f"Single booking classified as compound"
        assert result == "schedule", f"Expected 'schedule', got '{result}'"

    @pytest.mark.unit
    def test_sms_borrower_only(self):
        result = fast_intent("send SMS to the borrower about their application")
        assert result != "compound", f"Single SMS classified as compound"

    @pytest.mark.unit
    def test_call_only(self):
        result = fast_intent("call Phil George")
        assert result != "compound", f"Single call classified as compound"
        assert result == "calls", f"Expected 'calls', got '{result}'"


# ---------------------------------------------------------------------------
# 3. Edge cases
# ---------------------------------------------------------------------------

class TestCompoundEdgeCases:

    @pytest.mark.unit
    def test_same_action_type_not_compound(self):
        """Two schedule actions should not be compound -- it's the same domain."""
        result = fast_intent("schedule and reschedule")
        assert result != "compound", (
            f"Same-action-type pair 'schedule and reschedule' should not be compound, got '{result}'"
        )

    @pytest.mark.unit
    def test_mixed_case(self):
        """Compound detection should be case-insensitive."""
        result = fast_intent("TEXT John AND Book a Meeting on my calendar")
        assert result == "compound", f"Mixed case failed: got '{result}'"

    @pytest.mark.unit
    def test_extra_whitespace(self):
        """Extra whitespace should not break pattern matching."""
        result = fast_intent("  text  John  and  book  a  meeting  on  my  calendar  ")
        assert result == "compound", f"Extra whitespace failed: got '{result}'"

    @pytest.mark.unit
    def test_leading_trailing_whitespace(self):
        result = fast_intent("   send a text to Phil and schedule a call   ")
        assert result == "compound", f"Leading/trailing whitespace failed: got '{result}'"

    @pytest.mark.unit
    def test_connector_then(self):
        """'then' as a connector should work like 'and'."""
        result = fast_intent("text Phil then schedule a meeting")
        assert result == "compound", f"Connector 'then' failed: got '{result}'"

    @pytest.mark.unit
    def test_connector_also(self):
        """'also' as a connector should work."""
        result = fast_intent("send a message to Phil and also schedule a call")
        assert result == "compound", f"Connector 'also' failed: got '{result}'"

    @pytest.mark.unit
    def test_connector_plus(self):
        """'plus' as a connector should work."""
        result = fast_intent("email the docs to Sarah plus schedule a follow-up")
        assert result == "compound", f"Connector 'plus' failed: got '{result}'"

    @pytest.mark.unit
    def test_very_long_middle_section(self):
        """If the text between action keywords exceeds the pattern's character limit, it should not match."""
        # The compound patterns allow {1,40} chars between parts. Build a string with >40 chars in the middle.
        filler = "a" * 50
        query = f"text Phil {filler} and schedule a meeting"
        result = fast_intent(query)
        assert result != "compound", (
            f"Overly long middle section should not match compound, got '{result}'"
        )


# ---------------------------------------------------------------------------
# 4. Pattern ordering — compound must come before individual patterns
# ---------------------------------------------------------------------------

class TestCompoundPatternOrdering:

    @pytest.mark.unit
    def test_compound_before_email(self):
        """Compound patterns must appear before email patterns in INTENT_PATTERNS."""
        order = _pattern_order()
        compound_idx = order.index("compound")
        email_idx = order.index("email")
        assert compound_idx < email_idx, (
            f"'compound' at index {compound_idx} must come before 'email' at index {email_idx}"
        )

    @pytest.mark.unit
    def test_compound_before_schedule(self):
        order = _pattern_order()
        compound_idx = order.index("compound")
        schedule_idx = order.index("schedule")
        assert compound_idx < schedule_idx, (
            f"'compound' at index {compound_idx} must come before 'schedule' at index {schedule_idx}"
        )

    @pytest.mark.unit
    def test_compound_before_calls(self):
        order = _pattern_order()
        compound_idx = order.index("compound")
        calls_idx = order.index("calls")
        assert compound_idx < calls_idx, (
            f"'compound' at index {compound_idx} must come before 'calls' at index {calls_idx}"
        )

    @pytest.mark.unit
    def test_compound_before_pipeline(self):
        order = _pattern_order()
        compound_idx = order.index("compound")
        pipeline_idx = order.index("pipeline")
        assert compound_idx < pipeline_idx, (
            f"'compound' at index {compound_idx} must come before 'pipeline' at index {pipeline_idx}"
        )

    @pytest.mark.unit
    def test_compound_before_leads(self):
        order = _pattern_order()
        compound_idx = order.index("compound")
        leads_idx = order.index("leads")
        assert compound_idx < leads_idx, (
            f"'compound' at index {compound_idx} must come before 'leads' at index {leads_idx}"
        )

    @pytest.mark.unit
    def test_compound_before_all_single_action_intents(self):
        """Compound must come before every intent that could partially match a compound query."""
        single_action_intents = ["email", "schedule", "calls", "pipeline", "leads", "tasks", "documents"]
        order = _pattern_order()
        compound_idx = order.index("compound")
        for intent_key in single_action_intents:
            if intent_key in order:
                intent_idx = order.index(intent_key)
                assert compound_idx < intent_idx, (
                    f"'compound' at index {compound_idx} must come before "
                    f"'{intent_key}' at index {intent_idx}"
                )


# ---------------------------------------------------------------------------
# 5. Intent enum completeness
# ---------------------------------------------------------------------------

class TestIntentEnum:

    @pytest.mark.unit
    def test_compound_in_intent_enum(self):
        """The COMPOUND intent must exist in the Intent enum."""
        assert hasattr(Intent, "COMPOUND")
        assert Intent.COMPOUND.value == "compound"

    @pytest.mark.unit
    def test_compound_in_patterns(self):
        """The 'compound' key must exist in INTENT_PATTERNS."""
        assert "compound" in INTENT_PATTERNS, "Missing 'compound' key in INTENT_PATTERNS"

    @pytest.mark.unit
    def test_compound_patterns_not_empty(self):
        """There must be at least one compound regex pattern."""
        assert len(INTENT_PATTERNS["compound"]) > 0, "INTENT_PATTERNS['compound'] is empty"

    @pytest.mark.unit
    def test_all_compound_patterns_are_valid_regex(self):
        """Every compound pattern must be a valid regex."""
        for i, pattern in enumerate(INTENT_PATTERNS["compound"]):
            try:
                re.compile(pattern)
            except re.error as e:
                pytest.fail(f"Compound pattern [{i}] is invalid regex: {pattern!r} -- {e}")
