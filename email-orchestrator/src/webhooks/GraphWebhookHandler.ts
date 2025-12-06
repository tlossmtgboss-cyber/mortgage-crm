/**
 * Microsoft Graph Webhook Handler
 * Handles real-time email notifications from Microsoft Graph API
 */

import { Router, Request, Response } from 'express';
import { Logger } from 'winston';
import { Pool } from 'pg';
import { EmailOrchestrator } from '../core/EmailOrchestrator';
import { GraphEmailService } from '../services/GraphEmailService';
import { QueueManager } from '../services/QueueManager';
import { WebhookPayload, WebhookNotification } from '../types';

export function createWebhookHandler(
  orchestrator: EmailOrchestrator,
  graphService: GraphEmailService,
  queueManager: QueueManager,
  pool: Pool,
  logger: Logger,
  webhookSecret: string
): Router {
  const router = Router();

  /**
   * Webhook validation endpoint
   * Microsoft Graph sends a validation request when creating subscription
   */
  router.post('/graph', async (req: Request, res: Response) => {
    // Handle subscription validation
    if (req.query.validationToken) {
      logger.info('Webhook validation request received');
      res.contentType('text/plain');
      return res.send(req.query.validationToken);
    }

    // Verify client state
    const notifications = req.body as WebhookPayload;
    if (!notifications.value || notifications.value.length === 0) {
      logger.warn('Empty webhook notification received');
      return res.sendStatus(202);
    }

    // Verify client state matches
    const firstNotification = notifications.value[0];
    if (firstNotification.clientState !== webhookSecret) {
      logger.error('Invalid webhook client state', {
        received: firstNotification.clientState
      });
      return res.sendStatus(401);
    }

    // Acknowledge receipt immediately (Microsoft expects fast response)
    res.sendStatus(202);

    // Process notifications asynchronously
    processNotifications(notifications.value, orchestrator, graphService, queueManager, logger)
      .catch(error => {
        logger.error('Failed to process webhook notifications', { error });
      });
  });

  /**
   * Health check endpoint
   */
  router.get('/health', (req: Request, res: Response) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  return router;
}

/**
 * Process incoming webhook notifications
 */
async function processNotifications(
  notifications: WebhookNotification[],
  orchestrator: EmailOrchestrator,
  graphService: GraphEmailService,
  queueManager: QueueManager,
  logger: Logger
): Promise<void> {
  for (const notification of notifications) {
    try {
      // Only process created emails
      if (notification.changeType !== 'created') {
        continue;
      }

      // Extract email ID from resource
      const emailId = notification.resourceData.id;

      logger.info('Processing webhook notification', {
        emailId,
        subscriptionId: notification.subscriptionId
      });

      // Add to queue for processing
      await queueManager.enqueue(emailId, emailId, 50);

      // Optionally process immediately for high-priority handling
      // Uncomment to enable immediate processing:
      /*
      const email = await graphService.getEmail(emailId);
      if (email.importance === 'high') {
        await orchestrator.processEmail(email, 1, 'system');
      }
      */

    } catch (error) {
      logger.error('Failed to process notification', {
        error: error instanceof Error ? error.message : String(error),
        notification
      });
    }
  }
}

/**
 * Subscription management
 */
export class WebhookSubscriptionManager {
  private subscriptionId: string | null = null;
  private renewalTimer: NodeJS.Timeout | null = null;

  constructor(
    private readonly graphService: GraphEmailService,
    private readonly pool: Pool,
    private readonly logger: Logger,
    private readonly webhookUrl: string
  ) {}

  /**
   * Create or renew subscription
   */
  async ensureSubscription(): Promise<string> {
    try {
      // Check for existing subscription in database
      const existing = await this.pool.query(
        `SELECT subscription_id, expiration_datetime
         FROM webhook_subscriptions
         WHERE resource = '/me/mailFolders/inbox/messages'
           AND expiration_datetime > NOW() + INTERVAL '1 hour'
         ORDER BY expiration_datetime DESC
         LIMIT 1`
      );

      if (existing.rows.length > 0) {
        const existingSubscriptionId: string = existing.rows[0].subscription_id;
        this.subscriptionId = existingSubscriptionId;
        this.scheduleRenewal(new Date(existing.rows[0].expiration_datetime));
        this.logger.info('Using existing subscription', {
          subscriptionId: existingSubscriptionId
        });
        return existingSubscriptionId;
      }

      // Create new subscription
      const newSubscriptionId = await this.graphService.createSubscription(this.webhookUrl);
      this.subscriptionId = newSubscriptionId;

      // Store in database
      await this.pool.query(
        `INSERT INTO webhook_subscriptions
         (subscription_id, resource, change_type, notification_url, expiration_datetime, client_state)
         VALUES ($1, $2, $3, $4, NOW() + INTERVAL '3 days', $5)
         ON CONFLICT (subscription_id) DO UPDATE SET
           expiration_datetime = NOW() + INTERVAL '3 days',
           renewed_at = NOW()`,
        [
          newSubscriptionId,
          '/me/mailFolders/inbox/messages',
          'created',
          this.webhookUrl,
          process.env.WEBHOOK_SECRET || 'perennia-email-orchestrator'
        ]
      );

      // Schedule renewal
      const expirationDate = new Date();
      expirationDate.setDate(expirationDate.getDate() + 3);
      this.scheduleRenewal(expirationDate);

      return newSubscriptionId;
    } catch (error) {
      this.logger.error('Failed to ensure subscription', { error });
      throw error;
    }
  }

  /**
   * Schedule subscription renewal
   */
  private scheduleRenewal(expirationDate: Date): void {
    if (this.renewalTimer) {
      clearTimeout(this.renewalTimer);
    }

    // Renew 2 hours before expiration
    const renewalTime = expirationDate.getTime() - (2 * 60 * 60 * 1000);
    const delay = Math.max(renewalTime - Date.now(), 0);

    this.renewalTimer = setTimeout(async () => {
      try {
        await this.renewSubscription();
      } catch (error) {
        this.logger.error('Scheduled renewal failed', { error });
        // Retry in 5 minutes
        setTimeout(() => this.ensureSubscription(), 5 * 60 * 1000);
      }
    }, delay);

    this.logger.info('Subscription renewal scheduled', {
      renewalAt: new Date(Date.now() + delay).toISOString()
    });
  }

  /**
   * Renew existing subscription
   */
  private async renewSubscription(): Promise<void> {
    if (!this.subscriptionId) {
      await this.ensureSubscription();
      return;
    }

    await this.graphService.renewSubscription(this.subscriptionId);

    // Update database
    await this.pool.query(
      `UPDATE webhook_subscriptions
       SET expiration_datetime = NOW() + INTERVAL '3 days',
           renewed_at = NOW()
       WHERE subscription_id = $1`,
      [this.subscriptionId]
    );

    // Schedule next renewal
    const expirationDate = new Date();
    expirationDate.setDate(expirationDate.getDate() + 3);
    this.scheduleRenewal(expirationDate);

    this.logger.info('Subscription renewed', { subscriptionId: this.subscriptionId });
  }

  /**
   * Stop subscription management
   */
  stop(): void {
    if (this.renewalTimer) {
      clearTimeout(this.renewalTimer);
      this.renewalTimer = null;
    }
  }
}
