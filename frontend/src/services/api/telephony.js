/**
 * Telephony API calls — Dialer, Voice AI, Voicemail, Outreach, Call Monitoring.
 */
import api, { API_BASE_URL, ensureArray } from './client.js';
import axios from 'axios';

// Dialer / Click-to-Call API
export const dialerAPI = {
  // Click-to-dial - calls your phone first, then bridges to the contact
  clickToDial: async (data) => {
    const response = await api.post('/api/v1/dialer/click-to-dial', data);
    return response.data;
  },
  // Get agent's telephony settings
  getSettings: async () => {
    const response = await api.get('/api/v1/dialer/settings');
    return response.data;
  },
  // Update agent's telephony settings
  updateSettings: async (data) => {
    const response = await api.put('/api/v1/dialer/settings', data);
    return response.data;
  },
  // Get call history
  getCallLogs: async (params = {}) => {
    const response = await api.get('/api/v1/dialer/call-logs', { params });
    return response.data;
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
  // NOTE: Do NOT set Content-Type manually — axios auto-sets it with the
  // correct multipart boundary when the body is FormData.
  transcribe: async (formData) => {
    const response = await api.post('/api/v1/voicemail/transcribe', formData);
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
    return ensureArray(response.data, 'voicemails');
  },

  // Get voicemail analytics
  getAnalytics: async (startDate = null, endDate = null) => {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const response = await api.get('/api/v1/voicemail/analytics', { params });
    return response.data;
  },

  // Update voicemail template
  updateTemplate: async (templateId, data) => {
    const response = await api.put(`/api/v1/voicemail/templates/${templateId}`, data);
    return response.data;
  },

  // Delete voicemail template
  deleteTemplate: async (templateId) => {
    const response = await api.delete(`/api/v1/voicemail/templates/${templateId}`);
    return response.data;
  },

  // Upload audio for template
  uploadTemplateAudio: async (templateId, formData) => {
    const response = await api.post(`/api/v1/voicemail/templates/${templateId}/upload-audio`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Delete template audio
  deleteTemplateAudio: async (templateId) => {
    const response = await api.delete(`/api/v1/voicemail/templates/${templateId}/audio`);
    return response.data;
  },

  // Preview voice (TTS)
  previewVoice: async (data) => {
    const response = await api.post('/api/v1/voicemail/preview', data, {
      responseType: 'blob',
    });
    return response.data;
  },

  // Campaign CRUD
  getCampaigns: async (params = {}) => {
    const response = await api.get('/api/v1/voicemail/campaigns', { params });
    return ensureArray(response.data, 'campaigns');
  },

  createCampaign: async (data) => {
    const response = await api.post('/api/v1/voicemail/campaigns', data);
    return response.data;
  },

  getCampaign: async (campaignId) => {
    const response = await api.get(`/api/v1/voicemail/campaigns/${campaignId}`);
    return response.data;
  },

  updateCampaign: async (campaignId, data) => {
    const response = await api.put(`/api/v1/voicemail/campaigns/${campaignId}`, data);
    return response.data;
  },

  startCampaign: async (campaignId) => {
    const response = await api.post(`/api/v1/voicemail/campaigns/${campaignId}/start`);
    return response.data;
  },

  pauseCampaign: async (campaignId) => {
    const response = await api.post(`/api/v1/voicemail/campaigns/${campaignId}/pause`);
    return response.data;
  },

  cancelCampaign: async (campaignId) => {
    const response = await api.post(`/api/v1/voicemail/campaigns/${campaignId}/cancel`);
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

// Outreach/Communication API
export const outreachAPI = {
  // Send SMS message
  sendSMS: async (to, message, leadId = null) => {
    const response = await api.post('/api/v1/sms/send', {
      to,
      message,
      lead_id: leadId,
    });
    return response.data;
  },

  // Send email
  sendEmail: async (to, subject, body, leadId = null) => {
    const response = await api.post('/api/v1/outreach/email', {
      to,
      subject,
      body,
      lead_id: leadId,
    });
    return response.data;
  },

  // Request a phone call (creates task for LO to call)
  requestCall: async (phoneNumber, leadId = null, notes = '') => {
    const response = await api.post('/api/v1/outreach/request-call', {
      phone_number: phoneNumber,
      lead_id: leadId,
      notes,
    });
    return response.data;
  },

  // Send voicemail drop
  sendVoicemail: async (to, templateId = 'default', leadId = null) => {
    const response = await api.post('/api/v1/outreach/voicemail', {
      to,
      template_id: templateId,
      lead_id: leadId,
    });
    return response.data;
  },

  // Log an outreach activity
  logActivity: async (leadId, channel, direction, content, outcome = null) => {
    const response = await api.post('/api/v1/outreach/log', {
      lead_id: leadId,
      channel,
      direction,
      content,
      outcome,
    });
    return response.data;
  },
};

// Call Monitoring API (AI Call Intelligence)
export const callMonitoringAPI = {
  // Caller Identification - Look up phone number in database
  lookupCaller: async (phoneNumber) => {
    const response = await api.get('/api/v1/call-monitoring/lookup-caller', {
      params: { phone: phoneNumber }
    });
    return response.data;
  },

  // Create new client profile from call
  createClientFromCall: async (data) => {
    const response = await api.post('/api/v1/call-monitoring/create-client', data);
    return response.data;
  },

  // Search for clients by name or other criteria
  searchClients: async (params) => {
    const response = await api.get('/api/v1/call-monitoring/search-clients', { params });
    return response.data;
  },

  // Session Management
  createSession: async (data) => {
    const response = await api.post('/api/v1/call-monitoring/sessions', data);
    return response.data;
  },

  getSession: async (sessionId) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}`);
    return response.data;
  },

  updateSession: async (sessionId, data) => {
    const response = await api.patch(`/api/v1/call-monitoring/sessions/${sessionId}`, data);
    return response.data;
  },

  endSession: async (sessionId, options = {}) => {
    // Support both legacy boolean and new object format
    const data = typeof options === 'boolean'
      ? { run_agents: options }
      : options;
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/end`, data);
    return response.data;
  },

  listSessions: async (params = {}) => {
    const response = await api.get('/api/v1/call-monitoring/sessions', { params });
    return response.data;
  },

  // Transcript
  appendTranscriptChunk: async (sessionId, data) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/transcript/chunk`, data);
    return response.data;
  },

  getTranscript: async (sessionId) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/transcript`);
    return response.data;
  },

  // Agent Execution
  runAgents: async (sessionId, agentTypes = null) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/run-agents`, {
      agent_types: agentTypes
    });
    return response.data;
  },

  // Artifacts
  getArtifacts: async (sessionId, params = {}) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/artifacts`, { params });
    return response.data;
  },

  approveArtifacts: async (sessionId, artifactIds) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/artifacts/approve`, {
      artifact_ids: artifactIds
    });
    return response.data;
  },

  rejectArtifacts: async (sessionId, artifactIds, reason = null) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/artifacts/reject`, {
      artifact_ids: artifactIds,
      rejection_reason: reason
    });
    return response.data;
  },

  executeArtifacts: async (sessionId, artifactIds = null) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/artifacts/execute`, {
      artifact_ids: artifactIds
    });
    return response.data;
  },

  // Review Flow
  getReviewData: async (sessionId) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/review`);
    return response.data;
  },

  submitReview: async (sessionId, data) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/review/submit`, data);
    return response.data;
  },

  // Participants
  addParticipant: async (sessionId, data) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/participants`, data);
    return response.data;
  },

  getParticipants: async (sessionId) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/participants`);
    return response.data;
  },

  // Client Call History
  getClientCalls: async (clientId, params = {}) => {
    const response = await api.get(`/api/v1/call-monitoring/client/${clientId}/calls`, { params });
    return response.data;
  },

  getLoanCalls: async (loanId, params = {}) => {
    const response = await api.get(`/api/v1/call-monitoring/loan/${loanId}/calls`, { params });
    return response.data;
  },

  // CI Voice Integration
  listCIRecordings: async (params = {}) => {
    const response = await api.get('/api/v1/call-monitoring/ci-recordings', { params });
    return response.data;
  },

  processCIRecording: async (recordingId, runAgents = true) => {
    const response = await api.post('/api/v1/call-monitoring/process-ci-recording', {
      recording_id: recordingId,
      run_agents: runAgents
    });
    return response.data;
  },

  // Call Intelligence Page
  getLiveTranscript: async (sessionId) => {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/live-transcript`);
    return response.data;
  },

  convertToApplication: async (sessionId, data) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/convert-to-application`, data);
    return response.data;
  },

  getCallMetrics: async (days = 30) => {
    const response = await api.get('/api/v1/call-monitoring/metrics', { params: { days } });
    return response.data;
  },

  // Calculator Result Sharing
  createShareLink: async (artifactId, options = {}) => {
    const response = await api.post(`/api/v1/call-monitoring/artifacts/${artifactId}/share`, options);
    return response.data;
  },

  getSharedArtifact: async (shareToken) => {
    // This is a public endpoint - no auth required
    const response = await axios.get(`${API_BASE_URL}/api/v1/call-monitoring/shared/${shareToken}`);
    return response.data;
  },

  deactivateShareLink: async (artifactId, shareToken) => {
    const response = await api.delete(`/api/v1/call-monitoring/artifacts/${artifactId}/share/${shareToken}`);
    return response.data;
  },

  getArtifactShares: async (artifactId) => {
    const response = await api.get(`/api/v1/call-monitoring/artifacts/${artifactId}/shares`);
    return response.data;
  },

  getMyShares: async (includeExpired = false, limit = 50) => {
    const response = await api.get('/api/v1/call-monitoring/my-shares', {
      params: { include_expired: includeExpired, limit }
    });
    return response.data;
  },

  // Stacked Notes (Call Intelligence Expansion)
  getStackedNotes: async (clientId, limit = 100) => {
    const response = await api.get(`/api/v1/call-monitoring/client/${clientId}/stacked-notes`, {
      params: { limit }
    });
    return response.data;
  },

  // Underwriter Review Completion
  completeUWReview: async (sessionId, data) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/complete-uw-review`, data);
    return response.data;
  },

  // Create Review Task (from JR LO or Underwriter)
  createReviewTask: async (sessionId, taskData) => {
    const response = await api.post(`/api/v1/call-monitoring/sessions/${sessionId}/create-review-task`, taskData);
    return response.data;
  },

  // Mobile Audio Stream WebSocket URL
  getAudioStreamUrl: (sessionId) => {
    const wsBase = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
    // Security: Token must be sent as first message after connect, not in the
    // URL query string. Callers of this URL must send {"type":"auth","token":"..."}
    // as the first WebSocket message after onopen.
    return `${wsBase}/api/v1/call-monitoring/sessions/${sessionId}/audio-stream`;
  },
};
