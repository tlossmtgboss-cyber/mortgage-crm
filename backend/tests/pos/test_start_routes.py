"""Tests for POS start / email verification endpoints.

Covers:
- POST /pos/start  (OTP generation, dedup, org resolution)
- POST /pos/verify (OTP verification, lockout, expiry, workspace creation)
- POST /pos/resend (cooldown, code regeneration)
- POST /pos/login  (anti-enumeration, trusted devices)
- POST /pos/check-token (token validation)
- IP rate limiting
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from db import Base
from database import get_db
from routes.pos.start import (
    POSVerification,
    POSTrustedDevice,
    _hash_code,
    _ip_tracker,
    _mask_email,
    router as start_router,
)

# ── Test engine (session-scoped, SQLite in-memory) ──────────────────

_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def _start_engine():
    """Session-scoped engine with all tables the start routes need."""
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        # organizations (referenced by _resolve_organization_id)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                slug VARCHAR,
                domain VARCHAR,
                settings TEXT DEFAULT '{}',
                is_active BOOLEAN DEFAULT 1,
                subscription_tier VARCHAR DEFAULT 'lead_management',
                sso_enforced BOOLEAN DEFAULT 0,
                mfa_required BOOLEAN DEFAULT 0,
                timezone VARCHAR(50) DEFAULT 'America/Chicago',
                booking_slug VARCHAR,
                booking_logo_url TEXT,
                booking_primary_color VARCHAR(7) DEFAULT '#1a73e8',
                booking_accent_color VARCHAR(7) DEFAULT '#34a853',
                booking_tagline VARCHAR(200),
                booking_welcome_message TEXT,
                booking_custom_css TEXT,
                booking_cover_image_url TEXT,
                booking_show_testimonials BOOLEAN DEFAULT 0,
                booking_testimonials TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # users (referenced by _resolve_organization_id for lo_slug)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR NOT NULL UNIQUE,
                hashed_password VARCHAR NOT NULL DEFAULT '',
                first_name VARCHAR,
                last_name VARCHAR,
                role VARCHAR DEFAULT 'loan_officer',
                permission_role VARCHAR DEFAULT 'sales',
                branch_id INTEGER,
                organization_id INTEGER REFERENCES organizations(id),
                manager_id INTEGER,
                is_active BOOLEAN DEFAULT 1,
                slug VARCHAR UNIQUE,
                phone VARCHAR,
                nmls_number VARCHAR,
                business_address VARCHAR,
                current_role VARCHAR,
                business_hours TEXT,
                email_verified BOOLEAN DEFAULT 0,
                onboarding_completed BOOLEAN DEFAULT 0,
                user_metadata TEXT,
                email_verified_at TIMESTAMP,
                phone_verified_at TIMESTAMP,
                briefing_enabled BOOLEAN DEFAULT 1,
                briefing_hour INTEGER DEFAULT 7,
                briefing_preferences TEXT,
                company_logo_url TEXT,
                headshot_url TEXT,
                title TEXT,
                team_name TEXT,
                nmls_id VARCHAR,
                timezone VARCHAR DEFAULT 'America/Chicago',
                last_activity_at TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                last_failed_login_at TIMESTAMP,
                mfa_secret VARCHAR,
                mfa_enabled BOOLEAN DEFAULT 0,
                mfa_backup_codes TEXT,
                mfa_enabled_at TIMESTAMP,
                sso_provider VARCHAR,
                sso_subject_id VARCHAR,
                password_changed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # pos_verifications
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR UNIQUE NOT NULL,
                phone VARCHAR NOT NULL,
                phone_raw VARCHAR NOT NULL DEFAULT '',
                code_hash VARCHAR NOT NULL,
                first_name VARCHAR NOT NULL DEFAULT '',
                last_name VARCHAR NOT NULL DEFAULT '',
                email VARCHAR NOT NULL DEFAULT '',
                organization_id INTEGER,
                flow_type VARCHAR NOT NULL DEFAULT 'signup',
                contact_id INTEGER,
                attempts INTEGER DEFAULT 0,
                ip_address VARCHAR,
                consent_at TIMESTAMP,
                last_resend_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_pos_verifications_session_id
            ON pos_verifications (session_id)
        """))
        # pos_trusted_devices
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_trusted_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                ip_address VARCHAR NOT NULL,
                device_token VARCHAR NOT NULL DEFAULT '',
                organization_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_pos_trusted_devices_contact_ip
            ON pos_trusted_devices (contact_id, ip_address)
        """))
        # purl_workspaces (created by verify flow)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                slug VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'lead',
                display_name VARCHAR(500) NOT NULL,
                source VARCHAR(255),
                owner_user_id INTEGER,
                lead_at TIMESTAMP,
                application_at TIMESTAMP,
                active_loan_at TIMESTAMP,
                closing_at TIMESTAMP,
                post_close_at TIMESTAMP,
                meta_data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # purl_contacts (created by verify flow, queried by login)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id),
                contact_type VARCHAR(50) NOT NULL,
                first_name VARCHAR(255) NOT NULL,
                last_name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(50),
                auth_user_id INTEGER,
                auth_provider VARCHAR(50),
                meta_data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # purl_access_tokens (created by PURLTokenService)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_access_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                token_hash VARCHAR(255) NOT NULL UNIQUE,
                token_prefix VARCHAR(50) NOT NULL,
                scope VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                contact_id INTEGER,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                revoked_at TIMESTAMP,
                revoked_by INTEGER,
                revoked_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        """))
        # purl_events_outbox (used by PURLTokenService._emit_event)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purl_events_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                event_key VARCHAR(100) NOT NULL,
                workspace_id INTEGER,
                loan_id INTEGER,
                payload TEXT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 5,
                locked_at TIMESTAMP,
                locked_by VARCHAR(255),
                processed_duration_ms INTEGER,
                error_message TEXT,
                scheduled_for TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_start_engine) -> Generator[Session, None, None]:
    """Transactional session that rolls back after each test."""
    connection = _start_engine.connect()
    transaction = connection.begin()
    _SessionLocal = sessionmaker(bind=connection)
    session = _SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state between tests."""
    import routes.pos.start as start_mod
    # Reset IP rate limiter
    start_mod._ip_tracker.clear()
    # Reset table-ensured flag so _ensure_table is a no-op
    # (we already created tables above)
    start_mod._table_ensured = True
    yield
    start_mod._ip_tracker.clear()


@pytest.fixture
def default_org(db_session: Session) -> int:
    """Insert a default organization and return its id."""
    db_session.execute(text(
        "INSERT INTO organizations (id, name, slug, is_active) "
        "VALUES (1, 'Test Org', 'test-org', 1)"
    ))
    db_session.flush()
    return 1


@pytest.fixture
def app(db_session: Session, default_org: int) -> FastAPI:
    """Minimal FastAPI app with the start router and DB override."""
    test_app = FastAPI()
    test_app.include_router(start_router)

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = _override_db
    return test_app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# ── Helpers ──────────────────────────────────────────────────────────

def _start_payload(
    email: str = "alice@example.com",
    first_name: str = "Alice",
    last_name: str = "Anderson",
    phone: str = "555-1234",
    lo_slug: str | None = None,
) -> dict:
    d = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
    }
    if lo_slug is not None:
        d["lo_slug"] = lo_slug
    return d


def _create_verification(
    db: Session,
    *,
    session_id: str = "pos_sess_test123",
    email: str = "alice@example.com",
    code: str = "123456",
    org_id: int = 1,
    created_at: datetime | None = None,
    verified_at: datetime | None = None,
    attempts: int = 0,
    last_resend_at: datetime | None = None,
    flow_type: str = "signup",
    contact_id: int | None = None,
) -> POSVerification:
    now = created_at or datetime.now(timezone.utc)
    v = POSVerification(
        session_id=session_id,
        phone="555-1234",
        phone_raw="555-1234",
        code_hash=_hash_code(code),
        first_name="Alice",
        last_name="Anderson",
        email=email,
        organization_id=org_id,
        flow_type=flow_type,
        contact_id=contact_id,
        attempts=attempts,
        ip_address="testclient",
        consent_at=now,
        created_at=now,
        verified_at=verified_at,
        last_resend_at=last_resend_at,
    )
    db.add(v)
    db.flush()
    return v


def _create_contact(
    db: Session,
    *,
    email: str = "alice@example.com",
    org_id: int = 1,
    workspace_id: int | None = None,
    first_name: str = "Alice",
    last_name: str = "Anderson",
) -> int:
    """Insert a PURLContact (and workspace if needed) and return the contact id."""
    if workspace_id is None:
        db.execute(text(
            "INSERT INTO purl_workspaces (organization_id, slug, status, display_name, source) "
            "VALUES (:org, :slug, 'application', :name, 'test')"
        ), {"org": org_id, "slug": f"ws-{email}", "name": f"{first_name} {last_name}"})
        db.flush()
        row = db.execute(text("SELECT last_insert_rowid()")).scalar()
        workspace_id = row

    db.execute(text(
        "INSERT INTO purl_contacts (organization_id, workspace_id, contact_type, "
        "first_name, last_name, email, phone) "
        "VALUES (:org, :ws, 'borrower', :fn, :ln, :email, '555-1234')"
    ), {"org": org_id, "ws": workspace_id, "fn": first_name, "ln": last_name, "email": email})
    db.flush()
    contact_id = db.execute(text("SELECT last_insert_rowid()")).scalar()
    return contact_id


# =====================================================================
# Priority 1: Authentication Flow
# =====================================================================


class TestStart:
    """POST /api/v1/pos/start"""

    @patch("routes.pos.start._send_verification_email")
    def test_start_valid_email_returns_session(self, mock_email, client: TestClient):
        resp = client.post("/api/v1/pos/start", json=_start_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"].startswith("pos_sess_")
        assert "@" in body["email_masked"]
        assert body["expires_at"]  # ISO string present
        assert "sent" in body["message"].lower()
        mock_email.assert_called_once()
        # Verify the email was sent to the right address
        assert mock_email.call_args[0][0] == "alice@example.com"

    @patch("routes.pos.start._send_verification_email")
    def test_start_masks_email(self, mock_email, client: TestClient):
        resp = client.post("/api/v1/pos/start", json=_start_payload(email="bob@test.com"))
        body = resp.json()
        # "bob" -> "b***b@test.com"
        assert body["email_masked"] == "b***b@test.com"

    def test_start_invalid_email_returns_422(self, client: TestClient):
        resp = client.post("/api/v1/pos/start", json=_start_payload(email="not-an-email"))
        assert resp.status_code == 422

    def test_start_missing_first_name_returns_422(self, client: TestClient):
        payload = _start_payload()
        payload["first_name"] = ""
        resp = client.post("/api/v1/pos/start", json=payload)
        assert resp.status_code == 422

    def test_start_missing_last_name_returns_422(self, client: TestClient):
        payload = _start_payload()
        payload["last_name"] = ""
        resp = client.post("/api/v1/pos/start", json=payload)
        assert resp.status_code == 422

    @patch("routes.pos.start._send_verification_email")
    def test_start_dedup_within_5_minutes(self, mock_email, client: TestClient):
        """Two starts with same email within 5 min reuse the same session."""
        r1 = client.post("/api/v1/pos/start", json=_start_payload())
        assert r1.status_code == 200
        sid1 = r1.json()["session_id"]

        r2 = client.post("/api/v1/pos/start", json=_start_payload())
        assert r2.status_code == 200
        sid2 = r2.json()["session_id"]

        assert sid1 == sid2
        # Email should only be sent once (first call); second reuses existing
        assert mock_email.call_count == 1

    @patch("routes.pos.start._send_verification_email")
    def test_start_no_active_org_returns_400(self, mock_email, client: TestClient, db_session: Session):
        """When no active organization exists, return 400."""
        # Deactivate the default org
        db_session.execute(text("UPDATE organizations SET is_active = 0 WHERE id = 1"))
        db_session.flush()
        resp = client.post("/api/v1/pos/start", json=_start_payload())
        assert resp.status_code == 400
        assert "organization" in resp.json()["detail"].lower()


class TestVerify:
    """POST /api/v1/pos/verify"""

    @patch("routes.pos.start._send_verification_email")
    def test_verify_correct_code_creates_workspace(self, mock_email, client: TestClient, db_session: Session):
        """Correct OTP returns 201, token, and workspace slug."""
        code = "654321"
        _create_verification(db_session, session_id="pos_sess_v1", code=code)

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_v1",
            "code": code,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["token"]  # non-empty token
        assert body["workspace_slug"]
        assert "app.perenniaai.com" in body["redirect_url"]
        assert body["borrower_name"] == "Alice"

    @patch("routes.pos.start._send_verification_email")
    def test_verify_wrong_code_returns_401(self, mock_email, client: TestClient, db_session: Session):
        _create_verification(db_session, session_id="pos_sess_w1", code="111111")

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_w1",
            "code": "999999",
        })
        assert resp.status_code == 401
        assert "incorrect" in resp.json()["detail"].lower()
        assert "4 attempt" in resp.json()["detail"].lower()

    @patch("routes.pos.start._send_verification_email")
    def test_verify_decrements_attempts(self, mock_email, client: TestClient, db_session: Session):
        """Each wrong attempt decreases remaining attempts."""
        _create_verification(db_session, session_id="pos_sess_dec", code="111111")

        for i in range(3):
            resp = client.post("/api/v1/pos/verify", json={
                "session_id": "pos_sess_dec",
                "code": "000000",
            })
            assert resp.status_code == 401

        # After 3 wrong: 5 - 3 = 2 remaining
        body = resp.json()
        assert "2 attempt" in body["detail"].lower()

    @patch("routes.pos.start._send_verification_email")
    def test_verify_lockout_after_5_attempts(self, mock_email, client: TestClient, db_session: Session):
        """After 5 wrong codes, the session is locked."""
        _create_verification(db_session, session_id="pos_sess_lock", code="111111", attempts=5)

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_lock",
            "code": "111111",  # even correct code should be rejected
        })
        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"].lower()

    @patch("routes.pos.start._send_verification_email")
    def test_verify_expired_code_returns_410(self, mock_email, client: TestClient, db_session: Session):
        """Code older than 10 minutes is rejected."""
        old_time = datetime.now(timezone.utc) - timedelta(minutes=11)
        _create_verification(
            db_session, session_id="pos_sess_exp", code="111111",
            created_at=old_time,
        )

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_exp",
            "code": "111111",
        })
        assert resp.status_code == 410
        assert "expired" in resp.json()["detail"].lower()

    def test_verify_invalid_session_returns_404(self, client: TestClient):
        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_nonexistent",
            "code": "123456",
        })
        assert resp.status_code == 404

    @patch("routes.pos.start._send_verification_email")
    def test_verify_already_verified_returns_400(self, mock_email, client: TestClient, db_session: Session):
        _create_verification(
            db_session, session_id="pos_sess_used", code="111111",
            verified_at=datetime.now(timezone.utc),
        )

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_used",
            "code": "111111",
        })
        assert resp.status_code == 400
        assert "already been used" in resp.json()["detail"].lower()

    def test_verify_non_digit_code_returns_422(self, client: TestClient):
        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_x",
            "code": "abcdef",
        })
        assert resp.status_code == 422

    def test_verify_short_code_returns_422(self, client: TestClient):
        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_x",
            "code": "123",
        })
        assert resp.status_code == 422

    @patch("routes.pos.start._send_verification_email")
    def test_verify_remember_device_sets_cookie(self, mock_email, client: TestClient, db_session: Session):
        """remember_device=True sets a pos_device_token cookie."""
        code = "654321"
        _create_verification(db_session, session_id="pos_sess_dev", code=code)

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_dev",
            "code": code,
            "remember_device": True,
        })
        assert resp.status_code == 201
        # Cookie should be set
        assert "pos_device_token" in resp.cookies

    @patch("routes.pos.start._send_verification_email")
    def test_verify_login_flow_uses_existing_contact(self, mock_email, client: TestClient, db_session: Session):
        """Login flow (flow_type=login) uses existing contact/workspace."""
        contact_id = _create_contact(db_session, email="returning@example.com")
        # Get the workspace_id for the contact
        ws_id = db_session.execute(text(
            "SELECT workspace_id FROM purl_contacts WHERE id = :cid"
        ), {"cid": contact_id}).scalar()

        code = "654321"
        _create_verification(
            db_session, session_id="pos_sess_login",
            email="returning@example.com", code=code,
            flow_type="login", contact_id=contact_id,
        )

        resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_login",
            "code": code,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["borrower_name"] == "Alice"
        # Should use existing workspace slug, not generate new one
        assert body["workspace_slug"] == f"ws-returning@example.com"


class TestResend:
    """POST /api/v1/pos/resend"""

    @patch("routes.pos.start._send_verification_email")
    def test_resend_after_cooldown_succeeds(self, mock_email, client: TestClient, db_session: Session):
        """Resend works when cooldown has elapsed."""
        old_resend = datetime.now(timezone.utc) - timedelta(seconds=61)
        _create_verification(
            db_session, session_id="pos_sess_rs1",
            last_resend_at=old_resend,
        )

        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_rs1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "sent" in body["message"].lower()
        assert body["cooldown_seconds"] == 60
        mock_email.assert_called_once()

    @patch("routes.pos.start._send_verification_email")
    def test_resend_within_cooldown_returns_429(self, mock_email, client: TestClient, db_session: Session):
        """Resend within 60s cooldown is rejected."""
        recent_resend = datetime.now(timezone.utc) - timedelta(seconds=10)
        _create_verification(
            db_session, session_id="pos_sess_rs2",
            last_resend_at=recent_resend,
        )

        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_rs2"})
        assert resp.status_code == 429
        assert "wait" in resp.json()["detail"].lower()
        mock_email.assert_not_called()

    @patch("routes.pos.start._send_verification_email")
    def test_resend_resets_attempts_and_code(self, mock_email, client: TestClient, db_session: Session):
        """Resend generates a new code and resets attempt counter."""
        v = _create_verification(
            db_session, session_id="pos_sess_rs3", code="111111", attempts=3,
        )
        old_hash = v.code_hash

        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_rs3"})
        assert resp.status_code == 200

        db_session.refresh(v)
        assert v.attempts == 0
        assert v.code_hash != old_hash  # new code generated

    def test_resend_invalid_session_returns_404(self, client: TestClient):
        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_ghost"})
        assert resp.status_code == 404

    @patch("routes.pos.start._send_verification_email")
    def test_resend_already_verified_returns_400(self, mock_email, client: TestClient, db_session: Session):
        _create_verification(
            db_session, session_id="pos_sess_rs_done",
            verified_at=datetime.now(timezone.utc),
        )

        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_rs_done"})
        assert resp.status_code == 400
        assert "verified" in resp.json()["detail"].lower()

    @patch("routes.pos.start._send_verification_email")
    def test_resend_first_time_no_cooldown(self, mock_email, client: TestClient, db_session: Session):
        """First resend (last_resend_at=None) should succeed."""
        _create_verification(
            db_session, session_id="pos_sess_rs_first",
            last_resend_at=None,
        )

        resp = client.post("/api/v1/pos/resend", json={"session_id": "pos_sess_rs_first"})
        assert resp.status_code == 200
        mock_email.assert_called_once()


# =====================================================================
# Priority 2: Security Properties
# =====================================================================


class TestLogin:
    """POST /api/v1/pos/login — anti-enumeration behavior"""

    @patch("routes.pos.start.time.sleep")  # skip the timing jitter
    @patch("routes.pos.start._send_verification_email")
    def test_login_nonexistent_email_returns_200_generic(
        self, mock_email, mock_sleep, client: TestClient
    ):
        """Nonexistent email gets 200 with generic message (no 404)."""
        resp = client.post("/api/v1/pos/login", json={"email": "nobody@example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert "if an account exists" in body["message"].lower()
        # Must NOT send an email for nonexistent accounts
        mock_email.assert_not_called()

    @patch("routes.pos.start._send_verification_email")
    def test_login_existing_email_returns_200_generic(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Existing email gets 200 with same generic message shape."""
        _create_contact(db_session, email="exists@example.com")

        resp = client.post("/api/v1/pos/login", json={"email": "exists@example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert "if an account exists" in body["message"].lower()
        assert body["session_id"].startswith("pos_sess_")
        mock_email.assert_called_once()

    @patch("routes.pos.start.time.sleep")
    @patch("routes.pos.start._send_verification_email")
    def test_login_same_response_shape_both_paths(
        self, mock_email, mock_sleep, client: TestClient, db_session: Session
    ):
        """Both existing and nonexistent email responses have identical keys."""
        _create_contact(db_session, email="real@example.com")

        r_exists = client.post("/api/v1/pos/login", json={"email": "real@example.com"})
        r_missing = client.post("/api/v1/pos/login", json={"email": "fake@example.com"})

        assert set(r_exists.json().keys()) == set(r_missing.json().keys())

    @patch("routes.pos.start._send_verification_email")
    def test_login_trusted_device_skips_otp(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Login with matching device cookie + IP returns token directly."""
        contact_id = _create_contact(db_session, email="trusted@example.com")

        device_token = "abc123devicetoken"
        db_session.execute(text(
            "INSERT INTO pos_trusted_devices "
            "(contact_id, ip_address, device_token, organization_id, expires_at) "
            "VALUES (:cid, :ip, :dt, 1, :exp)"
        ), {
            "cid": contact_id,
            "ip": "testclient",
            "dt": device_token,
            "exp": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        })
        db_session.flush()

        resp = client.post(
            "/api/v1/pos/login",
            json={"email": "trusted@example.com"},
            cookies={"pos_device_token": device_token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trusted_device"] is True
        assert body["token"]  # non-empty token
        assert body["borrower_name"] == "Alice"
        # Should NOT send email for trusted device
        mock_email.assert_not_called()

    @patch("routes.pos.start._send_verification_email")
    def test_login_expired_trusted_device_sends_otp(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Expired device token falls through to OTP flow."""
        contact_id = _create_contact(db_session, email="expired-dev@example.com")

        device_token = "expiredtoken123"
        db_session.execute(text(
            "INSERT INTO pos_trusted_devices "
            "(contact_id, ip_address, device_token, organization_id, expires_at) "
            "VALUES (:cid, :ip, :dt, 1, :exp)"
        ), {
            "cid": contact_id,
            "ip": "testclient",
            "dt": device_token,
            "exp": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        })
        db_session.flush()

        resp = client.post(
            "/api/v1/pos/login",
            json={"email": "expired-dev@example.com"},
            cookies={"pos_device_token": device_token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trusted_device"] is False
        assert body["session_id"].startswith("pos_sess_")
        mock_email.assert_called_once()

    @patch("routes.pos.start._send_verification_email")
    def test_login_wrong_device_token_sends_otp(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Wrong device cookie falls through to OTP flow."""
        contact_id = _create_contact(db_session, email="wrongdev@example.com")

        db_session.execute(text(
            "INSERT INTO pos_trusted_devices "
            "(contact_id, ip_address, device_token, organization_id, expires_at) "
            "VALUES (:cid, :ip, :dt, 1, :exp)"
        ), {
            "cid": contact_id,
            "ip": "testclient",
            "dt": "real_token",
            "exp": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        })
        db_session.flush()

        resp = client.post(
            "/api/v1/pos/login",
            json={"email": "wrongdev@example.com"},
            cookies={"pos_device_token": "wrong_token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["trusted_device"] is False
        mock_email.assert_called_once()

    @patch("routes.pos.start._send_verification_email")
    def test_login_dedup_within_5_minutes(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Two logins for same email within 5 min reuse the same session."""
        contact_id = _create_contact(db_session, email="dedup@example.com")
        _create_verification(
            db_session, session_id="pos_sess_login_dedup",
            email="dedup@example.com", flow_type="login",
            contact_id=contact_id,
        )

        resp = client.post("/api/v1/pos/login", json={"email": "dedup@example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "pos_sess_login_dedup"
        mock_email.assert_not_called()


class TestCheckToken:
    """POST /api/v1/pos/check-token"""

    def test_check_token_no_auth_header_returns_invalid(self, client: TestClient):
        resp = client.post("/api/v1/pos/check-token")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_check_token_malformed_header_returns_invalid(self, client: TestClient):
        resp = client.post(
            "/api/v1/pos/check-token",
            headers={"authorization": "Basic notabearer"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_check_token_invalid_token_returns_invalid(self, client: TestClient):
        resp = client.post(
            "/api/v1/pos/check-token",
            headers={"authorization": "Bearer purl_live_invalidtokenthatdoesnotexist"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    @patch("routes.pos.start._send_verification_email")
    def test_check_token_valid_token_returns_valid(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """Full flow: start -> verify -> check-token with the resulting token."""
        code = "654321"
        _create_verification(db_session, session_id="pos_sess_tok", code=code)

        verify_resp = client.post("/api/v1/pos/verify", json={
            "session_id": "pos_sess_tok",
            "code": code,
        })
        assert verify_resp.status_code == 201
        token = verify_resp.json()["token"]

        check_resp = client.post(
            "/api/v1/pos/check-token",
            headers={"authorization": f"Bearer {token}"},
        )
        assert check_resp.status_code == 200
        body = check_resp.json()
        assert body["valid"] is True
        assert body["borrower_name"] == "Alice"


# =====================================================================
# Priority 3: Rate Limiting
# =====================================================================


class TestIPRateLimit:
    """IP-based rate limiting (5 starts per 10 min window)."""

    @patch("routes.pos.start._send_verification_email")
    def test_rate_limit_blocks_after_limit(self, mock_email, client: TestClient):
        """6th request from same IP within window returns 429."""
        for i in range(5):
            resp = client.post(
                "/api/v1/pos/start",
                json=_start_payload(email=f"user{i}@example.com"),
            )
            assert resp.status_code == 200, f"Request {i+1} should succeed"

        # 6th request should be blocked
        resp = client.post(
            "/api/v1/pos/start",
            json=_start_payload(email="onemore@example.com"),
        )
        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"].lower()

    @patch("routes.pos.start._send_verification_email")
    def test_login_also_rate_limited(self, mock_email, client: TestClient):
        """Login endpoint shares the same IP rate limiter."""
        # Use up 5 requests via /login
        for i in range(5):
            client.post(
                "/api/v1/pos/login",
                json={"email": f"user{i}@example.com"},
            )

        # 6th from same IP should be blocked
        resp = client.post(
            "/api/v1/pos/login",
            json={"email": "extra@example.com"},
        )
        assert resp.status_code == 429


# =====================================================================
# Priority 4: Helper / Edge Cases
# =====================================================================


class TestMaskEmail:
    """Unit tests for _mask_email helper."""

    def test_normal_email(self):
        assert _mask_email("alice@example.com") == "a***e@example.com"

    def test_single_char_local(self):
        assert _mask_email("a@example.com") == "a***@example.com"

    def test_two_char_local(self):
        assert _mask_email("ab@example.com") == "a***b@example.com"

    def test_no_at_sign(self):
        assert _mask_email("noatsign") == "***"


class TestHashCode:
    """Unit tests for _hash_code (HMAC-SHA256)."""

    def test_deterministic(self):
        assert _hash_code("123456") == _hash_code("123456")

    def test_different_codes_different_hashes(self):
        assert _hash_code("123456") != _hash_code("654321")

    def test_returns_hex_string(self):
        h = _hash_code("123456")
        assert len(h) == 64  # SHA-256 hex length
        int(h, 16)  # should not raise


class TestOrgResolution:
    """Organization resolution edge cases via /start."""

    @patch("routes.pos.start._send_verification_email")
    def test_lo_slug_resolves_to_org(
        self, mock_email, client: TestClient, db_session: Session
    ):
        """lo_slug pointing to a valid user resolves that user's org."""
        # Create an LO user with a slug
        db_session.execute(text(
            "INSERT INTO users (id, email, hashed_password, organization_id, slug) "
            "VALUES (10, 'lo@test.com', 'x', 1, 'tim-loss')"
        ))
        db_session.flush()

        resp = client.post(
            "/api/v1/pos/start",
            json=_start_payload(lo_slug="tim-loss"),
        )
        assert resp.status_code == 200

    @patch("routes.pos.start._send_verification_email")
    def test_invalid_lo_slug_falls_back_to_default_org(
        self, mock_email, client: TestClient
    ):
        """Unknown lo_slug falls back to the first active org."""
        resp = client.post(
            "/api/v1/pos/start",
            json=_start_payload(lo_slug="nonexistent-slug"),
        )
        assert resp.status_code == 200  # should fall back, not fail
