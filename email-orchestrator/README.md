# Perennia AI Email Orchestrator

AI-powered email automation system for mortgage CRM workflows using Microsoft Graph API and Claude AI.

## Features

- **Real-time Processing**: Microsoft Graph webhooks for instant email handling
- **AI Classification**: Claude-powered intent detection and routing
- **Event-Driven Architecture**: EventEmitter for real-time monitoring
- **Specialized Processors**:
  - Loan Application detection and auto-creation
  - Client inquiry handling with auto-responses
  - Invoice routing and categorization
  - Document classification and task creation
  - SLA monitoring with breach prevention
- **Queue Management**: Batch processing with retry logic
- **Metrics Collection**: Time savings, processor performance, ROI tracking
- **Daily Summaries**: Automated reporting on email metrics

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │       Microsoft Graph API           │
                    │    (Email, Calendar, Webhooks)      │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │        GraphEmailService            │
                    │   (OAuth, Rate Limiting, Retry)     │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │        EmailOrchestrator            │
                    │  (Observer Pattern + EventEmitter)  │
                    └──────────────┬──────────────────────┘
                                   │
       ┌───────────┬───────────┬───┴───┬───────────┬───────────┐
       │           │           │       │           │           │
  ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌▼────────┐ ┌▼─────────┐
  │  Loan   │ │ Client  │ │Invoice  │ │Document │ │   SLA    │
  │  App    │ │ Inquiry │ │Processor│ │Processor│ │ Monitor  │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘
```

## Quick Start

### Prerequisites

- Node.js 18+
- PostgreSQL 14+
- Microsoft 365 Business account (for Graph API)
- Anthropic API key

### Installation

```bash
# Install dependencies
npm install

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
psql $DATABASE_URL < database/schema.sql

# Build TypeScript
npm run build

# Start the server
npm start
```

### Development

```bash
# Run in development mode with hot reload
npm run dev

# Type checking
npm run typecheck

# Linting
npm run lint
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `GRAPH_ACCESS_TOKEN` | Microsoft Graph API token | Yes |
| `SENDER_EMAIL` | Email address to send from | Yes |
| `ANTHROPIC_API_KEY` | Claude API key | Yes |
| `WEBHOOK_SECRET` | Secret for webhook validation | Yes |
| `WEBHOOK_URL` | Public URL for webhooks | Production |
| `INTERNAL_DOMAINS` | Comma-separated internal domains | No |
| `SUMMARY_RECIPIENTS` | Comma-separated emails for summaries | No |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_AUTO_RESPONSES` | true | Send auto-reply emails |
| `ENABLE_LOAN_CREATION` | true | Auto-create loans from applications |
| `ENABLE_INVOICE_PROCESSING` | true | Route invoices to accounting |
| `ENABLE_SLA_MONITORING` | true | Track response times |

## Usage Examples

### Process a Single Email

```typescript
import { orchestrator } from './index';

const email = await fetchEmailFromGraph(emailId);
const results = await orchestrator.processEmail(email, userId, userEmail);

console.log('Processing results:', results);
```

### Process Batch of Emails

```typescript
const emails = await fetchRecentEmails();
const results = await orchestrator.processBatch(emails, userId, userEmail);

// results is a Map<emailId, ProcessingResult[]>
for (const [emailId, emailResults] of results) {
  console.log(`Email ${emailId}:`);
  emailResults.forEach(result => {
    console.log(`  - ${result.processor}: ${result.success ? 'SUCCESS' : 'FAILED'}`);
  });
}
```

### Listen to Events

```typescript
// Real-time monitoring with EventEmitter
orchestrator.onEvent('email:processed', ({ email, processor, result }) => {
  console.log(`✓ Processed by ${processor}:`, email.subject);
});

orchestrator.onEvent('email:processing:error', ({ email, processor, error }) => {
  console.error(`✗ Failed in ${processor}:`, error.message);
});

orchestrator.onEvent('batch:processed', ({ emailCount, totalTime }) => {
  console.log(`Batch complete: ${emailCount} emails in ${totalTime}ms`);
});
```

### Get Metrics

```typescript
import { MetricsCollector } from './monitoring';

const metrics = new MetricsCollector(pool, logger);

// Get time saved
const savings = await metrics.getTotalTimeSaved(30);
console.log(`Time saved: ${savings.totalHours} hours`);

// Get processor performance
const processors = await metrics.getProcessorMetrics();
processors.forEach(p => {
  console.log(`${p.processorName}: ${p.successCount}/${p.totalRuns} success`);
});

// Generate full report
const report = await metrics.generateReport(7);
console.log(report);
```

## Creating Custom Processors

```typescript
import { BaseEmailProcessor } from './core/IEmailProcessor';
import { Email, ProcessingContext } from './types';

export class CustomProcessor extends BaseEmailProcessor {
  readonly name = 'CustomProcessor';
  readonly priority = 75;
  readonly description = 'Handles custom email types';

  async canProcess(email: Email): Promise<boolean> {
    return this.matchesPattern(email.subject, ['keyword1', 'keyword2']);
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('Processing custom email', { emailId: email.id });

    const result = await yourCustomLogic(email);

    return {
      success: true,
      processor: this.name,
      action: 'custom_action_taken',
      timeSaved: 5, // minutes
      metadata: { result }
    };
  }
}

// Register it
orchestrator.registerProcessor('CustomProcessor', new CustomProcessor(pool, logger));
```

## API Endpoints

### Health & Metrics

- `GET /health` - Health check
- `GET /metrics` - Processing metrics

### Processing

- `POST /api/process` - Process single email
- `GET /api/status` - Today's processing summary

### Queue Management

- `GET /api/queue/status` - Queue status
- `POST /api/queue/process` - Process batch from queue

### Webhooks

- `POST /webhooks/graph` - Microsoft Graph notifications

## Processors

### LoanApplicationProcessor (Priority: 100)
Detects loan applications and auto-creates loan records.
- Time saved: 15 minutes per email
- Auto-response with confirmation

### SLAMonitorProcessor (Priority: 90)
Tracks email response times against SLA targets.
- Priorities: Critical (1hr), High (4hr), Medium (24hr), Low (48hr)
- Warning emails before breach

### InvoiceProcessor (Priority: 80)
Categorizes and routes invoices.
- Auto-forward to accounting
- Categories: appraisal, title, credit, legal

### DocumentProcessor (Priority: 70)
Classifies document attachments.
- Categories: income, assets, property, identity, credit
- Creates review tasks

### ClientInquiryProcessor (Priority: 50)
Handles client questions with AI responses.
- Types: status, document, rate, general
- Optional auto-responses

## Scheduled Jobs

| Schedule | Job | Description |
|----------|-----|-------------|
| */5 * * * * | Queue Processing | Process pending emails |
| 0 * * * * | SLA Check | Check for impending breaches |
| 0 18 * * 1-5 | Daily Summary | Send summary email |
| 0 2 * * 0 | Cleanup | Remove old logs |

## Database Schema

The schema includes tables for:
- `email_tracking` - Main email log
- `email_processing_log` - Processor execution logs
- `email_processing_queue` - Batch processing queue
- `email_response_tracking` - SLA monitoring
- `email_templates` - Response templates
- `webhook_subscriptions` - Graph subscription management
- `automation_time_savings` - Time savings tracking
- `processor_performance` - Processor metrics

See `database/schema.sql` for complete schema.

## Monitoring & Metrics

### View Processing Dashboard

```sql
-- Daily email summary
SELECT * FROM email_processing_summary
ORDER BY date DESC
LIMIT 7;

-- Processor performance
SELECT * FROM processor_performance
ORDER BY total_runs DESC;

-- Time savings
SELECT * FROM automation_time_savings
ORDER BY triggered_at DESC
LIMIT 50;
```

## Expected Results

After full implementation, you should see:

- **60-80% reduction** in time spent on email
- **90% of routine emails** processed automatically
- **Critical emails surfaced** within minutes
- **Professional, consistent** automated responses
- **Complete audit trail** of all email actions
- **Detailed analytics** on time saved and productivity gains

## Security Best Practices

1. **Store secrets in environment variables** - Never commit API keys
2. **Use Azure Key Vault** for production secrets
3. **Implement rate limiting** on webhook endpoints
4. **Validate webhook signatures** from Microsoft
5. **Use least-privilege** Graph API permissions
6. **Encrypt sensitive** email content at rest
7. **Audit all** automated actions

## Deployment Checklist

- [ ] Database schema created
- [ ] Environment variables configured
- [ ] Azure App Registration created
- [ ] Graph API permissions granted
- [ ] Webhook endpoint deployed
- [ ] Subscription created and validated
- [ ] Scheduled jobs configured
- [ ] Email templates loaded
- [ ] Processors registered
- [ ] Monitoring dashboard set up
- [ ] Logs configured
- [ ] Backup procedures in place

## License

Proprietary - Perennia AI / TL Development LLC
