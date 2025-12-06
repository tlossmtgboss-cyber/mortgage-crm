# Perennia AI Email Orchestrator

AI-powered email automation system for mortgage CRM workflows using Microsoft Graph API and Claude AI.

## Features

- **Real-time Processing**: Microsoft Graph webhooks for instant email handling
- **AI Classification**: Claude-powered intent detection and routing
- **Specialized Processors**:
  - Loan Application detection and auto-creation
  - Client inquiry handling with auto-responses
  - Invoice routing and categorization
  - Document classification and task creation
  - SLA monitoring with breach prevention
- **Queue Management**: Batch processing with retry logic
- **Daily Summaries**: Automated reporting on email metrics and time saved

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
                    │    (Observer Pattern Router)        │
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

See `database/schema.sql` for complete schema.

## Metrics & ROI

The system tracks time saved for each processor:
- Total time saved per day
- Per-processor breakdown
- SLA compliance rates
- Auto-response rates

Access via `/api/status` or daily summary emails.

## License

Proprietary - Perennia AI
