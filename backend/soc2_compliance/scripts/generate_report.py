"""
SOC 2 Evidence Report Generator

Generates a comprehensive compliance evidence report as JSON.
Can be extended to produce PDF output.

Usage:
    python -m soc2_compliance.scripts.generate_report --start 2025-01-01 --end 2025-12-31

Or programmatically:
    from soc2_compliance.scripts.generate_report import generate_weekly_report
    report = generate_weekly_report(db)
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from ..services.compliance_reporter import ComplianceReporter

logger = logging.getLogger("soc2.report_generator")


def generate_weekly_report(db: Session, tenant_id=None) -> dict:
    """
    Generate a weekly compliance evidence report.
    Intended to be called from a scheduled task.
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)

    reporter = ComplianceReporter(db)

    if tenant_id:
        report = reporter.generate_full_report(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
        )
    else:
        # If no tenant specified, generate a system-wide summary
        report = {
            "report_type": "weekly_system_compliance",
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "compliance_checks": reporter._compliance_check_results(start_date, end_date),
            "data_retention": reporter._retention_evidence(),
        }

    # Store report as JSON (could also write to S3, send via email, etc.)
    report_filename = f"soc2_report_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"

    logger.info(
        "compliance_report_generated",
        extra={
            "filename": report_filename,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }
    )

    return report


def generate_audit_period_report(
    db: Session,
    tenant_id,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """
    Generate a full audit period report for SOC 2 Type II examination.
    This is the primary deliverable for auditors.
    """
    reporter = ComplianceReporter(db)
    return reporter.generate_full_report(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )
