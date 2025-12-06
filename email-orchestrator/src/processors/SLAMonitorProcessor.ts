/**
 * SLA Monitor Processor
 * Tracks email response times and prevents SLA breaches
 * Runs on every email to track response obligations
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { BaseEmailProcessor } from '../core/IEmailProcessor';
import { Email, ProcessingContext, ProcessingResult, SLAConfig, SLAStatus } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

export class SLAMonitorProcessor extends BaseEmailProcessor {
  readonly name = 'SLAMonitorProcessor';
  readonly priority = 90; // High priority - run early
  readonly description = 'Monitors email SLA compliance and escalates breaches';

  constructor(
    pool: Pool,
    logger: Logger,
    anthropic: Anthropic,
    templateService: EmailTemplateService,
    private readonly slaConfig: SLAConfig
  ) {
    super(pool, logger, anthropic, templateService);
  }

  async canProcess(email: Email): Promise<boolean> {
    // Monitor all inbound emails that require responses
    // Skip automated emails and internal emails
    const isAutomated = this.isAutomatedEmail(email);
    if (isAutomated) return false;

    // Check if email requires a response
    return this.requiresResponse(email);
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('SLA monitoring email', {
      emailId: email.id,
      from: email.from.address
    });

    try {
      // Determine email priority/SLA tier
      const priority = await this.determinePriority(email);

      // Calculate SLA deadline
      const slaDeadline = this.calculateDeadline(email.receivedDateTime, priority);

      // Create tracking record
      await this.createSLATracking(email, priority, slaDeadline, context);

      // Check for existing SLA breaches for this sender
      const existingBreaches = await this.checkExistingBreaches(email.from.address);

      let createdTasks: any[] = [];

      // If sender has pending unresponded emails, escalate
      if (existingBreaches.length > 0) {
        const taskId = await this.createEscalationTask(email, existingBreaches, context);
        createdTasks.push({
          id: taskId,
          title: `SLA Alert: Multiple pending from ${email.from.address}`,
          priority: 'critical'
        });
      }

      // Calculate hours until deadline
      const hoursRemaining = (slaDeadline.getTime() - Date.now()) / (1000 * 60 * 60);

      return this.successResult('sla_tracked', 0, {
        createdTasks,
        metadata: {
          priority,
          slaDeadline: slaDeadline.toISOString(),
          hoursRemaining: Math.round(hoursRemaining * 10) / 10,
          existingBreaches: existingBreaches.length
        }
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('SLA monitoring failed', { error: errorMessage });
      return this.failureResult('monitoring_error', errorMessage);
    }
  }

  /**
   * Check if email is automated
   */
  private isAutomatedEmail(email: Email): boolean {
    const automatedIndicators = [
      'noreply@', 'no-reply@', 'donotreply@', 'mailer-daemon',
      'postmaster', 'notification@', 'alerts@', 'automated'
    ];
    return automatedIndicators.some(ind =>
      email.from.address.toLowerCase().includes(ind)
    );
  }

  /**
   * Check if email requires a response
   */
  private requiresResponse(email: Email): boolean {
    const content = `${email.subject} ${email.bodyPreview}`.toLowerCase();

    // Questions or requests typically need responses
    const responseIndicators = [
      '?', 'please', 'can you', 'could you', 'would you',
      'need', 'help', 'question', 'wondering', 'request',
      'when', 'how', 'what', 'where', 'status', 'update'
    ];

    // Check if this seems like a one-way notification
    const noResponseIndicators = [
      'do not reply', 'this is an automated',
      'fyi', 'for your information', 'thank you for'
    ];

    if (noResponseIndicators.some(ind => content.includes(ind))) {
      return false;
    }

    return responseIndicators.some(ind => content.includes(ind));
  }

  /**
   * Determine email priority for SLA
   */
  private async determinePriority(email: Email): Promise<'critical' | 'high' | 'medium' | 'low'> {
    // Check if from VIP client
    const isVip = await this.isVipClient(email.from.address);
    if (isVip) return 'critical';

    // Check importance flag
    if (email.importance === 'high') return 'high';

    // Check for urgent keywords
    const content = `${email.subject} ${email.bodyPreview}`.toLowerCase();
    const urgentKeywords = [
      'urgent', 'asap', 'immediately', 'emergency',
      'time sensitive', 'deadline', 'closing today', 'closing tomorrow'
    ];

    if (urgentKeywords.some(kw => content.includes(kw))) {
      return 'high';
    }

    // Check if about an active loan near closing
    const hasActiveLoan = await this.hasActiveLoanNearClosing(email.from.address);
    if (hasActiveLoan) return 'high';

    return 'medium';
  }

  /**
   * Check if sender is a VIP client
   */
  private async isVipClient(email: string): Promise<boolean> {
    const result = await this.pool.query(
      `SELECT EXISTS(
         SELECT 1 FROM leads WHERE email = $1 AND is_vip = true
         UNION
         SELECT 1 FROM contacts WHERE email = $1 AND is_vip = true
       ) as is_vip`,
      [email.toLowerCase()]
    );
    return result.rows[0].is_vip;
  }

  /**
   * Check if sender has active loan near closing
   */
  private async hasActiveLoanNearClosing(email: string): Promise<boolean> {
    const result = await this.pool.query(
      `SELECT EXISTS(
         SELECT 1 FROM loans
         WHERE (borrower_email = $1 OR co_borrower_email = $1)
           AND status NOT IN ('funded', 'cancelled', 'denied')
           AND expected_close_date IS NOT NULL
           AND expected_close_date <= CURRENT_DATE + INTERVAL '14 days'
       ) as near_closing`,
      [email.toLowerCase()]
    );
    return result.rows[0].near_closing;
  }

  /**
   * Calculate SLA deadline based on priority
   */
  private calculateDeadline(
    receivedAt: Date,
    priority: 'critical' | 'high' | 'medium' | 'low'
  ): Date {
    const hours = this.slaConfig[priority];
    const deadline = new Date(receivedAt);
    deadline.setHours(deadline.getHours() + hours);

    // Skip weekends for non-critical
    if (priority !== 'critical') {
      const day = deadline.getDay();
      if (day === 0) deadline.setDate(deadline.getDate() + 1); // Sunday -> Monday
      if (day === 6) deadline.setDate(deadline.getDate() + 2); // Saturday -> Monday
    }

    return deadline;
  }

  /**
   * Create SLA tracking record
   */
  private async createSLATracking(
    email: Email,
    priority: string,
    deadline: Date,
    context: ProcessingContext
  ): Promise<void> {
    await this.pool.query(
      `INSERT INTO email_response_tracking
       (email_id, from_email, subject, received_at, sla_priority, sla_deadline,
        sla_status, assigned_to, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
       ON CONFLICT (email_id) DO UPDATE SET
         sla_priority = EXCLUDED.sla_priority,
         sla_deadline = EXCLUDED.sla_deadline,
         updated_at = NOW()`,
      [
        email.id,
        email.from.address,
        email.subject,
        email.receivedDateTime,
        priority,
        deadline,
        'pending',
        context.userId
      ]
    );
  }

  /**
   * Check for existing unresponded emails from sender
   */
  private async checkExistingBreaches(email: string): Promise<SLAStatus[]> {
    const result = await this.pool.query(
      `SELECT email_id, sla_priority, received_at, sla_deadline, sla_status
       FROM email_response_tracking
       WHERE from_email = $1
         AND sla_status IN ('pending', 'warning')
         AND responded_at IS NULL
         AND received_at < NOW() - INTERVAL '1 hour'
       ORDER BY received_at ASC`,
      [email.toLowerCase()]
    );

    return result.rows.map(row => ({
      emailId: row.email_id,
      priority: row.sla_priority,
      receivedAt: row.received_at,
      slaDeadline: row.sla_deadline,
      hoursRemaining: (new Date(row.sla_deadline).getTime() - Date.now()) / (1000 * 60 * 60),
      status: row.sla_status
    }));
  }

  /**
   * Create escalation task for SLA risk
   */
  private async createEscalationTask(
    email: Email,
    existingBreaches: SLAStatus[],
    context: ProcessingContext
  ): Promise<number> {
    const oldestPending = existingBreaches[0];
    const hoursPending = (Date.now() - new Date(oldestPending.receivedAt).getTime()) / (1000 * 60 * 60);

    const result = await this.pool.query(
      `INSERT INTO tasks
       (title, description, assigned_to, priority, status, due_date, category, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
       RETURNING id`,
      [
        `SLA ALERT: ${existingBreaches.length} pending emails from ${email.from.address}`,
        `This client has ${existingBreaches.length} unanswered email(s).\n` +
        `Oldest pending: ${Math.round(hoursPending)} hours\n` +
        `New email: "${email.subject}"\n\n` +
        `Immediate response required to avoid SLA breach.`,
        context.userId,
        'critical',
        'pending',
        new Date(Date.now() + 60 * 60 * 1000), // Due in 1 hour
        'sla_escalation'
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Static method to check and escalate breaches (called by cron)
   */
  static async checkAndEscalateBreaches(
    pool: Pool,
    logger: Logger
  ): Promise<{ checked: number; escalated: number }> {
    // Find emails approaching SLA deadline
    const warningResult = await pool.query(
      `UPDATE email_response_tracking
       SET sla_status = 'warning', updated_at = NOW()
       WHERE sla_status = 'pending'
         AND responded_at IS NULL
         AND sla_deadline <= NOW() + INTERVAL '30 minutes'
       RETURNING email_id`
    );

    // Find breached emails
    const breachedResult = await pool.query(
      `UPDATE email_response_tracking
       SET sla_status = 'breached', updated_at = NOW()
       WHERE sla_status IN ('pending', 'warning')
         AND responded_at IS NULL
         AND sla_deadline < NOW()
       RETURNING email_id, from_email, subject, assigned_to`
    );

    // Log breaches
    for (const breach of breachedResult.rows) {
      await pool.query(
        `INSERT INTO sla_breaches
         (email_id, from_email, subject, assigned_to, breach_time, hours_overdue)
         VALUES ($1, $2, $3, $4, NOW(),
           EXTRACT(EPOCH FROM (NOW() - (SELECT sla_deadline FROM email_response_tracking WHERE email_id = $1))) / 3600)`,
        [breach.email_id, breach.from_email, breach.subject, breach.assigned_to]
      );
    }

    const warningCount = warningResult.rowCount ?? 0;
    const breachCount = breachedResult.rowCount ?? 0;

    logger.info('SLA breach check completed', {
      warnings: warningCount,
      breaches: breachCount
    });

    return {
      checked: warningCount + breachCount,
      escalated: breachCount
    };
  }
}
