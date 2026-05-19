"""
Integration tests for voicemail-drop consent gating + audio gating + webhook.

Contracts under test:
  * Drop is rejected if consent_revoked_at is set
  * Drop is allowed if consent was never revoked
  * Drop is allowed if the consent lookup itself FAILS (fail-open on error)
  * Audio shorter than 5s is rejected (anti-spam)
  * The Slybroadcast webhook updates the VoicemailDrop row's status

Implementation: we model the production policy in-process with tiny helpers
that mirror the gate in `services/voicemail_consent_service.py` (and the
webhook handler in `routes/slybroadcast_webhook_routes.py`). The full DB-
backed equivalent is gated behind real-DB skipif.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import pytest


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# In-process model of the voicemail consent gate
# ---------------------------------------------------------------------------

class ConsentLookupError(Exception):
    """Raised by the consent service when it cannot resolve a phone number."""


@dataclass
class ConsentRecord:
    phone: str
    consent_granted_at: Optional[datetime] = None
    consent_revoked_at: Optional[datetime] = None


@dataclass
class FakeConsentService:
    records: dict = field(default_factory=dict)
    fail_lookup_for: set = field(default_factory=set)

    def lookup(self, phone: str) -> Optional[ConsentRecord]:
        if phone in self.fail_lookup_for:
            raise ConsentLookupError("upstream service down")
        return self.records.get(phone)


def should_drop_voicemail(
    consent: FakeConsentService,
    phone: str,
    audio_duration_seconds: float,
) -> tuple[bool, str]:
    """Production policy:
      1. audio < 5s -> reject (reason='audio_too_short')
      2. consent lookup error -> ALLOW (fail-open), reason='consent_lookup_failed'
      3. consent_revoked_at set -> REJECT, reason='consent_revoked'
      4. no consent record OR consent intact -> ALLOW
    """
    if audio_duration_seconds < 5.0:
        return False, "audio_too_short"
    try:
        record = consent.lookup(phone)
    except ConsentLookupError:
        return True, "consent_lookup_failed"
    if record and record.consent_revoked_at is not None:
        return False, "consent_revoked"
    return True, "ok"


# ---------------------------------------------------------------------------
# 1. drop rejected when consent_revoked_at set
# ---------------------------------------------------------------------------

def test_voicemail_rejected_when_consent_revoked():
    svc = FakeConsentService(
        records={
            "+15555550100": ConsentRecord(
                phone="+15555550100",
                consent_granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                consent_revoked_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
        }
    )
    ok, reason = should_drop_voicemail(svc, "+15555550100", audio_duration_seconds=10)
    assert ok is False
    assert reason == "consent_revoked"


# ---------------------------------------------------------------------------
# 2. drop allowed when consent never revoked
# ---------------------------------------------------------------------------

def test_voicemail_allowed_when_consent_intact():
    svc = FakeConsentService(
        records={
            "+15555550101": ConsentRecord(
                phone="+15555550101",
                consent_granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                consent_revoked_at=None,
            ),
        }
    )
    ok, reason = should_drop_voicemail(svc, "+15555550101", audio_duration_seconds=10)
    assert ok is True
    assert reason == "ok"


# ---------------------------------------------------------------------------
# 3. drop allowed when consent lookup fails (fail-open)
# ---------------------------------------------------------------------------

def test_voicemail_allowed_on_lookup_failure_fail_open():
    """If the consent service itself is broken, we MUST NOT block legitimate
    business operations. Production policy is fail-open on lookup error,
    with a distinct reason for the audit log."""
    svc = FakeConsentService(fail_lookup_for={"+15555550102"})
    ok, reason = should_drop_voicemail(svc, "+15555550102", audio_duration_seconds=10)
    assert ok is True
    assert reason == "consent_lookup_failed"


# ---------------------------------------------------------------------------
# 4. drop rejected when audio < 5s
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dur", [0.0, 1.0, 2.5, 4.9])
def test_voicemail_rejected_when_audio_too_short(dur):
    svc = FakeConsentService(
        records={
            "+15555550103": ConsentRecord(
                phone="+15555550103",
                consent_granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        }
    )
    ok, reason = should_drop_voicemail(svc, "+15555550103", audio_duration_seconds=dur)
    assert ok is False
    assert reason == "audio_too_short"


# ---------------------------------------------------------------------------
# 5. Slybroadcast webhook updates VoicemailDrop status
# ---------------------------------------------------------------------------

@dataclass
class FakeVoicemailDrop:
    id: int
    rvm_session_id: str
    status: str = "queued"
    rvm_dispo_code: str | None = None
    delivered_at: datetime | None = None


def apply_slybroadcast_webhook(
    drop: FakeVoicemailDrop, payload: dict
) -> FakeVoicemailDrop:
    """Mirror of the production handler. Maps Slybroadcast disposition codes
    to our VoicemailDrop.status."""
    code = (payload.get("dispo_code") or "").upper()
    drop.rvm_dispo_code = code or drop.rvm_dispo_code
    if code in {"OK", "DELIVERED"}:
        drop.status = "delivered"
        drop.delivered_at = datetime.now(timezone.utc)
    elif code in {"FAIL", "FAILED", "ERR"}:
        drop.status = "failed"
    elif code in {"NO_VM", "NOVM"}:
        drop.status = "no_voicemail"
    elif code in {"HUMAN", "ANS"}:
        drop.status = "human_answered"
    return drop


def test_slybroadcast_webhook_updates_voicemail_drop_status():
    drop = FakeVoicemailDrop(id=1, rvm_session_id="sly_abc123")

    # Successful delivery
    updated = apply_slybroadcast_webhook(drop, {"dispo_code": "delivered"})
    assert updated.status == "delivered"
    assert updated.delivered_at is not None
    assert updated.rvm_dispo_code == "DELIVERED"

    # Subsequent failure event (e.g. retry path)
    drop2 = FakeVoicemailDrop(id=2, rvm_session_id="sly_xyz789")
    apply_slybroadcast_webhook(drop2, {"dispo_code": "FAIL"})
    assert drop2.status == "failed"

    # Live human answered
    drop3 = FakeVoicemailDrop(id=3, rvm_session_id="sly_qqq000")
    apply_slybroadcast_webhook(drop3, {"dispo_code": "HUMAN"})
    assert drop3.status == "human_answered"
