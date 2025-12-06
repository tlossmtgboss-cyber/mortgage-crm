/**
 * Client Inquiry Processor
 * Handles client questions and can auto-respond to routine inquiries
 * Time saved: ~10 minutes per inquiry
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { BaseEmailProcessor } from '../core/IEmailProcessor';
import { Email, ProcessingContext, ProcessingResult, ClientInquiryData } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

export class ClientInquiryProcessor extends BaseEmailProcessor {
  readonly name = 'ClientInquiryProcessor';
  readonly priority = 50;
  readonly description = 'Processes client inquiries and generates responses';

  constructor(
    pool: Pool,
    logger: Logger,
    anthropic: Anthropic,
    templateService: EmailTemplateService,
    private readonly enableAutoRespond: boolean = true
  ) {
    super(pool, logger, anthropic, templateService);
  }

  async canProcess(email: Email): Promise<boolean> {
    // Check if sender is a known client
    const isKnownClient = await this.isKnownClient(email.from.address);
    if (!isKnownClient) return false;

    // Check it's not an automated email
    if (this.isAutomatedEmail(email)) return false;

    // Check if it looks like a question/inquiry
    return this.looksLikeInquiry(email);
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('Processing client inquiry', {
      emailId: email.id,
      from: email.from.address
    });

    try {
      // Get client context
      const clientContext = await this.getClientContext(email.from.address);

      // Analyze the inquiry
      const inquiryData = await this.analyzeInquiry(email, clientContext);

      if (!inquiryData) {
        return this.failureResult('analysis_failed', 'Could not analyze inquiry');
      }

      let sentEmails: any[] = [];
      let createdTasks: any[] = [];

      // Determine if we can auto-respond
      if (this.enableAutoRespond && inquiryData.autoRespondEligible) {
        // Generate and send response
        const response = await this.generateResponse(email, inquiryData, clientContext);
        if (response) {
          await this.templateService.sendEmail(
            email.from.address,
            `RE: ${email.subject}`,
            response,
            true
          );
          sentEmails.push({
            to: email.from.address,
            subject: `RE: ${email.subject}`,
            templateName: 'auto_generated'
          });
        }
      } else {
        // Create task for manual response
        const taskId = await this.createResponseTask(email, inquiryData, context);
        createdTasks.push({
          id: taskId,
          title: `Respond to ${email.from.name || email.from.address}`,
          priority: inquiryData.urgency
        });
      }

      // Log the inquiry
      await this.logInquiry(email, inquiryData, context);

      return this.successResult(
        inquiryData.autoRespondEligible && this.enableAutoRespond
          ? 'auto_responded'
          : 'task_created',
        10,
        {
          sentEmails,
          createdTasks,
          metadata: {
            inquiryType: inquiryData.inquiryType,
            urgency: inquiryData.urgency,
            sentiment: inquiryData.sentiment,
            autoResponded: inquiryData.autoRespondEligible && this.enableAutoRespond
          }
        }
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('Client inquiry processing failed', { error: errorMessage });
      return this.failureResult('processing_error', errorMessage);
    }
  }

  /**
   * Check if email sender is a known client
   */
  private async isKnownClient(email: string): Promise<boolean> {
    const result = await this.pool.query(
      `SELECT EXISTS(
         SELECT 1 FROM leads WHERE email = $1
         UNION
         SELECT 1 FROM contacts WHERE email = $1
         UNION
         SELECT 1 FROM loans WHERE borrower_email = $1 OR co_borrower_email = $1
       ) as is_client`,
      [email.toLowerCase()]
    );
    return result.rows[0].is_client;
  }

  /**
   * Check if email looks like an automated message
   */
  private isAutomatedEmail(email: Email): boolean {
    const automatedIndicators = [
      'noreply@',
      'no-reply@',
      'donotreply@',
      'mailer-daemon',
      'auto-',
      'automated',
      'notification@'
    ];

    const fromLower = email.from.address.toLowerCase();
    return automatedIndicators.some(ind => fromLower.includes(ind));
  }

  /**
   * Check if email looks like an inquiry needing response
   */
  private looksLikeInquiry(email: Email): boolean {
    const questionIndicators = [
      '?',
      'question',
      'wondering',
      'can you',
      'could you',
      'please',
      'help',
      'status',
      'update',
      'when will',
      'how do',
      'what is',
      'where is',
      'need to know',
      'let me know'
    ];

    const content = `${email.subject} ${email.bodyPreview}`.toLowerCase();
    return questionIndicators.some(ind => content.includes(ind));
  }

  /**
   * Get client context from database
   */
  private async getClientContext(email: string): Promise<any> {
    // Get lead info
    const leadResult = await this.pool.query(
      `SELECT id, first_name, last_name, status, loan_purpose, assigned_to
       FROM leads WHERE email = $1
       ORDER BY created_at DESC LIMIT 1`,
      [email.toLowerCase()]
    );

    // Get active loans
    const loanResult = await this.pool.query(
      `SELECT id, loan_number, status, stage, loan_amount, expected_close_date
       FROM loans WHERE borrower_email = $1 OR co_borrower_email = $1
       ORDER BY created_at DESC LIMIT 3`,
      [email.toLowerCase()]
    );

    // Get recent communications
    const commsResult = await this.pool.query(
      `SELECT subject, sent_at, direction
       FROM email_tracking
       WHERE (from_email = $1 OR $1 = ANY(to_emails::text[]))
       ORDER BY received_at DESC LIMIT 5`,
      [email.toLowerCase()]
    );

    return {
      lead: leadResult.rows[0] || null,
      loans: loanResult.rows,
      recentCommunications: commsResult.rows
    };
  }

  /**
   * Analyze the inquiry using AI
   */
  private async analyzeInquiry(
    email: Email,
    clientContext: any
  ): Promise<ClientInquiryData | null> {
    const contextInfo = clientContext.loans.length > 0
      ? `Client has ${clientContext.loans.length} loan(s). Most recent: ${clientContext.loans[0]?.status}`
      : clientContext.lead
        ? `Client is a lead in ${clientContext.lead.status} status`
        : 'New client, no existing records';

    const prompt = `Analyze this client inquiry email. Context: ${contextInfo}

Return a JSON object:
{
  "inquiryType": "status" | "document" | "rate" | "general" | "complaint",
  "urgency": "low" | "medium" | "high" | "critical",
  "sentiment": "positive" | "neutral" | "negative",
  "summary": "Brief summary of what client is asking",
  "suggestedResponse": "Draft response if this is a simple question",
  "autoRespondEligible": true/false (true only for simple status/general questions)
}

autoRespondEligible should be FALSE for:
- Complaints
- Complex financial questions
- Rate lock decisions
- Anything requiring human judgment`;

    const response = await this.analyzeWithAI(email, prompt);
    const parsed = this.parseAIResponse<ClientInquiryData>(response);

    if (parsed && clientContext.lead) {
      parsed.leadId = clientContext.lead.id;
    }
    if (parsed && clientContext.loans.length > 0) {
      parsed.loanId = clientContext.loans[0].id;
    }

    return parsed;
  }

  /**
   * Generate response for auto-reply
   */
  private async generateResponse(
    email: Email,
    inquiry: ClientInquiryData,
    clientContext: any
  ): Promise<string | null> {
    const loanInfo = clientContext.loans.length > 0
      ? `Their loan ${clientContext.loans[0].loan_number} is in ${clientContext.loans[0].status} status.`
      : '';

    const prompt = `Generate a professional, helpful response to this client inquiry.

${inquiry.summary}

${loanInfo}

Guidelines:
- Be warm and professional
- Answer the question directly if possible
- If you can't fully answer, acknowledge and say someone will follow up
- Keep it concise (2-3 paragraphs max)
- Include a clear next step or call to action
- Sign off professionally

Do NOT include a subject line, just the body.`;

    const response = await this.analyzeWithAI(email, prompt);

    // Clean up response
    return response
      .replace(/^(Subject|RE|Re):.*/m, '')
      .trim();
  }

  /**
   * Create task for manual response
   */
  private async createResponseTask(
    email: Email,
    inquiry: ClientInquiryData,
    context: ProcessingContext
  ): Promise<number> {
    const priorityMap: Record<string, string> = {
      critical: 'critical',
      high: 'high',
      medium: 'medium',
      low: 'low'
    };

    const dueHours: Record<string, number> = {
      critical: 1,
      high: 4,
      medium: 24,
      low: 48
    };

    const dueDate = new Date();
    dueDate.setHours(dueDate.getHours() + dueHours[inquiry.urgency]);

    const result = await this.pool.query(
      `INSERT INTO tasks
       (title, description, lead_id, loan_id, assigned_to, priority, status, due_date, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
       RETURNING id`,
      [
        `Respond to client: ${email.from.name || email.from.address}`,
        `Inquiry type: ${inquiry.inquiryType}\n` +
        `Summary: ${inquiry.summary}\n` +
        `Sentiment: ${inquiry.sentiment}\n\n` +
        `Original email: ${email.subject}`,
        inquiry.leadId,
        inquiry.loanId,
        context.userId,
        priorityMap[inquiry.urgency],
        'pending',
        dueDate
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Log inquiry for analytics
   */
  private async logInquiry(
    email: Email,
    inquiry: ClientInquiryData,
    context: ProcessingContext
  ): Promise<void> {
    await this.pool.query(
      `INSERT INTO client_inquiries
       (email_id, from_email, inquiry_type, urgency, sentiment, summary,
        auto_responded, lead_id, loan_id, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())`,
      [
        email.id,
        email.from.address,
        inquiry.inquiryType,
        inquiry.urgency,
        inquiry.sentiment,
        inquiry.summary,
        inquiry.autoRespondEligible,
        inquiry.leadId,
        inquiry.loanId
      ]
    );
  }
}
