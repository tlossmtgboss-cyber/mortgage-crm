/**
 * Email Orchestrator - Core orchestration engine
 * Implements Observer pattern for routing emails to processors
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import { v4 as uuidv4 } from 'uuid';
import { IEmailProcessor } from './IEmailProcessor';
import {
  Email,
  ProcessingContext,
  ProcessingResult,
  OrchestratorConfig,
  ProcessorStats
} from '../types';
import { RetryManager } from '../utils/RetryManager';

export class EmailOrchestrator {
  private processors: Map<string, IEmailProcessor> = new Map();
  private retryManager: RetryManager;
  private processingStats: Map<string, ProcessorStats> = new Map();

  constructor(
    private readonly pool: Pool,
    private readonly logger: Logger,
    private readonly config: OrchestratorConfig
  ) {
    this.retryManager = new RetryManager(config.retryConfig, logger);
    this.logger.info('EmailOrchestrator initialized', {
      internalDomains: config.internalDomains
    });
  }

  /**
   * Register a processor with the orchestrator
   */
  registerProcessor(name: string, processor: IEmailProcessor): void {
    this.processors.set(name, processor);
    this.processingStats.set(name, {
      name,
      totalRuns: 0,
      successCount: 0,
      failureCount: 0,
      avgProcessingTimeMs: 0,
      totalTimeSavedMinutes: 0
    });
    this.logger.info(`Processor registered: ${name}`, {
      priority: processor.priority,
      description: processor.description
    });
  }

  /**
   * Unregister a processor
   */
  unregisterProcessor(name: string): boolean {
    const removed = this.processors.delete(name);
    if (removed) {
      this.logger.info(`Processor unregistered: ${name}`);
    }
    return removed;
  }

  /**
   * Get all registered processors sorted by priority (highest first)
   */
  getProcessors(): IEmailProcessor[] {
    return Array.from(this.processors.values())
      .sort((a, b) => b.priority - a.priority);
  }

  /**
   * Process a single email through all applicable processors
   */
  async processEmail(
    email: Email,
    userId: number,
    userEmail: string
  ): Promise<ProcessingResult[]> {
    const correlationId = uuidv4();
    const context: ProcessingContext = {
      userId,
      userEmail,
      timestamp: new Date(),
      correlationId,
      retryCount: 0,
      metadata: {}
    };

    this.logger.info('Processing email', {
      emailId: email.id,
      subject: email.subject,
      from: email.from.address,
      correlationId
    });

    const results: ProcessingResult[] = [];
    const sortedProcessors = this.getProcessors();

    // Track email in database
    await this.trackEmail(email, context);

    for (const processor of sortedProcessors) {
      try {
        // Check if processor can handle this email
        const canProcess = await processor.canProcess(email);

        if (canProcess) {
          this.logger.debug(`Processor ${processor.name} will process email`, {
            emailId: email.id,
            correlationId
          });

          // Process with retry logic
          const startTime = Date.now();
          const result = await this.retryManager.executeWithRetry(
            () => processor.process(email, context),
            `${processor.name}:${email.id}`
          );
          const processingTime = Date.now() - startTime;

          // Update stats
          this.updateProcessorStats(processor.name, result, processingTime);

          results.push(result);

          this.logger.info(`Processor ${processor.name} completed`, {
            emailId: email.id,
            success: result.success,
            action: result.action,
            timeSaved: result.timeSaved,
            processingTimeMs: processingTime,
            correlationId
          });

          // Log to database
          await this.logProcessingResult(email, processor.name, result, context);
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        this.logger.error(`Processor ${processor.name} failed`, {
          emailId: email.id,
          error: errorMessage,
          correlationId
        });

        // Log error to database
        await this.logProcessingError(email, processor.name, errorMessage, context);

        results.push({
          success: false,
          processor: processor.name,
          action: 'error',
          timeSaved: 0,
          error: errorMessage
        });
      }
    }

    // Update email tracking status
    await this.updateEmailStatus(email.id, results);

    return results;
  }

  /**
   * Process a batch of emails
   */
  async processBatch(
    emails: Email[],
    userId: number,
    userEmail: string
  ): Promise<Map<string, ProcessingResult[]>> {
    const results = new Map<string, ProcessingResult[]>();

    this.logger.info(`Processing batch of ${emails.length} emails`);

    for (const email of emails) {
      try {
        const emailResults = await this.processEmail(email, userId, userEmail);
        results.set(email.id, emailResults);
      } catch (error) {
        this.logger.error('Batch processing error for email', {
          emailId: email.id,
          error: error instanceof Error ? error.message : String(error)
        });
        results.set(email.id, [{
          success: false,
          processor: 'orchestrator',
          action: 'batch_error',
          timeSaved: 0,
          error: error instanceof Error ? error.message : String(error)
        }]);
      }
    }

    return results;
  }

  /**
   * Get processing statistics for all processors
   */
  getStats(): ProcessorStats[] {
    return Array.from(this.processingStats.values());
  }

  /**
   * Get statistics for a specific processor
   */
  getProcessorStats(name: string): ProcessorStats | undefined {
    return this.processingStats.get(name);
  }

  /**
   * Track incoming email in database
   */
  private async trackEmail(email: Email, context: ProcessingContext): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO email_tracking
         (email_id, message_id, conversation_id, subject, from_email, from_name,
          to_emails, received_at, has_attachments, importance, correlation_id, user_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
         ON CONFLICT (email_id) DO UPDATE SET
           updated_at = NOW()`,
        [
          email.id,
          email.messageId,
          email.conversationId,
          email.subject,
          email.from.address,
          email.from.name,
          JSON.stringify(email.to.map(t => t.address)),
          email.receivedDateTime,
          email.hasAttachments,
          email.importance,
          context.correlationId,
          context.userId
        ]
      );
    } catch (error) {
      this.logger.error('Failed to track email', { error, emailId: email.id });
    }
  }

  /**
   * Log processing result to database
   */
  private async logProcessingResult(
    email: Email,
    processorName: string,
    result: ProcessingResult,
    context: ProcessingContext
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO email_processing_log
         (email_id, processor_name, action, success, time_saved_minutes,
          created_records, sent_emails, created_tasks, metadata, correlation_id)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [
          email.id,
          processorName,
          result.action,
          result.success,
          result.timeSaved,
          JSON.stringify(result.createdRecords || []),
          JSON.stringify(result.sentEmails || []),
          JSON.stringify(result.createdTasks || []),
          JSON.stringify(result.metadata || {}),
          context.correlationId
        ]
      );

      // Also log time saved for analytics
      if (result.timeSaved > 0) {
        await this.pool.query(
          `INSERT INTO automation_time_savings
           (processor_name, email_id, time_saved_minutes, action, triggered_at)
           VALUES ($1, $2, $3, $4, NOW())`,
          [processorName, email.id, result.timeSaved, result.action]
        );
      }
    } catch (error) {
      this.logger.error('Failed to log processing result', { error, emailId: email.id });
    }
  }

  /**
   * Log processing error to database
   */
  private async logProcessingError(
    email: Email,
    processorName: string,
    error: string,
    context: ProcessingContext
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO email_processing_errors
         (email_id, processor_name, error_message, correlation_id, created_at)
         VALUES ($1, $2, $3, $4, NOW())`,
        [email.id, processorName, error, context.correlationId]
      );
    } catch (dbError) {
      this.logger.error('Failed to log processing error', { dbError, emailId: email.id });
    }
  }

  /**
   * Update email tracking status based on results
   */
  private async updateEmailStatus(
    emailId: string,
    results: ProcessingResult[]
  ): Promise<void> {
    const anySuccess = results.some(r => r.success);
    const allFailed = results.length > 0 && results.every(r => !r.success);
    const totalTimeSaved = results.reduce((sum, r) => sum + r.timeSaved, 0);

    const status = allFailed ? 'failed' : anySuccess ? 'processed' : 'no_match';

    try {
      await this.pool.query(
        `UPDATE email_tracking
         SET status = $1,
             processors_run = $2,
             total_time_saved_minutes = $3,
             processed_at = NOW(),
             updated_at = NOW()
         WHERE email_id = $4`,
        [
          status,
          results.length,
          totalTimeSaved,
          emailId
        ]
      );
    } catch (error) {
      this.logger.error('Failed to update email status', { error, emailId });
    }
  }

  /**
   * Update processor statistics
   */
  private updateProcessorStats(
    name: string,
    result: ProcessingResult,
    processingTimeMs: number
  ): void {
    const stats = this.processingStats.get(name);
    if (stats) {
      stats.totalRuns++;
      if (result.success) {
        stats.successCount++;
      } else {
        stats.failureCount++;
      }
      stats.totalTimeSavedMinutes += result.timeSaved;
      stats.avgProcessingTimeMs =
        (stats.avgProcessingTimeMs * (stats.totalRuns - 1) + processingTimeMs) /
        stats.totalRuns;
      stats.lastRunAt = new Date();
    }
  }
}
