# PURL (Personalized URL) System Documentation

## Overview

The PURL system provides secure, personalized application portals for mortgage borrowers. Each PURL is a unique, tokenized URL that allows borrowers to:
- Complete loan applications
- Upload required documents
- Track application progress
- Communicate with their loan officer

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PURL System                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Frontend    │    │   Backend    │    │   Database   │       │
│  │  React App   │◄──►│   FastAPI    │◄──►│  PostgreSQL  │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                    │               │
│         │                   │                    │               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ PURLPortal   │    │ PURL Routes  │    │ purl_tokens  │       │
│  │ PURLApp      │    │ PURL Services│    │ purl_sessions│       │
│  └──────────────┘    └──────────────┘    │ purl_events  │       │
│                                          └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Backend Services

| Service | File | Description |
|---------|------|-------------|
| Token Service | `services/purl_token_service.py` | Generates and validates PURL tokens |
| Workspace Service | `services/purl_workspace_service.py` | Manages borrower workspace data |
| Application Service | `services/purl_application_service.py` | Handles application submissions |
| Document Service | `services/purl_document_service.py` | Document upload and management |
| Timeline Service | `services/purl_timeline_service.py` | Activity tracking and timeline |
| Email Service | `services/purl_email_service.py` | Borrower email notifications |
| Cache Service | `services/purl_cache_service.py` | Redis caching for performance |

### Backend Routes

| Route | File | Description |
|-------|------|-------------|
| PURL API | `routes/purl_routes.py` | All PURL-related endpoints |

### Backend Models

| Model | File | Description |
|-------|------|-------------|
| PURL Models | `models/purl.py` | Database models for PURL system |

### Backend Middleware

| Middleware | File | Description |
|------------|------|-------------|
| PURL Auth | `middleware/purl_auth.py` | Token validation middleware |

### Backend Jobs

| Job | File | Description |
|-----|------|-------------|
| Event Processor | `jobs/purl_event_processor.py` | Background event processing |

### Frontend Pages

| Page | File | Description |
|------|------|-------------|
| PURL Portal | `pages/PURLPortal.js` | Main borrower portal |
| PURL Application | `pages/PURLApplication.js` | Application form |

### Admin Components

| Component | File | Description |
|-----------|------|-------------|
| PURL Manager | `components/admin/PURLManager.js` | Admin PURL management |

## API Endpoints

### Token Management

```
POST   /api/purl/generate          # Generate new PURL token
GET    /api/purl/validate/{token}  # Validate PURL token
POST   /api/purl/refresh/{token}   # Refresh expiring token
DELETE /api/purl/revoke/{token}    # Revoke PURL token
```

### Borrower Portal

```
GET    /api/purl/portal/{token}              # Get portal data
GET    /api/purl/portal/{token}/workspace    # Get workspace
POST   /api/purl/portal/{token}/application  # Submit application
GET    /api/purl/portal/{token}/timeline     # Get activity timeline
```

### Document Management

```
GET    /api/purl/portal/{token}/documents           # List documents
POST   /api/purl/portal/{token}/documents           # Upload document
GET    /api/purl/portal/{token}/documents/{doc_id}  # Get document
DELETE /api/purl/portal/{token}/documents/{doc_id}  # Delete document
```

### Admin Endpoints

```
GET    /api/purl/admin/tokens                # List all tokens
GET    /api/purl/admin/tokens/{token}        # Get token details
PUT    /api/purl/admin/tokens/{token}        # Update token settings
GET    /api/purl/admin/analytics             # PURL analytics
```

## Database Schema

### purl_tokens

```sql
CREATE TABLE purl_tokens (
    id UUID PRIMARY KEY,
    token VARCHAR(64) UNIQUE NOT NULL,
    lead_id UUID REFERENCES leads(id),
    loan_id UUID REFERENCES loans(id),
    loan_officer_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB
);
```

### purl_sessions

```sql
CREATE TABLE purl_sessions (
    id UUID PRIMARY KEY,
    token_id UUID REFERENCES purl_tokens(id),
    session_token VARCHAR(128) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    last_activity_at TIMESTAMP,
    ended_at TIMESTAMP
);
```

### purl_events

```sql
CREATE TABLE purl_events (
    id UUID PRIMARY KEY,
    token_id UUID REFERENCES purl_tokens(id),
    session_id UUID REFERENCES purl_sessions(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Token Security

### Token Generation

- Tokens are 64-character cryptographically secure random strings
- Generated using `secrets.token_urlsafe(48)`
- Tokens are stored hashed in the database for security

### Token Validation

1. Token format validation
2. Database lookup (using hashed value)
3. Expiration check
4. Active status check
5. Rate limiting verification

### Token Expiration

- Default expiration: 30 days
- Configurable per-token
- Auto-refresh available for active sessions
- Grace period for expired tokens (optional)

## Environment Variables

```bash
# PURL Configuration
PURL_TOKEN_EXPIRY_DAYS=30
PURL_BASE_URL=https://yourapp.com/portal
PURL_RATE_LIMIT_PER_MINUTE=60
PURL_SESSION_TIMEOUT_MINUTES=30

# Email Notifications
PURL_EMAIL_ENABLED=true
PURL_EMAIL_FROM=noreply@yourcompany.com

# Security
PURL_REQUIRE_EMAIL_VERIFICATION=true
PURL_MAX_FAILED_ATTEMPTS=5
PURL_LOCKOUT_DURATION_MINUTES=15
```

## Usage Examples

### Generating a PURL

```python
from services.purl_token_service import PURLTokenService

# Generate PURL for a lead
token_service = PURLTokenService(db)
purl = await token_service.generate_token(
    lead_id=lead.id,
    loan_officer_id=current_user.id,
    expiry_days=30,
    metadata={"campaign": "spring_promo"}
)

# Full URL
portal_url = f"https://yourapp.com/portal/{purl.token}"
```

### Validating a PURL

```python
from middleware.purl_auth import validate_purl_token

# In route handler
@router.get("/portal/{token}")
async def get_portal(
    token: str,
    purl_data: dict = Depends(validate_purl_token)
):
    # purl_data contains validated token info
    return await workspace_service.get_workspace(purl_data)
```

### Sending PURL Email

```python
from services.purl_email_service import PURLEmailService

email_service = PURLEmailService(db)
await email_service.send_portal_invitation(
    token_id=purl.id,
    template="welcome",
    custom_message="Start your application today!"
)
```

## Monitoring

### Key Metrics

- Token generation rate
- Portal access rate
- Document upload success rate
- Application completion rate
- Average session duration

### Logging

```python
from config.purl_logging import purl_logger

purl_logger.info("Token generated", extra={
    "token_id": token.id,
    "lead_id": lead_id,
    "expiry_days": expiry_days
})
```

### Alerts

Configure alerts for:
- High token generation rate (potential abuse)
- Failed validation spikes
- Document upload failures
- Application submission errors

## Troubleshooting

### Common Issues

**Token Not Found**
- Check if token was revoked
- Verify token hasn't expired
- Ensure token format is correct (no URL encoding issues)

**Session Expired**
- Sessions timeout after 30 minutes of inactivity
- Redirect user to re-enter portal

**Document Upload Failed**
- Check file size limits (default 10MB)
- Verify allowed file types
- Check storage permissions

### Debug Mode

Enable debug logging:
```bash
PURL_DEBUG=true
LOG_LEVEL=DEBUG
```

## Migration

Run the PURL migration:
```bash
python backend/migrations/add_purl_system.py
```

This creates:
- `purl_tokens` table
- `purl_sessions` table
- `purl_events` table
- Required indexes
- Foreign key constraints

## Testing

### Unit Tests
```bash
pytest backend/tests/test_purl_*.py -v
```

### Quick Integration Test
```bash
python backend/tests/test_purl_quick.py
```

### Load Testing
```bash
locust -f tests/load/purl_load_test.py
```

## Security Considerations

1. **Token Storage**: Tokens are hashed before storage
2. **Rate Limiting**: Per-IP and per-token rate limits
3. **Session Management**: Secure session tokens with expiration
4. **Input Validation**: All inputs sanitized and validated
5. **Audit Logging**: All access attempts logged
6. **HTTPS Required**: All PURL endpoints require HTTPS in production
