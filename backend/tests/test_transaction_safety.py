"""
Transaction Safety Tests for Smart Docs V2

Validates that financial operations use proper transaction boundaries:
- atomic_operation commits on success, rolls back on failure
- optimistic_lock detects concurrent modifications
- select_for_update prevents race conditions
- Envelope creation is all-or-nothing
- Deposit sourcing is serialized via SELECT FOR UPDATE
- Campaign creation + event recording are atomic
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy session with commit/rollback tracking."""
    db = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.execute = MagicMock()

    # Support begin_nested for savepoint tests
    nested = MagicMock()
    nested.commit = MagicMock()
    nested.rollback = MagicMock()
    db.begin_nested = MagicMock(return_value=nested)
    db._test_nested = nested

    return db


@pytest.fixture
def mock_model_class():
    """Create a mock SQLAlchemy model class with id and version columns."""
    model = MagicMock()
    model.__name__ = "TestModel"
    model.id = MagicMock()
    model.version = MagicMock()
    return model


# =============================================================================
# atomic_operation tests
# =============================================================================

class TestAtomicOperation:
    """Test the atomic_operation context manager."""

    def test_commits_on_success(self, mock_db):
        """atomic_operation should commit on clean exit."""
        from services.smart_docs.db_transaction import atomic_operation

        with atomic_operation(mock_db):
            mock_db.add("some_record")

        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_rolls_back_on_exception(self, mock_db):
        """atomic_operation should rollback on any exception."""
        from services.smart_docs.db_transaction import atomic_operation

        with pytest.raises(ValueError, match="test error"):
            with atomic_operation(mock_db):
                mock_db.add("some_record")
                raise ValueError("test error")

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_re_raises_exception_after_rollback(self, mock_db):
        """The original exception should propagate after rollback."""
        from services.smart_docs.db_transaction import atomic_operation

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError):
            with atomic_operation(mock_db):
                raise CustomError("should propagate")

        mock_db.rollback.assert_called_once()

    def test_nested_savepoint_commits(self, mock_db):
        """Nested atomic_operation should use savepoints and commit."""
        from services.smart_docs.db_transaction import atomic_operation

        with atomic_operation(mock_db, nested=True):
            mock_db.add("inner_record")

        mock_db.begin_nested.assert_called_once()
        mock_db._test_nested.commit.assert_called_once()
        mock_db._test_nested.rollback.assert_not_called()

    def test_nested_savepoint_rolls_back_on_error(self, mock_db):
        """Nested savepoint should rollback on error without affecting outer."""
        from services.smart_docs.db_transaction import atomic_operation

        with pytest.raises(RuntimeError):
            with atomic_operation(mock_db, nested=True):
                raise RuntimeError("inner failure")

        mock_db._test_nested.rollback.assert_called_once()
        mock_db._test_nested.commit.assert_not_called()
        # Outer session should NOT be rolled back
        mock_db.rollback.assert_not_called()


# =============================================================================
# optimistic_lock tests
# =============================================================================

class TestOptimisticLock:
    """Test the optimistic_lock function."""

    def test_passes_when_version_matches(self, mock_db, mock_model_class):
        """Should return entity when version matches."""
        from services.smart_docs.db_transaction import optimistic_lock

        entity = MagicMock()
        entity.version = 5
        mock_db.query.return_value.filter.return_value.first.return_value = entity

        result = optimistic_lock(mock_db, mock_model_class, entity_id=1, expected_version=5)

        assert result is entity

    def test_raises_conflict_when_version_differs(self, mock_db, mock_model_class):
        """Should raise ConflictError when version does not match."""
        from services.smart_docs.db_transaction import optimistic_lock, ConflictError

        entity = MagicMock()
        entity.version = 7
        mock_db.query.return_value.filter.return_value.first.return_value = entity

        with pytest.raises(ConflictError) as exc_info:
            optimistic_lock(mock_db, mock_model_class, entity_id=1, expected_version=5)

        assert exc_info.value.expected_version == 5
        assert exc_info.value.actual_version == 7
        assert "TestModel" in str(exc_info.value)

    def test_raises_conflict_when_entity_not_found(self, mock_db, mock_model_class):
        """Should raise ConflictError when entity does not exist."""
        from services.smart_docs.db_transaction import optimistic_lock, ConflictError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ConflictError) as exc_info:
            optimistic_lock(mock_db, mock_model_class, entity_id=999, expected_version=1)

        assert exc_info.value.actual_version is None

    def test_skips_check_when_no_version_column(self, mock_db, mock_model_class):
        """Should warn and pass when entity has no version attribute."""
        from services.smart_docs.db_transaction import optimistic_lock

        entity = MagicMock(spec=[])  # no version attribute
        del entity.version  # ensure hasattr returns False
        mock_db.query.return_value.filter.return_value.first.return_value = entity

        # getattr with default None
        result = optimistic_lock(mock_db, mock_model_class, entity_id=1, expected_version=1)
        assert result is entity


# =============================================================================
# select_for_update tests
# =============================================================================

class TestSelectForUpdate:
    """Test the select_for_update function."""

    def test_returns_locked_entity(self, mock_db, mock_model_class):
        """Should return the entity with FOR UPDATE lock."""
        from services.smart_docs.db_transaction import select_for_update

        entity = MagicMock()
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = entity

        result = select_for_update(mock_db, mock_model_class, entity_id=1)

        assert result is entity
        mock_db.query.return_value.filter.return_value.with_for_update.assert_called_once_with(
            nowait=False, skip_locked=False
        )

    def test_returns_none_for_missing_entity(self, mock_db, mock_model_class):
        """Should return None when entity does not exist."""
        from services.smart_docs.db_transaction import select_for_update

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        result = select_for_update(mock_db, mock_model_class, entity_id=999)

        assert result is None

    def test_nowait_flag(self, mock_db, mock_model_class):
        """Should pass nowait=True to with_for_update."""
        from services.smart_docs.db_transaction import select_for_update

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        select_for_update(mock_db, mock_model_class, entity_id=1, nowait=True)

        mock_db.query.return_value.filter.return_value.with_for_update.assert_called_once_with(
            nowait=True, skip_locked=False
        )

    def test_skip_locked_flag(self, mock_db, mock_model_class):
        """Should pass skip_locked=True to with_for_update."""
        from services.smart_docs.db_transaction import select_for_update

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        select_for_update(mock_db, mock_model_class, entity_id=1, skip_locked=True)

        mock_db.query.return_value.filter.return_value.with_for_update.assert_called_once_with(
            nowait=False, skip_locked=True
        )


# =============================================================================
# @transactional decorator tests
# =============================================================================

class TestTransactionalDecorator:
    """Test the @transactional decorator."""

    def test_commits_on_success(self, mock_db):
        """Decorated function should commit session on success."""
        from services.smart_docs.db_transaction import transactional

        @transactional
        def do_work(db):
            db.add("record")
            return {"ok": True}

        result = do_work(mock_db)

        assert result == {"ok": True}
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_rolls_back_on_exception(self, mock_db):
        """Decorated function should rollback session on exception."""
        from services.smart_docs.db_transaction import transactional

        @transactional
        def do_work(db):
            db.add("record")
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError, match="fail"):
            do_work(mock_db)

        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_works_with_self_parameter(self, mock_db):
        """Decorated method should find db in positional args after self."""
        from services.smart_docs.db_transaction import transactional

        class MyService:
            @transactional
            def do_work(self, db):
                db.add("record")
                return "done"

        svc = MyService()
        result = svc.do_work(mock_db)

        assert result == "done"
        mock_db.commit.assert_called_once()

    def test_works_with_db_kwarg(self, mock_db):
        """Decorated function should find db as keyword argument."""
        from services.smart_docs.db_transaction import transactional

        @transactional
        def do_work(name, db=None):
            db.add(name)
            return name

        result = do_work("test", db=mock_db)

        assert result == "test"
        mock_db.commit.assert_called_once()

    def test_raises_type_error_without_db(self):
        """Should raise TypeError if no Session argument found."""
        from services.smart_docs.db_transaction import transactional

        @transactional
        def do_work(name):
            return name

        with pytest.raises(TypeError, match="could not find a Session"):
            do_work("test")


# =============================================================================
# Envelope creation atomicity tests
# =============================================================================

class TestEnvelopeCreationAtomicity:
    """Test that envelope creation is all-or-nothing."""

    @patch("services.smart_docs.esignature_envelope_service.get_smart_docs_s3_service")
    def test_rolls_back_on_recipient_creation_failure(self, mock_s3_factory, mock_db):
        """If recipient creation fails, envelope should also be rolled back."""
        from services.smart_docs.esignature_envelope_service import (
            ESignatureEnvelopeService,
            EnvelopeCreateRequest,
        )

        # Setup
        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = {"success": True, "content": b"pdf_bytes"}
        mock_s3_factory.return_value = mock_s3

        mock_crypto = MagicMock()
        mock_crypto.generate_envelope_uuid.return_value = "test-uuid"
        mock_crypto.hash_document.return_value = "sha256hash"

        # Make add succeed for envelope but fail for first recipient
        call_count = [0]
        def add_side_effect(record):
            call_count[0] += 1
            if call_count[0] >= 2:  # fail on second add (first recipient)
                raise RuntimeError("DB constraint violation")
        mock_db.add.side_effect = add_side_effect

        service = ESignatureEnvelopeService.__new__(ESignatureEnvelopeService)
        service.db = mock_db
        service.crypto = mock_crypto
        service._frontend_base_url = "https://test.com"
        service._api_base_url = "https://api.test.com"

        request = EnvelopeCreateRequest(
            loan_id=1,
            organization_id=1,
            created_by_user_id=1,
            title="Test",
            description=None,
            document_storage_key="test/doc.pdf",
            recipients=[{"name": "Signer", "email": "s@test.com"}],
            fields=[],
        )

        with pytest.raises(RuntimeError, match="DB constraint violation"):
            service.create_envelope(request)

        # The atomic_operation should have called rollback
        mock_db.rollback.assert_called()
        # commit should NOT have been called
        mock_db.commit.assert_not_called()


# =============================================================================
# Deposit sourcing serialization tests
# =============================================================================

class TestDepositSourcingSerialization:
    """Test that deposit sourcing uses SELECT FOR UPDATE."""

    def test_source_deposit_uses_for_update(self, mock_db):
        """The source_large_deposit endpoint should lock the loan row."""
        # We test the route function directly by examining the SQL it generates.
        # The key assertion is that SELECT ... FOR UPDATE is used before
        # reading the cached analysis.
        from routes.smart_docs_bank_analysis_routes import source_large_deposit

        # The function is async, so we verify the pattern exists in the code
        import inspect
        source_code = inspect.getsource(source_large_deposit)

        assert "FOR UPDATE" in source_code, (
            "source_large_deposit must use SELECT ... FOR UPDATE to prevent "
            "concurrent modification of bank_analysis_result"
        )
        assert "atomic_operation" in source_code, (
            "source_large_deposit must use atomic_operation for commit/rollback safety"
        )


# =============================================================================
# Call intel extractor transaction tests
# =============================================================================

class TestCallIntelExtractorTransactions:
    """Test that call intel extractor uses proper transactions."""

    def test_save_analysis_uses_atomic_operation(self, mock_db):
        """save_analysis should use atomic_operation."""
        import inspect
        from services.smart_docs.call_intel_extractor import CallIntelDocumentExtractor

        source = inspect.getsource(CallIntelDocumentExtractor.save_analysis)
        assert "atomic_operation" in source, (
            "save_analysis must use atomic_operation context manager"
        )

    def test_auto_create_requests_uses_atomic_operation(self, mock_db):
        """auto_create_requests should use atomic_operation."""
        import inspect
        from services.smart_docs.call_intel_extractor import CallIntelDocumentExtractor

        source = inspect.getsource(CallIntelDocumentExtractor.auto_create_requests)
        assert "atomic_operation" in source, (
            "auto_create_requests must use atomic_operation context manager"
        )
        # Should NOT have bare db.commit() outside the context manager
        # Filter out the comment lines to check for bare commits
        lines = [
            line.strip() for line in source.split("\n")
            if line.strip() and not line.strip().startswith("#")
            and not line.strip().startswith("\"\"\"")
        ]
        bare_commits = [
            line for line in lines
            if "self.db.commit()" in line
        ]
        assert len(bare_commits) == 0, (
            "auto_create_requests should not have bare db.commit() calls "
            "outside atomic_operation"
        )


# =============================================================================
# Followup automation transaction tests
# =============================================================================

class TestFollowupAutomationTransactions:
    """Test that followup service uses proper transactions."""

    def test_create_campaign_is_atomic(self):
        """create_campaign should use atomic_operation."""
        import inspect
        from services.smart_docs.followup_automation_service import FollowupAutomationService

        source = inspect.getsource(FollowupAutomationService.create_campaign)
        assert "atomic_operation" in source, (
            "create_campaign must use atomic_operation to make campaign + event atomic"
        )

    def test_execute_campaign_step_is_atomic(self):
        """execute_campaign_step should commit event + advancement atomically."""
        import inspect
        from services.smart_docs.followup_automation_service import FollowupAutomationService

        source = inspect.getsource(FollowupAutomationService.execute_campaign_step)
        assert "atomic_operation" in source, (
            "execute_campaign_step must use atomic_operation for event + advancement"
        )

    def test_handle_document_uploaded_is_atomic(self):
        """handle_document_uploaded should commit all campaign updates atomically."""
        import inspect
        from services.smart_docs.followup_automation_service import FollowupAutomationService

        source = inspect.getsource(FollowupAutomationService.handle_document_uploaded)
        assert "atomic_operation" in source, (
            "handle_document_uploaded must use atomic_operation"
        )

    def test_handle_borrower_response_is_atomic(self):
        """handle_borrower_response should commit atomically."""
        import inspect
        from services.smart_docs.followup_automation_service import FollowupAutomationService

        source = inspect.getsource(FollowupAutomationService.handle_borrower_response)
        assert "atomic_operation" in source, (
            "handle_borrower_response must use atomic_operation"
        )


# =============================================================================
# E-signature transaction tests
# =============================================================================

class TestESignatureTransactions:
    """Test that e-signature service uses proper transactions."""

    def test_create_envelope_is_atomic(self):
        """create_envelope should use atomic_operation."""
        import inspect
        from services.smart_docs.esignature_envelope_service import ESignatureEnvelopeService

        source = inspect.getsource(ESignatureEnvelopeService.create_envelope)
        assert "atomic_operation" in source, (
            "create_envelope must use atomic_operation for all-or-nothing creation"
        )
        # Should not have bare db.commit() outside atomic_operation
        lines = [
            line.strip() for line in source.split("\n")
            if line.strip()
            and not line.strip().startswith("#")
            and not line.strip().startswith("\"\"\"")
        ]
        bare_commits = [line for line in lines if "self.db.commit()" in line]
        assert len(bare_commits) == 0, (
            "create_envelope should not have bare db.commit() outside atomic_operation"
        )

    def test_submit_signature_uses_select_for_update(self):
        """submit_signature should use SELECT FOR UPDATE on recipient."""
        import inspect
        from services.smart_docs.esignature_envelope_service import ESignatureEnvelopeService

        source = inspect.getsource(ESignatureEnvelopeService.submit_signature)
        assert "select_for_update" in source, (
            "submit_signature must use select_for_update to prevent concurrent signing"
        )
        assert "atomic_operation" in source, (
            "submit_signature must use atomic_operation for the signing transaction"
        )

    def test_complete_envelope_verifies_all_signed(self):
        """complete_envelope should verify all signers have status SIGNED."""
        import inspect
        from services.smart_docs.esignature_envelope_service import ESignatureEnvelopeService

        source = inspect.getsource(ESignatureEnvelopeService.complete_envelope)
        assert "unsigned" in source or "SIGNED" in source, (
            "complete_envelope must verify all recipients have signed"
        )
        assert "Cannot complete envelope" in source, (
            "complete_envelope must raise error if unsigned recipients remain"
        )


# =============================================================================
# ConflictError tests
# =============================================================================

class TestConflictError:
    """Test the ConflictError exception."""

    def test_conflict_error_attributes(self):
        """ConflictError should carry entity and version information."""
        from services.smart_docs.db_transaction import ConflictError

        error = ConflictError(
            entity_type="Loan",
            entity_id=42,
            expected_version=3,
            actual_version=5,
        )

        assert error.entity_type == "Loan"
        assert error.entity_id == 42
        assert error.expected_version == 3
        assert error.actual_version == 5
        assert "Loan" in str(error)
        assert "42" in str(error)
        assert error.code == "OPTIMISTIC_LOCK_CONFLICT"

    def test_conflict_error_is_perennia_error(self):
        """ConflictError should be a PerenniaError subclass."""
        from services.smart_docs.db_transaction import ConflictError
        from exceptions import PerenniaError

        error = ConflictError(
            entity_type="Test",
            entity_id=1,
            expected_version=1,
            actual_version=2,
        )

        assert isinstance(error, PerenniaError)
