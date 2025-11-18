// voice-orchestrator/src/tools/executor.ts
// CRM Tool Executor - Production Version
// TODO: This is a working stub. Replace with full implementation from your Voice OS spec.

import { CRMAPIClient } from '../crm/client';
import { logger } from '../utils/logger';

interface ToolCall {
  name: string;
  arguments: Record<string, any>;
}

interface ExecutionContext {
  callId: string;
  contactId?: string;
  agentId?: string;
}

export class ToolExecutor {
  constructor(private crmClient: CRMAPIClient) {}

  /**
   * Execute a CRM tool
   * TODO: Replace with full implementation from Voice OS spec (tool-executor.ts)
   */
  async execute(
    toolName: string,
    args: Record<string, any>,
    context: ExecutionContext
  ): Promise<any> {
    logger.info('Executing tool', { tool: toolName, args, context });

    try {
      switch (toolName) {
        case 'get_contact_by_phone':
          return await this.crmClient.findContactByPhone(args.phone_number);

        case 'create_lead':
          const lead = await this.crmClient.createLead({
            ...args,
            source: 'voice_ai',
            stage: 'new'
          });
          logger.info('Lead created via voice AI', { leadId: lead.id, callId: context.callId });
          return lead;

        case 'update_lead_stage':
          return await this.crmClient.updateLeadStage(args.lead_id, args.stage, {
            reason: args.reason,
            updated_by: 'voice_ai',
            call_id: context.callId
          });

        case 'schedule_appointment':
          const appointment = await this.crmClient.createAppointment({
            ...args,
            scheduled_by: 'voice_ai',
            status: 'scheduled',
            call_id: context.callId
          });

          // Send confirmation SMS
          if (appointment.contact?.phone) {
            await this.crmClient.sendSMS({
              to: appointment.contact.phone,
              message: `Your appointment is confirmed for ${this.formatDateTime(args.datetime)}.`
            });
          }

          return appointment;

        case 'log_call_note':
          return await this.crmClient.logCallNote({
            contact_id: args.contact_id || context.contactId,
            loan_id: args.loan_id,
            note: args.note,
            category: args.category || 'general',
            source: 'voice_ai',
            call_id: context.callId
          });

        case 'create_task':
          const task = await this.crmClient.createTask({
            ...args,
            contact_id: args.contact_id || context.contactId,
            created_by: 'voice_ai',
            status: 'pending',
            call_id: context.callId
          });

          logger.info('Task created via voice AI', { taskId: task.id, callId: context.callId });
          return task;

        case 'get_loan_status':
          const loan = await this.crmClient.getLoanStatus(args.loan_id);
          return {
            loan_id: loan.id,
            borrower_name: loan.borrower_name,
            property_address: loan.property_address,
            loan_amount: loan.loan_amount,
            current_stage: loan.stage,
            last_updated: loan.updated_at
          };

        case 'request_documents':
          const request = await this.crmClient.requestDocuments({
            loan_id: args.loan_id,
            document_types: args.document_types,
            urgent: args.urgent || false,
            requested_by: 'voice_ai',
            call_id: context.callId
          });

          logger.info('Documents requested via voice AI', {
            requestId: request.id,
            loanId: args.loan_id,
            callId: context.callId
          });

          return request;

        case 'escalate_to_human':
          const escalation = await this.crmClient.createEscalation({
            call_id: context.callId,
            contact_id: context.contactId,
            reason: args.reason,
            department: args.department || 'support',
            priority: args.priority || 'normal',
            status: 'pending'
          });

          logger.info('Call escalated to human', {
            escalationId: escalation.id,
            callId: context.callId
          });

          return {
            success: true,
            message: 'Transferring you now. Please hold.',
            escalation_id: escalation.id
          };

        default:
          throw new Error(`Unknown tool: ${toolName}`);
      }
    } catch (error) {
      logger.error('Tool execution failed', { tool: toolName, args, error });

      // Return user-friendly error message
      return {
        error: true,
        message: `I encountered an issue while ${this.getToolActionDescription(toolName)}. Let me try a different approach.`,
        details: error instanceof Error ? error.message : String(error)
      };
    }
  }

  private getToolActionDescription(toolName: string): string {
    const descriptions: Record<string, string> = {
      'get_contact_by_phone': 'looking up your information',
      'create_lead': 'creating your profile',
      'update_lead_stage': 'updating your status',
      'schedule_appointment': 'scheduling your appointment',
      'log_call_note': 'saving this information',
      'create_task': 'creating a follow-up',
      'get_loan_status': 'checking your loan status',
      'request_documents': 'sending the document request',
      'escalate_to_human': 'transferring you'
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

  /**
   * Get list of available tool names
   */
  getAvailableTools(): string[] {
    return [
      'get_contact_by_phone',
      'create_lead',
      'update_lead_stage',
      'schedule_appointment',
      'log_call_note',
      'create_task',
      'get_loan_status',
      'request_documents',
      'escalate_to_human'
    ];
  }

  /**
   * Get tool definitions for LLM function calling
   */
  getToolDefinitions(): any[] {
    return [
      {
        name: 'get_contact_by_phone',
        description: 'Look up a contact in the CRM by phone number',
        parameters: {
          type: 'object',
          properties: {
            phone_number: { type: 'string', description: 'E164 formatted phone number' }
          },
          required: ['phone_number']
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
            loan_purpose: { type: 'string', enum: ['purchase', 'refinance', 'heloc', 'other'] }
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
        name: 'schedule_appointment',
        description: 'Schedule an appointment with a loan officer',
        parameters: {
          type: 'object',
          properties: {
            contact_id: { type: 'string' },
            datetime: { type: 'string', format: 'date-time' },
            duration_minutes: { type: 'integer', default: 30 }
          },
          required: ['contact_id', 'datetime']
        }
      },
      {
        name: 'log_call_note',
        description: 'Add a note to a contact or loan record',
        parameters: {
          type: 'object',
          properties: {
            note: { type: 'string' },
            category: { type: 'string' }
          },
          required: ['note']
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
            due_date: { type: 'string', format: 'date' }
          },
          required: ['title', 'due_date']
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
        name: 'request_documents',
        description: 'Send a document request to a borrower',
        parameters: {
          type: 'object',
          properties: {
            loan_id: { type: 'string' },
            document_types: { type: 'array', items: { type: 'string' } }
          },
          required: ['loan_id', 'document_types']
        }
      },
      {
        name: 'escalate_to_human',
        description: 'Transfer the call to a human',
        parameters: {
          type: 'object',
          properties: {
            reason: { type: 'string' }
          },
          required: ['reason']
        }
      }
    ];
  }
}
