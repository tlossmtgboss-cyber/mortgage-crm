"""
SLA Monitor — checks for SLA violations across leads, loans, and compliance items.

Runs as a periodic check (called by cron or autonomous agent). Queries the database
for entities that have breached or are approaching SLA deadlines and emits structured
violations with severity levels.

Usage:
    from services.sla_monitor import SLAMonitor

    monitor = SLAMonitor()
    violations = await monitor.check_all(db, org_id=7)
    for v in violations:
        print(v.severity, v.message)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class SLASeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SLAViolation:
    """A single SLA violation or approaching-deadline alert."""
    entity_type: str          # "lead", "loan"
    entity_id: int
    violation_type: str       # e.g. "stale_lead", "overdue_condition", "trid_disclosure"
    severity: SLASeverity
    message: str
    deadline: Optional[datetime] = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Thresholds (hours)
# ---------------------------------------------------------------------------

# Leads in "New" stage with no activity after this many hours are stale
_STALE_LEAD_HOURS = 24

# Leads approaching staleness — warn at this threshold
_STALE_LEAD_WARNING_HOURS = 18

# TRID requires initial disclosures within 3 business days of application.
# We approximate with calendar days for simplicity (72 hours).
_TRID_DISCLOSURE_DEADLINE_HOURS = 72

# Warn when disclosure deadline is within this many hours
_TRID_DISCLOSURE_WARNING_HOURS = 48

# Loans sitting in the same stage beyond these thresholds (hours) are flagged
_STAGE_DWELL_THRESHOLDS = {
    "PROCESSING": 120,       # 5 days
    "UNDERWRITING": 168,     # 7 days
    "SUBMITTED": 72,         # 3 days
    "CONDITIONAL_APPROVAL": 120,  # 5 days
    "CLOSING": 72,           # 3 days
    "DOCS": 48,              # 2 days
}

# Terminal stages — never flag these
_TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN",
    "DOES_NOT_QUALIFY", "NURTURE",
})


class SLAMonitor:
    """Checks for SLA violations across leads, loans, and compliance items."""

    async def check_all(self, db: Session, org_id: int) -> List[SLAViolation]:
        """Run all SLA checks for an organization and return violations."""
        violations: List[SLAViolation] = []
        violations.extend(await self._check_stale_leads(db, org_id))
        violations.extend(await self._check_overdue_conditions(db, org_id))
        violations.extend(await self._check_compliance_deadlines(db, org_id))

        # Log at appropriate levels
        for v in violations:
            if v.severity == SLASeverity.CRITICAL:
                logger.critical(
                    "SLA CRITICAL [org=%d] %s #%d: %s",
                    org_id, v.entity_type, v.entity_id, v.message,
                )
            else:
                logger.warning(
                    "SLA WARNING [org=%d] %s #%d: %s",
                    org_id, v.entity_type, v.entity_id, v.message,
                )

        if violations:
            logger.info(
                "SLA check complete for org %d: %d violation(s) — %d critical, %d warning",
                org_id,
                len(violations),
                sum(1 for v in violations if v.severity == SLASeverity.CRITICAL),
                sum(1 for v in violations if v.severity == SLASeverity.WARNING),
            )
        return violations

    async def _check_stale_leads(
        self, db: Session, org_id: int,
    ) -> List[SLAViolation]:
        """Find leads in 'New' stage with no activity past the SLA threshold."""
        from database.models.lead_loan import Lead

        violations: List[SLAViolation] = []
        now = datetime.now(timezone.utc)
        warning_cutoff = now - timedelta(hours=_STALE_LEAD_WARNING_HOURS)
        critical_cutoff = now - timedelta(hours=_STALE_LEAD_HOURS)

        try:
            stale_leads = (
                db.query(Lead)
                .filter(and_(
                    Lead.organization_id == org_id,
                    Lead.stage == "New",
                    Lead.deleted_at.is_(None),
                    Lead.created_at <= warning_cutoff,
                    # No contact attempt recorded
                    Lead.last_contact.is_(None),
                ))
                .all()
            )

            for lead in stale_leads:
                created = lead.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = (now - created).total_seconds() / 3600
                deadline = created + timedelta(hours=_STALE_LEAD_HOURS)

                if age_hours >= _STALE_LEAD_HOURS:
                    severity = SLASeverity.CRITICAL
                    msg = (
                        f"Lead '{lead.name}' has been in New stage for "
                        f"{age_hours:.0f}h with no contact (SLA: {_STALE_LEAD_HOURS}h)"
                    )
                else:
                    severity = SLASeverity.WARNING
                    msg = (
                        f"Lead '{lead.name}' approaching stale threshold — "
                        f"{age_hours:.0f}h in New stage (SLA: {_STALE_LEAD_HOURS}h)"
                    )

                violations.append(SLAViolation(
                    entity_type="lead",
                    entity_id=lead.id,
                    violation_type="stale_lead",
                    severity=severity,
                    message=msg,
                    deadline=deadline,
                    extra={"owner_id": lead.owner_id, "stage": lead.stage},
                ))
        except Exception as e:
            logger.exception("Failed to check stale leads for org %d: %s", org_id, e)

        return violations

    async def _check_overdue_conditions(
        self, db: Session, org_id: int,
    ) -> List[SLAViolation]:
        """Find loans dwelling too long in processing stages."""
        from database.models.lead_loan import Loan

        violations: List[SLAViolation] = []
        now = datetime.now(timezone.utc)

        try:
            # Query active (non-terminal) loans
            active_loans = (
                db.query(Loan)
                .filter(and_(
                    Loan.organization_id == org_id,
                    Loan.deleted_at.is_(None),
                    Loan.stage.notin_(_TERMINAL_STAGES),
                ))
                .all()
            )

            for loan in active_loans:
                stage = loan.stage
                if stage not in _STAGE_DWELL_THRESHOLDS:
                    continue

                threshold_hours = _STAGE_DWELL_THRESHOLDS[stage]
                entered_at = loan.stage_changed_at or loan.updated_at or loan.created_at
                if entered_at is None:
                    continue
                if entered_at.tzinfo is None:
                    entered_at = entered_at.replace(tzinfo=timezone.utc)

                dwell_hours = (now - entered_at).total_seconds() / 3600
                deadline = entered_at + timedelta(hours=threshold_hours)

                # Warning at 80% of threshold, critical at 100%
                if dwell_hours >= threshold_hours:
                    severity = SLASeverity.CRITICAL
                    msg = (
                        f"Loan #{loan.loan_number} has been in {stage} for "
                        f"{dwell_hours:.0f}h — exceeds SLA of {threshold_hours}h"
                    )
                elif dwell_hours >= threshold_hours * 0.8:
                    severity = SLASeverity.WARNING
                    msg = (
                        f"Loan #{loan.loan_number} approaching SLA in {stage} — "
                        f"{dwell_hours:.0f}h of {threshold_hours}h threshold"
                    )
                else:
                    continue

                violations.append(SLAViolation(
                    entity_type="loan",
                    entity_id=loan.id,
                    violation_type="stage_dwell_exceeded",
                    severity=severity,
                    message=msg,
                    deadline=deadline,
                    extra={
                        "loan_number": loan.loan_number,
                        "stage": stage,
                        "loan_officer_id": loan.loan_officer_id,
                        "dwell_hours": round(dwell_hours, 1),
                    },
                ))
        except Exception as e:
            logger.exception("Failed to check overdue conditions for org %d: %s", org_id, e)

        return violations

    async def _check_compliance_deadlines(
        self, db: Session, org_id: int,
    ) -> List[SLAViolation]:
        """Check TRID disclosure deadlines — initial disclosures must be sent
        within 3 business days of application receipt."""
        from database.models.lead_loan import Loan

        violations: List[SLAViolation] = []
        now = datetime.now(timezone.utc)

        try:
            # Loans with an application date but no initial disclosures sent
            loans_pending_disclosure = (
                db.query(Loan)
                .filter(and_(
                    Loan.organization_id == org_id,
                    Loan.deleted_at.is_(None),
                    Loan.application_date.isnot(None),
                    Loan.initial_disclosures_sent_date.is_(None),
                    Loan.stage.notin_(_TERMINAL_STAGES),
                ))
                .all()
            )

            for loan in loans_pending_disclosure:
                app_date = loan.application_date
                if app_date is None:
                    continue
                if app_date.tzinfo is None:
                    app_date = app_date.replace(tzinfo=timezone.utc)

                hours_since_app = (now - app_date).total_seconds() / 3600
                deadline = app_date + timedelta(hours=_TRID_DISCLOSURE_DEADLINE_HOURS)

                if hours_since_app >= _TRID_DISCLOSURE_DEADLINE_HOURS:
                    severity = SLASeverity.CRITICAL
                    msg = (
                        f"Loan #{loan.loan_number} — TRID initial disclosure deadline "
                        f"BREACHED. Application received {hours_since_app:.0f}h ago, "
                        f"disclosures not yet sent (deadline: {_TRID_DISCLOSURE_DEADLINE_HOURS}h)"
                    )
                elif hours_since_app >= _TRID_DISCLOSURE_WARNING_HOURS:
                    severity = SLASeverity.WARNING
                    msg = (
                        f"Loan #{loan.loan_number} — TRID disclosure deadline approaching. "
                        f"Application received {hours_since_app:.0f}h ago, "
                        f"disclosures due within {_TRID_DISCLOSURE_DEADLINE_HOURS}h"
                    )
                else:
                    continue

                violations.append(SLAViolation(
                    entity_type="loan",
                    entity_id=loan.id,
                    violation_type="trid_disclosure",
                    severity=severity,
                    message=msg,
                    deadline=deadline,
                    extra={
                        "loan_number": loan.loan_number,
                        "loan_officer_id": loan.loan_officer_id,
                        "application_date": app_date.isoformat(),
                        "hours_elapsed": round(hours_since_app, 1),
                    },
                ))
        except Exception as e:
            logger.exception("Failed to check compliance deadlines for org %d: %s", org_id, e)

        return violations
