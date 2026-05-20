"""
Compliance Watchdog Agent

Proactive autonomous agent that scans all active loans for regulatory
compliance deadline violations. Runs on a schedule (e.g. hourly/daily)
and creates ComplianceAlert records for any issues found.

Checks implemented:
    1. TRID Initial Disclosure (3-business-day rule)
    2. TRID Closing Disclosure (3-day rule before consummation)
    3. ECOA Adverse Action (30-day notice rule)
    4. Stale/Abandoned Applications (30-day inactivity)
    5. Rate Lock Expiration (7-day warning window)
    6. Missing Documentation (underwriting+ stages)

Usage:
    from services.autonomous.compliance_watchdog import ComplianceWatchdogAgent

    agent = ComplianceWatchdogAgent(db=session, org_id=org.id)
    summary = await agent.run()
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from database.enums import DocumentType, RateLockStatus
from database.models.compliance import (
    AdverseActionNotice,
    ComplianceAlert,
    DisclosureEvent,
    DisclosureType,
)
from database.models.communication import Activity
from database.models.document import Document
from database.models.lead_loan import Lead, Loan
from database.models.rate_lock import RateLock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Stages where a closing disclosure should exist if closing is near
CD_REQUIRED_STAGES = frozenset({
    "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
})

# Stages at or beyond underwriting where core docs are expected
UW_PLUS_STAGES = frozenset({
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED",
    "SUSPENDED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
})

# Minimum document types expected before underwriting submission
REQUIRED_DOC_TYPES = frozenset({
    DocumentType.PAYSTUB,
    DocumentType.BANK_STATEMENT,
    DocumentType.DRIVERS_LICENSE,
    DocumentType.CREDIT_REPORT,
})

# Federal holidays (US) — simplified static set for the current year.
# In production this would be loaded from a config or holiday API.
_FEDERAL_HOLIDAYS: set[date] | None = None


def _get_federal_holidays(year: int) -> set[date]:
    """Return approximate US federal holidays for *year*.

    Covers the fixed holidays plus common observed-date rules. This is
    intentionally conservative — if a day might be a holiday, we include it
    so that business-day calculations err on the side of giving more time.
    """
    holidays = {
        date(year, 1, 1),    # New Year's Day
        date(year, 7, 4),    # Independence Day
        date(year, 11, 11),  # Veterans Day
        date(year, 12, 25),  # Christmas Day
    }
    # MLK Day — 3rd Monday of January
    jan1 = date(year, 1, 1)
    first_monday = jan1 + timedelta(days=(7 - jan1.weekday()) % 7)
    holidays.add(first_monday + timedelta(weeks=2))
    # Presidents' Day — 3rd Monday of February
    feb1 = date(year, 2, 1)
    first_monday = feb1 + timedelta(days=(7 - feb1.weekday()) % 7)
    holidays.add(first_monday + timedelta(weeks=2))
    # Memorial Day — last Monday of May
    may31 = date(year, 5, 31)
    holidays.add(may31 - timedelta(days=(may31.weekday()) % 7))
    # Labor Day — 1st Monday of September
    sep1 = date(year, 9, 1)
    first_monday = sep1 + timedelta(days=(7 - sep1.weekday()) % 7)
    holidays.add(first_monday)
    # Columbus Day — 2nd Monday of October
    oct1 = date(year, 10, 1)
    first_monday = oct1 + timedelta(days=(7 - oct1.weekday()) % 7)
    holidays.add(first_monday + timedelta(weeks=1))
    # Thanksgiving — 4th Thursday of November
    nov1 = date(year, 11, 1)
    first_thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    holidays.add(first_thursday + timedelta(weeks=3))
    return holidays


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ComplianceWatchdogAgent:
    """Autonomous agent that scans loans for compliance violations.

    Designed to be invoked from a scheduler (APScheduler / cron).  Each
    invocation runs all checks for a single organization and persists
    ComplianceAlert rows for anything that needs attention.  Existing
    unresolved alerts are never duplicated.
    """

    AGENT_TYPE = "compliance_watchdog"

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.gateway = gateway
        self.now = datetime.now(timezone.utc)
        self.today = self.now.date()
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """Execute all compliance checks and return an execution summary."""

        checks = [
            ("trid_initial_disclosure", self._check_trid_initial_disclosure),
            ("trid_closing_disclosure", self._check_trid_closing_disclosure),
            ("ecoa_adverse_action", self._check_ecoa_adverse_action),
            ("stale_applications", self._check_stale_applications),
            ("rate_lock_expirations", self._check_rate_lock_expirations),
            ("missing_documentation", self._check_missing_documentation),
        ]

        summary: dict[str, Any] = {
            "agent": self.AGENT_TYPE,
            "organization_id": self.org_id,
            "ran_at": self.now.isoformat(),
            "checks": {},
            "total_findings": 0,
            "errors": [],
        }

        for check_name, check_fn in checks:
            try:
                findings = check_fn()
                summary["checks"][check_name] = {
                    "findings": len(findings),
                    "details": findings,
                }
                summary["total_findings"] += len(findings)
            except Exception as e:
                self.logger.exception("Compliance check '%s' failed", check_name)
                summary["errors"].append({
                    "check": check_name,
                    "error": str(e),
                })

        try:
            self.db.commit()
        except Exception as e:
            self.logger.exception("Failed to commit compliance alerts")
            self.db.rollback()
            summary["errors"].append({"check": "commit", "error": str(e)})

        self.logger.info(
            "Compliance watchdog completed: %d findings, %d errors",
            summary["total_findings"],
            len(summary["errors"]),
        )
        return summary

    # ------------------------------------------------------------------
    # Check 1 — TRID Initial Disclosure (LE within 3 business days)
    # ------------------------------------------------------------------

    def _check_trid_initial_disclosure(self) -> list[dict]:
        """Loans in APPLICATION stage with no Loan Estimate sent within 3 business days."""

        findings: list[dict] = []

        loans = (
            self.db.query(Loan)
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage == "APPLICATION",
            )
            .all()
        )

        for loan in loans:
            # Determine application date — prefer explicit field, fall back to created_at
            app_date = loan.application_date or loan.created_at
            if app_date is None:
                continue

            app_date_d = app_date.date() if isinstance(app_date, datetime) else app_date

            # Check if an initial LE disclosure already exists
            existing_le = (
                self.db.query(DisclosureEvent)
                .filter(
                    DisclosureEvent.loan_id == loan.id,
                    DisclosureEvent.organization_id == self.org_id,
                    DisclosureEvent.disclosure_type == DisclosureType.LOAN_ESTIMATE,
                    DisclosureEvent.sent_at.isnot(None),
                )
                .first()
            )
            if existing_le:
                continue

            biz_days = self._calculate_business_days(app_date_d, self.today)
            deadline_date = self._add_business_days(app_date_d, 3)

            if biz_days > 3:
                severity = "critical"
                message = (
                    f"TRID violation: Initial Loan Estimate not sent. "
                    f"Application date {app_date_d.isoformat()}, "
                    f"{biz_days} business days elapsed (3-day limit)."
                )
            elif biz_days >= 2:
                severity = "warning"
                message = (
                    f"TRID warning: Initial Loan Estimate due by "
                    f"{deadline_date.isoformat()}. "
                    f"{biz_days} of 3 business days elapsed."
                )
            else:
                continue

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="trid_le_deadline",
                severity=severity,
                title="Initial Loan Estimate overdue" if severity == "critical" else "Initial Loan Estimate due soon",
                message=message,
                deadline_date=deadline_date,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "severity": severity,
                    "business_days_elapsed": biz_days,
                    "alert_id": alert.id if alert.id else None,
                })

        return findings

    # ------------------------------------------------------------------
    # Check 2 — TRID Closing Disclosure (3 days before closing)
    # ------------------------------------------------------------------

    def _check_trid_closing_disclosure(self) -> list[dict]:
        """Loans near closing with no Closing Disclosure sent."""

        findings: list[dict] = []

        loans = (
            self.db.query(Loan)
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage.in_(CD_REQUIRED_STAGES),
                Loan.closing_date.isnot(None),
            )
            .all()
        )

        for loan in loans:
            closing_d = (
                loan.closing_date.date()
                if isinstance(loan.closing_date, datetime)
                else loan.closing_date
            )

            # CD must be delivered 3 business days before closing
            cd_deadline = self._subtract_business_days(closing_d, 3)
            days_until_deadline = (cd_deadline - self.today).days

            # Only flag if deadline is within 10 calendar days or already passed
            if days_until_deadline > 10:
                continue

            existing_cd = (
                self.db.query(DisclosureEvent)
                .filter(
                    DisclosureEvent.loan_id == loan.id,
                    DisclosureEvent.organization_id == self.org_id,
                    DisclosureEvent.disclosure_type == DisclosureType.CLOSING_DISCLOSURE,
                    DisclosureEvent.sent_at.isnot(None),
                )
                .first()
            )
            if existing_cd:
                continue

            if days_until_deadline < 0:
                severity = "critical"
                message = (
                    f"TRID violation: Closing Disclosure not sent. "
                    f"Closing date {closing_d.isoformat()}, CD was due by "
                    f"{cd_deadline.isoformat()} ({abs(days_until_deadline)} days overdue)."
                )
            elif days_until_deadline <= 3:
                severity = "warning"
                message = (
                    f"TRID warning: Closing Disclosure must be sent by "
                    f"{cd_deadline.isoformat()} (closing {closing_d.isoformat()}). "
                    f"{days_until_deadline} days remaining."
                )
            else:
                severity = "info"
                message = (
                    f"Closing Disclosure should be prepared soon. "
                    f"Closing {closing_d.isoformat()}, CD deadline "
                    f"{cd_deadline.isoformat()}."
                )

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="trid_cd_deadline",
                severity=severity,
                title="Closing Disclosure overdue" if severity == "critical" else "Closing Disclosure due soon",
                message=message,
                deadline_date=cd_deadline,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "severity": severity,
                    "closing_date": closing_d.isoformat(),
                    "cd_deadline": cd_deadline.isoformat(),
                    "days_until_deadline": days_until_deadline,
                })

        return findings

    # ------------------------------------------------------------------
    # Check 3 — ECOA Adverse Action (30-day notice after denial)
    # ------------------------------------------------------------------

    def _check_ecoa_adverse_action(self) -> list[dict]:
        """Denied loans without a timely adverse action notice."""

        findings: list[dict] = []

        denied_loans = (
            self.db.query(Loan)
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage == "DENIED",
            )
            .all()
        )

        for loan in denied_loans:
            # When was the loan denied? Use stage_changed_at or updated_at.
            denial_date = loan.stage_changed_at or loan.updated_at or loan.created_at
            if denial_date is None:
                continue
            denial_d = denial_date.date() if isinstance(denial_date, datetime) else denial_date
            deadline = denial_d + timedelta(days=30)

            # Check if an adverse action notice exists
            existing_notice = (
                self.db.query(AdverseActionNotice)
                .filter(
                    AdverseActionNotice.loan_id == loan.id,
                    AdverseActionNotice.organization_id == self.org_id,
                )
                .first()
            )
            if existing_notice and existing_notice.notice_sent_date is not None:
                continue

            days_since_denial = (self.today - denial_d).days
            days_remaining = (deadline - self.today).days

            if days_remaining < 0:
                severity = "critical"
                message = (
                    f"ECOA violation: Adverse action notice not sent. "
                    f"Denial date {denial_d.isoformat()}, 30-day deadline "
                    f"was {deadline.isoformat()} ({abs(days_remaining)} days overdue)."
                )
            elif days_remaining <= 7:
                severity = "warning"
                message = (
                    f"ECOA warning: Adverse action notice due by "
                    f"{deadline.isoformat()} ({days_remaining} days remaining). "
                    f"Denial date {denial_d.isoformat()}."
                )
            elif days_remaining <= 14:
                severity = "info"
                message = (
                    f"Adverse action notice should be prepared. "
                    f"Due by {deadline.isoformat()} ({days_remaining} days). "
                    f"Denial date {denial_d.isoformat()}."
                )
            else:
                continue

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="ecoa_adverse_action",
                severity=severity,
                title="Adverse action notice overdue" if severity == "critical" else "Adverse action notice due",
                message=message,
                deadline_date=deadline,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "severity": severity,
                    "denial_date": denial_d.isoformat(),
                    "deadline": deadline.isoformat(),
                    "days_remaining": days_remaining,
                })

        return findings

    # ------------------------------------------------------------------
    # Check 4 — Stale / Abandoned Applications
    # ------------------------------------------------------------------

    def _check_stale_applications(self) -> list[dict]:
        """Applications with no activity in 30+ days — may need withdrawal notice."""

        findings: list[dict] = []
        stale_days = self.config.get("stale_application_days", 30)
        cutoff = self.now - timedelta(days=stale_days)

        # Loans in APPLICATION or DISCLOSED with no recent activity
        stale_loans = (
            self.db.query(Loan)
            .outerjoin(
                Activity,
                and_(
                    Activity.loan_id == Loan.id,
                    Activity.created_at > cutoff,
                ),
            )
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage.in_({"APPLICATION", "DISCLOSED"}),
                Activity.id.is_(None),
                Loan.created_at < cutoff,
            )
            .all()
        )

        for loan in stale_loans:
            # Find the most recent activity to report staleness accurately
            last_activity = (
                self.db.query(func.max(Activity.created_at))
                .filter(Activity.loan_id == loan.id)
                .scalar()
            )
            last_touch = last_activity or loan.created_at
            if isinstance(last_touch, datetime):
                days_inactive = (self.now - last_touch).days
            else:
                days_inactive = (self.today - last_touch).days

            severity = "warning" if days_inactive >= stale_days else "info"
            message = (
                f"Loan {loan.loan_number} in {loan.stage} stage has had "
                f"no activity for {days_inactive} days. Consider issuing "
                f"a withdrawal notice or re-engaging the borrower."
            )

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="stale_application",
                severity=severity,
                title=f"Stale application ({days_inactive} days inactive)",
                message=message,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "severity": severity,
                    "days_inactive": days_inactive,
                    "stage": loan.stage,
                })

        return findings

    # ------------------------------------------------------------------
    # Check 5 — Rate Lock Expirations
    # ------------------------------------------------------------------

    def _check_rate_lock_expirations(self) -> list[dict]:
        """Rate locks expiring within 7 days on non-closed loans."""

        findings: list[dict] = []
        warning_days = self.config.get("rate_lock_warning_days", 7)
        horizon = self.now + timedelta(days=warning_days)

        expiring_locks = (
            self.db.query(RateLock)
            .join(Loan, Loan.id == RateLock.loan_id)
            .filter(
                RateLock.organization_id == self.org_id,
                RateLock.status == RateLockStatus.LOCKED,
                RateLock.lock_expiration_date.isnot(None),
                RateLock.lock_expiration_date <= horizon,
                Loan.stage.notin_(TERMINAL_STAGES),
            )
            .all()
        )

        for lock in expiring_locks:
            exp_date = lock.lock_expiration_date
            if isinstance(exp_date, datetime):
                days_until = (exp_date - self.now).days
                exp_date_d = exp_date.date()
            else:
                days_until = (exp_date - self.today).days
                exp_date_d = exp_date

            if days_until < 0:
                severity = "critical"
                message = (
                    f"Rate lock expired {abs(days_until)} day(s) ago "
                    f"on {exp_date_d.isoformat()}. Rate: {lock.rate_locked}%. "
                    f"Extension or re-lock required."
                )
            elif days_until <= 3:
                severity = "warning"
                message = (
                    f"Rate lock expires in {days_until} day(s) "
                    f"on {exp_date_d.isoformat()}. Rate: {lock.rate_locked}%. "
                    f"Plan extension or ensure closing is scheduled."
                )
            else:
                severity = "info"
                message = (
                    f"Rate lock expires in {days_until} days "
                    f"on {exp_date_d.isoformat()}. Rate: {lock.rate_locked}%."
                )

            # Look up the loan for the alert
            loan = self.db.query(Loan).get(lock.loan_id)
            if not loan:
                continue

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="rate_lock_expiration",
                severity=severity,
                title=f"Rate lock {'expired' if days_until < 0 else 'expiring soon'}",
                message=message,
                deadline_date=exp_date_d,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "rate_lock_id": lock.id,
                    "severity": severity,
                    "expiration_date": exp_date_d.isoformat(),
                    "days_until_expiration": days_until,
                    "rate": str(lock.rate_locked) if lock.rate_locked else None,
                })

        return findings

    # ------------------------------------------------------------------
    # Check 6 — Missing Documentation
    # ------------------------------------------------------------------

    def _check_missing_documentation(self) -> list[dict]:
        """Loans in underwriting+ stages without core required documents."""

        findings: list[dict] = []

        loans = (
            self.db.query(Loan)
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage.in_(UW_PLUS_STAGES),
            )
            .all()
        )

        for loan in loans:
            existing_types = set(
                self.db.query(Document.doc_type)
                .filter(
                    Document.loan_id == loan.id,
                    Document.status == "active",
                )
                .all()
            )
            # Query returns list of tuples; flatten
            existing_types = {t[0] for t in existing_types}

            missing = REQUIRED_DOC_TYPES - existing_types
            if not missing:
                continue

            missing_names = sorted(dt.value for dt in missing)
            severity = "warning" if len(missing) >= 2 else "info"
            message = (
                f"Loan {loan.loan_number} in {loan.stage} is missing "
                f"{len(missing)} required document(s): {', '.join(missing_names)}."
            )

            alert = self._create_compliance_alert(
                loan=loan,
                alert_type="missing_documentation",
                severity=severity,
                title=f"Missing {len(missing)} document(s) for underwriting",
                message=message,
            )
            if alert:
                findings.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "severity": severity,
                    "missing_documents": missing_names,
                })

        return findings

    # ------------------------------------------------------------------
    # Alert creation (de-duplicated)
    # ------------------------------------------------------------------

    def _create_compliance_alert(
        self,
        loan: Loan,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        deadline_date: date | None = None,
    ) -> ComplianceAlert | None:
        """Create a ComplianceAlert if one doesn't already exist (open) for this loan+type."""

        existing = (
            self.db.query(ComplianceAlert)
            .filter(
                ComplianceAlert.loan_id == loan.id,
                ComplianceAlert.organization_id == self.org_id,
                ComplianceAlert.alert_type == alert_type,
                ComplianceAlert.status == "open",
            )
            .first()
        )
        if existing:
            # Update severity if it escalated
            if _severity_rank(severity) > _severity_rank(existing.severity):
                existing.severity = severity
                existing.title = title
                existing.description = message
                if deadline_date:
                    existing.days_remaining = (deadline_date - self.today).days
                self.logger.info(
                    "Escalated alert %d for loan %d (%s -> %s)",
                    existing.id, loan.id, existing.severity, severity,
                )
            return existing

        days_remaining = (deadline_date - self.today).days if deadline_date else None

        alert = ComplianceAlert(
            organization_id=self.org_id,
            loan_id=loan.id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=message,
            deadline_date=deadline_date,
            days_remaining=days_remaining,
            status="open",
        )
        if self.gateway:
            self.gateway.propose(
                "create_compliance_alert",
                lambda: (self.db.add(alert), self.db.flush()),
                target_entity="loan",
                target_id=loan.id,
                description=f"{alert_type}: {title}",
                payload={"severity": severity, "alert_type": alert_type},
            )
        else:
            self.db.add(alert)
            self.db.flush()
        self.logger.info(
            "Created compliance alert %d: %s [%s] for loan %d",
            alert.id, alert_type, severity, loan.id,
        )
        return alert

    # ------------------------------------------------------------------
    # Business-day arithmetic
    # ------------------------------------------------------------------

    def _calculate_business_days(self, start: date, end: date) -> int:
        """Count business days between *start* (exclusive) and *end* (inclusive).

        Excludes weekends and US federal holidays.
        """
        if end <= start:
            return 0

        holidays = self._holidays_for_range(start, end)
        count = 0
        current = start + timedelta(days=1)
        while current <= end:
            if current.weekday() < 5 and current not in holidays:
                count += 1
            current += timedelta(days=1)
        return count

    def _add_business_days(self, start: date, days: int) -> date:
        """Return the date that is *days* business days after *start*."""
        holidays = self._holidays_for_range(start, start + timedelta(days=days * 3))
        current = start
        added = 0
        while added < days:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in holidays:
                added += 1
        return current

    def _subtract_business_days(self, end: date, days: int) -> date:
        """Return the date that is *days* business days before *end*."""
        holidays = self._holidays_for_range(end - timedelta(days=days * 3), end)
        current = end
        subtracted = 0
        while subtracted < days:
            current -= timedelta(days=1)
            if current.weekday() < 5 and current not in holidays:
                subtracted += 1
        return current

    def _holidays_for_range(self, start: date, end: date) -> set[date]:
        """Collect federal holidays for all years spanned by *start* .. *end*."""
        years = set(range(start.year, end.year + 1))
        holidays: set[date] = set()
        for y in years:
            holidays |= _get_federal_holidays(y)
        return holidays


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, -1)
