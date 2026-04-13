"""
Tests for routes/mobile_sync_routes.py — Mobile Offline Sync Batch endpoint

Validates operation processing, field allowlisting, conflict resolution,
batch size limits, and error handling.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id=1, org_id=100):
    user = MagicMock()
    user.id = user_id
    user.organization_id = org_id
    return user


# ---------------------------------------------------------------------------
# 1. _parse_client_timestamp
# ---------------------------------------------------------------------------

class TestParseClientTimestamp:
    def test_parses_iso_with_z(self):
        from routes.mobile_sync_routes import _parse_client_timestamp
        result = _parse_client_timestamp("2026-04-13T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2026

    def test_parses_iso_with_offset(self):
        from routes.mobile_sync_routes import _parse_client_timestamp
        result = _parse_client_timestamp("2026-04-13T12:00:00+00:00")
        assert result is not None

    def test_returns_none_for_invalid(self):
        from routes.mobile_sync_routes import _parse_client_timestamp
        assert _parse_client_timestamp("not-a-date") is None
        assert _parse_client_timestamp("") is None

    def test_adds_utc_to_naive_datetime(self):
        from routes.mobile_sync_routes import _parse_client_timestamp
        result = _parse_client_timestamp("2026-04-13T12:00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# 2. _apply_allowed_fields
# ---------------------------------------------------------------------------

class TestApplyAllowedFields:
    def test_filters_to_allowed_keys(self):
        from routes.mobile_sync_routes import _apply_allowed_fields
        data = {"title": "Follow up", "secret": "hack", "status": "pending"}
        allowed = {"title", "status"}
        result = _apply_allowed_fields(data, allowed)
        assert result == {"title": "Follow up", "status": "pending"}

    def test_drops_none_values(self):
        from routes.mobile_sync_routes import _apply_allowed_fields
        data = {"title": "Test", "description": None}
        allowed = {"title", "description"}
        result = _apply_allowed_fields(data, allowed)
        assert result == {"title": "Test"}

    def test_returns_empty_for_no_matches(self):
        from routes.mobile_sync_routes import _apply_allowed_fields
        data = {"secret": "value"}
        allowed = {"title", "status"}
        result = _apply_allowed_fields(data, allowed)
        assert result == {}


# ---------------------------------------------------------------------------
# 3. Operation processors
# ---------------------------------------------------------------------------

class TestProcessCreateTask:
    def test_rejects_missing_title(self):
        from routes.mobile_sync_routes import _process_create_task
        result = _process_create_task(
            data={"description": "no title"},
            client_ts=None,
            user=_make_user(),
            db=MagicMock(),
        )
        assert result.success is False
        assert "title" in result.error_message.lower()

    def test_creates_task_with_valid_data(self):
        from routes.mobile_sync_routes import _process_create_task

        mock_db = MagicMock()
        mock_task_instance = MagicMock()
        mock_task_instance.id = 42

        with patch("database.models.task.Task", return_value=mock_task_instance) as MockTask:
            result = _process_create_task(
                data={"title": "Order appraisal", "priority": "high"},
                client_ts=datetime(2026, 4, 13, tzinfo=timezone.utc),
                user=_make_user(),
                db=mock_db,
            )

            assert result.success is True
            mock_db.add.assert_called_once()

    def test_filters_disallowed_fields(self):
        from routes.mobile_sync_routes import _process_create_task

        mock_db = MagicMock()
        mock_task_instance = MagicMock()
        mock_task_instance.id = 1

        with patch("database.models.task.Task", return_value=mock_task_instance) as MockTask:
            _process_create_task(
                data={
                    "title": "Test",
                    "organization_id": 999,  # Should be filtered
                    "owner_id": 999,  # Should be filtered
                },
                client_ts=None,
                user=_make_user(),
                db=mock_db,
            )

            # organization_id and owner_id should come from user, not data
            call_kwargs = MockTask.call_args.kwargs
            assert call_kwargs["organization_id"] == 100  # From user
            assert call_kwargs["owner_id"] == 1  # From user


class TestProcessUpdateLead:
    def test_rejects_missing_id(self):
        from routes.mobile_sync_routes import _process_update_lead
        result = _process_update_lead(
            data={"name": "Test"},
            client_ts=None,
            user=_make_user(),
            db=MagicMock(),
        )
        assert result.success is False
        assert "id" in result.error_message.lower()

    def test_rejects_not_found_lead(self):
        from routes.mobile_sync_routes import _process_update_lead

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = _process_update_lead(
            data={"id": 999},
            client_ts=None,
            user=_make_user(),
            db=mock_db,
        )
        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_detects_sync_conflict(self):
        from routes.mobile_sync_routes import _process_update_lead

        mock_lead = MagicMock()
        mock_lead.updated_at = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_lead

        # Client timestamp is OLDER than server
        client_ts = datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc)

        result = _process_update_lead(
            data={"id": 1, "stage": "Hot"},
            client_ts=client_ts,
            user=_make_user(),
            db=mock_db,
        )
        assert result.success is False
        assert "newer" in result.error_message.lower()


class TestProcessUpdateLoan:
    def test_rejects_missing_id(self):
        from routes.mobile_sync_routes import _process_update_loan
        result = _process_update_loan(
            data={"stage": "PROCESSING"},
            client_ts=None,
            user=_make_user(),
            db=MagicMock(),
        )
        assert result.success is False

    def test_filters_disallowed_loan_fields(self):
        from routes.mobile_sync_routes import _LOAN_UPDATE_FIELDS
        # organization_id should NOT be in the allowed set
        assert "organization_id" not in _LOAN_UPDATE_FIELDS
        assert "owner_id" not in _LOAN_UPDATE_FIELDS


class TestProcessLogCall:
    def test_rejects_empty_call_log(self):
        from routes.mobile_sync_routes import _process_log_call
        result = _process_log_call(
            data={},
            client_ts=None,
            user=_make_user(),
            db=MagicMock(),
        )
        assert result.success is False
        assert "contact" in result.error_message.lower()


class TestProcessAddNote:
    def test_rejects_empty_content(self):
        from routes.mobile_sync_routes import _process_add_note
        result = _process_add_note(
            data={"lead_id": 1},
            client_ts=None,
            user=_make_user(),
            db=MagicMock(),
        )
        assert result.success is False
        assert "content" in result.error_message.lower()


# ---------------------------------------------------------------------------
# 4. Batch endpoint validation
# ---------------------------------------------------------------------------

class TestSyncBatchValidation:
    def test_supported_operations_list(self):
        from routes.mobile_sync_routes import SUPPORTED_OPERATIONS
        expected = {"create_task", "update_lead", "update_loan", "log_call", "add_note"}
        assert SUPPORTED_OPERATIONS == expected

    def test_max_batch_size_is_reasonable(self):
        from routes.mobile_sync_routes import MAX_BATCH_SIZE
        assert MAX_BATCH_SIZE == 100

    def test_field_allowlists_exist(self):
        from routes.mobile_sync_routes import (
            _TASK_CREATE_FIELDS,
            _LEAD_UPDATE_FIELDS,
            _LOAN_UPDATE_FIELDS,
            _CALL_LOG_FIELDS,
            _NOTE_FIELDS,
        )
        # Each allowlist should have at least 2 fields
        assert len(_TASK_CREATE_FIELDS) >= 2
        assert len(_LEAD_UPDATE_FIELDS) >= 2
        assert len(_LOAN_UPDATE_FIELDS) >= 2
        assert len(_CALL_LOG_FIELDS) >= 2
        assert len(_NOTE_FIELDS) >= 2

        # Security-critical: server-managed fields must be excluded
        for fields in [_TASK_CREATE_FIELDS, _LEAD_UPDATE_FIELDS, _LOAN_UPDATE_FIELDS]:
            assert "organization_id" not in fields
            assert "owner_id" not in fields
            assert "created_by" not in fields


# ---------------------------------------------------------------------------
# 5. Pydantic models
# ---------------------------------------------------------------------------

class TestSyncModels:
    def test_sync_operation_requires_all_fields(self):
        from routes.mobile_sync_routes import SyncOperation
        op = SyncOperation(
            type="create_task",
            data={"title": "Test"},
            client_id="uuid-123",
            timestamp="2026-04-13T12:00:00Z",
        )
        assert op.type == "create_task"
        assert op.client_id == "uuid-123"

    def test_operation_result_shape(self):
        from routes.mobile_sync_routes import OperationResult
        result = OperationResult(
            client_id="uuid-123",
            success=True,
            server_id=42,
        )
        assert result.success is True
        assert result.server_id == 42
        assert result.error_code is None

    def test_sync_batch_response_shape(self):
        from routes.mobile_sync_routes import SyncBatchResponse, OperationResult
        response = SyncBatchResponse(
            processed=3,
            succeeded=2,
            failed=1,
            results=[
                OperationResult(client_id="a", success=True, server_id=1),
                OperationResult(client_id="b", success=True, server_id=2),
                OperationResult(client_id="c", success=False, error_code="VALIDATION_ERROR", error_message="bad"),
            ],
        )
        assert response.processed == 3
        assert response.succeeded == 2
        assert response.failed == 1
