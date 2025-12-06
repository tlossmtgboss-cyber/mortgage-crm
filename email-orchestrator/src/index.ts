/**
 * Email Orchestrator - Main Entry Point
 * Express server with webhook handling and scheduled jobs
 */

import express, { Express, Request, Response, NextFunction } from 'express';
import { Pool } from 'pg';
import winston from 'winston';
import cron from 'node-cron';
import dotenv from 'dotenv';

import { initializeEmailOrchestrator, InitializationResult } from './init';
import { createWebhookHandler, WebhookSubscriptionManager } from './webhooks/GraphWebhookHandler';

// Load environment variables
dotenv.config();

// Configuration
const PORT = parseInt(process.env.PORT || '3000', 10);
const NODE_ENV = process.env.NODE_ENV || 'development';

// Logger setup
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'email-orchestrator' },
  transports: [
    new winston.transports.Console({
      format: NODE_ENV === 'development'
        ? winston.format.combine(
            winston.format.colorize(),
            winston.format.simple()
          )
        : winston.format.json()
    }),
  ],
});

if (NODE_ENV === 'production') {
  logger.add(new winston.transports.File({ filename: 'logs/error.log', level: 'error' }));
  logger.add(new winston.transports.File({ filename: 'logs/combined.log' }));
}

// Database pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});

// Validate required environment variables
function validateEnvironment(): void {
  const required = [
    'DATABASE_URL',
    'GRAPH_ACCESS_TOKEN',
    'SENDER_EMAIL',
    'ANTHROPIC_API_KEY',
  ];

  const missing = required.filter(key => !process.env[key]);
  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }
}

// Create Express app
function createApp(result: InitializationResult, subscriptionManager: WebhookSubscriptionManager): Express {
  const app = express();

  // Middleware
  app.use(express.json({ limit: '10mb' }));
  app.use(express.urlencoded({ extended: true }));

  // Request logging
  app.use((req: Request, res: Response, next: NextFunction) => {
    const start = Date.now();
    res.on('finish', () => {
      const duration = Date.now() - start;
      logger.info('HTTP Request', {
        method: req.method,
        path: req.path,
        status: res.statusCode,
        duration: `${duration}ms`,
      });
    });
    next();
  });

  // Health check
  app.get('/health', async (req: Request, res: Response) => {
    try {
      await pool.query('SELECT 1');
      res.json({
        status: 'healthy',
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        environment: NODE_ENV,
      });
    } catch (error) {
      res.status(503).json({
        status: 'unhealthy',
        error: error instanceof Error ? error.message : 'Database connection failed',
      });
    }
  });

  // Metrics endpoint
  app.get('/metrics', async (req: Request, res: Response) => {
    try {
      const metrics = await getMetrics();
      res.json(metrics);
    } catch (error) {
      logger.error('Failed to get metrics', { error });
      res.status(500).json({ error: 'Failed to retrieve metrics' });
    }
  });

  // Webhook routes
  const webhookHandler = createWebhookHandler(
    result.orchestrator,
    result.graphService,
    result.queueManager,
    pool,
    logger,
    process.env.WEBHOOK_SECRET || 'perennia-email-orchestrator'
  );
  app.use('/webhooks', webhookHandler);

  // API routes
  app.get('/api/status', async (req: Request, res: Response) => {
    try {
      const summary = await result.summaryBot.generateDailySummary();
      res.json({
        date: summary.date,
        emailsReceived: summary.totalEmailsReceived,
        emailsProcessed: summary.totalEmailsProcessed,
        timeSavedMinutes: summary.totalTimeSavedMinutes,
        slaCompliance: summary.slaCompliance,
        pendingItems: summary.pendingItems,
      });
    } catch (error) {
      logger.error('Failed to get status', { error });
      res.status(500).json({ error: 'Failed to retrieve status' });
    }
  });

  // Manual trigger for email processing
  app.post('/api/process', async (req: Request, res: Response) => {
    const { emailId } = req.body;

    if (!emailId) {
      return res.status(400).json({ error: 'emailId is required' });
    }

    try {
      const email = await result.graphService.getEmail(emailId);
      const processingResult = await result.orchestrator.processEmail(email, 1, 'manual');
      res.json({
        success: true,
        results: processingResult,
      });
    } catch (error) {
      logger.error('Manual processing failed', { error, emailId });
      res.status(500).json({ error: 'Processing failed' });
    }
  });

  // Queue management
  app.get('/api/queue/status', async (req: Request, res: Response) => {
    try {
      const status = await result.queueManager.getQueueStatus();
      res.json(status);
    } catch (error) {
      logger.error('Failed to get queue status', { error });
      res.status(500).json({ error: 'Failed to retrieve queue status' });
    }
  });

  app.post('/api/queue/process', async (req: Request, res: Response) => {
    const limit = parseInt(req.query.limit as string) || 10;

    try {
      const processed = await result.queueManager.processBatch(
        async (item) => {
          const email = await result.graphService.getEmail(item.emailId);
          return result.orchestrator.processEmail(email, 1, 'batch');
        },
        limit
      );
      res.json({ processed });
    } catch (error) {
      logger.error('Batch processing failed', { error });
      res.status(500).json({ error: 'Batch processing failed' });
    }
  });

  // Summary email trigger
  app.post('/api/summary/send', async (req: Request, res: Response) => {
    const { recipients } = req.body;

    if (!recipients || !Array.isArray(recipients)) {
      return res.status(400).json({ error: 'recipients array is required' });
    }

    try {
      await result.summaryBot.sendDailySummary(recipients);
      res.json({ success: true, message: 'Summary sent' });
    } catch (error) {
      logger.error('Failed to send summary', { error });
      res.status(500).json({ error: 'Failed to send summary' });
    }
  });

  // Error handling middleware
  app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
    logger.error('Unhandled error', {
      error: err.message,
      stack: err.stack,
      path: req.path,
      method: req.method,
    });
    res.status(500).json({ error: 'Internal server error' });
  });

  // 404 handler
  app.use((req: Request, res: Response) => {
    res.status(404).json({ error: 'Not found' });
  });

  return app;
}

// Get metrics from database
async function getMetrics(): Promise<object> {
  const today = await pool.query(`
    SELECT
      COUNT(*) as emails_today,
      COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed_today,
      COALESCE(SUM(total_time_saved_minutes), 0) as time_saved_today
    FROM email_tracking
    WHERE received_at >= CURRENT_DATE
  `);

  const sla = await pool.query(`
    SELECT
      COUNT(*) as total,
      COUNT(CASE WHEN sla_status = 'ok' THEN 1 END) as on_time,
      COUNT(CASE WHEN sla_status = 'breached' THEN 1 END) as breached
    FROM email_response_tracking
    WHERE received_at >= CURRENT_DATE
  `);

  const queue = await pool.query(`
    SELECT
      COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
      COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
    FROM email_processing_queue
  `);

  return {
    timestamp: new Date().toISOString(),
    today: today.rows[0],
    sla: sla.rows[0],
    queue: queue.rows[0],
  };
}

// Setup scheduled jobs
function setupCronJobs(result: InitializationResult): void {
  // Process queue every 5 minutes
  cron.schedule('*/5 * * * *', async () => {
    logger.info('Running scheduled queue processing');
    try {
      const processed = await result.queueManager.processBatch(
        async (item) => {
          const email = await result.graphService.getEmail(item.emailId);
          return result.orchestrator.processEmail(email, 1, 'scheduled');
        },
        20
      );
      logger.info('Scheduled processing complete', { processed });
    } catch (error) {
      logger.error('Scheduled processing failed', { error });
    }
  });

  // SLA check every hour
  cron.schedule('0 * * * *', async () => {
    logger.info('Running SLA check');
    try {
      const breaches = await pool.query(`
        SELECT COUNT(*) as count
        FROM email_response_tracking
        WHERE sla_status = 'pending'
          AND sla_deadline < NOW()
      `);

      if (breaches.rows[0].count > 0) {
        logger.warn('SLA breaches detected', { count: breaches.rows[0].count });
      }
    } catch (error) {
      logger.error('SLA check failed', { error });
    }
  });

  // Daily summary at 6 PM
  cron.schedule('0 18 * * 1-5', async () => {
    logger.info('Sending daily summary');
    const summaryRecipients = process.env.SUMMARY_RECIPIENTS?.split(',') || [];

    if (summaryRecipients.length > 0) {
      try {
        await result.summaryBot.sendDailySummary(summaryRecipients);
        logger.info('Daily summary sent', { recipients: summaryRecipients.length });
      } catch (error) {
        logger.error('Failed to send daily summary', { error });
      }
    }
  });

  // Cleanup old records weekly
  cron.schedule('0 2 * * 0', async () => {
    logger.info('Running weekly cleanup');
    try {
      await pool.query(`
        DELETE FROM email_processing_log WHERE created_at < NOW() - INTERVAL '90 days';
        DELETE FROM email_processing_errors WHERE created_at < NOW() - INTERVAL '30 days';
        DELETE FROM email_processing_queue WHERE status = 'completed' AND processed_at < NOW() - INTERVAL '7 days';
      `);
      logger.info('Weekly cleanup complete');
    } catch (error) {
      logger.error('Weekly cleanup failed', { error });
    }
  });
}

// Graceful shutdown
function setupGracefulShutdown(server: any, subscriptionManager: WebhookSubscriptionManager): void {
  const shutdown = async (signal: string) => {
    logger.info(`Received ${signal}, starting graceful shutdown`);

    // Stop accepting new connections
    server.close(() => {
      logger.info('HTTP server closed');
    });

    // Stop subscription manager
    subscriptionManager.stop();

    // Close database pool
    await pool.end();
    logger.info('Database connections closed');

    process.exit(0);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

// Main startup
async function main(): Promise<void> {
  try {
    logger.info('Starting Email Orchestrator', { environment: NODE_ENV });

    // Validate environment
    validateEnvironment();

    // Test database connection
    await pool.query('SELECT 1');
    logger.info('Database connected');

    // Initialize orchestrator
    const result = await initializeEmailOrchestrator(
      {
        graphAccessToken: process.env.GRAPH_ACCESS_TOKEN!,
        senderEmail: process.env.SENDER_EMAIL!,
        anthropicApiKey: process.env.ANTHROPIC_API_KEY!,
        internalDomains: process.env.INTERNAL_DOMAINS?.split(',') || [],
        enableAutoResponses: process.env.ENABLE_AUTO_RESPONSES !== 'false',
        enableLoanCreation: process.env.ENABLE_LOAN_CREATION !== 'false',
        enableInvoiceProcessing: process.env.ENABLE_INVOICE_PROCESSING !== 'false',
        enableSlaMonitoring: process.env.ENABLE_SLA_MONITORING !== 'false',
        accountingEmail: process.env.ACCOUNTING_EMAIL,
      },
      pool,
      logger
    );

    // Setup webhook subscription manager
    const webhookUrl = process.env.WEBHOOK_URL || `http://localhost:${PORT}/webhooks/graph`;
    const subscriptionManager = new WebhookSubscriptionManager(
      result.graphService,
      pool,
      logger,
      webhookUrl
    );

    // Create and start server
    const app = createApp(result, subscriptionManager);
    const server = app.listen(PORT, () => {
      logger.info(`Server listening on port ${PORT}`);
    });

    // Setup cron jobs
    setupCronJobs(result);

    // Setup graceful shutdown
    setupGracefulShutdown(server, subscriptionManager);

    // Ensure webhook subscription (for production)
    if (NODE_ENV === 'production') {
      try {
        await subscriptionManager.ensureSubscription();
        logger.info('Webhook subscription active');
      } catch (error) {
        logger.error('Failed to setup webhook subscription', { error });
      }
    }

    logger.info('Email Orchestrator started successfully');

  } catch (error) {
    logger.error('Failed to start Email Orchestrator', { error });
    process.exit(1);
  }
}

// Run
main();
