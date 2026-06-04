import pytest
from aria.core import grounding
from aria.core.grounding import (
    GroundingResult,
    is_sufficiently_grounded,
    looks_like_guideline_question,
    format_grounded_message,
)


def test_sufficient_when_sources_and_confidence_ok():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=0.7)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is True


def test_insufficient_when_no_sources():
    r = GroundingResult(answer="a", sources=[], confidence=0.9)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_insufficient_when_low_confidence():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=0.2)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_insufficient_when_confidence_none():
    r = GroundingResult(answer="a", sources=[{"guideline_name": "FHA"}], confidence=None)
    assert is_sufficiently_grounded(r, min_confidence=0.45) is False


def test_looks_like_guideline_question():
    assert looks_like_guideline_question("What is the FHA reserve requirement?") is True
    assert looks_like_guideline_question("How many leads do I have today?") is False
    assert looks_like_guideline_question("") is False


def test_format_grounded_message_includes_sources():
    msg = format_grounded_message("Answer body [1].", [{"guideline_name": "FHA Handbook 4000.1"}])
    assert "Answer body [1]." in msg
    assert "FHA Handbook 4000.1" in msg


@pytest.mark.asyncio
async def test_ground_answer_marks_grounded(monkeypatch):
    async def fake_rag(self, question, loan_program=None, agency=None, include_overlays=True, tenant_id=None):
        return {"answer": "FHA requires X [1].",
                "sources": [{"guideline_name": "FHA Handbook 4000.1"}],
                "citations": [{"index": 1, "guideline_name": "FHA Handbook 4000.1"}],
                "confidence": 0.8, "rag_enabled": True, "query": question}
    monkeypatch.setattr("aria.tools.knowledge_tools.KnowledgeTools.search_guidelines_rag", fake_rag)
    result = await grounding.ground_answer("FHA reserves?", org_id=1)
    assert result.grounded is True
    assert result.sources and result.confidence == 0.8


@pytest.mark.asyncio
async def test_ground_answer_disclaimer_on_no_results(monkeypatch):
    async def fake_rag(self, question, loan_program=None, agency=None, include_overlays=True, tenant_id=None):
        return {"answer": "General knowledge answer.", "sources": [], "citations": [],
                "confidence": None, "rag_enabled": False,
                "disclaimer": "Answer based on general knowledge.", "query": question}
    monkeypatch.setattr("aria.tools.knowledge_tools.KnowledgeTools.search_guidelines_rag", fake_rag)
    result = await grounding.ground_answer("obscure question", org_id=1)
    assert result.grounded is False
    assert result.disclaimer
