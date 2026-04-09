import axios from 'axios';
import { Capacitor } from '@capacitor/core';
import { ensureArray } from '../utils/arrayHelpers';
import { getCSRFTokenFromCookie } from '../utils/security';
import { pinnedAdapter } from '../utils/pinnedFetch';

// Detect native mobile app FIRST — Capacitor serves from localhost,
// so we must check isNativePlatform() before the hostname check.
const isNativeApp = Capacitor.isNativePlatform();
const isLocalhost = !isNativeApp && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const API_BASE_URL = isNativeApp
  ? 'https://api.perenniaai.com'  // Native iOS/Android — always production
  : isLocalhost
    ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
    : 'https://api.perenniaai.com'; // Production web

// Create axios instance with mobile app identification
// On native iOS, route through certificate-pinned URLSession
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
    // Identify mobile app requests to bypass IP blocking middleware
    ...(isNativeApp && { 'X-Mobile-App': 'capacitor-ios' }),
  },
  ...(isNativeApp && { adapter: pinnedAdapter }),
});

// CSRF token cache — fetched once, reused for all requests
let csrfTokenPromise = null;

const fetchCSRFToken = async () => {
  // Try cookie first (set by backend on GET responses)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return cookieToken;

  // Fetch from server if no cookie
  try {
    const response = await axios.get(`${API_BASE_URL}/api/v1/csrf-token`, {
      withCredentials: true,
    });
    return response.data?.csrf_token || null;
  } catch (error) {
    console.warn('Could not fetch CSRF token:', error);
    return null;
  }
};

const getCSRFToken = () => {
  // Check cookie synchronously first (fast path)
  const cookieToken = getCSRFTokenFromCookie();
  if (cookieToken) return Promise.resolve(cookieToken);

  // Fetch from server (deduplicated — only one in-flight request)
  if (!csrfTokenPromise) {
    csrfTokenPromise = fetchCSRFToken().finally(() => {
      // Allow re-fetch after 5 minutes
      setTimeout(() => { csrfTokenPromise = null; }, 5 * 60 * 1000);
    });
  }
  return csrfTokenPromise;
};

const CSRF_METHODS = ['post', 'put', 'patch', 'delete'];

// Add token, impersonation, and CSRF headers to requests
api.interceptors.request.use(
  async (config) => {
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

    // Add CSRF token for state-changing requests
    if (CSRF_METHODS.includes(config.method)) {
      const csrfToken = await getCSRFToken();
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken;
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
  async (error) => {
    // Log network errors for debugging
    if (!error.response) {
      console.error('[API] Network error (no response):', {
        message: error.message,
        code: error.code,
        method: error.config?.method,
        // OBS-001: Don't log full URL — may contain PII in query params
        path: error.config?.url?.split('?')[0],
        status: 'no_response'
      });
    }

    // Retry once on CSRF token failure (token may have expired)
    if (
      error.response?.status === 403 &&
      error.response?.data?.code === 'CSRF_VALIDATION_FAILED' &&
      !error.config._csrfRetry
    ) {
      // Force re-fetch CSRF token
      csrfTokenPromise = null;
      const newToken = await fetchCSRFToken();
      if (newToken) {
        error.config._csrfRetry = true;
        error.config.headers['X-CSRF-Token'] = newToken;
        return api.request(error.config);
      }
    }

    // Sanitize error messages to prevent leaking backend internals to the UI.
    // For 500-level errors, replace the detail with a generic message.
    // For client errors (4xx), keep user-friendly messages from the backend.
    const SAFE_ERROR_MESSAGES = {
      400: "Invalid request. Please check your input.",
      401: "Session expired. Please log in again.",
      403: "You don't have permission for this action.",
      404: "The requested resource was not found.",
      409: "A conflict occurred. Please refresh and try again.",
      422: "Invalid data submitted.",
      429: "Too many requests. Please wait a moment.",
    };
    if (error.response) {
      const status = error.response.status;
      if (status >= 500) {
        // Never expose internal server errors to the UI
        error.response.data = {
          ...error.response.data,
          detail: "An unexpected error occurred. Please try again later.",
        };
      } else if (!error.response.data?.detail && SAFE_ERROR_MESSAGES[status]) {
        // Provide a safe fallback if no user-friendly detail was sent
        error.response.data = {
          ...error.response.data,
          detail: SAFE_ERROR_MESSAGES[status],
        };
      }
    }

    if (error.response?.status === 401) {
      // Don't redirect if already on login page or during logout
      const isLoginPage = window.location.pathname === '/login';

      // Don't logout for third-party integration token errors (Salesforce, HubSpot, etc.)
      // These 401s mean the integration token expired, not the user's CRM session
      const requestUrl = error.config?.url || '';
      const isIntegrationEndpoint =
        requestUrl.includes('/salesforce/') ||
        requestUrl.includes('/hubspot/') ||
        requestUrl.includes('/google-calendar/') ||
        requestUrl.includes('/microsoft/') ||
        requestUrl.includes('/zoom/') ||
        requestUrl.includes('/docusign/') ||
        requestUrl.includes('/calendly/');

      if (!isLoginPage && !isIntegrationEndpoint) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Authentication
export const authAPI = {
  login: async (email, password) => {
    const response = await api.post('/api/v1/auth/login', {
      x1: email,
      x2: password,
    });
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
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        await api.delete(`/api/v1/leads/${id}`);
        return;
      } catch (error) {
        lastError = error;
        if (error.message === 'Network Error' && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  bulkDelete: async (leadIds) => {
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await api.post('/api/v1/leads/bulk-delete', leadIds);
        return response.data;
      } catch (error) {
        lastError = error;
        if (error.message === 'Network Error' && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  bulkUpdateStatus: async (leadIds, status) => {
    const maxRetries = 2;
    let lastError;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await api.post('/api/v1/leads/bulk-update-status', {
          lead_ids: leadIds,
          status: status
        });
        return response.data;
      } catch (error) {
        lastError = error;
        if (error.message === 'Network Error' && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        throw error;
      }
    }
    throw lastError;
  },
  getDocuments: async (leadId) => {
    const response = await api.get(`/api/v1/leads/${leadId}/documents`);
    return response.data;
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
  create: async (data, skipDuplicateCheck = false, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const url = skipDuplicateCheck
        ? '/api/v1/loans/?skip_duplicate_check=true'
        : '/api/v1/loans/';
      const response = await api.post(url, data);
      return response.data;
    } catch (error) {
      // Retry on Network Error (up to maxRetries times)
      if (error.message === 'Network Error' && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second
        return loansAPI.create(data, skipDuplicateCheck, retryCount + 1);
      }

      // If 405 error, try without trailing slash as fallback
      if (error.response?.status === 405) {
        try {
          const url = skipDuplicateCheck
            ? '/api/v1/loans?skip_duplicate_check=true'
            : '/api/v1/loans';
          const retryResponse = await api.post(url, data);
          return retryResponse.data;
        } catch (retryError) {
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
  bulkDelete: async (loanIds) => {
    const response = await api.post('/api/v1/loans/bulk-delete', loanIds);
    return response.data;
  },
};

// Tasks
export const tasksAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/tasks', { params });
    return ensureArray(response.data, 'tasks');
  },
  getUnified: async () => {
    const response = await api.get('/api/v1/unified-tasks');
    return response.data;
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/tasks/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/tasks', data);
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
    const response = await api.get('/api/v1/referral-partners', { params });
    return ensureArray(response.data, 'partners');
  },
  getById: async (id) => {
    const response = await api.get(`/api/v1/referral-partners/${id}`);
    return response.data;
  },
  getReferrals: async (id) => {
    const response = await api.get(`/api/v1/referral-partners/${id}/referrals`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/v1/referral-partners', data);
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
    const response = await api.get('/api/v1/mum-clients/', { params });
    return Array.isArray(response.data) ? response.data : response.data.clients || [];
  },
  getMetrics: async () => {
    // Metrics are derived client-side from the MUM clients list
    return null;
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

  // Portal management
  getOrCreatePortal: async (clientId) => {
    const response = await api.post(`/api/v1/mum-clients/${clientId}/portal`);
    return response.data;
  },
  getPortalInfo: async (clientId) => {
    const response = await api.get(`/api/v1/mum-clients/${clientId}/portal`);
    return response.data;
  },
  postPortalMessage: async (clientId, content, messageType = 'update') => {
    const response = await api.post(`/api/v1/mum-clients/${clientId}/portal/message`, {
      content,
      message_type: messageType,
    });
    return response.data;
  },
};

// MUM Portal Public API (for client-facing portal)
export const mumPortalAPI = {
  getPortal: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}`, { params });
    return response.data;
  },
  getVideos: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}/videos`, { params });
    return response.data;
  },
  getDocuments: async (slug, token = null) => {
    const params = token ? { token } : {};
    const response = await api.get(`/api/v1/mum-portal/${slug}/documents`, { params });
    return response.data;
  },
  getMessages: async (slug, token = null, limit = 50) => {
    const params = { limit, ...(token ? { token } : {}) };
    const response = await api.get(`/api/v1/mum-portal/${slug}/messages`, { params });
    return response.data;
  },
  sendHeartbeat: async (slug, page = 'home', token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/heartbeat`, { page, token });
    return response.data;
  },
  markMessageRead: async (slug, messageId, token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/messages/${messageId}/read`, { token });
    return response.data;
  },
  markVideoViewed: async (slug, videoId, token = null) => {
    const response = await api.post(`/api/v1/mum-portal/${slug}/videos/${videoId}/viewed`, { token });
    return response.data;
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
      lead_id: context.lead_id || null,
      loan_id: context.loan_id || null,
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
  // Streaming version of processCommand for real-time responses.
  // Attempts true SSE streaming via /orchestrator-chat-stream first
  // (tokens appear as they are generated), then falls back to the
  // non-streaming /langgraph-chat endpoint with simulated chunking.
  processCommandStream: async (message, onContent, onStatus, onDone, onError, documentContext = null) => {
    const token = localStorage.getItem('token');

    try {
      // Show initial status
      if (onStatus) onStatus('Analyzing your request...');

      const body = { message };
      if (documentContext) {
        body.document_context = documentContext;
      }

      // --- Attempt true SSE streaming first ---
      try {
        const sseResponse = await fetch(`${API_BASE_URL}/api/v1/ai/orchestrator-chat-stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(body)
        });

        if (sseResponse.ok && sseResponse.headers.get('content-type')?.includes('text/event-stream')) {
          // True SSE stream available — read tokens in real-time
          const reader = sseResponse.body.getReader();
          const decoder = new TextDecoder();
          let fullResponse = '';
          let buffer = '';
          let metadata = {};

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE lines
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // Keep incomplete line in buffer

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue;
              try {
                const payload = JSON.parse(line.slice(6));

                if (payload.content && onContent) {
                  fullResponse += payload.content;
                  onContent(payload.content);
                } else if (payload.tool_use && onStatus) {
                  onStatus(`Using tool: ${payload.tool_use}...`);
                } else if (payload.error && onError) {
                  onError(payload.error);
                  return;
                } else if (payload.done) {
                  metadata = {
                    session_id: payload.session_id,
                    engine: payload.engine || 'langgraph',
                  };
                }
              } catch (_parseErr) {
                // Skip malformed SSE lines
              }
            }
          }

          // Signal completion
          if (onDone) {
            onDone(fullResponse, {
              full_response: fullResponse,
              engine: metadata.engine || 'langgraph',
              ...metadata,
            });
          }
          return; // SSE path succeeded — skip fallback
        }
        // If response is not SSE (e.g. 404 or wrong content-type), fall through to non-streaming
      } catch (sseErr) {
        console.warn('SSE streaming unavailable, falling back to non-streaming:', sseErr.message);
      }

      // --- Fallback: non-streaming endpoint with simulated chunking ---
      const response = await fetch(`${API_BASE_URL}/api/v1/ai/langgraph-chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      // Check for error in response
      if (data.error) {
        if (onError) onError(data.error);
        return;
      }

      // Simulate streaming by delivering content in chunks for smooth UI
      const fullResponse = data.response || '';
      if (fullResponse && onContent) {
        // Split into paragraphs for natural delivery
        const paragraphs = fullResponse.split('\n\n');

        for (const para of paragraphs) {
          if (para.trim()) {
            // Deliver paragraph
            onContent(para + '\n\n');
            // Small delay between paragraphs for readability
            await new Promise(resolve => setTimeout(resolve, 50));
          }
        }
      }

      // Signal completion with full response and metadata
      if (onDone) {
        onDone(fullResponse, {
          full_response: fullResponse,
          intent: data.intent,
          confidence: data.confidence,
          follow_up_suggestions: data.follow_up_suggestions,
          processing_time_seconds: data.processing_time_seconds,
          data_quality: data.data_quality,
          actions_executed: data.actions_executed,
          actions_pending: data.actions_pending,
          engine: data.engine || 'langgraph'
        });
      }
    } catch (error) {
      console.error('LangGraph chat error:', error);
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
  extractDocument: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/api/v1/ai/extract-document', formData, {
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
  submitTrainingInstruction: async (instruction, taskContext = {}) => {
    const response = await api.post('/api/v1/ai/training/instruction', {
      instruction,
      task_context: taskContext
    });
    return response.data;
  },
  // Inline thumbs-up/down feedback on individual AI responses
  submitInlineFeedback: async ({ sessionId, messageId, rating, userQuestion, aiResponse }) => {
    const response = await api.post('/api/v1/ai/feedback', {
      session_id: sessionId,
      message_id: messageId,
      rating,
      user_question: userQuestion,
      ai_response: aiResponse,
    });
    return response.data;
  },
  // AI Feedback methods (detailed report-wrong-answer flow)
  submitFeedback: async (feedbackData) => {
    const response = await api.post('/api/v1/ai-feedback/', feedbackData);
    return response.data;
  },
  getFeedbackLogs: async (params = {}) => {
    const response = await api.get('/api/v1/ai-feedback/', { params });
    return response.data;
  },
  getFeedbackStats: async () => {
    const response = await api.get('/api/v1/ai-feedback/stats');
    return response.data;
  },
  updateFeedback: async (feedbackId, updateData) => {
    const response = await api.patch(`/api/v1/ai-feedback/${feedbackId}`, updateData);
    return response.data;
  },
  deleteFeedback: async (feedbackId) => {
    const response = await api.delete(`/api/v1/ai-feedback/${feedbackId}`);
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

// CRM Calendar Sync API (syncs with Salesforce)
export const crmCalendarAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/calendar/events', { params });
    return ensureArray(response.data, 'events');
  },
  getById: async (id) => {
    const response = await api.get(`/api/calendar/events/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await api.post('/api/calendar/events', data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await api.put(`/api/calendar/events/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    await api.delete(`/api/calendar/events/${id}`);
  },
  // Force resync an event to Salesforce
  resync: async (id) => {
    const response = await api.post(`/api/calendar/events/${id}/resync`);
    return response.data;
  },
  // Get sync status for all events
  getSyncStatus: async () => {
    const response = await api.get('/api/calendar/sync/status');
    return response.data;
  },
  // Get sync history
  getSyncHistory: async (params = {}) => {
    const response = await api.get('/api/calendar/sync/history', { params });
    return response.data;
  },
  // Trigger manual sync
  triggerSync: async () => {
    const response = await api.post('/api/calendar/sync/trigger');
    return response.data;
  },
};

// Unified Calendar API (merges calendar, scheduler, and CRM events server-side)
export const unifiedCalendarAPI = {
  getAll: async (params = {}, { signal } = {}) => {
    const response = await api.get('/api/v1/calendar/unified', { params, signal });
    return response.data;
  },
};

// Scheduler Appointments API
export const schedulerAPI = {
  getAppointments: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/appointments', { params });
    return ensureArray(response.data, 'appointments');
  },
  getAppointmentById: async (id) => {
    const response = await api.get(`/api/v1/scheduler/appointments/${id}`);
    return response.data;
  },
  createAppointment: async (data) => {
    const response = await api.post('/api/v1/scheduler/appointments', data);
    return response.data;
  },
  updateAppointment: async (id, data) => {
    const response = await api.put(`/api/v1/scheduler/appointments/${id}`, data);
    return response.data;
  },
  cancelAppointment: async (id, reason) => {
    const response = await api.post(`/api/v1/scheduler/appointments/${id}/cancel`, { reason });
    return response.data;
  },
  sendReminder: async (id) => {
    const response = await api.post(`/api/v1/scheduler/appointments/${id}/remind`);
    return response.data;
  },
  getAppointmentTimeline: async (id) => {
    const response = await api.get(`/api/v1/scheduler/appointments/${id}/timeline`);
    return response.data;
  },
  searchAppointments: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/search', { params, paramsSerializer: (p) => {
      const parts = [];
      for (const [key, value] of Object.entries(p)) {
        if (value === undefined || value === null || value === '') continue;
        if (Array.isArray(value)) {
          value.forEach(v => parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`));
        } else {
          parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
        }
      }
      return parts.join('&');
    }});
    return response.data;
  },
  searchSuggestions: async (q) => {
    const response = await api.get('/api/v1/scheduler/search/suggestions', { params: { q } });
    return response.data;
  },
  getNotifications: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/notifications', { params });
    return response.data;
  },
  markNotificationRead: async (notificationId) => {
    const response = await api.put(`/api/v1/scheduler/notifications/${notificationId}/read`);
    return response.data;
  },
  markAllNotificationsRead: async () => {
    const response = await api.put('/api/v1/scheduler/notifications/read-all');
    return response.data;
  },
  // Conflict resolution
  checkConflicts: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/conflicts/check', { params });
    return response.data;
  },
  listConflicts: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/conflicts/list', { params });
    return response.data;
  },
  resolveConflict: async (appointmentId, data) => {
    const response = await api.post(`/api/v1/scheduler/conflicts/resolve/${appointmentId}`, data);
    return response.data;
  },
};

// Calendar Analytics API (dashboard metrics, trends, breakdowns)
export const calendarAnalyticsAPI = {
  getOverview: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/overview', { params });
    return response.data;
  },
  getTrends: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/trends', { params });
    return response.data;
  },
  getByType: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/by-type', { params });
    return response.data;
  },
  getByLO: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/by-lo', { params });
    return response.data;
  },
  getAppointmentOutcomes: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/appointment-outcomes', { params });
    return response.data;
  },
  getAppointmentTypeEffectiveness: async (params = {}) => {
    const response = await api.get('/api/v1/scheduler/analytics/appointment-type-effectiveness', { params });
    return response.data;
  },
};

// Calendar Labels API (color-coded appointment categorization)
export const calendarLabelsAPI = {
  getLabels: async () => {
    const response = await api.get('/api/v1/scheduler/labels');
    return response.data;
  },
  createLabel: async (data) => {
    const response = await api.post('/api/v1/scheduler/labels', data);
    return response.data;
  },
  updateLabel: async (id, data) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}`, data);
    return response.data;
  },
  deleteLabel: async (id) => {
    const response = await api.delete(`/api/v1/scheduler/labels/${id}`);
    return response.data;
  },
  reorderLabels: async (orderedIds) => {
    const response = await api.put('/api/v1/scheduler/labels/reorder', { order: orderedIds });
    return response.data;
  },
  assignLabels: async (appointmentId, labelIds) => {
    const response = await api.post('/api/v1/scheduler/labels/assign', {
      appointment_id: appointmentId,
      label_ids: labelIds,
    });
    return response.data;
  },
  unassignLabels: async (appointmentId, labelIds) => {
    const response = await api.delete('/api/v1/scheduler/labels/assign', {
      data: { appointment_id: appointmentId, label_ids: labelIds },
    });
    return response.data;
  },
  getAppointmentLabels: async (appointmentId) => {
    const response = await api.get(`/api/v1/scheduler/labels/appointment/${appointmentId}`);
    return response.data;
  },
};

// Team Calendar API (manager/admin multi-LO schedule view)
export const teamCalendarAPI = {
  getTeamCalendar: async (startDate, endDate, loIds = null) => {
    const params = { start_date: startDate, end_date: endDate };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team', { params });
    return response.data;
  },
  getCapacity: async (startDate, endDate, loIds = null) => {
    const params = { start_date: startDate, end_date: endDate };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team/capacity', { params });
    return response.data;
  },
  reassignAppointment: async (appointmentId, newLoId, reason = null) => {
    const response = await api.post('/api/v1/calendar/team/reassign', {
      appointment_id: appointmentId,
      new_lo_id: newLoId,
      reason,
    });
    return response.data;
  },
  getAvailabilityMatrix: async (targetDate, durationMinutes = 30, loIds = null) => {
    const params = { target_date: targetDate, duration_minutes: durationMinutes };
    if (loIds) params.lo_ids = loIds;
    const response = await api.get('/api/v1/calendar/team/availability-matrix', { params });
    return response.data;
  },
};

// Calendar Settings API (availability, appointment types, notifications, booking page, integrations, team)
export const calendarSettingsAPI = {
  // Availability
  getAvailability: async () => {
    const response = await api.get('/api/v1/calendar-settings/availability');
    return response.data;
  },
  updateAvailability: async (data) => {
    const response = await api.put('/api/v1/calendar-settings/availability', data);
    return response.data;
  },
  getAvailabilitySource: async () => {
    const response = await api.get('/api/v1/scheduler/settings/availability-source');
    return response.data;
  },
  // Appointment Types
  getAppointmentTypes: async () => {
    const response = await api.get('/api/v1/calendar-settings/appointment-types');
    return response.data;
  },
  createAppointmentType: async (data) => {
    const response = await api.post('/api/v1/calendar-settings/appointment-types', data);
    return response.data;
  },
  updateAppointmentType: async (id, data) => {
    const response = await api.put(`/api/v1/calendar-settings/appointment-types/${id}`, data);
    return response.data;
  },
  deleteAppointmentType: async (id) => {
    const response = await api.delete(`/api/v1/calendar-settings/appointment-types/${id}`);
    return response.data;
  },
  reorderAppointmentTypes: async (typeIds) => {
    const response = await api.put('/api/v1/calendar-settings/appointment-types/reorder', { type_ids: typeIds });
    return response.data;
  },
  // Notifications
  getNotifications: async () => {
    const response = await api.get('/api/v1/calendar-settings/notifications');
    return response.data;
  },
  updateNotifications: async (data) => {
    const response = await api.put('/api/v1/calendar-settings/notifications', data);
    return response.data;
  },
  // Booking Page
  getBookingPage: async () => {
    const response = await api.get('/api/v1/calendar-settings/booking-page');
    return response.data;
  },
  updateBookingPage: async (data) => {
    const response = await api.put('/api/v1/calendar-settings/booking-page', data);
    return response.data;
  },
  // Integrations
  getIntegrations: async () => {
    const response = await api.get('/api/v1/calendar-settings/integrations');
    return response.data;
  },
  updateIntegrations: async (data) => {
    const response = await api.put('/api/v1/scheduler/settings/integrations', data);
    return response.data;
  },
  // Cancellation Policy
  getCancellationPolicy: async () => {
    const response = await api.get('/api/v1/scheduler/cancellation-policy');
    return response.data;
  },
  updateCancellationPolicy: async (data) => {
    const response = await api.put('/api/v1/scheduler/cancellation-policy', data);
    return response.data;
  },
  // Advanced Settings
  getAdvancedSettings: async () => {
    const response = await api.get('/api/v1/scheduler/settings/all');
    // Extract the advanced section from the unified settings blob
    return { data: response.data?.advanced || {} };
  },
  updateAdvancedSettings: async (data) => {
    const response = await api.put('/api/v1/scheduler/settings/advanced', data);
    return response.data;
  },
  // Team
  getTeam: async () => {
    const response = await api.get('/api/v1/calendar-settings/team');
    return response.data;
  },
  updateTeam: async (data) => {
    const response = await api.put('/api/v1/calendar-settings/team', data);
    return response.data;
  },
  inviteTeamMember: async (data) => {
    const response = await api.post('/api/v1/calendar-settings/team/invite', data);
    return response.data;
  },
  // Labels — delegate to scheduler labels routes (the real backend)
  getLabels: async () => {
    const response = await api.get('/api/v1/scheduler/labels');
    return response.data;
  },
  createLabel: async (data) => {
    const response = await api.post('/api/v1/scheduler/labels', data);
    return response.data;
  },
  updateLabel: async (id, data) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}`, data);
    return response.data;
  },
  deleteLabel: async (id) => {
    const response = await api.delete(`/api/v1/scheduler/labels/${id}`);
    return response.data;
  },
  reorderLabels: async (labelIds) => {
    const response = await api.put('/api/v1/scheduler/labels/reorder', { label_ids: labelIds });
    return response.data;
  },
  updateLabelSettings: async (data) => {
    const response = await api.put('/api/v1/scheduler/settings/labels', data);
    return response.data;
  },
  // Appointment Templates — no backend yet, return empty defaults
  getTemplates: async () => {
    return { status: 'success', data: { templates: [] } };
  },
  deleteTemplate: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultTemplate: async () => {
    return { status: 'success', data: {} };
  },
  createTemplate: async () => {
    return { status: 'success', data: {} };
  },
  updateTemplate: async () => {
    return { status: 'success', data: {} };
  },
  duplicateTemplate: async () => {
    return { status: 'success', data: {} };
  },
  // Locations — no backend yet, return empty defaults
  getLocations: async () => {
    return { status: 'success', data: { locations: [] } };
  },
  createLocation: async () => {
    return { status: 'success', data: {} };
  },
  updateLocation: async () => {
    return { status: 'success', data: {} };
  },
  deleteLocation: async () => {
    return { status: 'success', data: {} };
  },
  reorderLocations: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultLocation: async () => {
    return { status: 'success', data: {} };
  },
  setDefaultLabel: async (id) => {
    const response = await api.put(`/api/v1/scheduler/labels/${id}/default`);
    return response.data;
  },
  // AI Scheduling
  getAIScheduling: async () => {
    const response = await api.get('/api/v1/scheduler/settings/ai-scheduling');
    return response.data;
  },
  updateAIScheduling: async (data) => {
    const response = await api.put('/api/v1/scheduler/settings/ai_scheduling', data);
    return response.data;
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

// Reconciliation API (AI Engine tasks)
// Command Center API - Unified Action Items Dashboard
export const commandCenterAPI = {
  // Get all action items across the CRM
  getAll: async () => {
    const response = await api.get('/api/v1/command-center');
    return response.data;
  }
};

export const reconciliationAPI = {
  // Get pending reconciliation items (optionally filter by status)
  getPending: async (status = null) => {
    const params = status ? { status } : {};
    const response = await api.get('/api/v1/reconciliation/pending', { params });
    return response.data;
  },

  // Delete a reconciliation item
  delete: async (id) => {
    await api.delete(`/api/v1/reconciliation/items/${id}`);
  },

  // Approve a reconciliation item
  approve: async (data) => {
    const response = await api.post('/api/v1/reconciliation/approve', data);
    return response.data;
  },

  // Reject a reconciliation item
  reject: async (data) => {
    const response = await api.post('/api/v1/reconciliation/reject', data);
    return response.data;
  },
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

// Borrower Application API (LO-facing authenticated endpoints)
export const borrowerApplicationAPI = {
  // Create a new borrower application
  create: async (data) => {
    const response = await api.post('/api/v1/applications/', data);
    return response.data;
  },

  // List all applications for current LO
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/applications/', { params });
    return response.data;
  },

  // Get specific application by ID
  getById: async (id) => {
    const response = await api.get(`/api/v1/applications/${id}`);
    return response.data;
  },

  // Get analytics for applications
  getAnalytics: async (days = 30) => {
    const response = await api.get('/api/v1/applications/analytics', { params: { days } });
    return response.data;
  },

  // Generate application link for a lead
  createForLead: async (leadId, options = {}) => {
    const response = await api.post('/api/v1/applications/', {
      lead_id: leadId,
      ...options
    });
    return response.data;
  }
};

// Public Borrower Application API (token-based, no auth required)
export const publicApplicationAPI = {
  // Get application by public token
  get: async (token) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/apply/${token}`);
    return response.data;
  },

  // Update application data
  update: async (token, data) => {
    const response = await axios.patch(`${API_BASE_URL}/api/v1/apply/${token}`, data);
    return response.data;
  },

  // Save step data
  saveStep: async (token, step, data, markCompleted = false) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/step`, {
      step,
      data,
      mark_completed: markCompleted
    });
    return response.data;
  },

  // Calculate pre-qualification
  prequalify: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/prequalify`, data);
    return response.data;
  },

  // Capture credit authorization
  captureCreditAuth: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/credit-auth`, data);
    return response.data;
  },

  // Submit application
  submit: async (token) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/submit`);
    return response.data;
  },

  // Upload document
  uploadDocument: async (token, file, category, description) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('category', category || 'other');
    if (description) formData.append('description', description);

    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // List documents
  getDocuments: async (token) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/apply/${token}/documents`);
    return response.data;
  },

  // Delete document
  deleteDocument: async (token, docId) => {
    const response = await axios.delete(`${API_BASE_URL}/api/v1/apply/${token}/documents/${docId}`);
    return response.data;
  },

  // Create co-borrower invitation
  createCoborrowerInvitation: async (token, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/apply/${token}/coborrower`, data);
    return response.data;
  }
};

// Co-borrower API (token-based, no auth required)
export const coborrowerAPI = {
  // Get invitation by token
  getInvitation: async (invitationToken) => {
    const response = await axios.get(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}`);
    return response.data;
  },

  // Save co-borrower data
  saveData: async (invitationToken, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/save`, data);
    return response.data;
  },

  // Submit co-borrower section
  submit: async (invitationToken) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/submit`);
    return response.data;
  },

  // Capture credit authorization
  captureCreditAuth: async (invitationToken, data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/coborrower/${invitationToken}/credit-auth`, data);
    return response.data;
  }
};

// Public pre-qualification calculator (no auth required)
export const prequalifyAPI = {
  calculate: async (data) => {
    const response = await axios.post(`${API_BASE_URL}/api/v1/prequalify`, data);
    return response.data;
  }
};

// Agent Governance API
export const agentAPI = {
  // Agent Profiles
  getAgents: async (params = {}) => {
    const response = await api.get('/api/v1/agents/profiles', { params });
    return ensureArray(response.data, 'agents');
  },
  getAgent: async (agentId) => {
    const response = await api.get(`/api/v1/agents/profiles/${agentId}`);
    return response.data;
  },
  createAgent: async (data) => {
    const response = await api.post('/api/v1/agents/profiles', data);
    return response.data;
  },
  updateAgent: async (agentId, data) => {
    const response = await api.put(`/api/v1/agents/profiles/${agentId}`, data);
    return response.data;
  },
  deleteAgent: async (agentId) => {
    const response = await api.delete(`/api/v1/agents/profiles/${agentId}`);
    return response.data;
  },
  updateAgentStatus: async (agentId, status, reason = null) => {
    const response = await api.post(`/api/v1/agents/profiles/${agentId}/status`, { status, reason });
    return response.data;
  },
  getAgentHealth: async (agentId) => {
    const response = await api.get(`/api/v1/agents/profiles/${agentId}/health`);
    return response.data;
  },

  // Agent Types
  getAgentTypes: async () => {
    const response = await api.get('/api/v1/agents/types');
    return response.data;
  },

  // Executions
  getExecutions: async (params = {}) => {
    const response = await api.get('/api/v1/agents/executions', { params });
    return response.data;
  },
  getAgentExecutions: async (agentId, params = {}) => {
    const response = await api.get(`/api/v1/agents/profiles/${agentId}/executions`, { params });
    return ensureArray(response.data, 'executions');
  },
  getExecution: async (executionId) => {
    const response = await api.get(`/api/v1/agents/executions/${executionId}`);
    return response.data;
  },

  // Metrics
  getAgentMetrics: async (agentId, params = {}) => {
    const response = await api.get(`/api/v1/agents/profiles/${agentId}/metrics`, { params });
    return response.data;
  },
  getAggregatedMetrics: async (agentId, params = {}) => {
    const response = await api.get(`/api/v1/agents/profiles/${agentId}/metrics/aggregate`, { params });
    return response.data;
  },

  // Alerts
  getAlerts: async (params = {}) => {
    const response = await api.get('/api/v1/agents/alerts', { params });
    return ensureArray(response.data, 'alerts');
  },
  acknowledgeAlert: async (alertId, userId) => {
    const response = await api.post(`/api/v1/agents/alerts/${alertId}/acknowledge`, null, {
      params: { acknowledged_by: userId }
    });
    return response.data;
  },
  resolveAlert: async (alertId, userId, notes = null) => {
    const response = await api.post(`/api/v1/agents/alerts/${alertId}/resolve`, null, {
      params: { resolved_by: userId, resolution_notes: notes }
    });
    return response.data;
  },

  // Dashboard
  getDashboard: async () => {
    const response = await api.get('/api/v1/agents/dashboard');
    return response.data;
  },
  getSystemHealth: async () => {
    const response = await api.get('/api/v1/agents/health');
    return response.data;
  },
  getHealthSummary: async () => {
    const response = await api.get('/api/v1/agents/health/summary');
    return response.data;
  },
  getStatistics: async (days = 30) => {
    const response = await api.get('/api/v1/agents/statistics', { params: { days } });
    return response.data;
  },

  // Bulk Operations
  bulkPauseAgents: async (agentIds, reason = null) => {
    const response = await api.post('/api/v1/agents/bulk/pause', agentIds, { params: { reason } });
    return response.data;
  },
  bulkActivateAgents: async (agentIds) => {
    const response = await api.post('/api/v1/agents/bulk/activate', agentIds);
    return response.data;
  },

  // Seed defaults
  seedDefaultAgents: async () => {
    const response = await api.post('/api/v1/agents/seed-defaults');
    return response.data;
  },

  // Governance Settings
  getSettings: async () => {
    const response = await api.get('/api/v1/agents/governance/settings');
    return response.data;
  },
  updateSettings: async (settings) => {
    const response = await api.put('/api/v1/agents/governance/settings', settings);
    return response.data;
  },

  // Dashboard & Profiles (for AgentDashboard)
  getDashboardSummary: async () => {
    const response = await api.get('/api/v1/agents/governance/dashboard');
    return response.data;
  },
  getProfiles: async (params = {}) => {
    const response = await api.get('/api/v1/agents/profiles', { params });
    return response.data;
  }
};

// Agent Gym API
export const agentGymAPI = {
  // Scenarios
  getScenarios: async (params = {}) => {
    const response = await api.get('/api/v1/agents/gym/scenarios', { params });
    return ensureArray(response.data, 'scenarios');
  },
  getScenario: async (scenarioId) => {
    const response = await api.get(`/api/v1/agents/gym/scenarios/${scenarioId}`);
    return response.data;
  },
  createScenario: async (data) => {
    const response = await api.post('/api/v1/agents/gym/scenarios', data);
    return response.data;
  },
  updateScenario: async (scenarioId, data) => {
    const response = await api.put(`/api/v1/agents/gym/scenarios/${scenarioId}`, data);
    return response.data;
  },
  deleteScenario: async (scenarioId) => {
    const response = await api.delete(`/api/v1/agents/gym/scenarios/${scenarioId}`);
    return response.data;
  },
  getScenarioStats: async (scenarioId) => {
    const response = await api.get(`/api/v1/agents/gym/scenarios/${scenarioId}/stats`);
    return response.data;
  },

  // Training Sessions
  startSession: async (scenarioId, agentId, initiatedBy = null) => {
    const response = await api.post(`/api/v1/agents/gym/scenarios/${scenarioId}/start`, {
      agent_id: agentId,
      initiated_by: initiatedBy
    });
    return response.data;
  },
  completeSession: async (sessionId, results, score, passed, feedback = null) => {
    const response = await api.post(`/api/v1/agents/gym/sessions/${sessionId}/complete`, {
      results,
      score,
      passed,
      feedback
    });
    return response.data;
  },
  failSession: async (sessionId, error) => {
    const response = await api.post(`/api/v1/agents/gym/sessions/${sessionId}/fail`, { error });
    return response.data;
  },
  getSessions: async (params = {}) => {
    const response = await api.get('/api/v1/agents/gym/sessions', { params });
    return ensureArray(response.data, 'sessions');
  },
  getSession: async (sessionId) => {
    const response = await api.get(`/api/v1/agents/gym/sessions/${sessionId}`);
    return response.data;
  },

  // Assessment & Benchmarking
  assessAgentSkills: async (agentId) => {
    const response = await api.get(`/api/v1/agents/gym/agents/${agentId}/assessment`);
    return response.data;
  },
  getRecommendedScenarios: async (agentId, limit = 5) => {
    const response = await api.get(`/api/v1/agents/gym/agents/${agentId}/recommended-scenarios`, {
      params: { limit }
    });
    return response.data;
  },
  benchmarkAgent: async (agentId, scenarioIds = null) => {
    const params = scenarioIds ? { scenario_ids: scenarioIds.join(',') } : {};
    const response = await api.get(`/api/v1/agents/gym/agents/${agentId}/benchmark`, { params });
    return response.data;
  },
  getLeaderboard: async (params = {}) => {
    const response = await api.get('/api/v1/agents/gym/leaderboard', { params });
    return response.data;
  },

  // Scenario Generation
  generateScenarioFromExecution: async (executionId, difficulty = 'intermediate') => {
    const response = await api.post('/api/v1/agents/gym/scenarios/generate-from-execution', null, {
      params: { execution_id: executionId, difficulty }
    });
    return response.data;
  },

  // Seed defaults
  seedDefaultScenarios: async () => {
    const response = await api.post('/api/v1/agents/gym/seed-defaults');
    return response.data;
  }
};

// Agent Chat API
export const agentChatAPI = {
  // Sessions
  createSession: async (agentId, userId = null, context = null) => {
    const response = await api.post('/api/v1/agents/chat/sessions', {
      agent_id: agentId,
      user_id: userId,
      context
    });
    return response.data;
  },
  getSessions: async (params = {}) => {
    const response = await api.get('/api/v1/agents/chat/sessions', { params });
    return response.data;
  },
  getSession: async (sessionId) => {
    const response = await api.get(`/api/v1/agents/chat/sessions/${sessionId}`);
    return response.data;
  },
  closeSession: async (sessionId) => {
    const response = await api.delete(`/api/v1/agents/chat/sessions/${sessionId}`);
    return response.data;
  },

  // Messages
  sendMessage: async (sessionId, content, context = null) => {
    const response = await api.post(`/api/v1/agents/chat/sessions/${sessionId}/messages`, {
      content,
      context
    });
    return response.data;
  },
  getMessages: async (sessionId, params = {}) => {
    const response = await api.get(`/api/v1/agents/chat/sessions/${sessionId}/messages`, { params });
    return response.data;
  },

  // Quick Action (no session)
  quickAction: async (agentId, content, context = null) => {
    const response = await api.post(`/api/v1/agents/chat/quick/${agentId}`, {
      content,
      context
    });
    return response.data;
  },

  // Streaming (returns EventSource URL)
  getStreamUrl: (sessionId) => {
    return `${API_BASE_URL}/api/v1/agents/chat/sessions/${sessionId}/messages/stream`;
  }
};

// PURL (Client Portal) API
export const purlAPI = {
  // Health check for debugging
  healthCheck: async () => {
    try {
      const response = await api.get('/api/v1/purl-admin/health');
      return { success: true, data: response.data };
    } catch (error) {
      return { success: false, error: error.message, details: error.response?.data };
    }
  },

  // Get workspace by lead ID (check if portal exists for this lead)
  getWorkspaceByLead: async (leadId, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.get(`/api/v1/purl-admin/workspaces/by-lead/${leadId}`);
      return response.data;
    } catch (error) {
      // Retry on Network Error (transient failures)
      if (error.message === 'Network Error' && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.getWorkspaceByLead(leadId, retryCount + 1);
      }

      throw error;
    }
  },

  // Get workspace by loan ID
  getWorkspaceByLoan: async (loanId, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.get(`/api/v1/purl-admin/workspaces/by-loan/${loanId}`);
      return response.data;
    } catch (error) {
      if (error.message === 'Network Error' && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.getWorkspaceByLoan(loanId, retryCount + 1);
      }
      throw error;
    }
  },

  // Create new workspace (portal) for a lead/loan
  createWorkspace: async (data, retryCount = 0) => {
    const maxRetries = 2;
    try {
      const response = await api.post('/api/v1/purl-admin/workspaces', data);
      return response.data;
    } catch (error) {
      if (error.message === 'Network Error' && retryCount < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        return purlAPI.createWorkspace(data, retryCount + 1);
      }

      throw error;
    }
  },

  // Get workspace details
  getWorkspace: async (workspaceId) => {
    const response = await api.get(`/api/v1/purl-admin/workspaces/${workspaceId}`);
    return response.data;
  },

  // Get full PURL URL with active token
  getPurlUrl: async (workspaceId) => {
    const response = await api.get(`/api/v1/purl-admin/workspaces/${workspaceId}/purl-url`);
    return response.data;
  },

  // Create access token for workspace
  createToken: async (workspaceId, data = {}) => {
    const response = await api.post(`/api/v1/purl-admin/workspaces/${workspaceId}/tokens`, data);
    return response.data;
  },

  // Resend portal invitation
  resendInvite: async (workspaceId) => {
    const response = await api.post(`/api/v1/purl-admin/workspaces/${workspaceId}/resend-invite`);
    return response.data;
  },

  // List all workspaces (for admin dashboard)
  listWorkspaces: async (params = {}) => {
    const response = await api.get('/api/v1/purl-admin/workspaces', { params });
    return response.data;
  },

  // Get PURL metrics
  getMetrics: async () => {
    const response = await api.get('/api/v1/purl-admin/metrics');
    return response.data;
  }
};

// Perennia Docs API
export const perenniaDocsAPI = {
  // Template Packs
  getTemplatePacks: async () => {
    const response = await api.get('/api/v1/perennia-docs/template-packs');
    return response.data;
  },

  getTemplatePack: async (packId) => {
    const response = await api.get(`/api/v1/perennia-docs/template-packs/${packId}`);
    return response.data;
  },

  createTemplatePack: async (data) => {
    const response = await api.post('/api/v1/perennia-docs/template-packs', data);
    return response.data;
  },

  updateTemplatePack: async (packId, data) => {
    const response = await api.put(`/api/v1/perennia-docs/template-packs/${packId}`, data);
    return response.data;
  },

  deleteTemplatePack: async (packId) => {
    await api.delete(`/api/v1/perennia-docs/template-packs/${packId}`);
  },

  // Document Review Queue
  getReviewQueue: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/review-queue', { params });
    return response.data;
  },

  approveDocuments: async (documentIds) => {
    const response = await api.post('/api/v1/perennia-docs/review/approve', {
      document_ids: documentIds,
    });
    return response.data;
  },

  rejectDocuments: async (documentIds, reason) => {
    const response = await api.post('/api/v1/perennia-docs/review/reject', {
      document_ids: documentIds,
      reason,
    });
    return response.data;
  },

  requestDocumentInfo: async (documentId, message) => {
    const response = await api.post(`/api/v1/perennia-docs/review/${documentId}/request-info`, {
      message,
    });
    return response.data;
  },

  // Activity Feed
  getActivityFeed: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/activity-feed', { params });
    return response.data;
  },

  // Loan Document Requirements
  getLoanDocumentRequirements: async (loanId) => {
    const response = await api.get(`/api/v1/perennia-docs/loans/${loanId}/requirements`);
    return response.data;
  },

  updateLoanDocumentRequirements: async (loanId, documentType, data) => {
    const response = await api.patch(
      `/api/v1/perennia-docs/loans/${loanId}/requirements/${documentType}`,
      data
    );
    return response.data;
  },

  // Document Upload (for borrower portal)
  uploadDocument: async (loanId, documentType, file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    const response = await api.post(
      `/api/v1/perennia-docs/loans/${loanId}/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: onProgress
          ? (progressEvent) => {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              onProgress(percentCompleted);
            }
          : undefined,
      }
    );
    return response.data;
  },

  // Get document download URL (signed S3 URL)
  getDocumentUrl: async (documentId) => {
    const response = await api.get(`/api/v1/perennia-docs/documents/${documentId}/url`);
    return response.data;
  },

  // Portal Notifications
  getPortalNotifications: async (params = {}) => {
    const response = await api.get('/api/v1/perennia-docs/portal/notifications', { params });
    return response.data;
  },

  markNotificationRead: async (notificationId) => {
    const response = await api.patch(`/api/v1/perennia-docs/portal/notifications/${notificationId}/read`);
    return response.data;
  },

  markAllNotificationsRead: async () => {
    const response = await api.post('/api/v1/perennia-docs/portal/notifications/read-all');
    return response.data;
  },

  // Send document reminder
  sendDocumentReminder: async (loanId, documentTypes = []) => {
    const response = await api.post(`/api/v1/perennia-docs/loans/${loanId}/remind`, {
      document_types: documentTypes,
    });
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

// Income Engine API
export const incomeAPI = {
  // Get supported income types
  getSupportedTypes: async () => {
    const response = await api.get('/api/v1/income/supported-types');
    return response.data;
  },

  // Calculate income from document facts
  calculate: async (data) => {
    const response = await api.post('/api/v1/income/calculate', data);
    return response.data;
  },

  // Validate documents for calculation
  validateDocuments: async (data) => {
    const response = await api.post('/api/v1/income/validate-documents', data);
    return response.data;
  },

  // Get income summary for a loan
  getLoanSummary: async (loanId, borrowerId = 1) => {
    const response = await api.get(`/api/v1/income/loan/${loanId}/summary`, {
      params: { borrower_id: borrowerId }
    });
    return response.data;
  },

  // Get income streams for a loan
  getLoanStreams: async (loanId, borrowerId = 1) => {
    const response = await api.get(`/api/v1/income/loan/${loanId}/streams`, {
      params: { borrower_id: borrowerId }
    });
    return response.data;
  },

  // Get income flags for a loan
  getLoanFlags: async (loanId, borrowerId = 1, severity = null) => {
    const params = { borrower_id: borrowerId };
    if (severity) params.severity = severity;
    const response = await api.get(`/api/v1/income/loan/${loanId}/flags`, { params });
    return response.data;
  },

  // Resolve an income flag
  resolveFlag: async (loanId, flagId, resolutionNote = '', resolvedBy = null) => {
    const response = await api.post(`/api/v1/income/loan/${loanId}/flags/${flagId}/resolve`, null, {
      params: { resolution_note: resolutionNote, resolved_by: resolvedBy }
    });
    return response.data;
  },

  // Get income worksheets
  getWorksheets: async (loanId, borrowerId = 1, worksheetType = null) => {
    const params = { borrower_id: borrowerId };
    if (worksheetType) params.worksheet_type = worksheetType;
    const response = await api.get(`/api/v1/income/loan/${loanId}/worksheets`, { params });
    return response.data;
  },
};

// Salesforce Integration API
export const salesforceAPI = {
  // Get connection status
  getStatus: async () => {
    const response = await api.get('/api/v1/salesforce/status');
    return response.data;
  },

  // Connect to Salesforce (returns auth URL)
  connect: async (redirectUrl = null) => {
    const params = redirectUrl ? { redirect_url: redirectUrl } : {};
    const response = await api.get('/api/v1/salesforce/connect', { params });
    return response.data;
  },

  // Disconnect from Salesforce
  disconnect: async () => {
    const response = await api.delete('/api/v1/salesforce/disconnect');
    return response.data;
  },

  // Test connection
  testConnection: async () => {
    const response = await api.get('/api/v1/salesforce/test-connection');
    return response.data;
  },

  // Push single loan to Salesforce
  pushLoan: async (loanId, sfObject = null) => {
    const params = sfObject ? { sf_object: sfObject } : {};
    const response = await api.post(`/api/v1/salesforce/push/loan/${loanId}`, null, { params });
    return response.data;
  },

  // Push multiple loans to Salesforce
  pushBatch: async (loanIds, sfObject = null) => {
    const response = await api.post('/api/v1/salesforce/push/batch', {
      loan_ids: loanIds,
      sf_object: sfObject || 'MtgPlanner_CRM__Transaction_Property__c'
    });
    return response.data;
  },

  // Get loans pending push
  getPendingLoans: async (limit = 50) => {
    const response = await api.get('/api/v1/salesforce/push/pending', { params: { limit } });
    return response.data;
  },

  // Get sync status for a loan
  getLoanSyncStatus: async (loanId) => {
    const response = await api.get(`/api/v1/salesforce/loan/${loanId}/sync-status`);
    return response.data;
  },

  // Pull/refresh single loan from Salesforce
  pullLoan: async (loanId, sfObject = null) => {
    const params = sfObject ? { sf_object: sfObject } : {};
    const response = await api.post(`/api/v1/salesforce/pull/loan/${loanId}`, null, { params });
    return response.data;
  },

  // Full sync from Salesforce
  fullSync: async () => {
    const response = await api.post('/api/v1/salesforce/sync/full');
    return response.data;
  },

  // Sync ALL loans from Salesforce (links unlinked loans and pulls all data)
  syncAllLoans: async () => {
    const response = await api.post('/api/v1/salesforce/sync-all-loans');
    return response.data;
  },

  // Get sync history
  getSyncHistory: async (limit = 20) => {
    const response = await api.get('/api/v1/salesforce/sync/history', { params: { limit } });
    return response.data;
  },

  // Import closed loans
  importClosedLoans: async () => {
    const response = await api.post('/api/v1/salesforce/import-closed-loans');
    return response.data;
  },

  // Get field mappings
  getMappings: async () => {
    const response = await api.get('/api/v1/salesforce/mappings');
    return response.data;
  },

  // Save field mapping
  saveMapping: async (mapping) => {
    const response = await api.post('/api/v1/salesforce/mappings', mapping);
    return response.data;
  },

  // Explore objects
  getObjects: async () => {
    const response = await api.get('/api/v1/salesforce/explore/objects');
    return response.data;
  },

  // Get object fields
  getObjectFields: async (objectName) => {
    const response = await api.get(`/api/v1/salesforce/explore/objects/${objectName}`);
    return response.data;
  },
};

// Rate Monitor API
export const rateMonitorAPI = {
  // Dashboard
  getDashboard: async () => {
    const response = await api.get('/api/v1/rate-monitor/dashboard');
    return response.data;
  },

  // Current rates
  getCurrentRates: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/current-rates', { params });
    return response.data;
  },

  // Targets
  getTargets: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/targets', { params });
    return response.data;
  },

  getTarget: async (targetId) => {
    const response = await api.get(`/api/v1/rate-monitor/targets/${targetId}`);
    return response.data;
  },

  createTarget: async (data) => {
    const response = await api.post('/api/v1/rate-monitor/targets', data);
    return response.data;
  },

  updateTarget: async (targetId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/targets/${targetId}`, data);
    return response.data;
  },

  deleteTarget: async (targetId) => {
    const response = await api.delete(`/api/v1/rate-monitor/targets/${targetId}`);
    return response.data;
  },

  // Check opportunity for a MUM client
  checkOpportunity: async (mumClientId, params = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/check-opportunity/${mumClientId}`, params);
    return response.data;
  },

  // Alerts
  getAlerts: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/alerts', { params });
    return response.data;
  },

  getAlert: async (alertId) => {
    const response = await api.get(`/api/v1/rate-monitor/alerts/${alertId}`);
    return response.data;
  },

  updateAlert: async (alertId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/alerts/${alertId}`, data);
    return response.data;
  },

  initiateCall: async (alertId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/alerts/${alertId}/initiate-call`, data);
    return response.data;
  },

  // History
  getHistory: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/history', { params });
    return response.data;
  },
};

// Rate Sheet API (Rate Sheet Upload & Refinance Opportunities)
export const rateSheetAPI = {
  // Rate Sheets
  uploadSheet: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/api/v1/rate-monitor/sheets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getSheets: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/sheets', { params });
    return response.data;
  },

  getSheet: async (sheetId) => {
    const response = await api.get(`/api/v1/rate-monitor/sheets/${sheetId}`);
    return response.data;
  },

  getSheetRates: async (sheetId, params = {}) => {
    const response = await api.get(`/api/v1/rate-monitor/sheets/${sheetId}/rates`, { params });
    return response.data;
  },

  deleteSheet: async (sheetId) => {
    const response = await api.delete(`/api/v1/rate-monitor/sheets/${sheetId}`);
    return response.data;
  },

  scanForOpportunities: async (sheetId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/sheets/${sheetId}/scan`, data);
    return response.data;
  },

  // Opportunities
  getOpportunities: async (params = {}) => {
    const response = await api.get('/api/v1/rate-monitor/opportunities', { params });
    return response.data;
  },

  getOpportunitiesDashboard: async () => {
    const response = await api.get('/api/v1/rate-monitor/opportunities/dashboard');
    return response.data;
  },

  getOpportunity: async (opportunityId) => {
    const response = await api.get(`/api/v1/rate-monitor/opportunities/${opportunityId}`);
    return response.data;
  },

  updateOpportunity: async (opportunityId, data) => {
    const response = await api.patch(`/api/v1/rate-monitor/opportunities/${opportunityId}`, data);
    return response.data;
  },

  // Outreach
  triggerOutreach: async (opportunityId, data = {}) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/outreach`, data);
    return response.data;
  },

  sendSMS: async (opportunityId) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/sms`);
    return response.data;
  },

  initiateCall: async (opportunityId, customMessage = null) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/call`, null, {
      params: customMessage ? { custom_message: customMessage } : {},
    });
    return response.data;
  },

  bulkOutreach: async (opportunityIds, skipSms = false) => {
    const response = await api.post('/api/v1/rate-monitor/opportunities/bulk-outreach', {
      opportunity_ids: opportunityIds,
      skip_sms: skipSms,
    });
    return response.data;
  },

  markOptedOut: async (opportunityId) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/opt-out`);
    return response.data;
  },

  markConverted: async (opportunityId, notes = null) => {
    const response = await api.post(`/api/v1/rate-monitor/opportunities/${opportunityId}/convert`, null, {
      params: notes ? { notes } : {},
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
    const token = localStorage.getItem('token');
    // Security: Browser WebSocket API does not support Authorization headers; token in URL is the only option.
    return `${wsBase}/api/v1/call-monitoring/sessions/${sessionId}/audio-stream?token=${token}`;
  },
};

// ==================== Email Drafts ====================
export const emailDraftsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/email-drafts', { params });
    return response.data;
  },

  getCallDrafts: async () => {
    const response = await api.get('/api/v1/email-drafts', {
      params: { source_type: 'call_recording', status: 'draft' }
    });
    return response.data.drafts || [];
  },

  getById: async (id) => {
    const response = await api.get(`/api/v1/email-drafts/${id}`);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/api/v1/email-drafts/${id}`, data);
    return response.data;
  },

  send: async (id) => {
    const response = await api.post(`/api/v1/email-drafts/${id}/send`);
    return response.data;
  },

  delete: async (id) => {
    const response = await api.delete(`/api/v1/email-drafts/${id}`);
    return response.data;
  },
};

// Agent Performance Metrics API
export const agentMetricsAPI = {
  getAgentMetrics: async (days = 30) => {
    const response = await api.get('/api/v1/agents/performance/metrics', { params: { days } });
    return response.data;
  },
  getAgentToolMetrics: async (days = 30) => {
    const response = await api.get('/api/v1/agents/performance/tools', { params: { days } });
    return response.data;
  },
  getAgentErrors: async (days = 30, limit = 50) => {
    const response = await api.get('/api/v1/agents/performance/errors', { params: { days, limit } });
    return response.data;
  },
};

export default api;
