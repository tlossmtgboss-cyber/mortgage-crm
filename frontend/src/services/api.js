import axios from 'axios';

// Use direct Railway URL for production, localhost for development
// Bypassing Vercel proxy due to POST request issues
const isProduction = window.location.hostname.includes('vercel.app');
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
    return response.data;
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
    return response.data;
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
    return response.data;
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
};

// Referral Partners
export const partnersAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/referral-partners/', { params });
    return response.data;
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
    return response.data;
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
    });
    return response.data;
  },
  getMemoryStats: async () => {
    const response = await api.get('/api/v1/ai/memory-stats');
    return response.data;
  },
  completeTask: async (taskId) => {
    const response = await api.post(`/api/v1/ai/complete-task?task_id=${taskId}`);
    return response.data;
  },
  getSuggestions: async () => {
    const response = await api.get('/api/v1/ai/suggestions');
    return response.data;
  },
};

export const conversationsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/conversations', { params });
    return response.data;
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
    return response.data;
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
    return response.data;
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
    return response.data;
  },
  getByRole: async (roleName) => {
    const response = await api.get(`/api/v1/process-templates/?role_name=${encodeURIComponent(roleName)}`);
    return response.data;
  },
  getRoles: async () => {
    const response = await api.get('/api/v1/process-templates/roles');
    return response.data;
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
    return response.data;
  },
  getMilestones: async () => {
    const response = await api.get('/api/v1/onboarding/milestones');
    return response.data;
  },
  getTasks: async (roleId = null, milestoneId = null) => {
    let url = '/api/v1/onboarding/tasks';
    const params = new URLSearchParams();
    if (roleId) params.append('role_id', roleId);
    if (milestoneId) params.append('milestone_id', milestoneId);
    if (params.toString()) url += `?${params.toString()}`;

    const response = await api.get(url);
    return response.data;
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
    return response.data;
  },
  getWorkflowMembers: async () => {
    const response = await api.get('/api/v1/team/workflow-members');
    return response.data;
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
    return response.data;
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

// AI Receptionist Dashboard API
export const aiReceptionistDashboardAPI = {
  // Activity Feed
  getActivityFeed: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/activity/feed', { params });
    return response.data;
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
    return response.data;
  },
  getRealtimeMetrics: async () => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/metrics/realtime');
    return response.data;
  },

  // Skills
  getSkills: async (params = {}) => {
    const response = await api.get('/api/v1/ai-receptionist/dashboard/skills', { params });
    return response.data;
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
    return response.data;
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
    return response.data;
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
    return response.data;
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
    return response.data;
  },
  getActiveSessions: async (userId) => {
    const response = await api.get(`/api/v1/users/${userId}/active-sessions`);
    return response.data;
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
    return response;
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
    return response;
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
    return response;
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

export default api;
