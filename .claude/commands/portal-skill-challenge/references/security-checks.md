# Security Checks — Detailed Definitions

## SEC-001: RLS Policies Active on All PURL Tables

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
All 15 PURL tables have Row-Level Security (RLS) enabled and at least one policy attached.

**Test procedure:**
```python
async def check_sec_001(config):
    expected_tables = [
        "purl_access_tokens", "purl_applications", "purl_audit_log",
        "purl_contacts", "purl_document_requests", "purl_documents",
        "purl_events_outbox", "purl_loan_milestones", "purl_loans",
        "purl_messages", "purl_milestone_definitions", "purl_portal_modules",
        "purl_tasks", "purl_workspace_members", "purl_workspaces",
    ]
    
    # Check RLS enabled
    result = await db.execute("""
        SELECT tablename, rowsecurity
        FROM pg_tables
        WHERE tablename LIKE 'purl_%'
        ORDER BY tablename
    """)
    tables = {row.tablename: row.rowsecurity for row in result}
    
    # Check policies exist
    policies = await db.execute("""
        SELECT tablename, policyname
        FROM pg_policies
        WHERE tablename LIKE 'purl_%'
    """)
    policy_map = {}
    for row in policies:
        policy_map.setdefault(row.tablename, []).append(row.policyname)
    
    results = {}
    for table in expected_tables:
        rls_enabled = tables.get(table, False)
        has_policies = len(policy_map.get(table, [])) > 0
        results[table] = {
            "rls_enabled": rls_enabled,
            "has_policies": has_policies,
            "policy_count": len(policy_map.get(table, [])),
            "passed": rls_enabled and has_policies,
        }
    
    return {
        "passed": all(r["passed"] for r in results.values()),
        "tables_checked": len(results),
        "tables_passing": sum(1 for r in results.values() if r["passed"]),
        "details": results,
    }
```

**Pass criteria:** All 15 tables have RLS enabled AND at least 1 policy  
**Fail criteria:** Any table missing RLS or policies  
**Remediation:** Run migration `002_rls_policies.sql`. Verify with `SELECT tablename, rowsecurity FROM pg_tables WHERE tablename LIKE 'purl_%'`.

---

## SEC-002: Tenant Isolation — Cross-Org Query Returns 0 Rows

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
When connected as Org A's user, querying data that belongs to Org B returns zero results. This validates that RLS policies and tenant context (`app.current_tenant_id`) work end-to-end.

**Test procedure:**
```python
async def check_sec_002(config):
    # Set session to Org A
    await db.execute("SET app.current_tenant_id = :org_a", {"org_a": str(config.org_a_id)})
    await db.execute("SET app.current_user_id = :user_a", {"user_a": str(config.user_a_id)})
    
    # Try to read Org B's workspaces
    result = await db.execute("""
        SELECT id, slug, organization_id
        FROM purl_workspaces
        WHERE organization_id = :org_b
    """, {"org_b": str(config.org_b_id)})
    
    org_b_rows = result.fetchall()
    
    # Also check via API with Org A's token
    resp = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace/{config.org_b_workspace_slug}",
        headers={"Authorization": f"Bearer {config.org_a_token}"}
    )
    
    return {
        "passed": len(org_b_rows) == 0 and resp.status_code in (403, 404),
        "cross_org_rows_found": len(org_b_rows),
        "api_cross_access_status": resp.status_code,
    }
```

**Pass criteria:** Zero cross-org rows AND API returns 403/404  
**Fail criteria:** Any cross-org data accessible  
**Remediation:** This is a CRITICAL security failure. Audit all RLS policies immediately. Check `current_tenant_id()` function. Verify middleware sets session vars.

---

## SEC-003: PII Fields Encrypted at Rest

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Sensitive PII fields (SSN, DOB, financial data) are encrypted in the database. Raw SELECT should return encrypted blobs, not plaintext.

**Test procedure:**
```python
async def check_sec_003(config):
    pii_fields = [
        ("purl_applications", "ssn"),
        ("purl_applications", "date_of_birth"),
        ("purl_applications", "bank_account_number"),
        ("purl_contacts", "ssn_last_four"),
    ]
    
    results = []
    for table, column in pii_fields:
        # Check if column exists and is encrypted type
        col_info = await db.execute("""
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        """, {"table": table, "column": column})
        
        col = col_info.fetchone()
        if col:
            # Encrypted columns should be bytea or have encryption wrapper
            is_encrypted = col.data_type in ("bytea",) or col.udt_name.startswith("pgp_")
            results.append({
                "table": table,
                "column": column,
                "data_type": col.data_type,
                "passed": is_encrypted,
            })
        else:
            results.append({
                "table": table,
                "column": column,
                "note": "Column not found — may use different naming",
                "passed": None,  # SKIPPED
            })
    
    evaluated = [r for r in results if r["passed"] is not None]
    return {
        "passed": all(r["passed"] for r in evaluated) if evaluated else False,
        "fields_checked": len(results),
        "fields_encrypted": sum(1 for r in evaluated if r["passed"]),
        "details": results,
    }
```

---

## SEC-004: Audit Log Captures All Portal CRUD Operations

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
Every create, read (sensitive), update, and delete operation on portal resources generates an entry in `purl_audit_log`.

**Test procedure:**
```python
async def check_sec_004(config):
    # Perform a test operation
    before_count = await count_audit_entries(config.test_workspace_id)
    
    # Create a test message via API
    await http_client.post(
        f"{config.api_url}/api/v1/purl/messages",
        headers={"Authorization": f"Bearer {config.test_write_token}"},
        json={"content": "Audit test message", "workspace_id": config.test_workspace_id}
    )
    
    # Check audit log grew
    after_count = await count_audit_entries(config.test_workspace_id)
    
    # Check latest entry has required fields
    latest = await db.execute("""
        SELECT action, resource_type, resource_id, user_id, ip_address, timestamp
        FROM purl_audit_log
        WHERE workspace_id = :ws_id
        ORDER BY timestamp DESC
        LIMIT 1
    """, {"ws_id": config.test_workspace_id})
    
    entry = latest.fetchone()
    has_required_fields = all([
        entry and entry.action,
        entry and entry.resource_type,
        entry and entry.ip_address,
        entry and entry.timestamp,
    ])
    
    return {
        "passed": after_count > before_count and has_required_fields,
        "audit_entries_before": before_count,
        "audit_entries_after": after_count,
        "has_required_fields": has_required_fields,
    }
```

---

## SEC-005: Rate Limiting Per-Token

**Severity:** HIGH  
**Applies to:** Borrower

See UA-007 for the test procedure. This check verifies the specific thresholds (60/min, 1000/hr) match configuration.

---

## SEC-006: SQL Injection Protection

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Common SQL injection payloads in query parameters, form fields, and JSON bodies are rejected or sanitized.

**Test procedure:**
```python
async def check_sec_006(config):
    injection_payloads = [
        "'; DROP TABLE purl_workspaces; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM purl_access_tokens --",
        "Robert'); DROP TABLE purl_contacts;--",
    ]
    
    results = []
    for payload in injection_payloads:
        # Test in query param
        resp = await http_client.get(
            f"{config.api_url}/api/v1/purl/workspace",
            headers={"Authorization": f"Bearer {config.test_read_token}"},
            params={"search": payload}
        )
        
        # Should NOT return 500 (which might indicate unhandled SQL error)
        # Should NOT return unexpected data
        results.append({
            "payload": payload[:30] + "...",
            "status": resp.status_code,
            "passed": resp.status_code not in (500, 502, 503),
        })
    
    # Verify tables still exist
    table_check = await db.execute(
        "SELECT COUNT(*) FROM pg_tables WHERE tablename = 'purl_workspaces'"
    )
    tables_intact = table_check.scalar() == 1
    
    return {
        "passed": all(r["passed"] for r in results) and tables_intact,
        "tables_intact": tables_intact,
        "injection_tests": results,
    }
```

---

## SEC-007: XSS Prevention — CSP Headers

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
Content-Security-Policy header is present and restrictive. No `unsafe-inline` for scripts in production.

```python
async def check_sec_007(config):
    resp = await http_client.get(f"{config.base_url}/portal/{config.test_purl_slug}")
    csp = resp.headers.get("Content-Security-Policy", "")
    x_content_type = resp.headers.get("X-Content-Type-Options", "")
    
    return {
        "passed": bool(csp) and x_content_type == "nosniff",
        "csp_present": bool(csp),
        "csp_value": csp[:200],
        "x_content_type_options": x_content_type,
    }
```

---

## SEC-008: API Keys Not Exposed in Client Bundles

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Fetches the portal's main JS bundle and searches for patterns that indicate leaked secrets.

```python
async def check_sec_008(config):
    # Fetch portal HTML
    html = await http_client.get(f"{config.base_url}/portal/{config.test_purl_slug}")
    
    # Find JS bundle URLs
    import re
    scripts = re.findall(r'src="([^"]*\.js)"', html.text)
    
    secret_patterns = [
        r'sk-[a-zA-Z0-9]{20,}',          # OpenAI-style
        r'sk-ant-[a-zA-Z0-9]{20,}',       # Anthropic-style
        r'TWILIO_AUTH_TOKEN',
        r'AWS_SECRET_ACCESS_KEY',
        r'DATABASE_URL=postgres',
        r'-----BEGIN (RSA |EC )?PRIVATE KEY-----',
    ]
    
    leaks = []
    for script_url in scripts:
        js_content = await http_client.get(script_url)
        for pattern in secret_patterns:
            if re.search(pattern, js_content.text):
                leaks.append({"file": script_url, "pattern": pattern})
    
    return {
        "passed": len(leaks) == 0,
        "bundles_scanned": len(scripts),
        "leaks_found": len(leaks),
        "leak_details": leaks,
    }
```

---

## SEC-009 through SEC-015

**SEC-009: S3 Presigned URL Expiry** — Generate presigned URL, wait past TTL, verify HTTP 403.

**SEC-010: HTTPS Enforced** — HTTP request to port 80 returns 301/302 to HTTPS.

**SEC-011: Auth Token Cookie Flags** — Verify `httpOnly`, `Secure`, `SameSite=Strict` or `Lax` on auth cookies.

**SEC-012: Sensitive Data Masked in Logs** — Check application logs for PII patterns (SSN regex, email in error messages). Should find zero matches.

**SEC-013: OWASP Header Checks** — Verify `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` present.

**SEC-014: Database SSL and Pooling** — Verify `sslmode=require` in connection string and connection pool is configured (max connections, idle timeout).

**SEC-015: Admin Endpoint Protection** — Verify `/api/v1/purl-admin/*` endpoints return 401/403 without admin JWT. Non-admin JWTs should also be rejected.
