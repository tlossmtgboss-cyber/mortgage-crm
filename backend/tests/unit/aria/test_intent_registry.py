"""
Tests for aria/core/intent_registry.py

Pure data-structure tests — no mocking, no DB, no async.
Validates every Intent and SlotSpec in the registry against expected values.
"""

import pytest
import sys
from pathlib import Path

# Ensure backend is on sys.path so bare imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from aria.core.intent_registry import IntentRegistry, Intent, SlotSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Fresh registry for each test (bypasses singleton cache)."""
    IntentRegistry._instance = None
    reg = IntentRegistry.get()
    yield reg
    # Reset so other tests aren't affected by cached singleton
    IntentRegistry._instance = None


# ---------------------------------------------------------------------------
# 1. Singleton pattern
# ---------------------------------------------------------------------------

class TestSingletonPattern:
    def test_get_returns_same_instance(self):
        IntentRegistry._instance = None
        a = IntentRegistry.get()
        b = IntentRegistry.get()
        assert a is b

    def test_get_returns_same_instance_across_multiple_calls(self):
        IntentRegistry._instance = None
        instances = [IntentRegistry.get() for _ in range(5)]
        assert all(inst is instances[0] for inst in instances)


# ---------------------------------------------------------------------------
# 2. All 14 intents registered
# ---------------------------------------------------------------------------

class TestIntentCount:
    def test_registry_contains_15_intents(self, registry):
        assert len(registry.intents) == 15

    def test_all_intent_names_are_unique(self, registry):
        names = [i.name for i in registry.intents]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# 3. Required slots defined correctly for each intent
# ---------------------------------------------------------------------------

EXPECTED_REQUIRED_SLOTS = {
    "send_preapproval_letter":    ["borrower_id", "recipient_email", "approval_amount"],
    "send_conditional_approval":  ["borrower_id", "recipient_email", "conditions"],
    "send_adverse_action_notice": ["borrower_id", "denial_reasons", "credit_score"],
    "generate_loe":               ["borrower_id", "loe_topic"],
    "send_sms":                   ["recipient", "message"],
    "send_email":                 ["recipient", "subject", "body"],
    "schedule_call":              ["with_person", "call_date", "call_time"],
    "update_loan_status":         ["borrower_id", "new_stage"],
    "add_loan_note":              ["borrower_id", "note_text"],
    "create_task":                ["task_description", "due_date"],
    "request_documents":          ["borrower_id", "doc_list"],
    "loan_status_lookup":         ["borrower_id"],
    "mortgage_guideline_question": ["question"],
    "pipeline_report":            [],
    "run_income_analysis":        ["borrower_id"],
}


class TestRequiredSlots:
    @pytest.mark.parametrize("intent_name,expected_slots", list(EXPECTED_REQUIRED_SLOTS.items()))
    def test_required_slot_names_match(self, registry, intent_name, expected_slots):
        intent = registry.get_intent(intent_name)
        assert intent is not None, f"Intent '{intent_name}' not found in registry"
        actual = [s.name for s in intent.required_slots]
        assert actual == expected_slots


# ---------------------------------------------------------------------------
# 4. get_intent() returns correct intent by name
# ---------------------------------------------------------------------------

ALL_INTENT_NAMES = [
    "send_preapproval_letter",
    "send_conditional_approval",
    "send_adverse_action_notice",
    "generate_loe",
    "send_sms",
    "send_email",
    "schedule_call",
    "update_loan_status",
    "add_loan_note",
    "create_task",
    "request_documents",
    "loan_status_lookup",
    "mortgage_guideline_question",
    "pipeline_report",
    "run_income_analysis",
]


class TestGetIntent:
    @pytest.mark.parametrize("name", ALL_INTENT_NAMES)
    def test_get_intent_returns_intent_by_name(self, registry, name):
        intent = registry.get_intent(name)
        assert intent is not None
        assert isinstance(intent, Intent)
        assert intent.name == name


# ---------------------------------------------------------------------------
# 5. get_intent() returns None for unknown intent
# ---------------------------------------------------------------------------

class TestGetIntentUnknown:
    @pytest.mark.parametrize("bogus_name", [
        "nonexistent_intent",
        "",
        "send_fax",
        "SEND_SMS",
        "send-sms",
        "send sms",
    ])
    def test_get_intent_returns_none_for_unknown(self, registry, bogus_name):
        assert registry.get_intent(bogus_name) is None


# ---------------------------------------------------------------------------
# 6. SlotSpec defaults
# ---------------------------------------------------------------------------

class TestSlotSpecDefaults:
    def test_required_defaults_to_true(self):
        slot = SlotSpec(name="test", description="desc", slot_type="text")
        assert slot.required is True

    def test_choices_defaults_to_empty_list(self):
        slot = SlotSpec(name="test", description="desc", slot_type="text")
        assert slot.choices == []

    def test_default_defaults_to_none(self):
        slot = SlotSpec(name="test", description="desc", slot_type="text")
        assert slot.default is None

    def test_extraction_hint_defaults_to_empty_string(self):
        slot = SlotSpec(name="test", description="desc", slot_type="text")
        assert slot.extraction_hint == ""

    def test_choices_are_independent_across_instances(self):
        """Ensure default list factory creates distinct lists per instance."""
        a = SlotSpec(name="a", description="d", slot_type="text")
        b = SlotSpec(name="b", description="d", slot_type="text")
        a.choices.append("oops")
        assert b.choices == []


# ---------------------------------------------------------------------------
# 7. Intent categories cover all expected categories
# ---------------------------------------------------------------------------

EXPECTED_CATEGORIES = {"documents", "communication", "pipeline", "lookup", "knowledge", "reporting", "analysis"}


class TestIntentCategories:
    def test_all_expected_categories_present(self, registry):
        actual = {i.category for i in registry.intents}
        assert actual == EXPECTED_CATEGORIES

    def test_no_intent_uses_default_general_category(self, registry):
        for intent in registry.intents:
            assert intent.category != "general", (
                f"Intent '{intent.name}' still uses default 'general' category"
            )


# ---------------------------------------------------------------------------
# 8. trigger_phrases are non-empty for all intents
# ---------------------------------------------------------------------------

class TestTriggerPhrases:
    @pytest.mark.parametrize("name", ALL_INTENT_NAMES)
    def test_trigger_phrases_non_empty(self, registry, name):
        intent = registry.get_intent(name)
        assert len(intent.trigger_phrases) > 0, (
            f"Intent '{name}' has no trigger phrases"
        )

    @pytest.mark.parametrize("name", ALL_INTENT_NAMES)
    def test_trigger_phrases_are_all_strings(self, registry, name):
        intent = registry.get_intent(name)
        for phrase in intent.trigger_phrases:
            assert isinstance(phrase, str)
            assert len(phrase.strip()) > 0, (
                f"Intent '{name}' has a blank trigger phrase"
            )


# ---------------------------------------------------------------------------
# 9. Intent.get_slot() finds required and optional slots
# ---------------------------------------------------------------------------

class TestIntentGetSlot:
    def test_get_slot_finds_required_slot(self, registry):
        intent = registry.get_intent("send_preapproval_letter")
        slot = intent.get_slot("borrower_id")
        assert slot is not None
        assert slot.name == "borrower_id"
        assert slot.required is True

    def test_get_slot_finds_optional_slot(self, registry):
        intent = registry.get_intent("send_preapproval_letter")
        slot = intent.get_slot("recipient_name")
        assert slot is not None
        assert slot.name == "recipient_name"
        assert slot.required is False

    def test_get_slot_finds_optional_slot_with_default(self, registry):
        intent = registry.get_intent("send_preapproval_letter")
        slot = intent.get_slot("expiry_days")
        assert slot is not None
        assert slot.default == 30

    def test_get_slot_works_for_send_email_cc(self, registry):
        intent = registry.get_intent("send_email")
        slot = intent.get_slot("cc")
        assert slot is not None
        assert slot.slot_type == "email"
        assert slot.required is False

    def test_get_slot_works_for_create_task_optional_borrower(self, registry):
        intent = registry.get_intent("create_task")
        slot = intent.get_slot("borrower_id")
        assert slot is not None
        assert slot.required is False
        assert slot.slot_type == "borrower"


# ---------------------------------------------------------------------------
# 10. Intent.get_slot() returns None for unknown slot name
# ---------------------------------------------------------------------------

class TestGetSlotUnknown:
    def test_get_slot_returns_none_for_unknown(self, registry):
        intent = registry.get_intent("send_sms")
        assert intent.get_slot("nonexistent_slot") is None

    def test_get_slot_returns_none_for_empty_string(self, registry):
        intent = registry.get_intent("send_sms")
        assert intent.get_slot("") is None

    def test_get_slot_returns_none_for_slot_from_different_intent(self, registry):
        """A slot that exists on another intent should not be found here."""
        intent = registry.get_intent("send_sms")
        assert intent.get_slot("approval_amount") is None


# ---------------------------------------------------------------------------
# 11. requires_confirmation defaults and overrides
# ---------------------------------------------------------------------------

class TestRequiresConfirmation:
    def test_default_requires_confirmation_is_true(self):
        """Intent dataclass default for requires_confirmation is True."""
        intent = Intent(
            name="test",
            description="test",
            trigger_phrases=["test"],
            required_slots=[],
        )
        assert intent.requires_confirmation is True

    @pytest.mark.parametrize("name", [
        "send_preapproval_letter",
        "send_conditional_approval",
        "send_adverse_action_notice",
        "generate_loe",
        "send_sms",
        "send_email",
        "schedule_call",
        "update_loan_status",
        "request_documents",
    ])
    def test_confirmation_required_intents(self, registry, name):
        intent = registry.get_intent(name)
        assert intent.requires_confirmation is True, (
            f"Intent '{name}' should require confirmation"
        )

    def test_add_loan_note_does_not_require_confirmation(self, registry):
        intent = registry.get_intent("add_loan_note")
        assert intent.requires_confirmation is False

    def test_create_task_does_not_require_confirmation(self, registry):
        intent = registry.get_intent("create_task")
        assert intent.requires_confirmation is False

    @pytest.mark.parametrize("name", [
        "loan_status_lookup",
        "mortgage_guideline_question",
        "pipeline_report",
        "run_income_analysis",
    ])
    def test_readonly_intents_do_not_require_confirmation(self, registry, name):
        intent = registry.get_intent(name)
        assert intent.requires_confirmation is False, (
            f"Read-only intent '{name}' should not require confirmation"
        )


# ---------------------------------------------------------------------------
# 12. Slot type values are valid
# ---------------------------------------------------------------------------

VALID_SLOT_TYPES = {"text", "number", "email", "phone", "date", "choice", "borrower", "contact"}


class TestSlotTypes:
    def test_all_slot_types_are_valid(self, registry):
        for intent in registry.intents:
            for slot in intent.required_slots + intent.optional_slots:
                assert slot.slot_type in VALID_SLOT_TYPES, (
                    f"Intent '{intent.name}', slot '{slot.name}' has invalid "
                    f"slot_type '{slot.slot_type}'. Valid types: {VALID_SLOT_TYPES}"
                )

    def test_choice_slot_has_choices_defined(self, registry):
        """Any slot with type 'choice' must have a non-empty choices list."""
        for intent in registry.intents:
            for slot in intent.required_slots + intent.optional_slots:
                if slot.slot_type == "choice":
                    assert len(slot.choices) > 0, (
                        f"Intent '{intent.name}', slot '{slot.name}' is type 'choice' "
                        f"but has no choices defined"
                    )

    def test_update_loan_status_new_stage_choices(self, registry):
        """Verify the specific pipeline stage choices on update_loan_status."""
        intent = registry.get_intent("update_loan_status")
        slot = intent.get_slot("new_stage")
        assert slot.slot_type == "choice"
        expected_stages = [
            "lead", "application", "processing", "underwriting",
            "conditional_approval", "clear_to_close", "closing", "funded", "denied",
        ]
        assert slot.choices == expected_stages

    def test_borrower_type_slots_are_present(self, registry):
        """Multiple intents reference borrower_id with type 'borrower'."""
        borrower_intents = [
            "send_preapproval_letter", "send_conditional_approval",
            "send_adverse_action_notice", "generate_loe",
            "update_loan_status", "add_loan_note", "request_documents",
            "loan_status_lookup", "run_income_analysis",
        ]
        for name in borrower_intents:
            intent = registry.get_intent(name)
            slot = intent.get_slot("borrower_id")
            assert slot is not None, f"Intent '{name}' missing borrower_id slot"
            assert slot.slot_type == "borrower"

    def test_contact_type_slots(self, registry):
        """send_sms and send_email use 'contact' type for recipient."""
        for name in ["send_sms", "send_email"]:
            intent = registry.get_intent(name)
            slot = intent.get_slot("recipient")
            assert slot.slot_type == "contact"

        intent = registry.get_intent("schedule_call")
        slot = intent.get_slot("with_person")
        assert slot.slot_type == "contact"


# ---------------------------------------------------------------------------
# Structural integrity extras
# ---------------------------------------------------------------------------

class TestStructuralIntegrity:
    def test_all_intents_have_non_empty_description(self, registry):
        for intent in registry.intents:
            assert isinstance(intent.description, str)
            assert len(intent.description.strip()) > 0, (
                f"Intent '{intent.name}' has empty description"
            )

    def test_all_slots_have_non_empty_description(self, registry):
        for intent in registry.intents:
            for slot in intent.required_slots + intent.optional_slots:
                assert isinstance(slot.description, str)
                assert len(slot.description.strip()) > 0, (
                    f"Intent '{intent.name}', slot '{slot.name}' has empty description"
                )

    def test_optional_slots_all_have_required_false(self, registry):
        """Every slot in optional_slots list should have required=False."""
        for intent in registry.intents:
            for slot in intent.optional_slots:
                assert slot.required is False, (
                    f"Intent '{intent.name}', optional slot '{slot.name}' "
                    f"has required=True (should be False)"
                )

    def test_required_slots_all_have_required_true(self, registry):
        """Every slot in required_slots list should have required=True."""
        for intent in registry.intents:
            for slot in intent.required_slots:
                assert slot.required is True, (
                    f"Intent '{intent.name}', required slot '{slot.name}' "
                    f"has required=False (should be True)"
                )
