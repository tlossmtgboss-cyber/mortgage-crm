# API Gateway & Developer Experience Guide

**Enterprise Readiness - Domain 11**

This guide covers the comprehensive API gateway features for developers integrating with Perennia AI.

---

## Table of Contents

1. [API Key Management](#api-key-management)
2. [Rate Limiting](#rate-limiting)
3. [Webhook Subscriptions](#webhook-subscriptions)
4. [Webhook Event Catalog](#webhook-event-catalog)
5. [Webhook Delivery & Retry Logic](#webhook-delivery--retry-logic)
6. [Security Best Practices](#security-best-practices)

---

## API Key Management

### Creating an API Key

**Endpoint:** `POST /api/v1/api-keys`

Generate a new API key for programmatic access to the platform.

**Request:**
```json
{
  "name": "Zapier Integration",
  "description": "Automation workflows for lead capture",
  "scopes": ["read:leads", "write:leads", "read:loans"],
  "expires_at": "2027-02-20T00:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 123,
    "api_key": "pk_live_abc123...xyz789",
    "name": "Zapier Integration",
    "scopes": ["read:leads", "write:leads", "read:loans"],
    "expires_at": "2027-02-20T00:00:00Z"
  },
  "message": "API key created successfully. Save this key securely - it will not be shown again."
}
```

**Important:** The full API key is only shown once at creation. Store it securely.

### Available Scopes

| Scope | Description |
|-------|-------------|
| `read:leads` | View lead information |
| `write:leads` | Create and update leads |
| `delete:leads` | Delete leads |
| `read:loans` | View loan information |
| `write:loans` | Create and update loans |
| `delete:loans` | Delete loans |
| `read:contacts` | View contact information |
| `write:contacts` | Create and update contacts |
| `delete:contacts` | Delete contacts |
| `read:documents` | View documents |
| `write:documents` | Upload documents |
| `delete:documents` | Delete documents |
| `read:analytics` | View analytics data |
| `read:reports` | Generate and view reports |
| `webhooks:manage` | Create and manage webhooks |
| `integrations:manage` | Configure integrations |
| `admin:full` | Full administrative access |

### Using an API Key

Include your API key in the `X-API-Key` header:

```bash
curl -X GET https://api.perenniaai.com/api/v1/leads \
  -H "X-API-Key: pk_live_abc123...xyz789"
```

### Listing API Keys

**Endpoint:** `GET /api/v1/api-keys`

Returns all API keys for your organization (keys are masked for security).

### Updating an API Key

**Endpoint:** `PUT /api/v1/api-keys/{key_id}`

Update the name, scopes, or active status of an existing API key.

### Revoking an API Key

**Endpoint:** `DELETE /api/v1/api-keys/{key_id}`

Permanently revoke and delete an API key. This action cannot be undone.

---

## Rate Limiting

### Per-Client Rate Limits

Rate limits are applied based on the client identifier:

| Client Type | Limit | Window |
|-------------|-------|--------|
| **API Key** | 1,000 requests | per minute |
| **Visitor ID** | 120 requests | per minute |
| **IP Address** | 120 requests | per minute |

### Rate Limit Categories

Different endpoint categories have specific limits:

| Category | Limit | Window |
|----------|-------|--------|
| Chat Messages | 60 requests | per minute |
| Session Creation | 10 requests | per hour |
| Call Initiation | 3 requests | per hour |
| Analytics | 100 requests | per minute |

### Rate Limit Headers

All API responses include rate limit information:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1645123456
```

### Rate Limit Exceeded Response

```json
{
  "error": "Rate limit exceeded",
  "retry_after": 45,
  "category": "api_key"
}
```

**HTTP Status:** `429 Too Many Requests`

---

## Webhook Subscriptions

### Creating a Webhook Subscription

**Endpoint:** `POST /api/v1/webhooks/subscriptions`

Subscribe to receive webhook events at a specified URL.

**Request:**
```json
{
  "name": "Zapier Lead Notifications",
  "url": "https://hooks.zapier.com/hooks/catch/123456/abcdef/",
  "events": ["lead.created", "lead.converted", "loan.funded"],
  "headers": {
    "X-Custom-Header": "custom-value"
  },
  "retry_count": 3,
  "timeout_seconds": 30
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 456,
    "name": "Zapier Lead Notifications",
    "url": "https://hooks.zapier.com/hooks/catch/123456/abcdef/",
    "events": ["lead.created", "lead.converted", "loan.funded"],
    "secret": "whsec_xyz789...",
    "retry_config": {
      "max_attempts": 4,
      "timeout_seconds": 30,
      "backoff_schedule": "1s, 5s, 25s, 125s"
    }
  },
  "message": "Webhook subscription created. Save the secret securely for signature verification."
}
```

**Important:** The webhook secret is only shown once. Use it to verify webhook signatures.

### Listing Webhook Subscriptions

**Endpoint:** `GET /api/v1/webhooks/subscriptions`

Returns all webhook subscriptions for your organization.

### Deleting a Webhook Subscription

**Endpoint:** `DELETE /api/v1/webhooks/subscriptions/{subscription_id}`

Remove a webhook subscription.

### Viewing Delivery Logs

**Endpoint:** `GET /api/v1/webhooks/subscriptions/{subscription_id}/logs`

View delivery attempts and status for a webhook subscription.

**Query Parameters:**
- `limit` (default: 50, max: 100) - Number of logs to return
- `status` - Filter by status: `success`, `failed`, `pending`

**Response:**
```json
{
  "success": true,
  "data": {
    "subscription_id": 456,
    "logs": [
      {
        "id": 1001,
        "event_type": "lead.created",
        "status": "success",
        "attempt_number": 1,
        "max_attempts": 4,
        "response_code": 200,
        "response_time_ms": 145,
        "created_at": "2026-02-20T15:30:00Z",
        "delivered_at": "2026-02-20T15:30:01Z"
      },
      {
        "id": 1002,
        "event_type": "loan.funded",
        "status": "failed",
        "attempt_number": 4,
        "max_attempts": 4,
        "response_code": 500,
        "error_message": "HTTP 500: Internal Server Error",
        "created_at": "2026-02-20T14:00:00Z"
      }
    ],
    "total": 2
  }
}
```

---

## Webhook Event Catalog

### Listing Available Events

**Endpoint:** `GET /api/v1/webhooks/events`

Get the complete catalog of available webhook events with schemas and examples.

**Query Parameters:**
- `category` - Filter by category: `leads`, `loans`, `documents`, `tasks`, `applications`

**Response:**
```json
{
  "success": true,
  "data": {
    "categories": {
      "leads": [
        {
          "event_id": "lead.created",
          "name": "Lead Created",
          "description": "Triggered when a new lead is created in the system",
          "payload_schema": {
            "type": "object",
            "properties": {
              "event": {"type": "string", "const": "lead.created"},
              "timestamp": {"type": "string", "format": "date-time"},
              "data": {
                "type": "object",
                "properties": {
                  "id": {"type": "integer"},
                  "name": {"type": "string"},
                  "email": {"type": "string", "format": "email"}
                }
              }
            }
          },
          "example_payload": {
            "event": "lead.created",
            "timestamp": "2026-02-20T15:30:00Z",
            "data": {
              "id": 12345,
              "name": "John Doe",
              "email": "john.doe@example.com"
            }
          }
        }
      ]
    },
    "total_events": 11,
    "available_categories": ["leads", "loans", "documents", "tasks", "applications"]
  }
}
```

### Available Events by Category

#### Leads
- `lead.created` - New lead created
- `lead.updated` - Lead information updated
- `lead.converted` - Lead converted to loan

#### Loans
- `loan.created` - New loan created
- `loan.stage_changed` - Loan moved to different stage
- `loan.funded` - Loan successfully funded

#### Documents
- `document.uploaded` - Document uploaded to loan
- `document.approved` - Document reviewed and approved

#### Tasks
- `task.created` - New task created
- `task.completed` - Task marked as completed

#### Applications
- `application.submitted` - Borrower submitted application

---

## Webhook Delivery & Retry Logic

### Delivery Process

1. **Event Triggered:** System event occurs (e.g., lead created)
2. **Signature Generation:** Payload is signed with HMAC-SHA256
3. **HTTP POST:** Webhook sent to subscribed URL
4. **Response Check:** 2xx status code = success, other = retry
5. **Retry if Failed:** Exponential backoff retry schedule

### Retry Schedule

| Attempt | Delay |
|---------|-------|
| 1 | Immediate |
| 2 | 1 second |
| 3 | 5 seconds |
| 4 | 25 seconds |
| 5 | 125 seconds |

After 5 failed attempts, the webhook is marked as failed and no further retries occur.

### Webhook Payload Format

Every webhook includes:

```json
{
  "event": "lead.created",
  "timestamp": "2026-02-20T15:30:00Z",
  "data": {
    // Event-specific data
  }
}
```

### Webhook Headers

```
Content-Type: application/json
X-Webhook-Signature: <HMAC-SHA256 signature>
X-Webhook-Timestamp: <Unix timestamp>
X-Webhook-Event: <Event type>
User-Agent: PerenniaAI-Webhooks/1.0
```

---

## Security Best Practices

### Verifying Webhook Signatures

Always verify webhook signatures to ensure authenticity:

```python
import hmac
import hashlib

def verify_webhook(payload, signature, secret, timestamp, event_type):
    """Verify webhook signature"""
    signature_payload = f"{timestamp}.{event_type}".encode() + str(payload).encode()
    expected_signature = hmac.new(
        secret.encode(),
        signature_payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)
```

### Protecting API Keys

- **Never commit API keys to source control**
- **Use environment variables** to store keys
- **Rotate keys regularly** (at least every 90 days)
- **Use minimal scopes** - only grant necessary permissions
- **Set expiration dates** when possible
- **Monitor usage** - review API key activity regularly

### Webhook Security

- **Use HTTPS only** - Webhook URLs must use HTTPS
- **Verify signatures** - Always validate webhook signatures
- **Implement idempotency** - Handle duplicate deliveries gracefully
- **Use IP whitelisting** (optional) - Restrict webhook sources

### Rate Limit Best Practices

- **Implement exponential backoff** when rate limited
- **Cache responses** where appropriate
- **Use batch endpoints** for bulk operations
- **Monitor rate limit headers** to avoid hitting limits

---

## Support

For technical support or questions:
- **Email:** support@perenniaai.com
- **Documentation:** https://docs.perenniaai.com
- **Status Page:** https://status.perenniaai.com

---

**Last Updated:** February 20, 2026
