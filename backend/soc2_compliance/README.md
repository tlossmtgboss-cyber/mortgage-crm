# SOC 2 Type II Compliance Module — Perennia AI

## Overview

This module implements the technical controls required for SOC 2 Type II certification across all five Trust Services Criteria:

- **Security** (CC) — Access controls, encryption, intrusion detection
- **Availability** (A) — Uptime monitoring, incident response, disaster recovery
- **Processing Integrity** (PI) — Data validation, error handling, audit trails
- **Confidentiality** (C) — Data classification, encryption at rest/in transit, access restrictions
- **Privacy** (P) — PII handling, consent management, data retention/disposal

## Architecture

```
soc2-compliance/
├── models/                    # SQLAlchemy models for audit/compliance tables
│   ├── __init__.py
│   ├── audit_log.py           # Core audit trail model
│   ├── access_event.py        # Authentication & authorization events
│   ├── security_incident.py   # Security incident tracking
│   ├── change_record.py       # Change management records
│   ├── data_classification.py # Data classification & PII tagging
│   └── compliance_check.py    # Automated compliance check results
├── services/
│   ├── __init__.py
│   ├── audit_service.py       # Audit logging service
│   ├── encryption_service.py  # Field-level encryption for PII
│   ├── access_control_service.py  # RBAC audit & enforcement
│   ├── incident_service.py    # Incident response workflow
│   ├── retention_service.py   # Data retention & disposal
│   └── compliance_reporter.py # SOC 2 report generation
├── middleware/
│   ├── __init__.py
│   ├── audit_middleware.py    # Auto-capture all API requests
│   ├── rate_limit_middleware.py # Rate limiting & abuse detection
│   └── security_headers.py   # Security header enforcement
├── api/
│   ├── __init__.py
│   ├── router.py              # Main compliance API router
│   ├── audit_endpoints.py     # Audit log query endpoints
│   ├── incident_endpoints.py  # Incident management endpoints
│   └── compliance_endpoints.py # Compliance dashboard endpoints
├── migrations/
│   └── soc2_tables.sql        # PostgreSQL migration script
├── scripts/
│   ├── compliance_scan.py     # Run automated compliance checks
│   └── generate_report.py     # Generate SOC 2 evidence report
├── tests/
│   └── test_audit_service.py  # Test suite
├── config.py                  # SOC 2 configuration
├── constants.py               # Enums and constants
└── README.md                  # This file
```

## Installation

### 1. Database Migration

Run the SQL migration to create all compliance tables:

```bash
psql $DATABASE_URL -f migrations/soc2_tables.sql
```

### 2. Install Dependencies

Add these to your `requirements.txt` (if not already present):

```
cryptography>=41.0.0
python-json-logger>=2.0.0
```

### 3. Environment Variables

Add to your `.env`:

```env
# SOC 2 Compliance Config
SOC2_FIELD_ENCRYPTION_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
SOC2_AUDIT_RETENTION_DAYS=730
SOC2_SESSION_TIMEOUT_MINUTES=30
SOC2_MAX_LOGIN_ATTEMPTS=5
SOC2_LOCKOUT_DURATION_MINUTES=30
SOC2_REQUIRE_MFA=true
SOC2_PII_FIELDS=ssn,tax_id,bank_account,routing_number,dob,income
```

### 4. Integration Points

#### A. Register Middleware (main.py)

```python
from soc2_compliance.middleware.audit_middleware import AuditMiddleware
from soc2_compliance.middleware.security_headers import SecurityHeadersMiddleware
from soc2_compliance.middleware.rate_limit_middleware import RateLimitMiddleware

app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
```

#### B. Register API Routes (main.py)

```python
from soc2_compliance.api.router import soc2_router

app.include_router(soc2_router, prefix="/api/v1/compliance", tags=["SOC 2 Compliance"])
```

#### C. Hook Into Auth System

In your existing login endpoint:

```python
from soc2_compliance.services.access_control_service import AccessControlService

access_service = AccessControlService(db)

# On successful login
await access_service.log_authentication(user_id=user.id, success=True, ip=request.client.host, user_agent=request.headers.get("user-agent"))

# On failed login
await access_service.log_authentication(user_id=None, success=False, ip=request.client.host, user_agent=request.headers.get("user-agent"), failure_reason="invalid_credentials", attempted_email=email)
```

#### D. Hook Into Data Access

For any endpoint that reads/writes PII or sensitive loan data:

```python
from soc2_compliance.services.audit_service import AuditService

audit = AuditService(db)
await audit.log_data_access(
    user_id=current_user.id,
    resource_type="loan_application",
    resource_id=loan_id,
    action="read",
    fields_accessed=["ssn", "income", "credit_score"]
)
```

#### E. Encrypt PII at Rest

```python
from soc2_compliance.services.encryption_service import EncryptionService

enc = EncryptionService()

# Before storing
encrypted_ssn = enc.encrypt(borrower.ssn)

# When retrieving
decrypted_ssn = enc.decrypt(encrypted_ssn)
```

### 5. Scheduled Jobs

Add these to your task scheduler (Railway cron or Celery):

```python
# Daily — retention policy enforcement
from soc2_compliance.services.retention_service import RetentionService
await RetentionService(db).enforce_retention_policies()

# Daily — automated compliance checks
from soc2_compliance.scripts.compliance_scan import run_compliance_scan
await run_compliance_scan(db)

# Weekly — generate compliance evidence report
from soc2_compliance.scripts.generate_report import generate_weekly_report
await generate_weekly_report(db)
```

## SOC 2 Trust Services Criteria Mapping

| Control Area | Implementation | Files |
|---|---|---|
| CC1 — Control Environment | Org policies, RBAC enforcement | `access_control_service.py` |
| CC2 — Communication | Audit trails, incident notifications | `audit_service.py`, `incident_service.py` |
| CC3 — Risk Assessment | Automated compliance scanning | `compliance_scan.py` |
| CC4 — Monitoring | Request logging, anomaly detection | `audit_middleware.py` |
| CC5 — Control Activities | Encryption, session mgmt, rate limiting | `encryption_service.py`, `rate_limit_middleware.py` |
| CC6 — Access Controls | Auth logging, MFA, lockout policies | `access_control_service.py` |
| CC7 — System Operations | Change management, incident response | `change_record.py`, `incident_service.py` |
| CC8 — Change Management | Tracked deployments, approval workflows | `change_record.py` |
| CC9 — Risk Mitigation | Vendor tracking, data classification | `data_classification.py` |
| A1 — Availability | Uptime checks, disaster recovery | `compliance_scan.py` |
| PI1 — Processing Integrity | Data validation, error tracking | `audit_service.py` |
| C1 — Confidentiality | Field-level encryption, access restrictions | `encryption_service.py` |
| P1-P8 — Privacy | PII tracking, retention, consent | `retention_service.py`, `data_classification.py` |

## Auditor Evidence

When the SOC 2 auditor requests evidence, use:

```bash
python scripts/generate_report.py --start 2025-01-01 --end 2025-12-31
```

This generates a comprehensive PDF report with:
- Access control logs
- Change management records
- Incident response timeline
- Encryption verification
- Data retention compliance
- Automated control test results
