/**
 * Metrics Collector
 * Tracks performance metrics, time savings, and processing statistics
 */

import { Pool } from 'pg';
import { Logger } from 'winston';

export interface ProcessorMetrics {
  processorName: string;
  totalRuns: number;
  successCount: number;
  failureCount: number;
  avgProcessingTimeMs: number;
  totalTimeSavedMinutes: number;
  lastRunAt: Date | null;
}

export interface DailyMetrics {
  date: Date;
  totalEmails: number;
  processedCount: number;
  autoRespondedCount: number;
  timeSavedMinutes: number;
  avgProcessingTimeSeconds: number;
  slaComplianceRate: number;
}

export interface TimeSavingsEntry {
  processorName: string;
  emailId: string;
  timeSavedMinutes: number;
  action: string;
  triggeredAt: Date;
}

export class MetricsCollector {
  constructor(
    private readonly pool: Pool,
    private readonly logger: Logger
  ) {}

  /**
   * Track time saved by a processor
   */
  async trackTimeSaved(
    processorName: string,
    emailId: string,
    timeSavedMinutes: number,
    action: string
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO automation_time_savings
         (processor_name, email_id, time_saved_minutes, action, triggered_at)
         VALUES ($1, $2, $3, $4, NOW())`,
        [processorName, emailId, timeSavedMinutes, action]
      );

      this.logger.debug('Time savings tracked', {
        processorName,
        emailId,
        timeSavedMinutes,
        action
      });
    } catch (error) {
      this.logger.error('Failed to track time savings', { error, processorName, emailId });
    }
  }

  /**
   * Record processor performance
   */
  async recordProcessorRun(
    processorName: string,
    success: boolean,
    processingTimeMs: number,
    timeSavedMinutes: number = 0
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO processor_performance
         (processor_name, date, total_runs, success_count, failure_count,
          avg_processing_time_ms, time_saved_minutes)
         VALUES ($1, CURRENT_DATE, 1, $2, $3, $4, $5)
         ON CONFLICT (processor_name, date) DO UPDATE SET
           total_runs = processor_performance.total_runs + 1,
           success_count = processor_performance.success_count + EXCLUDED.success_count,
           failure_count = processor_performance.failure_count + EXCLUDED.failure_count,
           avg_processing_time_ms = (
             (processor_performance.avg_processing_time_ms * processor_performance.total_runs + $4) /
             (processor_performance.total_runs + 1)
           ),
           time_saved_minutes = processor_performance.time_saved_minutes + EXCLUDED.time_saved_minutes,
           updated_at = NOW()`,
        [
          processorName,
          success ? 1 : 0,
          success ? 0 : 1,
          processingTimeMs,
          timeSavedMinutes
        ]
      );
    } catch (error) {
      this.logger.error('Failed to record processor run', { error, processorName });
    }
  }

  /**
   * Get processor metrics for a time period
   */
  async getProcessorMetrics(
    processorName?: string,
    days: number = 30
  ): Promise<ProcessorMetrics[]> {
    const params: any[] = [days];
    let whereClause = '';

    if (processorName) {
      whereClause = 'AND processor_name = $2';
      params.push(processorName);
    }

    const result = await this.pool.query(
      `SELECT
         processor_name,
         SUM(total_runs) as total_runs,
         SUM(success_count) as success_count,
         SUM(failure_count) as failure_count,
         AVG(avg_processing_time_ms) as avg_processing_time_ms,
         SUM(time_saved_minutes) as time_saved_minutes,
         MAX(updated_at) as last_run_at
       FROM processor_performance
       WHERE date >= CURRENT_DATE - $1
       ${whereClause}
       GROUP BY processor_name
       ORDER BY total_runs DESC`,
      params
    );

    return result.rows.map(row => ({
      processorName: row.processor_name,
      totalRuns: parseInt(row.total_runs) || 0,
      successCount: parseInt(row.success_count) || 0,
      failureCount: parseInt(row.failure_count) || 0,
      avgProcessingTimeMs: parseFloat(row.avg_processing_time_ms) || 0,
      totalTimeSavedMinutes: parseFloat(row.time_saved_minutes) || 0,
      lastRunAt: row.last_run_at
    }));
  }

  /**
   * Get daily metrics summary
   */
  async getDailyMetrics(days: number = 7): Promise<DailyMetrics[]> {
    const result = await this.pool.query(
      `SELECT
         date,
         total_received,
         total_processed,
         total_auto_responded,
         time_saved_minutes,
         sla_compliance_rate,
         COALESCE(
           (SELECT AVG(EXTRACT(EPOCH FROM (processed_at - received_at)))
            FROM email_tracking
            WHERE DATE(received_at) = eps.date AND processed_at IS NOT NULL),
           0
         ) as avg_processing_time_seconds
       FROM email_processing_summary eps
       WHERE date >= CURRENT_DATE - $1
       ORDER BY date DESC`,
      [days]
    );

    return result.rows.map(row => ({
      date: row.date,
      totalEmails: parseInt(row.total_received) || 0,
      processedCount: parseInt(row.total_processed) || 0,
      autoRespondedCount: parseInt(row.total_auto_responded) || 0,
      timeSavedMinutes: parseFloat(row.time_saved_minutes) || 0,
      avgProcessingTimeSeconds: parseFloat(row.avg_processing_time_seconds) || 0,
      slaComplianceRate: parseFloat(row.sla_compliance_rate) || 100
    }));
  }

  /**
   * Get total time saved
   */
  async getTotalTimeSaved(days: number = 30): Promise<{
    totalMinutes: number;
    totalHours: number;
    byProcessor: { name: string; minutes: number }[];
  }> {
    const result = await this.pool.query(
      `SELECT
         processor_name,
         SUM(time_saved_minutes) as minutes
       FROM automation_time_savings
       WHERE triggered_at >= CURRENT_DATE - $1
       GROUP BY processor_name
       ORDER BY minutes DESC`,
      [days]
    );

    const byProcessor = result.rows.map(row => ({
      name: row.processor_name,
      minutes: parseFloat(row.minutes) || 0
    }));

    const totalMinutes = byProcessor.reduce((sum, p) => sum + p.minutes, 0);

    return {
      totalMinutes,
      totalHours: Math.round(totalMinutes / 60 * 10) / 10,
      byProcessor
    };
  }

  /**
   * Get processing statistics
   */
  async getStatistics(days: number = 1): Promise<{
    totalEmails: number;
    processedCount: number;
    errorCount: number;
    avgProcessingTimeSeconds: number;
    slaComplianceRate: number;
  }> {
    const result = await this.pool.query(
      `SELECT
         COUNT(*) as total_emails,
         COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed_count,
         COUNT(CASE WHEN status = 'failed' THEN 1 END) as error_count,
         AVG(
           CASE WHEN processed_at IS NOT NULL
           THEN EXTRACT(EPOCH FROM (processed_at - received_at))
           END
         ) as avg_processing_time_seconds
       FROM email_tracking
       WHERE received_at >= CURRENT_DATE - $1`,
      [days]
    );

    const slaResult = await this.pool.query(
      `SELECT
         COUNT(*) as total,
         COUNT(CASE WHEN sla_status IN ('ok', 'pending') THEN 1 END) as compliant
       FROM email_response_tracking
       WHERE received_at >= CURRENT_DATE - $1`,
      [days]
    );

    const stats = result.rows[0];
    const sla = slaResult.rows[0];

    const slaComplianceRate = sla.total > 0
      ? (parseInt(sla.compliant) / parseInt(sla.total)) * 100
      : 100;

    return {
      totalEmails: parseInt(stats.total_emails) || 0,
      processedCount: parseInt(stats.processed_count) || 0,
      errorCount: parseInt(stats.error_count) || 0,
      avgProcessingTimeSeconds: parseFloat(stats.avg_processing_time_seconds) || 0,
      slaComplianceRate: Math.round(slaComplianceRate * 10) / 10
    };
  }

  /**
   * Get recent time savings entries
   */
  async getRecentTimeSavings(limit: number = 50): Promise<TimeSavingsEntry[]> {
    const result = await this.pool.query(
      `SELECT processor_name, email_id, time_saved_minutes, action, triggered_at
       FROM automation_time_savings
       ORDER BY triggered_at DESC
       LIMIT $1`,
      [limit]
    );

    return result.rows.map(row => ({
      processorName: row.processor_name,
      emailId: row.email_id,
      timeSavedMinutes: parseInt(row.time_saved_minutes) || 0,
      action: row.action,
      triggeredAt: row.triggered_at
    }));
  }

  /**
   * Generate metrics report
   */
  async generateReport(days: number = 7): Promise<{
    summary: {
      totalEmails: number;
      totalProcessed: number;
      successRate: number;
      totalTimeSavedHours: number;
      avgProcessingTimeMs: number;
    };
    byProcessor: ProcessorMetrics[];
    dailyTrend: DailyMetrics[];
  }> {
    const [processors, daily, timeSaved, stats] = await Promise.all([
      this.getProcessorMetrics(undefined, days),
      this.getDailyMetrics(days),
      this.getTotalTimeSaved(days),
      this.getStatistics(days)
    ]);

    const totalRuns = processors.reduce((sum, p) => sum + p.totalRuns, 0);
    const successCount = processors.reduce((sum, p) => sum + p.successCount, 0);
    const avgTime = processors.reduce((sum, p) => sum + p.avgProcessingTimeMs, 0) / (processors.length || 1);

    return {
      summary: {
        totalEmails: stats.totalEmails,
        totalProcessed: stats.processedCount,
        successRate: totalRuns > 0 ? (successCount / totalRuns) * 100 : 100,
        totalTimeSavedHours: timeSaved.totalHours,
        avgProcessingTimeMs: Math.round(avgTime)
      },
      byProcessor: processors,
      dailyTrend: daily
    };
  }
}
