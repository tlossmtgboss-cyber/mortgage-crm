// voice-orchestrator/src/crm/client.ts
// CRM API Client for integrating with Pipeline 360

import axios, { AxiosInstance } from 'axios';
import { logger } from '../utils/logger';

export class CRMAPIClient {
  private client: AxiosInstance;
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL,
      headers: {
        'Authorization': `Bearer ${process.env.CRM_API_KEY}`,
        'Content-Type': 'application/json'
      },
      timeout: 10000
    });

    // Add request/response interceptors for logging
    this.client.interceptors.request.use(
      (config) => {
        logger.debug('CRM API Request', {
          method: config.method,
          url: config.url,
          data: config.data
        });
        return config;
      },
      (error) => {
        logger.error('CRM API Request Error', { error });
        return Promise.reject(error);
      }
    );

    this.client.interceptors.response.use(
      (response) => {
        logger.debug('CRM API Response', {
          status: response.status,
          url: response.config.url
        });
        return response;
      },
      (error) => {
        logger.error('CRM API Response Error', {
          status: error.response?.status,
          url: error.config?.url,
          data: error.response?.data
        });
        return Promise.reject(error);
      }
    );
  }

  // ==================== AGENTS ====================

  async getAgent(agentId: string): Promise<any> {
    const { data } = await this.client.get(`/api/voice/agents/${agentId}`);
    return data;
  }

  async listAgents(params?: { status?: string }): Promise<any[]> {
    const { data } = await this.client.get('/api/voice/agents', { params });
    return data;
  }

  // ==================== CALL SESSIONS ====================

  async createCallSession(callData: any): Promise<any> {
    const { data } = await this.client.post('/api/voice/calls', callData);
    return data;
  }

  async getCall(callId: string): Promise<any> {
    const { data } = await this.client.get(`/api/voice/calls/${callId}`);
    return data;
  }

  async updateCallSession(callId: string, updates: any): Promise<any> {
    const { data } = await this.client.patch(`/api/voice/calls/${callId}`, updates);
    return data;
  }

  async listCalls(params?: {
    agentId?: string;
    status?: string;
    fromDate?: string;
    toDate?: string;
  }): Promise<any[]> {
    const { data } = await this.client.get('/api/voice/calls', { params });
    return data;
  }

  // ==================== CONTACTS ====================

  async findContactByPhone(phoneNumber: string): Promise<any> {
    try {
      const { data } = await this.client.get('/api/contacts/by-phone', {
        params: { phone: phoneNumber }
      });
      return data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null; // Contact not found
      }
      throw error;
    }
  }

  async getContact(contactId: string): Promise<any> {
    const { data } = await this.client.get(`/api/contacts/${contactId}`);
    return data;
  }

  // ==================== LEADS ====================

  async createLead(leadData: any): Promise<any> {
    const { data } = await this.client.post('/api/leads', leadData);
    return data;
  }

  async updateLeadStage(leadId: string, stage: string, metadata?: any): Promise<any> {
    const { data } = await this.client.patch(`/api/leads/${leadId}/stage`, {
      stage,
      ...metadata
    });
    return data;
  }

  // ==================== APPOINTMENTS ====================

  async createAppointment(appointmentData: any): Promise<any> {
    const { data } = await this.client.post('/api/appointments', appointmentData);
    return data;
  }

  // ==================== TASKS ====================

  async createTask(taskData: any): Promise<any> {
    const { data } = await this.client.post('/api/tasks', taskData);
    return data;
  }

  // ==================== NOTES ====================

  async logCallNote(noteData: any): Promise<any> {
    const { data } = await this.client.post('/api/notes', noteData);
    return data;
  }

  // ==================== LOANS ====================

  async getLoan(loanId: string): Promise<any> {
    const { data } = await this.client.get(`/api/loans/${loanId}`);
    return data;
  }

  async getLoanStatus(loanId: string): Promise<any> {
    const { data } = await this.client.get(`/api/loans/${loanId}/status`);
    return data;
  }

  // ==================== DOCUMENTS ====================

  async requestDocuments(requestData: any): Promise<any> {
    const { data } = await this.client.post('/api/documents/request', requestData);
    return data;
  }

  // ==================== ESCALATIONS ====================

  async createEscalation(escalationData: any): Promise<any> {
    const { data } = await this.client.post('/api/voice/escalations', escalationData);
    return data;
  }

  // ==================== NOTIFICATIONS ====================

  async sendNotification(notification: {
    type: string;
    message: string;
    user_id?: string;
    lead_id?: string;
    task_id?: string;
  }): Promise<any> {
    const { data } = await this.client.post('/api/notifications', notification);
    return data;
  }

  async sendSMS(sms: {
    to: string;
    message: string;
  }): Promise<any> {
    const { data } = await this.client.post('/api/sms/send', sms);
    return data;
  }

  async sendEmail(email: {
    to: string;
    subject: string;
    body: string;
  }): Promise<any> {
    const { data } = await this.client.post('/api/email/send', email);
    return data;
  }

  async sendCalendarInvite(invite: {
    contact_email: string;
    datetime: string;
    duration: number;
    meeting_type: string;
    notes?: string;
  }): Promise<any> {
    const { data } = await this.client.post('/api/calendar/invite', invite);
    return data;
  }

  // ==================== AI RECEPTIONIST DASHBOARD ====================

  async logAIReceptionistActivity(activityData: {
    client_name?: string;
    client_phone?: string;
    client_email?: string;
    action_type: string;
    channel?: string;
    message_in?: string;
    message_out?: string;
    confidence_score?: number;
    lead_stage?: string;
    outcome_status?: string;
    conversation_id?: string;
    transcript_url?: string;
    extra_data?: Record<string, any>;
  }): Promise<any> {
    try {
      const { data } = await this.client.post(
        '/api/v1/ai-receptionist/dashboard/activity',
        activityData
      );
      return data;
    } catch (error) {
      logger.warn('Failed to log AI Receptionist activity', { error, activityData });
      // Don't throw - we don't want logging failures to crash the call
      return null;
    }
  }

  // ==================== HEALTH CHECK ====================

  async healthCheck(): Promise<boolean> {
    try {
      const { data } = await this.client.get('/health');
      return data.status === 'healthy';
    } catch (error) {
      return false;
    }
  }
}
