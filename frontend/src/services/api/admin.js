/**
 * Admin, Team, Permissions, Compliance, Onboarding, and Process Templates API calls.
 */
import api, { ensureArray } from './client.js';

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
    // Try team endpoint first, fallback to admin endpoint
    try {
      await api.delete(`/api/v1/team/members/${memberId}`);
    } catch (error) {
      if (error.response?.status === 404) {
        // Fallback to admin delete endpoint
        await api.delete(`/api/v1/admin/users/${memberId}`);
      } else {
        throw error;
      }
    }
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
    const response = await api.get('/api/v1/mobile/notifications', { params });
    return { ...response, data: ensureArray(response.data, 'notifications') };
  },

  // Mark notification as read
  markAsRead: async (notificationId) => {
    const response = await api.patch(`/api/v1/mobile/notifications/${notificationId}/read`);
    return response;
  },

  // Mark all notifications as read
  markAllAsRead: async () => {
    const response = await api.post('/api/v1/mobile/notifications/read-all');
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
