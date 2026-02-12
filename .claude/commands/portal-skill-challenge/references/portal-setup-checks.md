# Portal Setup Checks — Detailed Definitions

## PS-001: Portal Route Resolves

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Each portal type has a base route that must return HTTP 200 (or 302 redirect to auth). This confirms the portal is deployed and reachable.

**Test procedure:**
```python
async def check_ps_001(config):
    endpoints = {
        "borrower": f"{config.base_url}/portal/{config.test_purl_slug}",
        "partner": f"{config.base_url}/partners/{config.test_partner_slug}",
        "lo": f"{config.base_url}/lo/{config.test_lo_slug}",
    }
    results = {}
    for portal_type, url in endpoints.items():
        response = await http_client.get(url, allow_redirects=False)
        results[portal_type] = {
            "passed": response.status_code in (200, 302),
            "status_code": response.status_code,
            "url": url,
        }
    return results
```

**Pass criteria:** HTTP 200 or 302  
**Fail criteria:** HTTP 404, 500, connection timeout  
**Remediation:** Check deployment status on Vercel/Railway. Verify routing config. Check DNS resolution.

---

## PS-002: PURL Workspace Exists and Status Is Valid

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
The PURL workspace for the test borrower exists in the database and has a valid status (`lead`, `active`, `in_progress`, `closed`).

**Test procedure:**
```python
async def check_ps_002(config):
    result = await db.execute(
        """
        SELECT id, slug, status, display_name, created_at
        FROM purl_workspaces
        WHERE slug = :slug AND organization_id = :org_id
        """,
        {"slug": config.test_purl_slug, "org_id": config.test_org_id}
    )
    workspace = result.fetchone()
    valid_statuses = {"lead", "active", "in_progress", "closed"}
    return {
        "passed": workspace is not None and workspace.status in valid_statuses,
        "workspace_id": str(workspace.id) if workspace else None,
        "status": workspace.status if workspace else "NOT_FOUND",
    }
```

**Pass criteria:** Workspace exists with valid status  
**Fail criteria:** Workspace not found, or status is invalid/null  
**Remediation:** Run workspace creation flow. Check migration ran successfully.

---

## PS-003: Portal Modules Match Subscription Tier

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
The modules enabled for a portal match what the org's subscription tier allows. A "Lead" tier user should not see "Portfolio" modules.

**Test procedure:**
```python
async def check_ps_003(config):
    # Get org subscription
    sub = await get_org_subscription(config.test_org_id)
    # Get enabled modules
    modules = await get_enabled_portal_modules(config.test_org_id)
    # Get tier-allowed modules
    allowed = TIER_MODULE_MAP[sub.tier]
    # Check for unauthorized modules
    unauthorized = [m for m in modules if m not in allowed]
    return {
        "passed": len(unauthorized) == 0,
        "tier": sub.tier,
        "enabled_modules": modules,
        "unauthorized_modules": unauthorized,
    }
```

**Pass criteria:** All enabled modules are within subscription tier  
**Fail criteria:** Modules enabled that exceed tier  
**Remediation:** Update portal_modules table. Check subscription enforcement middleware.

---

## PS-004: Branding Assets Load

**Severity:** MEDIUM  
**Applies to:** All portals

**What it checks:**  
Organization branding (logo, primary color, favicon) loads correctly via HTTP 200.

**Test procedure:**
```python
async def check_ps_004(config):
    branding = await get_org_branding(config.test_org_id)
    results = {}
    for asset_name, asset_url in branding.items():
        if asset_url:
            response = await http_client.head(asset_url)
            results[asset_name] = {
                "passed": response.status_code == 200,
                "url": asset_url,
                "status_code": response.status_code,
            }
        else:
            results[asset_name] = {"passed": True, "note": "Using default"}
    return {
        "passed": all(r["passed"] for r in results.values()),
        "assets": results,
    }
```

---

## PS-005: Feature Flags Match Org Configuration

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
Runtime feature flags (e.g., `enable_ai_assistant`, `enable_voice`, `enable_document_upload`) match the org's configuration record.

---

## PS-006: SSL/TLS Certificate Valid

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
SSL certificate is valid, not self-signed, and has > 30 days before expiry.

**Test procedure:**
```python
async def check_ps_006(config):
    import ssl, socket
    from datetime import datetime
    
    hostname = urlparse(config.base_url).hostname
    ctx = ssl.create_default_context()
    with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
        s.settimeout(10)
        s.connect((hostname, 443))
        cert = s.getpeercert()
    
    expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
    days_remaining = (expiry - datetime.utcnow()).days
    
    return {
        "passed": days_remaining > 30,
        "days_remaining": days_remaining,
        "expiry_date": expiry.isoformat(),
        "issuer": dict(x[0] for x in cert['issuer']),
    }
```

---

## PS-007: CORS Configuration

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
CORS headers only allow expected origins. No wildcard `*` in production.

**Test procedure:**
```python
async def check_ps_007(config):
    # Test with expected origin
    resp = await http_client.options(
        f"{config.api_url}/api/v1/health",
        headers={"Origin": config.expected_origin}
    )
    allowed_origin = resp.headers.get("Access-Control-Allow-Origin")
    
    # Test with malicious origin
    resp_bad = await http_client.options(
        f"{config.api_url}/api/v1/health",
        headers={"Origin": "https://evil.example.com"}
    )
    bad_origin = resp_bad.headers.get("Access-Control-Allow-Origin")
    
    return {
        "passed": (
            allowed_origin == config.expected_origin
            and bad_origin != "https://evil.example.com"
            and bad_origin != "*"
        ),
        "allowed_origin": allowed_origin,
        "rejected_malicious": bad_origin is None,
    }
```

---

## PS-008 through PS-010

**PS-008: Custom Domain DNS** — Verify partner/LO custom domains resolve to correct Vercel/Railway endpoints.  
**PS-009: Portal Modules Render** — Headless browser check that portal tabs load without JS console errors.  
**PS-010: Mobile Responsive** — Verify viewport meta tag and key breakpoints (375px, 768px, 1024px) render correctly.
