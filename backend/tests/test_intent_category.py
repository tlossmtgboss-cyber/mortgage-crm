from aria.core.intent_registry import intent_category


def test_knowledge_intent_is_factual():
    assert intent_category("mortgage_guideline_question") == "factual"


def test_action_intent_is_operational():
    assert intent_category("send_sms") == "operational"


def test_none_or_unknown_is_chitchat():
    assert intent_category(None) == "chitchat"
    assert intent_category("") == "chitchat"
    assert intent_category("not_a_real_intent") == "chitchat"
