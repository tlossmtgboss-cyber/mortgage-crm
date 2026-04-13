"""
Unit Tests for Aria Communication Tools

Tests send_sms, send_email, and schedule_call in isolation
with all external services mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def comm_tools():
    from aria.tools.communication_tools import CommunicationTools
    return CommunicationTools()


@pytest.fixture
def from_user():
    return {
        "id": 42,
        "email": "lo@example.com",
        "full_name": "Jane Doe",
        "organization_id": "org-100",
    }


# ===================================================================
# send_sms
# ===================================================================

class TestSendSms:

    @patch("aria.tools.communication_tools.SMSRetryService", create=True)
    async def test_calls_sms_retry_service_with_correct_params(
        self, _mock_cls, comm_tools, from_user,
    ):
        """send_sms() calls SMSRetryService.send_sms_with_retry with the right arguments."""
        mock_service = MagicMock()
        mock_service.send_sms_with_retry = AsyncMock(return_value={"message_id": "msg-1"})

        with patch(
            "services.sms_retry_service.SMSRetryService",
            return_value=mock_service,
        ):
            result = await comm_tools.send_sms(
                to_phone="+15551234567",
                from_user=from_user,
                message="Hello from Aria",
                org_id="org-100",
            )

        mock_service.send_sms_with_retry.assert_awaited_once()
        call_kwargs = mock_service.send_sms_with_retry.call_args
        assert call_kwargs.kwargs["to_phone"] == "+15551234567"
        assert call_kwargs.kwargs["message"] == "Hello from Aria"
        assert call_kwargs.kwargs["organization_id"] == "org-100"
        assert call_kwargs.kwargs["metadata"]["source"] == "aria"
        assert call_kwargs.kwargs["metadata"]["user_id"] == "42"

    @patch("aria.tools.communication_tools.SMSRetryService", create=True)
    async def test_returns_dict_with_sent_at_timestamp(
        self, _mock_cls, comm_tools, from_user,
    ):
        """send_sms() returns a dict containing sent_at ISO timestamp and status 'sent'."""
        mock_service = MagicMock()
        mock_service.send_sms_with_retry = AsyncMock(return_value={"message_id": "msg-2"})

        with patch(
            "services.sms_retry_service.SMSRetryService",
            return_value=mock_service,
        ):
            result = await comm_tools.send_sms(
                to_phone="+15559876543",
                from_user=from_user,
                message="Test",
                org_id="org-100",
            )

        assert "sent_at" in result
        # Verify the sent_at value is a valid ISO timestamp
        parsed = datetime.fromisoformat(result["sent_at"])
        assert parsed.tzinfo is not None
        assert result["status"] == "sent"
        assert result["message_id"] == "msg-2"

    async def test_handles_service_failure_gracefully(self, comm_tools, from_user):
        """send_sms() raises ValueError with descriptive message on service failure."""
        mock_service = MagicMock()
        mock_service.send_sms_with_retry = AsyncMock(
            side_effect=ConnectionError("Telnyx API unreachable")
        )

        with patch(
            "services.sms_retry_service.SMSRetryService",
            return_value=mock_service,
        ):
            with pytest.raises(ValueError, match="Failed to send SMS"):
                await comm_tools.send_sms(
                    to_phone="+15550000000",
                    from_user=from_user,
                    message="Will fail",
                    org_id="org-100",
                )


# ===================================================================
# send_email
# ===================================================================

class TestSendEmail:

    async def test_calls_email_delivery_service_with_correct_params(
        self, comm_tools, from_user,
    ):
        """send_email() passes all fields to EmailDeliveryService.send_email."""
        mock_result = MagicMock(
            message_id="email-abc", success=True, provider="sendgrid",
        )
        mock_service = MagicMock()
        mock_service.send_email = AsyncMock(return_value=mock_result)

        with patch(
            "services.email_delivery_service.EmailDeliveryService",
            return_value=mock_service,
        ):
            result = await comm_tools.send_email(
                to_email="borrower@example.com",
                to_name="John Smith",
                from_user=from_user,
                subject="Your Loan Update",
                body="Hello John, your loan is approved.",
                cc="processor@example.com",
            )

        mock_service.send_email.assert_awaited_once()
        call_kwargs = mock_service.send_email.call_args.kwargs
        assert call_kwargs["to"] == "borrower@example.com"
        assert call_kwargs["subject"] == "Your Loan Update"
        assert call_kwargs["text_body"] == "Hello John, your loan is approved."
        assert call_kwargs["from_email"] == "lo@example.com"
        assert call_kwargs["from_name"] == "Jane Doe"
        assert call_kwargs["cc"] == "processor@example.com"
        assert call_kwargs["user_id"] == "42"

    async def test_returns_dict_with_sent_at_and_message_id(
        self, comm_tools, from_user,
    ):
        """send_email() returns dict with sent_at, message_id, status, and provider."""
        mock_result = MagicMock(
            message_id="email-xyz", success=True, provider="msgraph",
        )
        mock_service = MagicMock()
        mock_service.send_email = AsyncMock(return_value=mock_result)

        with patch(
            "services.email_delivery_service.EmailDeliveryService",
            return_value=mock_service,
        ):
            result = await comm_tools.send_email(
                to_email="someone@example.com",
                to_name="Someone",
                from_user=from_user,
                subject="Test",
                body="Body text",
            )

        assert result["message_id"] == "email-xyz"
        assert result["status"] == "sent"
        assert result["provider"] == "msgraph"
        parsed = datetime.fromisoformat(result["sent_at"])
        assert parsed.tzinfo is not None

    async def test_handles_service_failure_gracefully(self, comm_tools, from_user):
        """send_email() raises ValueError with descriptive message on service failure."""
        mock_service = MagicMock()
        mock_service.send_email = AsyncMock(
            side_effect=RuntimeError("SMTP connection refused")
        )

        with patch(
            "services.email_delivery_service.EmailDeliveryService",
            return_value=mock_service,
        ):
            with pytest.raises(ValueError, match="Failed to send email"):
                await comm_tools.send_email(
                    to_email="nobody@example.com",
                    to_name="Nobody",
                    from_user=from_user,
                    subject="Fail",
                    body="This will fail",
                )


# ===================================================================
# schedule_call
# ===================================================================

class TestScheduleCall:

    async def test_creates_a_task_via_pipeline_tools(self, comm_tools):
        """schedule_call() delegates to PipelineTools.create_task to create a reminder."""
        mock_pipe = MagicMock()
        mock_pipe.create_task = AsyncMock(
            return_value={"id": 99, "created_at": "2026-04-13T10:00:00"}
        )

        with patch(
            "aria.tools.pipeline_tools.PipelineTools",
            return_value=mock_pipe,
        ):
            result = await comm_tools.schedule_call(
                with_contact={"id": 7, "name": "John Smith", "type": "borrower"},
                lo={"id": 42, "organization_id": "org-100"},
                date="2026-04-15",
                time="14:00",
                duration_minutes=30,
                topic="Pre-approval review",
            )

        mock_pipe.create_task.assert_awaited_once()
        call_kwargs = mock_pipe.create_task.call_args.kwargs
        assert "Call John Smith" in call_kwargs["description"]
        assert "Pre-approval review" in call_kwargs["description"]
        assert call_kwargs["due_date"] == "2026-04-15"
        assert call_kwargs["assigned_to"] == "42"
        assert call_kwargs["borrower_id"] == "7"

    async def test_returns_dict_indicating_no_calendar_integration(self, comm_tools):
        """schedule_call() returns calendar_link=None and a note about missing integration."""
        mock_pipe = MagicMock()
        mock_pipe.create_task = AsyncMock(
            return_value={"id": 55, "created_at": "2026-04-13T10:00:00"}
        )

        with patch(
            "aria.tools.pipeline_tools.PipelineTools",
            return_value=mock_pipe,
        ):
            result = await comm_tools.schedule_call(
                with_contact={"id": 3, "name": "Alice", "type": "lead"},
                lo={"id": 42, "organization_id": "org-100"},
                date="2026-04-20",
                time="09:30",
            )

        assert result["calendar_link"] is None
        assert "not yet integrated" in result["note"].lower()
        assert result["task_id"] == 55
        assert result["datetime"] == "2026-04-20 09:30"
        assert result["duration_minutes"] == 30
        assert result["with"] == "Alice"
