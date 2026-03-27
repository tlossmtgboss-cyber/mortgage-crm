"""
Scheduled Celery tasks for data retention policy enforcement.

Replaces the undecorated functions in sla_tasks.py with proper Celery
task registrations. Runs both CRM data retention and SOC 2 retention
enforcement.

Schedule (configured in celery_app.py beat_schedule):
    - Daily at 2:00 AM UTC: CRM data retention enforcement
    - Daily at 3:00 AM UTC: SOC 2 data retention enforcement
    - Weekly Sunday 3:30 AM UTC: Full retention report (logged)

Usage:
    # Start worker
    celery -A tasks.celery_app worker -l info

    # Start beat scheduler
    celery -A tasks.celery_app beat -l info

    # Manual trigger via Python
    from tasks.data_retention_tasks import enforce_data_retention
    enforce_data_retention.delay(dry_run=False)
"""

import logging
from datetime import datetime, timezone

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.data_retention_tasks.enforce_data_retention",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
    soft_time_limit=540,
    time_limit=600,
)
def enforce_data_retention(self, dry_run: bool = False):
    """
    Run all CRM data retention policies.

    Processes each table according to retention periods defined in
    services/data_retention.py. Records past their retention date are:
    - Hard deleted if they contain no regulatory data
    - PII-redacted if they contain communication data (SMS, email)
    - Skipped if they are in NEVER_PURGE_TABLES (audit_logs, etc.)

    Scheduled daily at 2:00 AM UTC. Can also be triggered manually via
    the admin endpoint POST /api/v1/admin/dr/retention-cleanup.

    This is a cross-tenant admin operation. RLS context is not set
    because the service internally iterates over all organizations.

    Args:
        dry_run: If True, report what would be cleaned without acting.

    Returns:
        Dict with cleanup results per table.
    """
    from db import SessionLocal
    from services.data_retention import DataRetentionService

    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting CRM data retention enforcement (dry_run={dry_run})")

    db = SessionLocal()
    try:
        service = DataRetentionService(db)
        result = service.run_retention_cleanup(dry_run=dry_run)

        total_affected = result.get("total_records_affected", 0)
        tables_count = len(result.get("tables_processed", []))
        errors = result.get("errors", [])

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"CRM data retention complete in {elapsed:.1f}s: "
            f"{total_affected} records affected across {tables_count} tables, "
            f"{len(errors)} errors (dry_run={dry_run})"
        )

        result["elapsed_seconds"] = round(elapsed, 2)
        return result

    except Exception as e:
        logger.exception(f"CRM data retention task failed: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(
    name="tasks.data_retention_tasks.enforce_soc2_retention",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
    soft_time_limit=540,
    time_limit=600,
)
def enforce_soc2_retention(self):
    """
    Run SOC 2 data retention policy enforcement.

    Enforces retention on SOC 2 compliance tables:
    - soc2_audit_log (730 days)
    - soc2_access_event (730 days)
    - soc2_security_incident (1095 days)
    - soc2_change_record (730 days)
    - soc2_compliance_check (730 days)
    - soc2_incident_timeline (1095 days)

    Records are archived to soc2_retention_archive before deletion.
    Scheduled daily at 3:00 AM UTC.

    Returns:
        Dict mapping policy name to count of records deleted.
    """
    from db import SessionLocal

    start_time = datetime.now(timezone.utc)
    logger.info("Starting SOC 2 data retention enforcement")

    db = SessionLocal()
    try:
        from soc2_compliance.services.retention_service import RetentionService

        service = RetentionService(db)
        result = service.enforce_retention_policies()

        total_deleted = sum(
            v for v in result.values() if isinstance(v, int) and v > 0
        )
        error_count = sum(
            1 for v in result.values() if isinstance(v, int) and v < 0
        )

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"SOC 2 retention complete in {elapsed:.1f}s: "
            f"{total_deleted} records deleted across {len(result)} policies, "
            f"{error_count} errors"
        )

        return {
            "policies": result,
            "total_deleted": total_deleted,
            "error_count": error_count,
            "elapsed_seconds": round(elapsed, 2),
            "run_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.exception(f"SOC 2 retention task failed: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(
    name="tasks.data_retention_tasks.generate_retention_report",
    bind=True,
    max_retries=1,
    acks_late=True,
    soft_time_limit=300,
    time_limit=360,
)
def generate_retention_report(self):
    """
    Generate a comprehensive data retention report across all systems.

    Combines CRM retention preview with SOC 2 retention status into
    a single report. This is equivalent to a dry-run of enforcement.
    Scheduled weekly for audit purposes; also available via the admin
    endpoint GET /api/v1/admin/data-retention/report.

    Returns:
        Dict with per-table retention status for both CRM and SOC 2.
    """
    from db import SessionLocal

    start_time = datetime.now(timezone.utc)
    logger.info("Generating data retention report")

    db = SessionLocal()
    try:
        report = {
            "generated_at": start_time.isoformat(),
            "crm": {},
            "soc2": {},
        }

        # CRM retention preview (dry run)
        try:
            from services.data_retention import DataRetentionService

            crm_service = DataRetentionService(db)
            crm_result = crm_service.run_retention_cleanup(dry_run=True)
            report["crm"] = {
                "tables_processed": crm_result.get("tables_processed", []),
                "total_eligible": crm_result.get("total_records_affected", 0),
            }
        except Exception as e:
            logger.warning(f"CRM retention report failed: {e}")
            report["crm"] = {"error": str(e)}

        # SOC 2 retention preview
        try:
            from soc2_compliance.services.retention_service import RetentionService

            soc2_service = RetentionService(db)
            soc2_preview = soc2_service.preview_retention_enforcement()
            soc2_status = soc2_service.get_retention_status()
            report["soc2"] = {
                "preview": soc2_preview,
                "status": soc2_status,
            }
        except Exception as e:
            logger.warning(f"SOC 2 retention report failed: {e}")
            report["soc2"] = {"error": str(e)}

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        report["elapsed_seconds"] = round(elapsed, 2)

        logger.info(
            f"Retention report generated in {elapsed:.1f}s: "
            f"CRM={report['crm'].get('total_eligible', 'N/A')} eligible, "
            f"SOC2={len(report['soc2'].get('preview', {}))} tables"
        )

        return report

    except Exception as e:
        logger.exception(f"Retention report generation failed: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(
    name="tasks.data_retention_tasks.verify_backup_integrity",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=300,
    time_limit=360,
)
def verify_backup_integrity(self):
    """
    Verify backup integrity and RPO compliance.

    Runs daily backup verification and records results for audit.
    Scheduled daily at 5:00 AM UTC.

    Returns:
        Dict with backup verification status and RPO compliance.
    """
    from db import SessionLocal

    start_time = datetime.now(timezone.utc)
    logger.info("Starting backup integrity verification")

    db = SessionLocal()
    try:
        from services.backup_service import BackupVerificationService

        service = BackupVerificationService(db)
        backup_status = service.verify_latest_backup()
        integrity = service.verify_backup_integrity()
        service.record_verification(backup_status, integrity)

        is_compliant = backup_status.get("rpo_compliant", False)
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        logger.info(
            f"Backup verification complete in {elapsed:.1f}s: "
            f"status={backup_status.get('status')}, RPO compliant={is_compliant}"
        )

        return {
            "status": backup_status.get("status"),
            "rpo_compliant": is_compliant,
            "elapsed_seconds": round(elapsed, 2),
            "run_at": start_time.isoformat(),
        }

    except Exception as e:
        logger.exception(f"Backup verification task failed: {e}")
        raise self.retry(exc=e)
    finally:
        db.close()
