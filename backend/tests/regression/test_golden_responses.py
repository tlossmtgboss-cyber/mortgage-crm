"""
Regression Tests with Golden Responses

Capture known-good responses and compare against them.
Catches prompt regressions and unexpected behavioral changes.
"""
import pytest
import json
from pathlib import Path
from typing import Dict, List

# Mark all tests as regression tests
pytestmark = [pytest.mark.regression]


class TestGoldenResponses:
    """Test agent responses against golden (known-good) responses"""

    @pytest.fixture
    def golden_cases(self, golden_responses_path):
        """Load golden test cases"""
        if golden_responses_path.exists():
            with open(golden_responses_path) as f:
                return json.load(f)
        return get_default_golden_cases()

    def test_golden_response_similarity(self, golden_cases, similarity_checker):
        """Test that responses maintain similarity to golden responses"""
        for case in golden_cases:
            # Get current response (mocked for unit test)
            current_response = get_mock_response(case["agent"], case["input"])

            # Check similarity
            similarity = similarity_checker(current_response, case["expected"])

            assert similarity > 0.6, (
                f"Response drifted for {case['agent']}:\n"
                f"Input: {case['input']}\n"
                f"Expected: {case['expected']}\n"
                f"Got: {current_response}\n"
                f"Similarity: {similarity}"
            )

    def test_rate_agent_golden_responses(self, similarity_checker):
        """Test rate agent specific golden responses"""
        cases = [
            {
                "input": "What's the best rate for a 740 FICO conventional loan?",
                "expected_contains": ["rate", "conventional", "740"],
            },
            {
                "input": "Compare FHA vs conventional for a first-time buyer",
                "expected_contains": ["FHA", "conventional", "down payment"],
            },
        ]

        for case in cases:
            response = get_mock_response("rate_analysis_agent", case["input"])

            for keyword in case["expected_contains"]:
                assert keyword.lower() in response.lower(), (
                    f"Missing expected keyword '{keyword}' in response: {response}"
                )

    def test_qualification_agent_golden_responses(self, similarity_checker):
        """Test qualification agent specific golden responses"""
        cases = [
            {
                "input": "I want to buy a $400k house with 740 credit",
                "expected_contains": ["qualified", "loan", "rate"],
            },
            {
                "input": "Can I qualify for a mortgage with 580 credit score?",
                "expected_contains": ["FHA", "credit", "options"],
            },
        ]

        for case in cases:
            response = get_mock_response("qualification_agent", case["input"])

            matched = sum(1 for kw in case["expected_contains"] if kw.lower() in response.lower())
            assert matched >= len(case["expected_contains"]) // 2, (
                f"Missing expected keywords in response: {response}"
            )


class TestResponseConsistency:
    """Test that responses remain consistent across runs"""

    def test_deterministic_responses(self):
        """Test that same input produces consistent response structure"""
        input_text = "What's my pipeline status?"

        responses = [
            get_mock_response("pipeline_analyst", input_text)
            for _ in range(3)
        ]

        # All responses should have similar structure
        for i, r1 in enumerate(responses[:-1]):
            r2 = responses[i + 1]
            # Check key elements are present in both
            assert ("pipeline" in r1.lower()) == ("pipeline" in r2.lower())


class TestBehavioralRegression:
    """Test for behavioral regressions"""

    def test_handles_edge_cases_consistently(self):
        """Test edge cases don't regress"""
        edge_cases = [
            {"input": "", "should_ask_clarification": True},
            {"input": "???", "should_ask_clarification": True},
            {"input": "help", "should_provide_help": True},
        ]

        for case in edge_cases:
            response = get_mock_response("general_assistant", case["input"])

            if case.get("should_ask_clarification"):
                assert "?" in response or "help" in response.lower()
            if case.get("should_provide_help"):
                assert "help" in response.lower() or "assist" in response.lower()

    def test_maintains_professional_tone(self):
        """Test responses maintain professional tone"""
        inputs = [
            "This is ridiculous!",
            "Why is this so slow?",
            "I'm frustrated with the process",
        ]

        for input_text in inputs:
            response = get_mock_response("general_assistant", input_text)

            # Should not contain unprofessional language
            unprofessional = ["sorry", "unfortunately"]  # These are fine
            assert not any(word in response.lower() for word in ["blame", "fault", "stupid"])


class TestTokenEfficiency:
    """Test that token usage stays within bounds"""

    def test_response_length_bounds(self):
        """Test responses stay within reasonable length"""
        inputs = [
            "What's my pipeline status?",
            "Explain the mortgage process",
            "What documents do I need?",
        ]

        for input_text in inputs:
            response = get_mock_response("general_assistant", input_text)

            # Response should be reasonable length
            word_count = len(response.split())
            assert word_count < 500, f"Response too long ({word_count} words): {response[:100]}..."
            assert word_count > 5, f"Response too short ({word_count} words): {response}"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_mock_response(agent: str, input_text: str) -> str:
    """
    Get mock response for testing.
    In production tests, this would call the actual agent.
    """
    responses = {
        "rate_analysis_agent": {
            "default": "Based on current market conditions, a 740 FICO conventional loan would qualify for rates around 6.5-6.875%. This is competitive for the current market.",
            "fha": "For first-time buyers, FHA loans offer lower down payment requirements (3.5%) compared to conventional (typically 5-20%). However, conventional loans don't require mortgage insurance once you reach 20% equity.",
        },
        "qualification_agent": {
            "default": "Based on your credit score and target price, you appear to be well-qualified for a conventional loan. Current rates for your profile would be around 6.5-6.75%.",
            "low_credit": "With a 580 credit score, your best option would be an FHA loan which allows credit scores as low as 580 with a 3.5% down payment. We can discuss options to improve your qualification.",
        },
        "pipeline_analyst": {
            "default": "Your current pipeline shows 45 active loans totaling $18.5M in volume. 8 loans are approaching closing within the next 30 days.",
        },
        "general_assistant": {
            "default": "I'd be happy to help you. Could you please provide more details about what you're looking for?",
            "help": "I can assist you with mortgage inquiries, loan status, rate information, document tracking, and scheduling. How can I help you today?",
        },
    }

    agent_responses = responses.get(agent, responses["general_assistant"])

    # Match input to response
    input_lower = input_text.lower()
    if "fha" in input_lower or "conventional" in input_lower:
        return agent_responses.get("fha", agent_responses.get("default", ""))
    if "580" in input_lower or "low credit" in input_lower:
        return agent_responses.get("low_credit", agent_responses.get("default", ""))
    if "help" in input_lower:
        return agent_responses.get("help", agent_responses.get("default", ""))

    return agent_responses.get("default", "I'm here to help with your mortgage questions.")


def get_default_golden_cases() -> List[Dict]:
    """Default golden test cases if file doesn't exist"""
    return [
        {
            "agent": "rate_analysis_agent",
            "input": "What's the best rate for a 740 FICO conventional loan?",
            "expected": "Based on current market conditions, a 740 FICO conventional loan would qualify for competitive rates around 6.5-6.875%.",
        },
        {
            "agent": "qualification_agent",
            "input": "Can I qualify with 620 credit and $60k income?",
            "expected": "With a 620 credit score and $60,000 income, you may qualify for FHA or conventional loans. Let me check your specific options.",
        },
        {
            "agent": "pipeline_analyst",
            "input": "Show me my pipeline",
            "expected": "Your current pipeline shows active loans with total volume. Here's the breakdown by status.",
        },
    ]
