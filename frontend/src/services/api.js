import axios from 'axios';
import { ensureArray } from '../utils/arrayHelpers';

// Use direct Railway URL for production, localhost for development
// Bypassing Vercel proxy due to POST request issues
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
export const API_BASE_URL = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app' // Direct Railway URL
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token and impersonation headers to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add impersonation token if present
    const impersonationData = localStorage.getItem('impersonation');
    if (impersonationData) {
      try {
        const data = JSON.parse(impersonationData);
        if (data.session_token) {
          config.headers['X-Impersonation-Token'] = data.session_token;
        }
      } catch (error) {
        console.error('Error parsing impersonation data:', error);
      }
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle response errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Authentication
export const authAPI = {
  login: async (email, password) => {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);
    const response = await axios.post(`${API_BASE_URL}/token`, formData);
    return response.data;
  },
  register: async (data) => {
    const response = await api.post('/api/v1/register', data);
    return response.data;
  },
};

// Dashboard
export const dashboardAPI = {
  getDashboard: async () => {
    const response = await api.get('/api/v1/dashboard');
    return response.data;
  },
};

// Leads
export const leadsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/leads/', { params });
    return ensureArray(response.data, 'leads');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/leads/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/leads/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/leads/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/leads/${id}`);
  },
};

// Loans
export const loansAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/loans/', { params });
    return ensureArray(response.data, 'loans');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/loans/${id}`);
    return response.data;
  },
  create: async (data) => {
    try {
      console.log('Creating loan with data:', data);
      console.log('API Base URL:', API_BASE_URL);
      console.log('Auth token exists:', !!localStorage.getItem('token'));

      const response = await api.post('/api/v1/loans/', data);
      console.log('Loan created successfully:', response.data);
      return response.data;
    } catch (error) {
      console.error('Loan creation error details:', {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        message: error.message,
        config: {
          url: error.config?.url,
          method: error.config?.method,
          baseURL: error.config?.baseURL
        }
      });

      // If 405 error, try without trailing slash as fallback
      if (error.response?.status === 405) {
        console.log('Retrying without trailing slash...');
        try {
          const retryResponse = await api.post('/api/v1/loans', data);
          console.log('Retry successful:', retryResponse.data);
          return retryResponse.data;
        } catch (retryError) {
          console.error('Retry also failed:', retryError);
          throw retryError;
        }
      }

      throw error;
    }
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/loans/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/loans/${id}`);
  },
};

// Tasks
export const tasksAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/tasks/', { params });
    return ensureArray(response.data, 'tasks');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/tasks/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/tasks/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/tasks/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/tasks/${id}`);
  },
  delegate: async (id, delegateToId) => {
    const response = await api.post(`/api/v1/tasks/${id}/delegate`, { delegate_to_id: delegateToId });
    return response.data;
  },
};

// Referral Partners
export const partnersAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/referral-partners/', { params });
    return ensureArray(response.data, 'partners');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/referral-partners/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/referral-partners/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/referral-partners/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/referral-partners/${id}`);
  },
};

// MUM Clients
export const mumAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/mum/clients', { params });
    return response.data.clients || [];
  },
  getMetrics: async () => {
    const response = await api.get('/api/v1/mum/metrics');
    return response.data;
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/mum-clients/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/mum-clients/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/mum-clients/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/mum-clients/${id}`);
  },
};

// Activities
export const activitiesAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/activities/', { params });
    return ensureArray(response.data, 'activities');
  },
  create: async (data) => {
    const response = await api.post('/api/v1/activities/', data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/activities/${id}`);
  },
};

// Analytics
export const analyticsAPI = {
  getConversionFunnel: async () => {
    const response = await api.get('/api/v1/analytics/conversion-funnel');
    return response.data;
  },
  getPipeline: async () => {
    const response = await api.get('/api/v1/analytics/pipeline');
    return response.data;
  },
  getScorecard: async () => {
    const response = await api.get('/api/v1/scorecard');
    return response.data;
  },
};

// AI Assistant & Conversations
export const aiAPI = {
  chat: async (message, context = {}) => {
    const response = await api.post('/api/v1/ai/chat', {
      message,
      lead_id: context.lead_id,
      loan_id: context.loan_id,
      context: context.metadata,
    });
    return response.data;
  },
  smartChat: async (message, context = {}) => {
    const response = await api.post('/api/v1/ai/smart-chat', {
      message,
      lead_id: context.lead_id,
      loan_id: context.loan_id,
      include_context: context.include_context !== false, // Default to true
      coaching_mode: context.coaching_mode,
      context_type: context.context_type,
    });
    return response.data;
  },
  getMemoryStats: async () => {
    const response = await api.get('/api/v1/ai/memory-stats');
    return response.data;
  },
  coach: async (mode, message = null) => {
    const response = await api.post('/api/v1/coach', {
      mode: mode,
      message: message
    });
    return response.data;
  },
  completeTask: async (taskId) => {
    const response = await api.post(`/api/v1/ai/complete-task?task_id=${taskId}`);
    return response.data;
  },
  getSuggestions: async () => {
    const response = await api.get('/api/v1/ai/suggestions');
    return ensureArray(response.data, 'suggestions');
  },
  processCommand: async (message, context = {}) => {
    // Detect coaching mode from message
    const coachingKeywords = [
      'daily briefing', 'pipeline audit', 'focus reset', 'what should i do',
      'accountability review', 'tough love', 'teach me', 'priorities',
      'what are my', 'help me focus', 'review my performance'
    ];
    const isCoachingMode = coachingKeywords.some(kw =>
      message.toLowerCase().includes(kw)
    );

    // Fetch user context for better AI responses
    let userContext = {};
    try {
      const [tasksRes, pipelineRes, profileRes] = await Promise.all([
        api.get('/api/v1/ai/context/tasks').catch(() => ({ data: null })),
        api.get('/api/v1/ai/context/pipeline').catch(() => ({ data: null })),
        api.get('/api/v1/ai/context/user/profile').catch(() => ({ data: null }))
      ]);

      userContext = {
        tasks: tasksRes.data,
        pipeline: pipelineRes.data,
        profile: profileRes.data
      };
    } catch (e) {
      console.warn('Failed to fetch user context:', e);
    }

    // Use the AgentOrchestrator-powered endpoint for smarter responses
    const response = await api.post('/api/v1/ai/orchestrator-chat', {
      message,
      context: {
        coaching_mode: isCoachingMode,
        user_context: userContext
      }
    });

    // Map orchestrator response to expected format
    const data = response.data;
    return {
      explanation: data.response || '',
      intent: data.intent,
      entities: data.entities,
      agent_used: data.agent_used,
      confidence: data.confidence,
      execution_id: data.execution_id,
      fallback: data.fallback,
      // For backwards compatibility
      success: true,
      ...data
    };
  },
  // Streaming version of processCommand for real-time responses
  processCommandStream: async (message, onContent, onStatus, onDone, onError) => {
    const token = localStorage.getItem('token');

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai/orchestrator-chat-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ message })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'content' && onContent) {
                onContent(data.content);
              } else if (data.type === 'status' && onStatus) {
                onStatus(data.content);
              } else if (data.type === 'done' && onDone) {
                // Pass full response and any additional data (like prioritized_tasks)
                onDone(data.full_response, data);
              } else if (data.type === 'error' && onError) {
                onError(data.content);
              }
            } catch (e) {
              console.warn('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
      if (onError) onError(error.message);
    }
  },
  executeAction: async (actionId, modifications = {}, sessionId = null) => {
    const response = await api.post('/api/v1/ai/execute-action', {
      action_id: actionId,
      session_id: sessionId,
      modifications,
    });
    return response.data;
  },
  parseScreenshot: async (imageFile) => {
    const formData = new FormData();
    formData.append('image', imageFile);
    const response = await api.post('/api/v1/ai/parse-screenshot', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  createLeadFromScreenshot: async (leadData) => {
    const response = await api.post('/api/v1/ai/create-lead-from-screenshot', leadData);
    return response.data;
  },
};

export const conversationsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/conversations', { params });
    return ensureArray(response.data, 'conversations');
  },
  create: async (data) => {
    const response = await api.post('/api/v1/conversations/', data);
    return response.data;
  },
};

// Portfolio
export const portfolioAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/portfolio/', { params });
    return ensureArray(response.data, 'portfolio');
  },
  getStats: async () => {
    const response = await api.get('/api/v1/portfolio/stats');
    return response.data;
  },
};

// Calendar Events
export const calendarAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/calendar/events', { params });
    return ensureArray(response.data, 'events');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/calendar/events/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/calendar/events', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/calendar/events/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/calendar/events/${id}`);
  },
};

// Process Templates API
export const processTemplatesAPI = {
  getAll: async () => {
    const response = await api.get('/api/v1/process-templates/');
    return ensureArray(response.data, 'templates');
  },
  getByRole: async (roleName) => {
    const response = await api.get(`/api/v1/process-templates/?role_name=${encodeURIComponent(roleName)}`);
    return ensureArray(response.data, 'templates');
  },
  getRoles: async () => {
    const response = await api.get('/api/v1/process-templates/roles');
    return ensureArray(response.data, 'roles');
  },
  create: async (data) => {
    const response = await api.post('/api/v1/process-templates/', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.patch(`/api/v1/process-templates/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/v1/process-templates/${id}`);
  },
  analyzeEfficiency: async (roleName = null) => {
    const url = roleName
      ? `/api/v1/process-templates/analyze-efficiency?role_name=${encodeURIComponent(roleName)}`
      : '/api/v1/process-templates/analyze-efficiency';
    const response = await api.post(url);
    return response.data;
  },
  seedDefaults: async () => {
    const response = await api.post('/api/v1/process-templates/seed-defaults');
    return response.data;
  },
};

// Onboarding API
export const onboardingAPI = {
  parseDocumentsUpload: async (files) => {
    // Upload actual files (PDFs, DOCX, etc.) to be parsed
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }

    const response = await api.post('/api/v1/onboarding/parse-documents-upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return response.data;
  },
  parseDocuments: async (documentContent, documentName = null, documentType = null) => {
    const response = await api.post('/api/v1/onboarding/parse-documents', {
      document_content: documentContent,
      document_name: documentName,
      document_type: documentType
    });
    return response.data;
  },
  getRoles: async () => {
    const response = await api.get('/api/v1/onboarding/roles');
    return ensureArray(response.data, 'roles');
  },
  getMilestones: async () => {
    const response = await api.get('/api/v1/onboarding/milestones');
    return ensureArray(response.data, 'milestones');
  },
  getTasks: async (roleId = null, milestoneId = null) => {
    let url = '/api/v1/onboarding/tasks';
    const params = new URLSearchParams();
    if (roleId) params.append('role_id', roleId);
    if (milestoneId) params.append('milestone_id', milestoneId);
    if (params.toString()) url += `?${params.toString()}`;

    const response = await api.get(url);
    return ensureArray(response.data, 'tasks');
  },
  updateTask: async (taskId, data) => {
    const response = await api.patch(`/api/v1/onboarding/tasks/${taskId}`, data);
    return response.data;
  },
  bulkUpdateTasks: async (tasks) => {
    const response = await api.patch('/api/v1/onboarding/tasks/bulk-update', tasks);
    return response.data;
  },
  createTask: async (data) => {
    const response = await api.post('/api/v1/onboarding/tasks', data);
    return response.data;
  },
  getProgress: async () => {
    const response = await api.get('/api/v1/onboarding/progress');
    return response.data;
  },
  updateProgress: async (data) => {
    const response = await api.post('/api/v1/onboarding/progress', data);
    return response.data;
  },
  complete: async () => {
    const response = await api.post('/api/v1/onboarding/complete');
    return response.data;
  },
};

// Team API
export const teamAPI = {
  getMembers: async () => {
    const response = await api.get('/api/v1/team/members');
    return ensureArray(response.data, 'team_members');
  },
  getWorkflowMembers: async () => {
    const response = await api.get('/api/v1/team/workflow-members');
    return ensureArray(response.data, 'members');
  },
  getMemberDetail: async (userId) => {
    const response = await api.get(`/api/v1/team/members/${userId}`);
    return response.data;
  },
  createMember: async (data) => {
    const response = await api.post('/api/v1/team/members', data);
    return response.data;
  },
  updateMember: async (memberId, data) => {
    const response = await api.patch(`/api/v1/team/members/${memberId}`, data);
    return response.data;
  },
  deleteMember: async (memberId) => {
    await api.delete(`/api/v1/team/members/${memberId}`);
  },
};

// Voice AI Receptionist
export const voiceAPI = {
  makeCall: async (data) => {
    const response = await api.post('/api/v1/voice/make-call', data);
    return response.data;
  },
  getCallHistory: async (params = {}) => {
    const response = await api.get('/api/v1/voice/call-history', { params });
    return ensureArray(response.data, 'calls');
  },
  getCallStats: async () => {
    const response = await api.get('/api/v1/voice/call-stats');
    return response.data;
  },
  getConfig: async () => {
    const response = await api.get('/api/v1/voice/ai-receptionist-config');
    return response.data;
  },
  updateConfig: async (data) => {
    const response = await api.post('/api/v1/voice/ai-receptionist-config', data);
    return response.data;
  },
  dropVoicemail: async (data) => {
    const response = await api.post('/api/v1/voice/drop-voicemail', data);
    return response.data;
  },
};

// Voicemail Drop System API
export const voicemailAPI = {
  // Drop a single voicemail
  drop: async (data) => {
    const response = await api.post('/api/v1/voicemail/drop', data);
    return response.data;
  },

  // Transcribe voice recording
  transcribe: async (formData) => {
    const response = await api.post('/api/v1/voicemail/transcribe', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    return response.data;
  },

  // Get voicemail templates
  getTemplates: async (category = null) => {
    const params = category ? { category } : {};
    const response = await api.get('/api/v1/voicemail/templates', { params });
    return ensureArray(response.data, 'templates');
  },

  // Create voicemail template
  createTemplate: async (data) => {
    const response = await api.post('/api/v1/voicemail/templates', data);
    return response.data;
  },

  // Get voicemail history
  getHistory: async (params = {}) => {
    const response = await api.get('/api/v1/voicemail/history', { params });
    return ensureArray(response.data, 'history');
  },

  // Get voicemail analytics
  getAnalytics: async (startDate = null, endDate = null) => {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get('/api/v1/voicemail/analytics', { params });
    return response.data;
  },
};

// AI Receptionist Dashboard API
export const aiReceptionistDashboardAPI = {
  // Activity Feed
  getActivityFeed: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/activity/feed', { params });
    return ensureArray(response.data, 'activities');
  },
  getActivityCount: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/activity/count', { params });
    return response.data;
  },

  // Metrics
  getDailyMetrics: async (startDate, endDate) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/metrics/daily', {
      params: { start_date: startDate, end_date: endDate }
    });
    return ensureArray(response.data, 'metrics');
  },
  getRealtimeMetrics: async () => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/metrics/realtime');
    return response.data;
  },

  // Skills
  getSkills: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/skills', { params });
    return ensureArray(response.data, 'skills');
  },
  getSkillDetail: async (skillName) => {
    const response = await api.get(`/api/v1/ai-receptionist/dashboard/skills/${skillName}`);
    return response.data;
  },

  // ROI
  getROI: async (startDate = null, endDate = null) => {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get('/api/v1/ai-receptionist/dashboard/roi', { params });
    return response.data;
  },

  // Errors
  getErrors: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/errors', { params });
    return ensureArray(response.data, 'errors');
  },
  approveErrorFix: async (errorId) => {
    const response = await api.post(`/api/v1/ai-receptionist/dashboard/errors/${errorId}/approve-fix`);
    return response.data;
  },

  // System Health
  getSystemHealth: async () => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/system-health');
    return response.data;
  },
  getComponentHealth: async (componentName) => {
    const response = await api.get(`/api/v1/ai-receptionist/dashboard/system-health/${componentName}`);
    return response.data;
  },

  // Conversations
  getConversations: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/conversations', { params });
    return ensureArray(response.data, 'conversations');
  },
  getConversationDetail: async (conversationId) => {
    const response = await api.get(`/api/v1/ai-receptionist/dashboard/conversations/${conversationId}`);
    return response.data;
  },
};

// Permissions API
export const permissionsAPI = {
  getUserPermissions: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/permissions`);
    return response.data;
  },
  getUserTemplate: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/permissions/template`);
    return response.data;
  },
  getAvailablePermissions: async () => {
    const response = await api.get('/api/v1/permissions/available');
    return ensureArray(response.data, 'permissions');
  },
  applyTemplate: async (userId, templateName) => {
    const response = await api.post(`/api/v1/users/${userId}/permissions/apply-template`, {
      template_name: templateName
    });
    return response.data;
  },
  updatePermissions: async (userId, permissions) => {
    const response = await api.put(`/api/v1/users/${userId}/permissions`, {
      permissions
    });
    return response.data;
  },
};

// Impersonation API
export const impersonationAPI = {
  start: async (data) => {
    const response = await api.post('/api/v1/impersonation/start', data);
    return response.data;
  },
  end: async () => {
    const response = await api.post('/api/v1/impersonation/end');
    return response.data;
  },
  getCurrent: async () => {
    const response = await api.get('/api/v1/impersonation/current');
    return response.data;
  },
};

// Audit & Access API (Tab 6)
export const accessAuditAPI = {
  getAuditLog: async (userId, startDate = null, endDate = null, changeType = null, search = null, limit = 50, offset = 0) => {
    const params = { limit, offset };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (changeType) params.change_type = changeType;
    if (search) params.search = search;
    const response = await api.get(`/api/v1/users/${userId}/audit-log`, { params });
    return response.data;
  },
  getImpersonationHistory: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/impersonation-history`);
    return ensureArray(response.data, 'history');
  },
  getActiveSessions: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/active-sessions`);
    return ensureArray(response.data, 'sessions');
  },
  revokeSession: async (userId, sessionId, reason = null) => {
    const response = await api.delete(`/api/v1/users/${userId}/sessions/${sessionId}`, {
      data: { reason }
    });
    return response.data;
  },
  revokeAllSessions: async (userId, reason) => {
    const response = await api.delete(`/api/v1/users/${userId}/sessions`, {
      data: { reason }
    });
    return response.data;
  },
  emergencyRevoke: async (userId, data) => {
    const response = await api.post(`/api/v1/users/${userId}/emergency-revoke`, data);
    return response.data;
  },
};

// Legacy alias for backward compatibility
export const auditAPI = accessAuditAPI;

// Permission Request API
export const permissionsApi = {
  // Get user's current permissions
  getUserPermissions: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/permissions`);
    return response;
  },

  // Get all available permissions
  getAvailablePermissions: async () => {
    const response = await api.get('/api/v1/permissions/available');
    return response;
  },

  // Get my permission requests
  getMyPermissionRequests: async (status = null) => {
    const params = status ? { status } : {};
    const response = await api.get('/api/v1/permission-requests', { params });
    return response;
  },

  // Create a new permission request
  createPermissionRequest: async (data) => {
    const response = await api.post('/api/v1/permission-requests', data);
    return response;
  },

  // Approve a permission request (manager only)
  approvePermissionRequest: async (requestId, notes = '') => {
    const response = await api.put(`/api/v1/permission-requests/${requestId}/approve`, { notes });
    return response;
  },

  // Deny a permission request (manager only)
  denyPermissionRequest: async (requestId, reason) => {
    const response = await api.put(`/api/v1/permission-requests/${requestId}/deny`, { reason });
    return response;
  },
};

// Notifications API
export const notificationsApi = {
  // Get notifications
  getNotifications: async (unreadOnly = false, limit = 50) => {
    const params = { unread_only: unreadOnly, limit };
    const response = await api.get('/api/v1/notifications', { params });
    return { ...response, data: ensureArray(response.data, 'notifications') };
  },

  // Mark notification as read
  markAsRead: async (notificationId) => {
    const response = await api.put(`/api/v1/notifications/${notificationId}/read`);
    return response;
  },

  // Mark all notifications as read
  markAllAsRead: async () => {
    const response = await api.put('/api/v1/notifications/read-all');
    return response;
  },
};

// Certifications API
export const certificationsApi = {
  // Get due certifications for manager's team
  getDueCertifications: async (status = null) => {
    const params = status ? { status } : {};
    const response = await api.get('/api/v1/certifications/due', { params });
    return { ...response, data: ensureArray(response.data, 'certifications') };
  },

  // Get certification details
  getCertificationDetails: async (certId) => {
    const response = await api.get(`/api/v1/certifications/${certId}`);
    return response;
  },

  // Certify employee access
  certifyAccess: async (certId, data) => {
    const response = await api.post(`/api/v1/certifications/${certId}/certify`, data);
    return response;
  },

  // Skip certification
  skipCertification: async (certId, data) => {
    const response = await api.post(`/api/v1/certifications/${certId}/skip`, data);
    return response;
  },

  // Get certification history for employee
  getCertificationHistory: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/certifications/history`);
    return { ...response, data: ensureArray(response.data, 'history') };
  },
};

// Compliance Dashboard API
export const complianceApi = {
  // Get compliance overview metrics
  getOverview: async () => {
    const response = await api.get('/api/v1/compliance/overview');
    return response;
  },

  // Get certifications by department
  getCertificationsByDepartment: async () => {
    const response = await api.get('/api/v1/compliance/certifications/by-department');
    return response;
  },

  // Export compliance report
  exportReport: async (format = 'csv') => {
    const response = await api.get('/api/v1/compliance/export', {
      params: { format },
      responseType: 'blob'
    });
    return response;
  },
};

// Circle of Cashflow API
export const circleOfCashflowAPI = {
  // Opportunities
  getOpportunities: async (contactId = null) => {
    const params = contactId ? { contact_id: contactId } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/opportunities', { params });
    return response.data;
  },
  acknowledgeOpportunity: async (opportunityId, data) => {
    const response = await api.post(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/acknowledge`, data);
    return response.data;
  },
  suggestPartner: async (opportunityId) => {
    const response = await api.get(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/suggest-partner`);
    return response.data;
  },
  sendIntroduction: async (opportunityId, partnerId, method = 'email') => {
    const response = await api.post(`/api/v1/circle-of-cashflow/opportunities/${opportunityId}/send?partner_id=${partnerId}&introduction_method=${method}`);
    return response.data;
  },

  // Partners
  getPartners: async (category = null) => {
    const params = category ? { category } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/partners', { params });
    return response.data;
  },

  // Referrals
  getReferrals: async (contactId = null) => {
    const params = contactId ? { contact_id: contactId } : {};
    const response = await api.get('/api/v1/circle-of-cashflow/referrals', { params });
    return response.data;
  },
  createReferral: async (data) => {
    const response = await api.post('/api/v1/circle-of-cashflow/referrals', data);
    return response.data;
  },

  // Questionnaires
  submitQuestionnaire: async (data) => {
    const response = await api.post('/api/v1/circle-of-cashflow/questionnaires', data);
    return response.data;
  },
  getQuestionnaire: async (id) => {
    const response = await api.get(`/api/v1/circle-of-cashflow/questionnaires/${id}`);
    return response.data;
  },
};

// Profitability Intelligence
export const profitabilityAPI = {
  // Dashboard
  getDashboard: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/dashboard', { params });
    return response.data;
  },
  getMetrics: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/metrics', { params });
    return response.data;
  },
  getTrends: async (months = 12) => {
    const response = await api.get('/api/v1/profitability/trends', { params: { months } });
    return response.data;
  },

  // Expenses
  getExpenses: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/expenses', { params: filters });
    return response.data;
  },
  createExpense: async (data) => {
    const response = await api.post('/api/v1/profitability/expenses', data);
    return response.data;
  },
  updateExpense: async (id, data) => {
    const response = await api.put(`/api/v1/profitability/expenses/${id}`, data);
    return response.data;
  },
  deleteExpense: async (id) => {
    const response = await api.delete(`/api/v1/profitability/expenses/${id}`);
    return response.data;
  },
  getExpenseCategories: async () => {
    const response = await api.get('/api/v1/profitability/expense-categories');
    return response.data;
  },

  // Roles
  getRoles: async () => {
    const response = await api.get('/api/v1/profitability/roles');
    return response.data;
  },
  createRole: async (data) => {
    const response = await api.post('/api/v1/profitability/roles', data);
    return response.data;
  },
  getRoleProfitability: async (roleId, month = null) => {
    const params = month ? { month } : {};
    const response = await api.get(`/api/v1/profitability/roles/${roleId}/profitability`, { params });
    return response.data;
  },

  // Employees
  getEmployees: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/employees', { params: filters });
    return response.data;
  },
  createEmployee: async (data) => {
    const response = await api.post('/api/v1/profitability/employees', data);
    return response.data;
  },
  updateEmployee: async (id, data) => {
    const response = await api.put(`/api/v1/profitability/employees/${id}`, data);
    return response.data;
  },
  getEmployeePerformance: async (id, month = null) => {
    const params = month ? { month } : {};
    const response = await api.get(`/api/v1/profitability/employees/${id}/performance`, { params });
    return response.data;
  },

  // Loans
  getLoans: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/loans', { params: filters });
    return response.data;
  },
  createLoan: async (data) => {
    const response = await api.post('/api/v1/profitability/loans', data);
    return response.data;
  },
  addLoanAttribution: async (loanId, data) => {
    const response = await api.post(`/api/v1/profitability/loans/${loanId}/attributions`, data);
    return response.data;
  },

  // Revenue
  getRevenue: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/revenue', { params: filters });
    return response.data;
  },
  createRevenue: async (data) => {
    const response = await api.post('/api/v1/profitability/revenue', data);
    return response.data;
  },

  // Scenarios
  getScenarios: async (savedOnly = false) => {
    const response = await api.get('/api/v1/profitability/scenarios', { params: { saved_only: savedOnly } });
    return response.data;
  },
  createScenario: async (data) => {
    const response = await api.post('/api/v1/profitability/scenarios', data);
    return response.data;
  },
  runScenario: async (baseMonth, parameters) => {
    const response = await api.post('/api/v1/profitability/scenarios/run', parameters, {
      params: { base_month: baseMonth }
    });
    return response.data;
  },
  saveScenario: async (id) => {
    const response = await api.put(`/api/v1/profitability/scenarios/${id}/save`);
    return response.data;
  },

  // Snapshots
  getSnapshots: async (limit = 12) => {
    const response = await api.get('/api/v1/profitability/snapshots', { params: { limit } });
    return response.data;
  },
  createSnapshot: async (month) => {
    const response = await api.post('/api/v1/profitability/snapshots', null, { params: { month } });
    return response.data;
  },

  // Insights
  getInsights: async (filters = {}) => {
    const response = await api.get('/api/v1/profitability/insights', { params: filters });
    return response.data;
  },
  generateInsights: async (month) => {
    const response = await api.post('/api/v1/profitability/insights/generate', null, { params: { month } });
    return response.data;
  },
  acknowledgeInsight: async (id) => {
    const response = await api.put(`/api/v1/profitability/insights/${id}/acknowledge`);
    return response.data;
  },

  // Analysis
  getGapsAndGains: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/analysis/gaps-gains', { params });
    return response.data;
  },
  getBreakEvenAnalysis: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/analysis/break-even', { params });
    return response.data;
  },

  // AI Insights
  queryAI: async (question, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/query', { question, month });
    return response.data;
  },
  getAIRecommendations: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/recommendations', { params });
    return response.data;
  },
  analyzeHiring: async (roleName, salary, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/hiring-analysis', {
      role_name: roleName,
      salary: salary,
      month: month
    });
    return response.data;
  },
  getExecutiveDigest: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/executive-digest', { params });
    return response.data;
  },
  getAnomalies: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/anomalies', { params });
    return response.data;
  },
  compareScenarios: async (scenarios, month = null) => {
    const response = await api.post('/api/v1/profitability/ai/compare-scenarios', {
      scenarios: scenarios,
      month: month
    });
    return response.data;
  },
  getQuickInsights: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/profitability/ai/quick-insights', { params });
    return response.data;
  },
  getSuggestedQuestions: async () => {
    const response = await api.get('/api/v1/profitability/ai/suggested-questions');
    return response.data;
  },
};

// Financial Intelligence API (Phase 3)
export const financialIntelligenceAPI = {
  getExecutiveDashboard: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/executive-dashboard', { params });
    return response.data;
  },
  getGainOnSale: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/gain-on-sale', { params });
    return response.data;
  },
  getHedgeAnalysis: async () => {
    const response = await api.get('/api/v1/financial-intelligence/hedge-analysis');
    return response.data;
  },
  getProductProfitability: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/product-profitability', { params });
    return response.data;
  },
  getCostPerLoan: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/cost-per-loan', { params });
    return response.data;
  },
  getCashRunway: async () => {
    const response = await api.get('/api/v1/financial-intelligence/cash-runway');
    return response.data;
  },
  getBreakEven: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/break-even', { params });
    return response.data;
  },
  getWarehouseEfficiency: async () => {
    const response = await api.get('/api/v1/financial-intelligence/warehouse-efficiency');
    return response.data;
  },
  getRateExposure: async () => {
    const response = await api.get('/api/v1/financial-intelligence/rate-exposure');
    return response.data;
  },
  getMSRStatus: async () => {
    const response = await api.get('/api/v1/financial-intelligence/msr-status');
    return response.data;
  },
  getPricingAnalysis: async () => {
    const response = await api.get('/api/v1/financial-intelligence/pricing-analysis');
    return response.data;
  },
  getCashForecast: async () => {
    const response = await api.get('/api/v1/financial-intelligence/cash-forecast');
    return response.data;
  },
  getLiquidity: async () => {
    const response = await api.get('/api/v1/financial-intelligence/liquidity');
    return response.data;
  },
  getCapital: async () => {
    const response = await api.get('/api/v1/financial-intelligence/capital');
    return response.data;
  },
  getComplianceRisks: async () => {
    const response = await api.get('/api/v1/financial-intelligence/compliance-risks');
    return response.data;
  },
  getTechROI: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/tech-roi', { params });
    return response.data;
  },
  getOperationalLosses: async () => {
    const response = await api.get('/api/v1/financial-intelligence/operational-losses');
    return response.data;
  },
  getInvestmentRecommendations: async (month = null) => {
    const params = month ? { month } : {};
    const response = await api.get('/api/v1/financial-intelligence/investment-recommendations', { params });
    return response.data;
  },
};

// Email Signature API
export const emailSignatureAPI = {
  get: async () => {
    const response = await api.get('/api/v1/email-signature');
    return response.data;
  },
  save: async (data) => {
    const response = await api.post('/api/v1/email-signature', data);
    return response.data;
  },
  uploadImage: async (file, imageType) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('image_type', imageType);
    const response = await api.post('/api/v1/email-signature/upload-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },
  getHtml: async () => {
    const response = await api.get('/api/v1/email-signature/html');
    return response.data;
  },
  getPreview: async () => {
    const response = await api.get('/api/v1/email-signature/preview');
    return response.data;
  },
};

// Email Drop API (drag-and-drop email/document processing)
export const emailDropAPI = {
  // Parse email with AI to extract fields and suggest actions
  parse: async (emailData) => {
    const response = await api.post('/api/v1/email-drop/parse', {
      email_data: {
        filename: emailData.filename,
        from: emailData.from,
        to: emailData.to,
        subject: emailData.subject,
        date: emailData.date,
        body: emailData.body,
        raw_content: emailData.rawContent,
        matched_borrower: emailData.matchedBorrower,
        matched_loan_number: emailData.matchedLoanNumber,
        confidence: emailData.confidence
      },
      parse_mode: 'smart'
    });
    return response.data;
  },

  // Process email based on user's chosen action
  process: async (action, emailData, extractedFields, targetEntityId, targetEntityType, createNew, userAnswers) => {
    const response = await api.post('/api/v1/email-drop/process', {
      action,
      email_data: {
        filename: emailData.filename,
        from: emailData.from,
        to: emailData.to,
        subject: emailData.subject,
        date: emailData.date,
        body: emailData.body,
        raw_content: emailData.rawContent,
        matched_borrower: emailData.matchedBorrower,
        matched_loan_number: emailData.matchedLoanNumber,
        confidence: emailData.confidence
      },
      extracted_fields: extractedFields || {},
      target_entity_id: targetEntityId,
      target_entity_type: targetEntityType,
      create_new: createNew || false,
      user_answers: userAnswers || {}
    });
    return response.data;
  },

  // Search for matching leads/loans
  searchMatches: async (searchTerm, email, loanNumber) => {
    const response = await api.post('/api/v1/email-drop/search-matches', {
      search_term: searchTerm,
      email: email,
      loan_number: loanNumber
    });
    return response.data;
  },

  // Health check
  health: async () => {
    const response = await api.get('/api/v1/email-drop/health');
    return response.data;
  }
};

// Document Drop API (drag-and-drop document upload)
export const documentDropAPI = {
  // Upload a document file
  upload: async (file, borrowerId, loanId, docType) => {
    const formData = new FormData();
    formData.append('file', file);
    if (borrowerId) formData.append('borrower_id', borrowerId);
    if (loanId) formData.append('loan_id', loanId);
    if (docType) formData.append('doc_type', docType);

    const response = await api.post('/api/v1/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Classify a document with AI
  classify: async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/api/v1/documents/classify', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Get documents for a borrower or loan
  getDocuments: async (borrowerId, loanId) => {
    const params = {};
    if (borrowerId) params.borrower_id = borrowerId;
    if (loanId) params.loan_id = loanId;

    const response = await api.get('/api/v1/documents/', { params });
    return ensureArray(response.data, 'documents');
  }
};

export default api;
