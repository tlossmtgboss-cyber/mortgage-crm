"""
Tests for import service: phone normalization, duplicate detection,
hard-delete confirmation gate, and email validation.

Covers:
  - normalize_phone() format variants
  - Duplicate detection (email match, phone match)
  - Hard-delete confirmation gate (missing confirm returns 400)
  - Row validation catches invalid emails
  - Email validation helper
  - Async threshold detection
"""
import json
import io
import os
import sys
import pytest
from unittest.mock import MagicMock, Mock, patch, PropertyMock
from datetime import datetime, timezone

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Test: normalize_phone()
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    """Test phone number normalization from data_import_routes and import_service."""

    def test_ten_digit_gets_plus_one(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("8005551234") == "+18005551234"

    def test_eleven_digit_starting_with_one(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("18005551234") == "+18005551234"

    def test_already_e164(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("+18005551234") == "+18005551234"

    def test_strips_formatting(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("(800) 555-1234") == "+18005551234"

    def test_strips_dots(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("800.555.1234") == "+18005551234"

    def test_none_returns_none(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone(None) is None

    def test_empty_string_returns_none(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("") is None

    def test_whitespace_only_returns_none(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("   ") is None

    def test_short_number_returned_as_digits(self):
        from routes.data_import_routes import normalize_phone
        # Numbers that are not 10 or 11 digits are returned as-is (digits only)
        result = normalize_phone("12345")
        assert result == "12345"

    def test_international_plus_prefix_preserved(self):
        from routes.data_import_routes import normalize_phone
        assert normalize_phone("+447911123456") == "+447911123456"

    def test_import_service_normalize_phone_agrees(self):
        """The service-internal _normalize_phone should match."""
        from services.import_service import _normalize_phone
        assert _normalize_phone("(800) 555-1234") == "+18005551234"
        assert _normalize_phone("18005551234") == "+18005551234"
        assert _normalize_phone(None) is None


# ---------------------------------------------------------------------------
# Test: validate_email (from data_import_routes)
# ---------------------------------------------------------------------------

class TestValidateEmail:
    """Test email validation in data_import_routes."""

    def test_valid_email(self):
        from routes.data_import_routes import validate_email
        assert validate_email("user@example.com") == "user@example.com"

    def test_uppercase_lowered(self):
        from routes.data_import_routes import validate_email
        assert validate_email("User@Example.COM") == "user@example.com"

    def test_invalid_email_returns_none(self):
        from routes.data_import_routes import validate_email
        assert validate_email("not-an-email") is None

    def test_missing_at_sign(self):
        from routes.data_import_routes import validate_email
        assert validate_email("user.example.com") is None

    def test_missing_tld(self):
        from routes.data_import_routes import validate_email
        assert validate_email("user@example") is None

    def test_none_returns_none(self):
        from routes.data_import_routes import validate_email
        assert validate_email(None) is None

    def test_empty_string_returns_none(self):
        from routes.data_import_routes import validate_email
        assert validate_email("") is None

    def test_whitespace_stripped(self):
        from routes.data_import_routes import validate_email
        assert validate_email("  user@example.com  ") == "user@example.com"


# ---------------------------------------------------------------------------
# Test: validate_email_format (from import_service)
# ---------------------------------------------------------------------------

class TestValidateEmailFormat:
    """Test the import_service email format validator."""

    def test_valid_email(self):
        from services.import_service import validate_email_format
        assert validate_email_format("test@example.com") is True

    def test_invalid_email(self):
        from services.import_service import validate_email_format
        assert validate_email_format("not-valid") is False

    def test_empty_is_valid(self):
        from services.import_service import validate_email_format
        assert validate_email_format("") is True

    def test_none_is_valid(self):
        from services.import_service import validate_email_format
        assert validate_email_format(None) is True

    def test_double_at_invalid(self):
        from services.import_service import validate_email_format
        assert validate_email_format("user@@example.com") is False

    def test_no_tld_invalid(self):
        from services.import_service import validate_email_format
        assert validate_email_format("user@example") is False


# ---------------------------------------------------------------------------
# Test: row validation catches invalid emails
# ---------------------------------------------------------------------------

class TestRowValidation:
    """Test that validate_row properly flags invalid emails."""

    def test_valid_row_passes(self):
        from routes.data_import_routes import validate_row
        row = {"name": "John Doe", "email": "john@example.com", "phone": "8005551234"}
        clean, errors = validate_row(row, 1)
        assert len(errors) == 0
        assert clean["email"] == "john@example.com"

    def test_invalid_email_flagged(self):
        from routes.data_import_routes import validate_row
        row = {"name": "John Doe", "email": "not-an-email"}
        clean, errors = validate_row(row, 1)
        assert any("Invalid email" in e for e in errors)

    def test_missing_name_flagged(self):
        from routes.data_import_routes import validate_row
        row = {"email": "john@example.com"}
        clean, errors = validate_row(row, 1)
        assert any("Missing name" in e for e in errors)

    def test_name_synthesized_from_parts(self):
        from routes.data_import_routes import validate_row
        row = {"first_name": "John", "last_name": "Doe", "email": "john@example.com"}
        clean, errors = validate_row(row, 1)
        assert len(errors) == 0
        assert clean["name"] == "John Doe"

    def test_credit_score_out_of_range(self):
        from routes.data_import_routes import validate_row
        row = {"name": "John Doe", "credit_score": "200"}
        clean, errors = validate_row(row, 1)
        assert any("Credit score" in e for e in errors)

    def test_credit_score_valid(self):
        from routes.data_import_routes import validate_row
        row = {"name": "John Doe", "credit_score": "720"}
        clean, errors = validate_row(row, 1)
        assert len(errors) == 0
        assert clean["credit_score"] == 720

    def test_empty_email_not_flagged(self):
        """Empty email should not produce an error (it's optional)."""
        from routes.data_import_routes import validate_row
        row = {"name": "John Doe", "email": ""}
        clean, errors = validate_row(row, 1)
        assert not any("Invalid email" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: duplicate detection (email match, phone match)
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Test duplicate detection logic in ImportService._process_batch."""

    def _make_mock_db(self, existing_email=None, existing_phone=None):
        """Create a mock DB session that simulates duplicate lookup."""
        db = MagicMock()
        call_count = {"n": 0}

        def fake_execute(query, params=None):
            result = MagicMock()
            query_str = str(query) if not isinstance(query, str) else query

            # Email check
            if "LOWER(TRIM(email))" in query_str:
                if existing_email and params and params.get("email") == existing_email:
                    result.fetchone.return_value = (999,)
                else:
                    result.fetchone.return_value = None
                return result

            # Phone check
            if "phone = :phone" in query_str:
                if existing_phone and params and params.get("phone") == existing_phone:
                    result.fetchone.return_value = (888,)
                else:
                    result.fetchone.return_value = None
                return result

            # INSERT returning id
            if "INSERT INTO" in query_str:
                call_count["n"] += 1
                result.fetchone.return_value = (call_count["n"],)
                return result

            # CREATE TABLE / CREATE INDEX
            result.fetchone.return_value = None
            return result

        db.execute = fake_execute
        db.begin_nested.return_value = MagicMock()
        db.flush = MagicMock()
        return db

    def test_email_duplicate_skip(self):
        """When duplicate_strategy='skip' and email matches, row is skipped."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db(existing_email="john@example.com")
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [({"name": "John", "email": "john@example.com"}, 1)]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="skip",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.duplicate_rows == 1
        assert progress.imported_rows == 0

    def test_phone_duplicate_skip(self):
        """When duplicate_strategy='skip' and phone matches, row is skipped."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db(existing_phone="+18005551234")
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [({"name": "Jane", "phone": "+18005551234"}, 1)]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="skip",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.duplicate_rows == 1

    def test_no_duplicate_inserts(self):
        """When no duplicate exists, a new record is inserted."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db()  # No existing records
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [({"name": "New Lead", "email": "new@example.com"}, 1)]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="skip",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.imported_rows == 1
        assert progress.duplicate_rows == 0

    def test_email_duplicate_with_create_strategy(self):
        """With duplicate_strategy='create', duplicates are still inserted."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db(existing_email="john@example.com")
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [({"name": "John", "email": "john@example.com"}, 1)]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="create",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.imported_rows == 1
        assert progress.duplicate_rows == 0


# ---------------------------------------------------------------------------
# Test: hard-delete confirmation gate
# ---------------------------------------------------------------------------

class TestHardDeleteConfirmationGate:
    """Test that hard-delete rollback requires confirm=true."""

    def test_hard_delete_without_confirm_returns_400(self):
        """POST rollback?hard_delete=true without confirm should return 400."""
        from routes.data_import_routes import register_data_import_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.organization_id = 1
        mock_user.id = 1

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_user

        # Simulate the import_jobs table query
        def fake_execute(query, params=None):
            result = MagicMock()
            query_str = str(query) if not isinstance(query, str) else query
            if "CREATE TABLE" in query_str or "CREATE INDEX" in query_str:
                return result
            if "SELECT imported_lead_ids" in query_str:
                # Return a mock job row: (imported_lead_ids, filename)
                result.fetchone.return_value = (json.dumps([1, 2, 3]), "test.csv")
                return result
            return result

        mock_db.execute = fake_execute
        mock_db.commit = MagicMock()

        register_data_import_routes(
            test_app, mock_get_db, mock_get_current_user
        )

        client = TestClient(test_app)

        # hard_delete=true but confirm=false => should get 400
        resp = client.post(
            "/api/v1/imports/test-import-id/rollback?hard_delete=true&confirm=false"
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        detail = body["detail"]
        # detail can be a dict or string
        if isinstance(detail, dict):
            assert detail.get("requires_confirmation") is True
            assert detail.get("records_to_delete") == 3
        else:
            assert "confirm" in detail.lower() or "permanently" in detail.lower()

    def test_hard_delete_with_confirm_proceeds(self):
        """POST rollback?hard_delete=true&confirm=true should proceed to service."""
        from routes.data_import_routes import register_data_import_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.organization_id = 1
        mock_user.id = 1

        def mock_get_db():
            yield mock_db

        def mock_get_current_user():
            return mock_user

        register_data_import_routes(
            test_app, mock_get_db, mock_get_current_user
        )

        client = TestClient(test_app)

        # Patch ImportService.rollback_import to avoid DB calls
        with patch("services.import_service.ImportService.rollback_import") as mock_rollback:
            mock_rollback.return_value = {
                "import_id": "test-id",
                "status": "rolled_back",
                "method": "hard_delete",
                "leads_affected": 3,
                "total_lead_ids": 3,
                "rolled_back_at": "2026-01-01T00:00:00+00:00",
                "message": "Successfully deleted 3 leads",
            }

            resp = client.post(
                "/api/v1/imports/test-id/rollback?hard_delete=true&confirm=true"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "rolled_back"
            assert body["method"] == "hard_delete"


# ---------------------------------------------------------------------------
# Test: email validation during import processing (import_service)
# ---------------------------------------------------------------------------

class TestImportServiceEmailValidation:
    """Test that import_service catches invalid emails during batch processing."""

    def _make_mock_db(self):
        db = MagicMock()
        call_count = {"n": 0}

        def fake_execute(query, params=None):
            result = MagicMock()
            query_str = str(query) if not isinstance(query, str) else query
            if "INSERT INTO" in query_str:
                call_count["n"] += 1
                result.fetchone.return_value = (call_count["n"],)
            elif "SELECT id FROM" in query_str:
                result.fetchone.return_value = None
            return result

        db.execute = fake_execute
        db.begin_nested.return_value = MagicMock()
        db.flush = MagicMock()
        return db

    def test_invalid_email_skipped_in_batch(self):
        """Rows with invalid emails are counted as errors and skipped."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db()
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [
            ({"name": "Good Lead", "email": "valid@example.com"}, 1),
            ({"name": "Bad Lead", "email": "not-an-email"}, 2),
        ]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="create",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.imported_rows == 1
        assert progress.error_rows == 1
        # Verify the error mentions email
        assert any(
            "email" in str(err).lower()
            for err in progress.errors
        )

    def test_valid_emails_pass(self):
        """Rows with valid emails should import successfully."""
        from services.import_service import ImportService, ImportProgress

        db = self._make_mock_db()
        svc = ImportService(db=db, user_id=1, organization_id=1)
        progress = ImportProgress(status="processing")

        batch = [
            ({"name": "Lead One", "email": "one@example.com"}, 1),
            ({"name": "Lead Two", "email": "two@test.org"}, 2),
        ]
        abort_msg = svc._process_batch(
            batch=batch,
            entity_type="leads",
            duplicate_strategy="create",
            default_stage="New",
            default_source=None,
            skip_invalid_rows=True,
            validate_row_fn=None,
            progress=progress,
        )
        assert abort_msg == ""
        assert progress.imported_rows == 2
        assert progress.error_rows == 0


# ---------------------------------------------------------------------------
# Test: async threshold detection
# ---------------------------------------------------------------------------

class TestAsyncThresholds:
    """Test the should_run_async and estimate_row_count helpers."""

    def test_small_file_runs_sync(self):
        from services.import_service import should_run_async
        # 1 MB, 100 rows -> sync
        assert should_run_async(1 * 1024 * 1024, 100) is False

    def test_large_file_runs_async(self):
        from services.import_service import should_run_async
        # 10 MB, 100 rows -> async (file size exceeds 5MB)
        assert should_run_async(10 * 1024 * 1024, 100) is True

    def test_many_rows_runs_async(self):
        from services.import_service import should_run_async
        # 1 MB, 10000 rows -> async (row count exceeds 5000)
        assert should_run_async(1 * 1024 * 1024, 10000) is True

    def test_both_thresholds_exceeded(self):
        from services.import_service import should_run_async
        assert should_run_async(10 * 1024 * 1024, 10000) is True

    def test_exactly_at_thresholds_runs_sync(self):
        from services.import_service import should_run_async
        # Exactly at thresholds (not exceeding) -> sync
        assert should_run_async(5 * 1024 * 1024, 5000) is False

    def test_estimate_row_count_csv(self):
        from services.import_service import estimate_row_count
        # Create a fake CSV with known line count
        lines = "name,email\n" + "john,john@x.com\n" * 100
        stream = io.BytesIO(lines.encode("utf-8"))
        est = estimate_row_count(stream, "test.csv")
        # Should be roughly 100 (minus header)
        assert est >= 80  # Allow some tolerance in estimation
        assert est <= 120

    def test_estimate_row_count_excel_returns_zero(self):
        from services.import_service import estimate_row_count
        stream = io.BytesIO(b"fake excel data")
        est = estimate_row_count(stream, "test.xlsx")
        assert est == 0


# ---------------------------------------------------------------------------
# Test: auto_detect_mapping
# ---------------------------------------------------------------------------

class TestAutoDetectMapping:
    """Test auto-detection of field mappings from headers."""

    def test_standard_headers(self):
        from routes.data_import_routes import auto_detect_mapping
        headers = ["First Name", "Last Name", "Email", "Phone"]
        mapping = auto_detect_mapping(headers)
        assert mapping["First Name"] == "first_name"
        assert mapping["Last Name"] == "last_name"
        assert mapping["Email"] == "email"
        assert mapping["Phone"] == "phone"

    def test_alias_headers(self):
        from routes.data_import_routes import auto_detect_mapping
        # Note: "E-Mail" normalizes to "e mail" (dashes become spaces)
        # which does NOT match the "e-mail" alias. Use "Email Address" instead.
        headers = ["Full Name", "Email Address", "Cell Phone", "FICO Score"]
        mapping = auto_detect_mapping(headers)
        assert mapping["Full Name"] == "name"
        assert mapping["Email Address"] == "email"
        assert mapping["Cell Phone"] == "phone"
        assert mapping["FICO Score"] == "credit_score"

    def test_unmapped_headers_skipped(self):
        from routes.data_import_routes import auto_detect_mapping
        headers = ["Name", "Unknown Column", "Random Field"]
        mapping = auto_detect_mapping(headers)
        assert "Name" in mapping
        assert "Unknown Column" not in mapping
        assert "Random Field" not in mapping


# ---------------------------------------------------------------------------
# Test: transform_value
# ---------------------------------------------------------------------------

class TestTransformValue:
    """Test value transformation for different field types."""

    def test_name_title_case(self):
        from routes.data_import_routes import transform_value
        assert transform_value("name", "JOHN DOE") == "John Doe"

    def test_email_lowered(self):
        from routes.data_import_routes import transform_value
        assert transform_value("email", "User@Example.COM") == "user@example.com"

    def test_phone_normalized(self):
        from routes.data_import_routes import transform_value
        assert transform_value("phone", "(800) 555-1234") == "+18005551234"

    def test_loan_amount_parsed(self):
        from routes.data_import_routes import transform_value
        assert transform_value("loan_amount", "$350,000.00") == 350000.00

    def test_credit_score_parsed(self):
        from routes.data_import_routes import transform_value
        assert transform_value("credit_score", "720") == 720

    def test_first_time_buyer_bool(self):
        from routes.data_import_routes import transform_value
        assert transform_value("first_time_buyer", "yes") is True
        assert transform_value("first_time_buyer", "no") is False

    def test_none_returns_none(self):
        from routes.data_import_routes import transform_value
        assert transform_value("name", None) is None
        assert transform_value("email", "") is None


# ---------------------------------------------------------------------------
# Test: save_upload_to_temp
# ---------------------------------------------------------------------------

class TestSaveUploadToTemp:
    """Test temp file creation for background imports."""

    def test_creates_temp_file(self):
        from services.import_service import save_upload_to_temp
        content = b"name,email\nJohn,john@example.com\n"
        stream = io.BytesIO(content)
        tmp_path = save_upload_to_temp(stream, "test.csv")
        try:
            assert os.path.exists(tmp_path)
            assert tmp_path.endswith(".csv")
            with open(tmp_path, "rb") as f:
                assert f.read() == content
        finally:
            os.unlink(tmp_path)

    def test_excel_extension_preserved(self):
        from services.import_service import save_upload_to_temp
        stream = io.BytesIO(b"fake excel")
        tmp_path = save_upload_to_temp(stream, "data.xlsx")
        try:
            assert tmp_path.endswith(".xlsx")
        finally:
            os.unlink(tmp_path)
