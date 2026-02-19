# Enterprise Readiness — Implementation Reference

Production-ready patterns for executing the 196 checks programmatically.

---

## Validator Architecture

```python
"""
Enterprise Readiness Validator
Run: python enterprise_validator.py --mode full --tenant-id {uuid}
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("perennia.enterprise_readiness")


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
    checks: list[CheckResult] = field(default_factory=list)

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
        # Critical failure caps score at 49
        has_critical_fail = any(
            c.result == Result.FAIL and c.severity == Severity.CRITICAL
            for c in self.checks
        )
        return min(raw, 49) if has_critical_fail else raw

    @property
    def grade(self) -> Grade:
        s = self.score
        if s >= 90: return Grade.A
        if s >= 80: return Grade.B
        if s >= 70: return Grade.C
        if s >= 60: return Grade.D
        return Grade.F


@dataclass
class EnterpriseReadinessReport:
    report_id: str
    generated_at: str
    mode: str
    domains: list[DomainResult] = field(default_factory=list)

    @property
    def overall_score(self) -> int:
        if not self.domains:
            return 0
        return int(sum(d.score for d in self.domains) / len(self.domains))

    @property
    def overall_grade(self) -> Grade:
        # Any F domain blocks overall certification
        if any(d.grade == Grade.F for d in self.domains):
            return Grade.F
        s = self.overall_score
        if s >= 90: return Grade.A
        if s >= 80: return Grade.B
        if s >= 70: return Grade.C
        if s >= 60: return Grade.D
        return Grade.F

    @property
    def enterprise_ready(self) -> bool:
        return (
            self.overall_grade in (Grade.A, Grade.B)
            and all(d.grade != Grade.F for d in self.domains)
        )

    @property
    def blocking_failures(self) -> list[str]:
        return [
            c.check_id
            for d in self.domains
            for c in d.checks
            if c.result == Result.FAIL and c.severity == Severity.CRITICAL
        ]
```

---

## Domain 1: Multi-Tenant Isolation — SQL & Test Patterns

```sql
-- CHECK 1.1: RLS policies exist on all tenant-scoped tables
-- Returns tables that SHOULD have RLS but DON'T
WITH tenant_tables AS (
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND a.attname IN ('org_id', 'tenant_id', 'organization_id')
      AND NOT a.attisdropped
),
rls_tables AS (
    SELECT c.relname AS table_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relrowsecurity = true
)
SELECT t.table_name, 
       CASE WHEN r.table_name IS NOT NULL THEN 'HAS_RLS' ELSE 'MISSING_RLS' END AS status
FROM tenant_tables t
LEFT JOIN rls_tables r ON t.table_name = r.table_name
ORDER BY status DESC, t.table_name;

-- CHECK 1.2: RLS policies are ENABLED
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND c.relname IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public')
ORDER BY c.relrowsecurity, c.relname;

-- CHECK 1.3-1.6: Cross-tenant CRUD verification
-- Execute as tenant_a, attempt operations on tenant_b data
-- This must be run with the application's connection pooler using SET app.current_tenant

-- Setup: Get two test tenant IDs
-- SELECT DISTINCT org_id FROM users LIMIT 2;

-- Test cross-tenant SELECT
SET app.current_tenant = '{tenant_a_id}';
SELECT COUNT(*) AS leaked_rows
FROM contacts
WHERE org_id = '{tenant_b_id}';
-- PASS: leaked_rows = 0

-- Test cross-tenant INSERT
SET app.current_tenant = '{tenant_a_id}';
INSERT INTO contacts (org_id, first_name, last_name, email)
VALUES ('{tenant_b_id}', 'Test', 'CrossTenant', 'test@cross.com');
-- PASS: INSERT rejected or org_id overridden to tenant_a_id

-- Test cross-tenant UPDATE
SET app.current_tenant = '{tenant_a_id}';
UPDATE contacts SET first_name = 'HACKED' WHERE org_id = '{tenant_b_id}';
-- PASS: 0 rows affected

-- Test cross-tenant DELETE
SET app.current_tenant = '{tenant_a_id}';
DELETE FROM contacts WHERE org_id = '{tenant_b_id}';
-- PASS: 0 rows affected
```

```python
# CHECK 1.7-1.10: API Isolation Tests
async def test_api_tenant_isolation(client, tenant_a_token, tenant_b_id):
    """Auth as tenant_A, attempt to access tenant_B resources."""
    endpoints = [
        f"/api/v1/contacts",
        f"/api/v1/loans",
        f"/api/v1/tasks",
        f"/api/v1/documents",
        f"/api/v1/activities",
        f"/api/v1/pipeline",
    ]
    results = []
    for endpoint in endpoints:
        # Try to access with tenant_B filter
        resp = await client.get(
            endpoint,
            headers={"Authorization": f"Bearer {tenant_a_token}"},
            params={"org_id": tenant_b_id}
        )
        leaked = False
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", data.get("data", []))
            leaked = any(
                item.get("org_id") == tenant_b_id
                for item in (items if isinstance(items, list) else [])
            )
        results.append({
            "endpoint": endpoint,
            "status": resp.status_code,
            "leaked": leaked,
            "pass": not leaked
        })
    return results
```

---

## Domain 2: Compliance — TRID Timeline Engine

```python
# CHECK 2.1-2.2: TRID deadline calculation
from datetime import date, timedelta

FEDERAL_HOLIDAYS_2025_2026 = {
    # Add all federal holidays
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4),
    date(2025, 9, 1), date(2025, 10, 13), date(2025, 11, 11),
    date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3),
    date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 11),
    date(2026, 11, 26), date(2026, 12, 25),
}


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in FEDERAL_HOLIDAYS_2025_2026


def add_business_days(start: date, days: int) -> date:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def subtract_business_days(end: date, days: int) -> date:
    current = end
    subtracted = 0
    while subtracted < days:
        current -= timedelta(days=1)
        if is_business_day(current):
            subtracted += 1
    return current


def check_trid_le_deadline(application_date: date) -> dict:
    """LE must be delivered within 3 business days of application."""
    deadline = add_business_days(application_date, 3)
    return {
        "check_id": "2.1",
        "application_date": str(application_date),
        "le_deadline": str(deadline),
        "description": "Loan Estimate must be delivered by this date"
    }


def check_trid_cd_deadline(closing_date: date) -> dict:
    """CD must be delivered at least 3 business days before closing."""
    latest_delivery = subtract_business_days(closing_date, 3)
    return {
        "check_id": "2.2",
        "closing_date": str(closing_date),
        "cd_latest_delivery": str(latest_delivery),
        "description": "Closing Disclosure must be delivered by this date"
    }


# CHECK 2.11-2.14: TCPA Verification
async def check_tcpa_consent(db, contact_id: str) -> dict:
    """Verify TCPA consent exists before any outbound contact."""
    query = """
        SELECT consent_type, consent_method, consented_at,
               consent_scope, revoked_at
        FROM tcpa_consents
        WHERE contact_id = $1
          AND revoked_at IS NULL
        ORDER BY consented_at DESC
    """
    consents = await db.fetch(query, contact_id)
    return {
        "check_id": "2.11",
        "contact_id": contact_id,
        "has_active_consent": len(consents) > 0,
        "consent_types": [c["consent_type"] for c in consents],
        "pass": len(consents) > 0
    }
```

---

## Domain 3: Data Quality — Validation Queries

```sql
-- CHECK 3.1: Required fields populated on contacts
SELECT
    COUNT(*) AS total_contacts,
    COUNT(*) FILTER (WHERE first_name IS NULL) AS null_first_name,
    COUNT(*) FILTER (WHERE last_name IS NULL) AS null_last_name,
    COUNT(*) FILTER (WHERE email IS NULL AND phone IS NULL) AS no_contact_method,
    COUNT(*) FILTER (WHERE org_id IS NULL) AS null_org_id,
    ROUND(
        COUNT(*) FILTER (WHERE first_name IS NULL OR last_name IS NULL)::numeric
        / NULLIF(COUNT(*), 0) * 100, 2
    ) AS null_rate_pct
FROM contacts
WHERE org_id = $1;
-- PASS: null_rate_pct < 2.0

-- CHECK 3.5: Contact method validity
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE email ~* '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        AS valid_email,
    COUNT(*) FILTER (WHERE phone ~ '^\+?[1-9]\d{9,14}$') AS valid_phone,
    ROUND(
        (COUNT(*) FILTER (WHERE
            email ~* '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            OR phone ~ '^\+?[1-9]\d{9,14}$'
        ))::numeric / NULLIF(COUNT(*), 0) * 100, 2
    ) AS valid_contact_rate_pct
FROM contacts
WHERE org_id = $1;
-- PASS: valid_contact_rate_pct > 95.0

-- CHECK 3.6-3.9: Referential integrity
-- Orphaned loans (no valid contact)
SELECT l.id AS orphaned_loan_id, l.loan_number
FROM loans l
LEFT JOIN contacts c ON l.contact_id = c.id
WHERE l.org_id = $1
  AND c.id IS NULL;
-- PASS: 0 rows

-- Orphaned tasks (invalid assignee)
SELECT t.id AS orphaned_task_id, t.title
FROM tasks t
LEFT JOIN users u ON t.assigned_to = u.id
WHERE t.org_id = $1
  AND t.assigned_to IS NOT NULL
  AND u.id IS NULL;
-- PASS: 0 rows

-- CHECK 3.10: FK constraints enforced at DB level
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY tc.table_name;
-- Verify critical FKs: loans→contacts, tasks→users, documents→loans

-- CHECK 3.11-3.13: Duplicate detection
SELECT email, COUNT(*) AS dupe_count
FROM contacts
WHERE org_id = $1
  AND email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY dupe_count DESC;
-- PASS: < 1% duplicate rate

-- CHECK 3.18-3.20: PII protection
-- SSN encryption check
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'contacts'
  AND column_name LIKE '%ssn%';
-- PASS: Column should be type TEXT (encrypted), not integer/varchar with raw SSN

-- PII in logs check (run against log output)
-- grep -rn "\\b[0-9]{3}-[0-9]{2}-[0-9]{4}\\b" /var/log/perennia/
-- PASS: 0 matches
```

---

## Domain 4: Security — Test Patterns

```python
# CHECK 4.1: JWT token expiration
async def check_jwt_expiration(client, expired_token):
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    return {
        "check_id": "4.1",
        "status_code": resp.status_code,
        "pass": resp.status_code == 401
    }

# CHECK 4.4: Account lockout
async def check_account_lockout(client, test_email):
    for i in range(11):
        resp = await client.post("/api/v1/auth/login", json={
            "email": test_email,
            "password": f"wrong_password_{i}"
        })
    return {
        "check_id": "4.4",
        "final_status": resp.status_code,
        "pass": resp.status_code == 429 or "locked" in resp.text.lower()
    }

# CHECK 4.12: SQL injection
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE contacts; --",
    "' OR '1'='1",
    "'; SELECT * FROM users; --",
    "1; UPDATE users SET role='admin' WHERE 1=1; --",
    "' UNION SELECT NULL, email, password_hash FROM users --",
]

async def check_sql_injection(client, token):
    results = []
    for payload in SQL_INJECTION_PAYLOADS:
        resp = await client.get(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
            params={"search": payload}
        )
        results.append({
            "payload": payload[:30] + "...",
            "status": resp.status_code,
            "safe": resp.status_code in (200, 400, 422)  # Not 500
        })
    return {
        "check_id": "4.12",
        "payloads_tested": len(results),
        "all_safe": all(r["safe"] for r in results),
        "pass": all(r["safe"] for r in results)
    }

# CHECK 4.13: XSS prevention
XSS_PAYLOADS = [
    '<script>alert("xss")</script>',
    '<img src=x onerror=alert("xss")>',
    '"><script>alert(document.cookie)</script>',
    "javascript:alert('xss')",
    '<svg onload=alert("xss")>',
]

async def check_xss_prevention(client, token):
    results = []
    for payload in XSS_PAYLOADS:
        # Create a contact with XSS in the name
        resp = await client.post(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
            json={"first_name": payload, "last_name": "Test", "email": "xss@test.com"}
        )
        if resp.status_code in (200, 201):
            contact = resp.json()
            # Retrieve and check if payload is escaped
            get_resp = await client.get(
                f"/api/v1/contacts/{contact['id']}",
                headers={"Authorization": f"Bearer {token}"}
            )
            stored = get_resp.json().get("first_name", "")
            results.append({
                "payload": payload[:30],
                "stored_as": stored[:50],
                "safe": "<script>" not in stored and "onerror=" not in stored
            })
    return {
        "check_id": "4.13",
        "payloads_tested": len(results),
        "all_safe": all(r["safe"] for r in results),
        "pass": all(r["safe"] for r in results)
    }

# CHECK 4.20: Secrets in source code
SECRETS_PATTERNS = [
    r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9]{20,}',
    r'(?i)(secret|password|passwd)\s*[=:]\s*["\'][^\s]{8,}',
    r'sk-[a-zA-Z0-9]{20,}',  # Anthropic/OpenAI keys
    r'SG\.[a-zA-Z0-9]{22}\.[a-zA-Z0-9]{43}',  # SendGrid
    r'AC[a-f0-9]{32}',  # Twilio Account SID
    r'(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*',  # Bearer tokens
]

# CHECK 4.24: Dependency vulnerability scan
# pip audit --json > audit_results.json
# npm audit --json > npm_audit_results.json
```

---

## Domain 6: Performance — Load Test Patterns

```python
# CHECK 6.1-6.4: API performance under load
import aiohttp
import statistics
import time

async def load_test_endpoint(
    url: str,
    token: str,
    concurrent_users: int = 100,
    requests_per_user: int = 10,
    method: str = "GET",
    payload: dict = None,
):
    latencies = []
    errors = 0

    async def single_request(session):
        nonlocal errors
        start = time.monotonic()
        try:
            if method == "GET":
                async with session.get(url, headers={
                    "Authorization": f"Bearer {token}"
                }) as resp:
                    await resp.read()
                    if resp.status >= 500:
                        errors += 1
            elif method == "POST":
                async with session.post(url, headers={
                    "Authorization": f"Bearer {token}"
                }, json=payload) as resp:
                    await resp.read()
                    if resp.status >= 500:
                        errors += 1
        except Exception:
            errors += 1
        finally:
            latencies.append((time.monotonic() - start) * 1000)

    async with aiohttp.ClientSession() as session:
        tasks = [
            single_request(session)
            for _ in range(concurrent_users * requests_per_user)
        ]
        await asyncio.gather(*tasks)

    sorted_lat = sorted(latencies)
    total = len(sorted_lat)
    return {
        "url": url,
        "concurrent_users": concurrent_users,
        "total_requests": total,
        "errors": errors,
        "error_rate_pct": round(errors / total * 100, 3),
        "p50_ms": round(sorted_lat[int(total * 0.50)], 1),
        "p95_ms": round(sorted_lat[int(total * 0.95)], 1),
        "p99_ms": round(sorted_lat[int(total * 0.99)], 1),
        "max_ms": round(sorted_lat[-1], 1),
        "rps": round(total / (sum(sorted_lat) / 1000 / concurrent_users), 1),
    }


# CHECK 6.5: Slow query detection
SLOW_QUERY_SQL = """
SELECT
    calls,
    round(mean_exec_time::numeric, 2) AS avg_ms,
    round(max_exec_time::numeric, 2) AS max_ms,
    round(total_exec_time::numeric, 2) AS total_ms,
    left(query, 100) AS query_preview
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY mean_exec_time DESC
LIMIT 20;
"""

# CHECK 6.7: Missing index detection
MISSING_INDEX_SQL = """
SELECT
    schemaname, relname AS table_name,
    seq_scan, idx_scan,
    seq_scan - idx_scan AS too_many_seq_scans,
    pg_size_pretty(pg_relation_size(relid)) AS table_size
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
  AND pg_relation_size(relid) > 10485760  -- > 10MB
ORDER BY too_many_seq_scans DESC
LIMIT 20;
"""
```

---

## Domain 7: Integration Health — Sync Validation

```python
# CHECK 7.3: Bidirectional sync integrity
async def check_sync_round_trip(los_client, db, test_loan_id):
    """Push a record to LOS, pull it back, diff the fields."""
    # Get current CRM state
    crm_record = await db.fetchrow(
        "SELECT * FROM loans WHERE id = $1", test_loan_id
    )

    # Push to LOS
    push_result = await los_client.push_loan(crm_record)

    # Wait for sync
    await asyncio.sleep(5)

    # Pull from LOS
    los_record = await los_client.get_loan(push_result["los_loan_id"])

    # Diff critical fields
    critical_fields = [
        "loan_amount", "interest_rate", "loan_term",
        "property_address", "borrower_name", "loan_status"
    ]
    diffs = {}
    for field in critical_fields:
        crm_val = crm_record.get(field)
        los_val = los_record.get(field)
        if str(crm_val) != str(los_val):
            diffs[field] = {"crm": crm_val, "los": los_val}

    return {
        "check_id": "7.3",
        "fields_checked": len(critical_fields),
        "fields_matched": len(critical_fields) - len(diffs),
        "diffs": diffs,
        "delta_pct": round(len(diffs) / len(critical_fields) * 100, 1),
        "pass": len(diffs) / len(critical_fields) < 0.02  # < 2% delta
    }

# CHECK 7.4: Sync latency
async def check_sync_latency(db, org_id):
    query = """
        SELECT
            provider,
            direction,
            AVG(EXTRACT(EPOCH FROM (completed_at - initiated_at))) AS avg_seconds,
            MAX(EXTRACT(EPOCH FROM (completed_at - initiated_at))) AS max_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (completed_at - initiated_at))
            ) AS p95_seconds
        FROM sync_events
        WHERE org_id = $1
          AND completed_at > NOW() - INTERVAL '24 hours'
        GROUP BY provider, direction
    """
    rows = await db.fetch(query, org_id)
    return {
        "check_id": "7.4",
        "providers": [
            {
                "provider": r["provider"],
                "direction": r["direction"],
                "avg_seconds": round(r["avg_seconds"], 1),
                "p95_seconds": round(r["p95_seconds"], 1),
                "pass": r["p95_seconds"] < 60  # < 60s SLA
            }
            for r in rows
        ]
    }
```

---

## Domain 12: White-Label — Branding Leak Detection

```python
# CHECK 12.12: Branding leak scan
PERENNIA_PATTERNS = [
    "perennia",
    "pipeline 360",
    "pipeline360",
    "tl development",
    "tldevelopment",
]

async def check_branding_leaks(client, tenant_domain, token):
    """Scan all user-facing output for platform branding leaks."""
    pages_to_check = [
        "/",                    # Landing/login
        "/dashboard",           # Main dashboard
        "/pipeline",            # Pipeline view
        "/contacts",            # Contact list
        "/portal/borrower",     # Borrower portal
    ]
    leaks = []
    for page in pages_to_check:
        resp = await client.get(
            f"https://{tenant_domain}{page}",
            headers={"Authorization": f"Bearer {token}"}
        )
        content = resp.text.lower()
        for pattern in PERENNIA_PATTERNS:
            if pattern in content:
                leaks.append({
                    "page": page,
                    "pattern": pattern,
                    "context": content[
                        max(0, content.index(pattern) - 30):
                        content.index(pattern) + len(pattern) + 30
                    ]
                })

    # Also check email templates
    templates = await client.get(
        "/api/v1/email-templates",
        headers={"Authorization": f"Bearer {token}"}
    )
    for tmpl in templates.json().get("items", []):
        content = (tmpl.get("html_body", "") + tmpl.get("subject", "")).lower()
        for pattern in PERENNIA_PATTERNS:
            if pattern in content:
                leaks.append({
                    "page": f"email_template:{tmpl['id']}",
                    "pattern": pattern,
                })

    return {
        "check_id": "12.12",
        "pages_scanned": len(pages_to_check),
        "templates_scanned": len(templates.json().get("items", [])),
        "leaks_found": len(leaks),
        "leaks": leaks,
        "pass": len(leaks) == 0
    }
```

---

## CLI Runner

```python
# enterprise_validator.py — Main entry point
import argparse
import uuid

DOMAIN_MODES = {
    "full": list(range(1, 13)),
    "security": [1, 4, 8],
    "compliance": [2, 3],
    "onboarding": [5, 6, 10, 12],
    "integration": [7, 11],
    "performance": [6],
}


async def run_audit(mode: str, tenant_id: str, output_dir: str):
    domains_to_run = DOMAIN_MODES.get(mode, list(range(1, 13)))

    report = EnterpriseReadinessReport(
        report_id=str(uuid.uuid4()),
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
    )

    domain_runners = {
        1: run_domain_1_multi_tenant,
        2: run_domain_2_compliance,
        3: run_domain_3_data_quality,
        4: run_domain_4_security,
        5: run_domain_5_onboarding,
        6: run_domain_6_performance,
        7: run_domain_7_integration,
        8: run_domain_8_disaster_recovery,
        9: run_domain_9_analytics,
        10: run_domain_10_migration,
        11: run_domain_11_api_gateway,
        12: run_domain_12_white_label,
    }

    for domain_id in domains_to_run:
        runner = domain_runners.get(domain_id)
        if runner:
            logger.info(f"Running Domain {domain_id}...")
            domain_result = await runner(tenant_id)
            report.domains.append(domain_result)
            logger.info(
                f"  Domain {domain_id}: {domain_result.score}/100 "
                f"({domain_result.grade.value})"
            )

    # Output
    json_path = f"{output_dir}/enterprise_readiness_{report.report_id}.json"
    md_path = f"{output_dir}/enterprise_readiness_{report.report_id}.md"

    with open(json_path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)

    with open(md_path, "w") as f:
        f.write(generate_markdown_report(report))

    # Summary
    print(f"\n{'='*60}")
    print(f"ENTERPRISE READINESS REPORT")
    print(f"{'='*60}")
    print(f"Overall Score: {report.overall_score}/100 ({report.overall_grade.value})")
    print(f"Enterprise Ready: {'YES' if report.enterprise_ready else 'NO'}")
    if report.blocking_failures:
        print(f"Blocking Failures: {', '.join(report.blocking_failures)}")
    print(f"\nDomain Scores:")
    for d in report.domains:
        status = "✅" if d.grade in (Grade.A, Grade.B) else "⚠️" if d.grade == Grade.C else "❌"
        print(f"  {status} {d.domain_id:2d}. {d.name:<35s} {d.score:3d}/100 ({d.grade.value})")
    print(f"\nReports saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")

    return 0 if report.enterprise_ready else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perennia AI Enterprise Readiness Validator")
    parser.add_argument("--mode", choices=list(DOMAIN_MODES.keys()) + ["targeted"],
                       default="full")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--output-dir", default="./reports")
    parser.add_argument("--domains", nargs="+", type=int,
                       help="Specific domain IDs for targeted mode")
    args = parser.parse_args()

    exit_code = asyncio.run(run_audit(args.mode, args.tenant_id, args.output_dir))
    exit(exit_code)
```

---

## Execution Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@host:5432/perennia
DATABASE_URL_TEST=postgresql://user:pass@host:5432/perennia_test

# API
API_BASE_URL=https://api.perenniaai.com
API_TEST_TOKEN_TENANT_A=...
API_TEST_TOKEN_TENANT_B=...

# Integrations
SALESFORCE_TEST_ORG_URL=https://test.salesforce.com
BYTEPRO_TEST_API_KEY=...
TWILIO_TEST_ACCOUNT_SID=...
MS_GRAPH_TEST_TOKEN=...

# Test Tenant IDs
TEST_TENANT_A_ID=uuid-for-tenant-a
TEST_TENANT_B_ID=uuid-for-tenant-b
TEST_ADMIN_USER_ID=uuid-for-admin

# Output
REPORT_OUTPUT_DIR=./reports
```
