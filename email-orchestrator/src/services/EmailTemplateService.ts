/**
 * Email Template Service
 * Manages email templates and sends templated emails
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import { GraphEmailService } from './GraphEmailService';
import { EmailTemplate } from '../types';

export class EmailTemplateService {
  private templateCache: Map<string, EmailTemplate> = new Map();
  private cacheLoadedAt: Date | null = null;
  private readonly cacheTtlMs = 5 * 60 * 1000; // 5 minutes

  constructor(
    private readonly pool: Pool,
    private readonly graphService: GraphEmailService,
    private readonly logger: Logger,
    private readonly senderEmail: string
  ) {}

  /**
   * Load templates from database into cache
   */
  async loadTemplates(): Promise<void> {
    try {
      const result = await this.pool.query(
        `SELECT id, name, subject, body, is_html, variables, category, created_at, updated_at
         FROM email_templates WHERE active = true`
      );

      this.templateCache.clear();
      for (const row of result.rows) {
        this.templateCache.set(row.name, {
          id: row.id,
          name: row.name,
          subject: row.subject,
          body: row.body,
          isHtml: row.is_html,
          variables: row.variables || [],
          category: row.category,
          createdAt: row.created_at,
          updatedAt: row.updated_at
        });
      }

      this.cacheLoadedAt = new Date();
      this.logger.info(`Loaded ${this.templateCache.size} email templates`);
    } catch (error) {
      this.logger.error('Failed to load email templates', { error });
      throw error;
    }
  }

  /**
   * Get a template by name
   */
  async getTemplate(name: string): Promise<EmailTemplate | null> {
    // Refresh cache if stale
    if (!this.cacheLoadedAt ||
        Date.now() - this.cacheLoadedAt.getTime() > this.cacheTtlMs) {
      await this.loadTemplates();
    }

    return this.templateCache.get(name) || null;
  }

  /**
   * Render a template with variables
   */
  renderTemplate(
    template: EmailTemplate,
    variables: Record<string, any>
  ): { subject: string; body: string } {
    let subject = template.subject;
    let body = template.body;

    // Replace variables in format {variableName} or {variableName|format}
    for (const [key, value] of Object.entries(variables)) {
      const plainPattern = new RegExp(`\\{${key}\\}`, 'g');
      subject = subject.replace(plainPattern, String(value));
      body = body.replace(plainPattern, String(value));

      // Handle formatted variables
      const formatPatterns = [
        { pattern: new RegExp(`\\{${key}\\|currency\\}`, 'g'), format: this.formatCurrency },
        { pattern: new RegExp(`\\{${key}\\|date\\}`, 'g'), format: this.formatDate },
        { pattern: new RegExp(`\\{${key}\\|capitalize\\}`, 'g'), format: this.capitalize },
        { pattern: new RegExp(`\\{${key}\\|uppercase\\}`, 'g'), format: (v: any) => String(v).toUpperCase() },
        { pattern: new RegExp(`\\{${key}\\|lowercase\\}`, 'g'), format: (v: any) => String(v).toLowerCase() }
      ];

      for (const { pattern, format } of formatPatterns) {
        subject = subject.replace(pattern, format(value));
        body = body.replace(pattern, format(value));
      }
    }

    return { subject, body };
  }

  /**
   * Send a templated email
   */
  async sendTemplatedEmail(
    templateName: string,
    to: string | string[],
    variables: Record<string, any>,
    cc?: string[]
  ): Promise<void> {
    const template = await this.getTemplate(templateName);

    if (!template) {
      throw new Error(`Template not found: ${templateName}`);
    }

    const { subject, body } = this.renderTemplate(template, variables);

    await this.graphService.sendEmail(to, subject, body, template.isHtml, cc);

    // Log the sent email
    await this.logSentEmail(templateName, to, subject, variables);
  }

  /**
   * Send a raw email (non-templated)
   */
  async sendEmail(
    to: string | string[],
    subject: string,
    body: string,
    isHtml: boolean = true,
    cc?: string[]
  ): Promise<void> {
    await this.graphService.sendEmail(to, subject, body, isHtml, cc);

    // Log the sent email
    await this.logSentEmail('raw', to, subject, {});
  }

  /**
   * Log sent email for tracking
   */
  private async logSentEmail(
    templateName: string,
    to: string | string[],
    subject: string,
    variables: Record<string, any>
  ): Promise<void> {
    try {
      await this.pool.query(
        `INSERT INTO sent_emails
         (template_name, to_emails, subject, variables, sent_at)
         VALUES ($1, $2, $3, $4, NOW())`,
        [
          templateName,
          Array.isArray(to) ? to : [to],
          subject,
          JSON.stringify(variables)
        ]
      );
    } catch (error) {
      this.logger.error('Failed to log sent email', { error });
    }
  }

  /**
   * Create a new template
   */
  async createTemplate(
    name: string,
    subject: string,
    body: string,
    isHtml: boolean = true,
    variables: string[] = [],
    category?: string
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO email_templates
       (name, subject, body, is_html, variables, category, active, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, true, NOW(), NOW())
       RETURNING id`,
      [name, subject, body, isHtml, variables, category]
    );

    // Refresh cache
    await this.loadTemplates();

    return result.rows[0].id;
  }

  /**
   * Update an existing template
   */
  async updateTemplate(
    name: string,
    updates: Partial<Pick<EmailTemplate, 'subject' | 'body' | 'isHtml' | 'variables'>>
  ): Promise<void> {
    const setClauses: string[] = [];
    const values: any[] = [];
    let paramIndex = 1;

    if (updates.subject !== undefined) {
      setClauses.push(`subject = $${paramIndex++}`);
      values.push(updates.subject);
    }
    if (updates.body !== undefined) {
      setClauses.push(`body = $${paramIndex++}`);
      values.push(updates.body);
    }
    if (updates.isHtml !== undefined) {
      setClauses.push(`is_html = $${paramIndex++}`);
      values.push(updates.isHtml);
    }
    if (updates.variables !== undefined) {
      setClauses.push(`variables = $${paramIndex++}`);
      values.push(updates.variables);
    }

    if (setClauses.length === 0) return;

    setClauses.push(`updated_at = NOW()`);
    values.push(name);

    await this.pool.query(
      `UPDATE email_templates SET ${setClauses.join(', ')} WHERE name = $${paramIndex}`,
      values
    );

    // Refresh cache
    await this.loadTemplates();
  }

  // Formatting helpers
  private formatCurrency(value: any): string {
    const num = parseFloat(value);
    if (isNaN(num)) return String(value);
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(num);
  }

  private formatDate(value: any): string {
    const date = value instanceof Date ? value : new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    }).format(date);
  }

  private capitalize(value: any): string {
    const str = String(value);
    return str.split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }
}
