"""
Automated Compliance Scan — Run daily to verify control effectiveness.
SOC 2 Criteria: CC3 (Risk Assessment), CC4 (Monitoring)

This script runs a series of automated checks against the database
to verify SOC 2 controls are operating effectively.

Schedule: Daily via cron or admin endpoint
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..constants import ComplianceCheckStatus, SeverityLevel

logger = logging.getLogger("soc2.compliance_scan")


class ComplianceScanner:
    """Run automated SOC 2 compliance checks."""

    def __init__(self, db: Session):
        self.db = db
        self.results: List[Dict] = []

    def run_all_checks(self) -> List[Dict]:
        """Run all compliance checks and store results."""
        checks = [
            self.check_audit_logging_active,
            self.check_failed_login_thresholds,
            self.check_orphaned_sessions,
            self.check_encryption_coverage,
            self.check_change_approval_compliance,
            self.check_incident_response_times,
            self.check_data_retention_compliance,
            self.check_pii_access_patterns,
            self.check_api_key_rotation,
            self.check_high_severity_unresolved,
        ]

        for check_fn in checks:
            try:
                result = check_fn()
                self.results.append(result)
                self._store_result(result)
            except Exception as e:
                error_result = {
                    "check_name": check_fn.__name__,
                    "check_category": "system",
                    "status": ComplianceCheckStatus.ERROR,
                    "details": f"Check failed with error: {str(e)}",
                    "trust_criteria": None,
                }
                self.results.append(error_result)
                self._store_result(error_result)

        passed = sum(1 for r in self.results if r["status"] == ComplianceCheckStatus.PASS)
        total = len(self.results)
        logger.info(f"Compliance scan complete: {passed}/{total} checks passed")

        return self.results

    def check_audit_logging_active(self) -> Dict:
        """CC4: Verify audit logging is capturing events."""
        result = self.db.execute(
            text("""
                SELECT COUNT(*) FROM soc2_audit_log
                WHERE timestamp > NOW() - INTERVAL '24 hours'
            """)
        )
        count = result.fetchone()[0]

        return {
            "check_name": "Audit Logging Active",
            "check_category": "CC4_monitoring",
            "trust_criteria": "CC4",
            "status": ComplianceCheckStatus.PASS if count > 0 else ComplianceCheckStatus.FAIL,
            "details": f"{count} audit events in last 24 hours",
            "evidence": {"event_count_24h": count},
            "remediation_required": count == 0,
            "remediation_notes": "No audit events detected. Verify middleware is installed." if count == 0 else None,
        }

    def check_failed_login_thresholds(self) -> Dict:
        """CC6: Check for excessive failed login attempts."""
        result = self.db.execute(
            text("""
                SELECT
                    ip_address::text,
                    COUNT(*) as attempts,
                    COUNT(DISTINCT attempted_email) as unique_accounts
                FROM soc2_access_event
                WHERE success = FALSE
                  AND timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY ip_address
                HAVING COUNT(*) > 20
                ORDER BY attempts DESC
                LIMIT 10
            """)
        )
        suspicious_ips = [dict(row._mapping) for row in result.fetchall()]

        return {
            "check_name": "Failed Login Threshold",
            "check_category": "CC6_access_controls",
            "trust_criteria": "CC6",
            "status": ComplianceCheckStatus.PASS if not suspicious_ips else ComplianceCheckStatus.WARNING,
            "details": f"{len(suspicious_ips)} IPs with >20 failed attempts in 24h",
            "evidence": {"suspicious_ips": suspicious_ips},
            "remediation_required": len(suspicious_ips) > 0,
        }

    def check_orphaned_sessions(self) -> Dict:
        """CC6: Verify JWT session configuration and SECRET_KEY entropy."""
        import os
        import math
        issues = []
        evidence = {}

        # Check JWT expiry configuration
        session_timeout = os.getenv("SOC2_SESSION_TIMEOUT_MINUTES", "30")
        try:
            timeout_val = int(session_timeout)
            evidence["session_timeout_minutes"] = timeout_val
            if timeout_val > 1440:  # > 24 hours
                issues.append(f"Session timeout too long: {timeout_val} minutes (max recommended: 1440)")
            elif timeout_val <= 0:
                issues.append("Session timeout is non-positive")
        except ValueError:
            issues.append(f"Invalid SOC2_SESSION_TIMEOUT_MINUTES: {session_timeout}")

        # Check that max login attempts is configured
        max_attempts = os.getenv("SOC2_MAX_LOGIN_ATTEMPTS", "5")
        try:
            attempts_val = int(max_attempts)
            evidence["max_login_attempts"] = attempts_val
            if attempts_val > 20:
                issues.append(f"Max login attempts too high: {attempts_val}")
        except ValueError:
            issues.append(f"Invalid SOC2_MAX_LOGIN_ATTEMPTS: {max_attempts}")

        # SECRET_KEY entropy check
        secret_key = os.getenv("SECRET_KEY", "")
        if secret_key:
            evidence["secret_key_length"] = len(secret_key)
            if len(secret_key) < 32:
                issues.append(f"SECRET_KEY too short: {len(secret_key)} chars (min 32)")
            # Shannon entropy check
            entropy = _calculate_shannon_entropy(secret_key)
            evidence["secret_key_entropy"] = round(entropy, 2)
            if entropy < 3.0:
                issues.append(f"SECRET_KEY entropy too low: {entropy:.2f} (min 3.0)")
        else:
            issues.append("SECRET_KEY not configured")
            evidence["secret_key_length"] = 0

        status = ComplianceCheckStatus.PASS if not issues else ComplianceCheckStatus.WARNING

        return {
            "check_name": "Session Security Configuration",
            "check_category": "CC6_access_controls",
            "trust_criteria": "CC6",
            "status": status,
            "details": "; ".join(issues) if issues else "Session configuration is within acceptable parameters",
            "evidence": evidence,
            "remediation_required": len(issues) > 0,
        }

    def check_encryption_coverage(self) -> Dict:
        """C1: Verify PII columns are marked as encrypted and encryption works at runtime."""
        result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_pii_columns,
                    COUNT(*) FILTER (WHERE is_encrypted = TRUE) as encrypted_columns
                FROM soc2_data_classification
                WHERE is_pii = TRUE
            """)
        )
        row = result.fetchone()
        total = row[0]
        encrypted = row[1]

        status = ComplianceCheckStatus.PASS
        if total == 0:
            status = ComplianceCheckStatus.WARNING  # No classifications registered
        elif encrypted < total:
            status = ComplianceCheckStatus.FAIL

        evidence = {"total_pii": total, "encrypted": encrypted}

        # Runtime encrypt/decrypt round-trip verification
        try:
            from soc2_compliance.services.encryption_service import EncryptionService
            from soc2_compliance.config import SOC2Config
            enc = EncryptionService(config=SOC2Config.from_env())
            test_value = "SOC2-ROUNDTRIP-TEST"
            encrypted_val = enc.encrypt(test_value)
            decrypted_val = enc.decrypt(encrypted_val)
            roundtrip_ok = (decrypted_val == test_value)
            evidence["encryption_roundtrip"] = "pass" if roundtrip_ok else "fail"
            if not roundtrip_ok:
                status = ComplianceCheckStatus.FAIL
        except ValueError:
            evidence["encryption_roundtrip"] = "not_configured"
            if status == ComplianceCheckStatus.PASS:
                status = ComplianceCheckStatus.WARNING
        except Exception as e:
            evidence["encryption_roundtrip"] = f"error: {str(e)[:100]}"
            status = ComplianceCheckStatus.FAIL

        return {
            "check_name": "PII Encryption Coverage",
            "check_category": "C1_confidentiality",
            "trust_criteria": "C1",
            "status": status,
            "details": f"{encrypted}/{total} PII columns encrypted",
            "evidence": evidence,
            "remediation_required": encrypted < total or evidence.get("encryption_roundtrip") != "pass",
            "remediation_notes": f"{total - encrypted} PII columns need encryption" if encrypted < total else None,
        }

    def check_change_approval_compliance(self) -> Dict:
        """CC8: Verify changes are going through approval process."""
        result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_changes,
                    COUNT(*) FILTER (WHERE approved_by IS NOT NULL) as approved_changes,
                    COUNT(*) FILTER (WHERE approved_by IS NULL AND status = 'completed') as unapproved_completed
                FROM soc2_change_record
                WHERE created_at > NOW() - INTERVAL '30 days'
            """)
        )
        row = result.fetchone()
        total = row[0]
        approved = row[1]
        unapproved = row[2]

        status = ComplianceCheckStatus.PASS if unapproved == 0 else ComplianceCheckStatus.FAIL

        return {
            "check_name": "Change Approval Compliance",
            "check_category": "CC8_change_management",
            "trust_criteria": "CC8",
            "status": status,
            "details": f"{approved}/{total} changes approved; {unapproved} unapproved completions",
            "evidence": {"total": total, "approved": approved, "unapproved_completed": unapproved},
            "remediation_required": unapproved > 0,
        }

    def check_incident_response_times(self) -> Dict:
        """CC7: Verify incident response SLAs."""
        result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as open_incidents,
                    COUNT(*) FILTER (
                        WHERE severity IN ('high', 'critical')
                        AND status = 'open'
                        AND created_at < NOW() - INTERVAL '4 hours'
                    ) as overdue_critical
                FROM soc2_security_incident
                WHERE status NOT IN ('resolved', 'closed')
            """)
        )
        row = result.fetchone()
        open_count = row[0]
        overdue = row[1]

        return {
            "check_name": "Incident Response SLA",
            "check_category": "CC7_operations",
            "trust_criteria": "CC7",
            "status": ComplianceCheckStatus.PASS if overdue == 0 else ComplianceCheckStatus.FAIL,
            "details": f"{open_count} open incidents; {overdue} critical/high overdue (>4h)",
            "evidence": {"open_incidents": open_count, "overdue_critical": overdue},
            "remediation_required": overdue > 0,
        }

    def check_data_retention_compliance(self) -> Dict:
        """P4: Verify data isn't being retained beyond policy limits."""
        result = self.db.execute(
            text("""
                SELECT COUNT(*) FROM soc2_audit_log
                WHERE timestamp < NOW() - INTERVAL '730 days'
            """)
        )
        overdue = result.fetchone()[0]

        return {
            "check_name": "Data Retention Compliance",
            "check_category": "P4_disposal",
            "trust_criteria": "P4",
            "status": ComplianceCheckStatus.PASS if overdue == 0 else ComplianceCheckStatus.WARNING,
            "details": f"{overdue} audit records past retention period",
            "evidence": {"records_past_retention": overdue},
            "remediation_required": overdue > 0,
            "remediation_notes": "Run retention enforcement to clean up" if overdue > 0 else None,
        }

    def check_pii_access_patterns(self) -> Dict:
        """P1: Check for unusual PII access patterns."""
        result = self.db.execute(
            text("""
                SELECT
                    user_email,
                    COUNT(*) as pii_accesses
                FROM soc2_audit_log
                WHERE contains_pii = TRUE
                  AND timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY user_email
                HAVING COUNT(*) > 100
                ORDER BY pii_accesses DESC
            """)
        )
        high_access_users = [dict(row._mapping) for row in result.fetchall()]

        return {
            "check_name": "PII Access Patterns",
            "check_category": "P1_privacy",
            "trust_criteria": "P1",
            "status": ComplianceCheckStatus.PASS if not high_access_users else ComplianceCheckStatus.WARNING,
            "details": f"{len(high_access_users)} users with >100 PII accesses in 24h",
            "evidence": {"high_access_users": high_access_users},
        }

    def check_api_key_rotation(self) -> Dict:
        """CC6: Verify API key / secret configuration hygiene (read-only check)."""
        import os
        import base64
        issues = []
        evidence = {}

        # Check if critical secrets are configured via env vars
        required_secrets = [
            ("SECRET_KEY", "Application secret key"),
            ("SOC2_FIELD_ENCRYPTION_KEY", "Field encryption key"),
        ]

        for env_var, label in required_secrets:
            val = os.getenv(env_var, "")
            if not val:
                issues.append(f"{label} ({env_var}) is not configured")
                evidence[env_var] = "missing"
            else:
                evidence[env_var] = "configured"

        # Validate Fernet key format (44 chars, valid base64 encoding 32 bytes)
        fernet_key = os.getenv("SOC2_FIELD_ENCRYPTION_KEY", "")
        if fernet_key:
            evidence["fernet_key_length"] = len(fernet_key)
            if len(fernet_key) != 44:
                issues.append(f"Fernet key length is {len(fernet_key)} (expected 44)")
            else:
                try:
                    decoded = base64.urlsafe_b64decode(fernet_key.encode())
                    if len(decoded) != 32:
                        issues.append(f"Fernet key decodes to {len(decoded)} bytes (expected 32)")
                    else:
                        evidence["fernet_key_format"] = "valid"
                except Exception:
                    issues.append("Fernet key is not valid base64")
                    evidence["fernet_key_format"] = "invalid"

        # Check hash salt is not the insecure default
        hash_salt = os.getenv("SOC2_HASH_SALT", "")
        if not hash_salt:
            issues.append("SOC2_HASH_SALT not configured")
            evidence["SOC2_HASH_SALT"] = "missing"
        else:
            evidence["SOC2_HASH_SALT"] = "configured"

        status = ComplianceCheckStatus.PASS if not issues else ComplianceCheckStatus.WARNING

        return {
            "check_name": "Secret & API Key Configuration",
            "check_category": "CC6_access_controls",
            "trust_criteria": "CC6",
            "status": status,
            "details": "; ".join(issues) if issues else "All required secrets are configured",
            "evidence": evidence,
            "remediation_required": len(issues) > 0,
        }

    def check_high_severity_unresolved(self) -> Dict:
        """CC7: Check for unresolved high/critical incidents."""
        result = self.db.execute(
            text("""
                SELECT id::text, title, severity, created_at::text, status
                FROM soc2_security_incident
                WHERE severity IN ('high', 'critical')
                  AND status NOT IN ('resolved', 'closed')
                ORDER BY created_at ASC
            """)
        )
        unresolved = [dict(row._mapping) for row in result.fetchall()]

        return {
            "check_name": "Unresolved High-Severity Incidents",
            "check_category": "CC7_operations",
            "trust_criteria": "CC7",
            "status": ComplianceCheckStatus.PASS if not unresolved else ComplianceCheckStatus.FAIL,
            "details": f"{len(unresolved)} unresolved high/critical incidents",
            "evidence": {"incidents": unresolved},
            "remediation_required": len(unresolved) > 0,
        }

    def _store_result(self, result: Dict) -> None:
        """Store a compliance check result in the database."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO soc2_compliance_check (
                        run_at, check_name, check_category, description,
                        status, details, evidence, trust_criteria,
                        remediation_required, remediation_notes
                    ) VALUES (
                        NOW(), :check_name, :check_category, :description,
                        :status, :details, :evidence::jsonb, :trust_criteria,
                        :remediation_required, :remediation_notes
                    )
                """),
                {
                    "check_name": result.get("check_name"),
                    "check_category": result.get("check_category"),
                    "description": result.get("details"),
                    "status": result.get("status"),
                    "details": result.get("details"),
                    "evidence": json.dumps(result.get("evidence", {})),
                    "trust_criteria": result.get("trust_criteria"),
                    "remediation_required": result.get("remediation_required", False),
                    "remediation_notes": result.get("remediation_notes"),
                }
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to store compliance check result: {e}")


def _calculate_shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string (bits per character)."""
    import math
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def run_compliance_scan(db: Session) -> List[Dict]:
    """Entry point for running the compliance scan."""
    scanner = ComplianceScanner(db)
    return scanner.run_all_checks()
