# Microsoft Graph Email Webhook Setup

This guide explains how to set up real-time email processing using Microsoft Graph webhooks.

## Overview

When configured, the system will:
1. Receive notifications from Microsoft Graph when new emails arrive
2. Automatically classify emails (loan applications, documents, inquiries, etc.)
3. Create tasks for important emails
4. Track time saved through automation

## Prerequisites

- Microsoft 365 Business account
- Azure App Registration with Graph API permissions
- HTTPS endpoint for webhooks (Railway provides this automatically)

## Step 1: Azure App Permissions

Ensure your Azure App Registration has these Graph API permissions:

### Application Permissions (for app-only access)
- `Mail.Read` - Read mail in all mailboxes
- `Mail.ReadWrite` - Read and write mail

### Delegated Permissions (for user-specific access)
- `Mail.Read` - Read user mail
- `Mail.ReadWrite` - Read and write user mail
- `offline_access` - Maintain access to data

**Important:** Click "Grant admin consent" after adding permissions.

## Step 2: Environment Variables

Add these to your `.env` file:

```bash
# Microsoft Graph API (should already be configured)
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret
MICROSOFT_TENANT_ID=your-tenant-id

# Webhook Configuration
GRAPH_WEBHOOK_URL=https://your-app.railway.app/api/webhooks/graph
GRAPH_WEBHOOK_SECRET=your-secret-string

# Fallback secret (optional, used if GRAPH_WEBHOOK_SECRET not set)
WEBHOOK_SECRET=your-webhook-secret
```

## Step 3: Run Database Migration

Apply the webhook tables migration:

```bash
# From the backend directory
psql $DATABASE_URL < migrations/add_email_webhook_tables.sql
```

This creates:
- `email_webhook_log` - Tracks incoming notifications
- `email_tracking` - Stores processed emails
- `email_processing_log` - Processor execution history
- `email_templates` - Auto-response templates
- `email_response_tracking` - SLA monitoring
- `graph_webhook_subscriptions` - Active subscriptions
- `automation_time_savings` - Time savings tracking

## Step 4: Register Webhook Subscription

Use the registration script:

```bash
# List existing subscriptions
python scripts/register_graph_webhook.py list

# Create a new subscription
python scripts/register_graph_webhook.py create

# For a specific user's mailbox
python scripts/register_graph_webhook.py create --user-email user@company.com

# Renew an existing subscription
python scripts/register_graph_webhook.py renew --subscription-id <id>

# Delete a subscription
python scripts/register_graph_webhook.py delete --subscription-id <id>
```

## Step 5: Verify Setup

### Check webhook status:
```bash
curl https://your-app.railway.app/api/webhooks/graph/status
```

Expected response:
```json
{
  "status": "active",
  "last_24h": {
    "received": 5,
    "processed": 5,
    "last_received": "2024-01-15T10:30:00Z"
  },
  "webhook_url": "https://your-app.railway.app/api/webhooks/graph",
  "secret_configured": true
}
```

### Check database:
```sql
-- Recent webhook notifications
SELECT * FROM email_webhook_log ORDER BY received_at DESC LIMIT 10;

-- Processed emails
SELECT * FROM email_tracking ORDER BY received_at DESC LIMIT 10;

-- Time savings
SELECT * FROM automation_time_savings ORDER BY triggered_at DESC LIMIT 10;
```

## Subscription Renewal

Graph webhook subscriptions expire after ~3 days. You need to renew them before expiration.

### Option 1: Manual Renewal
```bash
python scripts/register_graph_webhook.py renew --subscription-id <id>
```

### Option 2: Automatic Renewal (Recommended)

Add a cron job to renew daily:
```bash
# Every day at 2 AM
0 2 * * * cd /path/to/backend && python scripts/register_graph_webhook.py renew --subscription-id <id>
```

Or use the Railway cron feature.

## Email Classification

Emails are automatically classified into these categories:

| Category | Keywords | Action |
|----------|----------|--------|
| `loan_application` | "loan application", "mortgage application", "pre-approval" | Create high-priority task |
| `document_submission` | "attached", "paystub", "w2", "bank statement" | Create task, classify document |
| `urgent_inquiry` | "urgent", "asap", "critical", "emergency" | Create high-priority task |
| `client_inquiry` | "question", "status update", "when" | Track for SLA |
| `invoice` | "invoice", "payment", "bill" | Route to accounting |
| `general` | Everything else | Log and track |

## Troubleshooting

### Webhook not receiving notifications

1. Check the subscription is active:
   ```bash
   python scripts/register_graph_webhook.py list
   ```

2. Verify the webhook URL is accessible:
   ```bash
   curl -X POST https://your-app.railway.app/api/webhooks/graph?validationToken=test
   # Should return "test"
   ```

3. Check logs:
   ```bash
   railway logs | grep "GRAPH WEBHOOK"
   ```

### Emails not being processed

1. Check the webhook log:
   ```sql
   SELECT * FROM email_webhook_log
   WHERE processed = false
   ORDER BY received_at DESC;
   ```

2. Check for errors:
   ```sql
   SELECT * FROM email_webhook_log
   WHERE error_message IS NOT NULL
   ORDER BY received_at DESC;
   ```

### Missing access token

1. Verify Microsoft credentials in `.env`
2. Check if the app has proper permissions
3. Ensure admin consent is granted

## Security Considerations

1. **HTTPS Required**: Microsoft Graph only sends webhooks to HTTPS endpoints
2. **Client State Validation**: Always validate the `clientState` in notifications
3. **Token Security**: Never expose access tokens in logs or responses
4. **Rate Limiting**: Graph has rate limits; the webhook responds quickly to avoid timeouts

## Monitoring

### Key Metrics to Track

- Webhook notifications received per hour
- Processing success rate
- Time saved through automation
- SLA compliance rate

### Dashboard Query

```sql
SELECT
    DATE(received_at) as date,
    COUNT(*) as total_emails,
    COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed,
    SUM(COALESCE(time_saved_minutes, 0)) as time_saved
FROM email_tracking
WHERE received_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(received_at)
ORDER BY date DESC;
```

## Related Documentation

- [Email Orchestrator README](../../email-orchestrator/README.md)
- [Email Orchestrator Deployment](../../email-orchestrator/docs/DEPLOYMENT.md)
- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/api/overview)
