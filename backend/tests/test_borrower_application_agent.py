"""Unit tests for the BorrowerApplicationAgent and its tools."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestStructuredOutputParsing:
    def test_extracts_json_from_response(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = (
            "Great question! The employment section asks about your work history.\n\n"
            "```json\n"
            '{"borrower_question": "what is employment", "application_section": "employment", '
            '"field_name": null, "intent": "explain_field", "risk_level": "low", '
            '"documents_suggested": ["pay_stubs", "w2"], "escalate_to_human": false, '
            '"meeting_offered": false, "compliance_flags": [], "next_best_action": "continue"}\n'
            "```"
        )
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is not None
        assert result["intent"] == "explain_field"
        assert result["risk_level"] == "low"
        assert "pay_stubs" in result["documents_suggested"]

    def test_strips_json_block_from_content(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = 'Hello!\n\n```json\n{"intent": "test"}\n```'
        result = BorrowerApplicationAgent._strip_json_block(text)
        assert "```json" not in result
        assert "Hello!" in result

    def test_returns_none_for_invalid_json(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = '```json\n{invalid json}\n```'
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is None

    def test_returns_none_when_no_json_block(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = "Just a plain text response with no JSON."
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is None


class TestPromptDocumentUpload:
    def test_known_document_type(self):
        from agents.tools.borrower_application import prompt_document_upload

        result = prompt_document_upload(
            document_type="pay_stubs",
            reason="Needed for income verification",
            application_id="abc-123",
        )
        assert result.data["action"] == "prompt_upload"
        assert result.data["label"] == "Recent Pay Stubs (last 30 days)"
        assert "abc-123" in result.data["upload_url"]

    def test_unknown_document_type_uses_title_case(self):
        from agents.tools.borrower_application import prompt_document_upload

        result = prompt_document_upload(
            document_type="custom_doc",
            reason="Special request",
            application_id="xyz-456",
        )
        assert result.data["label"] == "Custom Doc"


class TestRecallBorrowerContext:
    @patch("agents.tools.borrower_application.get_db")
    @patch("agents.tools.borrower_application.execute_query")
    def test_returns_history(self, mock_query, mock_db):
        from agents.tools.borrower_application import recall_borrower_context
        from datetime import datetime

        mock_db.return_value = MagicMock()
        mock_query.return_value = [
            ("aria", "DTI stands for...", None, datetime(2026, 5, 1, 12, 1)),
            ("borrower", "What is DTI?", "high", datetime(2026, 5, 1, 12, 0)),
        ]

        result = recall_borrower_context(
            application_id="test-app",
            organization_id=1,
            limit=10,
        )
        assert result.data["message_count"] == 2
        assert result.data["history"][0]["role"] == "borrower"


class TestEmitCrmEvent:
    @pytest.mark.asyncio
    @patch("services.event_bus.event_bus")
    async def test_publishes_escalation_event(self, mock_bus):
        from agents.tools.borrower_application import emit_crm_event

        mock_bus.publish = AsyncMock()

        result = await emit_crm_event.__wrapped__(
            event_type="APPLICATION_ESCALATION",
            organization_id=1,
            application_id="app-123",
            contact_id=42,
            data={"trigger": "bankruptcy"},
        )
        assert result["published"] is True
        mock_bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_unknown_event_type(self):
        from agents.tools.borrower_application import emit_crm_event

        result = await emit_crm_event.__wrapped__(
            event_type="INVALID_TYPE",
            organization_id=1,
            application_id="app-123",
            contact_id=42,
            data={},
        )
        assert "error" in result
