"""
SOC 2 Compliance Scheduler — Daily automated scans and retention enforcement.
SOC 2 Criteria: CC3 (Risk Assessment), CC4 (Monitoring)

Provides:
1. Daily compliance scan (10 automated checks)
2. Daily retention policy enforcement
3. Weekly data classification audit
4. Admin endpoint for manual triggering
5. Alert emails on compliance scan failures

Integrates with the existing APScheduler-based scheduler_service.
"""
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger("soc2.scheduler")


def _get_session() -> Session:
    """Get a fresh sync session from the app's SessionLocal."""
    from db import SessionLocal
    return SessionLocal()


def _send_compliance_alert(failed_checks, warning_checks, total):
    """Send compliance scan failure alert via email and DataDog (best-effort)."""
    alert_email = os.getenv("SOC2_ALERT_EMAIL", "")

    # DataDog gauges
    try:
        from datadog import statsd
        statsd.gauge("soc2.compliance_scan.passed", total - len(failed_checks) - len(warning_checks))
        statsd.gauge("soc2.compliance_scan.failed", len(failed_checks))
        statsd.gauge("soc2.compliance_scan.warnings", len(warning_checks))
    except Exception as _exc:  # noqa: BLE001
        pass

    if not failed_checks:
        return

    # Build alert body
    failed_names = [c.get("check_name", "unknown") for c in failed_checks]
    warning_names = [c.get("check_name", "unknown") for c in warning_checks]
    subject = f"SOC 2 Compliance Alert: {len(failed_checks)} check(s) FAILED"
    body = (
        f"SOC 2 daily compliance scan completed with failures.\n\n"
        f"FAILED ({len(failed_checks)}):\n"
        + "\n".join(f"  - {name}" for name in failed_names)
        + (f"\n\nWARNINGS ({len(warning_checks)}):\n"
           + "\n".join(f"  - {name}" for name in warning_names)
           if warning_checks else "")
        + "\n\nPlease investigate and remediate."
    )

    if alert_email:
        try:
            from services.notification_service import NotificationService
            NotificationService.send_email(
                to_email=alert_email,
                subject=subject,
                body=body,
            )
            logger.info(f"SOC 2 compliance alert sent to {alert_email}")
        except Exception as e:
            logger.warning(f"Failed to send SOC 2 compliance alert email: {e}")

    # DataDog event for SIEM
    try:
        from datadog import statsd
        statsd.event(
            title=subject,
            text=body,
            alert_type="error",
            tags=["soc2:compliance_scan", f"failed:{len(failed_checks)}"],
        )
    except Exception as _exc:  # noqa: BLE001
        pass


def run_daily_compliance_scan():
    """
    Run all 10 SOC 2 compliance checks and store results.
    Scheduled daily at 02:15 UTC (off-peak).
    """
    session = _get_session()
    try:
        from soc2_compliance.scripts.compliance_scan import run_compliance_scan
        results = run_compliance_scan(session)

        passed = sum(1 for r in results if r.get("status") == "pass")
        failed = sum(1 for r in results if r.get("status") == "fail")
        warnings = sum(1 for r in results if r.get("status") == "warning")

        logger.info(
            f"SOC 2 daily scan complete: {passed} passed, {failed} failed, "
            f"{warnings} warnings out of {len(results)} checks"
        )

        # Alert on failures
        failed_checks = [r for r in results if r.get("status") == "fail"]
        warning_checks = [r for r in results if r.get("status") == "warning"]
        if failed_checks:
            _send_compliance_alert(failed_checks, warning_checks, len(results))

        return results
    except Exception as e:
        logger.error(f"SOC 2 daily scan failed: {e}")
        return []
    finally:
        session.close()


def run_retention_enforcement():
    """
    Enforce data retention policies — delete records past their retention window.
    Scheduled daily at 03:00 UTC (off-peak, after compliance scan).
    """
    session = _get_session()
    try:
        from soc2_compliance.services.retention_service import RetentionService
        svc = RetentionService(session)
        result = svc.enforce_retention_policies()

        total_deleted = sum(v for v in result.values() if isinstance(v, int) and v > 0)
        logger.info(
            f"SOC 2 retention enforcement complete: {total_deleted} records deleted "
            f"across {len(result)} policies"
        )
        return result
    except Exception as e:
        logger.error(f"SOC 2 retention enforcement failed: {e}")
        return []
    finally:
        session.close()


def run_data_classification_seed():
    """
    Re-seed / update data classification registry (idempotent).
    Scheduled weekly on Sunday at 04:00 UTC.
    """
    try:
        from soc2_compliance.scripts.seed_data_classification import seed_data_classification
        count = seed_data_classification()
        logger.info(f"SOC 2 data classification re-seeded: {count} entries")
        return count
    except Exception as e:
        logger.error(f"SOC 2 data classification seed failed: {e}")
        return 0


def register_soc2_jobs(scheduler):
    """
    Register SOC 2 compliance jobs with the app's APScheduler instance.

    Call from main.py startup:
        from soc2_compliance.scheduler import register_soc2_jobs
        register_soc2_jobs(scheduler)
    """
    from apscheduler.triggers.cron import CronTrigger

    # Daily compliance scan at 02:15 UTC
    scheduler.add_job(
        func=run_daily_compliance_scan,
        trigger=CronTrigger(hour=2, minute=15),
        id="soc2_daily_compliance_scan",
        name="SOC 2 Daily Compliance Scan",
        replace_existing=True,
    )

    # Daily retention enforcement at 03:00 UTC
    scheduler.add_job(
        func=run_retention_enforcement,
        trigger=CronTrigger(hour=3, minute=0),
        id="soc2_daily_retention",
        name="SOC 2 Daily Retention Enforcement",
        replace_existing=True,
    )

    # Weekly data classification re-seed on Sunday at 04:00 UTC
    scheduler.add_job(
        func=run_data_classification_seed,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="soc2_weekly_classification",
        name="SOC 2 Weekly Data Classification Update",
        replace_existing=True,
    )

    logger.info("SOC 2 compliance jobs registered (scan@02:15, retention@03:00, classification@Sun 04:00)")
