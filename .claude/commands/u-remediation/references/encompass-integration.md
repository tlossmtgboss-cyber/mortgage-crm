# Encompass LOS Integration

## Why This Is the #1 Priority

Over 60% of US mortgage lenders use Encompass (by ICE Mortgage Technology) as their LOS. The CRM-to-LOS data bridge is the single most important integration in mortgage tech. Without it, Perennia is limited to lenders who use Salesforce as their system of record — a much smaller market. Shape's #1 selling point is "native Encompass sync." Total Expert has 40+ LOS integrations.

## Integration Strategy

Start with **read-only sync** (import loan data from Encompass into Perennia). This:
- Proves the integration works without risking writes to the LOS
- Delivers immediate value (LOs see loan status in CRM without switching apps)
- Reduces enterprise buyer objections
- Enables Phase 2 (bi-directional sync) with proven infrastructure

## Phase 1: Read-Only Sync (Weeks 1–4)

### Step 1: Register with ICE Developer Connect

1. Go to https://developer.icemortgagetechnology.com
2. Create a developer account
3. Register an application to get OAuth2 credentials
4. Request access to the following APIs:
   - **Loan Pipeline API** — Get list of loans with status/stage
   - **Loan Data API** — Get detailed loan fields
   - **Borrower Contacts API** — Sync contact info
   - **Webhook Subscriptions API** — Real-time loan updates

### Step 2: OAuth2 Authentication

Encompass uses OAuth2 client credentials + user delegation:

```python
# app/integrations/encompass/auth.py
import httpx
from app.core.config import settings

ENCOMPASS_TOKEN_URL = "https://api.elliemae.com/oauth2/v1/token"

async def get_encompass_token(instance_id: str, client_id: str, client_secret: str) -> str:
    """Get OAuth2 access token for Encompass API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ENCOMPASS_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "lp",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        return response.json()["access_token"]
```

### Step 3: Loan Pipeline Sync

```python
# app/integrations/encompass/pipeline.py
from typing import List, Optional
import httpx

ENCOMPASS_API_BASE = "https://api.elliemae.com/encompass/v3"

async def fetch_loan_pipeline(
    token: str,
    instance_id: str,
    filter_terms: Optional[dict] = None,
    limit: int = 200
) -> List[dict]:
    """Fetch loan pipeline from Encompass."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Pipeline query — filter by date range, LO, or status
    payload = {
        "filter": filter_terms or {
            "operator": "and",
            "terms": [
                {
                    "canonicalName": "Fields.Log.MS.LastModified",
                    "matchType": "greaterThanOrEquals",
                    "value": "2026-01-01"
                }
            ]
        },
        "fields": [
            "Loan.LoanNumber",
            "Loan.BorrowerFirstName",
            "Loan.BorrowerLastName",
            "Loan.LoanAmount",
            "Loan.CurrentMilestone",
            "Loan.LoanOfficerName",
            "Loan.ClosingDate",
            "Loan.RateLock.LockDate",
            "Loan.RateLock.LockExpirationDate",
            "Loan.InterestRate"
        ],
        "sortOrder": [
            {"canonicalName": "Fields.Log.MS.LastModified", "order": "desc"}
        ]
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ENCOMPASS_API_BASE}/loanPipeline",
            headers=headers,
            json=payload,
            params={"limit": limit}
        )
        resp.raise_for_status()
        return resp.json()
```

### Step 4: Field Mapping

Map Encompass fields to Perennia's loan model. This is the most critical piece — incorrect mapping corrupts loan data.

```python
# app/integrations/encompass/field_mapping.py
from decimal import Decimal
from datetime import datetime
from typing import Any, Optional

ENCOMPASS_TO_PERENNIA = {
    # Encompass Field → (Perennia Field, Transform Function)
    "Loan.LoanNumber": ("encompass_loan_number", str),
    "Loan.BorrowerFirstName": ("borrower_first_name", str),
    "Loan.BorrowerLastName": ("borrower_last_name", str),
    "Loan.LoanAmount": ("loan_amount", lambda v: Decimal(str(v)) if v else None),
    "Loan.CurrentMilestone": ("loan_stage", map_milestone_to_stage),
    "Loan.LoanOfficerName": ("loan_officer_name", str),
    "Loan.ClosingDate": ("estimated_closing_date", parse_encompass_date),
    "Loan.InterestRate": ("interest_rate", lambda v: Decimal(str(v)) if v else None),
}

def map_milestone_to_stage(milestone: str) -> str:
    """Map Encompass milestones to Perennia loan stages."""
    MILESTONE_MAP = {
        "Started": "application",
        "Submitted": "processing",
        "Processing": "processing",
        "Underwriting": "underwriting",
        "Approved": "approved",
        "Clear to Close": "clear_to_close",
        "Closing": "closing",
        "Funded": "funded",
        "Purchased": "purchased",
    }
    return MILESTONE_MAP.get(milestone, "unknown")

def parse_encompass_date(value: Any) -> Optional[datetime]:
    """Parse Encompass date format to Python datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

def transform_loan_data(encompass_data: dict) -> dict:
    """Transform Encompass loan data to Perennia format.

    CRITICAL: Every transformation must preserve data integrity.
    Loan amounts especially must use Decimal, never float.
    """
    result = {}
    for enc_field, (per_field, transform) in ENCOMPASS_TO_PERENNIA.items():
        raw_value = encompass_data.get(enc_field)
        if raw_value is not None:
            try:
                result[per_field] = transform(raw_value)
            except Exception as e:
                # Log but don't fail — partial sync is better than no sync
                logger.warning(f"Field transform failed: {enc_field}={raw_value}: {e}")
                result[per_field] = None
    return result
```

### Step 5: Sync Service with Audit Trail

```python
# app/integrations/encompass/sync_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.loan import Loan
from app.models.sync_audit import SyncAuditLog

async def sync_loan_from_encompass(
    db: AsyncSession,
    encompass_data: dict,
    tenant_id: int,
    sync_source: str = "encompass_pipeline"
) -> tuple[Loan, bool]:
    """Sync a single loan from Encompass data.

    Returns (loan, created) — the loan object and whether it was newly created.

    CRITICAL: Creates audit trail for every field change.
    """
    transformed = transform_loan_data(encompass_data)
    enc_loan_number = transformed.get("encompass_loan_number")

    if not enc_loan_number:
        raise ValueError("Encompass loan number is required")

    # Find existing loan by Encompass loan number
    existing = await db.execute(
        select(Loan).where(
            Loan.tenant_id == tenant_id,
            Loan.encompass_loan_number == enc_loan_number
        )
    )
    loan = existing.scalar_one_or_none()

    if loan:
        # Update — track changes for audit
        changes = {}
        for field, new_value in transformed.items():
            old_value = getattr(loan, field, None)
            if old_value != new_value and new_value is not None:
                changes[field] = {"old": str(old_value), "new": str(new_value)}
                setattr(loan, field, new_value)

        if changes:
            audit = SyncAuditLog(
                tenant_id=tenant_id,
                entity_type="loan",
                entity_id=loan.id,
                sync_source=sync_source,
                changes=changes,
                encompass_loan_number=enc_loan_number
            )
            db.add(audit)

        return loan, False
    else:
        # Create new loan
        loan = Loan(tenant_id=tenant_id, **transformed)
        db.add(loan)
        await db.flush()

        audit = SyncAuditLog(
            tenant_id=tenant_id,
            entity_type="loan",
            entity_id=loan.id,
            sync_source=sync_source,
            changes={"action": "created", "fields": transformed},
            encompass_loan_number=enc_loan_number
        )
        db.add(audit)

        return loan, True
```

### Step 6: Webhook Listener for Real-Time Updates

```python
# app/integrations/encompass/webhooks.py
from fastapi import APIRouter, Request, HTTPException
import hmac
import hashlib

router = APIRouter(prefix="/api/webhooks/encompass")

@router.post("/loan-update")
async def handle_loan_update(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Encompass webhook for loan updates.

    Encompasses sends webhooks when loan data changes, enabling
    near-real-time sync without polling.
    """
    # Verify webhook signature
    signature = request.headers.get("X-Encompass-Signature")
    body = await request.body()

    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("eventType")
    loan_data = payload.get("loan", {})

    if event_type in ("LoanOpened", "LoanModified", "MilestoneChanged"):
        # Find tenant by Encompass instance ID
        tenant = await get_tenant_by_encompass_instance(
            db, payload.get("instanceId")
        )
        if tenant:
            await sync_loan_from_encompass(db, loan_data, tenant.id, "webhook")
            await db.commit()

    return {"status": "ok"}
```

## Phase 2: Bi-Directional Sync (Weeks 5–8)

Only after Phase 1 is proven stable in production:

1. **Write-back loan status changes** from Perennia to Encompass
2. **Push new contacts** created in Perennia to Encompass
3. **Sync documents** — allow uploading docs through Perennia that land in Encompass
4. **Conflict resolution** — when both systems change the same field, apply last-write-wins with full audit trail

## Database Schema Additions

```sql
-- Add Encompass tracking to loans table
ALTER TABLE loans ADD COLUMN encompass_loan_number VARCHAR(50);
ALTER TABLE loans ADD COLUMN encompass_instance_id VARCHAR(100);
ALTER TABLE loans ADD COLUMN encompass_last_synced TIMESTAMP WITH TIME ZONE;
CREATE INDEX idx_loans_encompass_number ON loans(encompass_loan_number);

-- Sync audit log
CREATE TABLE sync_audit_log (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    sync_source VARCHAR(50) NOT NULL,
    changes JSONB NOT NULL,
    encompass_loan_number VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_sync_audit_tenant ON sync_audit_log(tenant_id, created_at);

-- Encompass connection settings per tenant
CREATE TABLE encompass_connections (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL UNIQUE REFERENCES tenants(id),
    instance_id VARCHAR(100) NOT NULL,
    client_id VARCHAR(200) NOT NULL,
    client_secret_encrypted BYTEA NOT NULL,
    is_active BOOLEAN DEFAULT true,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_frequency_minutes INTEGER DEFAULT 15,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Validation Checklist

- [ ] ICE Developer Connect account registered and API credentials obtained
- [ ] OAuth2 token flow working against Encompass sandbox
- [ ] Pipeline API returns loan list with correct fields
- [ ] Field mapping transforms Encompass data to Perennia format
- [ ] Loan amounts use Decimal (not float) throughout the pipeline
- [ ] Sync audit log records every field change with before/after
- [ ] Webhook endpoint validates signatures and processes loan updates
- [ ] Tenant isolation — each tenant sees only their Encompass instance's data
- [ ] Error handling — sync failures are logged but don't crash the app
