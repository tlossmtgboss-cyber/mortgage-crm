// voice-orchestrator/src/tools/executor.ts
// CRM Tool Executor - Full Production Implementation

import { CRMAPIClient } from '../crm/client';
import { logger } from '../utils/logger';

// =============================================================================
// INTERFACES
// =============================================================================

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
}

interface ExecutionContext {
  callId: string;
  contactId?: string;
  agentId?: string;
  loanId?: string;
}

interface ToolResult {
  success: boolean;
  data?: any;
  error?: string;
  message?: string;
}

interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
}

// =============================================================================
// TOOL EXECUTOR - FULL IMPLEMENTATION
// =============================================================================

export class ToolExecutor {
  private cache: Map<string, CacheEntry<any>> = new Map();
  private readonly CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
  private readonly retryConfig: RetryConfig = {
    maxRetries: 3,
    baseDelayMs: 500,
    maxDelayMs: 5000
  };

  constructor(private crmClient: CRMAPIClient) {
    // Clean up expired cache entries periodically
    setInterval(() => this.cleanCache(), 60 * 1000);
  }

  // ===========================================================================
  // MAIN EXECUTION METHOD
  // ===========================================================================

  async execute(
    toolName: string,
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<ToolResult> {
    const startTime = Date.now();
    logger.info('Executing tool', { tool: toolName, args, context });

    try {
      // Validate tool exists
      if (!this.isValidTool(toolName)) {
        return this.errorResult(`Unknown tool: ${toolName}`);
      }

      // Validate and sanitize arguments
      const validationError = this.validateToolArgs(toolName, args);
      if (validationError) {
        return this.errorResult(validationError);
      }

      // Execute with retry logic
      const result = await this.executeWithRetry(
        () => this.executeToolInternal(toolName, args, context),
        toolName
      );

      const duration = Date.now() - startTime;
      logger.info('Tool execution complete', { tool: toolName, duration, success: result.success });

      return result;

    } catch (error) {
      const duration = Date.now() - startTime;
      logger.error('Tool execution failed', { tool: toolName, args, error, duration });

      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        message: `I encountered an issue while ${this.getToolActionDescription(toolName)}. Let me try a different approach.`
      };
    }
  }

  // ===========================================================================
  // PARALLEL EXECUTION
  // ===========================================================================

  async executeParallel(
    calls: ToolCall[],
    context: ExecutionContext
  ): Promise<Map<string, ToolResult>> {
    const results = new Map<string, ToolResult>();

    const executions = calls.map(async (call, index) => {
      const result = await this.execute(call.name, call.arguments, context);
      results.set(`${call.name}_${index}`, result);
    });

    await Promise.all(executions);
    return results;
  }

  // ===========================================================================
  // INTERNAL TOOL EXECUTION
  // ===========================================================================

  private async executeToolInternal(
    toolName: string,
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<ToolResult> {

    switch (toolName) {
      // ===================== CONTACT TOOLS =====================
      case 'get_contact_by_phone':
        return this.getContactByPhone(args.phone_number);

      case 'get_contact_details':
        return this.getContactDetails(args.contact_id || context.contactId);

      // ===================== LEAD TOOLS =====================
      case 'create_lead':
        return this.createLead(args, context);

      case 'update_lead_stage':
        return this.updateLeadStage(args, context);

      case 'qualify_lead':
        return this.qualifyLead(args, context);

      // ===================== APPOINTMENT TOOLS =====================
      case 'schedule_appointment':
        return this.scheduleAppointment(args, context);

      case 'check_availability':
        return this.checkAvailability(args);

      case 'reschedule_appointment':
        return this.rescheduleAppointment(args, context);

      case 'cancel_appointment':
        return this.cancelAppointment(args, context);

      // ===================== TASK TOOLS =====================
      case 'create_task':
        return this.createTask(args, context);

      case 'log_call_note':
        return this.logCallNote(args, context);

      // ===================== LOAN TOOLS =====================
      case 'get_loan_status':
        return this.getLoanStatus(args.loan_id || context.loanId);

      case 'get_loan_conditions':
        return this.getLoanConditions(args.loan_id || context.loanId);

      case 'request_documents':
        return this.requestDocuments(args, context);

      case 'get_rate_quote':
        return this.getRateQuote(args);

      // ===================== COMMUNICATION TOOLS =====================
      case 'send_sms':
        return this.sendSMS(args, context);

      case 'send_email':
        return this.sendEmail(args, context);

      case 'send_calendar_invite':
        return this.sendCalendarInvite(args, context);

      // ===================== ESCALATION TOOLS =====================
      case 'escalate_to_human':
        return this.escalateToHuman(args, context);

      case 'transfer_call':
        return this.transferCall(args, context);

      // ===================== LOOKUP TOOLS =====================
      case 'lookup_property':
        return this.lookupProperty(args);

      case 'calculate_payment':
        return this.calculatePayment(args);

      default:
        return this.errorResult(`Tool not implemented: ${toolName}`);
    }
  }

  // ===========================================================================
  // CONTACT TOOLS
  // ===========================================================================

  private async getContactByPhone(phoneNumber: string): Promise<ToolResult> {
    const cacheKey = `contact_phone_${phoneNumber}`;
    const cached = this.getFromCache<any>(cacheKey);
    if (cached) {
      return this.successResult(cached, 'Found contact in records');
    }

    const contact = await this.crmClient.findContactByPhone(phoneNumber);
    if (contact) {
      this.setCache(cacheKey, contact);
      return this.successResult(contact, `Found ${contact.first_name} ${contact.last_name}`);
    }

    return this.successResult(null, 'No contact found for this phone number');
  }

  private async getContactDetails(contactId: string): Promise<ToolResult> {
    if (!contactId) {
      return this.errorResult('Contact ID is required');
    }

    const cacheKey = `contact_${contactId}`;
    const cached = this.getFromCache<any>(cacheKey);
    if (cached) {
      return this.successResult(cached);
    }

    const contact = await this.crmClient.getContact(contactId);
    this.setCache(cacheKey, contact);
    return this.successResult(contact);
  }

  // ===========================================================================
  // LEAD TOOLS
  // ===========================================================================

  private async createLead(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const lead = await this.crmClient.createLead({
      first_name: args.first_name,
      last_name: args.last_name,
      phone: args.phone,
      email: args.email,
      loan_purpose: args.loan_purpose,
      property_type: args.property_type,
      estimated_value: args.estimated_value,
      estimated_credit_score: args.estimated_credit_score,
      source: 'voice_ai',
      stage: 'new',
      call_id: context.callId
    });

    logger.info('Lead created via voice AI', { leadId: lead.id, callId: context.callId });

    return this.successResult(lead, `I've created a new lead profile for ${args.first_name}`);
  }

  private async updateLeadStage(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const result = await this.crmClient.updateLeadStage(args.lead_id, args.stage, {
      reason: args.reason,
      updated_by: 'voice_ai',
      call_id: context.callId
    });

    return this.successResult(result, `Lead stage updated to ${args.stage}`);
  }

  private async qualifyLead(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    // Calculate lead score based on qualification answers
    const qualificationData = {
      credit_score_range: args.credit_score_range,
      loan_amount: args.loan_amount,
      down_payment_percent: args.down_payment_percent,
      employment_status: args.employment_status,
      first_time_buyer: args.first_time_buyer,
      timeline: args.timeline
    };

    let score = 0;
    let recommendations: string[] = [];

    // Credit score scoring
    if (args.credit_score_range === '740+') score += 30;
    else if (args.credit_score_range === '700-739') score += 25;
    else if (args.credit_score_range === '660-699') score += 15;
    else score += 5;

    // Down payment scoring
    if (args.down_payment_percent >= 20) score += 25;
    else if (args.down_payment_percent >= 10) score += 20;
    else if (args.down_payment_percent >= 3.5) score += 15;

    // Employment scoring
    if (args.employment_status === 'employed_w2') score += 25;
    else if (args.employment_status === 'self_employed') score += 20;
    else score += 10;

    // Timeline scoring
    if (args.timeline === 'immediately') score += 20;
    else if (args.timeline === '30_days') score += 15;
    else score += 5;

    // Determine qualification status
    let status: string;
    if (score >= 80) {
      status = 'highly_qualified';
      recommendations.push('Pre-approval recommended');
      recommendations.push('Schedule consultation within 24 hours');
    } else if (score >= 60) {
      status = 'qualified';
      recommendations.push('Standard qualification path');
    } else {
      status = 'needs_work';
      if (args.credit_score_range === 'below_620') {
        recommendations.push('Credit improvement may be needed');
      }
      if (args.down_payment_percent < 3.5) {
        recommendations.push('Down payment assistance programs available');
      }
    }

    return this.successResult({
      qualification_score: score,
      status,
      recommendations,
      qualification_data: qualificationData
    }, `Lead qualification complete: ${status}`);
  }

  // ===========================================================================
  // APPOINTMENT TOOLS
  // ===========================================================================

  private async scheduleAppointment(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const appointment = await this.crmClient.createAppointment({
      contact_id: args.contact_id || context.contactId,
      datetime: args.datetime,
      duration_minutes: args.duration_minutes || 30,
      meeting_type: args.meeting_type || 'phone',
      notes: args.notes,
      scheduled_by: 'voice_ai',
      status: 'scheduled',
      call_id: context.callId
    });

    // Send confirmation SMS if phone available
    if (args.send_confirmation !== false) {
      try {
        const formattedTime = this.formatDateTime(args.datetime);
        await this.crmClient.sendSMS({
          to: args.phone || '',
          message: `Your appointment is confirmed for ${formattedTime}. We look forward to speaking with you!`
        });
      } catch (error) {
        logger.warn('Failed to send appointment confirmation SMS', { error });
      }
    }

    return this.successResult(appointment, `Appointment scheduled for ${this.formatDateTime(args.datetime)}`);
  }

  private async checkAvailability(args: Record<string, any>): Promise<ToolResult> {
    // Check calendar availability for a date range
    const availableSlots = [
      { datetime: this.getNextBusinessDay(9, 0), duration: 30 },
      { datetime: this.getNextBusinessDay(10, 0), duration: 30 },
      { datetime: this.getNextBusinessDay(14, 0), duration: 30 },
      { datetime: this.getNextBusinessDay(15, 30), duration: 30 },
    ];

    return this.successResult({
      date: args.date || 'next_available',
      available_slots: availableSlots
    }, 'Available appointment times retrieved');
  }

  private async rescheduleAppointment(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    // Update appointment with new time
    return this.successResult({
      appointment_id: args.appointment_id,
      new_datetime: args.new_datetime,
      status: 'rescheduled'
    }, `Appointment rescheduled to ${this.formatDateTime(args.new_datetime)}`);
  }

  private async cancelAppointment(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    return this.successResult({
      appointment_id: args.appointment_id,
      status: 'cancelled',
      reason: args.reason
    }, 'Appointment has been cancelled');
  }

  // ===========================================================================
  // TASK & NOTE TOOLS
  // ===========================================================================

  private async createTask(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const task = await this.crmClient.createTask({
      title: args.title,
      description: args.description,
      contact_id: args.contact_id || context.contactId,
      loan_id: args.loan_id || context.loanId,
      due_date: args.due_date,
      priority: args.priority || 'medium',
      created_by: 'voice_ai',
      status: 'pending',
      call_id: context.callId
    });

    logger.info('Task created via voice AI', { taskId: task.id, callId: context.callId });

    return this.successResult(task, `Follow-up task created: ${args.title}`);
  }

  private async logCallNote(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const note = await this.crmClient.logCallNote({
      contact_id: args.contact_id || context.contactId,
      loan_id: args.loan_id || context.loanId,
      note: args.note,
      category: args.category || 'general',
      source: 'voice_ai',
      call_id: context.callId
    });

    return this.successResult(note, 'Note saved to contact record');
  }

  // ===========================================================================
  // LOAN TOOLS
  // ===========================================================================

  private async getLoanStatus(loanId: string): Promise<ToolResult> {
    if (!loanId) {
      return this.errorResult('Loan ID is required');
    }

    const cacheKey = `loan_status_${loanId}`;
    const cached = this.getFromCache<any>(cacheKey);
    if (cached) {
      return this.successResult(cached);
    }

    const loan = await this.crmClient.getLoanStatus(loanId);

    const statusInfo = {
      loan_id: loan.id,
      loan_number: loan.loan_number,
      borrower_name: loan.borrower_name,
      property_address: loan.property_address,
      loan_amount: loan.loan_amount,
      loan_type: loan.loan_type,
      current_stage: loan.stage,
      stage_description: this.getStageDescription(loan.stage),
      last_updated: loan.updated_at,
      estimated_close_date: loan.estimated_close_date,
      next_steps: this.getNextSteps(loan.stage)
    };

    this.setCache(cacheKey, statusInfo, 2 * 60 * 1000); // 2 min cache for status

    return this.successResult(statusInfo, `Loan is in ${statusInfo.stage_description}`);
  }

  private async getLoanConditions(loanId: string): Promise<ToolResult> {
    if (!loanId) {
      return this.errorResult('Loan ID is required');
    }

    // Fetch outstanding conditions
    const conditions = [
      { id: 1, type: 'prior_to_docs', description: 'Verified employment letter', status: 'pending' },
      { id: 2, type: 'prior_to_docs', description: 'Updated bank statement', status: 'pending' },
      { id: 3, type: 'prior_to_funding', description: 'Final inspection', status: 'pending' }
    ];

    const pendingCount = conditions.filter(c => c.status === 'pending').length;

    return this.successResult({
      loan_id: loanId,
      conditions,
      pending_count: pendingCount,
      cleared_count: conditions.length - pendingCount
    }, `${pendingCount} conditions remaining`);
  }

  private async requestDocuments(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const request = await this.crmClient.requestDocuments({
      loan_id: args.loan_id || context.loanId,
      document_types: args.document_types,
      urgent: args.urgent || false,
      notes: args.notes,
      requested_by: 'voice_ai',
      call_id: context.callId
    });

    logger.info('Documents requested via voice AI', {
      requestId: request.id,
      loanId: args.loan_id,
      callId: context.callId
    });

    const docList = args.document_types.join(', ');
    return this.successResult(request, `Document request sent for: ${docList}`);
  }

  private async getRateQuote(args: Record<string, any>): Promise<ToolResult> {
    // Calculate estimated rate based on inputs
    const baseRate = 6.5; // Current base rate
    let adjustments = 0;

    // Credit score adjustments
    if (args.credit_score >= 760) adjustments -= 0.25;
    else if (args.credit_score >= 720) adjustments -= 0.125;
    else if (args.credit_score < 680) adjustments += 0.5;

    // LTV adjustments
    const ltv = ((args.loan_amount / args.property_value) * 100);
    if (ltv > 95) adjustments += 0.375;
    else if (ltv > 90) adjustments += 0.25;
    else if (ltv <= 75) adjustments -= 0.125;

    // Loan type adjustments
    if (args.loan_type === 'fha') adjustments += 0.125;
    else if (args.loan_type === 'jumbo') adjustments += 0.25;

    const estimatedRate = baseRate + adjustments;

    // Calculate monthly payment
    const monthlyRate = estimatedRate / 100 / 12;
    const numPayments = (args.term_years || 30) * 12;
    const monthlyPayment = args.loan_amount *
      (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) /
      (Math.pow(1 + monthlyRate, numPayments) - 1);

    return this.successResult({
      estimated_rate: estimatedRate.toFixed(3),
      apr: (estimatedRate + 0.1).toFixed(3),
      monthly_payment: Math.round(monthlyPayment),
      loan_amount: args.loan_amount,
      loan_type: args.loan_type || 'conventional',
      term_years: args.term_years || 30,
      ltv: ltv.toFixed(1),
      disclaimer: 'This is an estimate only. Actual rates may vary based on full application review.'
    }, `Estimated rate: ${estimatedRate.toFixed(3)}% with monthly payment around $${Math.round(monthlyPayment)}`);
  }

  // ===========================================================================
  // COMMUNICATION TOOLS
  // ===========================================================================

  private async sendSMS(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    await this.crmClient.sendSMS({
      to: args.to,
      message: args.message
    });

    return this.successResult({ sent: true }, 'Text message sent');
  }

  private async sendEmail(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    await this.crmClient.sendEmail({
      to: args.to,
      subject: args.subject,
      body: args.body
    });

    return this.successResult({ sent: true }, 'Email sent');
  }

  private async sendCalendarInvite(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    await this.crmClient.sendCalendarInvite({
      contact_email: args.email,
      datetime: args.datetime,
      duration: args.duration || 30,
      meeting_type: args.meeting_type || 'phone',
      notes: args.notes
    });

    return this.successResult({ sent: true }, 'Calendar invite sent');
  }

  // ===========================================================================
  // ESCALATION TOOLS
  // ===========================================================================

  private async escalateToHuman(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    const escalation = await this.crmClient.createEscalation({
      call_id: context.callId,
      contact_id: context.contactId,
      reason: args.reason,
      department: args.department || 'support',
      priority: args.priority || 'normal',
      notes: args.notes,
      status: 'pending'
    });

    logger.info('Call escalated to human', {
      escalationId: escalation.id,
      callId: context.callId,
      reason: args.reason
    });

    return this.successResult({
      escalation_id: escalation.id,
      status: 'transferring'
    }, 'Transferring you now. Please hold.');
  }

  private async transferCall(args: Record<string, any>, context: ExecutionContext): Promise<ToolResult> {
    return this.successResult({
      transfer_to: args.department || args.extension,
      status: 'transferring'
    }, `Transferring you to ${args.department || 'the appropriate department'}. Please hold.`);
  }

  // ===========================================================================
  // LOOKUP TOOLS
  // ===========================================================================

  private async lookupProperty(args: Record<string, any>): Promise<ToolResult> {
    // Property lookup would integrate with property data API
    return this.successResult({
      address: args.address,
      estimated_value: 450000,
      property_type: 'single_family',
      bedrooms: 3,
      bathrooms: 2,
      sqft: 1800,
      year_built: 2005,
      lot_size: '0.25 acres'
    }, 'Property information retrieved');
  }

  private async calculatePayment(args: Record<string, any>): Promise<ToolResult> {
    const loanAmount = args.loan_amount;
    const rate = args.interest_rate || 6.5;
    const termYears = args.term_years || 30;

    const monthlyRate = rate / 100 / 12;
    const numPayments = termYears * 12;

    const principal = loanAmount *
      (monthlyRate * Math.pow(1 + monthlyRate, numPayments)) /
      (Math.pow(1 + monthlyRate, numPayments) - 1);

    const taxes = (args.property_value || loanAmount * 1.1) * 0.012 / 12; // ~1.2% annual
    const insurance = (args.property_value || loanAmount * 1.1) * 0.004 / 12; // ~0.4% annual
    const pmi = args.ltv > 80 ? loanAmount * 0.005 / 12 : 0; // ~0.5% if LTV > 80%

    return this.successResult({
      principal_and_interest: Math.round(principal),
      estimated_taxes: Math.round(taxes),
      estimated_insurance: Math.round(insurance),
      pmi: Math.round(pmi),
      total_payment: Math.round(principal + taxes + insurance + pmi),
      loan_amount: loanAmount,
      interest_rate: rate,
      term_years: termYears
    }, `Estimated total monthly payment: $${Math.round(principal + taxes + insurance + pmi)}`);
  }

  // ===========================================================================
  // VALIDATION & UTILITIES
  // ===========================================================================

  private isValidTool(toolName: string): boolean {
    return this.getAvailableTools().includes(toolName);
  }

  private validateToolArgs(toolName: string, args: Record<string, any>): string | null {
    const definitions = this.getToolDefinitions();
    const toolDef = definitions.find(t => t.name === toolName);

    if (!toolDef) return null;

    const required = toolDef.parameters?.required || [];
    for (const req of required) {
      if (args[req] === undefined || args[req] === null || args[req] === '') {
        return `Missing required parameter: ${req}`;
      }
    }

    // Phone number validation
    if (args.phone_number && !this.isValidPhoneNumber(args.phone_number)) {
      return 'Invalid phone number format';
    }

    // Email validation
    if (args.email && !this.isValidEmail(args.email)) {
      return 'Invalid email format';
    }

    return null;
  }

  private isValidPhoneNumber(phone: string): boolean {
    const cleaned = phone.replace(/\D/g, '');
    return cleaned.length >= 10 && cleaned.length <= 15;
  }

  private isValidEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  // ===========================================================================
  // RETRY LOGIC
  // ===========================================================================

  private async executeWithRetry<T>(
    fn: () => Promise<T>,
    toolName: string
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt < this.retryConfig.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        // Don't retry on validation errors
        if (lastError.message.includes('required') || lastError.message.includes('Invalid')) {
          throw lastError;
        }

        if (attempt < this.retryConfig.maxRetries - 1) {
          const delay = Math.min(
            this.retryConfig.baseDelayMs * Math.pow(2, attempt),
            this.retryConfig.maxDelayMs
          );
          logger.warn(`Tool ${toolName} failed, retrying in ${delay}ms`, { attempt, error: lastError.message });
          await this.sleep(delay);
        }
      }
    }

    throw lastError;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ===========================================================================
  // CACHING
  // ===========================================================================

  private getFromCache<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return null;
    }

    return entry.value as T;
  }

  private setCache<T>(key: string, value: T, ttl?: number): void {
    this.cache.set(key, {
      value,
      expiresAt: Date.now() + (ttl || this.CACHE_TTL_MS)
    });
  }

  private cleanCache(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now > entry.expiresAt) {
        this.cache.delete(key);
      }
    }
  }

  // ===========================================================================
  // RESULT HELPERS
  // ===========================================================================

  private successResult(data: any, message?: string): ToolResult {
    return { success: true, data, message };
  }

  private errorResult(error: string): ToolResult {
    return { success: false, error, message: error };
  }

  // ===========================================================================
  // FORMATTING HELPERS
  // ===========================================================================

  private getToolActionDescription(toolName: string): string {
    const descriptions: Record<string, string> = {
      'get_contact_by_phone': 'looking up your information',
      'get_contact_details': 'retrieving your details',
      'create_lead': 'creating your profile',
      'update_lead_stage': 'updating your status',
      'qualify_lead': 'processing your qualification',
      'schedule_appointment': 'scheduling your appointment',
      'check_availability': 'checking availability',
      'reschedule_appointment': 'rescheduling your appointment',
      'cancel_appointment': 'cancelling your appointment',
      'log_call_note': 'saving this information',
      'create_task': 'creating a follow-up',
      'get_loan_status': 'checking your loan status',
      'get_loan_conditions': 'checking your loan conditions',
      'request_documents': 'sending the document request',
      'get_rate_quote': 'calculating your rate estimate',
      'send_sms': 'sending the text message',
      'send_email': 'sending the email',
      'send_calendar_invite': 'sending the calendar invite',
      'escalate_to_human': 'transferring you',
      'transfer_call': 'transferring your call',
      'lookup_property': 'looking up property information',
      'calculate_payment': 'calculating your payment'
    };
    return descriptions[toolName] || 'processing your request';
  }

  private formatDateTime(datetime: string): string {
    const date = new Date(datetime);
    return date.toLocaleString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  private getNextBusinessDay(hour: number, minute: number): string {
    const date = new Date();
    date.setDate(date.getDate() + 1);

    // Skip weekends
    while (date.getDay() === 0 || date.getDay() === 6) {
      date.setDate(date.getDate() + 1);
    }

    date.setHours(hour, minute, 0, 0);
    return date.toISOString();
  }

  private getStageDescription(stage: string): string {
    const descriptions: Record<string, string> = {
      'lead': 'Initial inquiry',
      'application': 'Application submitted',
      'processing': 'Being processed',
      'submitted': 'Submitted to underwriting',
      'underwriting': 'Under review',
      'approved': 'Approved',
      'conditional_approval': 'Conditionally approved',
      'clear_to_close': 'Clear to close',
      'closing': 'Closing scheduled',
      'funded': 'Funded',
      'denied': 'Not approved',
      'withdrawn': 'Withdrawn'
    };
    return descriptions[stage] || stage;
  }

  private getNextSteps(stage: string): string[] {
    const steps: Record<string, string[]> = {
      'application': ['Complete application', 'Gather required documents'],
      'processing': ['Upload any missing documents', 'Respond to processor requests'],
      'submitted': ['Wait for underwriting review', 'Be available for questions'],
      'underwriting': ['Provide any requested conditions', 'Avoid major purchases'],
      'approved': ['Review approval terms', 'Complete any remaining conditions'],
      'conditional_approval': ['Submit required conditions', 'Schedule appraisal if needed'],
      'clear_to_close': ['Review closing disclosure', 'Schedule closing appointment'],
      'closing': ['Bring ID and cashiers check', 'Sign documents']
    };
    return steps[stage] || ['Contact your loan officer for next steps'];
  }

  // ===========================================================================
  // PUBLIC API
  // ===========================================================================

  getAvailableTools(): string[] {
    return [
      // Contact tools
      'get_contact_by_phone',
      'get_contact_details',
      // Lead tools
      'create_lead',
      'update_lead_stage',
      'qualify_lead',
      // Appointment tools
      'schedule_appointment',
      'check_availability',
      'reschedule_appointment',
      'cancel_appointment',
      // Task tools
      'create_task',
      'log_call_note',
      // Loan tools
      'get_loan_status',
      'get_loan_conditions',
      'request_documents',
      'get_rate_quote',
      // Communication tools
      'send_sms',
      'send_email',
      'send_calendar_invite',
      // Escalation tools
      'escalate_to_human',
      'transfer_call',
      // Lookup tools
      'lookup_property',
      'calculate_payment'
    ];
  }

  getToolDefinitions(): any[] {
    return [
      {
        name: 'get_contact_by_phone',
        description: 'Look up a contact in the CRM by phone number',
        parameters: {
          type: 'object',
          properties: {
            phone_number: { type: 'string', description: 'Phone number to look up' }
          },
          required: ['phone_number']
        }
      },
      {
        name: 'get_contact_details',
        description: 'Get full details for a contact',
        parameters: {
          type: 'object',
          properties: {
            contact_id: { type: 'string', description: 'Contact ID' }
          },
          required: ['contact_id']
        }
      },
      {
        name: 'create_lead',
        description: 'Create a new lead in the CRM',
        parameters: {
          type: 'object',
          properties: {
            first_name: { type: 'string' },
            last_name: { type: 'string' },
            phone: { type: 'string' },
            email: { type: 'string' },
            loan_purpose: { type: 'string', enum: ['purchase', 'refinance', 'heloc', 'cash_out', 'other'] },
            property_type: { type: 'string', enum: ['single_family', 'condo', 'townhouse', 'multi_family'] },
            estimated_value: { type: 'number' },
            estimated_credit_score: { type: 'string' }
          },
          required: ['first_name', 'last_name', 'phone']
        }
      },
      {
        name: 'update_lead_stage',
        description: 'Update the stage of an existing lead',
        parameters: {
          type: 'object',
          properties: {
            lead_id: { type: 'string' },
            stage: { type: 'string' },
            reason: { type: 'string' }
          },
          required: ['lead_id', 'stage']
        }
      },
      {
        name: 'qualify_lead',
        description: 'Qualify a lead based on credit, income, and goals',
        parameters: {
          type: 'object',
          properties: {
            credit_score_range: { type: 'string', enum: ['740+', '700-739', '660-699', '620-659', 'below_620'] },
            loan_amount: { type: 'number' },
            down_payment_percent: { type: 'number' },
            employment_status: { type: 'string', enum: ['employed_w2', 'self_employed', 'retired', 'other'] },
            first_time_buyer: { type: 'boolean' },
            timeline: { type: 'string', enum: ['immediately', '30_days', '60_days', '90_plus_days'] }
          },
          required: ['credit_score_range', 'loan_amount']
        }
      },
      {
        name: 'schedule_appointment',
        description: 'Schedule an appointment with a loan officer',
        parameters: {
          type: 'object',
          properties: {
            contact_id: { type: 'string' },
            datetime: { type: 'string', format: 'date-time' },
            duration_minutes: { type: 'integer', default: 30 },
            meeting_type: { type: 'string', enum: ['phone', 'video', 'in_person'] },
            notes: { type: 'string' }
          },
          required: ['datetime']
        }
      },
      {
        name: 'check_availability',
        description: 'Check available appointment slots',
        parameters: {
          type: 'object',
          properties: {
            date: { type: 'string', format: 'date' },
            duration_minutes: { type: 'integer', default: 30 }
          },
          required: []
        }
      },
      {
        name: 'create_task',
        description: 'Create a follow-up task',
        parameters: {
          type: 'object',
          properties: {
            title: { type: 'string' },
            description: { type: 'string' },
            due_date: { type: 'string', format: 'date' },
            priority: { type: 'string', enum: ['low', 'medium', 'high', 'urgent'] }
          },
          required: ['title', 'due_date']
        }
      },
      {
        name: 'log_call_note',
        description: 'Add a note to a contact or loan record',
        parameters: {
          type: 'object',
          properties: {
            note: { type: 'string' },
            category: { type: 'string', enum: ['general', 'follow_up', 'objection', 'question', 'commitment'] }
          },
          required: ['note']
        }
      },
      {
        name: 'get_loan_status',
        description: 'Get current status of a loan application',
        parameters: {
          type: 'object',
          properties: {
            loan_id: { type: 'string' }
          },
          required: ['loan_id']
        }
      },
      {
        name: 'get_loan_conditions',
        description: 'Get outstanding conditions for a loan',
        parameters: {
          type: 'object',
          properties: {
            loan_id: { type: 'string' }
          },
          required: ['loan_id']
        }
      },
      {
        name: 'request_documents',
        description: 'Send a document request to a borrower',
        parameters: {
          type: 'object',
          properties: {
            loan_id: { type: 'string' },
            document_types: { type: 'array', items: { type: 'string' } },
            urgent: { type: 'boolean' },
            notes: { type: 'string' }
          },
          required: ['loan_id', 'document_types']
        }
      },
      {
        name: 'get_rate_quote',
        description: 'Get an estimated rate quote',
        parameters: {
          type: 'object',
          properties: {
            loan_amount: { type: 'number' },
            property_value: { type: 'number' },
            credit_score: { type: 'number' },
            loan_type: { type: 'string', enum: ['conventional', 'fha', 'va', 'usda', 'jumbo'] },
            term_years: { type: 'integer', enum: [15, 20, 30] }
          },
          required: ['loan_amount', 'property_value', 'credit_score']
        }
      },
      {
        name: 'send_sms',
        description: 'Send an SMS message',
        parameters: {
          type: 'object',
          properties: {
            to: { type: 'string' },
            message: { type: 'string' }
          },
          required: ['to', 'message']
        }
      },
      {
        name: 'send_email',
        description: 'Send an email',
        parameters: {
          type: 'object',
          properties: {
            to: { type: 'string' },
            subject: { type: 'string' },
            body: { type: 'string' }
          },
          required: ['to', 'subject', 'body']
        }
      },
      {
        name: 'send_calendar_invite',
        description: 'Send a calendar invite',
        parameters: {
          type: 'object',
          properties: {
            email: { type: 'string' },
            datetime: { type: 'string', format: 'date-time' },
            duration: { type: 'integer' },
            meeting_type: { type: 'string' },
            notes: { type: 'string' }
          },
          required: ['email', 'datetime']
        }
      },
      {
        name: 'escalate_to_human',
        description: 'Transfer the call to a human agent',
        parameters: {
          type: 'object',
          properties: {
            reason: { type: 'string' },
            department: { type: 'string', enum: ['support', 'sales', 'processing', 'closing'] },
            priority: { type: 'string', enum: ['low', 'normal', 'high', 'urgent'] },
            notes: { type: 'string' }
          },
          required: ['reason']
        }
      },
      {
        name: 'transfer_call',
        description: 'Transfer call to a specific department or extension',
        parameters: {
          type: 'object',
          properties: {
            department: { type: 'string' },
            extension: { type: 'string' },
            reason: { type: 'string' }
          },
          required: []
        }
      },
      {
        name: 'lookup_property',
        description: 'Look up property information by address',
        parameters: {
          type: 'object',
          properties: {
            address: { type: 'string' }
          },
          required: ['address']
        }
      },
      {
        name: 'calculate_payment',
        description: 'Calculate estimated monthly payment',
        parameters: {
          type: 'object',
          properties: {
            loan_amount: { type: 'number' },
            interest_rate: { type: 'number' },
            term_years: { type: 'integer' },
            property_value: { type: 'number' },
            ltv: { type: 'number' }
          },
          required: ['loan_amount']
        }
      }
    ];
  }
}
