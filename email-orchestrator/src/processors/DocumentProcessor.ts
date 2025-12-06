/**
 * Document Processor
 * Classifies and routes document emails
 * Time saved: ~3 minutes per document email
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { BaseEmailProcessor } from '../core/IEmailProcessor';
import { Email, ProcessingContext, ProcessingResult, DocumentData } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

export class DocumentProcessor extends BaseEmailProcessor {
  readonly name = 'DocumentProcessor';
  readonly priority = 70;
  readonly description = 'Classifies documents and routes appropriately';

  private readonly documentKeywords = [
    'document', 'documents', 'attached', 'attachment',
    'paystub', 'pay stub', 'w-2', 'w2', 'tax return',
    'bank statement', 'verification', 'voe', 'vod',
    'appraisal', 'title', 'insurance', 'hoa',
    'driver license', 'id', 'passport', 'social security'
  ];

  constructor(
    pool: Pool,
    logger: Logger,
    anthropic: Anthropic,
    templateService: EmailTemplateService
  ) {
    super(pool, logger, anthropic, templateService);
  }

  async canProcess(email: Email): Promise<boolean> {
    // Must have attachments
    if (!email.hasAttachments) return false;

    const content = `${email.subject} ${email.bodyPreview}`.toLowerCase();
    return this.documentKeywords.some(kw => content.includes(kw));
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('Processing document email', {
      emailId: email.id,
      attachmentCount: email.attachments?.length || 0
    });

    try {
      // Classify the documents
      const documentData = await this.classifyDocuments(email);

      if (!documentData) {
        return this.failureResult('classification_failed', 'Could not classify documents');
      }

      // Try to match to lead or loan
      const match = await this.matchToRecord(email.from.address);

      // Log document receipt
      const docLogId = await this.logDocumentReceipt(email, documentData, match, context);

      // Create task for processing
      const taskId = await this.createProcessingTask(email, documentData, match, context);

      // Send acknowledgment to sender
      if (match) {
        await this.sendAcknowledgment(email, documentData);
      }

      return this.successResult('documents_classified', 3, {
        createdRecords: [
          { type: 'document' as any, id: docLogId, description: `${documentData.documentType} received` }
        ],
        createdTasks: [
          { id: taskId, title: `Review documents from ${email.from.address}`, priority: 'medium' as const }
        ],
        metadata: {
          documentType: documentData.documentType,
          category: documentData.category,
          attachmentCount: email.attachments?.length || 0,
          matchedLead: match?.leadId,
          matchedLoan: match?.loanId
        }
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('Document processing failed', { error: errorMessage });
      return this.failureResult('processing_error', errorMessage);
    }
  }

  /**
   * Classify documents using AI
   */
  private async classifyDocuments(email: Email): Promise<DocumentData | null> {
    const attachmentList = email.attachments
      ?.map(a => `- ${a.name} (${a.contentType}, ${Math.round(a.size / 1024)}KB)`)
      .join('\n') || 'No attachment details available';

    const prompt = `Classify the documents in this email based on the subject, body, and attachment names.

Attachments:
${attachmentList}

Return a JSON object:
{
  "documentType": "Primary document type (e.g., 'paystubs', 'bank_statements', 'tax_returns', 'drivers_license', 'appraisal', etc.)",
  "category": "income" | "asset" | "property" | "identity" | "credit" | "other",
  "extractedData": {
    // Any specific data you can extract, like:
    "employerName": "if visible",
    "bankName": "if visible",
    "dateRange": "if visible"
  }
}

Categories:
- income: Paystubs, W2s, tax returns, 1099s, P&L statements
- asset: Bank statements, investment statements, gift letters
- property: Appraisal, title, insurance, HOA docs, purchase contract
- identity: Driver's license, passport, SSN card
- credit: Credit report, credit explanations, bankruptcy docs
- other: Everything else`;

    const response = await this.analyzeWithAI(email, prompt);
    return this.parseAIResponse<DocumentData>(response);
  }

  /**
   * Match email to lead or loan
   */
  private async matchToRecord(
    email: string
  ): Promise<{ leadId?: number; loanId?: number; contactName?: string } | null> {
    // Try loan first
    const loanResult = await this.pool.query(
      `SELECT id, borrower_name FROM loans
       WHERE borrower_email = $1 OR co_borrower_email = $1
       AND status NOT IN ('funded', 'cancelled', 'denied')
       ORDER BY created_at DESC LIMIT 1`,
      [email.toLowerCase()]
    );

    if (loanResult.rows[0]) {
      return {
        loanId: loanResult.rows[0].id,
        contactName: loanResult.rows[0].borrower_name
      };
    }

    // Try lead
    const leadResult = await this.pool.query(
      `SELECT id, first_name, last_name FROM leads
       WHERE email = $1
       ORDER BY created_at DESC LIMIT 1`,
      [email.toLowerCase()]
    );

    if (leadResult.rows[0]) {
      return {
        leadId: leadResult.rows[0].id,
        contactName: `${leadResult.rows[0].first_name} ${leadResult.rows[0].last_name}`
      };
    }

    return null;
  }

  /**
   * Log document receipt
   */
  private async logDocumentReceipt(
    email: Email,
    documentData: DocumentData,
    match: { leadId?: number; loanId?: number } | null,
    context: ProcessingContext
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO document_receipts
       (email_id, from_email, document_type, category, lead_id, loan_id,
        attachment_count, extracted_data, received_at, processed_by)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
       RETURNING id`,
      [
        email.id,
        email.from.address,
        documentData.documentType,
        documentData.category,
        match?.leadId,
        match?.loanId,
        email.attachments?.length || 0,
        JSON.stringify(documentData.extractedData || {}),
        context.userId
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Create task for document review
   */
  private async createProcessingTask(
    email: Email,
    documentData: DocumentData,
    match: { leadId?: number; loanId?: number; contactName?: string } | null,
    context: ProcessingContext
  ): Promise<number> {
    const dueDate = new Date();
    dueDate.setHours(dueDate.getHours() + 24); // Due in 24 hours

    const result = await this.pool.query(
      `INSERT INTO tasks
       (title, description, lead_id, loan_id, assigned_to, priority, status,
        due_date, category, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
       RETURNING id`,
      [
        `Review ${documentData.documentType} from ${match?.contactName || email.from.address}`,
        `Document type: ${documentData.documentType}\n` +
        `Category: ${documentData.category}\n` +
        `Attachments: ${email.attachments?.length || 0}\n` +
        `From: ${email.from.name || email.from.address}\n\n` +
        `Subject: ${email.subject}`,
        match?.leadId,
        match?.loanId,
        context.userId,
        'medium',
        'pending',
        dueDate,
        'document_review'
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Send acknowledgment to sender
   */
  private async sendAcknowledgment(
    email: Email,
    documentData: DocumentData
  ): Promise<void> {
    const firstName = email.from.name?.split(' ')[0] || 'there';

    const body = `
<p>Hi ${firstName},</p>

<p>Thank you for sending your ${documentData.documentType}. We've received ${email.attachments?.length || 'your'} document(s) and they are being reviewed by our team.</p>

<p>If we need any additional information or clarification, we'll reach out to you directly.</p>

<p>Best regards,<br>
The Perennia AI Team</p>
`;

    try {
      await this.templateService.sendEmail(
        email.from.address,
        `RE: ${email.subject}`,
        body,
        true
      );
    } catch (error) {
      this.logger.error('Failed to send document acknowledgment', { error });
    }
  }
}
