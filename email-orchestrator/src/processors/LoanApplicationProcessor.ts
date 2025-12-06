/**
 * Loan Application Processor
 * Automatically extracts loan application data and creates records
 * Time saved: ~15 minutes per application
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { BaseEmailProcessor } from '../core/IEmailProcessor';
import { Email, ProcessingContext, ProcessingResult, LoanApplicationData } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

export class LoanApplicationProcessor extends BaseEmailProcessor {
  readonly name = 'LoanApplicationProcessor';
  readonly priority = 100; // Highest priority
  readonly description = 'Processes loan applications and creates records';

  private readonly applicationKeywords = [
    'loan application',
    'mortgage application',
    'apply for',
    'application for',
    'pre-approval',
    'preapproval',
    'pre-qualification',
    'prequalification',
    'new application',
    'refinance application',
    'purchase application',
    'home loan application'
  ];

  constructor(
    pool: Pool,
    logger: Logger,
    anthropic: Anthropic,
    templateService: EmailTemplateService,
    private readonly enableCreation: boolean = true
  ) {
    super(pool, logger, anthropic, templateService);
  }

  async canProcess(email: Email): Promise<boolean> {
    const subjectLower = email.subject.toLowerCase();
    const bodyLower = email.body.toLowerCase();

    // Check for application keywords
    const hasKeyword = this.applicationKeywords.some(keyword =>
      subjectLower.includes(keyword) || bodyLower.includes(keyword)
    );

    // Check for attachments (applications often have docs)
    const hasAttachments = email.hasAttachments;

    // Check for form-like content
    const hasFormContent = this.detectFormContent(email.body);

    return hasKeyword || (hasAttachments && hasFormContent);
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('Processing loan application email', {
      emailId: email.id,
      subject: email.subject,
      from: email.from.address
    });

    try {
      // Extract application data using AI
      const applicationData = await this.extractApplicationData(email);

      if (!applicationData) {
        return this.failureResult('extraction_failed', 'Could not extract application data');
      }

      // Validate required fields
      if (!applicationData.borrowerEmail || !applicationData.borrowerName) {
        return this.failureResult('validation_failed', 'Missing required fields: borrowerName or borrowerEmail');
      }

      let createdRecords: any[] = [];
      let sentEmails: any[] = [];
      let createdTasks: any[] = [];

      if (this.enableCreation) {
        // Create or update contact
        const contactId = await this.createOrUpdateContact(applicationData, context);
        createdRecords.push({
          type: 'contact',
          id: contactId,
          description: `Contact: ${applicationData.borrowerName}`
        });

        // Create lead
        const leadId = await this.createLead(applicationData, contactId, context);
        createdRecords.push({
          type: 'lead',
          id: leadId,
          description: `Lead: ${applicationData.borrowerName} - ${applicationData.loanType || 'unknown'}`
        });

        // Create initial task for loan officer
        const taskId = await this.createFollowUpTask(leadId, applicationData, context);
        createdTasks.push({
          id: taskId,
          title: `Review application: ${applicationData.borrowerName}`,
          priority: 'high'
        });

        // Send acknowledgment email
        const emailSent = await this.sendAcknowledgment(applicationData);
        if (emailSent) {
          sentEmails.push({
            to: applicationData.borrowerEmail,
            subject: 'Application Received',
            templateName: 'loan_application_received'
          });
        }
      }

      // Log processing
      await this.logProcessing(email, context, {
        success: true,
        processor: this.name,
        action: 'application_processed',
        timeSaved: 15,
        createdRecords,
        sentEmails,
        createdTasks
      });

      return this.successResult('application_processed', 15, {
        createdRecords,
        sentEmails,
        createdTasks,
        metadata: {
          borrowerName: applicationData.borrowerName,
          loanType: applicationData.loanType,
          loanAmount: applicationData.loanAmount
        }
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('Loan application processing failed', {
        emailId: email.id,
        error: errorMessage
      });
      return this.failureResult('processing_error', errorMessage);
    }
  }

  /**
   * Extract application data using AI
   */
  private async extractApplicationData(email: Email): Promise<LoanApplicationData | null> {
    const prompt = `Extract loan application information from this email. Return a JSON object with these fields:
{
  "borrowerName": "Full name of primary borrower",
  "borrowerEmail": "Email address",
  "borrowerPhone": "Phone number if provided",
  "coBorrowerName": "Co-borrower name if any",
  "coBorrowerEmail": "Co-borrower email if any",
  "loanType": "purchase, refinance, cash_out, or heloc",
  "loanAmount": "Loan amount as number (no commas/symbols)",
  "propertyAddress": "Property address if mentioned",
  "propertyType": "single_family, condo, townhouse, multi_family, etc.",
  "estimatedValue": "Property value as number",
  "creditScore": "Credit score if mentioned",
  "employmentType": "W2, self_employed, retired, etc.",
  "annualIncome": "Annual income as number"
}

Only include fields that can be confidently extracted. Use null for missing fields.`;

    const response = await this.analyzeWithAI(email, prompt);
    return this.parseAIResponse<LoanApplicationData>(response);
  }

  /**
   * Create or update contact in database
   */
  private async createOrUpdateContact(
    data: LoanApplicationData,
    context: ProcessingContext
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO contacts (first_name, last_name, email, phone, created_by, created_at)
       VALUES ($1, $2, $3, $4, $5, NOW())
       ON CONFLICT (email) DO UPDATE SET
         phone = COALESCE(EXCLUDED.phone, contacts.phone),
         updated_at = NOW()
       RETURNING id`,
      [
        data.borrowerName.split(' ')[0],
        data.borrowerName.split(' ').slice(1).join(' '),
        data.borrowerEmail,
        data.borrowerPhone,
        context.userId
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Create lead from application
   */
  private async createLead(
    data: LoanApplicationData,
    contactId: number,
    context: ProcessingContext
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO leads
       (contact_id, first_name, last_name, email, phone, status, source,
        loan_purpose, loan_amount, property_address, property_type,
        credit_score_range, assigned_to, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
       RETURNING id`,
      [
        contactId,
        data.borrowerName.split(' ')[0],
        data.borrowerName.split(' ').slice(1).join(' '),
        data.borrowerEmail,
        data.borrowerPhone,
        'new',
        'email_application',
        data.loanType || 'purchase',
        data.loanAmount,
        data.propertyAddress,
        data.propertyType,
        data.creditScore ? this.getCreditScoreRange(data.creditScore) : null,
        context.userId
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Create follow-up task for loan officer
   */
  private async createFollowUpTask(
    leadId: number,
    data: LoanApplicationData,
    context: ProcessingContext
  ): Promise<number> {
    const dueDate = new Date();
    dueDate.setHours(dueDate.getHours() + 2); // Due in 2 hours

    const result = await this.pool.query(
      `INSERT INTO tasks
       (title, description, lead_id, assigned_to, priority, status, due_date, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
       RETURNING id`,
      [
        `Call new applicant: ${data.borrowerName}`,
        `New ${data.loanType || 'loan'} application received via email.\n` +
        `Amount: ${data.loanAmount ? `$${data.loanAmount.toLocaleString()}` : 'Not specified'}\n` +
        `Contact: ${data.borrowerPhone || data.borrowerEmail}`,
        leadId,
        context.userId,
        'high',
        'pending',
        dueDate
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Send acknowledgment email to applicant
   */
  private async sendAcknowledgment(data: LoanApplicationData): Promise<boolean> {
    try {
      await this.templateService.sendTemplatedEmail(
        'loan_application_received',
        data.borrowerEmail,
        {
          borrowerName: data.borrowerName.split(' ')[0],
          loanType: data.loanType || 'home loan',
          timestamp: new Date().toLocaleString()
        }
      );
      return true;
    } catch (error) {
      this.logger.error('Failed to send acknowledgment email', { error });
      return false;
    }
  }

  /**
   * Detect if email body contains form-like content
   */
  private detectFormContent(body: string): boolean {
    const formIndicators = [
      /name\s*[:=]/i,
      /email\s*[:=]/i,
      /phone\s*[:=]/i,
      /address\s*[:=]/i,
      /loan\s+amount\s*[:=]/i,
      /property\s*[:=]/i,
      /income\s*[:=]/i,
      /credit\s+score\s*[:=]/i
    ];

    const matchCount = formIndicators.filter(pattern => pattern.test(body)).length;
    return matchCount >= 3; // At least 3 form-like fields
  }

  /**
   * Get credit score range from exact score
   */
  private getCreditScoreRange(score: number): string {
    if (score >= 760) return '760+';
    if (score >= 720) return '720-759';
    if (score >= 680) return '680-719';
    if (score >= 640) return '640-679';
    if (score >= 580) return '580-639';
    return 'Below 580';
  }
}
