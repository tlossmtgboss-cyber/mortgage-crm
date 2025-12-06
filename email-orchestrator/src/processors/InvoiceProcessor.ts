/**
 * Invoice Processor
 * Automatically routes invoices to accounting and creates tracking records
 * Time saved: ~5 minutes per invoice
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';
import { BaseEmailProcessor } from '../core/IEmailProcessor';
import { Email, ProcessingContext, ProcessingResult, InvoiceData } from '../types';
import { EmailTemplateService } from '../services/EmailTemplateService';

export class InvoiceProcessor extends BaseEmailProcessor {
  readonly name = 'InvoiceProcessor';
  readonly priority = 80;
  readonly description = 'Processes invoices and routes to accounting';

  private readonly invoiceKeywords = [
    'invoice',
    'bill',
    'payment due',
    'amount due',
    'statement',
    'appraisal fee',
    'title fee',
    'credit report',
    'payable',
    'remittance'
  ];

  constructor(
    pool: Pool,
    logger: Logger,
    anthropic: Anthropic,
    templateService: EmailTemplateService,
    private readonly accountingEmail: string = 'accounting@company.com'
  ) {
    super(pool, logger, anthropic, templateService);
  }

  async canProcess(email: Email): Promise<boolean> {
    const content = `${email.subject} ${email.bodyPreview}`.toLowerCase();

    // Check for invoice keywords
    const hasKeyword = this.invoiceKeywords.some(kw => content.includes(kw));
    if (!hasKeyword) return false;

    // Check for attachments (invoices usually have PDFs)
    if (email.hasAttachments) return true;

    // Check for amount patterns ($X,XXX.XX)
    const hasAmount = /\$[\d,]+\.?\d*/i.test(content);
    return hasAmount;
  }

  async process(email: Email, context: ProcessingContext): Promise<ProcessingResult> {
    this.logger.info('Processing invoice email', {
      emailId: email.id,
      from: email.from.address
    });

    try {
      // Extract invoice data
      const invoiceData = await this.extractInvoiceData(email);

      if (!invoiceData) {
        return this.failureResult('extraction_failed', 'Could not extract invoice data');
      }

      // Try to match to a loan
      const loanMatch = await this.matchToLoan(invoiceData, email);

      // Create invoice record
      const invoiceId = await this.createInvoiceRecord(invoiceData, loanMatch, context);

      // Create task for accounting
      const taskId = await this.createAccountingTask(invoiceData, invoiceId, context);

      // Forward to accounting
      await this.forwardToAccounting(email, invoiceData, loanMatch);

      return this.successResult('invoice_processed', 5, {
        createdRecords: [
          { type: 'invoice' as any, id: invoiceId, description: `Invoice from ${invoiceData.vendorName}` }
        ],
        createdTasks: [
          { id: taskId, title: `Process invoice: ${invoiceData.vendorName}`, priority: 'medium' as const }
        ],
        metadata: {
          vendorName: invoiceData.vendorName,
          amount: invoiceData.amount,
          category: invoiceData.category,
          matchedLoan: loanMatch?.loanNumber
        }
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.logger.error('Invoice processing failed', { error: errorMessage });
      return this.failureResult('processing_error', errorMessage);
    }
  }

  /**
   * Extract invoice data using AI
   */
  private async extractInvoiceData(email: Email): Promise<InvoiceData | null> {
    const prompt = `Extract invoice information from this email. Return a JSON object:
{
  "vendorName": "Name of the company/vendor",
  "vendorEmail": "Email of the vendor",
  "invoiceNumber": "Invoice or reference number if present",
  "amount": "Amount as a number (no $ or commas)",
  "dueDate": "Due date in YYYY-MM-DD format if present",
  "category": "appraisal" | "title" | "credit" | "legal" | "other",
  "loanNumber": "Loan number if mentioned"
}

For category:
- appraisal: Appraisal fees, property inspection
- title: Title company, escrow, recording fees
- credit: Credit report, credit monitoring
- legal: Attorney fees, legal documents
- other: Everything else`;

    const response = await this.analyzeWithAI(email, prompt);
    const data = this.parseAIResponse<InvoiceData>(response);

    if (data) {
      data.vendorEmail = data.vendorEmail || email.from.address;
    }

    return data;
  }

  /**
   * Try to match invoice to a loan
   */
  private async matchToLoan(
    invoiceData: InvoiceData,
    email: Email
  ): Promise<{ loanId: number; loanNumber: string } | null> {
    // Try matching by loan number in invoice
    if (invoiceData.loanNumber) {
      const result = await this.pool.query(
        `SELECT id, loan_number FROM loans WHERE loan_number = $1`,
        [invoiceData.loanNumber]
      );
      if (result.rows[0]) {
        return { loanId: result.rows[0].id, loanNumber: result.rows[0].loan_number };
      }
    }

    // Try matching by email subject (often contains loan number)
    const loanNumberMatch = email.subject.match(/(?:loan|ln|#)\s*[:# ]?\s*(\d{6,12})/i);
    if (loanNumberMatch) {
      const result = await this.pool.query(
        `SELECT id, loan_number FROM loans WHERE loan_number LIKE $1`,
        [`%${loanNumberMatch[1]}%`]
      );
      if (result.rows[0]) {
        return { loanId: result.rows[0].id, loanNumber: result.rows[0].loan_number };
      }
    }

    // Try matching by vendor relationship
    const vendorMatch = await this.pool.query(
      `SELECT l.id, l.loan_number
       FROM loans l
       JOIN loan_vendors lv ON lv.loan_id = l.id
       WHERE lv.vendor_email = $1
       AND l.status NOT IN ('funded', 'cancelled', 'denied')
       ORDER BY l.created_at DESC
       LIMIT 1`,
      [invoiceData.vendorEmail]
    );

    if (vendorMatch.rows[0]) {
      return { loanId: vendorMatch.rows[0].id, loanNumber: vendorMatch.rows[0].loan_number };
    }

    return null;
  }

  /**
   * Create invoice record in database
   */
  private async createInvoiceRecord(
    invoiceData: InvoiceData,
    loanMatch: { loanId: number; loanNumber: string } | null,
    context: ProcessingContext
  ): Promise<number> {
    const result = await this.pool.query(
      `INSERT INTO invoices
       (vendor_name, vendor_email, invoice_number, amount, due_date,
        category, loan_id, status, received_at, created_by)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
       RETURNING id`,
      [
        invoiceData.vendorName,
        invoiceData.vendorEmail,
        invoiceData.invoiceNumber,
        invoiceData.amount,
        invoiceData.dueDate,
        invoiceData.category,
        loanMatch?.loanId,
        'pending',
        context.userId
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Create task for accounting team
   */
  private async createAccountingTask(
    invoiceData: InvoiceData,
    invoiceId: number,
    context: ProcessingContext
  ): Promise<number> {
    const dueDate = invoiceData.dueDate
      ? new Date(invoiceData.dueDate)
      : new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // Default 7 days

    // Set task due 2 days before invoice due date
    dueDate.setDate(dueDate.getDate() - 2);

    const result = await this.pool.query(
      `INSERT INTO tasks
       (title, description, category, priority, status, due_date, metadata, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
       RETURNING id`,
      [
        `Process invoice: ${invoiceData.vendorName}`,
        `Invoice #${invoiceData.invoiceNumber || 'N/A'}\n` +
        `Amount: ${invoiceData.amount ? `$${invoiceData.amount.toLocaleString()}` : 'See attachment'}\n` +
        `Category: ${invoiceData.category}\n` +
        `Due: ${invoiceData.dueDate || 'Not specified'}`,
        'accounting',
        invoiceData.dueDate && new Date(invoiceData.dueDate) < new Date(Date.now() + 3 * 24 * 60 * 60 * 1000)
          ? 'high'
          : 'medium',
        'pending',
        dueDate,
        JSON.stringify({ invoiceId, vendorEmail: invoiceData.vendorEmail })
      ]
    );

    return result.rows[0].id;
  }

  /**
   * Forward invoice to accounting
   */
  private async forwardToAccounting(
    email: Email,
    invoiceData: InvoiceData,
    loanMatch: { loanId: number; loanNumber: string } | null
  ): Promise<void> {
    const body = `
<p><strong>Invoice Received - Auto-Forwarded</strong></p>

<table style="border-collapse: collapse;">
  <tr><td style="padding: 4px 8px;"><strong>Vendor:</strong></td><td>${invoiceData.vendorName}</td></tr>
  <tr><td style="padding: 4px 8px;"><strong>Amount:</strong></td><td>${invoiceData.amount ? `$${invoiceData.amount.toLocaleString()}` : 'See attachment'}</td></tr>
  <tr><td style="padding: 4px 8px;"><strong>Invoice #:</strong></td><td>${invoiceData.invoiceNumber || 'N/A'}</td></tr>
  <tr><td style="padding: 4px 8px;"><strong>Due Date:</strong></td><td>${invoiceData.dueDate || 'Not specified'}</td></tr>
  <tr><td style="padding: 4px 8px;"><strong>Category:</strong></td><td>${invoiceData.category}</td></tr>
  ${loanMatch ? `<tr><td style="padding: 4px 8px;"><strong>Loan:</strong></td><td>${loanMatch.loanNumber}</td></tr>` : ''}
</table>

<hr>
<p><strong>Original Email:</strong></p>
<p><strong>From:</strong> ${email.from.name} &lt;${email.from.address}&gt;</p>
<p><strong>Subject:</strong> ${email.subject}</p>
<hr>
${email.body}
`;

    await this.templateService.sendEmail(
      this.accountingEmail,
      `[Invoice] ${invoiceData.vendorName} - ${invoiceData.amount ? `$${invoiceData.amount.toLocaleString()}` : 'Amount in attachment'}`,
      body,
      true
    );
  }
}
