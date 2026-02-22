# Security & Compliance Remediation

## Table of Contents
1. [SOC 2 Type I Preparation](#soc2)
2. [Data Integrity & Audit Trails](#data-integrity)
3. [Dependency Security](#dependency-security)

---

<a name="soc2"></a>
## 1. SOC 2 Type I Preparation

### Why This Matters
Every major competitor (Shape, Total Expert, Jungo) has or is pursuing SOC 2 certification. Enterprise mortgage lenders require it in their vendor assessment. Without it, Perennia can't pass due diligence for any lender with >50 LOs.

### What SOC 2 Type I Requires

SOC 2 Type I evaluates the *design* of controls at a point in time (unlike Type II which evaluates *operating effectiveness* over 6+ months). This is achievable in 3–6 months.

The five Trust Service Criteria:

1. **Security** (required) — Protection against unauthorized access
2. **Availability** — System uptime and performance
3. **Processing Integrity** — Data processing is complete, accurate, timely
4. **Confidentiality** — Data classified as confidential is protected
5. **Privacy** — Personal information is collected/used/retained/disclosed properly

### Perennia's Existing Strengths

The recent remediation gives a head start:
- RLS (Row-Level Security) implemented
- Auth centralization effort completed
- Error handling standardized (434 fixes)
- DNC blocking enforcement
- Float→Numeric conversions (data integrity)

### Gap Analysis & Action Items

#### Security Controls

| Control | Current State | Action Needed |
|---------|--------------|---------------|
| Authentication | JWT-based, recently centralized | Document; add rate limiting on auth endpoints |
| Authorization | RBAC implemented | Document role definitions; audit all endpoints |
| Encryption at rest | PostgreSQL (Railway default) | Verify Railway encryption settings; document |
| Encryption in transit | HTTPS (Railway/Vercel) | Verify TLS 1.2+; document |
| Password policy | Implemented | Document requirements; add complexity rules if missing |
| Session management | JWT expiration | Document token lifetime; add refresh token rotation |
| Audit logging | Partial | Expand to cover all data modifications |
| Vulnerability scanning | None | Add Dependabot/Snyk; schedule quarterly scans |
| Incident response | None documented | Write incident response plan |
| Access reviews | None | Quarterly review of admin access |

#### Availability Controls

| Control | Current State | Action Needed |
|---------|--------------|---------------|
| Uptime monitoring | Railway dashboard | Add external monitoring (UptimeRobot/Pingdom) |
| Backup/recovery | Railway auto-backups | Document RTO/RPO; test recovery procedure |
| Disaster recovery | None documented | Write DR plan; test quarterly |
| Capacity planning | ~20 DB connections | Document connection pool limits; plan scaling triggers |

#### Processing Integrity

| Control | Current State | Action Needed |
|---------|--------------|---------------|
| Data validation | Pydantic schemas | Document validation rules for financial data |
| Error handling | Recently standardized | Document error codes; monitoring dashboards |
| Data reconciliation | Loan state reconciliation exists | Document reconciliation processes |
| Change management | Git-based | Document deployment process; add PR review requirement |

### Documentation to Produce

1. **Information Security Policy** — Overall security philosophy and controls
2. **Access Control Policy** — How users/admins get access, role definitions
3. **Data Classification Policy** — What's confidential, what's public
4. **Incident Response Plan** — Steps when a security event occurs
5. **Change Management Policy** — How code changes get reviewed and deployed
6. **Vendor Management Policy** — How third-party services are evaluated
7. **Business Continuity Plan** — DR/backup procedures
8. **Employee Security Policy** — Onboarding/offboarding, security training

### Timeline

| Month | Milestone |
|-------|-----------|
| Month 1 | Policies drafted, controls documented, gap analysis complete |
| Month 2 | Technical controls implemented (monitoring, scanning, audit logging) |
| Month 3 | Internal audit of controls, documentation review |
| Month 4 | Engage SOC 2 auditor, pre-assessment |
| Month 5-6 | Formal Type I audit |

---

<a name="data-integrity"></a>
## 2. Data Integrity & Audit Trails

### The Risk

The Salesforce sync service creates leads AND loans, handling field mappings, stage transitions, and bi-directional updates. A field mapping bug could corrupt a loan amount ($350,000 → $35,000). The customer's money is at stake. Same risk applies to the Encompass integration.

### Comprehensive Audit Trail

Every data modification to financial records must be tracked:

```python
# app/models/audit.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Null for system actions
    entity_type = Column(String(50), nullable=False)  # "loan", "lead", "contact"
    entity_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)  # "create", "update", "delete"
    changes = Column(JSON, nullable=False)  # {"field": {"old": X, "new": Y}}
    source = Column(String(50), nullable=False)  # "ui", "api", "salesforce_sync", "encompass_sync"
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### Middleware for Automatic Auditing

```python
# app/middleware/audit.py
from sqlalchemy import event
from app.models.audit import AuditLog

AUDITED_MODELS = ["Loan", "Lead", "Contact", "User"]
FINANCIAL_FIELDS = ["loan_amount", "interest_rate", "monthly_payment", "closing_costs"]

@event.listens_for(Session, "before_flush")
def audit_changes(session, flush_context, instances):
    for obj in session.dirty:
        if obj.__class__.__name__ in AUDITED_MODELS:
            changes = {}
            insp = inspect(obj)
            for attr in insp.attrs:
                hist = attr.history
                if hist.has_changes():
                    old_val = hist.deleted[0] if hist.deleted else None
                    new_val = hist.added[0] if hist.added else None
                    changes[attr.key] = {
                        "old": str(old_val),
                        "new": str(new_val)
                    }

                    # Extra validation for financial fields
                    if attr.key in FINANCIAL_FIELDS:
                        _validate_financial_change(obj, attr.key, old_val, new_val)

            if changes:
                audit = AuditLog(
                    tenant_id=obj.tenant_id,
                    entity_type=obj.__class__.__name__.lower(),
                    entity_id=obj.id,
                    action="update",
                    changes=changes,
                    source=_get_current_source()
                )
                session.add(audit)

def _validate_financial_change(obj, field, old_val, new_val):
    """Flag suspicious financial data changes."""
    if old_val and new_val:
        try:
            old_num = float(old_val)
            new_num = float(new_val)
            # Flag if value changed by more than 10x (likely a decimal error)
            if old_num > 0 and (new_num / old_num > 10 or new_num / old_num < 0.1):
                logger.critical(
                    f"SUSPICIOUS FINANCIAL CHANGE: {field} on {obj.__class__.__name__} "
                    f"#{obj.id}: {old_val} → {new_val} (ratio: {new_num/old_num:.2f})"
                )
        except (ValueError, ZeroDivisionError):
            pass
```

### Rollback Mechanism

```python
# app/services/audit_service.py
async def rollback_entity(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    to_audit_id: int,
    tenant_id: int
) -> dict:
    """Rollback an entity to its state at a specific audit log entry.

    Applies all field changes in reverse from newest to target audit entry.
    Creates a new audit log entry documenting the rollback.
    """
    # Get all audit entries newer than target
    entries = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
            AuditLog.tenant_id == tenant_id,
            AuditLog.id > to_audit_id
        )
        .order_by(AuditLog.id.desc())
    )

    # Apply changes in reverse
    model_class = get_model_class(entity_type)
    entity = await db.get(model_class, entity_id)

    rollback_changes = {}
    for entry in entries.scalars():
        for field, change in entry.changes.items():
            if "old" in change:
                setattr(entity, field, change["old"])
                rollback_changes[field] = {
                    "old": change.get("new"),
                    "new": change["old"],
                    "rolled_back_from_audit": entry.id
                }

    # Log the rollback itself
    rollback_audit = AuditLog(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action="rollback",
        changes=rollback_changes,
        source="admin_rollback"
    )
    db.add(rollback_audit)
    await db.commit()

    return rollback_changes
```

---

<a name="dependency-security"></a>
## 3. Dependency Security

### Current State
- 112 Python dependencies
- requirements.lock is 3 days old
- No automated vulnerability scanning
- No CI/CD pipeline to detect breaking changes

### Immediate Actions

#### Step 1: Enable Dependabot

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "security"

  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "security"
```

#### Step 2: Add Safety Check to CI

```yaml
# In .github/workflows/ci.yml
security-scan:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install safety
    - run: safety check -r requirements.txt --output json > safety-report.json
    - run: |
        # Fail on critical/high vulnerabilities
        python -c "
        import json
        report = json.load(open('safety-report.json'))
        criticals = [v for v in report.get('vulnerabilities', []) if v.get('severity', '') in ('critical', 'high')]
        if criticals:
            for v in criticals:
                print(f'CRITICAL: {v[\"package_name\"]}=={v[\"analyzed_version\"]}: {v[\"vulnerability_id\"]}')
            exit(1)
        print('No critical vulnerabilities found')
        "
```

#### Step 3: Pin Dependencies with Hash Verification

```bash
# Generate locked requirements with hashes
pip install pip-tools
pip-compile --generate-hashes requirements.in -o requirements.txt
```

This ensures:
- Exact versions are pinned (no surprise upgrades)
- Package integrity is verified via hashes
- Supply chain attacks are detectable

## Validation Checklist

### SOC 2
- [ ] All 8 policy documents drafted
- [ ] External uptime monitoring configured
- [ ] Backup recovery procedure tested
- [ ] Incident response plan documented and tested
- [ ] Dependabot/vulnerability scanning enabled
- [ ] Quarterly access review process defined

### Data Integrity
- [ ] AuditLog model created and migrated
- [ ] All Loan/Lead/Contact modifications logged
- [ ] Financial field change validation active
- [ ] Rollback mechanism tested
- [ ] Salesforce sync audit trail verified
- [ ] Suspicious change alerting configured

### Dependency Security
- [ ] Dependabot enabled for Python and npm
- [ ] Safety check in CI pipeline
- [ ] Requirements pinned with hashes
- [ ] No known critical vulnerabilities in dependencies
