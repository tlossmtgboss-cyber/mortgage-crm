"""Unit tests for Email Tools.

Tests for the get_emails_needing_response tool and related email intelligence
functionality.

Run with:
    pytest tests/test_email_tools.py -v
    pytest tests/test_email_tools.py -v --cov=agents.tools.email_intel
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

# Skip entire module if agents.tools.email_intel can't be imported
# (requires full DB/package chain that isn't available in SQLite test env)
pytest.importorskip("agents.tools.email_intel", reason="agents.tools.email_intel not importable in test env")


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_execute_query():
    """Mock the execute_query function."""
    with patch('agents.tools.email_intel.execute_query') as mock:
        yield mock


@pytest.fixture
def sample_email_results():
    """Sample email results from database."""
    return [
        {
            "id": 1,
            "from_email": "john.borrower@gmail.com",
            "from_name": "John Borrower",
            "subject": "Question about my loan application",
            "body_preview": "Hi, I wanted to ask about the status of my...",
            "received_date": datetime(2025, 12, 3, 10, 30, 0, tzinfo=timezone.utc),
            "match_client_name": "John Borrower",
            "matched_loan_id": 123,
            "matched_lead_id": None,
            "is_priority": True,
            "status": "pending",
            "disposition": None,
            "has_attachments": True,
            "match_confidence": 0.95,
        },
        {
            "id": 2,
            "from_email": "jane.smith@outlook.com",
            "from_name": "Jane Smith",
            "subject": "Document upload confirmation",
            "body_preview": "I've uploaded the requested documents...",
            "received_date": datetime(2025, 12, 3, 9, 15, 0, tzinfo=timezone.utc),
            "match_client_name": "Jane Smith",
            "matched_loan_id": None,
            "matched_lead_id": 456,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": True,
            "match_confidence": 0.90,
        },
        {
            "id": 3,
            "from_email": "unknown@company.com",
            "from_name": "Unknown Sender",
            "subject": "RE: Mortgage inquiry",
            "body_preview": "Thank you for your interest in our services...",
            "received_date": datetime(2025, 12, 2, 14, 0, 0, tzinfo=timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        },
    ]


# ============================================================
# Tests: get_emails_needing_response
# ============================================================

class TestGetEmailsNeedingResponse:
    """Tests for the get_emails_needing_response tool."""

    def test_requires_user_id(self):
        """Should return error when user_id is not provided."""
        from agents.tools.email_intel import get_emails_needing_response

        result = get_emails_needing_response(user_id=None)

        assert result.status.value == "error"
        # ToolResult uses 'message' for error text, not 'error' attribute
        assert "user_id is required" in result.message

    def test_returns_emails(self, mock_execute_query, sample_email_results):
        """Should return emails needing response."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1, days=7)

        assert result.status.value == "success"
        assert result.data["total_count"] == 3
        assert len(result.data["emails"]) == 3

    def test_counts_priority_emails(self, mock_execute_query, sample_email_results):
        """Should count priority emails correctly."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1)

        assert result.data["priority_count"] == 1  # Only John Borrower is priority

    def test_empty_inbox(self, mock_execute_query):
        """Should handle empty inbox gracefully."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = []

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "success"
        assert result.data["total_count"] == 0
        assert "clear" in result.message.lower()

    def test_respects_days_parameter(self, mock_execute_query, sample_email_results):
        """Should filter by days parameter."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1, days=30)

        # Check that query was called with correct date range
        # The implementation uses start_date calculated from days parameter
        call_args = mock_execute_query.call_args
        params = call_args[0][1]  # Second arg is params dict
        assert "start_date" in params  # days is converted to start_date in implementation

    def test_respects_limit_parameter(self, mock_execute_query, sample_email_results):
        """Should respect limit parameter."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results[:2]

        result = get_emails_needing_response(user_id=1, limit=2)

        assert len(result.data["emails"]) <= 2

    def test_unread_only_filter(self, mock_execute_query, sample_email_results):
        """Should filter by unread_only parameter."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1, unread_only=True)

        # Check that status filter was included in query
        call_args = mock_execute_query.call_args
        query = call_args[0][0]
        assert "pending" in query.lower() or "status" in query.lower()

    def test_email_format(self, mock_execute_query, sample_email_results):
        """Should format email data correctly."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1)

        email = result.data["emails"][0]

        # Check all required fields
        assert "email_id" in email
        assert "from_email" in email
        assert "from_name" in email
        assert "subject" in email
        assert "preview" in email
        assert "received_date" in email
        assert "is_priority" in email
        assert "status" in email
        assert "has_attachments" in email

    def test_preview_truncation(self, mock_execute_query):
        """Should truncate long previews."""
        from agents.tools.email_intel import get_emails_needing_response

        long_preview = "x" * 500
        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "Test",
            "body_preview": long_preview,
            "received_date": datetime.now(timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        # Preview should be truncated to 200 chars
        assert len(result.data["emails"][0]["preview"]) <= 200

    def test_handles_database_error(self, mock_execute_query):
        """Should handle database errors gracefully."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.side_effect = Exception("Database connection failed")

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "error"
        # ToolResult uses 'message' for error text, and 'errors' list for details
        assert "failed" in result.message.lower() or "database" in result.message.lower()

    def test_handles_null_received_date(self, mock_execute_query):
        """Should handle null received_date gracefully."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "Test",
            "body_preview": "Test preview",
            "received_date": None,
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "success"
        assert result.data["emails"][0]["received_date"] is None

    def test_includes_client_match_info(self, mock_execute_query, sample_email_results):
        """Should include client match information."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1)

        # First email has loan_id match
        email1 = result.data["emails"][0]
        assert email1["client_name"] == "John Borrower"
        assert email1["loan_id"] == 123

        # Second email has lead_id match
        email2 = result.data["emails"][1]
        assert email2["client_name"] == "Jane Smith"
        assert email2["lead_id"] == 456

    def test_summary_message_with_priority(self, mock_execute_query, sample_email_results):
        """Should include priority count in summary message."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = sample_email_results

        result = get_emails_needing_response(user_id=1)

        assert "priority" in result.message.lower()
        assert "3" in result.message  # Total count
        assert "1" in result.message  # Priority count

    def test_summary_message_without_priority(self, mock_execute_query):
        """Should not mention priority when none exist."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "Test",
            "body_preview": "Test",
            "received_date": datetime.now(timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        # Message should just say count, not mention "0 priority"
        assert "0 priority" not in result.message.lower()


# ============================================================
# Tests: Tool Registration
# ============================================================

class TestEmailToolRegistration:
    """Tests for email tool registration."""

    def test_tool_is_registered(self):
        """Should be registered in tool registry."""
        from agents.tools.base import tool_registry

        tool = tool_registry.get("get_emails_needing_response")
        assert tool is not None

    def test_tool_metadata(self):
        """Should have correct metadata."""
        from agents.tools.base import tool_registry

        metadata = tool_registry.get_metadata("get_emails_needing_response")

        assert metadata is not None
        assert "email_intelligence" in metadata.get("agent_roles", [])
        assert metadata.get("risk_level") == "LOW"


# ============================================================
# Tests: Edge Cases
# ============================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_handles_empty_body_preview(self, mock_execute_query):
        """Should handle empty body preview."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "Test",
            "body_preview": "",
            "received_date": datetime.now(timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "success"
        assert result.data["emails"][0]["preview"] == ""

    def test_handles_none_body_preview(self, mock_execute_query):
        """Should handle None body preview."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "Test",
            "body_preview": None,
            "received_date": datetime.now(timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "success"
        # Should not crash on None

    def test_large_result_set(self, mock_execute_query):
        """Should handle large result sets."""
        from agents.tools.email_intel import get_emails_needing_response

        # Create 100 mock emails
        large_results = []
        for i in range(100):
            large_results.append({
                "id": i,
                "from_email": f"test{i}@example.com",
                "from_name": f"Test {i}",
                "subject": f"Subject {i}",
                "body_preview": f"Preview {i}",
                "received_date": datetime.now(timezone.utc),
                "match_client_name": None,
                "matched_loan_id": None,
                "matched_lead_id": None,
                "is_priority": i % 5 == 0,  # Every 5th is priority
                "status": "pending",
                "disposition": None,
                "has_attachments": False,
                "match_confidence": None,
            })

        mock_execute_query.return_value = large_results

        result = get_emails_needing_response(user_id=1, limit=100)

        assert result.status.value == "success"
        assert result.data["total_count"] == 100
        assert result.data["priority_count"] == 20  # 100/5 = 20

    def test_special_characters_in_subject(self, mock_execute_query):
        """Should handle special characters in subject."""
        from agents.tools.email_intel import get_emails_needing_response

        mock_execute_query.return_value = [{
            "id": 1,
            "from_email": "test@example.com",
            "from_name": "Test",
            "subject": "RE: Loan #12345 - 🏠 New Home! <Important>",
            "body_preview": "Test",
            "received_date": datetime.now(timezone.utc),
            "match_client_name": None,
            "matched_loan_id": None,
            "matched_lead_id": None,
            "is_priority": False,
            "status": "pending",
            "disposition": None,
            "has_attachments": False,
            "match_confidence": None,
        }]

        result = get_emails_needing_response(user_id=1)

        assert result.status.value == "success"
        assert "🏠" in result.data["emails"][0]["subject"]


# ============================================================
# Run tests if executed directly
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
