"""
Tests for aria/tools/pipeline_tools.py — PipelineTools class.

Mocks SessionLocal and asyncio.to_thread so tests run without a database.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session():
    """Return a fresh MagicMock that behaves like a SQLAlchemy Session."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


async def _passthrough_to_thread(fn, *args, **kwargs):
    """Replace asyncio.to_thread — just call the function synchronously."""
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    return _make_mock_session()


@pytest.fixture
def pipeline_tools(mock_session):
    """Import PipelineTools with SessionLocal patched."""
    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        yield PipelineTools(), mock_session


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_status_updates_loan_stage_and_commits(mock_session):
    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.update_status(loan_id=42, new_stage="processing", user_id="u1")

        # Verify the session executed an UPDATE and committed
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

        assert result["loan_id"] == 42
        assert result["new_stage"] == "PROCESSING"


@pytest.mark.asyncio
async def test_update_status_uppercases_and_underscores_stage(mock_session):
    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.update_status(loan_id=1, new_stage="clear to close", user_id="u1")

        assert result["new_stage"] == "CLEAR_TO_CLOSE"

        # Confirm the SQL params used the uppercased stage
        sql_call_args = mock_session.execute.call_args
        params = sql_call_args[0][1]  # positional arg [1] is the params dict
        assert params["stage"] == "CLEAR_TO_CLOSE"


# ---------------------------------------------------------------------------
# add_note
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_note_creates_note_in_loan_notes_table(mock_session):
    """When loan_notes INSERT succeeds, return the new note id and timestamp."""
    fake_created = datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc)
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: (7, fake_created)[idx]

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_result

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.add_note(loan_id=10, user_id="u1", note="Borrower called", note_type="manual")

        assert result["id"] == 7
        assert result["created_at"] == fake_created.isoformat()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_add_note_falls_back_to_lead_notes_when_loan_notes_fails(mock_session):
    """When loan_notes INSERT raises, fall back to updating leads.notes."""
    # First execute call (INSERT INTO loan_notes) raises
    # Second execute call (UPDATE leads) succeeds
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("relation loan_notes does not exist")
        return MagicMock()

    mock_session.execute.side_effect = side_effect

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.add_note(loan_id=10, user_id="u1", note="Fallback note")

        # Should have attempted rollback after first failure, then committed fallback
        mock_session.rollback.assert_called_once()
        # The second commit is from the fallback path
        assert mock_session.commit.call_count == 1
        # Two execute calls: the failed INSERT and the fallback UPDATE
        assert mock_session.execute.call_count == 2
        # Fallback returns id=0
        assert result["id"] == 0
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_task_creates_with_correct_fields(mock_session):
    fake_created = datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: (99, fake_created)[idx]

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_result

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.create_task(
            description="Follow up with borrower",
            due_date="2026-04-20",
            assigned_to="u5",
            borrower_id="b3",
            created_by="u1",
            org_id="org7",
        )

        assert result["id"] == 99
        assert result["created_at"] == fake_created.isoformat()
        mock_session.commit.assert_called_once()

        # Verify the params passed to execute
        sql_call_args = mock_session.execute.call_args
        params = sql_call_args[0][1]
        assert params["title"] == "Follow up with borrower"
        assert params["desc"] == "Follow up with borrower"
        assert params["due"] == "2026-04-20"
        assert params["owner"] == "u5"
        assert params["lead"] == "b3"
        assert params["org"] == "org7"


@pytest.mark.asyncio
async def test_create_task_truncates_title_to_200_chars(mock_session):
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, idx: (1, None)[idx]
    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_result

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        long_desc = "A" * 300
        await pt.create_task(description=long_desc, due_date="2026-05-01", assigned_to="u1")

        params = mock_session.execute.call_args[0][1]
        assert len(params["title"]) == 200
        assert params["desc"] == long_desc  # full description preserved


# ---------------------------------------------------------------------------
# get_open_tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_open_tasks_returns_list_of_open_tasks(mock_session):
    mock_rows = [
        (1, "Call borrower", "2026-04-15", "pending"),
        (2, "Order appraisal", "2026-04-16", "in_progress"),
    ]
    mock_session.execute.return_value.fetchall.return_value = mock_rows

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.get_open_tasks(loan_id=42)

        assert len(result) == 2
        assert result[0] == {"id": 1, "title": "Call borrower", "due_date": "2026-04-15", "status": "pending"}
        assert result[1] == {"id": 2, "title": "Order appraisal", "due_date": "2026-04-16", "status": "in_progress"}
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_open_tasks_returns_empty_list_when_no_tasks(mock_session):
    mock_session.execute.return_value.fetchall.return_value = []

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.get_open_tasks(loan_id=999)

        assert result == []


@pytest.mark.asyncio
async def test_get_open_tasks_returns_empty_list_on_exception(mock_session):
    """When the DB query fails, get_open_tasks catches the exception and returns []."""
    mock_session.execute.side_effect = Exception("connection lost")

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.get_open_tasks(loan_id=1)

        assert result == []
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# get_document_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_document_status_returns_document_status_list(mock_session):
    mock_rows = [
        (10, "W-2 2025", "completed"),
        (11, "Pay Stubs", "pending"),
        (12, "Bank Statements", "completed"),
    ]
    mock_session.execute.return_value.fetchall.return_value = mock_rows

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.get_document_status(loan_id=42)

        assert len(result) == 3
        assert result[0] == {"id": 10, "name": "W-2 2025", "received": True, "status": "completed"}
        assert result[1] == {"id": 11, "name": "Pay Stubs", "received": False, "status": "pending"}
        assert result[2] == {"id": 12, "name": "Bank Statements", "received": True, "status": "completed"}
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_document_status_returns_empty_list_on_error(mock_session):
    mock_session.execute.side_effect = Exception("table not found")

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.get_document_status(loan_id=1)

        assert result == []


# ---------------------------------------------------------------------------
# send_document_request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_document_request_creates_request_records(mock_session):
    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        borrower = {"id": "b55"}
        result = await pt.send_document_request(
            loan_id=42,
            borrower=borrower,
            doc_list="W-2, Pay Stubs, Bank Statements",
            due_date="2026-04-20",
            note="Needed for UW",
            requested_by="u1",
        )

        assert result["docs_requested"] == 3
        assert result["portal_link"] == "https://app.perenniaai.com/portal/b55/documents"

        # One INSERT per document
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_send_document_request_returns_error_on_failure(mock_session):
    mock_session.execute.side_effect = Exception("insert failed")

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.send_document_request(
            loan_id=42, borrower={"id": "b1"}, doc_list="W-2",
        )

        assert result["docs_requested"] == 0
        assert "error" in result
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_report_returns_report_dict(mock_session):
    # Set up the three sequential execute calls:
    # 1) COUNT(*) for active loans (scalar)
    # 2) stage breakdown (fetchall)
    # 3) funded summary (fetchone)

    mock_active_result = MagicMock()
    mock_active_result.scalar.return_value = 15

    mock_stage_rows = [("PROCESSING", 6), ("UNDERWRITING", 5), ("APPLICATION", 4)]
    mock_stages_result = MagicMock()
    mock_stages_result.fetchall.return_value = mock_stage_rows

    mock_funded_row = MagicMock()
    mock_funded_row.__getitem__ = lambda self, idx: (3, 1250000.00)[idx]
    mock_funded_result = MagicMock()
    mock_funded_result.fetchone.return_value = mock_funded_row

    mock_session.execute.side_effect = [
        mock_active_result,
        mock_stages_result,
        mock_funded_result,
    ]

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.generate_report(user_id="u1", org_id="org7", time_period="this month")

        assert result["active_loans"] == 15
        assert result["by_stage"] == {"PROCESSING": 6, "UNDERWRITING": 5, "APPLICATION": 4}
        assert result["funded_this_month"] == 3
        assert result["funded_volume"] == 1250000.00
        assert result["time_period"] == "this month"
        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_generate_report_returns_error_on_failure(mock_session):
    mock_session.execute.side_effect = Exception("db unavailable")

    with patch("aria.tools.pipeline_tools.SessionLocal", return_value=mock_session), \
         patch("aria.tools.pipeline_tools.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = _passthrough_to_thread

        from aria.tools.pipeline_tools import PipelineTools
        pt = PipelineTools()

        result = await pt.generate_report(user_id="u1", org_id="org7")

        assert "error" in result
        mock_session.close.assert_called_once()
