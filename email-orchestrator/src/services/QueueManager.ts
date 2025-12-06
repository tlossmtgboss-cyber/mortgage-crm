/**
 * Queue Manager
 * Manages email processing queue for batch operations
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import { QueuedEmail } from '../types';

export class QueueManager {
  constructor(
    private readonly pool: Pool,
    private readonly logger: Logger
  ) {}

  /**
   * Add email to processing queue
   */
  async enqueue(
    emailId: string,
    messageId: string,
    priority: number = 50
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO email_processing_queue
       (email_id, message_id, priority, status, retry_count, created_at)
       VALUES ($1, $2, $3, 'pending', 0, NOW())
       ON CONFLICT (email_id) DO UPDATE SET
         priority = GREATEST(email_processing_queue.priority, EXCLUDED.priority),
         updated_at = NOW()
       RETURNING id`,
      [emailId, messageId, priority]
    );

    return result.rows[0].id;
  }

  /**
   * Get next batch of emails to process
   */
  async getNextBatch(limit: number = 10): Promise<QueuedEmail[]> {
    const result = await this.pool.query(
      `UPDATE email_processing_queue
       SET status = 'processing', updated_at = NOW()
       WHERE id IN (
         SELECT id FROM email_processing_queue
         WHERE status = 'pending'
           OR (status = 'retry' AND retry_count < 3)
         ORDER BY priority DESC, created_at ASC
         LIMIT $1
         FOR UPDATE SKIP LOCKED
       )
       RETURNING id, email_id, message_id, priority, status, retry_count, last_error, created_at, processed_at`,
      [limit]
    );

    return result.rows.map(row => ({
      id: row.id,
      emailId: row.email_id,
      messageId: row.message_id,
      priority: row.priority,
      status: row.status,
      retryCount: row.retry_count,
      lastError: row.last_error,
      createdAt: row.created_at,
      processedAt: row.processed_at
    }));
  }

  /**
   * Mark email as completed
   */
  async markCompleted(queueId: number): Promise<void> {
    await this.pool.query(
      `UPDATE email_processing_queue
       SET status = 'completed', processed_at = NOW(), updated_at = NOW()
       WHERE id = $1`,
      [queueId]
    );
  }

  /**
   * Mark email as failed
   */
  async markFailed(queueId: number, error: string): Promise<void> {
    await this.pool.query(
      `UPDATE email_processing_queue
       SET status = CASE WHEN retry_count >= 2 THEN 'failed' ELSE 'retry' END,
           retry_count = retry_count + 1,
           last_error = $2,
           updated_at = NOW()
       WHERE id = $1`,
      [queueId, error]
    );
  }

  /**
   * Get queue statistics
   */
  async getStats(): Promise<{
    pending: number;
    processing: number;
    completed: number;
    failed: number;
    retry: number;
  }> {
    const result = await this.pool.query(
      `SELECT status, COUNT(*) as count
       FROM email_processing_queue
       WHERE created_at >= CURRENT_DATE
       GROUP BY status`
    );

    const stats = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      retry: 0
    };

    for (const row of result.rows) {
      if (row.status in stats) {
        stats[row.status as keyof typeof stats] = parseInt(row.count);
      }
    }

    return stats;
  }

  /**
   * Clean up old completed items
   */
  async cleanup(daysToKeep: number = 7): Promise<number> {
    const result = await this.pool.query(
      `DELETE FROM email_processing_queue
       WHERE status = 'completed'
         AND processed_at < NOW() - INTERVAL '1 day' * $1
       RETURNING id`,
      [daysToKeep]
    );

    this.logger.info(`Cleaned up ${result.rowCount} old queue items`);
    return result.rowCount || 0;
  }

  /**
   * Reset stuck processing items
   */
  async resetStuck(stuckMinutes: number = 30): Promise<number> {
    const result = await this.pool.query(
      `UPDATE email_processing_queue
       SET status = 'retry',
           retry_count = retry_count + 1,
           last_error = 'Processing timeout - reset',
           updated_at = NOW()
       WHERE status = 'processing'
         AND updated_at < NOW() - INTERVAL '1 minute' * $1
       RETURNING id`,
      [stuckMinutes]
    );

    if (result.rowCount && result.rowCount > 0) {
      this.logger.warn(`Reset ${result.rowCount} stuck queue items`);
    }

    return result.rowCount || 0;
  }

  /**
   * Get failed items for review
   */
  async getFailedItems(limit: number = 50): Promise<QueuedEmail[]> {
    const result = await this.pool.query(
      `SELECT id, email_id, message_id, priority, status, retry_count, last_error, created_at, processed_at
       FROM email_processing_queue
       WHERE status = 'failed'
       ORDER BY created_at DESC
       LIMIT $1`,
      [limit]
    );

    return result.rows.map(row => ({
      id: row.id,
      emailId: row.email_id,
      messageId: row.message_id,
      priority: row.priority,
      status: row.status,
      retryCount: row.retry_count,
      lastError: row.last_error,
      createdAt: row.created_at,
      processedAt: row.processed_at
    }));
  }

  /**
   * Retry a specific failed item
   */
  async retryItem(queueId: number): Promise<void> {
    await this.pool.query(
      `UPDATE email_processing_queue
       SET status = 'pending',
           retry_count = 0,
           last_error = NULL,
           updated_at = NOW()
       WHERE id = $1`,
      [queueId]
    );
  }

  /**
   * Get queue status (alias for getStats with additional info)
   */
  async getQueueStatus(): Promise<{
    stats: {
      pending: number;
      processing: number;
      completed: number;
      failed: number;
      retry: number;
    };
    oldestPending: Date | null;
    recentErrors: string[];
  }> {
    const stats = await this.getStats();

    const oldestResult = await this.pool.query(
      `SELECT MIN(created_at) as oldest
       FROM email_processing_queue
       WHERE status = 'pending'`
    );

    const errorsResult = await this.pool.query(
      `SELECT DISTINCT last_error
       FROM email_processing_queue
       WHERE status = 'failed' AND last_error IS NOT NULL
       ORDER BY last_error
       LIMIT 5`
    );

    return {
      stats,
      oldestPending: oldestResult.rows[0]?.oldest || null,
      recentErrors: errorsResult.rows.map(r => r.last_error),
    };
  }

  /**
   * Process a batch of queued emails
   */
  async processBatch(
    processor: (item: QueuedEmail) => Promise<any>,
    limit: number = 10
  ): Promise<number> {
    const batch = await this.getNextBatch(limit);
    let processed = 0;

    for (const item of batch) {
      try {
        await processor(item);
        await this.markCompleted(item.id);
        processed++;
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        await this.markFailed(item.id, errorMessage);
        this.logger.error('Failed to process queue item', {
          queueId: item.id,
          emailId: item.emailId,
          error: errorMessage,
        });
      }
    }

    return processed;
  }
}
