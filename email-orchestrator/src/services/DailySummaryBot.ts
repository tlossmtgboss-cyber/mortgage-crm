/**
 * Daily Summary Bot
 * Generates and sends daily/weekly email processing summaries
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import { EmailTemplateService } from './EmailTemplateService';
import { DailySummary, ProcessorStats } from '../types';

export class DailySummaryBot {
  constructor(
    private readonly pool: Pool,
    private readonly templateService: EmailTemplateService,
    private readonly logger: Logger
  ) {}

  /**
   * Generate daily summary data
   */
  async generateDailySummary(date: Date = new Date()): Promise<DailySummary> {
    const startOfDay = new Date(date);
    startOfDay.setHours(0, 0, 0, 0);

    const endOfDay = new Date(date);
    endOfDay.setHours(23, 59, 59, 999);

    // Get email counts
    const emailStats = await this.pool.query(
      `SELECT
         COUNT(*) as total_received,
         COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed,
         COUNT(CASE WHEN processors_run > 0 THEN 1 END) as auto_handled,
         COALESCE(SUM(total_time_saved_minutes), 0) as time_saved
       FROM email_tracking
       WHERE received_at BETWEEN $1 AND $2`,
      [startOfDay, endOfDay]
    );

    // Get processor breakdown
    const processorStats = await this.pool.query(
      `SELECT
         processor_name,
         COUNT(*) as total_runs,
         COUNT(CASE WHEN success THEN 1 END) as success_count,
         COUNT(CASE WHEN NOT success THEN 1 END) as failure_count,
         AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER (PARTITION BY processor_name ORDER BY created_at)))) * 1000 as avg_time_ms,
         SUM(time_saved_minutes) as time_saved
       FROM email_processing_log
       WHERE created_at BETWEEN $1 AND $2
       GROUP BY processor_name
       ORDER BY total_runs DESC`,
      [startOfDay, endOfDay]
    );

    // Get SLA compliance
    const slaStats = await this.pool.query(
      `SELECT
         COUNT(*) as total,
         COUNT(CASE WHEN sla_status = 'ok' OR responded_at IS NOT NULL THEN 1 END) as on_time,
         COUNT(CASE WHEN sla_status = 'breached' THEN 1 END) as breached
       FROM email_response_tracking
       WHERE received_at BETWEEN $1 AND $2`,
      [startOfDay, endOfDay]
    );

    // Get top senders
    const topSenders = await this.pool.query(
      `SELECT from_email, COUNT(*) as count
       FROM email_tracking
       WHERE received_at BETWEEN $1 AND $2
       GROUP BY from_email
       ORDER BY count DESC
       LIMIT 5`,
      [startOfDay, endOfDay]
    );

    // Get pending items count
    const pendingResult = await this.pool.query(
      `SELECT COUNT(*) as pending
       FROM email_response_tracking
       WHERE sla_status IN ('pending', 'warning')
         AND responded_at IS NULL`
    );

    const stats = emailStats.rows[0];
    const sla = slaStats.rows[0];

    return {
      date,
      totalEmailsReceived: parseInt(stats.total_received) || 0,
      totalEmailsProcessed: parseInt(stats.processed) || 0,
      totalEmailsAutoResponded: parseInt(stats.auto_handled) || 0,
      totalTimeSavedMinutes: parseFloat(stats.time_saved) || 0,
      processorBreakdown: processorStats.rows.map(row => ({
        name: row.processor_name,
        totalRuns: parseInt(row.total_runs) || 0,
        successCount: parseInt(row.success_count) || 0,
        failureCount: parseInt(row.failure_count) || 0,
        avgProcessingTimeMs: parseFloat(row.avg_time_ms) || 0,
        totalTimeSavedMinutes: parseFloat(row.time_saved) || 0
      })),
      slaCompliance: {
        total: parseInt(sla.total) || 0,
        onTime: parseInt(sla.on_time) || 0,
        breached: parseInt(sla.breached) || 0,
        complianceRate: sla.total > 0
          ? (parseInt(sla.on_time) / parseInt(sla.total)) * 100
          : 100
      },
      topSenders: topSenders.rows.map(row => ({
        email: row.from_email,
        count: parseInt(row.count)
      })),
      pendingItems: parseInt(pendingResult.rows[0].pending) || 0
    };
  }

  /**
   * Send daily summary email
   */
  async sendDailySummary(
    recipients: string[],
    date: Date = new Date()
  ): Promise<void> {
    const summary = await this.generateDailySummary(date);

    const html = this.formatSummaryHtml(summary);

    await this.templateService.sendEmail(
      recipients,
      `Email Processing Summary - ${date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })}`,
      html,
      true
    );

    this.logger.info('Daily summary sent', { recipients, date });

    // Store summary in database
    await this.storeSummary(summary);
  }

  /**
   * Format summary as HTML
   */
  private formatSummaryHtml(summary: DailySummary): string {
    const timeSavedHours = (summary.totalTimeSavedMinutes / 60).toFixed(1);

    return `
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: #2563eb; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
    .content { background: #f9fafb; padding: 20px; border-radius: 0 0 8px 8px; }
    .stat-box { background: white; padding: 15px; border-radius: 8px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .stat-number { font-size: 28px; font-weight: bold; color: #2563eb; }
    .stat-label { color: #6b7280; font-size: 14px; }
    .section-title { font-size: 18px; font-weight: bold; margin-top: 20px; margin-bottom: 10px; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; }
    th, td { padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }
    th { background: #f3f4f6; }
    .success { color: #059669; }
    .warning { color: #d97706; }
    .danger { color: #dc2626; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 style="margin: 0;">Email Processing Summary</h1>
      <p style="margin: 5px 0 0 0; opacity: 0.9;">${summary.date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</p>
    </div>

    <div class="content">
      <div style="display: flex; gap: 15px; flex-wrap: wrap;">
        <div class="stat-box" style="flex: 1; min-width: 120px;">
          <div class="stat-number">${summary.totalEmailsReceived}</div>
          <div class="stat-label">Emails Received</div>
        </div>
        <div class="stat-box" style="flex: 1; min-width: 120px;">
          <div class="stat-number">${summary.totalEmailsProcessed}</div>
          <div class="stat-label">Processed</div>
        </div>
        <div class="stat-box" style="flex: 1; min-width: 120px;">
          <div class="stat-number success">${timeSavedHours}h</div>
          <div class="stat-label">Time Saved</div>
        </div>
      </div>

      <div class="section-title">SLA Compliance</div>
      <div class="stat-box">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>Response Rate</span>
          <span class="${summary.slaCompliance.complianceRate >= 95 ? 'success' : summary.slaCompliance.complianceRate >= 80 ? 'warning' : 'danger'}" style="font-size: 24px; font-weight: bold;">
            ${summary.slaCompliance.complianceRate.toFixed(1)}%
          </span>
        </div>
        <div style="margin-top: 10px; font-size: 14px; color: #6b7280;">
          ${summary.slaCompliance.onTime} on-time | ${summary.slaCompliance.breached} breached | ${summary.pendingItems} pending
        </div>
      </div>

      <div class="section-title">Processor Performance</div>
      <table>
        <tr>
          <th>Processor</th>
          <th>Runs</th>
          <th>Success</th>
          <th>Time Saved</th>
        </tr>
        ${summary.processorBreakdown.map(p => `
        <tr>
          <td>${p.name.replace('Processor', '')}</td>
          <td>${p.totalRuns}</td>
          <td class="${p.failureCount === 0 ? 'success' : 'warning'}">${((p.successCount / p.totalRuns) * 100).toFixed(0)}%</td>
          <td>${p.totalTimeSavedMinutes} min</td>
        </tr>
        `).join('')}
      </table>

      <div class="section-title">Top Senders</div>
      <table>
        <tr>
          <th>Email</th>
          <th>Count</th>
        </tr>
        ${summary.topSenders.map(s => `
        <tr>
          <td>${s.email}</td>
          <td>${s.count}</td>
        </tr>
        `).join('')}
      </table>

      <div style="margin-top: 20px; padding: 15px; background: #ecfdf5; border-radius: 8px; border-left: 4px solid #059669;">
        <strong>Daily Impact:</strong> Your team saved approximately <strong>${timeSavedHours} hours</strong> today through email automation.
      </div>
    </div>
  </div>
</body>
</html>
`;
  }

  /**
   * Store summary in database for historical tracking
   */
  private async storeSummary(summary: DailySummary): Promise<void> {
    await this.pool.query(
      `INSERT INTO email_processing_summary
       (date, total_received, total_processed, total_auto_responded,
        time_saved_minutes, sla_compliance_rate, pending_count, processor_stats)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       ON CONFLICT (date) DO UPDATE SET
         total_received = EXCLUDED.total_received,
         total_processed = EXCLUDED.total_processed,
         total_auto_responded = EXCLUDED.total_auto_responded,
         time_saved_minutes = EXCLUDED.time_saved_minutes,
         sla_compliance_rate = EXCLUDED.sla_compliance_rate,
         pending_count = EXCLUDED.pending_count,
         processor_stats = EXCLUDED.processor_stats,
         updated_at = NOW()`,
      [
        summary.date,
        summary.totalEmailsReceived,
        summary.totalEmailsProcessed,
        summary.totalEmailsAutoResponded,
        summary.totalTimeSavedMinutes,
        summary.slaCompliance.complianceRate,
        summary.pendingItems,
        JSON.stringify(summary.processorBreakdown)
      ]
    );
  }

  /**
   * Generate weekly summary
   */
  async generateWeeklySummary(): Promise<DailySummary[]> {
    const summaries: DailySummary[] = [];
    const today = new Date();

    for (let i = 6; i >= 0; i--) {
      const date = new Date(today);
      date.setDate(date.getDate() - i);
      summaries.push(await this.generateDailySummary(date));
    }

    return summaries;
  }
}
