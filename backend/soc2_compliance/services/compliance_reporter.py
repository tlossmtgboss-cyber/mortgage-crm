"""
Compliance Reporter — SOC 2 evidence and report generation.
SOC 2 Criteria: All — Cross-cutting evidence collection

Generates comprehensive compliance reports with evidence for SOC 2 Type II audits.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("soc2.reporting")


class ComplianceReporter:
    """
    Generate SOC 2 compliance evidence reports.

    Usage:
        reporter = ComplianceReporter(db)
        report = reporter.generate_full_report(
            tenant_id=tenant_id,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
        )
    """

    def __init__(self, db: Session):
        self.db = db

    def generate_full_report(
        self,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Generate a comprehensive SOC 2 compliance report."""
        report = {
            "report_metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "tenant_id": str(tenant_id),
                "period_start": start_date.isoformat(),
                "period_end": end_date.isoformat(),
                "report_type": "SOC 2 Type II Evidence Report",
            },
            "executive_summary": self._executive_summary(tenant_id, start_date, end_date),
            "cc6_access_controls": self._access_control_evidence(tenant_id, start_date, end_date),
            "cc7_incident_response": self._incident_evidence(tenant_id, start_date, end_date),
            "cc8_change_management": self._change_management_evidence(tenant_id, start_date, end_date),
            "c1_confidentiality": self._confidentiality_evidence(tenant_id, start_date, end_date),
            "cc4_monitoring": self._monitoring_evidence(tenant_id, start_date, end_date),
            "a1_availability": self._availability_evidence(tenant_id, start_date, end_date),
            "p1_privacy": self._privacy_evidence(tenant_id, start_date, end_date),
            "compliance_checks": self._compliance_check_results(start_date, end_date),
            "data_retention": self._retention_evidence(),
        }

        return report

    def _executive_summary(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """High-level summary stats."""
        # Audit stats
        audit_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_audit_events,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(*) FILTER (WHERE severity IN ('high', 'critical')) as high_severity_events,
                    COUNT(*) FILTER (WHERE contains_pii = TRUE) as pii_events
                FROM soc2_audit_log
                WHERE tenant_id = :tid AND timestamp BETWEEN :s AND :e
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )
        audit = dict(audit_result.fetchone()._mapping)

        # Access stats
        access_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE success = TRUE AND event_type = 'login') as successful_logins,
                    COUNT(*) FILTER (WHERE success = FALSE) as failed_logins,
                    COUNT(*) FILTER (WHERE is_anomalous = TRUE) as anomalous_events
                FROM soc2_access_event
                WHERE tenant_id = :tid AND timestamp BETWEEN :s AND :e
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )
        access = dict(access_result.fetchone()._mapping)

        # Incident stats
        incident_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_incidents,
                    COUNT(*) FILTER (WHERE severity IN ('high', 'critical')) as critical_incidents,
                    COUNT(*) FILTER (WHERE data_compromised = TRUE) as data_breaches,
                    COUNT(*) FILTER (WHERE status = 'closed') as resolved_incidents
                FROM soc2_security_incident
                WHERE tenant_id = :tid AND created_at BETWEEN :s AND :e
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )
        incidents = dict(incident_result.fetchone()._mapping)

        # Change stats
        change_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_changes,
                    COUNT(*) FILTER (WHERE status = 'completed' AND success = TRUE) as successful_changes,
                    COUNT(*) FILTER (WHERE status = 'rolled_back') as rollbacks
                FROM soc2_change_record
                WHERE tenant_id = :tid AND created_at BETWEEN :s AND :e
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )
        changes = dict(change_result.fetchone()._mapping)

        return {
            "audit": audit,
            "access": access,
            "incidents": incidents,
            "changes": changes,
        }

    def _access_control_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """CC6 — Access control evidence."""
        # Failed login trends (by week)
        failed_trends = self.db.execute(
            text("""
                SELECT
                    DATE_TRUNC('week', timestamp) as week,
                    COUNT(*) as failed_logins,
                    COUNT(DISTINCT attempted_email) as unique_accounts,
                    COUNT(DISTINCT ip_address) as unique_ips
                FROM soc2_access_event
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                  AND success = FALSE
                GROUP BY DATE_TRUNC('week', timestamp)
                ORDER BY week
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Account lockout events
        lockouts = self.db.execute(
            text("""
                SELECT timestamp, attempted_email, ip_address, failure_reason
                FROM soc2_access_event
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                  AND event_type = 'account_locked'
                ORDER BY timestamp DESC
                LIMIT 100
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "failed_login_trends": [dict(row._mapping) for row in failed_trends.fetchall()],
            "lockout_events": [dict(row._mapping) for row in lockouts.fetchall()],
        }

    def _incident_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """CC7 — Incident response evidence."""
        incidents = self.db.execute(
            text("""
                SELECT id, title, category, severity, status,
                       detected_at, contained_at, resolved_at, closed_at,
                       data_compromised, pii_involved,
                       root_cause IS NOT NULL as has_root_cause,
                       post_mortem_completed
                FROM soc2_security_incident
                WHERE tenant_id = :tid AND created_at BETWEEN :s AND :e
                ORDER BY created_at DESC
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Mean time to contain / resolve
        mttr = self.db.execute(
            text("""
                SELECT
                    AVG(EXTRACT(EPOCH FROM (contained_at - detected_at))/3600)
                        FILTER (WHERE contained_at IS NOT NULL) as avg_hours_to_contain,
                    AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))/3600)
                        FILTER (WHERE resolved_at IS NOT NULL) as avg_hours_to_resolve
                FROM soc2_security_incident
                WHERE tenant_id = :tid AND created_at BETWEEN :s AND :e
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "incidents": [dict(row._mapping) for row in incidents.fetchall()],
            "response_times": dict(mttr.fetchone()._mapping),
        }

    def _change_management_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """CC8 — Change management evidence."""
        changes = self.db.execute(
            text("""
                SELECT id, title, change_type, status, risk_level,
                       requested_by, approved_by, implemented_by,
                       approved_at, implemented_at, verified_at,
                       success, git_commit, pull_request_url
                FROM soc2_change_record
                WHERE tenant_id = :tid AND created_at BETWEEN :s AND :e
                ORDER BY created_at DESC
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Unauthorized changes (implemented without approval)
        unauthorized = self.db.execute(
            text("""
                SELECT COUNT(*) FROM soc2_change_record
                WHERE tenant_id = :tid
                  AND created_at BETWEEN :s AND :e
                  AND status = 'completed'
                  AND approved_by IS NULL
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "changes": [dict(row._mapping) for row in changes.fetchall()],
            "unauthorized_changes": unauthorized.fetchone()[0],
        }

    def _confidentiality_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """C1 — Confidentiality / encryption evidence."""
        # PII access audit
        pii_access = self.db.execute(
            text("""
                SELECT
                    user_email, action, resource_type,
                    COUNT(*) as access_count,
                    array_agg(DISTINCT unnest_field) as fields
                FROM soc2_audit_log
                LEFT JOIN LATERAL unnest(fields_accessed) as unnest_field ON TRUE
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                  AND contains_pii = TRUE
                  AND fields_accessed IS NOT NULL
                GROUP BY user_email, action, resource_type
                ORDER BY access_count DESC
                LIMIT 50
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Data classification coverage
        classification = self.db.execute(
            text("""
                SELECT
                    classification,
                    COUNT(*) as column_count,
                    COUNT(*) FILTER (WHERE is_encrypted = TRUE) as encrypted_count,
                    COUNT(*) FILTER (WHERE is_pii = TRUE) as pii_count
                FROM soc2_data_classification
                GROUP BY classification
            """)
        )

        return {
            "pii_access_summary": [dict(row._mapping) for row in pii_access.fetchall()],
            "data_classification": [dict(row._mapping) for row in classification.fetchall()],
        }

    def _monitoring_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """CC4 — Monitoring evidence."""
        # Audit volume trends
        trends = self.db.execute(
            text("""
                SELECT
                    DATE_TRUNC('day', timestamp) as day,
                    COUNT(*) as events,
                    COUNT(*) FILTER (WHERE severity IN ('high', 'critical')) as high_severity
                FROM soc2_audit_log
                WHERE tenant_id = :tid AND timestamp BETWEEN :s AND :e
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY day
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "daily_event_trends": [dict(row._mapping) for row in trends.fetchall()],
        }

    def _availability_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """A1 — Availability evidence: rate limits, incident impact, response times."""
        # Rate limit events (429 responses in audit log)
        rate_limit_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_429s,
                    COUNT(DISTINCT ip_address) as unique_ips,
                    DATE_TRUNC('day', timestamp) as day
                FROM soc2_audit_log
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                  AND status_code = 429
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY day
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Response time distribution from audit log
        response_times = self.db.execute(
            text("""
                SELECT
                    DATE_TRUNC('day', timestamp) as day,
                    COUNT(*) as total_requests,
                    COUNT(*) FILTER (WHERE status_code >= 500) as server_errors
                FROM soc2_audit_log
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                GROUP BY DATE_TRUNC('day', timestamp)
                ORDER BY day
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        # Incidents affecting availability
        availability_incidents = self.db.execute(
            text("""
                SELECT id::text, title, severity, status, detected_at, resolved_at,
                       affected_users
                FROM soc2_security_incident
                WHERE tenant_id = :tid
                  AND created_at BETWEEN :s AND :e
                  AND 'application' = ANY(affected_systems)
                ORDER BY created_at DESC
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "rate_limit_events": [dict(row._mapping) for row in rate_limit_result.fetchall()],
            "daily_request_summary": [dict(row._mapping) for row in response_times.fetchall()],
            "availability_incidents": [dict(row._mapping) for row in availability_incidents.fetchall()],
        }

    def _privacy_evidence(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> Dict:
        """P1-P8 — Privacy evidence: PII classification, retention, access patterns."""
        # PII classification coverage
        classification_result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_classified,
                    COUNT(*) FILTER (WHERE is_pii = TRUE) as pii_columns,
                    COUNT(*) FILTER (WHERE is_pii = TRUE AND is_encrypted = TRUE) as pii_encrypted,
                    COUNT(*) FILTER (WHERE retention_policy IS NOT NULL) as with_retention_policy
                FROM soc2_data_classification
            """)
        )
        classification = dict(classification_result.fetchone()._mapping)

        # Retention enforcement results (from audit log)
        retention_result = self.db.execute(
            text("""
                SELECT timestamp, new_values, description
                FROM soc2_audit_log
                WHERE action = 'retention_enforcement'
                  AND timestamp BETWEEN :s AND :e
                ORDER BY timestamp DESC
                LIMIT 30
            """),
            {"s": start, "e": end}
        )

        # PII access by user role
        pii_by_role = self.db.execute(
            text("""
                SELECT
                    user_role,
                    COUNT(*) as pii_access_count,
                    COUNT(DISTINCT user_id) as unique_users
                FROM soc2_audit_log
                WHERE tenant_id = :tid
                  AND timestamp BETWEEN :s AND :e
                  AND contains_pii = TRUE
                GROUP BY user_role
                ORDER BY pii_access_count DESC
            """),
            {"tid": str(tenant_id), "s": start, "e": end}
        )

        return {
            "data_classification_coverage": classification,
            "retention_enforcement_history": [dict(row._mapping) for row in retention_result.fetchall()],
            "pii_access_by_role": [dict(row._mapping) for row in pii_by_role.fetchall()],
        }

    def _compliance_check_results(
        self, start: datetime, end: datetime
    ) -> Dict:
        """Automated compliance check results."""
        checks = self.db.execute(
            text("""
                SELECT check_name, check_category, status, trust_criteria,
                       details, run_at, remediation_required, remediated_at
                FROM soc2_compliance_check
                WHERE run_at BETWEEN :s AND :e
                ORDER BY run_at DESC
            """),
            {"s": start, "e": end}
        )

        # Pass rate
        pass_rate = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'pass') as passed,
                    COUNT(*) FILTER (WHERE status = 'fail') as failed,
                    COUNT(*) FILTER (WHERE status = 'warning') as warnings
                FROM soc2_compliance_check
                WHERE run_at BETWEEN :s AND :e
            """),
            {"s": start, "e": end}
        )

        return {
            "checks": [dict(row._mapping) for row in checks.fetchall()],
            "summary": dict(pass_rate.fetchone()._mapping),
        }

    def _retention_evidence(self) -> Dict:
        """Data retention compliance evidence."""
        tables = [
            ("soc2_audit_log", "timestamp"),
            ("soc2_access_event", "timestamp"),
            ("soc2_security_incident", "created_at"),
            ("soc2_change_record", "created_at"),
        ]

        status = {}
        for table, ts_col in tables:
            try:
                result = self.db.execute(
                    text(f"""
                        SELECT
                            COUNT(*) as total_records,
                            MIN({ts_col}) as oldest,
                            MAX({ts_col}) as newest
                        FROM {table}
                    """)
                )
                row = result.fetchone()
                status[table] = dict(row._mapping)
            except Exception as e:
                status[table] = {"error": str(e)}

        return status
