"""Tests for SchedulingConversationService — AI-driven SMS scheduling negotiation.

Covers: initiate_scheduling, handle_reply (all intent branches), _attempt_booking,
_classify_reply, _check_alternative, SMS consent blocking, max turns escalation,
and error handling for LLM/SMS/booking failures.

All external dependencies are mocked: database session, Anthropic LLM client,
Telnyx SMS (via NotificationService), and appointment creation service.
"""

import json
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins so tests don't need a running DB or imports
# ---------------------------------------------------------------------------

def _make_workflow(**overrides):
    """Build a mock VoiceWorkflow with sensible defaults."""
    wf = MagicMock()
    wf.id = overrides.get("id", 100)
    wf.organization_id = overrides.get("organization_id", 1)
    wf.user_id = overrides.get("user_id", 10)
    wf.contact_name = overrides.get("contact_name", "Jane Doe")
    wf.contact_phone = overrides.get("contact_phone", "+15551234567")
    wf.contact_email = overrides.get("contact_email", "jane@example.com")
    wf.lead_id = overrides.get("lead_id", 42)
    wf.meeting_type = overrides.get("meeting_type", "discovery_call")
    wf.meeting_duration_minutes = overrides.get("meeting_duration_minutes", 30)
    wf.state = overrides.get("state", "awaiting_reply")
    wf.turn_count = overrides.get("turn_count", 1)
    wf.max_turns = overrides.get("max_turns", 6)
    wf.conversation_history = overrides.get("conversation_history", [])
    wf.proposed_slots = overrides.get("proposed_slots", [
        {"start": "2026-03-26T10:00:00", "end": "2026-03-26T10:30:00", "formatted": "Thursday Mar 26 at 10:00 AM"},
        {"start": "2026-03-26T14:00:00", "end": "2026-03-26T14:30:00", "formatted": "Thursday Mar 26 at 2:00 PM"},
        {"start": "2026-03-27T09:00:00", "end": "2026-03-27T09:30:00", "formatted": "Friday Mar 27 at 9:00 AM"},
    ])
    wf.last_sms_sent_at = None
    wf.last_sms_received_at = None
    wf.confirmed_datetime = None
    wf.appointment_id = None
    wf.error_message = None

    # add_message should behave like the real model: append + increment turn_count
    _history = list(wf.conversation_history)
    _turn_count = [wf.turn_count]

    def _add_message(role, content):
        _history.append({"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()})
        wf.conversation_history = list(_history)
        if role == "contact":
            _turn_count[0] += 1
            wf.turn_count = _turn_count[0]

    wf.add_message = _add_message
    wf.is_active = Mock(return_value=overrides.get("is_active", True))
    return wf


@dataclass
class FakeAppointmentResult:
    success: bool = True
    appointment_id: Optional[int] = 999
    video_link: Optional[str] = "https://meet.example.com/abc"
    error: Optional[str] = None


# Fake available slots returned by _generate_available_slots
FAKE_SLOTS = [
    {"start": datetime(2026, 3, 26, 10, 0), "end": datetime(2026, 3, 26, 10, 30), "day_name": "Thursday"},
    {"start": datetime(2026, 3, 26, 14, 0), "end": datetime(2026, 3, 26, 14, 30), "day_name": "Thursday"},
    {"start": datetime(2026, 3, 27, 9, 0), "end": datetime(2026, 3, 27, 9, 30), "day_name": "Friday"},
    {"start": datetime(2026, 3, 27, 11, 0), "end": datetime(2026, 3, 27, 11, 30), "day_name": "Friday"},
    {"start": datetime(2026, 3, 28, 10, 0), "end": datetime(2026, 3, 28, 10, 30), "day_name": "Saturday"},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.query = MagicMock()
    return session


@pytest.fixture
def mock_wf_service():
    """Mock VoiceSchedulingWorkflowService."""
    svc = MagicMock()
    svc.advance_state = MagicMock()
    return svc


@pytest.fixture
def mock_workflow():
    """A ready-to-use mock workflow in awaiting_reply state."""
    return _make_workflow()


@pytest.fixture
def service(mock_db):
    """Create a SchedulingConversationService with patched internals."""
    from services.scheduling_conversation_service import SchedulingConversationService
    svc = SchedulingConversationService(db=mock_db)
    return svc


# ---------------------------------------------------------------------------
# 1. initiate_scheduling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInitiateScheduling:
    """Tests for the public initiate_scheduling() method."""

    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_success_creates_workflow_and_sends_sms(
        self, mock_slots, mock_name, mock_sms, service
    ):
        """initiate_scheduling should query slots, send SMS, update workflow, and return success."""
        mock_slots.return_value = FAKE_SLOTS
        mock_name.return_value = "Tim Loss"
        mock_sms.return_value = {"success": True}

        # Patch the workflow service import inside the method
        mock_wf_svc_instance = MagicMock()
        mock_wf = _make_workflow(state="initiated")
        mock_wf_svc_instance.get_workflow.return_value = mock_wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc_instance,
        ):
            result = service.initiate_scheduling(
                workflow_id=1,
                user_id=10,
                organization_id=1,
                contact_name="Jane Doe",
                contact_phone="+15551234567",
                meeting_type="discovery_call",
                duration_minutes=30,
                message_context="rate options",
            )

        assert result["success"] is True
        assert result["slots_offered"] == 5  # MAX_SLOTS_TO_SEND
        assert "message_sent" in result

        # SMS should contain the LO name and slots
        sent_message = mock_sms.call_args[0][1]
        assert "Tim Loss" in sent_message
        assert "rate options" in sent_message

        # Workflow state should advance to AWAITING_REPLY
        mock_wf_svc_instance.advance_state.assert_called_once()
        call_args = mock_wf_svc_instance.advance_state.call_args
        assert call_args[0][1] == "awaiting_reply"

    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_no_available_slots_returns_error(self, mock_slots, service):
        """Should return error when no slots are available."""
        mock_slots.return_value = []

        result = service.initiate_scheduling(
            workflow_id=1, user_id=10, organization_id=1,
            contact_name="Jane", contact_phone="+15551234567",
        )

        assert result["success"] is False
        assert "No available slots" in result["error"]

    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_sms_failure_returns_error(self, mock_slots, mock_name, mock_sms, service):
        """Should return error when SMS send fails."""
        mock_slots.return_value = FAKE_SLOTS
        mock_name.return_value = "Tim Loss"
        mock_sms.return_value = {"success": False, "error": "Invalid phone number"}

        result = service.initiate_scheduling(
            workflow_id=1, user_id=10, organization_id=1,
            contact_name="Jane", contact_phone="+1bad",
        )

        assert result["success"] is False
        assert "Invalid phone number" in result["error"]

    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_caps_slots_at_max(self, mock_slots, mock_name, mock_sms, service):
        """Should offer at most MAX_SLOTS_TO_SEND slots (5)."""
        many_slots = FAKE_SLOTS * 4  # 20 slots
        mock_slots.return_value = many_slots
        mock_name.return_value = "Tim"
        mock_sms.return_value = {"success": True}

        mock_wf_svc_instance = MagicMock()
        mock_wf_svc_instance.get_workflow.return_value = _make_workflow(state="initiated")

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc_instance,
        ):
            result = service.initiate_scheduling(
                workflow_id=1, user_id=10, organization_id=1,
                contact_name="Jane", contact_phone="+15551234567",
            )

        assert result["slots_offered"] == 5


# ---------------------------------------------------------------------------
# 2. handle_reply — intent routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestHandleReply:
    """Tests for handle_reply routing to correct handler per classified intent."""

    def _setup_handle_reply(self, service, workflow, classify_return):
        """Shared setup: patch wf_service + _classify_reply and call handle_reply."""
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = workflow
        mock_wf_svc.advance_state = MagicMock()

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_classify_reply", return_value=classify_return,
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ), patch.object(
            service, "_attempt_booking", return_value={"action": "booked", "appointment_id": 999},
        ) as mock_book, patch.object(
            service, "_check_alternative", return_value={"action": "confirming"},
        ) as mock_alt, patch.object(
            service, "_ask_clarification", return_value={"action": "clarification_requested"},
        ) as mock_clarify:
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="test")
            return result, mock_book, mock_alt, mock_clarify, mock_wf_svc

    def test_returns_none_for_inactive_workflow(self, service):
        """handle_reply should return None if workflow is inactive/not found."""
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = None

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ):
            result = service.handle_reply(workflow_id=999, sender_phone="+15551234567", message_body="hi")

        assert result is None

    def test_returns_none_for_completed_workflow(self, service):
        """handle_reply should return None for a workflow in terminal state."""
        wf = _make_workflow(is_active=False)
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ):
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="hi")

        assert result is None

    def test_confirm_time_with_datetime_calls_attempt_booking(self, service):
        """confirm_time intent with parsed_datetime should invoke _attempt_booking."""
        wf = _make_workflow()
        classify_result = {
            "intent": "confirm_time",
            "parsed_datetime": "2026-03-26T10:00:00",
            "confidence": 0.95,
        }
        result, mock_book, _, _, _ = self._setup_handle_reply(service, wf, classify_result)

        mock_book.assert_called_once()
        assert result["action"] == "booked"

    def test_confirm_time_without_datetime_asks_clarification(self, service):
        """confirm_time without parsed_datetime should ask for clarification."""
        wf = _make_workflow()
        classify_result = {"intent": "confirm_time", "parsed_datetime": None}
        result, mock_book, _, mock_clarify, _ = self._setup_handle_reply(service, wf, classify_result)

        mock_book.assert_not_called()
        mock_clarify.assert_called_once()

    def test_suggest_alternative_calls_check_alternative(self, service):
        """suggest_alternative intent should invoke _check_alternative."""
        wf = _make_workflow()
        classify_result = {
            "intent": "suggest_alternative",
            "suggested_datetime": "2026-03-27T15:00:00",
        }
        result, _, mock_alt, _, _ = self._setup_handle_reply(service, wf, classify_result)

        mock_alt.assert_called_once()
        assert result["action"] == "confirming"

    def test_decline_sends_message_and_cancels(self, service):
        """decline intent should send decline message and advance to CANCELLED."""
        wf = _make_workflow()
        classify_result = {
            "intent": "decline",
            "response_text": "No worries! Feel free to reach out anytime.",
        }

        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_classify_reply", return_value=classify_result,
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ) as mock_sms:
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="no thanks")

        assert result["action"] == "declined"
        mock_sms.assert_called_once()
        mock_wf_svc.advance_state.assert_called()
        # State should be cancelled
        state_arg = mock_wf_svc.advance_state.call_args[0][1]
        assert state_arg == "cancelled"

    def test_question_sends_response_and_stays_negotiating(self, service):
        """question intent should send AI response and advance to NEGOTIATING."""
        wf = _make_workflow()
        classify_result = {
            "intent": "question",
            "response_text": "The call will take about 30 minutes.",
        }

        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_classify_reply", return_value=classify_result,
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ):
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="how long?")

        assert result["action"] == "question_answered"
        assert result["response_sent"] == "The call will take about 30 minutes."
        state_arg = mock_wf_svc.advance_state.call_args[0][1]
        assert state_arg == "negotiating"

    def test_ambiguous_asks_clarification(self, service):
        """ambiguous intent should ask for clarification."""
        wf = _make_workflow()
        classify_result = {"intent": "ambiguous"}

        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_classify_reply", return_value=classify_result,
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ), patch.object(
            service, "_ask_clarification", return_value={"action": "clarification_requested"},
        ) as mock_clarify:
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="lol ok")

        assert result["action"] == "clarification_requested"
        mock_clarify.assert_called_once()

    def test_opt_out_cancels_workflow(self, service):
        """STOP keyword should cancel the workflow."""
        wf = _make_workflow()
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_handle_opt_out",
        ) as mock_opt_out:
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="STOP")

        assert result["action"] == "opted_out"
        mock_opt_out.assert_called_once_with(wf, "+15551234567")
        state_arg = mock_wf_svc.advance_state.call_args[0][1]
        assert state_arg == "cancelled"


# ---------------------------------------------------------------------------
# 3. _attempt_booking
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAttemptBooking:
    """Tests for _attempt_booking — booking appointment when contact confirms a time."""

    @patch("services.scheduling_conversation_service.SchedulingConversationService._notify_lo")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    def test_successful_booking(self, mock_name, mock_sms, mock_notify, service):
        """Successful booking should send confirmation SMS, update workflow, and notify LO."""
        mock_name.return_value = "Tim Loss"
        mock_sms.return_value = {"success": True}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        fake_result = FakeAppointmentResult(success=True, appointment_id=999, video_link="https://meet.example.com/abc")

        with patch(
            "services.scheduling_conversation_service.asyncio"
        ) as mock_asyncio:
            # Simulate no running loop -> asyncio.run path
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run.return_value = fake_result

            result = service._attempt_booking(wf, "2026-03-26T10:00:00", mock_wf_svc)

        assert result["action"] == "booked"
        assert result["appointment_id"] == 999
        assert result["video_link"] == "https://meet.example.com/abc"

        # Confirmation SMS should have been sent
        mock_sms.assert_called_once()
        sent_msg = mock_sms.call_args[0][1]
        assert "confirmed" in sent_msg.lower()
        assert "Tim Loss" in sent_msg

        # Workflow state advanced to appointment_booked
        mock_wf_svc.advance_state.assert_called_once()
        state_arg = mock_wf_svc.advance_state.call_args[0][1]
        assert state_arg == "appointment_booked"

        # LO notified
        mock_notify.assert_called_once()

    @patch("services.scheduling_conversation_service.SchedulingConversationService._offer_alternatives")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    def test_booking_failure_offers_alternatives(self, mock_name, mock_sms, mock_offer, service):
        """When create_appointment fails, should offer alternative slots."""
        mock_name.return_value = "Tim Loss"
        mock_offer.return_value = {"action": "alternatives_offered", "slots": 3}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        failed_result = FakeAppointmentResult(success=False, appointment_id=None, error="Time slot conflict")

        with patch(
            "services.scheduling_conversation_service.asyncio"
        ) as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run.return_value = failed_result

            result = service._attempt_booking(wf, "2026-03-26T10:00:00", mock_wf_svc)

        mock_offer.assert_called_once()
        assert result["action"] == "alternatives_offered"

    def test_booking_exception_returns_error(self, service):
        """Exception during booking should return error dict gracefully."""
        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        with patch(
            "services.scheduling_conversation_service.asyncio"
        ) as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run.side_effect = Exception("Database connection lost")

            result = service._attempt_booking(wf, "2026-03-26T10:00:00", mock_wf_svc)

        assert result["action"] == "error"
        assert "Database connection lost" in result["error"]

    @patch("services.scheduling_conversation_service.SchedulingConversationService._offer_alternatives")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    def test_booking_returns_none_offers_alternatives(self, mock_name, mock_sms, mock_offer, service):
        """When create_appointment returns None (async bridge issue), should offer alternatives."""
        mock_name.return_value = "Tim Loss"
        mock_offer.return_value = {"action": "alternatives_offered", "slots": 3}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        with patch(
            "services.scheduling_conversation_service.asyncio"
        ) as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            mock_asyncio.run.return_value = None

            result = service._attempt_booking(wf, "2026-03-26T10:00:00", mock_wf_svc)

        mock_offer.assert_called_once()
        assert result["action"] == "alternatives_offered"


# ---------------------------------------------------------------------------
# 4. _classify_reply — LLM-based intent classification
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClassifyReply:
    """Tests for _classify_reply — mock the Anthropic client call."""

    def test_returns_parsed_json_from_llm(self, service):
        """Should return structured intent when LLM responds with valid JSON."""
        wf = _make_workflow()
        llm_response_text = json.dumps({
            "intent": "confirm_time",
            "parsed_datetime": "2026-03-26T10:00:00",
            "suggested_datetime": None,
            "response_text": None,
            "confidence": 0.95,
        })

        mock_content = MagicMock()
        mock_content.text = llm_response_text
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim Loss",
        ):
            result = service._classify_reply(wf, "Option 1 works for me")

        assert result["intent"] == "confirm_time"
        assert result["parsed_datetime"] == "2026-03-26T10:00:00"
        assert result["confidence"] == 0.95

    def test_extracts_json_from_surrounding_text(self, service):
        """Should extract JSON even if LLM wraps it in extra text."""
        wf = _make_workflow()
        llm_response_text = 'Here is my classification:\n{"intent": "decline", "response_text": "No worries!", "confidence": 0.9}\nDone.'

        mock_content = MagicMock()
        mock_content.text = llm_response_text
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ):
            result = service._classify_reply(wf, "nah I'm good")

        assert result["intent"] == "decline"

    def test_returns_ambiguous_when_no_client(self, service):
        """Should return ambiguous if Anthropic client is unavailable."""
        wf = _make_workflow()

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=None,
        ):
            result = service._classify_reply(wf, "some reply")

        assert result["intent"] == "ambiguous"

    def test_returns_ambiguous_on_llm_exception(self, service):
        """Should return ambiguous if the LLM call throws an exception."""
        wf = _make_workflow()

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API rate limit exceeded")

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ):
            result = service._classify_reply(wf, "yes")

        assert result["intent"] == "ambiguous"

    def test_returns_ambiguous_on_invalid_json(self, service):
        """Should return ambiguous if LLM returns non-JSON text."""
        wf = _make_workflow()

        mock_content = MagicMock()
        mock_content.text = "I think they want to confirm but I'm not sure."
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ):
            result = service._classify_reply(wf, "maybe")

        assert result["intent"] == "ambiguous"

    def test_includes_proposed_slots_in_system_prompt(self, service):
        """Should pass the workflow's proposed slots into the LLM system prompt."""
        wf = _make_workflow()

        mock_content = MagicMock()
        mock_content.text = '{"intent": "ambiguous"}'
        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ):
            service._classify_reply(wf, "option 1")

        # Verify that the system prompt contains slot info
        call_kwargs = mock_client.messages.create.call_args
        system_prompt = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert "Thursday Mar 26 at 10:00 AM" in system_prompt


# ---------------------------------------------------------------------------
# 5. _check_alternative — validate suggested time against availability
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckAlternative:
    """Tests for _check_alternative — validates contact-suggested time."""

    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_available_time_sends_confirmation_prompt(self, mock_slots, mock_name, mock_sms, service):
        """When suggested time matches an available slot, should ask for final confirmation."""
        mock_slots.return_value = FAKE_SLOTS
        mock_name.return_value = "Tim Loss"
        mock_sms.return_value = {"success": True}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        # Suggest a time within 30 min of an existing slot
        result = service._check_alternative(wf, "2026-03-26T10:15:00", mock_wf_svc)

        assert result["action"] == "confirming"
        mock_sms.assert_called_once()
        sent_msg = mock_sms.call_args[0][1]
        assert "works" in sent_msg.lower()
        # State should advance to negotiating
        mock_wf_svc.advance_state.assert_called_once()

    @patch("services.scheduling_conversation_service.SchedulingConversationService._offer_alternatives")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_unavailable_time_offers_alternatives(self, mock_slots, mock_offer, service):
        """When suggested time is not available, should offer alternative slots."""
        mock_slots.return_value = FAKE_SLOTS
        mock_offer.return_value = {"action": "alternatives_offered", "slots": 3}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        # Suggest a time that doesn't match any slot (different day entirely)
        result = service._check_alternative(wf, "2026-04-01T08:00:00", mock_wf_svc)

        mock_offer.assert_called_once()
        assert result["action"] == "alternatives_offered"

    @patch("services.scheduling_conversation_service.SchedulingConversationService._ask_clarification")
    def test_no_suggested_datetime_asks_clarification(self, mock_clarify, service):
        """When suggested_datetime is None, should ask for clarification."""
        mock_clarify.return_value = {"action": "clarification_requested"}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        result = service._check_alternative(wf, None, mock_wf_svc)

        mock_clarify.assert_called_once()
        assert result["action"] == "clarification_requested"

    @patch("services.scheduling_conversation_service.SchedulingConversationService._ask_clarification")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_available_slots")
    def test_exception_falls_back_to_clarification(self, mock_slots, mock_clarify, service):
        """On exception during alternative check, should ask for clarification."""
        mock_slots.side_effect = Exception("DB timeout")
        mock_clarify.return_value = {"action": "clarification_requested"}

        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        result = service._check_alternative(wf, "2026-03-26T10:00:00", mock_wf_svc)

        mock_clarify.assert_called_once()


# ---------------------------------------------------------------------------
# 6. SMS consent check — blocks SMS if no consent
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSmsConsentCheck:
    """Tests for _send_sms — SMS consent enforcement."""

    def test_blocked_by_consent_check(self, service):
        """SMS should be blocked when consent check returns False."""
        with patch(
            "services.scheduling_conversation_service.check_sms_consent",
            return_value=(False, "No SMS consent on file"),
        ):
            result = service._send_sms("+15551234567", "Hello", org_id=1)

        assert result["success"] is False
        assert "Compliance blocked" in result["error"]
        assert "consent" in result["error"].lower()

    def test_allowed_by_consent_sends_sms(self, service):
        """SMS should be sent when consent check passes."""
        mock_ns = MagicMock()
        mock_ns.send_sms.return_value = {"success": True, "message_id": "abc123"}

        with patch(
            "services.scheduling_conversation_service.check_sms_consent",
            return_value=(True, ""),
        ), patch(
            "services.scheduling_conversation_service.NotificationService",
            return_value=mock_ns,
        ):
            result = service._send_sms("+15551234567", "Hello", org_id=1)

        assert result["success"] is True
        mock_ns.send_sms.assert_called_once_with(
            to_phone="+15551234567",
            message="Hello",
            organization_id=1,
        )

    def test_exception_in_send_returns_error(self, service):
        """Exception during SMS send should return error gracefully."""
        with patch(
            "services.scheduling_conversation_service.check_sms_consent",
            side_effect=ImportError("sms_compliance module not found"),
        ):
            result = service._send_sms("+15551234567", "Hello", org_id=1)

        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# 7. Max turns escalation — creates Task when conversation exceeds max turns
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMaxTurnsEscalation:
    """Tests for max turn limit enforcement and Task creation."""

    def test_max_turns_triggers_escalation(self, service):
        """When turn_count >= max_turns, should escalate and expire."""
        wf = _make_workflow(turn_count=6, max_turns=6)
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_send_escalation",
        ) as mock_esc:
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="hello again")

        assert result["action"] == "expired"
        assert result["reason"] == "max_turns"
        mock_esc.assert_called_once_with(wf)
        # State should advance to expired
        mock_wf_svc.advance_state.assert_called_once()
        state_arg = mock_wf_svc.advance_state.call_args[0][1]
        assert state_arg == "expired"

    @patch("services.scheduling_conversation_service.SchedulingConversationService._send_sms")
    @patch("services.scheduling_conversation_service.SchedulingConversationService._get_user_name")
    def test_send_escalation_sends_sms_and_notifies_lo(self, mock_name, mock_sms, service):
        """_send_escalation should send message to contact and call _notify_lo with escalation=True."""
        mock_name.return_value = "Tim Loss"
        mock_sms.return_value = {"success": True}

        wf = _make_workflow()

        with patch.object(service, "_notify_lo") as mock_notify:
            service._send_escalation(wf)

        mock_sms.assert_called_once()
        sent_msg = mock_sms.call_args[0][1]
        assert "Tim Loss" in sent_msg
        assert "reach out" in sent_msg.lower()

        mock_notify.assert_called_once_with(wf, None, escalation=True)

    def test_create_followup_task(self, mock_db, service):
        """_create_followup_task should add a Task to the session."""
        wf = _make_workflow(turn_count=6)

        # Patch the Task model import inside _create_followup_task
        mock_task_class = MagicMock()

        with patch(
            "services.scheduling_conversation_service.Task",
            mock_task_class,
            create=True,
        ):
            # Since the import is inside the method, we need to patch at the import site
            with patch.dict("sys.modules", {"database.models.task": MagicMock(Task=mock_task_class)}):
                service._create_followup_task(wf)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_notify_lo_escalation_creates_task(self, service):
        """_notify_lo with escalation=True should call _create_followup_task."""
        wf = _make_workflow()

        with patch.object(service, "_create_followup_task") as mock_create:
            service._notify_lo(wf, confirmed_dt=None, escalation=True)

        mock_create.assert_called_once_with(wf)

    def test_notify_lo_normal_booking_does_not_create_task(self, service):
        """_notify_lo without escalation should NOT create a follow-up task."""
        wf = _make_workflow()

        with patch.object(service, "_create_followup_task") as mock_create:
            service._notify_lo(wf, confirmed_dt=datetime(2026, 3, 26, 10, 0), escalation=False)

        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Error handling — graceful failure for LLM, SMS, booking failures
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorHandling:
    """Tests for graceful error handling in various failure scenarios."""

    def test_classify_reply_llm_api_error_returns_ambiguous(self, service):
        """LLM API error should not crash; returns ambiguous intent."""
        wf = _make_workflow()

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("API unreachable")

        with patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ):
            result = service._classify_reply(wf, "yes please")

        assert result == {"intent": "ambiguous"}

    def test_initiate_scheduling_slots_exception_returns_empty(self, service):
        """Exception in _get_available_slots should result in no slots and error."""
        with patch.object(
            service, "_get_available_slots", return_value=[],
        ):
            result = service.initiate_scheduling(
                workflow_id=1, user_id=10, organization_id=1,
                contact_name="Jane", contact_phone="+15551234567",
            )

        assert result["success"] is False
        assert "No available slots" in result["error"]

    def test_attempt_booking_with_invalid_datetime_string(self, service):
        """Invalid datetime string in _attempt_booking should return error."""
        wf = _make_workflow()
        mock_wf_svc = MagicMock()

        result = service._attempt_booking(wf, "not-a-date", mock_wf_svc)

        assert result["action"] == "error"
        assert "error" in result

    def test_send_sms_notification_service_exception(self, service):
        """Exception from NotificationService.send_sms should be caught."""
        mock_ns = MagicMock()
        mock_ns.send_sms.side_effect = Exception("Telnyx API timeout")

        with patch(
            "services.scheduling_conversation_service.check_sms_consent",
            return_value=(True, ""),
        ), patch(
            "services.scheduling_conversation_service.NotificationService",
            return_value=mock_ns,
        ):
            result = service._send_sms("+15551234567", "Hello", org_id=1)

        assert result["success"] is False
        assert "Telnyx API timeout" in result["error"]

    def test_handle_reply_full_flow_with_llm_failure(self, service):
        """When LLM fails during handle_reply, should fall back to clarification."""
        wf = _make_workflow()
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("LLM down")

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch(
            "services.scheduling_conversation_service._get_anthropic",
            return_value=mock_client,
        ), patch.object(
            service, "_get_user_name", return_value="Tim",
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ):
            result = service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="option 1")

        # Should end up in clarification since _classify_reply returns ambiguous
        assert result["action"] == "clarification_requested"

    def test_create_followup_task_exception_is_swallowed(self, service):
        """Exception during task creation should be caught, not propagated."""
        wf = _make_workflow()

        with patch.dict("sys.modules", {"database.models.task": MagicMock(side_effect=ImportError("no module"))}):
            # Should not raise
            service._create_followup_task(wf)

    def test_get_user_name_db_error_returns_fallback(self, mock_db, service):
        """_get_user_name should return fallback string on DB error."""
        mock_db.query.side_effect = Exception("DB connection lost")

        with patch.dict("sys.modules", {"database.models.core": MagicMock()}):
            name = service._get_user_name(user_id=999)

        assert name == "your loan officer"


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_is_opt_out_various_keywords(self, service):
        """_is_opt_out should recognize all opt-out keywords."""
        for keyword in ["STOP", "stop", "Unsubscribe", "opt out", "OPTOUT", "cancel", "quit", "QUIT"]:
            assert service._is_opt_out(keyword) is True

    def test_is_opt_out_rejects_normal_messages(self, service):
        """_is_opt_out should NOT match regular messages."""
        for msg in ["yes", "option 1", "stop by later", "I want to cancel my other meeting", "nope", ""]:
            # "stop by later" is not exactly "stop" so should be False
            # "I want to cancel my other meeting" is not exactly "cancel"
            # However, empty string is not in the opt-out set either
            if msg.strip().lower() in {"stop", "unsubscribe", "opt out", "optout", "cancel", "quit"}:
                assert service._is_opt_out(msg) is True
            else:
                assert service._is_opt_out(msg) is False

    def test_format_slots_for_sms_with_datetime_objects(self, service):
        """_format_slots_for_sms should handle datetime objects."""
        slots = [
            {"start": datetime(2026, 3, 26, 10, 0), "end": datetime(2026, 3, 26, 10, 30)},
            {"start": datetime(2026, 3, 27, 14, 0), "end": datetime(2026, 3, 27, 14, 30)},
        ]
        text = service._format_slots_for_sms(slots)

        assert "1." in text
        assert "2." in text
        assert "Thursday" in text or "Mar" in text  # Date formatting present

    def test_format_slots_for_sms_with_string_datetimes(self, service):
        """_format_slots_for_sms should handle ISO string datetimes."""
        slots = [
            {"start": "2026-03-26T10:00:00", "end": "2026-03-26T10:30:00"},
        ]
        text = service._format_slots_for_sms(slots)

        assert "1." in text
        assert "Mar" in text

    def test_format_slots_for_sms_with_unparseable_start(self, service):
        """_format_slots_for_sms should handle slots with non-datetime start values."""
        slots = [
            {"start": "Morning", "day_name": "Thursday"},
        ]
        text = service._format_slots_for_sms(slots)

        assert "1." in text
        assert "Thursday" in text

    def test_handle_reply_records_inbound_message(self, service):
        """handle_reply should record the inbound message on the workflow before classifying."""
        wf = _make_workflow()
        original_history_len = len(wf.conversation_history)
        mock_wf_svc = MagicMock()
        mock_wf_svc.get_workflow.return_value = wf

        with patch(
            "services.scheduling_conversation_service.VoiceSchedulingWorkflowService",
            return_value=mock_wf_svc,
        ), patch.object(
            service, "_classify_reply", return_value={"intent": "ambiguous"},
        ), patch.object(
            service, "_send_sms", return_value={"success": True},
        ):
            service.handle_reply(workflow_id=100, sender_phone="+15551234567", message_body="hello there")

        # The contact message should be in the conversation history
        assert len(wf.conversation_history) > original_history_len
        last_contact_msg = [m for m in wf.conversation_history if m["role"] == "contact"]
        assert len(last_contact_msg) >= 1
        assert last_contact_msg[-1]["content"] == "hello there"
