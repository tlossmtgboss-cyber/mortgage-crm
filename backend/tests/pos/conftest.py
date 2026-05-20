"""Shared fixtures for POS tests.

Converted from async to sync to match Perennia's sync SQLAlchemy + FastAPI
TestClient pattern (see backend/tests/conftest.py).
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import String, Text, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Project-local imports.
from db import Base
from database import get_db
from database.models.pos import POSApplication, POSStatus
from middleware.purl_auth import (
    PURLAuthContext,
    TokenScope,
    check_purl_rate_limit,
    require_purl_token,
    require_purl_write_scope,
)

from routes.pos.application import router as application_router
from routes.pos.calendar import router as calendar_router
from routes.pos.ai_qa import router as ai_qa_router
from services.pos.ai_qa_service import AIQAService
from services.pos._scheduler_bridge import (
    BridgeBooking,
    BridgeCancellation,
    BridgeHold,
    BridgeSlot,
    SchedulerBridge,
)
from services.pos.calendar_service import CalendarService


# ---------------------------------------------------------------------------
# Borrower contexts
# ---------------------------------------------------------------------------

# Re-import TokenScope from models.purl so we get the real enum.
from models.purl import TokenScope  # noqa: E402, F811


def _make_purl_ctx(
    *,
    contact_id: int,
    organization_id: int = 1,
    workspace_id: int = 1,
    scope: TokenScope = TokenScope.WRITE,
) -> PURLAuthContext:
    """Build a PURLAuthContext for tests.

    The real constructor requires token_id, workspace_slug, workspace_status
    (see middleware/purl_auth.py). We supply safe defaults for testing.
    """
    return PURLAuthContext(
        token_id=9999,
        organization_id=organization_id,
        workspace_id=workspace_id,
        workspace_slug="test-workspace",
        workspace_status="active",
        contact_id=contact_id,
        scope=scope,
    )


# ---------------------------------------------------------------------------
# Rate limiter reset (autouse)
# ---------------------------------------------------------------------------
#
# The in-memory PURLRateLimiter is a module-level singleton in
# middleware/purl_auth.py. Without resetting, request counts accumulate across
# tests for the same token_id (9999) and trigger 429 cascades that mask the
# real assertions. We belt-and-suspenders this two ways:
#
#   1. An autouse fixture clears the limiter's internal buckets before every
#      test (handles any route that uses check_purl_rate_limit even if the
#      test app forgets to override it).
#   2. The `app` fixture below also short-circuits check_purl_rate_limit via
#      dependency_overrides so the limiter is never even consulted in tests.
#
@pytest.fixture(autouse=True)
def _reset_purl_rate_limiter():
    from middleware import purl_auth as _pa

    limiter = getattr(_pa, "_rate_limiter", None)
    if limiter is not None:
        # Preferred: explicit reset() if it ever gets added.
        reset = getattr(limiter, "reset", None)
        if callable(reset):
            reset()
        else:
            # Fall back to clearing any dict-shaped internal store.
            for attr in (
                "_minute_counters",
                "_hour_counters",
                "_buckets",
                "_counts",
                "_requests",
                "_window",
            ):
                store = getattr(limiter, attr, None)
                if isinstance(store, dict):
                    store.clear()
    yield


@pytest.fixture
def borrower_alice() -> PURLAuthContext:
    return _make_purl_ctx(contact_id=1001)


@pytest.fixture
def borrower_bob() -> PURLAuthContext:
    return _make_purl_ctx(contact_id=1002)


@pytest.fixture
def borrower_alice_readonly() -> PURLAuthContext:
    return _make_purl_ctx(contact_id=1001, scope=TokenScope.READ)


# ---------------------------------------------------------------------------
# DB session (SQLite in-memory, sync)
# ---------------------------------------------------------------------------

# Use SQLite in-memory for fast, isolated tests.
_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def _pos_engine():
    """Create a session-scoped test engine with POS tables via raw DDL.

    SQLite cannot render JSONB, INET, or PostgreSQL UUID natively, so we
    create the tables with SQLite-compatible types (TEXT for JSON, VARCHAR
    for UUID/INET). The ORM still works because SQLAlchemy's type
    negotiation adapts at the Python binding level.

    FK references to external tables (loans, scheduler_appointments) are
    intentionally omitted since those tables don't exist in the test DB.
    """
    from sqlalchemy import event, text

    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )

    # Enable foreign keys for SQLite.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_applications (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                loan_id INTEGER,
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                current_step VARCHAR(32) NOT NULL DEFAULT 'personal',
                completion_pct INTEGER NOT NULL DEFAULT 0,
                submitted_at TIMESTAMP,
                submitted_appointment_id INTEGER,
                source_channel VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_application_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id VARCHAR(36) NOT NULL
                    REFERENCES pos_applications(id) ON DELETE CASCADE,
                section_key VARCHAR(32) NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                is_complete BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(application_id, section_key)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_application_pii (
                application_id VARCHAR(36) PRIMARY KEY
                    REFERENCES pos_applications(id) ON DELETE CASCADE,
                ssn_encrypted TEXT,
                co_ssn_encrypted TEXT,
                dob DATE,
                co_dob DATE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_application_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id VARCHAR(36) NOT NULL
                    REFERENCES pos_applications(id) ON DELETE CASCADE,
                actor_type VARCHAR(16) NOT NULL,
                actor_id INTEGER,
                event_type VARCHAR(64) NOT NULL,
                section_key VARCHAR(32),
                delta TEXT,
                ip_address VARCHAR(45),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_ai_qa_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id VARCHAR(36) NOT NULL
                    REFERENCES pos_applications(id) ON DELETE CASCADE,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                follow_ups TEXT,
                latency_ms INTEGER,
                tokens_used INTEGER,
                confidence VARCHAR(16),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Stub tables referenced by calendar routes (Appointment, BookingLink).
        # Only the columns accessed by POS code are included.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scheduler_appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER,
                appointment_type_id INTEGER,
                assigned_user_id INTEGER,
                created_by_user_id INTEGER,
                lead_id INTEGER,
                loan_id INTEGER,
                contact_id INTEGER,
                idempotency_key TEXT,
                external_id TEXT,
                external_source TEXT,
                title TEXT,
                description TEXT,
                meeting_type TEXT,
                meeting_mode TEXT,
                scheduled_start TIMESTAMP,
                scheduled_end TIMESTAMP,
                duration_minutes INTEGER,
                timezone TEXT,
                location TEXT,
                video_link TEXT,
                phone_number TEXT,
                dial_in_info TEXT,
                attendee_name TEXT,
                attendee_email TEXT,
                attendee_phone TEXT,
                attendee_notes TEXT,
                intake_responses TEXT,
                status TEXT DEFAULT 'scheduled',
                status_changed_at TIMESTAMP,
                status_changed_by INTEGER,
                completed_at TIMESTAMP,
                no_show_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                cancellation_reason TEXT,
                rescheduled_from_id INTEGER,
                reschedule_count INTEGER DEFAULT 0,
                booked_by_ai BOOLEAN DEFAULT 0,
                ai_booking_context TEXT,
                auto_confirmed BOOLEAN DEFAULT 0,
                google_calendar_event_id TEXT,
                outlook_event_id TEXT,
                last_synced_at TIMESTAMP,
                internal_notes TEXT,
                meeting_notes TEXT,
                version INTEGER DEFAULT 1,
                recovery_step TEXT,
                recovery_started_at TIMESTAMP,
                recovery_completed_at TIMESTAMP,
                recovery_opted_out BOOLEAN DEFAULT 0,
                communication_consent_at TIMESTAMP,
                communication_consent_source TEXT,
                booking_attribution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_pos_engine) -> Generator[Session, None, None]:
    """Yield a transactional sync session that rolls back after each test."""
    connection = _pos_engine.connect()
    transaction = connection.begin()
    _SessionLocal = sessionmaker(bind=connection)
    session = _SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# FastAPI app + client
# ---------------------------------------------------------------------------


@pytest.fixture
def app(
    db_session: Session,
    borrower_alice: PURLAuthContext,
    fake_scheduler_bridge: "FakeSchedulerBridge",
    fake_guidelines_agent: "FakeGuidelinesAgent",
) -> FastAPI:
    """A minimal FastAPI app with all POS routers mounted.

    Auth and DB are overridden so tests run hermetically without a real
    PURL token or live scheduler.
    """
    test_app = FastAPI()
    test_app.include_router(application_router)
    test_app.include_router(calendar_router)
    test_app.include_router(ai_qa_router)

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = _override_db
    test_app.dependency_overrides[require_purl_token] = lambda: borrower_alice
    test_app.dependency_overrides[require_purl_write_scope] = lambda: borrower_alice
    # Short-circuit the in-memory PURLRateLimiter so tests never produce 429
    # cascades from singleton state. See _reset_purl_rate_limiter above for
    # the autouse counterpart that also clears any direct module access.
    test_app.dependency_overrides[check_purl_rate_limit] = lambda: borrower_alice

    # Override service singletons with fakes.
    from routes.pos.calendar import get_calendar_service
    from routes.pos.ai_qa import get_ai_qa_service

    test_app.dependency_overrides[get_calendar_service] = lambda: CalendarService(
        bridge=fake_scheduler_bridge
    )
    test_app.dependency_overrides[get_ai_qa_service] = lambda: AIQAService(
        guidelines_agent=fake_guidelines_agent
    )
    return test_app


@pytest.fixture
def app_as_bob(
    app: FastAPI, borrower_bob: PURLAuthContext
) -> FastAPI:
    """Same app, but PURL context resolves to Bob (a different borrower)."""
    app.dependency_overrides[require_purl_token] = lambda: borrower_bob
    app.dependency_overrides[require_purl_write_scope] = lambda: borrower_bob
    app.dependency_overrides[check_purl_rate_limit] = lambda: borrower_bob
    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_as_bob(app_as_bob: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app_as_bob) as c:
        yield c


# ---------------------------------------------------------------------------
# Application factories
# ---------------------------------------------------------------------------


@pytest.fixture
def alice_application(
    db_session: Session, borrower_alice: PURLAuthContext
) -> POSApplication:
    """Create a draft application owned by Alice with a couple of sections filled."""
    application = POSApplication(
        id=uuid4(),
        organization_id=borrower_alice.organization_id,
        workspace_id=borrower_alice.workspace_id,
        contact_id=borrower_alice.contact_id,
        loan_id=None,
        status=POSStatus.DRAFT,
        current_step="personal",
        completion_pct=0,
    )
    db_session.add(application)
    db_session.flush()
    return application


@pytest.fixture
def alice_application_with_loan(
    db_session: Session, borrower_alice: PURLAuthContext
) -> POSApplication:
    """Application linked to loan_id=42 (Alice's loan)."""
    application = POSApplication(
        id=uuid4(),
        organization_id=borrower_alice.organization_id,
        workspace_id=borrower_alice.workspace_id,
        contact_id=borrower_alice.contact_id,
        loan_id=42,
        status=POSStatus.DRAFT,
        current_step="personal",
    )
    db_session.add(application)
    db_session.flush()
    return application


@pytest.fixture
def bob_application(
    db_session: Session, borrower_bob: PURLAuthContext
) -> POSApplication:
    """Application owned by Bob -- used to test cross-borrower access denial."""
    application = POSApplication(
        id=uuid4(),
        organization_id=borrower_bob.organization_id,
        workspace_id=borrower_bob.workspace_id,
        contact_id=borrower_bob.contact_id,
        loan_id=99,
        status=POSStatus.DRAFT,
        current_step="personal",
    )
    db_session.add(application)
    db_session.flush()
    return application


# ---------------------------------------------------------------------------
# Fake scheduler bridge
# ---------------------------------------------------------------------------


class FakeSchedulerBridge(SchedulerBridge):
    """In-memory fake of the scheduler bridge for hermetic tests."""

    def __init__(self) -> None:
        super().__init__()
        self.holds_placed: list[dict[str, Any]] = []
        self.bookings_made: list[dict[str, Any]] = []
        self.cancellations: list[dict[str, Any]] = []
        self._next_appointment_id = 5000

    async def get_available_slots(self, **kwargs):  # type: ignore[override]
        # Return 3 fake slots -- one weekday morning (recommended), one
        # afternoon, one weekend.
        base = datetime.now(timezone.utc).replace(
            hour=10, minute=0, second=0, microsecond=0
        ) + timedelta(days=2)
        if base.weekday() >= 5:
            base += timedelta(days=2)
        return [
            BridgeSlot(start=base, end=base + timedelta(minutes=30), is_available=True),
            BridgeSlot(
                start=base.replace(hour=14),
                end=base.replace(hour=14) + timedelta(minutes=30),
                is_available=True,
            ),
            BridgeSlot(
                start=base + timedelta(days=4, hours=2),  # might be weekend
                end=base + timedelta(days=4, hours=2, minutes=30),
                is_available=True,
            ),
        ]

    async def hold_slot(self, **kwargs):  # type: ignore[override]
        self.holds_placed.append(kwargs)
        return BridgeHold(
            hold_id=9001,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            slot_start=kwargs["slot_start"],
            slot_end=kwargs["slot_end"],
        )

    async def book(self, **kwargs):  # type: ignore[override]
        self.bookings_made.append(kwargs)
        appt_id = self._next_appointment_id
        self._next_appointment_id += 1
        return BridgeBooking(
            appointment_id=appt_id,
            scheduled_start=kwargs["slot_start"],
            scheduled_end=kwargs["slot_end"],
            confirmation_url=f"https://test/confirm/{appt_id}",
            ics_link=f"https://test/ics/{appt_id}.ics",
            email_sent=True,
            calendar_event_created=True,
        )

    async def cancel(self, **kwargs):  # type: ignore[override]
        self.cancellations.append(kwargs)
        return BridgeCancellation(
            appointment_id=kwargs["appointment_id"],
            cancelled_at=datetime.now(timezone.utc),
            notification_sent=True,
        )


@pytest.fixture
def fake_scheduler_bridge() -> FakeSchedulerBridge:
    return FakeSchedulerBridge()


# ---------------------------------------------------------------------------
# Fake GuidelinesChatAgent
# ---------------------------------------------------------------------------


class FakeGuidelinesAgent:
    """Deterministic agent for tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def answer(
        self,
        *,
        question: str,
        loan_context: dict,
        history: list,
        current_step: str | None,
    ) -> dict:
        self.calls.append(
            {
                "question": question,
                "loan_context": loan_context,
                "history": history,
                "current_step": current_step,
            }
        )

        q = question.lower()
        if "gift" in q:
            return {
                "content": "Yes, gift funds are eligible for your conventional loan.",
                "sources": [
                    {
                        "type": "guideline",
                        "label": "FNMA Selling Guide B3-4.3-04",
                        "anchor": "https://selling-guide.fanniemae.com/B3-4.3-04",
                    },
                    {
                        "type": "loan_file",
                        "label": "Your loan file",
                        "anchor": "sections.assets",
                    },
                ],
                "follow_ups": [
                    "How do I document the gift?",
                    "Are there limits?",
                ],
                "tokens_used": 412,
                "escalation_reason": None,
            }
        if "escalate" in q:
            return {
                "content": "Let me loop in your loan officer.",
                "sources": [],
                "follow_ups": [],
                "tokens_used": 50,
                "escalation_reason": "test_escalation",
            }
        return {
            "content": "Generic answer.",
            "sources": [
                {"type": "loan_file", "label": "Your loan file", "anchor": None}
            ],
            "follow_ups": ["Anything else?"],
            "tokens_used": 100,
            "escalation_reason": None,
        }


@pytest.fixture
def fake_guidelines_agent() -> FakeGuidelinesAgent:
    return FakeGuidelinesAgent()
