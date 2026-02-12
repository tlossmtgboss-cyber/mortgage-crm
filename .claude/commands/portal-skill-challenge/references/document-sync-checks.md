# Document Sync Checks — Detailed Definitions

## DOC-001: Document Request Created in CRM Appears in Borrower Portal

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
When an LO creates a document request in the CRM (via Perennia Docs), it appears in the borrower's PURL portal document tab.

**Test procedure:**
```python
async def check_doc_001(config):
    import time
    
    # Create document request via CRM/admin API
    doc_request = await http_client.post(
        f"{config.api_url}/api/v1/perennia-docs/requests",
        headers={"Authorization": f"Bearer {config.admin_jwt}"},
        json={
            "workspace_id": config.test_workspace_id,
            "document_type": "pay_stub",
            "title": f"Pay Stub - Validator Test {int(time.time())}",
            "description": "Most recent pay stub for income verification",
            "due_date": "2026-03-01",
            "priority": "high",
        }
    )
    request_id = doc_request.json()["id"]
    create_time = time.time()
    
    # Check borrower portal API for the document request
    portal_found = False
    latency = None
    
    for attempt in range(12):  # 60s max
        await asyncio.sleep(5)
        
        portal_docs = await http_client.get(
            f"{config.api_url}/api/v1/purl/documents",
            headers={"Authorization": f"Bearer {config.borrower_token}"}
        )
        
        docs = portal_docs.json().get("documents", [])
        if any(d.get("request_id") == request_id or d.get("title", "").startswith("Pay Stub - Validator Test") for d in docs):
            portal_found = True
            latency = time.time() - create_time
            break
    
    # Cleanup
    await cleanup_doc_request(config, request_id)
    
    return {
        "passed": portal_found,
        "portal_found": portal_found,
        "latency_seconds": round(latency, 2) if latency else None,
        "request_id": request_id,
    }
```

**Pass criteria:** Document request visible in borrower portal  
**Fail criteria:** Request not visible after 60s  
**Remediation:** Check PURL-Perennia integration routes. Verify `purl_perennia_integration_routes.py` document-status endpoint. Check events_outbox processing.

---

## DOC-002: Document Upload from Portal Stores in S3 and Updates CRM

**Severity:** CRITICAL  
**Applies to:** Borrower

**What it checks:**  
When a borrower uploads a document through the PURL portal, the file is stored in S3 and the CRM document record is updated with the S3 key, upload timestamp, and status change.

**Test procedure:**
```python
async def check_doc_002(config):
    import time
    
    # Step 1: Get presigned upload URL
    upload_url_resp = await http_client.post(
        f"{config.api_url}/api/v1/purl/documents/upload-url",
        headers={"Authorization": f"Bearer {config.borrower_write_token}"},
        json={
            "workspace_id": config.test_workspace_id,
            "filename": "test_pay_stub.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
        }
    )
    
    presigned = upload_url_resp.json()
    upload_url = presigned.get("upload_url")
    document_id = presigned.get("document_id")
    
    # Step 2: Upload test file to S3 via presigned URL
    test_file_content = b"%PDF-1.4 test content for validator"
    s3_resp = await http_client.put(
        upload_url,
        content=test_file_content,
        headers={"Content-Type": "application/pdf"}
    )
    s3_uploaded = s3_resp.status_code in (200, 204)
    
    # Step 3: Confirm upload completion
    confirm_resp = await http_client.post(
        f"{config.api_url}/api/v1/purl/documents/{document_id}/confirm-upload",
        headers={"Authorization": f"Bearer {config.borrower_write_token}"}
    )
    
    # Step 4: Verify CRM record updated
    await asyncio.sleep(5)  # Brief wait for async processing
    
    crm_doc = await http_client.get(
        f"{config.api_url}/api/v1/perennia-docs/documents/{document_id}",
        headers={"Authorization": f"Bearer {config.admin_jwt}"}
    )
    
    doc_data = crm_doc.json()
    crm_updated = (
        doc_data.get("status") == "uploaded"
        and doc_data.get("s3_key") is not None
        and doc_data.get("uploaded_at") is not None
    )
    
    # Cleanup
    await cleanup_test_document(config, document_id)
    
    return {
        "passed": s3_uploaded and crm_updated,
        "presigned_url_generated": upload_url is not None,
        "s3_upload_success": s3_uploaded,
        "crm_record_updated": crm_updated,
        "document_status": doc_data.get("status"),
    }
```

---

## DOC-003: Document Status Transitions Propagate

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
The full document lifecycle status chain propagates correctly across systems:

`requested → uploaded → under_review → reviewed → approved` (or `rejected → re_requested`)

```python
async def check_doc_003(config):
    # Use existing test document
    doc_id = config.test_document_id
    
    transitions = [
        ("uploaded", "under_review"),
        ("under_review", "reviewed"),
        ("reviewed", "approved"),
    ]
    
    results = []
    for from_status, to_status in transitions:
        # Update status via CRM admin
        resp = await http_client.patch(
            f"{config.api_url}/api/v1/perennia-docs/documents/{doc_id}/status",
            headers={"Authorization": f"Bearer {config.admin_jwt}"},
            json={"status": to_status}
        )
        
        await asyncio.sleep(3)
        
        # Check borrower portal reflects the change
        portal_doc = await http_client.get(
            f"{config.api_url}/api/v1/purl/documents/{doc_id}",
            headers={"Authorization": f"Bearer {config.borrower_token}"}
        )
        
        portal_status = portal_doc.json().get("status")
        results.append({
            "transition": f"{from_status} → {to_status}",
            "crm_update_status": resp.status_code,
            "portal_status": portal_status,
            "passed": portal_status == to_status,
        })
    
    return {
        "passed": all(r["passed"] for r in results),
        "transitions_tested": len(results),
        "transitions_passed": sum(1 for r in results if r["passed"]),
        "details": results,
    }
```

---

## DOC-004: Presigned URL Generation and Expiry

**Severity:** HIGH  
**Applies to:** Borrower

**What it checks:**  
S3 presigned URLs are generated correctly for uploads and downloads, and they expire after the configured TTL.

```python
async def check_doc_004(config):
    # Generate download URL for existing doc
    download_resp = await http_client.get(
        f"{config.api_url}/api/v1/purl/documents/{config.test_document_id}/download-url",
        headers={"Authorization": f"Bearer {config.borrower_token}"}
    )
    
    download_url = download_resp.json().get("url")
    
    # Verify URL works now
    s3_resp = await http_client.get(download_url)
    url_works = s3_resp.status_code == 200
    
    # Check URL has expiry params
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(download_url)
    params = parse_qs(parsed.query)
    has_expiry = "X-Amz-Expires" in params or "Expires" in params
    
    # Extract TTL
    ttl = int(params.get("X-Amz-Expires", [0])[0])
    ttl_acceptable = 60 <= ttl <= 3600  # Between 1 min and 1 hour
    
    return {
        "passed": url_works and has_expiry and ttl_acceptable,
        "url_works": url_works,
        "has_expiry_param": has_expiry,
        "ttl_seconds": ttl,
        "ttl_acceptable": ttl_acceptable,
    }
```

---

## DOC-005: File Type Validation

**Severity:** HIGH  
**Applies to:** All portals

**What it checks:**  
Attempting to upload a disallowed file type (e.g., `.exe`, `.sh`, `.bat`) is rejected.

```python
async def check_doc_005(config):
    disallowed_types = [
        ("malware.exe", "application/x-msdownload"),
        ("script.sh", "application/x-sh"),
        ("payload.bat", "application/x-msdos-program"),
        ("hack.php", "application/x-httpd-php"),
    ]
    
    results = []
    for filename, content_type in disallowed_types:
        resp = await http_client.post(
            f"{config.api_url}/api/v1/purl/documents/upload-url",
            headers={"Authorization": f"Bearer {config.borrower_write_token}"},
            json={
                "workspace_id": config.test_workspace_id,
                "filename": filename,
                "content_type": content_type,
                "file_size": 1024,
            }
        )
        results.append({
            "filename": filename,
            "content_type": content_type,
            "status": resp.status_code,
            "passed": resp.status_code in (400, 422),  # Should reject
        })
    
    return {
        "passed": all(r["passed"] for r in results),
        "types_tested": len(results),
        "types_rejected": sum(1 for r in results if r["passed"]),
        "details": results,
    }
```

---

## DOC-006: File Size Limits

**Severity:** MEDIUM  
**Applies to:** All portals

**What it checks:**  
Attempting to upload a file exceeding the org's configured size limit is rejected at the presigned URL generation step.

---

## DOC-007: Template Pack Application

**Severity:** HIGH  
**Applies to:** Borrower

**What it checks:**  
Applying a template pack (e.g., "Purchase Conventional") to a workspace creates the correct set of document requests (ID, income verification, bank statements, etc.).

```python
async def check_doc_007(config):
    # Apply template pack via integration endpoint
    resp = await http_client.post(
        f"{config.api_url}/api/v1/purl-integration/workspaces/{config.test_workspace_id}/initialize-documents",
        headers={"Authorization": f"Bearer {config.admin_jwt}"},
        json={"template_pack": "purchase_conventional"}
    )
    
    # Get document list
    docs = await http_client.get(
        f"{config.api_url}/api/v1/purl-integration/workspaces/{config.test_workspace_id}/document-status",
        headers={"Authorization": f"Bearer {config.admin_jwt}"}
    )
    
    doc_list = docs.json().get("documents", [])
    expected_types = {"government_id", "pay_stubs", "w2", "bank_statements", "tax_returns"}
    actual_types = {d["document_type"] for d in doc_list}
    
    missing = expected_types - actual_types
    
    return {
        "passed": len(missing) == 0,
        "template_applied": resp.status_code == 200,
        "documents_created": len(doc_list),
        "expected_types": list(expected_types),
        "missing_types": list(missing),
    }
```

---

## DOC-008: Document Download Authorization

**Severity:** CRITICAL  
**Applies to:** All portals

**What it checks:**  
Documents can only be downloaded by authorized users. Borrower A cannot download Borrower B's documents. Unauthenticated requests are rejected.

```python
async def check_doc_008(config):
    # Borrower A's document
    doc_id = config.borrower_a_document_id
    
    # Test 1: Authorized user can download
    resp_ok = await http_client.get(
        f"{config.api_url}/api/v1/purl/documents/{doc_id}/download-url",
        headers={"Authorization": f"Bearer {config.borrower_a_token}"}
    )
    
    # Test 2: Different borrower cannot download
    resp_cross = await http_client.get(
        f"{config.api_url}/api/v1/purl/documents/{doc_id}/download-url",
        headers={"Authorization": f"Bearer {config.borrower_b_token}"}
    )
    
    # Test 3: No auth rejected
    resp_noauth = await http_client.get(
        f"{config.api_url}/api/v1/purl/documents/{doc_id}/download-url"
    )
    
    return {
        "passed": (
            resp_ok.status_code == 200
            and resp_cross.status_code in (403, 404)
            and resp_noauth.status_code == 401
        ),
        "authorized_access": resp_ok.status_code,
        "cross_user_access": resp_cross.status_code,
        "unauthenticated_access": resp_noauth.status_code,
    }
```

---

## DOC-009 through DOC-012

**DOC-009: Perennia Docs ↔ PURL Activity Feed** — Verify the unified activity feed (`/api/v1/purl-integration/workspaces/{id}/activity-feed`) includes events from both Perennia Docs and PURL systems.

**DOC-010: Document Version History** — Upload a document twice to the same request. Verify both versions are tracked with correct timestamps and the latest version is returned by default.

**DOC-011: Bulk Document Operations** — Upload 5 documents simultaneously. Verify all 5 are stored correctly with no data corruption or lost uploads.

**DOC-012: Document Notifications** — When a document status changes, verify a notification is created in `purl-integration/workspaces/{id}/notifications` and (if configured) email/SMS is dispatched.
