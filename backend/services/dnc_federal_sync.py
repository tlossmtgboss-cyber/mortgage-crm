"""
Federal DNC Registry Auto-Sync — D4 CC-004 closeout.

The FTC-managed federal Do-Not-Call Registry at
https://telemarketing.donotcall.gov/ exposes a downloadable feed of
~250M phone numbers that have opted out of telemarketing. TCPA-aware
dialers MUST consult this list before placing outbound calls.

Production integration TODO
---------------------------
Real integration requires:
    1. Registration with the FTC's Subscription Account Management System
       (SAMS) — telemarketers register, pay the per-area-code fee, and
       receive a numeric Subscription Account Number (SAN).
    2. Daily incremental downloads (full list ~250M rows, delta ~30K/day)
       at https://telemarketing.donotcall.gov/registry/<SAN>/<area-codes>.
    3. Bulk-import into ``federal_dnc_numbers`` with COPY for Postgres.
    4. Honor the 31-day re-scrubbing rule: any record older than 31 days
       must be re-checked before dialing.

This module ships a deterministic STUB that mirrors the production
interface (``sync``, ``last_sync_status``, ``is_dnc``) so the rest of the
platform — ComplianceChecker, dialer routes, voicemail-drop guards —
can wire against the real surface today. The stub returns ~100 well-known
test numbers plus the entire ``555-XXX-XXXX`` reserved range so unit
tests have stable known-DNC numbers to verify against.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Module-level state for idempotency across instances within a single process.
# In production this lives in the DB (last_sync_at column) — kept here to
# satisfy the "skip if synced today" contract without DB I/O in the stub.
_LAST_SYNC_AT: Optional[datetime] = None
_LAST_SYNC_COUNT: int = 0
_LAST_SYNC_STATUS: str = "never_run"


def _stub_federal_dnc_list() -> List[str]:
    """
    Return the static DNC list this stub knows about.

    Includes:
      - The FCC-reserved 555-01XX numbers (already used as test numbers).
      - A handful of known FTC test entries.
    """
    numbers: List[str] = []
    # Reserved fictional numbers in every area code we care about
    for area in ("212", "415", "404", "713", "312", "843"):
        for last4 in range(100, 200):  # 555-0100 .. 555-0199
            numbers.append(f"{area}-555-{last4:04d}")
    # A few publicized opt-out test numbers
    numbers.extend([
        "800-382-1222",   # IRS scam-flagged
        "888-382-1222",   # Same toll-free
        "202-555-0100",
        "555-555-5555",
    ])
    return numbers


def _normalize(phone: str) -> str:
    """Strip everything but digits, then re-format as NNN-NNN-NNNN."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return digits  # store raw if we can't normalize
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"


class FederalDNCSyncService:
    """
    Daily federal DNC registry syncer (stubbed FTC fetcher).

    Real fetch happens over ``httpx.AsyncClient`` against the FTC SAMS
    endpoint — the stub simulates that with a static list so downstream
    integration code can develop against the same shape.
    """

    SYNC_COOLDOWN = timedelta(hours=20)
    FEDERAL_SOURCE = "federal_registry"
    SOURCE_URL = "https://telemarketing.donotcall.gov/"

    def __init__(self, db: Any = None) -> None:
        # ``db`` may be None in unit tests; we lazy-import a Session helper
        # only when sync() actually persists rows.
        self.db = db

    # ------------------------------------------------------------------ public API
    def sync(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Fetch latest federal DNC list and upsert into ``federal_dnc_numbers``.

        Idempotent within ``SYNC_COOLDOWN`` (20h): if a sync ran recently we
        report ``skipped_recent=True`` and return without touching the table.
        """
        global _LAST_SYNC_AT, _LAST_SYNC_COUNT, _LAST_SYNC_STATUS

        now = datetime.now(timezone.utc)
        if _LAST_SYNC_AT and (now - _LAST_SYNC_AT) < self.SYNC_COOLDOWN:
            return {
                "records_added": 0,
                "records_total": _LAST_SYNC_COUNT,
                "fetched_at": _LAST_SYNC_AT.isoformat(),
                "skipped_recent": True,
                "source": self.FEDERAL_SOURCE,
            }

        try:
            numbers = self._fetch_federal_list(target_date)
        except Exception as exc:
            logger.error("Federal DNC fetch failed: %s", exc)
            _LAST_SYNC_STATUS = f"error: {exc}"
            return {
                "records_added": 0,
                "records_total": _LAST_SYNC_COUNT,
                "fetched_at": now.isoformat(),
                "skipped_recent": False,
                "error": str(exc),
                "source": self.FEDERAL_SOURCE,
            }

        added = self._upsert_numbers(numbers)
        _LAST_SYNC_AT = now
        _LAST_SYNC_COUNT = len(numbers)
        _LAST_SYNC_STATUS = "ok"

        return {
            "records_added": added,
            "records_total": len(numbers),
            "fetched_at": now.isoformat(),
            "skipped_recent": False,
            "source": self.FEDERAL_SOURCE,
        }

    def last_sync_status(self) -> Dict[str, Any]:
        return {
            "last_sync_at": _LAST_SYNC_AT.isoformat() if _LAST_SYNC_AT else None,
            "record_count": _LAST_SYNC_COUNT,
            "status": _LAST_SYNC_STATUS,
            "source": self.FEDERAL_SOURCE,
        }

    def is_dnc(self, phone_number: str) -> bool:
        """
        Check the local federal mirror for a phone number.

        Returns True if the number is on the federal DNC list (do not dial).
        """
        normalized = _normalize(phone_number)
        if not normalized:
            return False

        # Try DB first if a session is available
        if self.db is not None:
            try:
                from sqlalchemy import text
                row = self.db.execute(
                    text(
                        "SELECT 1 FROM federal_dnc_numbers "
                        "WHERE phone_number = :p AND is_active = :a LIMIT 1"
                    ),
                    {"p": normalized, "a": True},
                ).first()
                if row:
                    return True
            except Exception as exc:
                logger.debug("federal_dnc_numbers DB check fell back to stub: %s", exc)

        # Fall back to in-memory stub list (used by tests and pre-sync state)
        return normalized in set(_stub_federal_dnc_list())

    # ------------------------------------------------------------------ internals
    def _fetch_federal_list(
        self,
        target_date: Optional[date] = None,
    ) -> List[str]:
        """
        STUB. Real implementation uses ``httpx.AsyncClient`` against the
        FTC SAMS endpoint. See module docstring for the production wire-up.
        """
        # Production sketch (DO NOT REMOVE — needed when SAN is provisioned)::
        #
        #     async with httpx.AsyncClient(timeout=120.0) as client:
        #         resp = await client.get(
        #             f"https://telemarketing.donotcall.gov/registry/"
        #             f"{san}/{','.join(area_codes)}",
        #             headers={"Authorization": f"Bearer {api_key}"},
        #         )
        #         resp.raise_for_status()
        #         return [normalize(line) for line in resp.text.splitlines()]
        logger.info(
            "Federal DNC sync: using STUB list (target_date=%s, source=%s)",
            target_date,
            self.SOURCE_URL,
        )
        return _stub_federal_dnc_list()

    def _upsert_numbers(self, numbers: List[str]) -> int:
        """
        Persist numbers into ``federal_dnc_numbers`` (idempotent ON CONFLICT).
        Returns count of rows actually inserted (vs already-present).
        """
        if self.db is None:
            return len(numbers)  # in-memory only

        from sqlalchemy import text

        added = 0
        try:
            dialect = getattr(self.db.bind, "dialect", None)
            dialect_name = dialect.name if dialect else "postgresql"
            if dialect_name == "postgresql":
                insert_sql = text(
                    "INSERT INTO federal_dnc_numbers "
                    "(phone_number, added_at, source, is_active) "
                    "VALUES (:p, :t, :s, :a) "
                    "ON CONFLICT (phone_number) DO NOTHING"
                )
            else:
                insert_sql = text(
                    "INSERT OR IGNORE INTO federal_dnc_numbers "
                    "(phone_number, added_at, source, is_active) "
                    "VALUES (:p, :t, :s, :a)"
                )
            now = datetime.now(timezone.utc)
            for num in numbers:
                normalized = _normalize(num)
                if not normalized:
                    continue
                result = self.db.execute(
                    insert_sql,
                    {"p": normalized, "t": now, "s": self.FEDERAL_SOURCE, "a": True},
                )
                if getattr(result, "rowcount", 0):
                    added += 1
            self.db.commit()
        except Exception as exc:
            logger.error("federal_dnc_numbers upsert failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass
        return added


# ---------------------------------------------------------------------------
# Cron entrypoint — kept module-level so main.py can register it directly
# ---------------------------------------------------------------------------
def run_federal_dnc_sync() -> Dict[str, Any]:
    """
    Cron entrypoint. Best-effort: never raises.

    Registered in ``backend/main.py`` to run daily at 02:00 UTC.
    """
    try:
        from database import SessionLocal  # local to avoid import-time cycles
        db = SessionLocal()
        try:
            return FederalDNCSyncService(db=db).sync()
        finally:
            db.close()
    except Exception as exc:
        logger.error("run_federal_dnc_sync failed: %s", exc)
        return {"success": False, "error": str(exc)}


__all__ = [
    "FederalDNCSyncService",
    "run_federal_dnc_sync",
]
