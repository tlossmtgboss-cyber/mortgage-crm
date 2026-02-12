# CRM Data Sync Checks — Detailed Definitions

## SYNC-001: Salesforce OAuth Token Is Valid

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
The per-user Salesforce integration profile has a valid, non-expired access token. If expired, the refresh token flow works.

**Test procedure:**
```python
async def check_sync_001(config):
    # Get integration profile for test user
    profile = await db.execute("""
        SELECT id, status, instance_url, token_encrypted, refresh_token_encrypted,
               token_expires_at, last_sync_at
        FROM integration_profiles
        WHERE user_id = :user_id AND provider = 'salesforce'
    """, {"user_id": config.test_user_id})
    
    prof = profile.fetchone()
    if not prof:
        return {"passed": False, "reason": "No Salesforce integration profile found"}
    
    # Decrypt and test token
    access_token = decrypt_token(prof.token_encrypted)
    
    # Call Salesforce identity endpoint
    sf_resp = await http_client.get(
        f"{prof.instance_url}/services/oauth2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    token_valid = sf_resp.status_code == 200
    
    # If token expired, test refresh
    refresh_worked = None
    if not token_valid and prof.refresh_token_encrypted:
        refresh_token = decrypt_token(prof.refresh_token_encrypted)
        refresh_resp = await http_client.post(
            f"{config.salesforce_token_url}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": config.sf_client_id,
                "client_secret": config.sf_client_secret,
            }
        )
        refresh_worked = refresh_resp.status_code == 200
    
    return {
        "passed": token_valid or refresh_worked == True,
        "profile_status": prof.status,
        "token_valid": token_valid,
        "refresh_worked": refresh_worked,
        "instance_url": prof.instance_url,
        "last_sync_at": str(prof.last_sync_at) if prof.last_sync_at else None,
    }
```

**Pass criteria:** Token valid OR refresh succeeds  
**Fail criteria:** Token expired AND refresh fails  
**Remediation:** User needs to re-authorize Salesforce OAuth. Check connected app settings. Verify refresh token hasn't been revoked.

---

## SYNC-002: Field Mapping Configuration Is Complete

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
All required CRM fields have a corresponding Salesforce field mapping. No required fields are unmapped.

**Test procedure:**
```python
async def check_sync_002(config):
    # Get required CRM fields
    required_fields = await db.execute("""
        SELECT field_name, field_label, is_required, object_type
        FROM crm_field_definitions
        WHERE is_required = true AND sync_enabled = true
    """)
    
    # Get user's field mappings
    mappings = await db.execute("""
        SELECT crm_field, salesforce_object, salesforce_field, transform_type
        FROM field_mappings
        WHERE user_id = :user_id AND is_active = true
    """, {"user_id": config.test_user_id})
    
    mapped_fields = {m.crm_field for m in mappings}
    required = required_fields.fetchall()
    
    unmapped = []
    for field in required:
        if field.field_name not in mapped_fields:
            unmapped.append({
                "field": field.field_name,
                "label": field.field_label,
                "object_type": field.object_type,
            })
    
    return {
        "passed": len(unmapped) == 0,
        "total_required": len(required),
        "total_mapped": len(mapped_fields),
        "unmapped_required": unmapped,
    }
```

**Pass criteria:** All required fields have mappings  
**Fail criteria:** Any required field unmapped  
**Remediation:** Navigate to Settings → Salesforce → Field Mapping. Complete mapping for missing fields.

---

## SYNC-003: Push Sync — CRM Create Appears in Salesforce < 60s

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Creating a test record in the CRM triggers a push to Salesforce within the SLA (< 5s immediate push, < 60s polling fallback).

**Test procedure:**
```python
async def check_sync_003(config):
    import time
    
    # Create a test lead in CRM
    test_lead = await http_client.post(
        f"{config.api_url}/api/v1/leads",
        headers={"Authorization": f"Bearer {config.admin_jwt}"},
        json={
            "first_name": "SyncTest",
            "last_name": f"Validator_{int(time.time())}",
            "email": f"synctest_{int(time.time())}@test.perennia.ai",
            "phone": "+15551234567",
            "source": "portal_validator",
        }
    )
    lead_id = test_lead.json()["id"]
    create_time = time.time()
    
    # Poll Salesforce for the record (up to 90s)
    sf_found = False
    sf_latency = None
    access_token = await get_sf_token(config)
    
    for attempt in range(18):  # 18 * 5s = 90s max
        await asyncio.sleep(5)
        
        sf_query = await http_client.get(
            f"{config.sf_instance_url}/services/data/v60.0/query",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": f"SELECT Id FROM Lead WHERE Email = '{test_lead.json()['email']}'"}
        )
        
        records = sf_query.json().get("records", [])
        if len(records) > 0:
            sf_found = True
            sf_latency = time.time() - create_time
            break
    
    # Cleanup: delete test lead
    await cleanup_test_lead(config, lead_id)
    
    return {
        "passed": sf_found and (sf_latency or 999) < 60,
        "sf_record_found": sf_found,
        "latency_seconds": round(sf_latency, 2) if sf_latency else None,
        "sla_target_seconds": 60,
        "within_sla": (sf_latency or 999) < 60,
    }
```

**Pass criteria:** Salesforce record appears within 60 seconds  
**Fail criteria:** Record not found after 90s, or latency > 60s  
**Remediation:** Check sync job status. Verify push queue is processing. Check Railway worker logs.

---

## SYNC-004: Pull Sync — Salesforce Update Reflects in CRM < 60s

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Updating a field in Salesforce triggers the pull sync to update the CRM within 60 seconds.

**Test procedure:**
```python
async def check_sync_004(config):
    import time
    
    # Find a synced record
    synced_record = await get_synced_test_record(config)
    sf_id = synced_record["salesforce_id"]
    crm_id = synced_record["crm_id"]
    
    # Update a field in Salesforce
    new_phone = f"+1555{int(time.time()) % 10000000:07d}"
    access_token = await get_sf_token(config)
    
    await http_client.patch(
        f"{config.sf_instance_url}/services/data/v60.0/sobjects/Lead/{sf_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"Phone": new_phone}
    )
    update_time = time.time()
    
    # Poll CRM for the updated value (up to 90s)
    crm_updated = False
    pull_latency = None
    
    for attempt in range(18):
        await asyncio.sleep(5)
        
        crm_record = await http_client.get(
            f"{config.api_url}/api/v1/leads/{crm_id}",
            headers={"Authorization": f"Bearer {config.admin_jwt}"}
        )
        
        if crm_record.json().get("phone") == new_phone:
            crm_updated = True
            pull_latency = time.time() - update_time
            break
    
    return {
        "passed": crm_updated and (pull_latency or 999) < 60,
        "crm_updated": crm_updated,
        "latency_seconds": round(pull_latency, 2) if pull_latency else None,
        "sla_target_seconds": 60,
        "within_sla": (pull_latency or 999) < 60,
    }
```

---

## SYNC-005: Conflict Resolution

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
When both CRM and Salesforce modify the same record within the same sync cycle, the configured conflict policy (`last_write_wins`, `crm_wins`, `outlook_wins`) is applied correctly.

---

## SYNC-006: Lead Status Changes Trigger Workflows

**Severity:** CRITICAL  
**Applies to:** Borrower / LO

**What it checks:**  
When a lead status changes in Salesforce (e.g., `New` → `Contacted` → `Qualified`), the corresponding CRM workflow triggers (task creation, notification, stage advancement).

```python
async def check_sync_006(config):
    # Update lead status in Salesforce
    await update_sf_lead_status(config, status="Qualified")
    
    # Wait for sync
    await asyncio.sleep(65)
    
    # Check CRM for:
    # 1. Status updated
    lead = await get_crm_lead(config)
    status_synced = lead["status"] == "qualified"
    
    # 2. SLA task generated
    tasks = await get_lead_tasks(config, lead["id"])
    task_generated = any(t["type"] == "sla_follow_up" for t in tasks)
    
    # 3. Milestone updated
    milestones = await get_lead_milestones(config, lead["id"])
    milestone_updated = any(m["name"] == "qualified" and m["completed"] for m in milestones)
    
    return {
        "passed": status_synced and task_generated and milestone_updated,
        "status_synced": status_synced,
        "task_generated": task_generated,
        "milestone_updated": milestone_updated,
    }
```

---

## SYNC-007 through SYNC-014

**SYNC-007: Contact/Borrower Profile Match** — Compare 10 key fields (name, email, phone, address, employer, etc.) between CRM and Salesforce for test record. All should match after sync.

**SYNC-008: Opportunity/Loan Stage Sync** — Verify loan stage in CRM matches Salesforce opportunity stage per milestone_definitions mapping.

**SYNC-009: Sync Error Rate < 1%** — Query `integration_events` for last 24h. Calculate `error_count / total_count`. Must be < 0.01.

**SYNC-010: Retry Queue Draining** — Query `integration_record_tracking` for records with `status = 'failed'` and `updated_at < NOW() - INTERVAL '1 hour'`. Should be zero.

**SYNC-011: Echo Prevention** — After a CRM→SF push, verify the pull cycle does NOT create a duplicate or re-update the same record. Check via fingerprint/hash comparison.

**SYNC-012: Custom Object Sync** — Verify `Mortgage_App__c` and other custom Salesforce objects sync correctly to CRM.

**SYNC-013: Watermark Advancing** — Verify the sync watermark/cursor in `integration_profiles.last_sync_at` is advancing. If it's stale (> 5 minutes old), sync may be stalled.

**SYNC-014: SLA Dashboard Metrics** — Query the sync metrics aggregation and verify all 5 SLA targets are met (push latency, pull latency, echo prevention, success rate, retry rate).
