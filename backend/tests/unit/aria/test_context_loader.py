"""
Unit Tests for Aria Context Loader

Tests for AriaContextLoader which loads pipeline context, recent contacts,
and borrower data for context-aware Aria responses.

All database access and asyncio.to_thread calls are mocked -- no real DB required.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock, call

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session(
    user_row=None,
    active_count=0,
    stages=None,
    urgent_count=0,
    recent_leads=None,
    slot_leads=None,
    borrower_row=None,
):
    """Build a mock SessionLocal that returns predetermined query results.

    The real _query() functions call db.execute(text(...)).fetchone/fetchall/scalar
    in a specific order.  We use side_effect lists on a single mock execute to
    return the right result object for each successive call.
    """
    db = MagicMock()

    # Each db.execute() returns a result proxy; .fetchone(), .fetchall(), .scalar()
    # are called on that proxy.  We build one proxy per call.
    call_results = []

    # --- load_full order ---
    # 1. user row (fetchone)
    user_result = MagicMock()
    user_result.fetchone.return_value = user_row
    call_results.append(user_result)

    if user_row is not None:
        # 2. active loan count (scalar)
        count_result = MagicMock()
        count_result.scalar.return_value = active_count
        call_results.append(count_result)

        # 3. stage breakdown (fetchall)
        stages_result = MagicMock()
        stages_result.fetchall.return_value = stages or []
        call_results.append(stages_result)

        # 4. urgent tasks (scalar)
        urgent_result = MagicMock()
        urgent_result.scalar.return_value = urgent_count
        call_results.append(urgent_result)

        # 5. recent leads (fetchall)
        recent_result = MagicMock()
        recent_result.fetchall.return_value = recent_leads or []
        call_results.append(recent_result)

    db.execute.side_effect = call_results
    return db


def _make_slot_session(user_row=None, slot_rows=None, borrower_row=None):
    """Build mock session for load_for_slot queries."""
    db = MagicMock()
    call_results = []

    # 1. user org lookup (fetchone)
    org_result = MagicMock()
    org_result.fetchone.return_value = user_row
    call_results.append(org_result)

    if user_row is not None:
        if slot_rows is not None:
            # borrower slot: leads fetchall
            leads_result = MagicMock()
            leads_result.fetchall.return_value = slot_rows
            call_results.append(leads_result)
        elif borrower_row is not None:
            # borrower_id lookup: fetchone
            borrow_result = MagicMock()
            borrow_result.fetchone.return_value = borrower_row
            call_results.append(borrow_result)

    db.execute.side_effect = call_results
    return db


def _make_slot(slot_type="borrower"):
    """Create a minimal slot mock."""
    slot = MagicMock()
    slot.slot_type = slot_type
    return slot


def _make_intent(required_slots=None):
    """Create a minimal intent mock."""
    intent = MagicMock()
    intent.required_slots = required_slots or []
    return intent


# ---------------------------------------------------------------------------
# Tests: load_full
# ---------------------------------------------------------------------------

class TestLoadFull:
    """Tests for AriaContextLoader.load_full()."""

    @pytest.mark.asyncio
    async def test_load_full_returns_pipeline_summary(self):
        """load_full returns dict with pipeline_summary containing active loan count and breakdown."""
        user_row = ("Tim", "Loss", "org-1")
        stages = [("PROCESSING", 3), ("UNDERWRITING", 2)]

        db = _make_mock_session(
            user_row=user_row,
            active_count=5,
            stages=stages,
            urgent_count=1,
            recent_leads=[("Alice Smith", "APPLICATION", "2026-04-10")],
        )

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-123")

        assert "pipeline_summary" in result
        assert "5 active loans" in result["pipeline_summary"]
        assert "PROCESSING: 3" in result["pipeline_summary"]
        assert "UNDERWRITING: 2" in result["pipeline_summary"]
        assert "1 urgent task." in result["pipeline_summary"]

    @pytest.mark.asyncio
    async def test_load_full_returns_user_name(self):
        """load_full includes the user's full name."""
        user_row = ("Jane", "Doe", "org-2")

        db = _make_mock_session(user_row=user_row)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-456")

        assert result["user_name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_load_full_returns_safe_default_on_db_error(self):
        """load_full returns safe defaults when the database raises an exception."""
        db = MagicMock()
        db.execute.side_effect = Exception("connection refused")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-bad")

        assert result["user_name"] == "there"
        assert result["pipeline_summary"] == ""
        assert result["recent_contacts"] == ""
        assert result["active_loan_count"] == 0
        assert result["urgent_task_count"] == 0

    @pytest.mark.asyncio
    async def test_load_full_returns_safe_default_when_user_not_found(self):
        """load_full returns safe defaults when user row is None."""
        db = _make_mock_session(user_row=None)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("nonexistent")

        assert result["user_name"] == "there"
        assert result["pipeline_summary"] == ""

    @pytest.mark.asyncio
    async def test_load_full_includes_lead_and_loan_counts(self):
        """load_full result includes active_loan_count and urgent_task_count."""
        user_row = ("Bob", "Builder", "org-3")

        db = _make_mock_session(
            user_row=user_row,
            active_count=12,
            stages=[("APPLICATION", 5), ("CTC", 7)],
            urgent_count=3,
        )

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-bob")

        assert result["active_loan_count"] == 12
        assert result["urgent_task_count"] == 3

    @pytest.mark.asyncio
    async def test_load_full_handles_empty_database(self):
        """load_full handles a database with no loans, tasks, or leads gracefully."""
        user_row = ("New", "User", "org-empty")

        db = _make_mock_session(
            user_row=user_row,
            active_count=0,
            stages=[],
            urgent_count=0,
            recent_leads=[],
        )

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-new")

        assert result["active_loan_count"] == 0
        assert result["urgent_task_count"] == 0
        assert "0 active loans" in result["pipeline_summary"]
        assert "empty" in result["pipeline_summary"]
        assert result["recent_contacts"] == "No recent contacts."

    @pytest.mark.asyncio
    async def test_load_full_plural_urgent_tasks(self):
        """load_full uses plural 'tasks' when urgent count is not 1."""
        user_row = ("A", "B", "org-1")

        db = _make_mock_session(user_row=user_row, active_count=1, urgent_count=4)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-x")

        assert "4 urgent tasks." in result["pipeline_summary"]

    @pytest.mark.asyncio
    async def test_load_full_singular_urgent_task(self):
        """load_full uses singular 'task' when urgent count is 1."""
        user_row = ("A", "B", "org-1")

        db = _make_mock_session(user_row=user_row, active_count=1, urgent_count=1)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-x")

        assert "1 urgent task." in result["pipeline_summary"]

    @pytest.mark.asyncio
    async def test_load_full_closes_session(self):
        """load_full always closes the database session, even on success."""
        user_row = ("A", "B", "org-1")
        db = _make_mock_session(user_row=user_row)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            await loader.load_full("user-1")

        db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_full_closes_session_on_error(self):
        """load_full closes the database session even when an error occurs."""
        db = MagicMock()
        db.execute.side_effect = RuntimeError("boom")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            await loader.load_full("user-err")

        db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_full_recent_contacts_formatting(self):
        """load_full formats recent contacts as bulleted list."""
        user_row = ("A", "B", "org-1")
        recent = [
            ("Alice Jones", "APPLICATION", "2026-04-10"),
            ("Bob Green", "PROCESSING", "2026-04-09"),
        ]

        db = _make_mock_session(user_row=user_row, recent_leads=recent)

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-1")

        assert "- Alice Jones (APPLICATION)" in result["recent_contacts"]
        assert "- Bob Green (PROCESSING)" in result["recent_contacts"]


# ---------------------------------------------------------------------------
# Tests: load_for_slot
# ---------------------------------------------------------------------------

class TestLoadForSlot:
    """Tests for AriaContextLoader.load_for_slot()."""

    @pytest.mark.asyncio
    async def test_load_for_slot_borrower_type_returns_recent_leads(self):
        """load_for_slot with borrower slot type returns recent borrower list."""
        user_row = ("org-1",)
        slot_rows = [
            ("Alice Smith", 350000, "APPLICATION", "123 Main St"),
            ("Bob Jones", None, "PROCESSING", None),
        ]

        db = _make_slot_session(user_row=user_row, slot_rows=slot_rows)
        slot = _make_slot(slot_type="borrower")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("user-1", slot, {})

        assert "Recent borrowers:" in result
        assert "Alice Smith" in result
        assert "$350,000" in result
        assert "123 Main St" in result
        assert "Bob Jones" in result
        assert "N/A" in result  # None loan_amount formatted as N/A

    @pytest.mark.asyncio
    async def test_load_for_slot_with_borrower_id_in_slots(self):
        """load_for_slot returns borrower details when borrower_id is in slots_so_far."""
        user_row = ("org-1",)
        borrower_row = ("Alice Smith", 450000, "456 Oak Ave", "UNDERWRITING")

        db = _make_slot_session(user_row=user_row, borrower_row=borrower_row)
        slot = _make_slot(slot_type="amount")  # non-borrower slot

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("user-1", slot, {"borrower_id": "42"})

        assert "Alice Smith" in result
        assert "$450,000" in result
        assert "456 Oak Ave" in result
        assert "UNDERWRITING" in result

    @pytest.mark.asyncio
    async def test_load_for_slot_returns_no_context_when_user_not_found(self):
        """load_for_slot returns fallback string when user does not exist."""
        db = _make_slot_session(user_row=None)
        slot = _make_slot()

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("ghost", slot, {})

        assert result == "No context available."

    @pytest.mark.asyncio
    async def test_load_for_slot_returns_fallback_on_db_error(self):
        """load_for_slot returns fallback string on database exception."""
        db = MagicMock()
        db.execute.side_effect = Exception("timeout")
        slot = _make_slot()

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("user-1", slot, {})

        assert result == "No additional context."

    @pytest.mark.asyncio
    async def test_load_for_slot_no_matching_borrower_returns_fallback(self):
        """load_for_slot returns fallback when borrower_id does not match any lead."""
        user_row = ("org-1",)
        db = _make_slot_session(user_row=user_row, borrower_row=None)

        # Need to add a second execute result for the borrower lookup
        # When slot_type != "borrower" and borrower_id is set, it queries for borrower
        slot = _make_slot(slot_type="amount")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("user-1", slot, {"borrower_id": "999"})

        assert result == "No additional context."

    @pytest.mark.asyncio
    async def test_load_for_slot_non_borrower_no_borrower_id_returns_fallback(self):
        """load_for_slot returns fallback when slot is not borrower type and no borrower_id."""
        user_row = ("org-1",)
        db = _make_slot_session(user_row=user_row)
        slot = _make_slot(slot_type="amount")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_for_slot("user-1", slot, {})

        assert result == "No additional context."

    @pytest.mark.asyncio
    async def test_load_for_slot_closes_session(self):
        """load_for_slot always closes the database session."""
        user_row = ("org-1",)
        db = _make_slot_session(user_row=user_row)
        slot = _make_slot(slot_type="amount")

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            await loader.load_for_slot("user-1", slot, {})

        db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: build_preview_context
# ---------------------------------------------------------------------------

class TestBuildPreviewContext:
    """Tests for AriaContextLoader.build_preview_context()."""

    @pytest.mark.asyncio
    async def test_build_preview_context_delegates_to_load_for_slot(self):
        """build_preview_context calls load_for_slot with first required slot."""
        user_row = ("org-1",)
        slot_rows = [("Alice", 300000, "APPLICATION", "100 First St")]

        db = _make_slot_session(user_row=user_row, slot_rows=slot_rows)

        slot = _make_slot(slot_type="borrower")
        intent = _make_intent(required_slots=[slot])

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.build_preview_context("user-1", intent, {"key": "val"})

        assert isinstance(result, str)
        assert "Alice" in result

    @pytest.mark.asyncio
    async def test_build_preview_context_with_no_required_slots(self):
        """build_preview_context passes None as slot when intent has no required_slots."""
        user_row = ("org-1",)

        db = MagicMock()
        # With None slot, slot.slot_type will raise, triggering the except block
        db.execute.side_effect = AttributeError("'NoneType' has no attribute 'slot_type'")

        intent = _make_intent(required_slots=[])

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.build_preview_context("user-1", intent, {})

        # Should return fallback since None slot causes error in load_for_slot
        assert result == "No additional context."

    @pytest.mark.asyncio
    async def test_build_preview_context_returns_string(self):
        """build_preview_context always returns a string."""
        db = MagicMock()
        db.execute.side_effect = Exception("any error")

        intent = _make_intent(required_slots=[_make_slot()])

        with patch("aria.core.context_loader.SessionLocal", return_value=db):
            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.build_preview_context("user-1", intent, {})

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Tests: asyncio.to_thread usage
# ---------------------------------------------------------------------------

class TestAsyncioToThreadUsage:
    """Verify that sync DB functions are properly wrapped via asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_load_full_uses_asyncio_to_thread(self):
        """load_full wraps its sync _query function via asyncio.to_thread."""
        user_row = ("A", "B", "org-1")
        db = _make_mock_session(user_row=user_row)

        with patch("aria.core.context_loader.SessionLocal", return_value=db), \
             patch("aria.core.context_loader.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Make to_thread return a plausible result
            mock_to_thread.return_value = {
                "user_name": "A B", "pipeline_summary": "mocked",
                "recent_contacts": "", "org_name": "",
                "active_loan_count": 0, "urgent_task_count": 0,
            }

            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            result = await loader.load_full("user-1")

        mock_to_thread.assert_called_once()
        # The argument should be a callable (the inner _query function)
        called_fn = mock_to_thread.call_args[0][0]
        assert callable(called_fn)

    @pytest.mark.asyncio
    async def test_load_for_slot_uses_asyncio_to_thread(self):
        """load_for_slot wraps its sync _query function via asyncio.to_thread."""
        with patch("aria.core.context_loader.SessionLocal", return_value=MagicMock()), \
             patch("aria.core.context_loader.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = "mocked context"

            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            slot = _make_slot()
            result = await loader.load_for_slot("user-1", slot, {})

        mock_to_thread.assert_called_once()
        called_fn = mock_to_thread.call_args[0][0]
        assert callable(called_fn)
        assert result == "mocked context"

    @pytest.mark.asyncio
    async def test_build_preview_context_uses_asyncio_to_thread(self):
        """build_preview_context (via load_for_slot) uses asyncio.to_thread."""
        with patch("aria.core.context_loader.SessionLocal", return_value=MagicMock()), \
             patch("aria.core.context_loader.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = "preview context"

            from aria.core.context_loader import AriaContextLoader

            loader = AriaContextLoader()
            intent = _make_intent(required_slots=[_make_slot()])
            result = await loader.build_preview_context("user-1", intent, {})

        mock_to_thread.assert_called_once()
        assert result == "preview context"
