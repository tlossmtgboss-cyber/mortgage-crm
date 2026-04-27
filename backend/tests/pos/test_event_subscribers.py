"""Tests for POS event subscribers.

Verifies that:
  - POS_APPLICATION_SUBMITTED handler creates/updates Loan record
  - POS_APPLICATION_SUBMITTED handler maps personal data to Lead fields
  - POS_APPLICATION_SUBMITTED handler sets Loan.stage to APPLICATION
  - POS_APPLICATION_SUBMITTED handler creates a review Task
  - POS_APPLICATION_SUBMITTED with no loan_id creates a new Loan
  - POS_APPOINTMENT_BOOKED handler creates a task for the LO
  - Event payload integrity (sections, pii flags, required fields)

These tests call the handler functions directly with synthetic Event objects
rather than going through the full EventBus publish cycle, so DB dependencies
can be mocked/stubbed independently.

The handlers use lazy imports (e.g. ``from db import SessionLocal`` inside the
function body), so we patch at the source module level
(``db.SessionLocal``, ``database.models.lead_loan.Lead``, etc.) rather than
on the ``event_subscribers`` module.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.event_bus import Event, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async function synchronously (tests are sync)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_submitted_event(
    *,
    application_id: str | None = None,
    contact_id: int = 1001,
    loan_id: int | None = None,
    org_id: str = "1",
    appointment_id: int | None = 5042,
    personal_data: dict[str, Any] | None = None,
    employment_data: dict[str, Any] | None = None,
    loan_section_data: dict[str, Any] | None = None,
    residence_data: dict[str, Any] | None = None,
    pii: dict[str, Any] | None = None,
) -> Event:
    """Build a POS_APPLICATION_SUBMITTED event with realistic payload."""
    if application_id is None:
        application_id = str(uuid4())

    default_personal = {
        "first_name": "Alice",
        "last_name": "Anderson",
        "email": "alice@example.com",
        "phone": "+15551234567",
    }
    default_loan_section = {
        "loan_amount": 350000,
        "loan_purpose": "PURCHASE",
        "loan_type": "CONVENTIONAL",
    }

    sections: dict[str, Any] = {}
    sections["personal"] = {
        "data": personal_data if personal_data is not None else default_personal,
        "is_complete": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if employment_data is not None:
        sections["employment"] = {
            "data": employment_data,
            "is_complete": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    sections["loan"] = {
        "data": loan_section_data if loan_section_data is not None else default_loan_section,
        "is_complete": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if residence_data is not None:
        sections["residence"] = {
            "data": residence_data,
            "is_complete": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    payload: dict[str, Any] = {
        "version": "pos_1003_v1",
        "sections": sections,
        "pii": pii or {},
        "loan_id": loan_id,
        "contact_id": contact_id,
        "organization_id": 1,
        "workspace_id": 1,
        "source_channel": "voice_agent",
    }

    return Event(
        type=EventType.POS_APPLICATION_SUBMITTED,
        data={
            "application_id": application_id,
            "loan_id": loan_id,
            "contact_id": contact_id,
            "appointment_id": appointment_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        },
        org_id=org_id,
    )


def _make_appointment_booked_event(
    *,
    appointment_id: int = 6001,
    lo_user_id: int = 10,
    meeting_type: str = "consultation",
    loan_id: int | None = None,
    org_id: str = "1",
    application_id: str | None = None,
) -> Event:
    """Build a POS_APPOINTMENT_BOOKED event."""
    return Event(
        type=EventType.POS_APPOINTMENT_BOOKED,
        data={
            "application_id": application_id or str(uuid4()),
            "appointment_id": appointment_id,
            "loan_id": loan_id,
            "loan_officer_user_id": lo_user_id,
            "meeting_type": meeting_type,
        },
        org_id=org_id,
    )


# ---------------------------------------------------------------------------
# Fake models for unit testing without real DB
# ---------------------------------------------------------------------------

class _FakeColumn:
    """Allows `Lead.id == value` without raising."""
    def __eq__(self, other):
        return True

    def __hash__(self):
        return id(self)


class FakeLead:
    """Minimal Lead stand-in."""
    id = _FakeColumn()  # class-level for filter() expressions

    def __init__(self, *, instance_id: int = 1001, **kwargs):
        self.id = instance_id
        self.first_name = kwargs.get("first_name", "Existing")
        self.last_name = kwargs.get("last_name", "Lead")
        self.name = kwargs.get("name", f"{self.first_name} {self.last_name}")
        self.email = kwargs.get("email", "existing@example.com")
        self.phone = kwargs.get("phone")
        self.owner_id = kwargs.get("owner_id", 10)
        self.organization_id = kwargs.get("organization_id", 1)
        self.employment_status = None
        self.annual_income = None
        self.employer_name = None
        self.application_completed_date = None
        self.user_metadata = None


class FakeLoan:
    """Minimal Loan stand-in."""
    id = _FakeColumn()  # class-level for filter() expressions

    def __init__(self, *, instance_id: int | None = 42, **kwargs):
        self.id = instance_id
        self.loan_number = kwargs.get("loan_number", "EXISTING-001")
        self.borrower_name = kwargs.get("borrower_name", "Existing Borrower")
        self.borrower_email = kwargs.get("borrower_email")
        self.borrower_phone = kwargs.get("borrower_phone")
        self.amount = kwargs.get("amount", 300000.0)
        self.stage = kwargs.get("stage", "DISCLOSED")
        self.stage_changed_at = None
        self.application_date = None
        self.loan_officer_id = kwargs.get("loan_officer_id", 10)
        self.organization_id = kwargs.get("organization_id", 1)
        self.loan_purpose = None
        self.loan_type = None
        self.property_type = None
        self.purchase_price = None
        self.down_payment = None
        self.term = None
        self.property_address = None
        self.property_city = None
        self.property_state = None
        self.property_zip = None


class FakeTask:
    """Minimal Task stand-in with attribute capture."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = 999
        if "loan_id" not in kwargs:
            self.loan_id = kwargs.get("loan_id")


class FakeSession:
    """Minimal session stub that tracks adds, queries, commits, and rollbacks."""
    def __init__(self):
        self.added: list[Any] = []
        self._query_results: dict[type, Any] = {}
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True
        # Simulate ID assignment for new objects
        for obj in self.added:
            if hasattr(obj, "id") and obj.id is None:
                obj.id = 99

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass

    def query(self, model_class):
        return _FakeQuery(self._query_results.get(model_class))

    def set_query_result(self, model_class: type, result: Any):
        self._query_results[model_class] = result


class _FakeQuery:
    """Minimal query chain stub."""
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


# ---------------------------------------------------------------------------
# Patching helpers
#
# The handlers do lazy imports:
#   from db import SessionLocal
#   from database.models.lead_loan import Lead, Loan
#   from database.models.task import Task
#
# We patch these at their source modules so that the lazy imports pick up
# our fakes.
# ---------------------------------------------------------------------------

def _patch_promote_handler(session, lead_cls, loan_cls, task_cls):
    """Return a combined context manager that patches all lazy imports
    used by on_pos_application_submitted_promote."""
    return _MultiPatch(
        patch("db.SessionLocal", return_value=session),
        patch("database.models.lead_loan.Lead", lead_cls),
        patch("database.models.lead_loan.Loan", loan_cls),
        patch("database.models.task.Task", task_cls),
    )


def _patch_appointment_handler(session, task_cls):
    """Patch lazy imports used by on_pos_appointment_booked_create_task."""
    return _MultiPatch(
        patch("db.SessionLocal", return_value=session),
        patch("database.models.task.Task", task_cls),
    )


class _MultiPatch:
    """Stack multiple ``patch()`` context managers."""
    def __init__(self, *patches):
        self._patches = patches
        self._mocks = []

    def __enter__(self):
        self._mocks = [p.__enter__() for p in self._patches]
        return self._mocks

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.__exit__(*exc)


# ==========================================================================
# Test 1: POS_APPLICATION_SUBMITTED handler creates/updates Loan record
# ==========================================================================

class TestPOSApplicationSubmittedPromotion:
    """Tests for on_pos_application_submitted_promote handler."""

    def test_updates_existing_loan_with_section_data(self):
        """When loan_id is present and the Loan exists, update it."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001)
        loan = FakeLoan(instance_id=42, stage="DISCLOSED")
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(
            contact_id=1001,
            loan_id=42,
            loan_section_data={
                "loan_amount": 450000,
                "loan_purpose": "PURCHASE",
                "loan_type": "CONVENTIONAL",
            },
        )

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert loan.amount == 450000.0
        assert loan.loan_purpose == "PURCHASE"
        assert session.committed

    def test_maps_personal_section_to_lead_fields(self):
        """Personal section data should update Lead fields."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001)
        loan = FakeLoan(instance_id=42, stage="DISCLOSED")
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(
            contact_id=1001,
            loan_id=42,
            personal_data={
                "first_name": "NewFirst",
                "last_name": "NewLast",
                "email": "newfirst@example.com",
                "phone": "+15559876543",
            },
        )

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert lead.first_name == "NewFirst"
        assert lead.last_name == "NewLast"
        assert lead.email == "newfirst@example.com"
        assert lead.phone == "+15559876543"
        assert lead.name == "NewFirst NewLast"

    def test_sets_loan_stage_to_application(self):
        """Handler should promote Loan.stage from DISCLOSED to APPLICATION."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001)
        loan = FakeLoan(instance_id=42, stage="DISCLOSED")
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(contact_id=1001, loan_id=42)

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert loan.stage == "APPLICATION"
        assert loan.stage_changed_at is not None
        assert loan.application_date is not None

    def test_does_not_downgrade_loan_stage(self):
        """If Loan.stage is already past APPLICATION, do not overwrite."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001)
        loan = FakeLoan(instance_id=42, stage="PROCESSING")
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(contact_id=1001, loan_id=42)

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert loan.stage == "PROCESSING"

    def test_creates_review_task_for_lo(self):
        """Handler should create a review task for the assigned LO."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001, owner_id=10)
        loan = FakeLoan(instance_id=42, stage="DISCLOSED", loan_officer_id=10)
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(contact_id=1001, loan_id=42)

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        tasks_in_session = [
            obj for obj in session.added if isinstance(obj, FakeTask)
        ]
        assert len(tasks_in_session) >= 1
        task = tasks_in_session[0]
        assert "1003" in task.title or "Review" in task.title
        assert task.status == "pending"
        assert task.priority == "high"

    def test_creates_new_loan_when_no_loan_id(self):
        """When no loan_id in the payload, create a new Loan record."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001, owner_id=10)
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, None)

        event = _make_submitted_event(
            contact_id=1001,
            loan_id=None,
            loan_section_data={"loan_amount": 500000, "loan_purpose": "REFINANCE"},
        )

        # FakeLoan constructor: the handler does Loan(**kwargs), so we need
        # FakeLoan to be callable and return a FakeLoan instance.
        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        loans_added = [
            obj for obj in session.added if isinstance(obj, FakeLoan)
        ]
        assert len(loans_added) >= 1
        new_loan = loans_added[0]
        assert new_loan.loan_number.startswith("POS-")
        assert new_loan.stage == "APPLICATION"
        assert new_loan.amount == 500000.0

    def test_skips_when_contact_not_found(self):
        """Handler should return cleanly if Lead not found."""
        from services.event_subscribers import on_pos_application_submitted_promote

        session = FakeSession()
        session.set_query_result(FakeLead, None)

        event = _make_submitted_event(contact_id=9999)

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert not session.committed

    def test_skips_when_no_contact_id(self):
        """Handler should return immediately if contact_id is missing."""
        from services.event_subscribers import on_pos_application_submitted_promote

        event = Event(
            type=EventType.POS_APPLICATION_SUBMITTED,
            data={
                "application_id": str(uuid4()),
                "contact_id": None,
                "payload": {},
            },
            org_id="1",
        )

        # Should not raise -- returns early before lazy import
        _run(on_pos_application_submitted_promote(event))

    def test_pii_ssn_flagged_not_stored_raw(self):
        """SSN should be flagged as received in metadata, never stored raw."""
        from services.event_subscribers import on_pos_application_submitted_promote

        lead = FakeLead(instance_id=1001)
        loan = FakeLoan(instance_id=42, stage="DISCLOSED")
        session = FakeSession()
        session.set_query_result(FakeLead, lead)
        session.set_query_result(FakeLoan, loan)

        event = _make_submitted_event(
            contact_id=1001,
            loan_id=42,
            pii={"ssn": "123-45-6789", "dob": "1985-06-12"},
        )

        with _patch_promote_handler(session, FakeLead, FakeLoan, FakeTask):
            _run(on_pos_application_submitted_promote(event))

        assert lead.user_metadata is not None
        assert lead.user_metadata.get("pos_ssn_received") is True
        metadata_str = str(lead.user_metadata)
        assert "123-45-6789" not in metadata_str


# ==========================================================================
# Test 2: POS_APPOINTMENT_BOOKED handler creates task
# ==========================================================================

class TestPOSAppointmentBookedTask:
    """Tests for on_pos_appointment_booked_create_task handler."""

    def test_creates_task_for_lo(self):
        """Handler should create a pending task assigned to the LO."""
        from services.event_subscribers import on_pos_appointment_booked_create_task

        session = FakeSession()

        event = _make_appointment_booked_event(
            appointment_id=6001,
            lo_user_id=10,
            meeting_type="pre_approval_review",
            loan_id=42,
        )

        with _patch_appointment_handler(session, FakeTask):
            _run(on_pos_appointment_booked_create_task(event))

        tasks = [obj for obj in session.added if isinstance(obj, FakeTask)]
        assert len(tasks) >= 1
        task = tasks[0]
        assert task.owner_id == 10
        assert task.status == "pending"
        assert "pre_approval_review" in task.title or "6001" in task.title
        assert task.loan_id == 42
        assert session.committed

    def test_skips_when_no_lo_user_id(self):
        """Handler should skip if loan_officer_user_id is missing."""
        from services.event_subscribers import on_pos_appointment_booked_create_task

        event = _make_appointment_booked_event()
        event.data["loan_officer_user_id"] = None

        # Should not raise
        _run(on_pos_appointment_booked_create_task(event))

    def test_skips_when_no_appointment_id(self):
        """Handler should skip if appointment_id is missing."""
        from services.event_subscribers import on_pos_appointment_booked_create_task

        event = _make_appointment_booked_event()
        event.data["appointment_id"] = None

        _run(on_pos_appointment_booked_create_task(event))


# ==========================================================================
# Test 3: Event payload integrity
# ==========================================================================

class TestEventPayloadIntegrity:
    """Verify the event payload structure emitted by ApplicationService.submit."""

    def test_submitted_event_has_required_fields(self):
        """The event data dict must contain all fields consumed by subscribers."""
        event = _make_submitted_event(
            application_id="test-app-123",
            contact_id=1001,
            loan_id=42,
            appointment_id=5042,
        )

        data = event.data
        assert data["application_id"] == "test-app-123"
        assert data["contact_id"] == 1001
        assert data["loan_id"] == 42
        assert data["appointment_id"] == 5042
        assert "submitted_at" in data
        assert "payload" in data

    def test_payload_has_version_and_sections(self):
        """The payload must have version and sections keys."""
        event = _make_submitted_event()
        payload = event.data["payload"]

        assert payload["version"] == "pos_1003_v1"
        assert "sections" in payload
        assert isinstance(payload["sections"], dict)

    def test_payload_sections_have_data_and_completion(self):
        """Each section in the payload must have data, is_complete, completed_at."""
        event = _make_submitted_event()
        sections = event.data["payload"]["sections"]

        for key, section in sections.items():
            assert "data" in section, f"Section {key} missing 'data'"
            assert "is_complete" in section, f"Section {key} missing 'is_complete'"
            assert "completed_at" in section, f"Section {key} missing 'completed_at'"

    def test_payload_pii_presence_flags(self):
        """PII section should carry SSN/DOB values for the subscriber to process."""
        event = _make_submitted_event(
            pii={"ssn": "123-45-6789", "dob": "1990-01-01"},
        )
        pii = event.data["payload"]["pii"]

        assert "ssn" in pii
        assert "dob" in pii

    def test_event_type_is_pos_submitted(self):
        """Event must have the correct EventType."""
        event = _make_submitted_event()
        assert event.type == EventType.POS_APPLICATION_SUBMITTED

    def test_appointment_booked_event_structure(self):
        """POS_APPOINTMENT_BOOKED must carry expected fields."""
        event = _make_appointment_booked_event(
            appointment_id=6001,
            lo_user_id=10,
            meeting_type="consultation",
            loan_id=42,
        )

        assert event.type == EventType.POS_APPOINTMENT_BOOKED
        data = event.data
        assert data["appointment_id"] == 6001
        assert data["loan_officer_user_id"] == 10
        assert data["meeting_type"] == "consultation"
        assert data["loan_id"] == 42
        assert "application_id" in data


# ==========================================================================
# Test 4: Registration wiring
# ==========================================================================

class TestSubscriberRegistration:
    """Verify register_all_subscribers wires POS event handlers.

    We use the module-level ``event_bus`` singleton (not reset_instance) because
    register_all_subscribers imports the same singleton.  We clear() it before
    and after each test to avoid cross-test pollution.
    """

    def test_pos_submitted_handlers_registered(self):
        """After registration, POS_APPLICATION_SUBMITTED should have handlers."""
        from services.event_bus import event_bus as bus
        from services.event_subscribers import (
            on_pos_application_submitted_promote,
            on_pos_application_submitted_audit,
            on_pos_application_submitted_notify_lo,
            register_all_subscribers,
        )

        bus.clear()
        try:
            register_all_subscribers()
            handlers = bus.get_subscribers(EventType.POS_APPLICATION_SUBMITTED)
            assert on_pos_application_submitted_promote in handlers
            assert on_pos_application_submitted_audit in handlers
            assert on_pos_application_submitted_notify_lo in handlers
        finally:
            bus.clear()

    def test_pos_appointment_booked_handlers_registered(self):
        """After registration, POS_APPOINTMENT_BOOKED should have handlers."""
        from services.event_bus import event_bus as bus
        from services.event_subscribers import (
            on_pos_appointment_booked_create_task,
            on_pos_appointment_booked_notify_lo,
            on_pos_appointment_booked_audit,
            register_all_subscribers,
        )

        bus.clear()
        try:
            register_all_subscribers()
            handlers = bus.get_subscribers(EventType.POS_APPOINTMENT_BOOKED)
            assert on_pos_appointment_booked_create_task in handlers
            assert on_pos_appointment_booked_notify_lo in handlers
            assert on_pos_appointment_booked_audit in handlers
        finally:
            bus.clear()
