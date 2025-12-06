# Email Orchestrator - Perennia AI Integration Guide

## Overview

This guide shows you how to integrate the Email Orchestrator system into your existing Perennia AI codebase.

## Architecture Integration

```
Perennia AI (Existing)                    Email Orchestrator (New)
├── services/                             ├── core/
│   ├── microsoftGraphService.js          │   ├── EmailOrchestrator.ts
│   ├── anthropicService.js               │   └── IEmailProcessor.ts
│   └── ...                               ├── processors/
├── routes/                               │   ├── LoanApplicationProcessor.ts
│   ├── loans.js                          │   ├── ClientInquiryProcessor.ts
│   └── ...                               │   └── ... (add more)
└── database/                             ├── services/
    ├── pool.js                           │   ├── EmailTemplateService.ts
    └── ...                               │   └── DailySummaryBot.ts
                                          ├── utils/
                                          │   └── RetryManager.ts
                                          └── types/
                                              └── index.ts
```

## Step-by-Step Integration

### 1. Add to Your Existing Express App

```javascript
// In your main app.js or server.js
import { initializeEmailOrchestrator } from './email-orchestrator/init';

// After your existing setup
const emailOrchestrator = await initializeEmailOrchestrator(pool, logger);

// Add to your app
app.emailOrchestrator = emailOrchestrator;

// Mount webhook endpoint
app.use('/api/webhooks', require('./email-orchestrator/webhooks/graphWebhook'));
```

### 2. Create Initialization Module

```typescript
// src/email-orchestrator/init.ts
import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { EmailOrchestrator } from './core/EmailOrchestrator';
import { RetryManager } from './utils/RetryManager';
import { MetricsCollector } from './monitoring/MetricsCollector';
import { EmailTemplateService } from './services/EmailTemplateService';
import { LoanApplicationProcessor } from './processors/LoanApplicationProcessor';
import { ClientInquiryProcessor } from './processors/ClientInquiryProcessor';

export async function initializeEmailOrchestrator(
  pool: Pool,
  logger: Logger
): Promise<EmailOrchestrator> {

  // Initialize dependencies
  const anthropic = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY!
  });

  const retryManager = new RetryManager(logger);
  const metrics = new MetricsCollector(logger);

  // Get Graph access token from your existing auth service
  const graphAccessToken = await getGraphAccessToken(); // Your existing function

  const templateService = new EmailTemplateService(
    pool,
    logger,
    graphAccessToken,
    process.env.SENDER_EMAIL!
  );

  // Load templates
  await templateService.loadTemplates();

  // Create orchestrator
  const orchestrator = new EmailOrchestrator(
    pool,
    logger,
    retryManager,
    metrics
  );

  // Register processors
  const internalDomains = process.env.INTERNAL_DOMAINS?.split(',') || [];

  orchestrator.registerProcessor(
    'LoanApplicationProcessor',
    new LoanApplicationProcessor(pool, logger, anthropic, templateService)
  );

  orchestrator.registerProcessor(
    'ClientInquiryProcessor',
    new ClientInquiryProcessor(
      pool,
      logger,
      anthropic,
      templateService,
      internalDomains
    )
  );

  // Set up event listeners for monitoring
  orchestrator.on('email:processed', ({ email, processor, result }) => {
    logger.info('Email processed successfully', {
      emailId: email.id,
      processor,
      timeSaved: result.timeSaved
    });
  });

  orchestrator.on('email:processing:error', ({ email, processor, error }) => {
    logger.error('Email processing failed', {
      emailId: email.id,
      processor,
      error
    });
  });

  logger.info('Email Orchestrator initialized', {
    processors: orchestrator.getProcessors()
  });

  return orchestrator;
}
```

### 3. Integrate with Your Email Service

Update your existing `microsoftGraphService.js`:

```javascript
// services/microsoftGraphService.js

class MicrosoftGraphService {
  // ... existing methods

  /**
   * New: Process incoming email with orchestrator
   */
  async processIncomingEmail(emailId) {
    try {
      // Fetch email from Graph API (your existing method)
      const email = await this.getEmail(emailId);

      // Get orchestrator from app
      const orchestrator = this.app.emailOrchestrator;

      // Process with orchestrator
      const results = await orchestrator.processEmail(email);

      this.logger.info('Email processed via orchestrator', {
        emailId,
        results
      });

      return results;
    } catch (error) {
      this.logger.error('Failed to process email via orchestrator', {
        emailId,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * New: Batch process unread emails
   */
  async processBatchUnread() {
    try {
      // Get unread emails from last 24 hours
      const emails = await this.getUnreadEmails();

      // Process batch
      const orchestrator = this.app.emailOrchestrator;
      const results = await orchestrator.processBatch(emails);

      this.logger.info('Batch processing complete', {
        totalEmails: emails.length,
        successCount: Array.from(results.values())
          .flat()
          .filter(r => r.success).length
      });

      return results;
    } catch (error) {
      this.logger.error('Batch processing failed', { error: error.message });
      throw error;
    }
  }
}
```

### 4. Add API Routes

```javascript
// routes/emailAutomation.js
const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');

/**
 * Get processing statistics
 */
router.get('/stats', authenticateToken, async (req, res) => {
  try {
    const orchestrator = req.app.emailOrchestrator;

    const { startDate, endDate } = req.query;
    const stats = await orchestrator.getStatistics(
      startDate ? new Date(startDate) : undefined,
      endDate ? new Date(endDate) : undefined
    );

    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Get processor metrics
 */
router.get('/processors/metrics', authenticateToken, async (req, res) => {
  try {
    const orchestrator = req.app.emailOrchestrator;
    const { processor } = req.query;

    const metrics = await orchestrator.getProcessorMetrics(processor);
    res.json(metrics);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Manually trigger email processing
 */
router.post('/process/:emailId', authenticateToken, async (req, res) => {
  try {
    const { emailId } = req.params;
    const graphService = req.app.microsoftGraphService;

    const email = await graphService.getEmail(emailId);
    const orchestrator = req.app.emailOrchestrator;

    const results = await orchestrator.processEmail(email);

    res.json({
      success: true,
      emailId,
      results
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Process batch of unread emails
 */
router.post('/process-batch', authenticateToken, async (req, res) => {
  try {
    const graphService = req.app.microsoftGraphService;
    const results = await graphService.processBatchUnread();

    res.json({
      success: true,
      emailsProcessed: Array.from(results.keys()).length,
      results: Object.fromEntries(results)
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Get list of registered processors
 */
router.get('/processors', authenticateToken, async (req, res) => {
  try {
    const orchestrator = req.app.emailOrchestrator;
    const processors = orchestrator.getProcessors();

    res.json({ processors });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
```

### 5. Set Up Cron Jobs

```javascript
// jobs/emailJobs.js
const cron = require('node-cron');
const { DailySummaryBot } = require('../email-orchestrator/services/DailySummaryBot');

function initializeEmailJobs(app) {
  const { pool, logger, emailOrchestrator } = app;

  // Process emails every 15 minutes
  cron.schedule('*/15 * * * *', async () => {
    logger.info('[Email Job] Starting scheduled email processing');

    try {
      const graphService = app.microsoftGraphService;
      await graphService.processBatchUnread();
    } catch (error) {
      logger.error('[Email Job] Failed', { error: error.message });
    }
  });

  // Daily summary at 8 AM
  cron.schedule('0 8 * * *', async () => {
    logger.info('[Email Job] Generating daily summaries');

    try {
      const summaryBot = new DailySummaryBot(
        pool,
        logger,
        app.templateService,
        app.anthropic
      );

      // Get all users with email monitoring enabled
      const users = await pool.query(`
        SELECT user_id, email
        FROM email_monitoring_schedule
        WHERE enabled = TRUE
      `);

      for (const user of users.rows) {
        await summaryBot.generateDailySummary(user.user_id, user.email);
      }

      logger.info('[Email Job] Daily summaries sent', {
        count: users.rows.length
      });
    } catch (error) {
      logger.error('[Email Job] Daily summary failed', {
        error: error.message
      });
    }
  });

  logger.info('Email automation jobs scheduled');
}

module.exports = { initializeEmailJobs };
```

### 6. Update Your Main Server File

```javascript
// server.js or app.js
const express = require('express');
const { initializeEmailOrchestrator } = require('./email-orchestrator/init');
const { initializeEmailJobs } = require('./jobs/emailJobs');
const emailAutomationRoutes = require('./routes/emailAutomation');

async function startServer() {
  const app = express();

  // ... your existing setup

  // Initialize email orchestrator
  app.emailOrchestrator = await initializeEmailOrchestrator(pool, logger);

  // Mount email automation routes
  app.use('/api/email-automation', emailAutomationRoutes);

  // Initialize cron jobs
  initializeEmailJobs(app);

  // ... rest of your server setup

  app.listen(PORT, () => {
    logger.info(`Server started on port ${PORT}`);
    logger.info('Email Orchestrator active');
  });
}

startServer();
```

### 7. Add to Your Existing Loan Workflow

Integrate with your existing loan creation:

```javascript
// In your existing loans.js route or service

// When a loan is created manually
router.post('/loans', authenticateToken, async (req, res) => {
  try {
    // Your existing loan creation logic
    const loan = await createLoan(req.body);

    // NEW: If this came from an email, update the email tracking
    if (req.body.sourceEmailId) {
      const orchestrator = req.app.emailOrchestrator;

      await pool.query(`
        UPDATE email_tracking
        SET status = 'processed',
            processing_results = $2
        WHERE email_id = $1
      `, [
        req.body.sourceEmailId,
        JSON.stringify([{
          success: true,
          processor: 'ManualLoanCreation',
          data: { loanId: loan.id }
        }])
      ]);
    }

    res.json(loan);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});
```

## Testing Your Integration

### 1. Test Email Processing

```javascript
// test/emailOrchestrator.test.js
const { orchestrator } = require('../app');

describe('Email Orchestrator', () => {
  it('should process loan application email', async () => {
    const testEmail = {
      id: 'test-email-1',
      subject: 'Loan Application - John Doe',
      from: {
        emailAddress: {
          name: 'John Doe',
          address: 'john@example.com'
        }
      },
      body: {
        content: 'I would like to apply for a $300,000 purchase loan...'
      },
      receivedDateTime: new Date().toISOString(),
      hasAttachments: false
    };

    const results = await orchestrator.processEmail(testEmail);

    expect(results).toBeDefined();
    expect(results.some(r => r.success)).toBe(true);
  });
});
```

### 2. Test Manual Processing

```bash
# Send test request
curl -X POST http://localhost:3000/api/email-automation/process-batch \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 3. Check Statistics

```bash
# Get processing stats
curl http://localhost:3000/api/email-automation/stats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Monitoring in Production

### 1. Add to Your Dashboard

Create a new dashboard view showing:
- Emails processed today
- Time saved today
- Processor success rates
- Pending responses

### 2. Set Up Alerts

```javascript
// Add to your monitoring service
orchestrator.on('email:processing:error', ({ email, error }) => {
  if (error.includes('AI API')) {
    // Alert: AI service down
    alertService.send('Critical: AI email processing failing');
  }
});

orchestrator.on('batch:processed', ({ emailCount, totalTime }) => {
  const avgTime = totalTime / emailCount;
  if (avgTime > 5000) { // More than 5 seconds per email
    alertService.send('Warning: Email processing slow');
  }
});
```

## Migration Strategy

### Phase 1: Observation (Week 1)
- Deploy orchestrator in read-only mode
- Process emails but don't send responses
- Validate AI classifications
- Monitor performance

### Phase 2: Limited Automation (Week 2-3)
- Enable auto-responses for simple inquiries
- Keep loan applications in manual review
- Daily summaries to loan officers

### Phase 3: Full Automation (Week 4+)
- Enable all processors
- Auto-create loan records
- Full automated responses
- Monitor and optimize

## Rollback Plan

If issues occur:

```javascript
// Disable orchestrator
app.emailOrchestrator = null;

// Or disable specific processor
orchestrator.unregisterProcessor('LoanApplicationProcessor');

// Revert to manual email handling
```

## Next Steps

1. **Run database migration** - Execute schema.sql
2. **Configure environment** - Set all env vars
3. **Deploy orchestrator** - Add to your codebase
4. **Test thoroughly** - Run test suite
5. **Monitor closely** - Watch logs for first week
6. **Optimize** - Adjust based on metrics

## Support

For questions or issues:
- Check logs: `tail -f logs/combined.log`
- Query database: `SELECT * FROM email_processing_errors`
- Review metrics: `GET /api/email-automation/stats`

---

**You're now ready to automate email processing at scale!**
