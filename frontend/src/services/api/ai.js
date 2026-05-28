/**
 * AI Assistant, Agents, Conversations, and Agent Governance API calls.
 */
import api, { API_BASE_URL, attemptTokenRefresh, ensureArray } from './client.js';
import { getToken } from '../../utils/tokenStore';

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
  processCommandStream: async (message, onContent, onStatus, onDone, onError, documentContext = null, sessionId = null, leadId = null, loanId = null, abortSignal = null) => {
    let token = getToken();

    try {
      // Show initial status
      if (onStatus) onStatus('Analyzing your request...');

      const body = { message };
      if (documentContext) {
        body.document_context = documentContext;
      }
      if (sessionId) {
        body.session_id = sessionId;
      }
      if (leadId) { body.lead_id = leadId; }
      if (loanId) { body.loan_id = loanId; }

      // --- Attempt true SSE streaming first ---
      const controller = new AbortController();
      const streamTimeout = setTimeout(() => controller.abort(), 120000);
      // If caller provided an external signal, listen for it too
      if (abortSignal) {
        abortSignal.addEventListener('abort', () => controller.abort());
      }
      try {
        let sseResponse = await fetch(`${API_BASE_URL}/api/v1/ai/orchestrator-chat-stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(body),
          signal: controller.signal
        });

        // On 401, attempt a silent token refresh and retry once
        if (sseResponse.status === 401) {
          const refreshed = await attemptTokenRefresh();
          if (refreshed) {
            token = getToken();
            sseResponse = await fetch(`${API_BASE_URL}/api/v1/ai/orchestrator-chat-stream`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
              },
              body: JSON.stringify(body),
              signal: controller.signal
            });
          }
        }

        // Bug 1 fix: surface non-2xx errors instead of silently falling through to fallback
        if (!sseResponse.ok) {
          clearTimeout(streamTimeout);
          let errorMsg = `Request failed (${sseResponse.status})`;
          try {
            const errData = await sseResponse.json();
            errorMsg = errData.detail || errData.error || errorMsg;
          } catch (_) {}
          if (sseResponse.status === 429) {
            const retryAfter = sseResponse.headers.get('Retry-After');
            errorMsg = `Rate limit exceeded.${retryAfter ? ` Try again in ${retryAfter}s.` : ' Please wait.'}`;
          }
          if (onError) onError(errorMsg);
          return;
        }

        if (sseResponse.ok && sseResponse.headers.get('content-type')?.includes('text/event-stream')) {
          // True SSE stream available — read tokens in real-time
          const reader = sseResponse.body.getReader();
          const decoder = new TextDecoder();
          let fullResponse = '';
          let buffer = '';
          let metadata = {};
          let doneSignaled = false; // Bug 3 fix: track whether done event was received

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
                  clearTimeout(streamTimeout); // Bug 2 fix: clear timer before returning on error
                  onError(payload.error);
                  return;
                } else if (payload.done) {
                  doneSignaled = true; // Bug 3 fix: mark done received
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

          clearTimeout(streamTimeout);

          // Flush any remaining buffer content
          if (buffer.trim().startsWith('data: ')) {
            try {
              const payload = JSON.parse(buffer.trim().slice(6));
              if (payload.content && onContent) {
                fullResponse += payload.content;
                onContent(payload.content);
              }
              if (payload.done) {
                doneSignaled = true; // Bug 3 fix: mark done received from buffer flush
                metadata = { session_id: payload.session_id, engine: payload.engine || 'langgraph' };
              }
            } catch (_) {}
          }

          // Signal completion
          if (onDone) {
            onDone(fullResponse, {
              full_response: fullResponse,
              engine: metadata.engine || 'langgraph',
              ...metadata,
              // Bug 3 fix: flag incomplete streams so callers can handle gracefully
              ...(doneSignaled ? {} : { incomplete: true }),
            });
          }
          return; // SSE path succeeded — skip fallback
        }
        clearTimeout(streamTimeout);
        // If response is not SSE (e.g. 404 or wrong content-type), fall through to non-streaming
      } catch (sseErr) {
        clearTimeout(streamTimeout);
        if (sseErr.name === 'AbortError') {
          if (onError) onError('Request timed out after 2 minutes. Please try again.');
          return;
        }
        console.warn('SSE streaming unavailable, falling back to non-streaming:', sseErr.message);
      }

      // --- Fallback: non-streaming endpoint with simulated chunking ---
      let response = await fetch(`${API_BASE_URL}/api/v1/ai/langgraph-chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(body)
      });

      // On 401, attempt a silent token refresh and retry once
      if (response.status === 401) {
        const refreshed = await attemptTokenRefresh();
        if (refreshed) {
          token = getToken();
          response = await fetch(`${API_BASE_URL}/api/v1/ai/langgraph-chat`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(body)
          });
        }
      }

      // Bug 4 fix: surface structured error messages instead of throwing raw status
      if (!response.ok) {
        clearTimeout(streamTimeout);
        let errorMsg = `Request failed (${response.status})`;
        try {
          const errData = await response.json();
          errorMsg = errData.detail || errData.error || errorMsg;
        } catch (_) {}
        if (response.status === 429) {
          const retryAfter = response.headers.get('Retry-After');
          errorMsg = `Rate limit exceeded.${retryAfter ? ` Try again in ${retryAfter}s.` : ' Please wait.'}`;
        }
        if (onError) onError(errorMsg);
        return;
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
          session_id: data.session_id,
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
  getTrainingInstructions: async (taskType) => {
    const params = taskType ? { task_type: taskType } : {};
    const response = await api.get('/api/v1/ai/training/instructions', { params });
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
