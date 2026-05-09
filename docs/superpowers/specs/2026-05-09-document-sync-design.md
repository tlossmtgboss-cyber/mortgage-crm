# Document Sync: Unified Smart Docs Across All Surfaces

**Date:** 2026-05-09
**Status:** Approved design, pending implementation

## Problem

Three surfaces display documents with no synchronization:

- **Smart Docs page** (LO) — reads/writes `smart_documents` + `smart_document_requests`
- **Client File page** (LO) — reads/writes `smart_documents` + `smart_document_requests` (same endpoints)
- **Borrower Portal** (borrower) — reads/writes `perennia_documents` + `perennia_document_requests`

LO document requests never appear in the Borrower Portal. Borrower uploads never appear in Smart Docs or Client File. Two independent systems with no cross-writes.

## Decision

**Smart Docs tables are the single source of truth.** The Borrower Portal routes become a thin adapter layer over `smart_documents` and `smart_document_requests`, using magic-link auth instead of JWT. The `perennia_*` tables stop receiving writes and become dormant.

## Data Flow (After)

```
smart_document_requests  <-->  smart_documents
         ^                          ^
    +----+-----+              +-----+------+
    |          |              |            |
Smart Docs  Client File   Portal Upload  Portal List
(LO create  (LO create    (borrower      (borrower
 request)    request)      uploads)       sees status)
```

1. LO creates request -> `smart_document_requests` row (status: OPEN)
2. Borrower sees request in portal checklist -> same row, filtered to borrower-visible fields
3. Borrower uploads document -> `smart_documents` row linked via `request_id`, runs full Smart Docs pipeline (screenshot detection, AI extraction, freshness validation)
4. LO reviews in Smart Docs or Client File -> approves/rejects `smart_documents` row, updates linked request
5. Borrower sees updated status in portal

## Status Mapping

### Request Status (Smart Docs -> Portal Display)

| Smart Docs Status | Portal Shows |
|---|---|
| OPEN | Pending |
| PENDING_REVIEW | Under Review |
| ACCEPTED | Complete |
| REJECTED | Needs Reupload |
| WAIVED | Waived (hidden/dimmed) |

### Document Status (Smart Docs -> Portal Display)

| Smart Docs Status | Portal Shows |
|---|---|
| UPLOADED, SCANNING, PROCESSING | Processing |
| PENDING_REVIEW, NEEDS_REVIEW | Under Review |
| APPROVED | Accepted |
| REJECTED | Rejected (with fix_instructions) |
| EXPIRED | Expired |

## Backend Changes

### 1. portal_document_routes.py — Rewrite core endpoints

Switch all queries from `perennia_documents` to `smart_documents`:

- **POST /upload/initiate** — Create `SmartDocument` row (status: UPLOADED), generate presigned S3 URL using Smart Docs storage key pattern, set `upload_source='PORTAL'`
- **POST /upload/confirm** — Trigger Smart Docs processing pipeline (screenshot detection -> AI extraction -> freshness validation)
- **GET /workspace/{workspace_id}** — Query `smart_documents` + `smart_document_requests`, filter to borrower-safe fields (hide review notes, LO comments)
- **POST /{document_id}/review** — Redirect to Smart Docs approval logic (set decision, status, update linked request)
- **GET /{document_id}/preview** and **GET /{document_id}/download** — Use Smart Docs `storage_key` for presigned URLs

### 2. perennia_docs_routes.py — Rewrite checklist endpoint

- **GET /portal/checklist** — Query `smart_document_requests` instead of `perennia_document_requests`. Apply status mapping above.

### 3. smart_docs_crud_routes.py — Track upload source

- **POST /upload** — Already works. Ensure `upload_source` field distinguishes PORTAL uploads from LO uploads (WEB, MOBILE, EMAIL already exist).

### 4. portal_document_service.py — Rewrite to use Smart Docs models

All methods switch from `perennia_documents`/`perennia_document_requests` to `smart_documents`/`smart_document_requests`:

- `upload_document()` — Create SmartDocument
- `get_document()` — Query SmartDocument
- `get_loan_documents()` — Query SmartDocument by loan_id
- `update_document_status()` — Update SmartDocument status
- `get_document_checklist()` — Query smart_document_requests with approved/pending counts
- `get_document_summary()` — Aggregate smart_document_requests completion stats

### 5. Smart Docs / Client File routes — No changes

Already query `smart_documents` / `smart_document_requests`. Portal writes land in the same tables and appear automatically.

## Frontend Changes

### portalApi.js — Minimal response shape adjustments

API paths stay the same (`/api/v1/portal/documents/*`). Backend returns Smart Docs field names. Adjustments:

- `classification_status` -> `detected_doc_type` (or keep mapping in backend response)
- `virus_scan_status` field removed (not in Smart Docs model)
- `compression_ratio` field removed
- `rejection_reason` stays (exists in both models)
- `fix_instructions` added (Smart Docs feature, now visible to borrower)

### BorrowerPortal.jsx — DocumentsSection

- `documentSummary` response shape stays the same — backend computes from `smart_document_requests`
- Checklist endpoint returns same shape, just sourced from different table

### No changes to SmartDocs.js, DocumentsPane.tsx, or Client File components

## What Happens to perennia_* Tables

Tables remain in the database but stop receiving new writes:

- `perennia_documents` — dormant
- `perennia_document_requests` — dormant
- `perennia_document_events` — dormant
- `perennia_notifications` — dormant
- `perennia_template_packs` — can later be adapted to generate `smart_document_requests`
- `perennia_portal_sessions` — still active (magic link auth, independent of document storage)

No migration or deletion needed. Historical data remains queryable.

## Files Affected

### Backend (modify)
- `backend/routes/portal_document_routes.py` — rewrite upload, list, review endpoints
- `backend/routes/perennia_docs_routes.py` — rewrite portal/checklist endpoint
- `backend/services/portal_document_service.py` — rewrite all methods to Smart Docs models
- `backend/routes/smart_docs_crud_routes.py` — ensure upload_source='PORTAL' support

### Frontend (modify)
- `frontend/src/services/portalApi.js` — adjust response field mappings if needed
- `frontend/src/pages/BorrowerPortal.jsx` — adjust field names if response shape changes

### No new files needed
The adapter logic lives in existing portal route/service files.

## Out of Scope

- Virus scanning (not in Smart Docs pipeline currently — can be added later)
- Document compression (optimization, not blocking)
- Template packs generating requests (future enhancement)
- Migrating historical perennia_documents data into smart_documents
