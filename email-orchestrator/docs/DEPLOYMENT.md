# Email Orchestrator - Deployment Guide

## Prerequisites

Before deploying, ensure you have:

- **Node.js 18+** installed
- **PostgreSQL 14+** running
- **Microsoft 365 Business** account with Graph API access
- **Azure App Registration** for Graph API authentication
- **Anthropic API key** for Claude AI

---

## Step 1: Database Setup

### 1.1 Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE perennia_email;

# Connect to new database
\c perennia_email
```

### 1.2 Run Schema

```bash
# From the email-orchestrator directory
psql -U postgres -d perennia_email -f database/schema.sql
```

### 1.3 Verify Tables

```sql
-- List all tables
\dt

-- Should see:
-- email_tracking
-- email_processing_log
-- email_processing_errors
-- email_templates
-- email_processing_queue
-- email_response_tracking
-- automation_time_savings
-- processor_performance
-- webhook_subscriptions
-- And more...
```

---

## Step 2: Azure App Registration

### 2.1 Create App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Configure:
   - Name: `Perennia Email Orchestrator`
   - Supported account types: `Single tenant`
   - Redirect URI: Leave blank for now

### 2.2 Configure API Permissions

Add these **Application permissions** for Microsoft Graph:

```
Mail.Read           - Read mail in all mailboxes
Mail.ReadWrite      - Read and write mail in all mailboxes
Mail.Send           - Send mail as any user
User.Read.All       - Read all users' profiles
```

Then click **Grant admin consent**.

### 2.3 Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Set expiration (recommended: 24 months)
4. Copy the secret value immediately (you won't see it again)

### 2.4 Note Your Credentials

You'll need:
- **Tenant ID** (from Overview page)
- **Client ID** (Application ID from Overview)
- **Client Secret** (the value you just created)

---

## Step 3: Environment Configuration

### 3.1 Create .env File

```bash
cp .env.example .env
```

### 3.2 Configure All Variables

Edit `.env` with your values:

```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/perennia_email

# Microsoft Graph API
GRAPH_ACCESS_TOKEN=your-access-token
SENDER_EMAIL=automation@yourcompany.com
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Anthropic API
ANTHROPIC_API_KEY=sk-ant-your-key

# Webhook Configuration
WEBHOOK_SECRET=your-random-secret-string
WEBHOOK_URL=https://your-domain.com/webhooks/graph

# Application Settings
PORT=3000
NODE_ENV=production
LOG_LEVEL=info

# Internal Domains (comma-separated)
INTERNAL_DOMAINS=yourcompany.com,perennia.ai

# Feature Flags
ENABLE_AUTO_RESPONSES=true
ENABLE_LOAN_CREATION=true
ENABLE_INVOICE_PROCESSING=true
ENABLE_SLA_MONITORING=true

# Summary Recipients (comma-separated)
SUMMARY_RECIPIENTS=manager@yourcompany.com,team@yourcompany.com

# Accounting Email for Invoice Routing
ACCOUNTING_EMAIL=accounting@yourcompany.com
```

---

## Step 4: Install and Build

### 4.1 Install Dependencies

```bash
npm install
```

### 4.2 Build TypeScript

```bash
npm run build
```

### 4.3 Verify Build

```bash
# Check dist folder was created
ls -la dist/

# Should see compiled .js files
```

---

## Step 5: Start the Server

### 5.1 Development Mode

```bash
npm run dev
```

### 5.2 Production Mode

```bash
npm start
```

### 5.3 Verify Server is Running

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "uptime": 45.123,
  "environment": "production"
}
```

---

## Step 6: Create Graph Webhook Subscription

### 6.1 Get Access Token

First, get an access token for Graph API:

```bash
curl -X POST "https://login.microsoftonline.com/$AZURE_TENANT_ID/oauth2/v2.0/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$AZURE_CLIENT_ID" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "client_secret=$AZURE_CLIENT_SECRET" \
  -d "grant_type=client_credentials"
```

### 6.2 Create Subscription

```bash
curl -X POST "https://graph.microsoft.com/v1.0/subscriptions" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "changeType": "created",
    "notificationUrl": "https://your-domain.com/webhooks/graph",
    "resource": "/me/mailFolders/inbox/messages",
    "expirationDateTime": "2024-01-18T00:00:00Z",
    "clientState": "your-webhook-secret"
  }'
```

### 6.3 Verify Subscription

The webhook endpoint must respond to validation:
- Microsoft will send a POST with `validationToken` query param
- Your endpoint must return the token as plain text

---

## Step 7: Load Email Templates

### 7.1 Default Templates

The schema includes default templates. Verify they're loaded:

```sql
SELECT name, subject FROM email_templates;
```

### 7.2 Add Custom Templates

```sql
INSERT INTO email_templates (name, subject, body, is_html, variables, category)
VALUES (
  'custom_response',
  'Re: Your Inquiry',
  '<p>Hello {firstName},</p><p>Thank you for your message...</p>',
  TRUE,
  ARRAY['firstName', 'inquiryType'],
  'inquiry'
);
```

---

## Step 8: Test the System

### 8.1 Health Check

```bash
curl http://localhost:3000/health
```

### 8.2 Get Metrics

```bash
curl http://localhost:3000/metrics
```

### 8.3 Manual Email Processing

```bash
curl -X POST http://localhost:3000/api/process \
  -H "Content-Type: application/json" \
  -d '{"emailId": "your-test-email-id"}'
```

### 8.4 Batch Processing

```bash
curl -X POST http://localhost:3000/api/queue/process?limit=10
```

### 8.5 Check Status

```bash
curl http://localhost:3000/api/status
```

---

## Step 9: Production Deployment

### 9.1 Using PM2 (Recommended)

```bash
# Install PM2
npm install -g pm2

# Start with PM2
pm2 start dist/index.js --name email-orchestrator

# Save PM2 configuration
pm2 save

# Setup startup script
pm2 startup
```

### 9.2 Using Docker

Create `Dockerfile`:

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY dist/ ./dist/

ENV NODE_ENV=production

EXPOSE 3000

CMD ["node", "dist/index.js"]
```

Build and run:

```bash
docker build -t email-orchestrator .
docker run -d -p 3000:3000 --env-file .env email-orchestrator
```

### 9.3 Using systemd

Create `/etc/systemd/system/email-orchestrator.service`:

```ini
[Unit]
Description=Email Orchestrator
After=network.target postgresql.service

[Service]
Type=simple
User=node
WorkingDirectory=/opt/email-orchestrator
ExecStart=/usr/bin/node dist/index.js
Restart=on-failure
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=email-orchestrator
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable email-orchestrator
sudo systemctl start email-orchestrator
```

---

## Step 10: Monitoring Setup

### 10.1 Log Monitoring

```bash
# View combined logs
tail -f logs/combined.log

# View errors only
tail -f logs/error.log

# Search for specific processor
grep "LoanApplicationProcessor" logs/combined.log
```

### 10.2 Database Monitoring

```sql
-- Emails processed today
SELECT COUNT(*) as today_count,
       SUM(total_time_saved_minutes) as time_saved
FROM email_tracking
WHERE received_at >= CURRENT_DATE;

-- Processor performance
SELECT * FROM processor_performance
ORDER BY total_runs DESC;

-- Recent errors
SELECT * FROM email_processing_errors
ORDER BY created_at DESC
LIMIT 10;
```

### 10.3 Health Monitoring

Set up external monitoring to ping `/health` endpoint every minute.

---

## Step 11: Backup Configuration

### 11.1 Database Backup

```bash
# Daily backup script
pg_dump -U postgres perennia_email > backup_$(date +%Y%m%d).sql
```

### 11.2 Configuration Backup

```bash
# Backup .env (securely)
cp .env .env.backup.$(date +%Y%m%d)
```

---

## Troubleshooting

### Server Won't Start

1. Check Node.js version: `node --version` (needs 18+)
2. Verify dependencies: `npm install`
3. Check .env file exists and is configured
4. Check database connection: `psql $DATABASE_URL -c "SELECT 1"`

### Webhooks Not Working

1. Ensure WEBHOOK_URL is publicly accessible
2. Check SSL certificate is valid
3. Verify WEBHOOK_SECRET matches subscription clientState
4. Check firewall allows incoming connections on port 3000

### Emails Not Processing

1. Check Graph API token is valid
2. Verify subscription is active: `GET /v1.0/subscriptions`
3. Check processor logs for errors
4. Verify email matches processor criteria

### High Error Rate

1. Check Anthropic API key is valid
2. Verify rate limits aren't exceeded
3. Review error logs for patterns
4. Check database connection pool

---

## Security Checklist

- [ ] .env file is not in version control
- [ ] Database uses strong password
- [ ] HTTPS enabled for webhook endpoint
- [ ] API keys rotated regularly
- [ ] Logs don't contain sensitive data
- [ ] Firewall rules configured
- [ ] Access logs enabled

---

## Maintenance Tasks

### Daily
- Review error logs
- Check processing metrics

### Weekly
- Review time savings reports
- Check subscription expiration
- Verify backup integrity

### Monthly
- Rotate API keys
- Review and clean old logs
- Update dependencies
- Review processor performance

---

## Support

If you encounter issues:

1. Check logs: `logs/combined.log`
2. Query errors: `SELECT * FROM email_processing_errors`
3. Review metrics: `GET /metrics`
4. Check health: `GET /health`

---

*Email Orchestrator - Perennia AI*
