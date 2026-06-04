import pytest
from aria.core import conversation_engine as ce
from aria.core import grounding


def _base_state(message, intent="mortgage_guideline_question", slots=None):
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content=message)],
        "intent": intent, "slots": slots if slots is not None else {"question": message},
        "missing_slots": [], "current_slot_question": None,
        "phase": ce.DialoguePhase.UNDERSTANDING.value,
        "task_result": None, "confirmation_preview": None,
        "user_id": "u1", "org_id": "1", "user_name": "Lo", "user_email": None,
        "user_role": "loan_officer", "mode": None, "voice_preferences": None,
        "iteration_count": 0, "error": None,
    }


def test_route_after_nlu_sends_factual_to_ground_when_flag_on(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    state = _base_state("FHA reserves?")
    assert ce.route_after_nlu(state) == "ground"


def test_route_after_nlu_unchanged_when_flag_off(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "false")
    state = _base_state("FHA reserves?")
    assert ce.route_after_nlu(state) == "confirmation"


@pytest.mark.asyncio
async def test_grounding_check_emits_disclaimer_when_insufficient(monkeypatch):
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(answer="x", sources=[], confidence=None,
                                         grounded=False, disclaimer="DISC")
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("obscure")
    out = await ce.ground_node(state)
    merged = {**state, **out}
    final = ce.grounding_check_node(merged)
    assert "DISC" in final["messages"][-1].content


@pytest.mark.asyncio
async def test_grounding_check_emits_cited_answer_when_grounded(monkeypatch):
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(
            answer="FHA requires X [1].",
            sources=[{"guideline_name": "FHA Handbook 4000.1"}],
            confidence=0.8, grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("FHA reserves?")
    out = await ce.ground_node(state)
    merged = {**state, **out}
    final = ce.grounding_check_node(merged)
    text = final["messages"][-1].content
    assert "FHA requires X [1]." in text
    assert "FHA Handbook 4000.1" in text


@pytest.mark.asyncio
async def test_query_mode_delegates_guideline_question(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    async def fake_ground(question, org_id):
        return grounding.GroundingResult(answer="FHA X [1].",
            sources=[{"guideline_name": "FHA Handbook 4000.1"}], confidence=0.8, grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    state = _base_state("What is the FHA reserve requirement?", intent=None, slots={})
    state["mode"] = "query"
    out = await ce.query_mode_node(state)
    text = out["messages"][-1].content
    assert "FHA X [1]." in text and "FHA Handbook 4000.1" in text


@pytest.mark.asyncio
async def test_query_mode_operational_not_delegated(monkeypatch):
    monkeypatch.setenv("ARIA_GROUNDING_ENABLED", "true")
    called = {"ground": False}
    async def fake_ground(question, org_id):
        called["ground"] = True
        return grounding.GroundingResult(answer="x", grounded=True)
    monkeypatch.setattr(ce, "ground_answer", fake_ground)
    from aria.core.grounding import looks_like_guideline_question
    # Operational lookups must NOT be classified as guideline questions:
    assert looks_like_guideline_question("How many leads do I have today?") is False
    assert called["ground"] is False
