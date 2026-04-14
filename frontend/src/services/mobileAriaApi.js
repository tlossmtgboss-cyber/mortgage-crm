/**
 * Mobile Aria API Service
 *
 * API client for Aria AI interactions on the mobile app:
 * - Orchestrator chat (conversational AI)
 * - Autonomous task execution (SMS, tasks, appointments)
 * - Smart context suggestions
 * - Morning briefings
 * - Lead and loan AI analysis
 * - Call intelligence session artifacts
 * - Caller lookup
 */

import api from './api';

// =============================================================================
// FEEDBACK
// =============================================================================

/**
 * Submit feedback (thumbs up/down) on an AI message.
 *
 * POST /api/v1/ai-feedback/
 *
 * @param {string} sessionId - Chat session ID
 * @param {string} messageId - The message ID being rated
 * @param {string} rating - "positive" or "negative"
 * @param {string} feedbackText - Optional text feedback (max 200 chars)
 * @returns {Promise<Object>} Feedback submission result
 */
export async function submitMessageFeedback(sessionId, messageId, rating, feedbackText = '') {
  try {
    const response = await api.post('/api/v1/ai-feedback/', {
      session_id: sessionId,
      message_id: messageId,
      rating,
      feedback_text: feedbackText,
      source: 'mobile_aria_chat',
    });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] submitMessageFeedback error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to submit feedback';
    return { success: false, error: errMsg };
  }
}

// =============================================================================
// CHAT & ORCHESTRATION
// =============================================================================

/**
 * Send a chat message to Aria.
 *
 * POST /api/v1/ai/orchestrator-chat
 *
 * @param {string} message - The user's message text
 * @param {string|null} sessionId - Existing session ID (null to start new session)
 * @param {Object} options - Optional extras (document_context, etc.)
 * @returns {Promise<{
 *   success: boolean,
 *   response: string,
 *   session_id: string,
 *   intent: string,
 *   confidence: number,
 *   follow_up_suggestions: string[],
 *   actions_executed: Object[],
 *   actions_pending: Object[]
 * }>}
 */
export async function sendMessage(message, sessionId = null, options = {}, { signal } = {}) {
  try {
    const body = {
      message,
      ...(sessionId && { session_id: sessionId }),
      ...options,
    };
    const response = await api.post('/api/v1/ai/orchestrator-chat', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] sendMessage error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to send message';
    return { success: false, error: errMsg };
  }
}

/**
 * Stream a chat message to Aria via SSE.
 *
 * POST /api/v1/ai/orchestrator-chat-stream
 *
 * Calls `onChunk(text)` for each token as it arrives, and
 * `onDone(fullText, sessionId)` when the stream completes.
 * Returns an abort function the caller can use to cancel.
 *
 * @param {string} message
 * @param {string|null} sessionId
 * @param {Object} callbacks - { onChunk, onDone, onError }
 * @returns {{ abort: () => void }}
 */
export function streamMessage(message, sessionId = null, { onChunk, onDone, onError } = {}) {
  const controller = new AbortController();

  (async () => {
    try {
      // Build auth header — read token the same way the axios instance does
      const { getItem, STORAGE_KEYS } = await import('../utils/storage');
      const token = await getItem(STORAGE_KEYS.AUTH_TOKEN);

      const res = await fetch(`${api.defaults.baseURL}/api/v1/ai/orchestrator-chat-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: JSON.stringify({
          message,
          ...(sessionId && { session_id: sessionId }),
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.content) {
              fullText += data.content;
              onChunk?.(data.content, fullText);
            }
            if (data.done) {
              onDone?.(fullText, data.session_id);
            }
            if (data.error) {
              onError?.(data.error);
            }
          } catch { /* skip malformed SSE lines */ }
        }
      }

      // If stream ended without a 'done' event, fire onDone anyway
      if (fullText) {
        onDone?.(fullText, sessionId);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('[mobileAriaApi] streamMessage error:', err);
        onError?.(err.message || 'Stream failed');
      }
    }
  })();

  return { abort: () => controller.abort() };
}

/**
 * Execute an autonomous task via Aria (send SMS, create task, schedule appointment, etc.).
 *
 * POST /api/v1/ai/autonomous-task
 *
 * @param {string} task - Natural language task description
 * @param {Object} context - Optional context (lead_id, lead_name, lead_phone, context)
 * @returns {Promise<{
 *   success: boolean,
 *   message: string,
 *   activity_log: Object[],
 *   final_response: string
 * }>}
 */
export async function executeTask(task, context = {}, { signal } = {}) {
  try {
    const body = { task, ...context };
    const response = await api.post('/api/v1/ai/autonomous-task', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] executeTask error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to execute task';
    return { success: false, error: errMsg };
  }
}

/**
 * Get AI-powered suggestions for a specific context (lead, loan, or general next steps).
 *
 * POST /api/v1/ai/smart-chat
 *
 * @param {Object} context - { lead_id?, loan_id?, message? }
 * @returns {Promise<Object>} AI suggestion response
 */
export async function getAISuggestions(context = {}, { signal } = {}) {
  try {
    const body = {
      message: context.message || 'What should I do next?',
      include_context: true,
      ...(context.lead_id && { lead_id: context.lead_id }),
      ...(context.loan_id && { loan_id: context.loan_id }),
    };
    const response = await api.post('/api/v1/ai/smart-chat', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] getAISuggestions error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to get suggestions';
    return { success: false, error: errMsg };
  }
}

// =============================================================================
// BRIEFINGS & ANALYSIS
// =============================================================================

/**
 * Get an AI-generated morning briefing for the dashboard.
 *
 * POST /api/v1/ai/orchestrator-chat
 *
 * @param {string|null} sessionId - Optional session ID
 * @returns {Promise<Object>} Orchestrator chat response with briefing content
 */
export async function getMorningBriefing(sessionId = null, { signal } = {}) {
  try {
    const body = {
      message: 'Give me a brief morning briefing — top priorities, pipeline health, and any urgent items I should know about today.',
      ...(sessionId && { session_id: sessionId }),
    };
    const response = await api.post('/api/v1/ai/orchestrator-chat', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] getMorningBriefing error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to get morning briefing';
    return { success: false, error: errMsg };
  }
}

/**
 * Get AI analysis for a specific lead.
 *
 * POST /api/v1/ai/smart-chat
 *
 * @param {string} leadId - Lead ID to analyze
 * @returns {Promise<Object>} AI analysis response
 */
export async function analyzeLeadForMobile(leadId, { signal } = {}) {
  try {
    const body = {
      message: 'Analyze this lead — score, engagement history, recommended next actions, and any red flags.',
      lead_id: leadId,
      include_context: true,
    };
    const response = await api.post('/api/v1/ai/smart-chat', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] analyzeLeadForMobile error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to analyze lead';
    return { success: false, error: errMsg };
  }
}

/**
 * Get AI analysis for a specific loan.
 *
 * POST /api/v1/ai/smart-chat
 *
 * @param {string} loanId - Loan ID to analyze
 * @returns {Promise<Object>} AI analysis response
 */
export async function analyzeLoanForMobile(loanId, { signal } = {}) {
  try {
    const body = {
      message: 'Analyze this loan — stage, outstanding conditions, SLA status, third-party order status, and recommended next steps.',
      loan_id: loanId,
      include_context: true,
    };
    const response = await api.post('/api/v1/ai/smart-chat', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] analyzeLoanForMobile error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to analyze loan';
    return { success: false, error: errMsg };
  }
}

// =============================================================================
// ARIA AUTONOMOUS ACTIONS
// =============================================================================

/**
 * Send an SMS via Aria's autonomous task engine.
 *
 * POST /api/v1/ai/autonomous-task
 *
 * @param {string} recipientName - Display name of the recipient
 * @param {string} phone - Recipient phone number (E.164 or local)
 * @param {string} message - SMS body text
 * @returns {Promise<Object>} Task execution result
 */
export async function sendSMSViaAria(recipientName, phone, message, { signal } = {}) {
  try {
    const body = {
      task: `Send SMS to ${recipientName} at ${phone}: ${message}`,
    };
    const response = await api.post('/api/v1/ai/autonomous-task', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] sendSMSViaAria error:', error);
    const msg = error.response?.data?.detail || error.message || 'Failed to send SMS via Aria';
    return { success: false, error: msg };
  }
}

/**
 * Create a task via Aria's autonomous task engine.
 *
 * POST /api/v1/ai/autonomous-task
 *
 * @param {string} title - Task title / description
 * @param {string} dueDate - Due date string (e.g. "tomorrow", "2026-04-15")
 * @param {string|null} leadId - Optional lead to associate the task with
 * @returns {Promise<Object>} Task execution result
 */
export async function createTaskViaAria(title, dueDate, leadId = null, { signal } = {}) {
  try {
    const body = {
      task: `Create a task: ${title} due ${dueDate}`,
      ...(leadId && { lead_id: leadId }),
    };
    const response = await api.post('/api/v1/ai/autonomous-task', body, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] createTaskViaAria error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to create task via Aria';
    return { success: false, error: errMsg };
  }
}

// =============================================================================
// CALL INTELLIGENCE
// =============================================================================

/**
 * Get call intelligence session artifacts (transcripts, summaries, action items).
 *
 * GET /api/v1/call-monitoring/sessions/{sessionId}/artifacts
 *
 * @param {string} sessionId - CI session ID
 * @returns {Promise<Object>} Artifacts response
 */
export async function getSessionArtifacts(sessionId, { signal } = {}) {
  try {
    const response = await api.get(`/api/v1/call-monitoring/sessions/${sessionId}/artifacts`, { signal });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] getSessionArtifacts error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to get session artifacts';
    return { success: false, error: errMsg };
  }
}

/**
 * Approve specific call intelligence artifacts.
 *
 * POST /api/v1/call-monitoring/sessions/{sessionId}/artifacts/approve
 *
 * @param {string} sessionId - CI session ID
 * @param {string[]} artifactIds - Array of artifact IDs to approve
 * @returns {Promise<Object>} Approval result
 */
export async function approveArtifacts(sessionId, artifactIds, { signal } = {}) {
  try {
    const response = await api.post(
      `/api/v1/call-monitoring/sessions/${sessionId}/artifacts/approve`,
      { artifact_ids: artifactIds },
      { signal }
    );
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] approveArtifacts error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to approve artifacts';
    return { success: false, error: errMsg };
  }
}

/**
 * Execute approved call intelligence artifacts (create tasks, send follow-ups, etc.).
 *
 * POST /api/v1/call-monitoring/sessions/{sessionId}/artifacts/execute
 *
 * @param {string} sessionId - CI session ID
 * @param {string[]|null} artifactIds - Specific artifact IDs to execute, or null for all approved
 * @returns {Promise<Object>} Execution result
 */
export async function executeArtifacts(sessionId, artifactIds = null, { signal } = {}) {
  try {
    const body = artifactIds ? { artifact_ids: artifactIds } : {};
    const response = await api.post(
      `/api/v1/call-monitoring/sessions/${sessionId}/artifacts/execute`,
      body,
      { signal }
    );
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] executeArtifacts error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to execute artifacts';
    return { success: false, error: errMsg };
  }
}

/**
 * Lookup a caller by phone number to identify leads or clients.
 *
 * GET /api/v1/call-monitoring/lookup-caller?phone={phone}
 *
 * @param {string} phone - Phone number to look up
 * @returns {Promise<Object>} Caller identity data
 */
export async function lookupCaller(phone, { signal } = {}) {
  try {
    const response = await api.get('/api/v1/call-monitoring/lookup-caller', {
      params: { phone },
      signal,
    });
    return response.data;
  } catch (error) {
    console.error('[mobileAriaApi] lookupCaller error:', error);
    const errMsg = error.response?.data?.detail || error.message || 'Failed to lookup caller';
    return { success: false, error: errMsg };
  }
}
