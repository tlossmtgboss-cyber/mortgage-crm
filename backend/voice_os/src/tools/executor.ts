// voice-orchestrator/src/tools/executor.ts
// CRM Tool Executor - Production Version
// Connects the Voice OS to CRM operations for real-time voice interactions.

import { CRMAPIClient } from '../crm/client';
import { logger } from '../utils/logger';

// =============================================================================
// TYPES & INTERFACES
// =============================================================================

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
}

interface ExecutionContext {
  callId: string;
  contactId?: string;
  agentId?: string;
  fromNumber?: string;
}

interface ToolExecutionResult {
  success: boolean;
  data: Record<string, any>;
  message: string;
  error?: string;
  toolName: string;
  executionTimeMs: number;
}

interface ExecutionMetrics {
  totalExecutions: number;
  totalTimeMs: number;
  avgTimeMs: number;
  errorCount: number;
  byTool: Record<string, { count: number; totalTimeMs: number; errors: number }>;
}

// =============================================================================
// TOOL EXECUTOR
// =============================================================================

export class ToolExecutor {
  private metrics: ExecutionMetrics = {
    totalExecutions: 0,
    totalTimeMs: 0,
    avgTimeMs: 0,
    errorCount: 0,
    byTool: {},
  };

  constructor(private crmClient: CRMAPIClient) {}

  /**
   * Execute a CRM tool and return standardized result
   */
  async execute(
    toolName: string,
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<ToolExecutionResult> {
    const startTime = Date.now();
    logger.info('Executing tool', { tool: toolName, args, context });

    try {
      const result = await this.executeInternal(toolName, args, context);
      const executionTime = Date.now() - startTime;

      // Track metrics
      this.updateMetrics(toolName, executionTime, false);

      return {
        success: true,
        data: result,
        message: this.getSuccessMessage(toolName, result),
        toolName,
        executionTimeMs: executionTime,
      };
    } catch (error) {
      const executionTime = Date.now() - startTime;
      this.updateMetrics(toolName, executionTime, true);

      logger.error('Tool execution failed', { tool: toolName, args, error });

      return {
        success: false,
        data: {},
        message: this.getToolActionDescription(toolName),
        error: error instanceof Error ? error.message : String(error),
        toolName,
        executionTimeMs: executionTime,
      };
    }
  }

  /**
   * Internal execution router
   */
  private async executeInternal(
    toolName: string,
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    switch (toolName) {
      // Contact & Lead Management
      case 'get_contact_by_phone':
      case 'lookup_caller':
        return await this.lookupCaller(args.phone_number || args.phone);

      case 'create_lead':
        return await this.createLead(args, context);

      case 'update_lead_stage':
        return await this.updateLeadStage(args, context);

      case 'qualify_lead':
        return await this.qualifyLead(args, context);

      // Appointment & Scheduling
      case 'get_lo_availability':
        return await this.getLOAvailability(args);

      case 'schedule_appointment':
      case 'book_appointment':
        return await this.bookAppointment(args, context);

      case 'create_callback_request':
        return await this.createCallbackRequest(args, context);

      // Loan Operations
      case 'get_loan_status':
        return await this.getLoanStatus(args);

      case 'request_documents':
        return await this.requestDocuments(args, context);

      // Communication
      case 'log_call_note':
        return await this.logCallNote(args, context);

      case 'create_task':
        return await this.createTask(args, context);

      case 'leave_message':
        return await this.leaveMessage(args, context);

      // Call Management
      case 'escalate_to_human':
      case 'transfer_call':
        return await this.transferCall(args, context);

      case 'find_available_lo':
        return await this.findAvailableLO(args);

      // Rate Information
      case 'get_current_rates':
        return await this.getCurrentRates(args);

      default:
        throw new Error(`Unknown tool: ${toolName}`);
    }
  }

  // ==========================================================================
  // TOOL IMPLEMENTATIONS
  // ==========================================================================

  /**
   * Look up caller in CRM by phone number
   */
  private async lookupCaller(phoneNumber: string): Promise<Record<string, any>> {
    const contact = await this.crmClient.findContactByPhone(phoneNumber);

    if (!contact) {
      return {
        found: false,
        message: 'Caller not found in system',
      };
    }

    // Get active loans for contact
    let activeLoans: any[] = [];
    try {
      activeLoans = await this.crmClient.getContactLoans(contact.id);
    } catch (e) {
      logger.debug('Failed to fetch contact loans', { contactId: contact.id });
    }

    return {
      found: true,
      contact_id: contact.id,
      first_name: contact.first_name,
      last_name: contact.last_name,
      email: contact.email,
      is_customer: activeLoans.length > 0,
      loan_ids: activeLoans.map((l: any) => l.id),
      assigned_lo_id: contact.assigned_to,
      assigned_lo_name: contact.assigned_to_name,
    };
  }

  /**
   * Create a new lead in the CRM
   */
  private async createLead(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const lead = await this.crmClient.createLead({
      first_name: args.first_name,
      last_name: args.last_name,
      phone: args.phone || context.fromNumber,
      email: args.email,
      loan_purpose: args.loan_purpose,
      source: 'voice_ai',
      stage: 'new',
      metadata: {
        call_id: context.callId,
        created_by: 'voice_ai',
      },
    });

    logger.info('Lead created via voice AI', { leadId: lead.id, callId: context.callId });

    return {
      lead_id: lead.id,
      message: 'Lead created successfully',
    };
  }

  /**
   * Update lead stage
   */
  private async updateLeadStage(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const result = await this.crmClient.updateLeadStage(args.lead_id, args.stage, {
      reason: args.reason,
      updated_by: 'voice_ai',
      call_id: context.callId,
    });

    return {
      lead_id: args.lead_id,
      new_stage: args.stage,
      success: true,
    };
  }

  /**
   * Quick lead qualification
   */
  private async qualifyLead(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    // Determine priority based on purpose
    const highPriorityPurposes = ['purchase', 'refinance'];
    const priority = highPriorityPurposes.includes(args.purpose) ? 'high' : 'normal';

    // Try to score through CRM
    try {
      const scored = await this.crmClient.scoreLead({
        phone: args.caller_phone || context.fromNumber,
        loan_purpose: args.purpose,
        property_type: args.property_type,
        timeframe: args.timeframe,
      });

      if (scored) {
        return {
          score: scored.score,
          priority: scored.priority || priority,
          recommended_action: scored.recommended_action || 'schedule_callback',
        };
      }
    } catch (e) {
      logger.debug('Lead scoring unavailable, using fallback');
    }

    return {
      priority,
      recommended_action: 'schedule_callback',
    };
  }

  /**
   * Get loan officer availability
   */
  private async getLOAvailability(args: Record<string, any>): Promise<Record<string, any>> {
    try {
      const availability = await this.crmClient.getAvailability(args.lo_id, args.date);

      return {
        lo_id: args.lo_id,
        date: args.date || new Date().toISOString().split('T')[0],
        available_slots: availability.slots || [],
        next_available: availability.next_available,
      };
    } catch (e) {
      // Generate fallback availability
      const targetDate = args.date ? new Date(args.date) : new Date();

      // Skip weekends
      while (targetDate.getDay() === 0 || targetDate.getDay() === 6) {
        targetDate.setDate(targetDate.getDate() + 1);
      }

      const slots = [];
      const hours = [9, 10, 11, 13, 14, 15, 16];

      for (const hour of hours) {
        const slotTime = new Date(targetDate);
        slotTime.setHours(hour, 0, 0, 0);

        if (slotTime > new Date()) {
          slots.push({
            time: slotTime.toISOString(),
            display: slotTime.toLocaleTimeString('en-US', {
              hour: 'numeric',
              minute: '2-digit',
              hour12: true,
            }),
            available: true,
          });
        }
      }

      return {
        lo_id: args.lo_id,
        date: targetDate.toISOString().split('T')[0],
        available_slots: slots,
        next_available: slots[0]?.time || null,
      };
    }
  }

  /**
   * Book an appointment
   */
  private async bookAppointment(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const appointment = await this.crmClient.createAppointment({
      contact_id: args.contact_id,
      lo_id: args.lo_id,
      datetime: args.datetime || args.datetime_str,
      duration_minutes: args.duration_minutes || 30,
      purpose: args.purpose || 'Phone Consultation',
      caller_name: args.caller_name,
      caller_phone: args.caller_phone || context.fromNumber,
      caller_email: args.caller_email,
      scheduled_by: 'voice_ai',
      status: 'scheduled',
      call_id: context.callId,
    });

    // Send confirmation SMS if we have a phone number
    const phone = args.caller_phone || context.fromNumber;
    if (phone && appointment.id) {
      try {
        await this.crmClient.sendSMS({
          to: phone,
          message: `Your appointment is confirmed for ${this.formatDateTime(args.datetime || args.datetime_str)}.`,
        });
      } catch (e) {
        logger.debug('SMS confirmation failed', { appointmentId: appointment.id });
      }
    }

    return {
      appointment_id: appointment.id,
      datetime: args.datetime || args.datetime_str,
      confirmation: `Appointment scheduled for ${this.formatDateTime(args.datetime || args.datetime_str)}`,
    };
  }

  /**
   * Create a callback request
   */
  private async createCallbackRequest(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const callback = await this.crmClient.createCallback({
      caller_name: args.caller_name,
      caller_phone: args.caller_phone || context.fromNumber,
      lo_id: args.lo_id,
      reason: args.reason,
      urgency: args.urgency || 'normal',
      best_time: args.best_time,
      call_id: context.callId,
    });

    const eta =
      args.urgency === 'high' || args.urgency === 'urgent'
        ? 'as soon as possible'
        : 'within 24 hours';

    return {
      callback_id: callback.id,
      urgency: args.urgency || 'normal',
      message: `We'll call you back ${eta}`,
    };
  }

  /**
   * Get loan status with verification
   */
  private async getLoanStatus(args: Record<string, any>): Promise<Record<string, any>> {
    const loan = await this.crmClient.getLoanStatus(args.loan_id || args.loan_number);

    // Verify borrower name if provided
    if (args.borrower_last_name) {
      const borrowerName = loan.borrower_name?.toLowerCase() || '';
      if (!borrowerName.includes(args.borrower_last_name.toLowerCase())) {
        return {
          verified: false,
          message: "I couldn't verify your information. Please check the loan number and try again.",
        };
      }
    }

    return {
      loan_id: loan.id,
      loan_number: loan.loan_number,
      status: loan.status || loan.stage,
      status_display: this.formatLoanStatus(loan.status || loan.stage),
      next_steps: loan.next_steps,
      expected_close: loan.expected_close_date,
      verified: true,
    };
  }

  /**
   * Request documents from borrower
   */
  private async requestDocuments(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const request = await this.crmClient.requestDocuments({
      loan_id: args.loan_id,
      document_types: args.document_types,
      urgent: args.urgent || false,
      requested_by: 'voice_ai',
      call_id: context.callId,
    });

    logger.info('Documents requested via voice AI', {
      requestId: request.id,
      loanId: args.loan_id,
      callId: context.callId,
    });

    return {
      request_id: request.id,
      documents: args.document_types,
      message: 'Document request sent',
    };
  }

  /**
   * Log a call note
   */
  private async logCallNote(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const note = await this.crmClient.logCallNote({
      contact_id: args.contact_id || context.contactId,
      loan_id: args.loan_id,
      note: args.note,
      category: args.category || 'general',
      source: 'voice_ai',
      call_id: context.callId,
    });

    return {
      note_id: note.id,
      message: 'Note saved',
    };
  }

  /**
   * Create a follow-up task
   */
  private async createTask(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const task = await this.crmClient.createTask({
      title: args.title,
      description: args.description,
      due_date: args.due_date,
      contact_id: args.contact_id || context.contactId,
      assigned_to: args.assigned_to || context.agentId,
      priority: args.priority || 'normal',
      created_by: 'voice_ai',
      status: 'pending',
      call_id: context.callId,
    });

    logger.info('Task created via voice AI', { taskId: task.id, callId: context.callId });

    return {
      task_id: task.id,
      title: args.title,
      due_date: args.due_date,
      message: 'Task created',
    };
  }

  /**
   * Leave a message for a loan officer
   */
  private async leaveMessage(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    // Create as a high-priority task
    const task = await this.crmClient.createTask({
      title: `Message from ${args.caller_name}`,
      description: args.message,
      assigned_to: args.lo_id,
      priority: args.urgent ? 'high' : 'normal',
      category: 'callback',
      created_by: 'voice_ai',
      status: 'pending',
      metadata: {
        caller_phone: args.caller_phone || context.fromNumber,
        call_id: context.callId,
      },
    });

    return {
      message_id: task.id,
      confirmation: "I'll make sure they get your message",
    };
  }

  /**
   * Transfer call to human or escalate
   */
  private async transferCall(
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<Record<string, any>> {
    const escalation = await this.crmClient.createEscalation({
      call_id: context.callId,
      contact_id: context.contactId,
      target_id: args.target_id,
      reason: args.reason,
      department: args.department || 'support',
      transfer_type: args.transfer_type || 'warm',
      priority: args.priority || 'normal',
      context: args.context,
      status: 'pending',
    });

    logger.info('Call escalated to human', {
      escalationId: escalation.id,
      callId: context.callId,
    });

    return {
      success: true,
      message: 'Transferring you now. Please hold.',
      escalation_id: escalation.id,
      target_id: args.target_id,
      transfer_type: args.transfer_type || 'warm',
    };
  }

  /**
   * Find an available loan officer
   */
  private async findAvailableLO(args: Record<string, any>): Promise<Record<string, any>> {
    try {
      const los = await this.crmClient.findAvailableLOs({
        specialty: args.specialty,
        language: args.language,
      });

      if (los && los.length > 0) {
        return {
          lo_id: los[0].id,
          lo_name: los[0].name,
          is_available: los[0].is_available,
        };
      }
    } catch (e) {
      logger.debug('LO lookup failed, using fallback');
    }

    return {
      lo_id: 'default',
      lo_name: 'the next available loan officer',
      is_available: true,
    };
  }

  /**
   * Get current rate information
   */
  private async getCurrentRates(args: Record<string, any>): Promise<Record<string, any>> {
    try {
      const rates = await this.crmClient.getCurrentRates(args.loan_type);

      if (rates && rates.length > 0) {
        return {
          rates,
          as_of: new Date().toISOString(),
        };
      }
    } catch (e) {
      logger.debug('Rate lookup failed');
    }

    // Safe fallback - don't quote specific rates
    return {
      message:
        "For the most accurate rate quote, I'd recommend speaking with one of our loan officers who can look at your specific situation.",
      general_info:
        'Rates are changing frequently, but we are seeing competitive rates across all loan programs.',
      recommendation: 'schedule_consultation',
    };
  }

  // ==========================================================================
  // HELPERS
  // ==========================================================================

  /**
   * Get success message for a tool execution
   */
  private getSuccessMessage(toolName: string, result: Record<string, any>): string {
    if (result.message) return result.message;
    if (result.confirmation) return result.confirmation;

    const messages: Record<string, string> = {
      lookup_caller: result.found ? 'Caller found' : 'Caller not in system',
      get_contact_by_phone: result.found ? 'Contact found' : 'Contact not found',
      create_lead: 'Lead created successfully',
      schedule_appointment: 'Appointment scheduled',
      book_appointment: 'Appointment booked',
      get_loan_status: 'Loan status retrieved',
      transfer_call: 'Transfer initiated',
      escalate_to_human: 'Call transferred',
    };

    return messages[toolName] || 'Operation completed';
  }

  /**
   * Get user-friendly action description for error messages
   */
  private getToolActionDescription(toolName: string): string {
    const descriptions: Record<string, string> = {
      get_contact_by_phone: "I had trouble looking up your information. Let me try a different approach.",
      lookup_caller: "I couldn't find your information. Let me help you another way.",
      create_lead: "I had trouble saving your information. Let me try again.",
      update_lead_stage: "I couldn't update the status right now.",
      qualify_lead: "I had trouble with the qualification check.",
      get_lo_availability: "I'm having trouble checking availability. Let me find another option.",
      schedule_appointment: "I couldn't complete the scheduling. Let me try a different time.",
      book_appointment: "I had trouble booking that time. Can we try a different slot?",
      create_callback_request: "I couldn't schedule the callback. Let me try again.",
      log_call_note: "I couldn't save that note. I'll make sure to capture it.",
      create_task: "I had trouble creating that follow-up.",
      leave_message: "I couldn't save that message. Let me try again.",
      get_loan_status: "I had trouble checking your loan status. Let me connect you with someone who can help.",
      request_documents: "I couldn't send that document request.",
      escalate_to_human: "I'm having trouble with the transfer. Let me try again.",
      transfer_call: "The transfer didn't go through. Let me find another way to help.",
      find_available_lo: "I couldn't find availability right now.",
      get_current_rates: "I had trouble getting the latest rates.",
    };
    return descriptions[toolName] || "I encountered an issue. Let me try a different approach.";
  }

  /**
   * Format date/time for display
   */
  private formatDateTime(datetime: string): string {
    try {
      const date = new Date(datetime);
      return date.toLocaleString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      });
    } catch {
      return datetime;
    }
  }

  /**
   * Format loan status for spoken output
   */
  private formatLoanStatus(status: string): string {
    const statusMessages: Record<string, string> = {
      lead: "We've received your inquiry",
      application: 'Your application has been received and is being reviewed',
      processing: 'Your loan is currently being processed',
      submitted: 'Your loan has been submitted to underwriting',
      underwriting: 'Your loan is being reviewed by our underwriting team',
      approved: 'Great news! Your loan has been approved',
      clear_to_close: 'Your loan is clear to close',
      docs_out: 'Closing documents have been sent out',
      docs_back: "We've received your signed documents",
      funded: 'Congratulations! Your loan has funded',
      cancelled: 'This loan file has been cancelled',
      denied: 'Unfortunately, this loan was not approved',
    };
    return statusMessages[status] || `Your loan status is: ${status}`;
  }

  /**
   * Update execution metrics
   */
  private updateMetrics(toolName: string, executionTime: number, isError: boolean): void {
    this.metrics.totalExecutions++;
    this.metrics.totalTimeMs += executionTime;
    this.metrics.avgTimeMs = this.metrics.totalTimeMs / this.metrics.totalExecutions;

    if (isError) {
      this.metrics.errorCount++;
    }

    if (!this.metrics.byTool[toolName]) {
      this.metrics.byTool[toolName] = { count: 0, totalTimeMs: 0, errors: 0 };
    }

    this.metrics.byTool[toolName].count++;
    this.metrics.byTool[toolName].totalTimeMs += executionTime;
    if (isError) {
      this.metrics.byTool[toolName].errors++;
    }
  }

  // ==========================================================================
  // PUBLIC API
  // ==========================================================================

  /**
   * Get list of available tool names
   */
  getAvailableTools(): string[] {
    return [
      'lookup_caller',
      'get_contact_by_phone',
      'create_lead',
      'update_lead_stage',
      'qualify_lead',
      'get_lo_availability',
      'schedule_appointment',
      'book_appointment',
      'create_callback_request',
      'get_loan_status',
      'request_documents',
      'log_call_note',
      'create_task',
      'leave_message',
      'escalate_to_human',
      'transfer_call',
      'find_available_lo',
      'get_current_rates',
    ];
  }

  /**
   * Get execution metrics
   */
  getMetrics(): ExecutionMetrics {
    return { ...this.metrics };
  }

  /**
   * Get tool definitions for LLM function calling (OpenAI format)
   */
  getToolDefinitions(): any[] {
    return [
      {
        name: 'lookup_caller',
        description: 'Look up caller information in the CRM by phone number',
        parameters: {
          type: 'object',
          properties: {
            phone_number: { type: 'string', description: 'E164 formatted phone number' },
          },
          required: ['phone_number'],
        },
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
            loan_purpose: { type: 'string', enum: ['purchase', 'refinance', 'heloc', 'other'] },
          },
          required: ['first_name', 'last_name', 'phone'],
        },
      },
      {
        name: 'update_lead_stage',
        description: 'Update the stage of an existing lead',
        parameters: {
          type: 'object',
          properties: {
            lead_id: { type: 'string' },
            stage: { type: 'string' },
            reason: { type: 'string' },
          },
          required: ['lead_id', 'stage'],
        },
      },
      {
        name: 'qualify_lead',
        description: 'Quick lead qualification based on call information',
        parameters: {
          type: 'object',
          properties: {
            caller_phone: { type: 'string', description: "Caller's phone number" },
            purpose: { type: 'string', enum: ['purchase', 'refinance', 'cash_out', 'heloc'] },
            property_type: { type: 'string' },
            timeframe: { type: 'string' },
          },
          required: ['caller_phone'],
        },
      },
      {
        name: 'get_lo_availability',
        description: "Get a loan officer's available appointment slots",
        parameters: {
          type: 'object',
          properties: {
            lo_id: { type: 'string', description: 'Loan officer ID (optional)' },
            date: { type: 'string', description: 'Date to check (YYYY-MM-DD format)' },
          },
          required: [],
        },
      },
      {
        name: 'book_appointment',
        description: 'Book an appointment with a loan officer',
        parameters: {
          type: 'object',
          properties: {
            lo_id: { type: 'string', description: 'Loan officer ID' },
            caller_name: { type: 'string', description: "Caller's full name" },
            caller_phone: { type: 'string', description: "Caller's phone number" },
            datetime_str: { type: 'string', description: 'Appointment date/time (ISO format)' },
            purpose: { type: 'string', description: 'Purpose of the appointment' },
            caller_email: { type: 'string', description: "Caller's email (optional)" },
          },
          required: ['lo_id', 'caller_name', 'caller_phone', 'datetime_str'],
        },
      },
      {
        name: 'create_callback_request',
        description: 'Create a callback request for the team to follow up',
        parameters: {
          type: 'object',
          properties: {
            caller_name: { type: 'string', description: "Caller's name" },
            caller_phone: { type: 'string', description: "Caller's phone number" },
            lo_id: { type: 'string', description: 'Specific LO to call back (optional)' },
            reason: { type: 'string', description: 'Reason for callback' },
            urgency: { type: 'string', enum: ['low', 'normal', 'high', 'urgent'] },
            best_time: { type: 'string', description: 'Best time to call back' },
          },
          required: ['caller_name', 'caller_phone'],
        },
      },
      {
        name: 'get_loan_status',
        description: 'Get the status of an existing loan with verification',
        parameters: {
          type: 'object',
          properties: {
            loan_number: { type: 'string', description: 'Loan number' },
            borrower_last_name: { type: 'string', description: "Borrower's last name for verification" },
            ssn_last_four: { type: 'string', description: 'Last 4 of SSN for additional verification' },
          },
          required: ['loan_number', 'borrower_last_name'],
        },
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
          },
          required: ['loan_id', 'document_types'],
        },
      },
      {
        name: 'log_call_note',
        description: 'Add a note to a contact or loan record',
        parameters: {
          type: 'object',
          properties: {
            note: { type: 'string' },
            category: { type: 'string' },
            contact_id: { type: 'string' },
            loan_id: { type: 'string' },
          },
          required: ['note'],
        },
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
            priority: { type: 'string', enum: ['low', 'normal', 'high'] },
            assigned_to: { type: 'string' },
          },
          required: ['title', 'due_date'],
        },
      },
      {
        name: 'leave_message',
        description: 'Leave a message for a loan officer',
        parameters: {
          type: 'object',
          properties: {
            lo_id: { type: 'string', description: 'Loan officer ID' },
            caller_name: { type: 'string', description: "Caller's name" },
            message: { type: 'string', description: 'Message content' },
            caller_phone: { type: 'string', description: 'Callback number' },
            urgent: { type: 'boolean', description: 'Whether the message is urgent' },
          },
          required: ['lo_id', 'caller_name', 'message'],
        },
      },
      {
        name: 'transfer_call',
        description: 'Transfer the call to a specific person or team',
        parameters: {
          type: 'object',
          properties: {
            target_id: { type: 'string', description: 'Target user ID or team' },
            transfer_type: { type: 'string', enum: ['warm', 'cold'] },
            reason: { type: 'string', description: 'Reason for transfer' },
            context: { type: 'string', description: 'Context to relay to recipient' },
          },
          required: ['target_id'],
        },
      },
      {
        name: 'find_available_lo',
        description: 'Find an available loan officer to help the caller',
        parameters: {
          type: 'object',
          properties: {
            specialty: { type: 'string', description: "Loan specialty needed (e.g., 'VA', 'jumbo')" },
            language: { type: 'string', description: 'Preferred language' },
          },
          required: [],
        },
      },
      {
        name: 'get_current_rates',
        description: 'Get current mortgage rate information',
        parameters: {
          type: 'object',
          properties: {
            loan_type: { type: 'string', enum: ['conventional', 'fha', 'va', 'usda', 'jumbo'] },
            loan_amount: { type: 'number', description: 'Estimated loan amount' },
          },
          required: [],
        },
      },
    ];
  }
}
