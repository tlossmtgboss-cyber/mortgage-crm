/**
 * Conversation Intelligence API Service
 *
 * API client for the voice call analysis platform:
 * - Call recordings
 * - Transcription
 * - AI analysis
 * - QA scoring
 * - Real-time assist
 * - Coaching
 * - Dashboards
 */

// Import the base API instance
import api, { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const BASE_PATH = '/api/v1/conversation-intelligence';

// =============================================================================
// RECORDINGS API
// =============================================================================

export const recordingsApi = {
  /**
   * Create a new call recording entry
   */
  create: async (data) => {
    const response = await api.post(`${BASE_PATH}/recordings`, data);
    return response.data;
  },

  /**
   * Get a specific recording by ID
   */
  get: async (recordingId) => {
    const response = await api.get(`${BASE_PATH}/recordings/${recordingId}`);
    return response.data;
  },

  /**
   * List recordings with filters
   */
  list: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.agentId) params.append('agent_id', filters.agentId.toString());
    if (filters.loanId) params.append('loan_id', filters.loanId.toString());
    if (filters.status) params.append('status', filters.status);
    if (filters.startDate) params.append('start_date', filters.startDate);
    if (filters.endDate) params.append('end_date', filters.endDate);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.offset) params.append('offset', filters.offset.toString());

    const response = await api.get(`${BASE_PATH}/recordings?${params.toString()}`);
    return response.data;
  },

  /**
   * Upload audio file for a recording
   */
  uploadAudio: async (recordingId, file) => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post(
      `${BASE_PATH}/recordings/${recordingId}/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },
};

// =============================================================================
// TRANSCRIPTION API
// =============================================================================

export const transcriptionApi = {
  /**
   * Start transcription for a recording
   */
  transcribe: async (recordingId, data) => {
    const response = await api.post(`${BASE_PATH}/recordings/${recordingId}/transcribe`, data);
    return response.data;
  },

  /**
   * Get transcription for a recording
   */
  get: async (recordingId) => {
    const response = await api.get(`${BASE_PATH}/recordings/${recordingId}/transcription`);
    return response.data;
  },

  /**
   * Poll for transcription completion
   */
  waitForCompletion: async (recordingId, maxAttempts = 60, intervalMs = 2000) => {
    for (let i = 0; i < maxAttempts; i++) {
      const transcription = await transcriptionApi.get(recordingId);
      if (transcription.status === 'completed' || transcription.status === 'failed') {
        return transcription;
      }
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    throw new Error('Transcription timed out');
  },
};

// =============================================================================
// ANALYSIS API
// =============================================================================

export const analysisApi = {
  /**
   * Start analysis for a recording
   */
  analyze: async (recordingId, data = {}) => {
    const response = await api.post(`${BASE_PATH}/recordings/${recordingId}/analyze`, data);
    return response.data;
  },

  /**
   * Get analysis for a recording
   */
  get: async (recordingId) => {
    const response = await api.get(`${BASE_PATH}/recordings/${recordingId}/analysis`);
    return response.data;
  },

  /**
   * Poll for analysis completion
   */
  waitForCompletion: async (recordingId, maxAttempts = 60, intervalMs = 2000) => {
    for (let i = 0; i < maxAttempts; i++) {
      const analysis = await analysisApi.get(recordingId);
      if (analysis.status === 'completed' || analysis.status === 'failed') {
        return analysis;
      }
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    throw new Error('Analysis timed out');
  },
};

// =============================================================================
// QA SCORING API
// =============================================================================

export const qaApi = {
  /**
   * Create QA scorecard for a recording
   */
  createScorecard: async (recordingId, data = {}) => {
    const response = await api.post(`${BASE_PATH}/recordings/${recordingId}/qa-score`, data);
    return response.data;
  },

  /**
   * Get all scorecards for a recording
   */
  getScorecards: async (recordingId) => {
    const response = await api.get(`${BASE_PATH}/recordings/${recordingId}/qa-scorecards`);
    return response.data;
  },

  /**
   * List available QA rubrics
   */
  listRubrics: async () => {
    const response = await api.get(`${BASE_PATH}/qa-rubrics`);
    return response.data;
  },
};

// =============================================================================
// REAL-TIME ASSIST API
// =============================================================================

export const realTimeApi = {
  /**
   * Create a real-time assist session
   */
  createSession: async (data) => {
    const response = await api.post(`${BASE_PATH}/realtime/sessions`, data);
    return response.data;
  },

  /**
   * End a real-time assist session
   */
  endSession: async (sessionId) => {
    const response = await api.post(`${BASE_PATH}/realtime/sessions/${sessionId}/end`);
    return response.data;
  },

  /**
   * Get WebSocket URL for a session
   */
  getWebSocketUrl: (sessionId) => {
    // Derive WebSocket URL from the shared API_BASE_URL
    const wsUrl = API_BASE_URL.replace(/^http/, 'ws');
    return `${wsUrl}${BASE_PATH}/realtime/sessions/${sessionId}/ws`;
  },

  /**
   * Create WebSocket connection for real-time assist
   */
  createWebSocket: (sessionId) => {
    const url = realTimeApi.getWebSocketUrl(sessionId);
    const token = getToken();
    // Security: Token in URL is a browser WebSocket API limitation.
    // Backend should accept token via first message post-connection.
    const ws = new WebSocket(url);
    if (token) {
      ws.addEventListener('open', () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
      });
    }
    return ws;
  },
};

// =============================================================================
// COACHING API
// =============================================================================

export const coachingApi = {
  /**
   * Create a coaching clip
   */
  createClip: async (data) => {
    const response = await api.post(`${BASE_PATH}/coaching/clips`, data);
    return response.data;
  },

  /**
   * List coaching clips
   */
  listClips: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.category) params.append('category', filters.category);
    if (filters.agentId) params.append('agent_id', filters.agentId.toString());
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.offset) params.append('offset', filters.offset.toString());

    const response = await api.get(`${BASE_PATH}/coaching/clips?${params.toString()}`);
    return response.data;
  },

  /**
   * Create a coaching assignment
   */
  createAssignment: async (data) => {
    const response = await api.post(`${BASE_PATH}/coaching/assignments`, data);
    return response.data;
  },

  /**
   * List coaching assignments
   */
  listAssignments: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.assignedTo) params.append('assigned_to', filters.assignedTo.toString());
    if (filters.status) params.append('status', filters.status);
    if (filters.limit) params.append('limit', filters.limit.toString());

    const response = await api.get(`${BASE_PATH}/coaching/assignments?${params.toString()}`);
    return response.data;
  },

  /**
   * Complete a coaching assignment
   */
  completeAssignment: async (assignmentId) => {
    const response = await api.patch(`${BASE_PATH}/coaching/assignments/${assignmentId}/complete`);
    return response.data;
  },
};

// =============================================================================
// DASHBOARD API
// =============================================================================

export const dashboardApi = {
  /**
   * Get team dashboard metrics
   */
  getTeamDashboard: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.startDate) params.append('start_date', filters.startDate);
    if (filters.endDate) params.append('end_date', filters.endDate);
    if (filters.teamId) params.append('team_id', filters.teamId.toString());

    const response = await api.get(`${BASE_PATH}/dashboard/team?${params.toString()}`);
    return response.data;
  },

  /**
   * Get agent dashboard metrics
   */
  getAgentDashboard: async (agentId, filters = {}) => {
    const params = new URLSearchParams();
    if (filters.startDate) params.append('start_date', filters.startDate);
    if (filters.endDate) params.append('end_date', filters.endDate);

    const response = await api.get(
      `${BASE_PATH}/dashboard/agent/${agentId}?${params.toString()}`
    );
    return response.data;
  },

  /**
   * Get compliance dashboard metrics
   */
  getComplianceDashboard: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.startDate) params.append('start_date', filters.startDate);
    if (filters.endDate) params.append('end_date', filters.endDate);

    const response = await api.get(`${BASE_PATH}/dashboard/compliance?${params.toString()}`);
    return response.data;
  },
};

// =============================================================================
// EXPORT API
// =============================================================================

export const exportApi = {
  /**
   * Export recordings data
   */
  exportRecordings: async (format = 'csv', filters = {}) => {
    const params = new URLSearchParams();
    params.append('format', format);
    if (filters.startDate) params.append('start_date', filters.startDate);
    if (filters.endDate) params.append('end_date', filters.endDate);
    if (filters.agentId) params.append('agent_id', filters.agentId.toString());

    if (format === 'csv') {
      const response = await api.get(`${BASE_PATH}/export/recordings?${params.toString()}`, {
        responseType: 'blob',
      });
      return response.data;
    } else {
      const response = await api.get(`${BASE_PATH}/export/recordings?${params.toString()}`);
      return response.data;
    }
  },

  /**
   * Download exported file
   */
  downloadCsv: (blob, filename = 'recordings_export.csv') => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

// =============================================================================
// HEALTH CHECK
// =============================================================================

export const healthApi = {
  /**
   * Check service health
   */
  check: async () => {
    const response = await api.get(`${BASE_PATH}/health`);
    return response.data;
  },
};

// =============================================================================
// AUTOMATED CALL SUMMARIES API
// =============================================================================

export const summaryApi = {
  /**
   * Generate summary for a recording
   */
  generate: async (recordingId, data = {}) => {
    const response = await api.post(`${BASE_PATH}/recordings/${recordingId}/summary`, {
      summary_type: data.summaryType || 'standard',
      auto_create_tasks: data.autoCreateTasks !== false,
    });
    return response.data;
  },

  /**
   * Get existing summary for a recording
   */
  get: async (recordingId) => {
    const response = await api.get(`${BASE_PATH}/recordings/${recordingId}/summary`);
    return response.data;
  },

  /**
   * Get recent summaries with filters
   */
  getRecent: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.agentId) params.append('agent_id', filters.agentId.toString());
    if (filters.days) params.append('days', filters.days.toString());
    if (filters.limit) params.append('limit', filters.limit.toString());

    const response = await api.get(`${BASE_PATH}/summaries/recent?${params.toString()}`);
    return response.data;
  },

  /**
   * Get summary statistics
   */
  getStats: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.agentId) params.append('agent_id', filters.agentId.toString());
    if (filters.days) params.append('days', filters.days.toString());

    const response = await api.get(`${BASE_PATH}/summaries/stats?${params.toString()}`);
    return response.data;
  },

  /**
   * Get summary feed for dashboard
   */
  getFeed: async (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.teamId) params.append('team_id', filters.teamId.toString());
    if (filters.outcome) params.append('outcome', filters.outcome);
    if (filters.sentiment) params.append('sentiment', filters.sentiment);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.offset) params.append('offset', filters.offset.toString());

    const response = await api.get(`${BASE_PATH}/summaries/feed?${params.toString()}`);
    return response.data;
  },

  /**
   * Process pending summaries (batch generate)
   */
  processPending: async (options = {}) => {
    const params = new URLSearchParams();
    if (options.limit) params.append('limit', options.limit.toString());

    const response = await api.post(`${BASE_PATH}/summaries/process-pending?${params.toString()}`);
    return response.data;
  },
};

// =============================================================================
// COMBINED API EXPORT
// =============================================================================

export const conversationIntelligenceApi = {
  recordings: recordingsApi,
  transcription: transcriptionApi,
  analysis: analysisApi,
  qa: qaApi,
  realTime: realTimeApi,
  coaching: coachingApi,
  dashboard: dashboardApi,
  export: exportApi,
  health: healthApi,
  summary: summaryApi,
};

export default conversationIntelligenceApi;
