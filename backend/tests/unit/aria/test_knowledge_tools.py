"""
Unit Tests for Aria Knowledge Tools

Tests answer_guideline_question and run_income_analysis in isolation
with Anthropic client and income services mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def knowledge_tools():
    from aria.tools.knowledge_tools import KnowledgeTools
    return KnowledgeTools()


def _make_anthropic_response(text: str):
    """Build a mock Anthropic messages.create() response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ===================================================================
# answer_guideline_question
# ===================================================================

class TestAnswerGuidelineQuestion:

    async def test_calls_anthropic_api(self, knowledge_tools):
        """answer_guideline_question() invokes the Anthropic messages.create endpoint."""
        mock_response = _make_anthropic_response(
            "FHA requires a minimum 3.5% down payment with a 580+ credit score."
        )

        with patch(
            "aria.tools.knowledge_tools.client"
        ) as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            await knowledge_tools.answer_guideline_question(
                "What is the FHA minimum down payment?"
            )

        mock_client.messages.create.assert_awaited_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_tokens"] == 500
        # Verify the question text is embedded in the prompt
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert "FHA minimum down payment" in messages[0]["content"]

    async def test_returns_answer_text_and_disclaimer(self, knowledge_tools):
        """answer_guideline_question() returns text, sources, and a compliance disclaimer."""
        answer_text = "For Conventional loans, the max DTI is typically 45-50%."
        mock_response = _make_anthropic_response(answer_text)

        with patch(
            "aria.tools.knowledge_tools.client"
        ) as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            result = await knowledge_tools.answer_guideline_question(
                "What is the conventional max DTI?"
            )

        assert result["text"] == answer_text
        assert isinstance(result["sources"], list)
        assert len(result["sources"]) > 0
        assert "disclaimer" in result
        assert "verify" in result["disclaimer"].lower()

    async def test_includes_rag_enabled_false_in_response(self, knowledge_tools):
        """answer_guideline_question() marks rag_enabled=False (no vector store yet)."""
        mock_response = _make_anthropic_response("VA loans have no down payment.")

        with patch(
            "aria.tools.knowledge_tools.client"
        ) as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            result = await knowledge_tools.answer_guideline_question(
                "Does VA require a down payment?"
            )

        assert result["rag_enabled"] is False
        assert result["confidence"] is None


# ===================================================================
# run_income_analysis
# ===================================================================

class TestRunIncomeAnalysis:

    async def test_tries_income_calculation_service_first(self, knowledge_tools):
        """run_income_analysis() delegates to IncomeCalculationService when available."""
        mock_service = MagicMock()
        mock_service.calculate_for_loan.return_value = {
            "total_qualifying_income": 8500.00,
            "income_sources": [
                {"type": "base_salary", "amount": 7000.00},
                {"type": "bonus", "amount": 1500.00},
            ],
            "dti_ratio": 38.2,
            "notes": "Bonus averaged over 24 months.",
        }

        with patch(
            "services.income.income_calculation_service.IncomeCalculationService",
            return_value=mock_service,
        ):
            result = await knowledge_tools.run_income_analysis(
                loan_id=101, org_id="org-100",
            )

        mock_service.calculate_for_loan.assert_called_once_with(101, "org-100")
        assert result["qualifying_income"] == 8500.00
        assert len(result["income_sources"]) == 2
        assert result["dti_ratio"] == 38.2
        assert "Bonus" in result["analysis_notes"]

    async def test_falls_back_gracefully_when_service_unavailable(self, knowledge_tools):
        """run_income_analysis() returns a placeholder when IncomeCalculationService fails."""
        with patch(
            "services.income.income_calculation_service.IncomeCalculationService",
            side_effect=ImportError("Module not configured"),
        ):
            result = await knowledge_tools.run_income_analysis(
                loan_id=999, org_id="org-100",
            )

        assert result["qualifying_income"] is None
        assert result["income_sources"] == []
        assert result["dti_ratio"] is None
        assert "manual review" in result["analysis_notes"].lower()

    async def test_returns_dict_with_analysis_data(self, knowledge_tools):
        """run_income_analysis() returns the expected dict structure from a successful calc."""
        mock_service = MagicMock()
        mock_service.calculate_for_loan.return_value = {
            "total_qualifying_income": 12000.00,
            "income_sources": [
                {"type": "w2_salary", "amount": 10000.00},
                {"type": "rental_income", "amount": 2000.00},
            ],
            "dti_ratio": 32.5,
            "notes": "",
        }

        with patch(
            "services.income.income_calculation_service.IncomeCalculationService",
            return_value=mock_service,
        ):
            result = await knowledge_tools.run_income_analysis(
                loan_id=200, org_id="org-200",
            )

        # Verify every expected key exists and has a sensible type
        assert isinstance(result["qualifying_income"], (int, float))
        assert isinstance(result["income_sources"], list)
        assert isinstance(result["analysis_notes"], str)
        assert result["qualifying_income"] == 12000.00
        assert result["dti_ratio"] == 32.5

    async def test_falls_back_when_service_returns_none(self, knowledge_tools):
        """run_income_analysis() falls back when calculate_for_loan returns None."""
        mock_service = MagicMock()
        mock_service.calculate_for_loan.return_value = None

        with patch(
            "services.income.income_calculation_service.IncomeCalculationService",
            return_value=mock_service,
        ):
            result = await knowledge_tools.run_income_analysis(
                loan_id=404, org_id="org-100",
            )

        # Should fall through to placeholder
        assert result["qualifying_income"] is None
        assert result["income_sources"] == []
        assert "manual review" in result["analysis_notes"].lower()
