"""
Tests for aria/tasks/task_executor.py

Verifies intent routing, handler logic, error handling, and
correct interaction with tool dependencies (CRM, Comms, Pipeline, etc.).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tools():
    """Patch all five tool classes so TaskExecutor.__init__ gets mocks."""
    with (
        patch("aria.tasks.task_executor.CRMTools") as MockCRM,
        patch("aria.tasks.task_executor.CommunicationTools") as MockComms,
        patch("aria.tasks.task_executor.PipelineTools") as MockPipe,
        patch("aria.tasks.task_executor.KnowledgeTools") as MockKnow,
        patch("aria.tasks.task_executor.DocumentGenerator") as MockDocs,
    ):
        MockCRM.return_value = MagicMock()
        MockComms.return_value = MagicMock()
        MockPipe.return_value = MagicMock()
        MockKnow.return_value = MagicMock()
        MockDocs.return_value = MagicMock()

        yield {
            "CRM": MockCRM,
            "Comms": MockComms,
            "Pipe": MockPipe,
            "Know": MockKnow,
            "Docs": MockDocs,
        }


@pytest.fixture
def executor(mock_tools):
    """Return a TaskExecutor whose tool instances are all mocks."""
    from aria.tasks.task_executor import TaskExecutor

    te = TaskExecutor()
    # All instance attributes (te.crm, te.comms, ...) are already mocks
    # because the class constructors were patched above.
    return te


USER_ID = "user-001"
ORG_ID = "org-001"


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------

class TestTaskExecutorInit:
    EXPECTED_HANDLERS = [
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

    def test_all_handlers_registered(self, executor):
        """TaskExecutor should register all 15 intent handlers."""
        registered = set(executor._handlers.keys())
        assert registered == set(self.EXPECTED_HANDLERS)
        assert len(registered) == 15


# ---------------------------------------------------------------------------
# 2. execute() routing
# ---------------------------------------------------------------------------

class TestExecuteRouting:
    @pytest.mark.asyncio
    async def test_routes_to_correct_handler(self, executor):
        """execute() should call the handler matching the intent name."""
        sentinel = {"action": "test_result"}
        executor._send_sms = AsyncMock(return_value=sentinel)
        executor._handlers["send_sms"] = executor._send_sms

        result = await executor.execute(
            intent="send_sms",
            slots={"recipient": "John", "message": "hi"},
            user_id=USER_ID,
            org_id=ORG_ID,
        )

        executor._send_sms.assert_awaited_once_with(
            slots={"recipient": "John", "message": "hi"},
            user_id=USER_ID,
            org_id=ORG_ID,
        )
        assert result == sentinel

    @pytest.mark.asyncio
    async def test_raises_value_error_for_unknown_intent(self, executor):
        """execute() should raise ValueError when given an unregistered intent."""
        with pytest.raises(ValueError, match="No handler registered for intent: bogus_intent"):
            await executor.execute(
                intent="bogus_intent",
                slots={},
                user_id=USER_ID,
                org_id=ORG_ID,
            )


# ---------------------------------------------------------------------------
# 4. _send_preapproval_letter
# ---------------------------------------------------------------------------

class TestSendPreapprovalLetter:
    @pytest.mark.asyncio
    async def test_sends_preapproval_letter_correct_sequence(self, executor):
        """Should fetch borrower/loan/lo, generate doc, send email, add note, and return expected shape."""
        borrower = {"id": "b-1", "full_name": "Jane Doe", "last_name": "Doe"}
        loan = {"id": "loan-1"}
        lo = {"full_name": "Tim LO", "nmls_number": "12345"}
        doc_result = {"pdf_bytes": b"%PDF", "document_id": "doc-1"}
        sent_result = {"message_id": "msg-1"}

        executor.crm.get_borrower = AsyncMock(return_value=borrower)
        executor.crm.get_active_loan = AsyncMock(return_value=loan)
        executor.crm.get_user = AsyncMock(return_value=lo)
        executor.docs.generate_preapproval_letter = AsyncMock(return_value=doc_result)
        executor.comms.send_email = AsyncMock(return_value=sent_result)
        executor.pipe.add_note = AsyncMock()

        slots = {
            "borrower_id": "b-1",
            "approval_amount": 450000,
            "recipient_email": "agent@example.com",
            "recipient_name": "Agent Smith",
            "property_address": "123 Main St",
            "expiry_days": 60,
        }

        result = await executor._send_preapproval_letter(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        # Verify call sequence
        executor.crm.get_borrower.assert_awaited_once_with("b-1", ORG_ID)
        executor.crm.get_active_loan.assert_awaited_once_with("b-1", ORG_ID)
        executor.crm.get_user.assert_awaited_once_with(USER_ID)

        executor.docs.generate_preapproval_letter.assert_awaited_once()
        call_kwargs = executor.docs.generate_preapproval_letter.call_args.kwargs
        assert call_kwargs["borrower"] is borrower
        assert call_kwargs["loan"] is loan
        assert call_kwargs["approval_amount"] == 450000.0
        assert call_kwargs["expiry_days"] == 60

        executor.comms.send_email.assert_awaited_once()
        email_kwargs = executor.comms.send_email.call_args.kwargs
        assert email_kwargs["to_email"] == "agent@example.com"
        assert "Pre-Approval Letter" in email_kwargs["subject"]
        assert len(email_kwargs["attachments"]) == 1
        assert email_kwargs["attachments"][0]["content_type"] == "application/pdf"

        executor.pipe.add_note.assert_awaited_once()

        # Verify return dict shape
        assert result["action"] == "pre_approval_letter_sent"
        assert result["borrower_name"] == "Jane Doe"
        assert result["recipient_email"] == "agent@example.com"
        assert result["amount"] == 450000
        assert result["message_id"] == "msg-1"
        assert result["loan_id"] == "loan-1"
        assert result["document_id"] == "doc-1"
        assert "sent_at" in result


# ---------------------------------------------------------------------------
# 5. _send_sms
# ---------------------------------------------------------------------------

class TestSendSMS:
    @pytest.mark.asyncio
    async def test_resolves_contact_and_sends_sms(self, executor):
        """Should resolve contact via CRM and send SMS via comms."""
        contact = {"name": "Bob", "phone": "+15551234567"}
        lo = {"full_name": "Tim LO"}
        sms_result = {"sent_at": "2026-04-13T12:00:00Z"}

        executor.crm.resolve_contact = AsyncMock(return_value=contact)
        executor.crm.get_user = AsyncMock(return_value=lo)
        executor.comms.send_sms = AsyncMock(return_value=sms_result)

        slots = {"recipient": "Bob", "message": "Hey, checking in"}
        result = await executor._send_sms(slots=slots, user_id=USER_ID, org_id=ORG_ID)

        executor.crm.resolve_contact.assert_awaited_once_with("Bob", ORG_ID)
        executor.comms.send_sms.assert_awaited_once_with(
            to_phone="+15551234567",
            from_user=lo,
            message="Hey, checking in",
            org_id=ORG_ID,
        )

        assert result["action"] == "sms_sent"
        assert result["to"] == "Bob"
        assert result["phone"] == "+15551234567"
        assert result["sent_at"] == "2026-04-13T12:00:00Z"


# ---------------------------------------------------------------------------
# 6. _send_email
# ---------------------------------------------------------------------------

class TestSendEmail:
    @pytest.mark.asyncio
    async def test_sends_email_with_correct_fields(self, executor):
        """Should resolve contact and send email with subject and body."""
        contact = {"name": "Alice", "email": "alice@example.com"}
        lo = {"full_name": "Tim LO"}
        email_result = {"sent_at": "2026-04-13T13:00:00Z"}

        executor.crm.resolve_contact = AsyncMock(return_value=contact)
        executor.crm.get_user = AsyncMock(return_value=lo)
        executor.comms.send_email = AsyncMock(return_value=email_result)

        slots = {
            "recipient": "Alice",
            "subject": "Loan Update",
            "body": "Your loan is on track.",
        }
        result = await executor._send_email(slots=slots, user_id=USER_ID, org_id=ORG_ID)

        executor.crm.resolve_contact.assert_awaited_once_with("Alice", ORG_ID)
        executor.comms.send_email.assert_awaited_once_with(
            to_email="alice@example.com",
            to_name="Alice",
            from_user=lo,
            subject="Loan Update",
            body="Your loan is on track.",
        )

        assert result["action"] == "email_sent"
        assert result["to"] == "Alice"
        assert result["email"] == "alice@example.com"
        assert result["sent_at"] == "2026-04-13T13:00:00Z"


# ---------------------------------------------------------------------------
# 7. _loan_status_lookup
# ---------------------------------------------------------------------------

class TestLoanStatusLookup:
    @pytest.mark.asyncio
    async def test_returns_expected_fields(self, executor):
        """Should return borrower info, loan stage, tasks, and missing docs."""
        borrower = {"id": "b-2", "full_name": "Sam Smith"}
        loan = {
            "id": "loan-2",
            "loan_amount": 350000,
            "stage": "PROCESSING",
            "sla_days_remaining": 12,
            "last_activity_at": "2026-04-10T10:00:00Z",
        }
        open_tasks = [{"id": "t1"}, {"id": "t2"}]
        doc_status = [
            {"name": "W-2", "received": True},
            {"name": "Bank Statement", "received": False},
            {"name": "Tax Return", "received": False},
        ]

        executor.crm.get_borrower = AsyncMock(return_value=borrower)
        executor.crm.get_active_loan = AsyncMock(return_value=loan)
        executor.pipe.get_open_tasks = AsyncMock(return_value=open_tasks)
        executor.pipe.get_document_status = AsyncMock(return_value=doc_status)

        slots = {"borrower_id": "b-2"}
        result = await executor._loan_status_lookup(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        assert result["borrower_name"] == "Sam Smith"
        assert result["loan_amount"] == 350000
        assert result["stage"] == "PROCESSING"
        assert result["sla_days_remaining"] == 12
        assert result["open_tasks"] == 2
        assert result["missing_docs"] == ["Bank Statement", "Tax Return"]
        assert result["last_activity"] == "2026-04-10T10:00:00Z"


# ---------------------------------------------------------------------------
# 8. _update_loan_status
# ---------------------------------------------------------------------------

class TestUpdateLoanStatus:
    @pytest.mark.asyncio
    async def test_updates_stage_and_adds_note(self, executor):
        """Should update loan stage via pipeline and add a status_change note."""
        borrower = {"id": "b-3", "full_name": "Rita Realtor"}
        loan = {"id": "loan-3", "stage": "PROCESSING"}

        executor.crm.get_borrower = AsyncMock(return_value=borrower)
        executor.crm.get_active_loan = AsyncMock(return_value=loan)
        executor.pipe.update_status = AsyncMock()
        executor.pipe.add_note = AsyncMock()

        slots = {"borrower_id": "b-3", "new_stage": "UNDERWRITING"}
        result = await executor._update_loan_status(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        executor.pipe.update_status.assert_awaited_once_with(
            "loan-3", "UNDERWRITING", USER_ID,
        )
        executor.pipe.add_note.assert_awaited_once_with(
            "loan-3", USER_ID,
            "Stage updated: PROCESSING \u2192 UNDERWRITING",
            "status_change",
        )

        assert result["action"] == "status_updated"
        assert result["borrower_name"] == "Rita Realtor"
        assert result["from_stage"] == "PROCESSING"
        assert result["to_stage"] == "UNDERWRITING"


# ---------------------------------------------------------------------------
# 9. _create_task
# ---------------------------------------------------------------------------

class TestCreateTask:
    @pytest.mark.asyncio
    async def test_creates_task_with_correct_fields(self, executor):
        """Should create a pipeline task with description, due date, and assignee."""
        task_result = {"id": "task-42"}

        executor.pipe.create_task = AsyncMock(return_value=task_result)

        slots = {
            "task_description": "Order appraisal",
            "due_date": "2026-04-20",
            "assigned_to": "user-009",
            "borrower_id": "b-4",
        }
        result = await executor._create_task(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        executor.pipe.create_task.assert_awaited_once_with(
            description="Order appraisal",
            due_date="2026-04-20",
            assigned_to="user-009",
            borrower_id="b-4",
            created_by=USER_ID,
            org_id=ORG_ID,
        )

        assert result["action"] == "task_created"
        assert result["task_id"] == "task-42"
        assert result["description"] == "Order appraisal"
        assert result["due_date"] == "2026-04-20"

    @pytest.mark.asyncio
    async def test_defaults_assigned_to_current_user(self, executor):
        """When assigned_to is absent from slots, should default to user_id."""
        executor.pipe.create_task = AsyncMock(return_value={"id": "task-43"})

        slots = {"task_description": "Follow up", "due_date": "2026-04-21"}
        await executor._create_task(slots=slots, user_id=USER_ID, org_id=ORG_ID)

        call_kwargs = executor.pipe.create_task.call_args.kwargs
        assert call_kwargs["assigned_to"] == USER_ID


# ---------------------------------------------------------------------------
# 10. _guideline_question
# ---------------------------------------------------------------------------

class TestGuidelineQuestion:
    @pytest.mark.asyncio
    async def test_returns_answer_from_knowledge_tools(self, executor):
        """Should forward question to knowledge tools and return text/sources/confidence."""
        answer = {
            "text": "FHA requires 3.5% down payment.",
            "sources": ["HUD Handbook 4000.1"],
            "confidence": 0.95,
        }
        executor.know.answer_guideline_question = AsyncMock(return_value=answer)

        slots = {"question": "What is the minimum down payment for FHA?"}
        result = await executor._guideline_question(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        executor.know.answer_guideline_question.assert_awaited_once_with(
            "What is the minimum down payment for FHA?"
        )

        assert result["answer"] == "FHA requires 3.5% down payment."
        assert result["sources"] == ["HUD Handbook 4000.1"]
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_defaults_sources_and_confidence_when_absent(self, executor):
        """If knowledge tools omit sources/confidence, return defaults."""
        executor.know.answer_guideline_question = AsyncMock(
            return_value={"text": "Conforming limit is $766,550."}
        )

        slots = {"question": "What is the conforming loan limit?"}
        result = await executor._guideline_question(
            slots=slots, user_id=USER_ID, org_id=ORG_ID,
        )

        assert result["answer"] == "Conforming limit is $766,550."
        assert result["sources"] == []
        assert result["confidence"] is None


# ---------------------------------------------------------------------------
# 11. Borrower not found raises ValueError
# ---------------------------------------------------------------------------

class TestBorrowerNotFound:
    @pytest.mark.asyncio
    async def test_preapproval_raises_when_borrower_not_found(self, executor):
        """_send_preapproval_letter should raise ValueError when CRM returns None."""
        executor.crm.get_borrower = AsyncMock(return_value=None)

        slots = {
            "borrower_id": "nonexistent",
            "approval_amount": 300000,
            "recipient_email": "agent@example.com",
        }

        with pytest.raises(ValueError, match="Borrower not found: nonexistent"):
            await executor._send_preapproval_letter(
                slots=slots, user_id=USER_ID, org_id=ORG_ID,
            )

        # Downstream tools should never have been called
        executor.crm.get_active_loan.assert_not_called()
