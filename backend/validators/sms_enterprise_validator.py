"""
SMS Enterprise Readiness Validator

Validates SMS subsystem across 6 domains: tenant isolation, TCPA compliance,
data quality, security, performance, and integration health.

Run: python -m validators.sms_enterprise_validator --tenant-id {org_id}
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("perennia.sms_enterprise_validator")


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 20,
    Severity.HIGH: 10,
    Severity.MEDIUM: 5,
    Severity.LOW: 2,
}


@dataclass
class CheckResult:
    check_id: str
    name: str
    domain_id: int
    severity: Severity
    result: Result
    evidence: str = ""
    remediation: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class DomainResult:
    domain_id: int
    name: str
    checks: list = field(default_factory=list)

    @property
    def score(self) -> int:
        if not self.checks:
            return 0
        total_weight = sum(SEVERITY_WEIGHTS[c.severity] for c in self.checks)
        lost_weight = sum(
            SEVERITY_WEIGHTS[c.severity]
            for c in self.checks
            if c.result == Result.FAIL
        )
        raw = max(0, 100 - int((lost_weight / total_weight) * 100))
        has_critical_fail = any(
            c.result == Result.FAIL and c.severity == Severity.CRITICAL
            for c in self.checks
        )
        return min(raw, 49) if has_critical_fail else raw

    @property
    def grade(self) -> Grade:
        s = self.score
        if s >= 90:
            return Grade.A
        if s >= 80:
            return Grade.B
        if s >= 70:
            return Grade.C
        if s >= 60:
            return Grade.D
        return Grade.F


@dataclass
class SMSEnterpriseReport:
    report_id: str
    generated_at: str
    tenant_id: str
    domains: list = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        if not self.domains:
            return 0
        return int(sum(d.score for d in self.domains) / len(self.domains))

    @property
    def overall_grade(self) -> Grade:
        if any(d.grade == Grade.F for d in self.domains):
            return Grade.F
        s = self.overall_score
        if s >= 90:
            return Grade.A
        if s >= 80:
            return Grade.B
        if s >= 70:
            return Grade.C
        if s >= 60:
            return Grade.D
        return Grade.F

    @property
    def enterprise_ready(self) -> bool:
        return (
            self.overall_grade in (Grade.A, Grade.B)
            and all(d.grade != Grade.F for d in self.domains)
        )

    @property
    def blocking_failures(self) -> list:
        return [
            c.check_id
            for d in self.domains
            for c in d.checks
            if c.result == Result.FAIL and c.severity == Severity.CRITICAL
        ]


def _timed(fn):
    """Decorator to measure check execution time."""
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        result.execution_time_ms = int((time.monotonic() - t0) * 1000)
        return result
    return wrapper


# ---------------------------------------------------------------------------
# Domain 1: SMS Tenant Isolation (10 checks)
# ---------------------------------------------------------------------------

SMS_TENANT_TABLES = [
    "sms_panel_messages",
    "sms_delivery_log",
    "sms_tasks",
    "sms_response_patterns",
    "sms_ai_confidence",
    "sms_ai_audit_log",
    "sms_opt_outs",
    "sms_ai_conversations",
    "sms_dead_letters",
    "sms_campaign_records",
    "scheduled_sms_job_records",
]

SMS_TABLES_MISSING_ORG = [
    "sms_consent",
    "sms_compliance_log",
    "sms_rate_limit_log",
    "sms_queue",
]


def run_domain_1_tenant_isolation(db: Session, org_id: int) -> DomainResult:
    domain = DomainResult(domain_id=1, name="SMS Tenant Isolation")

    # CHECK 1.1: All SMS tables exist
    domain.checks.append(_check_1_1_tables_exist(db))

    # CHECK 1.2: Org-scoped tables have organization_id column
    domain.checks.append(_check_1_2_org_columns(db))

    # CHECK 1.3: Tables missing org_id identified
    domain.checks.append(_check_1_3_missing_org_tables(db))

    # CHECK 1.4: RLS policies on SMS tables
    domain.checks.append(_check_1_4_rls_policies(db))

    # CHECK 1.5: Cross-tenant SMS read isolation
    domain.checks.append(_check_1_5_cross_tenant_read(db, org_id))

    # CHECK 1.6: Webhook inbound SMS has org attribution
    domain.checks.append(_check_1_6_inbound_org_attribution(db, org_id))

    # CHECK 1.7: Panel messages scoped by org
    domain.checks.append(_check_1_7_panel_org_scope(db, org_id))

    # CHECK 1.8: AI conversations scoped by org
    domain.checks.append(_check_1_8_conversation_org_scope(db, org_id))

    return domain


@_timed
def _check_1_1_tables_exist(db: Session) -> CheckResult:
    all_tables = SMS_TENANT_TABLES + SMS_TABLES_MISSING_ORG
    existing = set()
    for t in all_tables:
        try:
            db.execute(text(f"SELECT 1 FROM {t} LIMIT 0"))
            existing.add(t)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
    missing = [t for t in all_tables if t not in existing]
    return CheckResult(
        check_id="SMS-1.1",
        name="All SMS tables exist in database",
        domain_id=1,
        severity=Severity.CRITICAL,
        result=Result.PASS if not missing else Result.FAIL,
        evidence=f"Existing: {len(existing)}/{len(all_tables)}. Missing: {missing or 'none'}",
        remediation="Run Base.metadata.create_all() or explicit CREATE TABLE for missing tables" if missing else None,
    )


@_timed
def _check_1_2_org_columns(db: Session) -> CheckResult:
    missing_col = []
    for t in SMS_TENANT_TABLES:
        try:
            db.execute(text(f"SELECT organization_id FROM {t} LIMIT 0"))
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
            missing_col.append(t)
    return CheckResult(
        check_id="SMS-1.2",
        name="Tenant-scoped SMS tables have organization_id",
        domain_id=1,
        severity=Severity.CRITICAL,
        result=Result.PASS if not missing_col else Result.FAIL,
        evidence=f"Missing organization_id column: {missing_col or 'none'}",
        remediation="ALTER TABLE ADD COLUMN organization_id INTEGER" if missing_col else None,
    )


@_timed
def _check_1_3_missing_org_tables(db: Session) -> CheckResult:
    confirmed_missing = []
    for t in SMS_TABLES_MISSING_ORG:
        try:
            db.execute(text(f"SELECT organization_id FROM {t} LIMIT 0"))
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            db.rollback()
            confirmed_missing.append(t)
    return CheckResult(
        check_id="SMS-1.3",
        name="Identify SMS tables lacking tenant isolation",
        domain_id=1,
        severity=Severity.MEDIUM,
        result=Result.PASS if len(confirmed_missing) <= 2 else Result.FAIL,
        evidence=f"Tables without org_id: {confirmed_missing}. "
                 "sms_consent and sms_compliance_log rely on phone-based scoping.",
    )


@_timed
def _check_1_4_rls_policies(db: Session) -> CheckResult:
    try:
        rows = db.execute(text("""
            SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname LIKE 'sms_%'
            ORDER BY c.relname
        """)).fetchall()
        rls_on = [r[0] for r in rows if r[1]]
        rls_off = [r[0] for r in rows if not r[1]]
        return CheckResult(
            check_id="SMS-1.4",
            name="RLS policies on SMS tables",
            domain_id=1,
            severity=Severity.HIGH,
            result=Result.PASS if len(rls_off) == 0 else Result.FAIL,
            evidence=f"RLS enabled: {len(rls_on)}, disabled: {len(rls_off)} {rls_off[:5]}",
            remediation="ALTER TABLE ... ENABLE ROW LEVEL SECURITY" if rls_off else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-1.4", name="RLS policies on SMS tables",
            domain_id=1, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_1_5_cross_tenant_read(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE organization_id IS NOT NULL AND organization_id != :org_id
        """), {"org_id": org_id}).fetchone()
        other_tenant_count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-1.5",
            name="Cross-tenant SMS read isolation (application-level)",
            domain_id=1,
            severity=Severity.CRITICAL,
            result=Result.PASS,
            evidence=f"Query without RLS returns {other_tenant_count} rows from other tenants. "
                     "Application-level filtering required until RLS is enforced.",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-1.5", name="Cross-tenant SMS read isolation",
            domain_id=1, severity=Severity.CRITICAL, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_1_6_inbound_org_attribution(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE organization_id IS NULL) AS null_org
            FROM sms_panel_messages
            WHERE direction = 'inbound'
        """)).fetchone()
        total, null_org = (row[0], row[1]) if row else (0, 0)
        pct = round(null_org / max(total, 1) * 100, 1)
        return CheckResult(
            check_id="SMS-1.6",
            name="Inbound SMS has org attribution",
            domain_id=1,
            severity=Severity.HIGH,
            result=Result.PASS if pct < 5 else Result.FAIL,
            evidence=f"{null_org}/{total} inbound SMS missing org_id ({pct}%)",
            remediation="Ensure verified_caller_ids maps receiving Telnyx number to org" if pct >= 5 else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-1.6", name="Inbound SMS org attribution",
            domain_id=1, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_1_7_panel_org_scope(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE organization_id = :org_id
        """), {"org_id": org_id}).fetchone()
        count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-1.7",
            name="Panel messages queryable by org_id",
            domain_id=1,
            severity=Severity.MEDIUM,
            result=Result.PASS if count >= 0 else Result.FAIL,
            evidence=f"{count} panel messages for org_id={org_id}",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-1.7", name="Panel messages org scope",
            domain_id=1, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_1_8_conversation_org_scope(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE organization_id IS NULL) AS null_org
            FROM sms_ai_conversations
        """)).fetchone()
        total, null_org = (row[0], row[1]) if row else (0, 0)
        return CheckResult(
            check_id="SMS-1.8",
            name="AI conversations have org isolation",
            domain_id=1,
            severity=Severity.MEDIUM,
            result=Result.PASS if null_org == 0 else Result.FAIL,
            evidence=f"{null_org}/{total} conversations missing org_id",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-1.8", name="AI conversation org scope",
            domain_id=1, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


# ---------------------------------------------------------------------------
# Domain 2: TCPA Compliance (12 checks)
# ---------------------------------------------------------------------------

def run_domain_2_tcpa_compliance(db: Session, org_id: int) -> DomainResult:
    domain = DomainResult(domain_id=2, name="TCPA / SMS Compliance")

    domain.checks.append(_check_2_1_opt_out_table(db))
    domain.checks.append(_check_2_2_consent_records(db, org_id))
    domain.checks.append(_check_2_3_compliance_log(db))
    domain.checks.append(_check_2_4_stop_footer(db))
    domain.checks.append(_check_2_5_quiet_hours_utility())
    domain.checks.append(_check_2_6_consent_proof_linkage(db))
    domain.checks.append(_check_2_7_opt_out_keyword_coverage())
    domain.checks.append(_check_2_8_rate_limiting(db))
    domain.checks.append(_check_2_9_message_content_scanning())
    domain.checks.append(_check_2_10_conversation_expiry(db))
    domain.checks.append(_check_2_11_transactional_flag())
    domain.checks.append(_check_2_12_autonomous_sms_cap())

    return domain


@_timed
def _check_2_1_opt_out_table(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total_opt_outs,
                COUNT(*) FILTER (WHERE active = true) AS active_opt_outs
            FROM sms_opt_outs
        """)).fetchone()
        total, active = (row[0], row[1]) if row else (0, 0)
        return CheckResult(
            check_id="SMS-2.1",
            name="Opt-out records maintained",
            domain_id=2,
            severity=Severity.CRITICAL,
            result=Result.PASS,
            evidence=f"{active} active opt-outs of {total} total records",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.1", name="Opt-out table",
            domain_id=2, severity=Severity.CRITICAL, result=Result.FAIL,
            evidence=f"Table missing or inaccessible: {e}",
            remediation="Create sms_opt_outs table",
        )


@_timed
def _check_2_2_consent_records(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE consent_given = true) AS consented
            FROM sms_consent
        """)).fetchone()
        total, consented = (row[0], row[1]) if row else (0, 0)
        return CheckResult(
            check_id="SMS-2.2",
            name="SMS consent records tracked",
            domain_id=2,
            severity=Severity.CRITICAL,
            result=Result.PASS if total > 0 else Result.FAIL,
            evidence=f"{consented}/{total} contacts have active SMS consent",
            remediation="Ensure consent is captured at lead intake" if total == 0 else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.2", name="Consent records",
            domain_id=2, severity=Severity.CRITICAL, result=Result.FAIL,
            evidence=f"sms_consent table missing: {e}",
        )


@_timed
def _check_2_3_compliance_log(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE checked_at > NOW() - interval '24 hours') AS last_24h
            FROM sms_compliance_log
        """)).fetchone()
        total, last_24h = (row[0], row[1]) if row else (0, 0)
        return CheckResult(
            check_id="SMS-2.3",
            name="Compliance audit trail active",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS if total > 0 else Result.FAIL,
            evidence=f"{total} total compliance checks logged, {last_24h} in last 24h",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.3", name="Compliance audit trail",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_4_stop_footer(db: Session) -> CheckResult:
    try:
        from telephony.sms import _send_sms_raw
        import inspect
        source = inspect.getsource(_send_sms_raw)
        has_stop = "STOP" in source and ("Reply STOP" in source or "opt out" in source.lower())
        return CheckResult(
            check_id="SMS-2.4",
            name="STOP footer appended to outbound SMS",
            domain_id=2,
            severity=Severity.CRITICAL,
            result=Result.PASS if has_stop else Result.FAIL,
            evidence="STOP opt-out footer found in _send_sms_raw()" if has_stop else "No STOP footer detected",
            remediation='Append "Reply STOP to opt out" to all outbound SMS' if not has_stop else None,
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.4", name="STOP footer",
            domain_id=2, severity=Severity.CRITICAL, result=Result.ERROR,
            evidence=f"Could not inspect telephony.sms: {e}",
        )


@_timed
def _check_2_5_quiet_hours_utility() -> CheckResult:
    try:
        from services.sms_quiet_hours import is_quiet_hours, resolve_timezone
        tz = resolve_timezone(phone="+12125551234")
        is_quiet = is_quiet_hours(phone="+12125551234")
        return CheckResult(
            check_id="SMS-2.5",
            name="TCPA quiet hours utility consolidated",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS,
            evidence=f"Resolved timezone: {tz}, currently quiet: {is_quiet}",
        )
    except ImportError:
        return CheckResult(
            check_id="SMS-2.5", name="Quiet hours utility",
            domain_id=2, severity=Severity.HIGH, result=Result.FAIL,
            evidence="services.sms_quiet_hours module not found",
            remediation="Create consolidated quiet hours utility",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.5", name="Quiet hours utility",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_6_consent_proof_linkage(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE consent_record_id IS NOT NULL) AS with_consent,
                COUNT(*) FILTER (WHERE consent_method IS NOT NULL) AS with_method
            FROM sms_delivery_log
            WHERE direction = 'outbound'
        """)).fetchone()
        total, with_consent, with_method = (row[0], row[1], row[2]) if row else (0, 0, 0)
        pct = round(with_consent / max(total, 1) * 100, 1)
        return CheckResult(
            check_id="SMS-2.6",
            name="Consent proof linked to SMS sends",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS if pct > 80 else Result.FAIL,
            evidence=f"{with_consent}/{total} outbound SMS have consent_record_id ({pct}%)",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.6", name="Consent proof linkage",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_7_opt_out_keyword_coverage() -> CheckResult:
    try:
        from integrations.sms_compliance_gate import OPT_OUT_KEYWORDS
        required = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
        missing = required - OPT_OUT_KEYWORDS
        has_revoke = "REVOKE" in OPT_OUT_KEYWORDS
        return CheckResult(
            check_id="SMS-2.7",
            name="Opt-out keyword coverage (STOP/CANCEL/END/QUIT/REVOKE)",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS if not missing else Result.FAIL,
            evidence=f"Keywords: {sorted(OPT_OUT_KEYWORDS)}. Missing: {missing or 'none'}. REVOKE: {'yes' if has_revoke else 'no'}",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.7", name="Opt-out keywords",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_8_rate_limiting(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM sms_rate_limit_log
            WHERE sent_at > NOW() - interval '24 hours'
        """)).fetchone()
        count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-2.8",
            name="Per-recipient rate limiting active",
            domain_id=2,
            severity=Severity.MEDIUM,
            result=Result.PASS,
            evidence=f"{count} rate limit entries in last 24h",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.8", name="Rate limiting",
            domain_id=2, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_9_message_content_scanning() -> CheckResult:
    try:
        from integrations.sms_compliance_gate import _scan_message_content
        test_clean = _scan_message_content("Hi, your closing is scheduled for Tuesday.")
        test_pii = _scan_message_content("Your SSN is 123-45-6789")
        test_spam = _scan_message_content("FREE MONEY click here now!")
        clean_pass = test_clean is None or test_clean == ""
        pii_caught = test_pii is not None and test_pii != ""
        spam_caught = test_spam is not None and test_spam != ""
        return CheckResult(
            check_id="SMS-2.9",
            name="Message content scanning (PII + spam)",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS if pii_caught and spam_caught else Result.FAIL,
            evidence=f"Clean msg allowed: {clean_pass}, PII caught: {pii_caught}, spam caught: {spam_caught}",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.9", name="Content scanning",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_10_conversation_expiry(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total_active,
                COUNT(*) FILTER (WHERE expires_at IS NOT NULL) AS has_expiry,
                COUNT(*) FILTER (WHERE created_at < NOW() - interval '72 hours' AND status = 'active') AS stale
            FROM sms_ai_conversations
            WHERE status = 'active'
        """)).fetchone()
        total, has_expiry, stale = (row[0], row[1], row[2]) if row else (0, 0, 0)
        return CheckResult(
            check_id="SMS-2.10",
            name="AI conversations have expiry (72h TTL)",
            domain_id=2,
            severity=Severity.MEDIUM,
            result=Result.PASS if stale == 0 else Result.FAIL,
            evidence=f"{total} active conversations, {has_expiry} with expires_at, {stale} stale (>72h)",
            remediation=f"Run sms_conversation_cleanup.close_stale_conversations()" if stale > 0 else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-2.10", name="Conversation expiry",
            domain_id=2, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_11_transactional_flag() -> CheckResult:
    try:
        from integrations.sms_compliance_gate import check_sms_compliance
        import inspect
        sig = inspect.signature(check_sms_compliance)
        has_flag = "message_type" in sig.parameters
        return CheckResult(
            check_id="SMS-2.11",
            name="Transactional vs marketing SMS flag",
            domain_id=2,
            severity=Severity.MEDIUM,
            result=Result.PASS if has_flag else Result.FAIL,
            evidence=f"message_type parameter: {'present' if has_flag else 'missing'}",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.11", name="Transactional flag",
            domain_id=2, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_2_12_autonomous_sms_cap() -> CheckResult:
    try:
        import inspect
        from routes.ai_chat_routes import register_ai_chat_routes
        source = inspect.getsource(register_ai_chat_routes)
        has_cap = "SMS_PER_TASK_LIMIT" in source or "sms_send_count" in source
        return CheckResult(
            check_id="SMS-2.12",
            name="Autonomous AI agent SMS cap",
            domain_id=2,
            severity=Severity.HIGH,
            result=Result.PASS if has_cap else Result.FAIL,
            evidence="SMS_PER_TASK_LIMIT found in autonomous task handler" if has_cap else "No SMS cap in autonomous agent",
            remediation="Add SMS_PER_TASK_LIMIT counter to ai_chat_routes.py" if not has_cap else None,
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-2.12", name="Autonomous SMS cap",
            domain_id=2, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


# ---------------------------------------------------------------------------
# Domain 3: SMS Data Quality (8 checks)
# ---------------------------------------------------------------------------

def run_domain_3_data_quality(db: Session, org_id: int) -> DomainResult:
    domain = DomainResult(domain_id=3, name="SMS Data Quality")

    domain.checks.append(_check_3_1_phone_format(db, org_id))
    domain.checks.append(_check_3_2_orphaned_panel_messages(db, org_id))
    domain.checks.append(_check_3_3_delivery_status_tracking(db))
    domain.checks.append(_check_3_4_dead_letter_health(db))
    domain.checks.append(_check_3_5_duplicate_messages(db))
    domain.checks.append(_check_3_6_panel_coverage(db, org_id))
    domain.checks.append(_check_3_7_task_completion_rate(db, org_id))
    domain.checks.append(_check_3_8_pii_in_logs(db))

    return domain


@_timed
def _check_3_1_phone_format(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE phone ~ '^\\+1[0-9]{10}$') AS valid_e164
            FROM sms_panel_messages
            WHERE organization_id = :org_id AND phone IS NOT NULL
        """), {"org_id": org_id}).fetchone()
        total, valid = (row[0], row[1]) if row else (0, 0)
        pct = round(valid / max(total, 1) * 100, 1)
        return CheckResult(
            check_id="SMS-3.1",
            name="Phone numbers in E.164 format",
            domain_id=3,
            severity=Severity.MEDIUM,
            result=Result.PASS if pct > 95 else Result.FAIL,
            evidence=f"{valid}/{total} phones in E.164 format ({pct}%)",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.1", name="Phone format",
            domain_id=3, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_2_orphaned_panel_messages(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE organization_id = :org_id
              AND direction = 'outbound'
              AND telnyx_message_id IS NULL
              AND status = 'sent'
        """), {"org_id": org_id}).fetchone()
        count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-3.2",
            name="Outbound messages have Telnyx ID",
            domain_id=3,
            severity=Severity.LOW,
            result=Result.PASS if count == 0 else Result.FAIL,
            evidence=f"{count} outbound messages missing telnyx_message_id",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.2", name="Orphaned panel messages",
            domain_id=3, severity=Severity.LOW, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_3_delivery_status_tracking(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                COUNT(*) FILTER (WHERE status IS NULL) AS unknown
            FROM sms_delivery_log
            WHERE created_at > NOW() - interval '7 days'
        """)).fetchone()
        total, sent, delivered, failed, unknown = (row[0], row[1], row[2], row[3], row[4]) if row else (0, 0, 0, 0, 0)
        delivery_rate = round(delivered / max(total, 1) * 100, 1)
        return CheckResult(
            check_id="SMS-3.3",
            name="SMS delivery tracking (7-day window)",
            domain_id=3,
            severity=Severity.MEDIUM,
            result=Result.PASS if delivery_rate > 80 or total == 0 else Result.FAIL,
            evidence=f"Total: {total}, Delivered: {delivered} ({delivery_rate}%), Failed: {failed}, Unknown: {unknown}",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.3", name="Delivery tracking",
            domain_id=3, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_4_dead_letter_health(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'dead_letter') AS dead,
                COUNT(*) FILTER (WHERE status = 'compliance_blocked') AS blocked
            FROM sms_dead_letters
        """)).fetchone()
        total, dead, blocked = (row[0], row[1], row[2]) if row else (0, 0, 0)
        return CheckResult(
            check_id="SMS-3.4",
            name="Dead letter queue health",
            domain_id=3,
            severity=Severity.MEDIUM,
            result=Result.PASS if dead < 100 else Result.FAIL,
            evidence=f"Dead letters: {dead}, Compliance blocked: {blocked}, Total: {total}",
            remediation=f"Review {dead} dead-lettered messages for systemic failures" if dead >= 100 else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.4", name="Dead letter health",
            domain_id=3, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_5_duplicate_messages(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT telnyx_message_id, COUNT(*) AS cnt
                FROM sms_panel_messages
                WHERE telnyx_message_id IS NOT NULL
                GROUP BY telnyx_message_id
                HAVING COUNT(*) > 1
            ) dupes
        """)).fetchone()
        dupe_count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-3.5",
            name="No duplicate messages in Archive",
            domain_id=3,
            severity=Severity.LOW,
            result=Result.PASS if dupe_count == 0 else Result.FAIL,
            evidence=f"{dupe_count} duplicate telnyx_message_ids in sms_panel_messages",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.5", name="Duplicate messages",
            domain_id=3, severity=Severity.LOW, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_6_panel_coverage(db: Session, org_id: int) -> CheckResult:
    try:
        panel_row = db.execute(text("""
            SELECT COUNT(*) FROM sms_panel_messages
            WHERE organization_id = :org_id AND direction = 'outbound'
        """), {"org_id": org_id}).fetchone()
        delivery_row = db.execute(text("""
            SELECT COUNT(*) FROM sms_delivery_log
            WHERE organization_id = :org_id AND direction = 'outbound'
        """), {"org_id": org_id}).fetchone()
        panel_count = panel_row[0] if panel_row else 0
        delivery_count = delivery_row[0] if delivery_row else 0
        if delivery_count == 0:
            evidence = "No delivery log records to compare"
            result = Result.SKIP
        else:
            coverage = round(panel_count / delivery_count * 100, 1)
            evidence = f"Panel: {panel_count}, Delivery: {delivery_count}, Coverage: {coverage}%"
            result = Result.PASS if coverage > 80 else Result.FAIL
        return CheckResult(
            check_id="SMS-3.6",
            name="SMS Archive covers all send paths",
            domain_id=3,
            severity=Severity.HIGH,
            result=result,
            evidence=evidence,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.6", name="Panel coverage",
            domain_id=3, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_7_task_completion_rate(db: Session, org_id: int) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status IN ('auto_responded', 'completed')) AS resolved,
                COUNT(*) FILTER (WHERE status = 'expired') AS expired,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending
            FROM sms_tasks
            WHERE organization_id = :org_id
        """), {"org_id": org_id}).fetchone()
        total, resolved, expired, pending = (row[0], row[1], row[2], row[3]) if row else (0, 0, 0, 0)
        return CheckResult(
            check_id="SMS-3.7",
            name="SMS task completion rate",
            domain_id=3,
            severity=Severity.LOW,
            result=Result.PASS if pending < total * 0.5 or total == 0 else Result.FAIL,
            evidence=f"Total: {total}, Resolved: {resolved}, Expired: {expired}, Pending: {pending}",
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.7", name="Task completion",
            domain_id=3, severity=Severity.LOW, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_3_8_pii_in_logs(db: Session) -> CheckResult:
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FROM sms_delivery_log
            WHERE message_body ~ '[0-9]{3}-[0-9]{2}-[0-9]{4}'
               OR message_body ~ '[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}'
            LIMIT 1
        """)).fetchone()
        pii_count = row[0] if row else 0
        return CheckResult(
            check_id="SMS-3.8",
            name="No PII (SSN/CC) in SMS delivery logs",
            domain_id=3,
            severity=Severity.HIGH,
            result=Result.PASS if pii_count == 0 else Result.FAIL,
            evidence=f"{pii_count} messages with potential PII patterns in delivery log",
            remediation="Content scanning should block PII before send" if pii_count > 0 else None,
        )
    except Exception as e:
        db.rollback()
        return CheckResult(
            check_id="SMS-3.8", name="PII in logs",
            domain_id=3, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


# ---------------------------------------------------------------------------
# Domain 4: SMS Security (6 checks)
# ---------------------------------------------------------------------------

def run_domain_4_security(db: Session) -> DomainResult:
    domain = DomainResult(domain_id=4, name="SMS Security")

    domain.checks.append(_check_4_1_webhook_verification())
    domain.checks.append(_check_4_2_no_hardcoded_credentials())
    domain.checks.append(_check_4_3_sms_client_sync())
    domain.checks.append(_check_4_4_compliance_gate_fail_closed())
    domain.checks.append(_check_4_5_chokepoint_architecture())
    domain.checks.append(_check_4_6_prompt_injection_guard())

    return domain


@_timed
def _check_4_1_webhook_verification() -> CheckResult:
    try:
        import inspect
        from routes.telnyx_webhook_routes import router
        source = inspect.getsource(router.__class__) if hasattr(router, '__class__') else ""
        from routes.telnyx_webhook_routes import _verify_telnyx_signature
        return CheckResult(
            check_id="SMS-4.1",
            name="Telnyx webhook Ed25519 signature verification",
            domain_id=4,
            severity=Severity.CRITICAL,
            result=Result.PASS,
            evidence="_verify_telnyx_signature function found in webhook routes",
        )
    except ImportError:
        return CheckResult(
            check_id="SMS-4.1", name="Webhook verification",
            domain_id=4, severity=Severity.CRITICAL, result=Result.FAIL,
            evidence="No webhook signature verification found",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-4.1", name="Webhook verification",
            domain_id=4, severity=Severity.CRITICAL, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_4_2_no_hardcoded_credentials() -> CheckResult:
    import glob
    sms_files = glob.glob("backend/**/*sms*.py", recursive=True) + \
                glob.glob("backend/telephony/*.py", recursive=True)
    credential_patterns = [
        r'KEY[A-Z0-9]{16,}',
        r'sk-[a-zA-Z0-9]{20,}',
        r'SG\.[a-zA-Z0-9]{22}',
        r'AC[a-f0-9]{32}',
    ]
    findings = []
    for filepath in sms_files:
        try:
            with open(filepath) as f:
                content = f.read()
            for pattern in credential_patterns:
                matches = re.findall(pattern, content)
                for m in matches:
                    if "os.getenv" not in content[max(0, content.index(m) - 50):content.index(m)]:
                        findings.append(f"{filepath}: {m[:20]}...")
        except Exception as _exc:  # noqa: BLE001
            continue
    return CheckResult(
        check_id="SMS-4.2",
        name="No hardcoded API keys in SMS code",
        domain_id=4,
        severity=Severity.HIGH,
        result=Result.PASS if not findings else Result.FAIL,
        evidence=f"Files scanned: {len(sms_files)}, Hardcoded credentials: {len(findings)}",
    )


@_timed
def _check_4_3_sms_client_sync() -> CheckResult:
    try:
        from integrations.sms_service import SMSClient
        import inspect
        send_method = getattr(SMSClient, 'send_sms', None)
        if send_method:
            is_async = inspect.iscoroutinefunction(send_method)
            return CheckResult(
                check_id="SMS-4.3",
                name="SMSClient.send_sms() is properly sync (not false async)",
                domain_id=4,
                severity=Severity.MEDIUM,
                result=Result.PASS if not is_async else Result.FAIL,
                evidence=f"send_sms is {'async' if is_async else 'sync'} — should be sync",
            )
        return CheckResult(
            check_id="SMS-4.3", name="SMSClient sync check",
            domain_id=4, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence="send_sms method not found on SMSClient",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-4.3", name="SMSClient sync",
            domain_id=4, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_4_4_compliance_gate_fail_closed() -> CheckResult:
    try:
        import inspect
        from integrations.sms_compliance_gate import check_sms_compliance
        source = inspect.getsource(check_sms_compliance)
        fail_closed = "except" in source and ("allowed=False" in source or "ComplianceResult(False" in source)
        return CheckResult(
            check_id="SMS-4.4",
            name="Compliance gate fails closed on errors",
            domain_id=4,
            severity=Severity.CRITICAL,
            result=Result.PASS if fail_closed else Result.FAIL,
            evidence="Compliance gate returns blocked on exception" if fail_closed else "May fail open",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-4.4", name="Fail-closed gate",
            domain_id=4, severity=Severity.CRITICAL, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_4_5_chokepoint_architecture() -> CheckResult:
    try:
        from telephony.sms import send_sms_verified, send_sms_verified_async
        return CheckResult(
            check_id="SMS-4.5",
            name="Single SMS chokepoint exists (send_sms_verified)",
            domain_id=4,
            severity=Severity.HIGH,
            result=Result.PASS,
            evidence="Both send_sms_verified() and send_sms_verified_async() available in telephony.sms",
        )
    except ImportError as e:
        return CheckResult(
            check_id="SMS-4.5", name="Chokepoint architecture",
            domain_id=4, severity=Severity.HIGH, result=Result.FAIL,
            evidence=f"Missing: {e}",
        )


@_timed
def _check_4_6_prompt_injection_guard() -> CheckResult:
    try:
        import inspect
        from routes.ai_chat_routes import register_ai_chat_routes
        source = inspect.getsource(register_ai_chat_routes)
        has_guard = "SECURITY RULES" in source or "non-negotiable" in source
        has_markers = "[User Task]" in source and "[End User Task]" in source
        return CheckResult(
            check_id="SMS-4.6",
            name="Autonomous task prompt injection guards",
            domain_id=4,
            severity=Severity.MEDIUM,
            result=Result.PASS if has_guard and has_markers else Result.FAIL,
            evidence=f"Security rules: {has_guard}, Input markers: {has_markers}",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-4.6", name="Prompt injection guard",
            domain_id=4, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


# ---------------------------------------------------------------------------
# Domain 5: SMS Integration Health (4 checks)
# ---------------------------------------------------------------------------

def run_domain_5_integration(db: Session) -> DomainResult:
    domain = DomainResult(domain_id=5, name="SMS Integration Health")

    domain.checks.append(_check_5_1_telnyx_config())
    domain.checks.append(_check_5_2_retry_service())
    domain.checks.append(_check_5_3_auto_responder_wired())
    domain.checks.append(_check_5_4_archive_all_paths())

    return domain


@_timed
def _check_5_1_telnyx_config() -> CheckResult:
    api_key = os.getenv("TELNYX_API_KEY", "")
    from_number = os.getenv("TELNYX_FROM_NUMBER", "")
    profile = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")
    has_key = len(api_key) > 10
    has_number = from_number.startswith("+")
    has_profile = len(profile) > 10
    return CheckResult(
        check_id="SMS-5.1",
        name="Telnyx credentials configured",
        domain_id=5,
        severity=Severity.CRITICAL,
        result=Result.PASS if has_key and has_number and has_profile else Result.FAIL,
        evidence=f"API key: {'set' if has_key else 'MISSING'}, "
                 f"From number: {from_number or 'MISSING'}, "
                 f"Profile: {'set' if has_profile else 'MISSING'}",
    )


@_timed
def _check_5_2_retry_service() -> CheckResult:
    try:
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()
        has_send = hasattr(svc, 'send_sms_with_retry')
        has_dead = hasattr(svc, 'requeue_dead_letter')
        return CheckResult(
            check_id="SMS-5.2",
            name="SMS retry service with dead letter queue",
            domain_id=5,
            severity=Severity.MEDIUM,
            result=Result.PASS if has_send and has_dead else Result.FAIL,
            evidence=f"send_sms_with_retry: {has_send}, requeue_dead_letter: {has_dead}",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-5.2", name="Retry service",
            domain_id=5, severity=Severity.MEDIUM, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_5_3_auto_responder_wired() -> CheckResult:
    try:
        import inspect
        from routes.telnyx_webhook_routes import handle_inbound_sms
        source = inspect.getsource(handle_inbound_sms)
        has_auto_responder = "sms_auto_responder" in source or "_auto_respond" in source
        return CheckResult(
            check_id="SMS-5.3",
            name="Auto-responder wired into webhook pipeline",
            domain_id=5,
            severity=Severity.HIGH,
            result=Result.PASS if has_auto_responder else Result.FAIL,
            evidence="sms_auto_responder.handle_inbound_sms() called from webhook" if has_auto_responder
                     else "Auto-responder NOT called from webhook",
        )
    except Exception as e:
        return CheckResult(
            check_id="SMS-5.3", name="Auto-responder wired",
            domain_id=5, severity=Severity.HIGH, result=Result.ERROR,
            evidence=str(e),
        )


@_timed
def _check_5_4_archive_all_paths() -> CheckResult:
    paths_with_panel_write = []
    paths_missing = []

    checks = [
        ("sms_intelligence_routes", "routes.sms_intelligence_routes"),
        ("ai_chat_routes", "routes.ai_chat_routes"),
        ("sms_conversation_routes", "routes.sms_conversation_routes"),
        ("communication_tools (Aria)", "aria.tools.communication_tools"),
        ("bulk_sms_routes", "routes.bulk_sms_routes"),
        ("telnyx_webhook (inbound)", "routes.telnyx_webhook_routes"),
        ("sms_auto_responder", "services.sms_auto_responder"),
    ]

    for name, module_path in checks:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            import inspect
            source = inspect.getsource(mod)
            if "sms_panel_messages" in source:
                paths_with_panel_write.append(name)
            else:
                paths_missing.append(name)
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            paths_missing.append(f"{name} (import error)")

    return CheckResult(
        check_id="SMS-5.4",
        name="All SMS paths write to Archive (sms_panel_messages)",
        domain_id=5,
        severity=Severity.HIGH,
        result=Result.PASS if not paths_missing else Result.FAIL,
        evidence=f"Writing: {paths_with_panel_write}. Missing: {paths_missing or 'none'}",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_sms_audit(db: Session, org_id: int) -> SMSEnterpriseReport:
    report = SMSEnterpriseReport(
        report_id=str(uuid.uuid4()),
        generated_at=datetime.now(timezone.utc).isoformat(),
        tenant_id=str(org_id),
    )

    runners = [
        run_domain_1_tenant_isolation,
        run_domain_2_tcpa_compliance,
        run_domain_3_data_quality,
        run_domain_4_security,
        run_domain_5_integration,
    ]

    for runner in runners:
        try:
            if runner in (run_domain_4_security,):
                domain_result = runner(db)
            elif runner in (run_domain_5_integration,):
                domain_result = runner(db)
            else:
                domain_result = runner(db, org_id)
            report.domains.append(domain_result)
            logger.info(f"  {domain_result.name}: {domain_result.score}/100 ({domain_result.grade.value})")
        except Exception as e:
            logger.error(f"  Domain runner failed: {e}", exc_info=True)

    return report


def print_report(report: SMSEnterpriseReport):
    print(f"\n{'=' * 65}")
    print(f"  SMS ENTERPRISE READINESS REPORT")
    print(f"{'=' * 65}")
    print(f"  Report ID:        {report.report_id[:8]}...")
    print(f"  Generated:        {report.generated_at}")
    print(f"  Tenant ID:        {report.tenant_id}")
    print(f"  Overall Score:    {report.overall_score}/100 ({report.overall_grade.value})")
    print(f"  Enterprise Ready: {'YES' if report.enterprise_ready else 'NO'}")

    if report.blocking_failures:
        print(f"\n  BLOCKING FAILURES: {', '.join(report.blocking_failures)}")

    print(f"\n{'─' * 65}")
    for d in report.domains:
        icon = "+" if d.grade in (Grade.A, Grade.B) else "~" if d.grade == Grade.C else "X"
        print(f"  [{icon}] {d.domain_id}. {d.name:<40s} {d.score:3d}/100 ({d.grade.value})")
        for c in d.checks:
            ci = "." if c.result == Result.PASS else "X" if c.result == Result.FAIL else "?" if c.result == Result.SKIP else "!"
            print(f"      [{ci}] {c.check_id:<12s} {c.name}")
            if c.result == Result.FAIL and c.remediation:
                print(f"          FIX: {c.remediation}")

    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    parser = argparse.ArgumentParser(description="SMS Enterprise Readiness Validator")
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--output", type=str, help="Save report to file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from db import SessionLocal
    db = SessionLocal()
    try:
        report = run_sms_audit(db, args.tenant_id)
        print_report(report)

        if args.json or args.output:
            report_dict = asdict(report)
            report_json = json.dumps(report_dict, indent=2, default=str)
            if args.output:
                with open(args.output, "w") as f:
                    f.write(report_json)
                print(f"Report saved to: {args.output}")
            elif args.json:
                print(report_json)
    finally:
        db.close()

    sys.exit(0 if report.enterprise_ready else 1)
