# User Access Checks — Detailed Definitions

## UA-001: Token Generation Returns Valid Token with Correct Scopes

**Severity:** CRITICAL  
**Applies to:** Borrower (PURL)

**What it checks:**  
The PURL token generation endpoint creates a `purl_live_*` token with the requested scopes (read, write, full) and correct expiry.

**Test procedure:**
```python
async def check_ua_001(config):
    # Generate a test token via admin endpoint
    response = await http_client.post(
        f"{config.api_url}/api/v1/purl-admin/tokens",
        headers={"Authorization": f"Bearer {config.admin_jwt}"},
        json={
            "workspace_id": config.test_workspace_id,
            "scope": "read",
            "expires_in_hours": 24,
        }
    )
    token_data = response.json()
    
    # Verify token structure
    token = token_data.get("token", "")
    has_prefix = token.startswith("purl_live_")
    
    # Verify token works
    verify_resp = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    return {
        "passed": has_prefix and verify_resp.status_code == 200,
        "has_prefix": has_prefix,
        "scope": token_data.get("scope"),
        "verify_status": verify_resp.status_code,
        "expires_at": token_data.get("expires_at"),
    }
```

**Pass criteria:** Token generated, prefix correct, scope matches, and token authenticates  
**Fail criteria:** Token generation fails, wrong prefix, scope mismatch, or auth fails  
**Remediation:** Check purl_token_service.py, verify purl_access_tokens table exists.

---

## UA-002: Expired Tokens Are Rejected

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
A token with an expired `expires_at` timestamp returns HTTP 401 Unauthorized.

**Test procedure:**
```python
async def check_ua_002(config):
    # Use a pre-generated expired token OR generate one with -1h expiry
    expired_token = config.expired_test_token
    
    # Attempt access with expired token
    response = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    
    return {
        "passed": response.status_code == 401,
        "status_code": response.status_code,
        "error_message": response.json().get("detail", ""),
    }
```

**Pass criteria:** HTTP 401  
**Fail criteria:** HTTP 200 or any non-401  
**Remediation:** Check token validation middleware. Verify expiry check in purl_auth.py.

---

## UA-003: Revoked Tokens Are Rejected Immediately

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
After revoking a token via the admin API, the token is immediately rejected.

**Test procedure:**
```python
async def check_ua_003(config):
    # Generate fresh token
    token = await generate_test_token(config, scope="read")
    
    # Confirm it works
    resp1 = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp1.status_code == 200, "Token should work before revocation"
    
    # Revoke the token
    await http_client.post(
        f"{config.api_url}/api/v1/purl-admin/tokens/revoke",
        headers={"Authorization": f"Bearer {config.admin_jwt}"},
        json={"token": token}
    )
    
    # Attempt access with revoked token
    resp2 = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    return {
        "passed": resp1.status_code == 200 and resp2.status_code == 401,
        "pre_revoke_status": resp1.status_code,
        "post_revoke_status": resp2.status_code,
    }
```

---

## UA-004: OAuth Flow Completes

**Severity:** CRITICAL  
**Applies to:** Partner / LO portals

**What it checks:**  
The Salesforce OAuth authorization flow initiates correctly (302 redirect to Salesforce), and the callback endpoint exchanges the code for a valid JWT.

---

## UA-005: Role-Based Permissions Enforce Correct Access

**Severity:** CRITICAL  
**Applies to:** LO Portal

**What it checks:**  
Each of the 10 user roles (Application Analysis, Concierge, Jr. LO, etc.) can only access resources permitted by their role template. Tests permission boundaries:

- Jr. LO cannot access admin settings
- Concierge can view but not modify loan terms
- Manager can see all team members' pipelines

**Test procedure:**
```python
async def check_ua_005(config):
    role_tests = [
        {"role": "jr_loan_officer", "endpoint": "/api/v1/admin/settings", "expected": 403},
        {"role": "concierge", "endpoint": "/api/v1/loans/update-terms", "expected": 403},
        {"role": "manager", "endpoint": "/api/v1/team/pipeline", "expected": 200},
        {"role": "application_analysis", "endpoint": "/api/v1/loans/review", "expected": 200},
    ]
    
    results = []
    for test in role_tests:
        token = config.role_tokens[test["role"]]
        resp = await http_client.get(
            f"{config.api_url}{test['endpoint']}",
            headers={"Authorization": f"Bearer {token}"}
        )
        passed = resp.status_code == test["expected"]
        results.append({
            "role": test["role"],
            "endpoint": test["endpoint"],
            "expected": test["expected"],
            "actual": resp.status_code,
            "passed": passed,
        })
    
    return {
        "passed": all(r["passed"] for r in results),
        "role_tests": results,
    }
```

---

## UA-006: Scope Enforcement — Read-Only Token Cannot Write

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
A PURL token with `scope=read` is rejected (HTTP 403) when attempting write operations (POST, PUT, PATCH, DELETE).

**Test procedure:**
```python
async def check_ua_006(config):
    read_token = await generate_test_token(config, scope="read")
    
    write_operations = [
        ("POST", "/api/v1/purl/messages", {"content": "test"}),
        ("PUT", "/api/v1/purl/application", {"first_name": "test"}),
        ("DELETE", "/api/v1/purl/documents/test-id", None),
    ]
    
    results = []
    for method, endpoint, body in write_operations:
        resp = await http_client.request(
            method,
            f"{config.api_url}{endpoint}",
            headers={"Authorization": f"Bearer {read_token}"},
            json=body,
        )
        results.append({
            "method": method,
            "endpoint": endpoint,
            "status": resp.status_code,
            "passed": resp.status_code == 403,
        })
    
    return {
        "passed": all(r["passed"] for r in results),
        "operations": results,
    }
```

---

## UA-007: Rate Limiting Triggers

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
Per-token rate limits (60/min, 1000/hr) trigger correctly. After exceeding the threshold, requests return HTTP 429.

**Test procedure:**
```python
async def check_ua_007(config):
    token = await generate_test_token(config, scope="read")
    
    # Send requests up to just under the limit
    for i in range(58):
        await http_client.get(
            f"{config.api_url}/api/v1/purl/workspace",
            headers={"Authorization": f"Bearer {token}"}
        )
    
    # Next few should still work
    resp_ok = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Exceed limit
    for i in range(5):
        await http_client.get(
            f"{config.api_url}/api/v1/purl/workspace",
            headers={"Authorization": f"Bearer {token}"}
        )
    
    resp_limited = await http_client.get(
        f"{config.api_url}/api/v1/purl/workspace",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    return {
        "passed": resp_ok.status_code == 200 and resp_limited.status_code == 429,
        "pre_limit_status": resp_ok.status_code,
        "post_limit_status": resp_limited.status_code,
        "retry_after": resp_limited.headers.get("Retry-After"),
    }
```

---

## UA-008 through UA-012

**UA-008: Session Timeout** — Verify inactive sessions expire after configured period. Check for session cookie expiry or JWT exp claim.

**UA-009: Concurrent Sessions** — For LO portal, verify that only N concurrent sessions are allowed per policy. New login should invalidate oldest.

**UA-010: Token Refresh** — Verify refresh token flow issues new access token without re-authentication. Old access token should be invalid after refresh.

**UA-011: Multi-Tenant Isolation** — Generate tokens for Org A and Org B. Verify Org A's token cannot access Org B's workspace data. This is THE most critical access control check.

**UA-012: Subscription Tier Gating** — Verify that attempting to access a feature outside the org's subscription tier returns HTTP 403 with a clear upgrade message.
