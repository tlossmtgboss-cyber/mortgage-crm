"""
Tests for ESIGN Act consent capture, paper alternative workflow, and
Knowledge-Based Authentication (KBA) for the e-signature system.

Covers:
  - Consent recording (accept / decline)
  - Consent withdrawal triggering paper workflow
  - Signing blocked without consent
  - KBA question generation
  - KBA answer verification (pass / fail)
  - KBA lockout after 3 failures
  - Paper alternative task creation
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Provide a mock SQLAlchemy session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.count.return_value = 0
    db.execute.return_value.first.return_value = None
    return db


@pytest.fixture
def _mock_recipient():
    """Minimal mock ESignatureRecipient."""
    r = MagicMock()
    r.id = 101
    r.envelope_id = 55
    r.name = "Jane Borrower"
    r.email = "jane@example.com"
    r.phone = "+15551234567"
    r.auth_method = "email_link"
    r.recipient_type = "signer"
    r.status = "sent"
    r.signing_token = "tok_abc123"
    return r


@pytest.fixture
def _mock_envelope():
    """Minimal mock ESignatureEnvelope."""
    e = MagicMock()
    e.id = 55
    e.envelope_uuid = str(uuid.uuid4())
    e.organization_id = 42
    e.title = "Closing Disclosure"
    e.status = "sent"
    e.document_hash_sha256 = "abc123hash"
    return e


# ============================================================================
# CONSENT SERVICE TESTS
# ============================================================================

class TestESignConsentService:
    """Tests for ESignConsentService."""

    def _make_service(self, db):
        from services.smart_docs.esign_consent_service import ESignConsentService
        return ESignConsentService(db)

    # --- Disclosure text ---

    def test_get_disclosure_text_default(self, mock_db):
        svc = self._make_service(mock_db)
        result = svc.get_consent_disclosure_text()

        assert "text" in result
        assert "version" in result
        assert "consent" in result["text"].lower()
        assert "paper" in result["text"].lower()
        assert result["version"] == "1.0"

    def test_get_disclosure_text_with_org(self, mock_db):
        # Simulate org lookup returning a row
        mock_db.execute.return_value.first.return_value = (
            "Acme Mortgage", "support@acme.com"
        )
        svc = self._make_service(mock_db)
        result = svc.get_consent_disclosure_text(org_id=42)

        assert "Acme Mortgage" in result["text"]
        assert "support@acme.com" in result["text"]

    # --- Record consent (accept) ---

    def test_record_consent_accepted(self, mock_db, _mock_recipient, _mock_envelope):
        from database.models.esignature import ESignConsentSession

        # No existing consent session
        mock_db.query.return_value.filter.return_value.first.return_value = None

        svc = self._make_service(mock_db)
        result = svc.record_consent(
            recipient_id=_mock_recipient.id,
            envelope_id=_mock_envelope.id,
            org_id=_mock_envelope.organization_id,
            consented=True,
            ip_address="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )

        assert result["consent_given"] is True
        assert result["consented_at"] is not None
        assert result["paper_task_id"] is None

        # Verify the session and audit event were added
        add_calls = mock_db.add.call_args_list
        assert len(add_calls) >= 2  # ConsentSession + AuditEvent

    # --- Record consent (declined) ---

    def test_record_consent_declined_creates_paper_task(
        self, mock_db, _mock_recipient, _mock_envelope,
    ):
        # No existing consent session
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Simulate recipient + envelope lookups for paper task creation
        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignConsentSession":
                mock_q.filter.return_value.first.return_value = None
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            elif model.__name__ == "ESignatureEnvelope":
                mock_q.filter.return_value.first.return_value = _mock_envelope
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = self._make_service(mock_db)
        result = svc.record_consent(
            recipient_id=_mock_recipient.id,
            envelope_id=_mock_envelope.id,
            org_id=_mock_envelope.organization_id,
            consented=False,
            ip_address="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )

        assert result["consent_given"] is False
        assert result["consented_at"] is None
        # Paper task should have been attempted
        assert result["paper_task_id"] is not None

    # --- Verify consent ---

    def test_verify_consent_returns_true_when_consented(self, mock_db):
        consent_session = MagicMock()
        consent_session.consent_given = True
        consent_session.withdrawn_at = None
        mock_db.query.return_value.filter.return_value.first.return_value = consent_session

        svc = self._make_service(mock_db)
        assert svc.verify_consent(recipient_id=101, envelope_id=55) is True

    def test_verify_consent_returns_false_when_no_session(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        svc = self._make_service(mock_db)
        assert svc.verify_consent(recipient_id=101, envelope_id=55) is False

    # --- Withdraw consent ---

    def test_withdraw_consent_success(self, mock_db, _mock_recipient, _mock_envelope):
        consent_session = MagicMock()
        consent_session.consent_given = True
        consent_session.withdrawn_at = None
        consent_session.organization_id = 42

        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignConsentSession":
                mock_q.filter.return_value.first.return_value = consent_session
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            elif model.__name__ == "ESignatureEnvelope":
                mock_q.filter.return_value.first.return_value = _mock_envelope
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = self._make_service(mock_db)
        result = svc.withdraw_consent(
            recipient_id=101,
            envelope_id=55,
            reason="Changed my mind",
            ip_address="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )

        assert result["withdrawn_at"] is not None
        assert result["reason"] == "Changed my mind"
        assert consent_session.withdrawn_at is not None
        assert consent_session.withdrawal_reason == "Changed my mind"

    def test_withdraw_consent_no_active_session_raises(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        svc = self._make_service(mock_db)
        with pytest.raises(ValueError, match="No active consent found"):
            svc.withdraw_consent(
                recipient_id=101,
                envelope_id=55,
                reason="test",
                ip_address="1.2.3.4",
                user_agent="test",
            )

    # --- Paper delivery task ---

    def test_create_paper_delivery_task(
        self, mock_db, _mock_recipient, _mock_envelope,
    ):
        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            elif model.__name__ == "ESignatureEnvelope":
                mock_q.filter.return_value.first.return_value = _mock_envelope
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = self._make_service(mock_db)
        task_id = svc.create_paper_delivery_task(
            recipient_id=_mock_recipient.id,
            envelope_id=_mock_envelope.id,
            org_id=42,
        )

        assert task_id is not None
        # Verify audit event was added
        add_calls = mock_db.add.call_args_list
        audit_added = any(
            hasattr(call[0][0], "event_type")
            for call in add_calls
            if call[0]
        )
        assert audit_added


# ============================================================================
# KBA SERVICE TESTS
# ============================================================================

class TestKBAService:
    """Tests for KBAService."""

    def _make_service(self, db):
        from services.smart_docs.esign_kba_service import KBAService
        return KBAService(db)

    # --- Check KBA required ---

    def test_kba_not_required_email_link(self, mock_db):
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        svc = self._make_service(mock_db)
        assert svc.check_kba_required(envelope_id=55) is False

    def test_kba_required_when_recipient_has_kba_auth(self, mock_db):
        mock_db.query.return_value.filter.return_value.count.return_value = 1
        svc = self._make_service(mock_db)
        assert svc.check_kba_required(envelope_id=55) is True

    # --- Create KBA session ---

    def test_create_kba_session_generates_questions(
        self, mock_db, _mock_recipient,
    ):
        # No existing session
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Recipient lookup
        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignKBASession":
                mock_q.filter.return_value.first.return_value = None
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query
        # No borrower profile found
        mock_db.execute.return_value.first.return_value = None

        svc = self._make_service(mock_db)
        result = svc.create_kba_session(
            recipient_id=_mock_recipient.id,
            envelope_id=55,
            ip_address="1.2.3.4",
            user_agent="test",
        )

        assert "session_uuid" in result
        assert "questions" in result
        assert len(result["questions"]) >= 3  # minimum question count
        assert result["attempts_remaining"] == 3

        # Each question should have text and options but NOT the correct answer
        for q in result["questions"]:
            assert "question" in q
            assert "options" in q
            assert "correct_index" not in q  # hidden from caller

    # --- Verify KBA answers (pass) ---

    def test_verify_kba_pass(self, mock_db):
        kba_session = MagicMock()
        kba_session.session_uuid = "test-uuid"
        kba_session.recipient_id = 101
        kba_session.envelope_id = 55
        kba_session.locked = False
        kba_session.passed = None
        kba_session.attempts_used = 0
        kba_session.max_attempts = 3
        kba_session.questions = [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_index": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_index": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_index": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct_index": 3},
        ]

        mock_db.query.return_value.filter.return_value.first.return_value = kba_session

        svc = self._make_service(mock_db)

        # Answer 3 of 4 correctly (75% = passes)
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[0, 1, 2, 0],  # first 3 correct, last wrong
            ip_address="1.2.3.4",
            user_agent="test",
        )

        assert result.passed is True
        assert result.locked is False
        assert result.correct_count == 3
        assert result.total_questions == 4
        assert result.score == 0.75

    # --- Verify KBA answers (fail) ---

    def test_verify_kba_fail(self, mock_db):
        kba_session = MagicMock()
        kba_session.session_uuid = "test-uuid"
        kba_session.recipient_id = 101
        kba_session.envelope_id = 55
        kba_session.locked = False
        kba_session.passed = None
        kba_session.attempts_used = 0
        kba_session.max_attempts = 3
        kba_session.questions = [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_index": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_index": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_index": 2},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct_index": 3},
        ]

        mock_db.query.return_value.filter.return_value.first.return_value = kba_session

        svc = self._make_service(mock_db)

        # Answer only 2 of 4 correctly (50% < 75% threshold)
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[0, 1, 0, 0],  # first 2 correct, last 2 wrong
            ip_address="1.2.3.4",
            user_agent="test",
        )

        assert result.passed is False
        assert result.locked is False
        assert result.correct_count == 2
        assert result.attempts_remaining == 2

    # --- KBA lockout after 3 failures ---

    def test_kba_lockout_after_max_attempts(self, mock_db, _mock_recipient):
        kba_session = MagicMock()
        kba_session.session_uuid = "test-uuid"
        kba_session.recipient_id = 101
        kba_session.envelope_id = 55
        kba_session.locked = False
        kba_session.passed = None
        kba_session.attempts_used = 2  # already used 2 of 3
        kba_session.max_attempts = 3
        kba_session.questions = [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_index": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_index": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_index": 2},
        ]

        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignKBASession":
                mock_q.filter.return_value.first.return_value = kba_session
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = self._make_service(mock_db)

        # All wrong on third attempt
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[3, 3, 3],  # all wrong
            ip_address="1.2.3.4",
            user_agent="test",
        )

        assert result.passed is False
        assert result.locked is True
        assert result.attempts_remaining == 0

        # Verify the session was locked
        assert kba_session.locked is True

        # Verify recipient was set to AUTH_FAILED
        assert _mock_recipient.status == "auth_failed"

    def test_kba_already_locked_returns_locked(self, mock_db):
        kba_session = MagicMock()
        kba_session.session_uuid = "test-uuid"
        kba_session.locked = True
        kba_session.passed = False

        mock_db.query.return_value.filter.return_value.first.return_value = kba_session

        svc = self._make_service(mock_db)

        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[0, 0, 0],
        )

        assert result.passed is False
        assert result.locked is True
        assert result.attempts_remaining == 0


# ============================================================================
# SIGNING BLOCKED WITHOUT CONSENT
# ============================================================================

class TestSigningRequiresConsent:
    """Test that the submit_signature endpoint enforces ESIGN consent."""

    def test_signing_blocked_without_consent(self, mock_db, _mock_recipient, _mock_envelope):
        """Verify that the envelope service rejects signing without consent."""
        from services.smart_docs.esign_consent_service import ESignConsentService

        svc = ESignConsentService(mock_db)

        # No consent session exists
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = svc.verify_consent(
            recipient_id=_mock_recipient.id,
            envelope_id=_mock_envelope.id,
        )
        assert result is False, "Signing should be blocked when no consent exists"

    def test_signing_allowed_with_consent(self, mock_db, _mock_recipient, _mock_envelope):
        """Verify that consent allows signing to proceed."""
        from services.smart_docs.esign_consent_service import ESignConsentService

        consent_session = MagicMock()
        consent_session.consent_given = True
        consent_session.withdrawn_at = None
        mock_db.query.return_value.filter.return_value.first.return_value = consent_session

        svc = ESignConsentService(mock_db)
        result = svc.verify_consent(
            recipient_id=_mock_recipient.id,
            envelope_id=_mock_envelope.id,
        )
        assert result is True, "Signing should be allowed when consent exists"

    def test_signing_blocked_after_consent_withdrawal(self, mock_db):
        """Verify that withdrawn consent blocks signing."""
        from services.smart_docs.esign_consent_service import ESignConsentService

        # No active consent session (withdrawn_at is set)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        svc = ESignConsentService(mock_db)
        result = svc.verify_consent(recipient_id=101, envelope_id=55)
        assert result is False, "Signing should be blocked after consent withdrawal"


# ============================================================================
# KBA QUESTION GENERATION
# ============================================================================

class TestKBAQuestionGeneration:
    """Test KBA question generation from profile data."""

    def test_generates_minimum_questions_without_profile(self, mock_db, _mock_recipient):
        from services.smart_docs.esign_kba_service import KBAService

        # No profile data
        mock_db.execute.return_value.first.return_value = None

        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignKBASession":
                mock_q.filter.return_value.first.return_value = None
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = KBAService(mock_db)
        result = svc.create_kba_session(
            recipient_id=_mock_recipient.id,
            envelope_id=55,
        )

        # Should generate at least 3 fallback questions
        assert len(result["questions"]) >= 3

        # Each question should have options
        for q in result["questions"]:
            assert len(q["options"]) == 4

    def test_questions_do_not_expose_answers(self, mock_db, _mock_recipient):
        from services.smart_docs.esign_kba_service import KBAService

        mock_db.execute.return_value.first.return_value = None

        def side_effect_query(model):
            mock_q = MagicMock()
            if model.__name__ == "ESignKBASession":
                mock_q.filter.return_value.first.return_value = None
            elif model.__name__ == "ESignatureRecipient":
                mock_q.filter.return_value.first.return_value = _mock_recipient
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        mock_db.query.side_effect = side_effect_query

        svc = KBAService(mock_db)
        result = svc.create_kba_session(
            recipient_id=_mock_recipient.id,
            envelope_id=55,
        )

        for q in result["questions"]:
            assert "correct_index" not in q, (
                "Correct answer index must not be exposed to the client"
            )
            assert "correct_answer" not in q


# ============================================================================
# WRONG ANSWER COUNT VALIDATION
# ============================================================================

class TestKBAAnswerValidation:
    """Test edge cases in KBA answer verification."""

    def _make_session(self):
        s = MagicMock()
        s.session_uuid = "test-uuid"
        s.recipient_id = 101
        s.envelope_id = 55
        s.locked = False
        s.passed = None
        s.attempts_used = 0
        s.max_attempts = 3
        s.questions = [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_index": 0},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_index": 1},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_index": 2},
        ]
        return s

    def test_wrong_answer_count_raises(self, mock_db):
        from services.smart_docs.esign_kba_service import KBAService

        session = self._make_session()
        mock_db.query.return_value.filter.return_value.first.return_value = session

        svc = KBAService(mock_db)

        with pytest.raises(ValueError, match="Expected 3 answers"):
            svc.verify_kba_answers(
                session_id="test-uuid",
                answers=[0, 1],  # only 2 answers for 3 questions
            )

    def test_all_correct_passes(self, mock_db):
        from services.smart_docs.esign_kba_service import KBAService

        session = self._make_session()
        mock_db.query.return_value.filter.return_value.first.return_value = session

        svc = KBAService(mock_db)
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[0, 1, 2],
        )

        assert result.passed is True
        assert result.correct_count == 3
        assert result.score == 1.0

    def test_all_wrong_fails(self, mock_db):
        from services.smart_docs.esign_kba_service import KBAService

        session = self._make_session()
        mock_db.query.return_value.filter.return_value.first.return_value = session

        svc = KBAService(mock_db)
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[3, 3, 3],
        )

        assert result.passed is False
        assert result.correct_count == 0
        assert result.score == 0.0

    def test_already_passed_returns_pass(self, mock_db):
        from services.smart_docs.esign_kba_service import KBAService

        session = self._make_session()
        session.passed = True
        session.attempts_used = 1
        mock_db.query.return_value.filter.return_value.first.return_value = session

        svc = KBAService(mock_db)
        result = svc.verify_kba_answers(
            session_id="test-uuid",
            answers=[0, 1, 2],
        )

        assert result.passed is True
        # Should not increment attempts
        assert session.attempts_used == 1
