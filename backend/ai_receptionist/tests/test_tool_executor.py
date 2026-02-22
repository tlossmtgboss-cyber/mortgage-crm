"""
================================================================================
PERENNIA AI - TOOL EXECUTOR TESTS
================================================================================
Tests for receptionist tool execution and CRM integration.

Run with: pytest backend/ai_receptionist/tests/test_tool_executor.py -v
================================================================================
"""

import pytest
import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ai_receptionist.tool_executor import (
    ToolExecutionResult,
    ReceptionistToolExecutor,
    AIReceptionist,
    ReceptionistTester,
    create_receptionist,
    create_tool_executor,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_tool_registry():
    """Create mock tool registry."""
    registry = Mock()

    # Mock get_customer_360 tool
    customer_360_result = Mock()
    customer_360_result.status = "success"
    customer_360_result.data = {
        "contact_id": "123",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "is_customer": True,
        "active_loans": ["LOAN-001"],
        "assigned_lo_id": "LO-001",
        "assigned_lo_name": "Jane Smith",
    }

    customer_360_tool = Mock(return_value=customer_360_result)
    registry.get = Mock(side_effect=lambda name: {
        "get_customer_360": customer_360_tool,
    }.get(name))

    return registry


@pytest.fixture
def tool_executor(mock_tool_registry):
    """Create tool executor with mock registry."""
    return ReceptionistToolExecutor(tool_registry=mock_tool_registry)


@pytest.fixture
def tool_executor_no_registry():
    """Create tool executor without registry (fallback mode)."""
    return ReceptionistToolExecutor(tool_registry=None)


# =============================================================================
# TOOL EXECUTION RESULT TESTS
# =============================================================================

class TestToolExecutionResult:
    """Tests for ToolExecutionResult class."""

    def test_ok_result(self):
        """Test creating successful result."""
        result = ToolExecutionResult.ok(
            data={"key": "value"},
            message="Success",
        )

        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.message == "Success"
        assert result.error is None

    def test_fail_result(self):
        """Test creating failed result."""
        result = ToolExecutionResult.fail(
            error="Something went wrong",
            message="Operation failed",
        )

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.message == "Operation failed"

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = ToolExecutionResult.ok({"test": 123})

        data = result.to_dict()

        assert "success" in data
        assert "data" in data
        assert data["data"] == {"test": 123}


# =============================================================================
# TOOL EXECUTOR TESTS
# =============================================================================

class TestReceptionistToolExecutor:
    """Tests for ReceptionistToolExecutor class."""

    @pytest.mark.asyncio
    async def test_execute_lookup_caller_with_registry(self, tool_executor):
        """Test caller lookup with registry."""
        result = await tool_executor.execute(
            "lookup_caller",
            phone_number="+15551234567",
        )

        assert result.success is True
        assert result.data.get("found") is True
        assert result.data.get("first_name") == "John"

    @pytest.mark.asyncio
    async def test_execute_lookup_caller_not_found(self, tool_executor_no_registry):
        """Test caller lookup when not found."""
        result = await tool_executor.execute(
            "lookup_caller",
            phone_number="+15559999999",
        )

        assert result.success is True
        assert result.data.get("found") is False

    @pytest.mark.asyncio
    async def test_execute_get_lo_availability(self, tool_executor_no_registry):
        """Test LO availability lookup."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        result = await tool_executor.execute(
            "get_lo_availability",
            lo_id="LO-001",
            date=tomorrow,
        )

        assert result.success is True
        assert "available_slots" in result.data
        assert isinstance(result.data["available_slots"], list)

    @pytest.mark.asyncio
    async def test_execute_book_appointment(self, tool_executor_no_registry):
        """Test appointment booking."""
        result = await tool_executor.execute(
            "book_appointment",
            lo_id="LO-001",
            caller_name="John Doe",
            caller_phone="+15551234567",
            datetime_str="2025-01-15T10:00:00",
            purpose="Consultation",
        )

        assert result.success is True
        assert "appointment_id" in result.data
        assert "confirmation" in result.data

    @pytest.mark.asyncio
    async def test_execute_create_callback_request(self, tool_executor_no_registry):
        """Test callback request creation."""
        result = await tool_executor.execute(
            "create_callback_request",
            caller_name="John Doe",
            caller_phone="+15551234567",
            reason="Rate inquiry",
            urgency="high",
        )

        assert result.success is True
        assert "callback_id" in result.data
        assert "as soon as possible" in result.data.get("message", "")

    @pytest.mark.asyncio
    async def test_execute_get_loan_status(self, tool_executor_no_registry):
        """Test loan status lookup."""
        result = await tool_executor.execute(
            "get_loan_status",
            loan_number="123456",
            borrower_last_name="Doe",
        )

        assert result.success is True
        assert "status" in result.data
        assert "status_display" in result.data

    @pytest.mark.asyncio
    async def test_execute_transfer_call(self, tool_executor_no_registry):
        """Test call transfer setup."""
        result = await tool_executor.execute(
            "transfer_call",
            target_id="LO-001",
            transfer_type="warm",
            context="Rate inquiry",
        )

        assert result.success is True
        assert result.data.get("target_id") == "LO-001"
        assert result.data.get("transfer_type") == "warm"

    @pytest.mark.asyncio
    async def test_execute_leave_message(self, tool_executor_no_registry):
        """Test leaving a message."""
        result = await tool_executor.execute(
            "leave_message",
            lo_id="LO-001",
            caller_name="John Doe",
            message="Please call me back about refinancing",
            caller_phone="+15551234567",
            urgent=True,
        )

        assert result.success is True
        assert "message_id" in result.data
        assert "confirmation" in result.data

    @pytest.mark.asyncio
    async def test_execute_get_current_rates(self, tool_executor_no_registry):
        """Test rate information."""
        result = await tool_executor.execute(
            "get_current_rates",
            loan_type="conventional",
        )

        assert result.success is True
        # Should not return specific rates without registry
        assert "message" in result.data or "rates" in result.data

    @pytest.mark.asyncio
    async def test_execute_find_available_lo(self, tool_executor_no_registry):
        """Test finding available LO."""
        result = await tool_executor.execute(
            "find_available_lo",
            specialty="VA",
        )

        assert result.success is True
        assert "lo_name" in result.data

    @pytest.mark.asyncio
    async def test_execute_qualify_lead(self, tool_executor_no_registry):
        """Test lead qualification."""
        result = await tool_executor.execute(
            "qualify_lead",
            caller_phone="+15551234567",
            purpose="purchase",
        )

        assert result.success is True
        assert "priority" in result.data
        assert result.data.get("priority") == "high"  # Purchase is high priority

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, tool_executor_no_registry):
        """Test executing unknown tool."""
        result = await tool_executor.execute("unknown_tool_name")

        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_get_available_tools(self, tool_executor):
        """Test getting tool definitions."""
        tools = tool_executor.get_available_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check tool structure
        tool = tools[0]
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool

    @pytest.mark.asyncio
    async def test_get_metrics(self, tool_executor_no_registry):
        """Test metrics tracking."""
        # Execute some tools
        await tool_executor_no_registry.execute(
            "lookup_caller",
            phone_number="+15551234567",
        )
        await tool_executor_no_registry.execute(
            "get_current_rates",
        )

        metrics = tool_executor_no_registry.get_metrics()

        assert metrics["total_executions"] == 2
        assert metrics["total_time_ms"] > 0
        assert metrics["avg_time_ms"] > 0


# =============================================================================
# AI RECEPTIONIST TESTS
# =============================================================================

class TestAIReceptionist:
    """Tests for AIReceptionist class."""

    @pytest.mark.asyncio
    async def test_create_receptionist(self):
        """Test receptionist creation."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = AIReceptionist.create(
                    company_name="Test Mortgage",
                    receptionist_name="TestBot",
                )

                assert receptionist is not None
                assert receptionist.config["company_name"] == "Test Mortgage"
                assert receptionist.config["receptionist_name"] == "TestBot"

    @pytest.mark.asyncio
    async def test_handle_incoming_call_new_caller(self):
        """Test handling call from new caller."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = AIReceptionist.create()

                greeting = await receptionist.handle_incoming_call(
                    call_sid="CA123",
                    from_number="+15551234567",
                )

                assert "Sarah" in greeting
                assert "Perennia" in greeting
                assert "help" in greeting.lower()

    @pytest.mark.asyncio
    async def test_process_speech_appointment(self):
        """Test processing appointment request."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = AIReceptionist.create()

                await receptionist.handle_incoming_call(
                    call_sid="CA123",
                    from_number="+15551234567",
                )

                response = await receptionist.process_speech(
                    call_sid="CA123",
                    speech_text="I'd like to schedule an appointment",
                )

                assert "appointment" in response.lower()

    @pytest.mark.asyncio
    async def test_process_speech_rates(self):
        """Test processing rate inquiry."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = AIReceptionist.create()

                await receptionist.handle_incoming_call(
                    call_sid="CA123",
                    from_number="+15551234567",
                )

                response = await receptionist.process_speech(
                    call_sid="CA123",
                    speech_text="What are your current rates?",
                )

                assert "rate" in response.lower()

    @pytest.mark.asyncio
    async def test_end_call(self):
        """Test ending a call."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = AIReceptionist.create()

                await receptionist.handle_incoming_call(
                    call_sid="CA123",
                    from_number="+15551234567",
                )

                summary = await receptionist.end_call("CA123")

                assert "call_sid" in summary
                assert "duration_seconds" in summary
                assert summary["call_sid"] == "CA123"


# =============================================================================
# RECEPTIONIST TESTER TESTS
# =============================================================================

class TestReceptionistTester:
    """Tests for ReceptionistTester class."""

    @pytest.mark.asyncio
    async def test_simulate_call(self):
        """Test call simulation."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                tester = ReceptionistTester()

                greeting = await tester.simulate_call("+15551234567")

                assert isinstance(greeting, str)
                assert len(greeting) > 0

    @pytest.mark.asyncio
    async def test_say(self):
        """Test saying something."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                tester = ReceptionistTester()
                await tester.simulate_call()

                response = await tester.say("Hello")

                assert isinstance(response, str)
                assert len(response) > 0

    @pytest.mark.asyncio
    async def test_run_scenario(self):
        """Test running a scenario."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                tester = ReceptionistTester()

                summary = await tester.run_scenario([
                    "I need an appointment",
                    "Tomorrow works",
                    "Thank you",
                ])

                assert "duration_seconds" in summary
                assert len(summary.get("messages", [])) >= 3


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_receptionist_function(self):
        """Test create_receptionist factory."""
        with patch('ai_receptionist.tool_executor.AudioProcessor'):
            with patch('ai_receptionist.tool_executor.TelnyxStreamHandler'):
                receptionist = create_receptionist(
                    company_name="Test Co",
                    receptionist_name="Bot",
                )

                assert receptionist is not None
                assert receptionist.config["company_name"] == "Test Co"

    def test_create_tool_executor_function(self):
        """Test create_tool_executor factory."""
        executor = create_tool_executor()

        assert executor is not None
        assert isinstance(executor, ReceptionistToolExecutor)


# =============================================================================
# LOAN STATUS FORMATTING TESTS
# =============================================================================

class TestLoanStatusFormatting:
    """Tests for loan status formatting."""

    def test_format_loan_status(self):
        """Test various loan status formats."""
        executor = ReceptionistToolExecutor()

        statuses = {
            "application": "received",
            "processing": "processed",
            "underwriting": "underwriting",
            "approved": "approved",
            "funded": "funded",
        }

        for status, expected_word in statuses.items():
            formatted = executor._format_loan_status(status)
            assert expected_word in formatted.lower()

    def test_format_unknown_status(self):
        """Test formatting unknown status."""
        executor = ReceptionistToolExecutor()

        formatted = executor._format_loan_status("unknown_status")

        assert "unknown_status" in formatted


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_execute_with_exception(self):
        """Test tool execution when exception occurs."""
        registry = Mock()
        registry.get = Mock(side_effect=Exception("Database error"))

        executor = ReceptionistToolExecutor(tool_registry=registry)

        result = await executor.execute("lookup_caller", phone_number="+15551234567")

        # Should fall back gracefully
        assert result.success is True
        assert result.data.get("found") is False

    @pytest.mark.asyncio
    async def test_availability_weekend_skip(self):
        """Test that availability skips weekends."""
        executor = ReceptionistToolExecutor()

        # Get a Saturday
        from datetime import date
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        saturday = today + timedelta(days=days_until_saturday)

        result = await executor.execute(
            "get_lo_availability",
            date=saturday.strftime("%Y-%m-%d"),
        )

        # Should return Monday slots, not Saturday
        assert result.success is True
        returned_date = result.data.get("date")
        if returned_date:
            returned = datetime.strptime(returned_date, "%Y-%m-%d")
            assert returned.weekday() < 5  # Not a weekend

    @pytest.mark.asyncio
    async def test_callback_urgency_levels(self):
        """Test different urgency levels for callbacks."""
        executor = ReceptionistToolExecutor()

        # High urgency
        high = await executor.execute(
            "create_callback_request",
            caller_name="Test",
            caller_phone="+15551234567",
            urgency="urgent",
        )
        assert "as soon as possible" in high.data.get("message", "")

        # Normal urgency
        normal = await executor.execute(
            "create_callback_request",
            caller_name="Test",
            caller_phone="+15551234567",
            urgency="normal",
        )
        assert "24 hours" in normal.data.get("message", "")


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
