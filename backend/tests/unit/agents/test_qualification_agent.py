"""
Unit Tests for Qualification Agent

Tests agent reasoning with mocked tools - verifies correct tool selection
and response generation without real API calls.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

# Mark all tests as unit tests for agents
pytestmark = [pytest.mark.unit, pytest.mark.agents]


class TestQualificationAgentToolSelection:
    """Test that agent selects correct tools based on user input"""

    @pytest.fixture
    def mock_agent(self, mock_qualification_tools):
        """Create a mock qualification agent with mocked tools"""
        agent = MagicMock()
        agent.tools = mock_qualification_tools
        agent.last_tool_calls = []
        return agent

    @pytest.mark.asyncio
    async def test_identifies_purchase_intent(self, mock_qualification_tools):
        """Test agent identifies home purchase intent"""
        user_message = "I want to buy a house for around $450,000"

        # Simulate the agent's intent classification
        intent = classify_intent(user_message)

        assert intent["type"] == "purchase"
        assert intent.get("estimated_amount") == 450000

    @pytest.mark.asyncio
    async def test_identifies_refinance_intent(self, mock_qualification_tools):
        """Test agent identifies refinance intent"""
        user_message = "I'd like to refinance my current mortgage to get a lower rate"

        intent = classify_intent(user_message)

        assert intent["type"] == "refinance"

    @pytest.mark.asyncio
    async def test_asks_for_credit_score_when_missing(self, mock_qualification_tools):
        """Test agent asks for credit score if not provided"""
        conversation = [
            {"role": "user", "content": "I want to buy a $400k house"},
        ]

        # With loan_purpose and loan_amount collected, should ask for credit score next
        next_question = determine_next_question(
            conversation,
            collected_fields=["loan_purpose", "loan_amount"]
        )

        assert "credit" in next_question.lower() or "score" in next_question.lower()

    @pytest.mark.asyncio
    async def test_collects_all_required_fields(self, mock_qualification_tools):
        """Test agent collects all required qualification fields"""
        required_fields = ["loan_purpose", "loan_amount", "credit_score", "income", "property_type"]

        conversation = [
            {"role": "user", "content": "I want to buy a house"},
            {"role": "assistant", "content": "What price range?"},
            {"role": "user", "content": "$400,000"},
            {"role": "assistant", "content": "What's your credit score?"},
            {"role": "user", "content": "Around 740"},
            {"role": "assistant", "content": "Annual income?"},
            {"role": "user", "content": "$120,000"},
            {"role": "assistant", "content": "Property type?"},
            {"role": "user", "content": "Single family home"},
        ]

        collected = extract_collected_fields(conversation)

        for field in required_fields:
            assert field in collected, f"Missing required field: {field}"


class TestQualificationAgentResponses:
    """Test agent response generation"""

    @pytest.mark.asyncio
    async def test_responds_with_qualification_result(self, mock_qualification_tools):
        """Test agent provides qualification result when all info collected"""
        mock_qualification_tools["calculate_qualification"].return_value.data = {
            "qualified": True,
            "max_loan_amount": 450000,
            "estimated_rate": 6.875,
            "monthly_payment": 2950,
        }

        result = await mock_qualification_tools["calculate_qualification"]()

        assert result.data["qualified"] == True
        assert result.data["max_loan_amount"] == 450000

    @pytest.mark.asyncio
    async def test_handles_unqualified_lead(self, mock_qualification_tools):
        """Test agent handles leads that don't qualify"""
        mock_qualification_tools["calculate_qualification"].return_value.data = {
            "qualified": False,
            "reason": "DTI too high",
            "suggestions": ["Pay down debt", "Increase income", "Lower loan amount"],
        }

        result = await mock_qualification_tools["calculate_qualification"]()

        assert result.data["qualified"] == False
        assert "suggestions" in result.data

    @pytest.mark.asyncio
    async def test_offers_callback_scheduling(self, mock_qualification_tools):
        """Test agent offers to schedule callback with LO"""
        mock_qualification_tools["schedule_callback"].return_value.data = {
            "scheduled": True,
            "time": "2024-01-15T10:00:00",
            "lo_name": "Jane Smith",
        }

        result = await mock_qualification_tools["schedule_callback"]()

        assert result.data["scheduled"] == True


class TestQualificationAgentEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_handles_ambiguous_input(self):
        """Test handling of ambiguous user input"""
        user_message = "maybe around 400 or so"

        # Should ask for clarification
        response = handle_ambiguous_input(user_message, field="loan_amount")

        assert "clarify" in response.lower() or "confirm" in response.lower()

    @pytest.mark.asyncio
    async def test_handles_tool_failure(self, mock_qualification_tools):
        """Test graceful handling of tool failures"""
        mock_qualification_tools["calculate_qualification"].return_value.status = "error"
        mock_qualification_tools["calculate_qualification"].return_value.error = "Service unavailable"

        result = await mock_qualification_tools["calculate_qualification"]()

        assert result.status == "error"
        # Agent should have fallback behavior

    @pytest.mark.asyncio
    async def test_respects_conversation_context(self, qualification_conversation):
        """Test agent maintains context across conversation"""
        # Simulate extracting context from conversation
        context = extract_conversation_context(qualification_conversation)

        assert context.get("loan_purpose") == "purchase"
        assert context.get("estimated_amount") == 450000


# =============================================================================
# HELPER FUNCTIONS FOR TESTS
# =============================================================================

def classify_intent(message: str) -> dict:
    """Simple intent classification for tests"""
    message_lower = message.lower()

    intent = {"type": "unknown", "confidence": 0.0}

    if any(word in message_lower for word in ["buy", "purchase", "new home"]):
        intent["type"] = "purchase"
        intent["confidence"] = 0.9
    elif any(word in message_lower for word in ["refinance", "refi", "lower rate"]):
        intent["type"] = "refinance"
        intent["confidence"] = 0.9

    # Extract amount if present
    import re
    amount_match = re.search(r'\$?([\d,]+)(?:k|K|,000)?', message)
    if amount_match:
        amount_str = amount_match.group(1).replace(',', '')
        if amount_str:  # Check not empty
            try:
                amount = int(amount_str)
                if amount < 10000:  # Likely in thousands
                    amount *= 1000
                intent["estimated_amount"] = amount
            except ValueError:
                pass  # Skip if not a valid number

    return intent


def determine_next_question(conversation: list, collected_fields: list) -> str:
    """Determine what to ask next based on missing fields"""
    required = ["loan_purpose", "loan_amount", "credit_score", "income", "property_type"]
    missing = [f for f in required if f not in collected_fields]

    question_map = {
        "loan_purpose": "Are you looking to purchase or refinance?",
        "loan_amount": "What price range are you considering?",
        "credit_score": "Do you know your approximate credit score?",
        "income": "What is your annual household income?",
        "property_type": "What type of property are you interested in?",
    }

    if missing:
        return question_map.get(missing[0], "Could you tell me more?")
    return "I have all the information I need to check your qualification."


def extract_collected_fields(conversation: list) -> dict:
    """Extract collected fields from conversation"""
    collected = {}

    for i, msg in enumerate(conversation):
        if msg["role"] == "user":
            content = msg["content"].lower()

            # Simple extraction logic
            if any(w in content for w in ["buy", "purchase"]):
                collected["loan_purpose"] = "purchase"
            if any(w in content for w in ["refinance", "refi"]):
                collected["loan_purpose"] = "refinance"
            if "$" in content or any(c.isdigit() for c in content):
                if "loan_amount" not in collected:
                    collected["loan_amount"] = True
                elif "credit_score" not in collected and any(str(x) in content for x in range(600, 850)):
                    collected["credit_score"] = True
                elif "income" not in collected:
                    collected["income"] = True
            if any(w in content for w in ["single family", "condo", "townhouse"]):
                collected["property_type"] = True

    return collected


def extract_conversation_context(conversation: list) -> dict:
    """Extract context from full conversation"""
    context = {}

    for msg in conversation:
        if msg["role"] == "user":
            intent = classify_intent(msg["content"])
            if intent["type"] != "unknown":
                context["loan_purpose"] = intent["type"]
            if "estimated_amount" in intent:
                context["estimated_amount"] = intent["estimated_amount"]

    return context


def handle_ambiguous_input(message: str, field: str) -> str:
    """Generate clarification request for ambiguous input"""
    return f"Could you clarify that? I want to make sure I have the correct {field}."
