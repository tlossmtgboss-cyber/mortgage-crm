"""
Test Notification Action Routes

Verifies the push-notification quick-action endpoints:
- POST /api/v1/loans/{loan_id}/rate-lock/extend
- POST /api/v1/smart-docs/delivery/send-reminder

These endpoints are called from iOS push notification actions and the
frontend notificationActions.js handler.
"""

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from database.enums import RateLockStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _override_require_auth(db_session, mock_user):
    """
    Override the router-level ``require_auth`` dependency so that
    requests without a real Bearer token are still admitted during
    tests.  The notification-action router uses
    ``dependencies=[Depends(require_auth)]`` which checks for an
    HTTPBearer credential *before* calling get_current_user_flexible.
    Without this override the TestClient would always receive 401.
    """
    from main import app
    from routes.auth_deps import require_auth

    async def _no_op_auth(**kwargs):
        return mock_user

    app.dependency_overrides[require_auth] = _no_op_auth
    yield
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
def _make_loan(db_session):
    """
    Factory that inserts a real Loan row into the test DB and returns it.
    Accepts keyword overrides for any column.
    """
    from database.models.lead_loan import Loan

    def _create(**overrides):
        defaults = dict(
            organization_id=1,
            user_id=1,
            borrower_name="Jane Doe",
            loan_amount=400000,
            rate_lock_status=RateLockStatus.LOCKED,
            lock_expiration_date=datetime.now(timezone.utc) + timedelta(days=10),
            lock_term_days=30,
            rate_lock_history=[],
        )
        defaults.update(overrides)
        loan = Loan(**defaults)
        db_session.add(loan)
        db_session.flush()
        return loan

    return _create


# =========================================================================
# Rate-lock extend  — auth & error cases
# =========================================================================


@pytest.mark.unit
class TestRateLockExtendAuth:
    """Requests without authentication must be rejected."""

    def test_rate_lock_extend_requires_auth(self, client: TestClient):
        """401 or 403 when no Bearer token is supplied."""
        response = client.post("/api/v1/loans/999/rate-lock/extend")
        assert response.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {response.status_code}: "
            f"{response.text}"
        )


@pytest.mark.unit
class TestRateLockExtendErrors:
    """Edge-case validation for the extend endpoint."""

    def test_rate_lock_extend_loan_not_found(
        self,
        authenticated_client: TestClient,
        _override_require_auth,
    ):
        """404 when the loan ID does not exist."""
        response = authenticated_client.post(
            "/api/v1/loans/999999/rate-lock/extend",
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "bad_status",
        [
            RateLockStatus.NOT_ELIGIBLE,
            RateLockStatus.ELIGIBLE_NO_LOCK,
            RateLockStatus.FLOAT_MONITORING,
            RateLockStatus.LOCK_EXPIRED,
        ],
    )
    def test_rate_lock_extend_wrong_status(
        self,
        authenticated_client: TestClient,
        _override_require_auth,
        _make_loan,
        bad_status,
    ):
        """400 when the lock status is not LOCKED / LOCK_EXPIRING / LOCK_EXTENDED."""
        loan = _make_loan(rate_lock_status=bad_status)
        response = authenticated_client.post(
            f"/api/v1/loans/{loan.id}/rate-lock/extend",
        )
        assert response.status_code == 400
        body = response.json()
        assert "cannot extend" in body["detail"].lower()


# =========================================================================
# Rate-lock extend  — success path
# =========================================================================


@pytest.mark.unit
class TestRateLockExtendSuccess:
    """Happy-path tests for extending a rate lock."""

    # NOTE: The endpoint already wraps the RateLockIntelligenceEngine import
    # in try/except and falls back to a 15-day extension when the engine is
    # unavailable.  No patching is needed for the default behaviour.

    @pytest.mark.parametrize(
        "initial_status",
        [
            RateLockStatus.LOCKED,
            RateLockStatus.LOCK_EXPIRING,
            RateLockStatus.LOCK_EXTENDED,
        ],
    )
    def test_rate_lock_extend_success(
        self,
        authenticated_client: TestClient,
        _override_require_auth,
        _make_loan,
        initial_status,
    ):
        """
        Extending a lock with a valid status returns the expected
        response shape: {success, loan_id, extension_days,
        new_expiration, message}.
        """
        loan = _make_loan(rate_lock_status=initial_status)
        response = authenticated_client.post(
            f"/api/v1/loans/{loan.id}/rate-lock/extend",
        )
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["success"] is True
        assert body["loan_id"] == loan.id
        assert body["extension_days"] == 15  # default fallback
        assert "new_expiration" in body
        assert "message" in body

    def test_rate_lock_extend_updates_history(
        self,
        authenticated_client: TestClient,
        _override_require_auth,
        _make_loan,
        db_session,
    ):
        """
        After extension the loan's rate_lock_history must contain a new
        entry with action ``"extend"`` and correct metadata.
        """
        old_exp = datetime.now(timezone.utc) + timedelta(days=5)
        loan = _make_loan(
            rate_lock_status=RateLockStatus.LOCKED,
            lock_expiration_date=old_exp,
            lock_term_days=30,
            rate_lock_history=[],
        )
        original_id = loan.id

        response = authenticated_client.post(
            f"/api/v1/loans/{original_id}/rate-lock/extend",
        )
        assert response.status_code == 200

        # Re-fetch from DB to see the committed state
        from database.models.lead_loan import Loan

        refreshed = db_session.get(Loan, original_id)
        history = refreshed.rate_lock_history
        assert isinstance(history, list)
        assert len(history) == 1

        entry = history[0]
        assert entry["action"] == "extend"
        assert entry["extension_days"] == 15
        assert entry["source"] == "notification_action"
        assert "timestamp" in entry
        assert "old_expiration" in entry
        assert "new_expiration" in entry

        # Status should now be LOCK_EXTENDED
        assert refreshed.rate_lock_status == RateLockStatus.LOCK_EXTENDED

        # lock_term_days should have increased by 15
        assert refreshed.lock_term_days == 45  # 30 + 15


# =========================================================================
# Doc reminder  — auth & basic validation
# =========================================================================


@pytest.mark.unit
class TestDocReminderAuth:
    """Requests without authentication must be rejected."""

    def test_doc_reminder_requires_auth(self, client: TestClient):
        """401 or 403 when no Bearer token is supplied."""
        response = client.post(
            "/api/v1/smart-docs/delivery/send-reminder",
            json={"loan_id": 1},
        )
        assert response.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {response.status_code}: "
            f"{response.text}"
        )


@pytest.mark.unit
class TestDocReminderAcceptsRequest:
    """Verify the endpoint accepts a well-formed reminder request."""

    def test_doc_reminder_accepts_request(
        self,
        authenticated_client: TestClient,
        _override_require_auth,
    ):
        """
        A valid reminder body returns a DocReminderResponse (success may
        be True or False depending on whether the delivery module is
        available, but the endpoint itself must not error).
        """
        payload = {
            "loan_id": 42,
            "channels": ["email"],
            "document_types": ["pay_stub", "w2"],
        }
        response = authenticated_client.post(
            "/api/v1/smart-docs/delivery/send-reminder",
            json=payload,
        )
        # The endpoint should return 200 even if the underlying delivery
        # service is unavailable (it returns success=False in that case).
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "success" in body
        assert body["loan_id"] == 42
