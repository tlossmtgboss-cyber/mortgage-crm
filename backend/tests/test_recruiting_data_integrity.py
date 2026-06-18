"""
Tests for recruiting service data integrity fixes (Task 2).

Covers:
- 2a: not_selected added to VALID_TRANSITIONS
- 2b: respond_to_offer expired offer guard
- 2c: _create_portal_workspace TOCTOU fix (INSERT + IntegrityError retry)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from sqlalchemy.exc import IntegrityError

from services.recruiting_service import VALID_TRANSITIONS, RecruitingService


# ---------------------------------------------------------------------------
# 2a: VALID_TRANSITIONS — not_selected
# ---------------------------------------------------------------------------

class TestNotSelectedTransitions:
    def test_interview_can_transition_to_not_selected(self):
        assert "not_selected" in VALID_TRANSITIONS["interview"]

    def test_assessment_can_transition_to_not_selected(self):
        assert "not_selected" in VALID_TRANSITIONS["assessment"]

    def test_offer_can_transition_to_not_selected(self):
        assert "not_selected" in VALID_TRANSITIONS["offer"]

    def test_not_selected_can_reopen_to_new(self):
        assert "new" in VALID_TRANSITIONS["not_selected"]

    def test_new_cannot_transition_directly_to_not_selected(self):
        """'new' → 'not_selected' must not be a valid shortcut."""
        assert "not_selected" not in VALID_TRANSITIONS["new"]

    def test_not_selected_is_present_in_transitions(self):
        assert "not_selected" in VALID_TRANSITIONS

    def test_not_selected_only_allows_new(self):
        """not_selected terminal state should only allow re-opening to 'new'."""
        assert VALID_TRANSITIONS["not_selected"] == {"new"}


# ---------------------------------------------------------------------------
# 2a: advance_candidate_stage raises ValueError for invalid transitions
# ---------------------------------------------------------------------------

def _make_service(db=None):
    """Build a RecruitingService with a mock DB session."""
    if db is None:
        db = MagicMock()
    return RecruitingService(db)


class TestAdvanceCandidateStageNotSelected:
    """Ensure the state machine rejects new→not_selected via update_candidate_status."""

    @pytest.mark.asyncio
    async def test_new_to_not_selected_raises_value_error(self):
        db = MagicMock()
        # Simulate candidate currently at 'new'
        candidate_row = MagicMock()
        candidate_row.status = "new"

        execute_result = MagicMock()
        execute_result.fetchone.return_value = candidate_row
        db.execute.return_value = execute_result

        service = _make_service(db)

        with pytest.raises(ValueError, match="not_selected"):
            await service.update_candidate_status(
                candidate_id=1,
                new_status="not_selected",
                updated_by=1,
                organization_id=1,
            )


# ---------------------------------------------------------------------------
# 2b: respond_to_offer — expired offer guard
# ---------------------------------------------------------------------------

class TestRespondToOfferExpiry:
    """respond_to_offer must reject expired offers with a clear ValueError."""

    @pytest.mark.asyncio
    async def test_expired_offer_raises_value_error_with_expired_message(self):
        db = MagicMock()

        # First execute (UPDATE with expiry guard) returns no row → offer expired/responded
        update_result = MagicMock()
        update_result.fetchone.return_value = None

        # Second execute (diagnostic SELECT) returns a row → offer exists but is expired
        expired_check_result = MagicMock()
        expired_row = MagicMock()
        expired_check_result.fetchone.return_value = expired_row

        db.execute.side_effect = [update_result, expired_check_result]

        service = _make_service(db)

        with pytest.raises(ValueError) as exc_info:
            await service.respond_to_offer(
                offer_id=42,
                accepted=True,
                organization_id=1,
            )

        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_missing_offer_raises_value_error_with_not_found_message(self):
        db = MagicMock()

        # UPDATE returns nothing
        update_result = MagicMock()
        update_result.fetchone.return_value = None

        # Diagnostic SELECT also returns nothing → offer truly missing
        not_found_result = MagicMock()
        not_found_result.fetchone.return_value = None

        db.execute.side_effect = [update_result, not_found_result]

        service = _make_service(db)

        with pytest.raises(ValueError) as exc_info:
            await service.respond_to_offer(
                offer_id=99,
                accepted=True,
                organization_id=1,
            )

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_active_offer_accepted_successfully(self):
        db = MagicMock()

        # UPDATE mm_offers succeeds → offer was active and not expired
        offer_row = MagicMock()
        offer_row.candidate_id = 7
        offer_row.offer_number = "OFF-001"

        update_offer_result = MagicMock()
        update_offer_result.fetchone.return_value = offer_row

        # UPDATE mm_candidates (hired)
        update_candidate_result = MagicMock()

        # SELECT mm_candidates (hired_as_user_id lookup)
        candidate_lookup_result = MagicMock()
        candidate_lookup_result.fetchone.return_value = MagicMock(hired_as_user_id=None)

        # INSERT mm_candidate_activities (activity log)
        activity_result = MagicMock()

        # _log_activity makes 2 more calls: INSERT activity + UPDATE last_activity_at
        last_activity_result = MagicMock()

        db.execute.side_effect = [
            update_offer_result,
            update_candidate_result,
            candidate_lookup_result,
            activity_result,
            last_activity_result,
        ]

        service = _make_service(db)

        result = await service.respond_to_offer(
            offer_id=5,
            accepted=True,
            organization_id=1,
        )

        assert result["status"] == "accepted"
        assert result["offer_id"] == 5


# ---------------------------------------------------------------------------
# 2c: _create_portal_workspace — TOCTOU fix
# ---------------------------------------------------------------------------

class TestCreatePortalWorkspaceTOCTOU:
    """_create_portal_workspace should use INSERT+IntegrityError retry, not TOCTOU SELECT."""

    @pytest.mark.asyncio
    async def test_successful_insert_on_first_attempt(self):
        db = MagicMock()
        workspace_row = MagicMock()
        workspace_row.id = 101

        token_result = MagicMock()
        insert_result = MagicMock()
        insert_result.fetchone.return_value = workspace_row

        db.execute.side_effect = [insert_result, token_result]

        service = _make_service(db)
        result = await service._create_portal_workspace(
            candidate_id=1, first_name="Bob", last_name="Jones"
        )

        assert result["workspace_id"] == 101
        assert "slug" in result
        assert "token" in result

    @pytest.mark.asyncio
    async def test_retries_on_integrity_error_and_succeeds(self):
        """On slug collision (IntegrityError) the function retries with a new slug."""
        db = MagicMock()

        workspace_row = MagicMock()
        workspace_row.id = 202
        success_result = MagicMock()
        success_result.fetchone.return_value = workspace_row

        token_result = MagicMock()

        # First call raises IntegrityError (slug collision), second succeeds
        db.execute.side_effect = [
            IntegrityError("slug collision", {}, None),
            success_result,
            token_result,
        ]

        service = _make_service(db)
        result = await service._create_portal_workspace(
            candidate_id=2, first_name="Carol", last_name="White"
        )

        assert result["workspace_id"] == 202
        # rollback must have been called once after the IntegrityError
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_runtime_error_after_10_failures(self):
        """After 10 consecutive IntegrityErrors the function raises RuntimeError."""
        db = MagicMock()
        db.execute.side_effect = IntegrityError("persistent collision", {}, None)

        service = _make_service(db)

        with pytest.raises(RuntimeError, match="10 attempts"):
            await service._create_portal_workspace(
                candidate_id=3, first_name="Dave", last_name="Brown"
            )

        assert db.rollback.call_count == 10

    @pytest.mark.asyncio
    async def test_no_select_before_insert(self):
        """The old TOCTOU pattern did a SELECT before INSERT — verify it's gone."""
        db = MagicMock()
        workspace_row = MagicMock()
        workspace_row.id = 303
        success_result = MagicMock()
        success_result.fetchone.return_value = workspace_row

        token_result = MagicMock()
        db.execute.side_effect = [success_result, token_result]

        service = _make_service(db)
        await service._create_portal_workspace(
            candidate_id=4, first_name="Eve", last_name="Green"
        )

        # Check that no SELECT-only query was issued before the INSERT
        calls = db.execute.call_args_list
        first_sql = str(calls[0][0][0])  # first positional arg of first call
        assert "SELECT" not in first_sql.upper() or "RETURNING" in first_sql.upper(), (
            "Expected INSERT as first DB call, not a pre-flight SELECT"
        )
