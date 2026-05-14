/**
 * AI domain -- chat, orchestrator streaming, agents, feedback, conversations.
 */
import api from './client';
import { API_BASE_URL } from './client';
import { attemptTokenRefresh } from './auth';
import { ensureArray } from '../../utils/arrayHelpers.js';
import { getToken } from '../../utils/tokenStore';

// AI Assistant & Conversations
export const aiAPI = {
  chat: async (message: string, context: any = {}) => {
    const response = await api.post('/api/v1/ai/chat', {
      message,
      lead_id: context.lead_id,
      loan_id: context.loan_id,
      context: context.metadata,
    });
    return response.data;
  },
  smartChat: async (message: string, context: any = {}) => {
    const response = await api.post('/api/v1/ai/smart-chat', {
      message,
      lead_id: context.lead_id,
      loan_id: context.loan_id,
      include_context: context.include_context !== false,
      coaching_mode: context.coaching_mode,
      context_type: context.context_type,
    });
    return response.data;
  },
  getMemoryStats: async () => {
    const response = await api.get('/api/v1/ai/memory-stats');
    return response.data;
  },
  coach: async (mode: string, message: string | null = null) => {
    const response = await api.post('/api/v1/coach', { mode, message });
    return response.data;
  },
  completeTask: async (taskId: string) => {
    const response = await api.post(`/api/v1/ai/complete-task?task_id=${taskId}`);
    return response.data;
  },
  getSuggestions: async () => {
    const response = await api.get('/api/v1/ai/suggestions');
    return ensureArray(response.data, 'suggestions');
  },
  processCommand: async (message: string, context: any = {}) => {
    const coachingKeywords = [
      'daily briefing', 'pipeline audit', 'focus reset', 'what should i do',
      'accountability review', 'tough love', 'teach me', 'priorities',
      'what are my', 'help me focus', 'review my performance'
    ];
    const isCoachingMode = coachingKeywords.some(kw =>
      message.toLowerCase().includes(kw)
    );

    let userContext: any = {};
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

    const response = await api.post('/api/v1/ai/orchestrator-chat', {
      message,
      lead_id: context.lead_id || null,
      loan_id: context.loan_id || null,
      context: {
        coaching_mode: isCoachingMode,
        user_context: userContext
      }
    });

    const data = response.data;
    return {
      explanation: data.response || '',
      intent: data.intent,
      entities: data.entities,
      agent_used: data.agent_used,
      confidence: data.confidence,
      execution_id: data.execution_id,
      fallback: data.fallback,
      success: true,
      ...data
    };
  },
  processCommandStream: async (
    message: string,
    onContent: ((content: string) => void) | null,
    onStatus: ((status: string) => void) | null,
    onDone: ((response: string, meta: any) => void) | null,
    onError: ((error: string) => void) | null,
    documentContext: any = null,
    sessionId: string | null = null,
    leadId: string | null = null,
    loanId: string | null = null,
    abortSignal: AbortSignal | null = null
  ) => {
    let token = getToken();

    try {
      if (onStatus) onStatus('Analyzing your request...');

      const body: any = { message };
      if (documentContext) body.document_context = documentContext;
      if (sessionId) body.session_id = sessionId;
      if (leadId) body.lead_id = leadId;
      if (loanId) body.loan_id = loanId;

      // --- Attempt true SSE streaming first ---
      const controller = new AbortController();
      const streamTimeout = setTimeout(() => controller.abort(), 120000);
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
          const reader = sseResponse.body!.getReader();
          const decoder = new TextDecoder();
          let fullResponse = '';
          let buffer = '';
          let metadata: any = {};
          let doneSignaled = false;

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

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
                  clearTimeout(streamTimeout);
                  onError(payload.error);
                  return;
                } else if (payload.done) {
                  doneSignaled = true;
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

          if (buffer.trim().startsWith('data: ')) {
            try {
              const payload = JSON.parse(buffer.trim().slice(6));
              if (payload.content && onContent) {
                fullResponse += payload.content;
                onContent(payload.content);
              }
              if (payload.done) {
                doneSignaled = true;
                metadata = { session_id: payload.session_id, engine: payload.engine || 'langgraph' };
              }
            } catch (_) {}
          }

          if (onDone) {
            onDone(fullResponse, {
              full_response: fullResponse,
              engine: metadata.engine || 'langgraph',
              ...metadata,
              ...(doneSignaled ? {} : { incomplete: true }),
            });
          }
          return;
        }
        clearTimeout(streamTimeout);
      } catch (sseErr: any) {
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

      if (!response.ok) {
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

      if (data.error) {
        if (onError) onError(data.error);
        return;
      }

      const fullResponse = data.response || '';
      if (fullResponse && onContent) {
        const paragraphs = fullResponse.split('\n\n');
        for (const para of paragraphs) {
          if (para.trim()) {
            onContent(para + '\n\n');
            await new Promise(resolve => setTimeout(resolve, 50));
          }
        }
      }

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
    } catch (error: any) {
      console.error('LangGraph chat error:', error);
      if (onError) onError(error.message);
    }
  },
  executeAction: async (actionId: string, modifications = {}, sessionId: string | null = null) => {
    const response = await api.post('/api/v1/ai/execute-action', {
      action_id: actionId,
      session_id: sessionId,
      modifications,
    });
    return response.data;
  },
  parseScreenshot: async (imageFile: File) => {
    const formData = new FormData();
    formData.append('image', imageFile);
    const response = await api.post('/api/v1/ai/parse-screenshot', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  extractDocument: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/api/v1/ai/extract-document', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  createLeadFromScreenshot: async (leadData: any) => {
    const response = await api.post('/api/v1/ai/create-lead-from-screenshot', leadData);
    return response.data;
  },
  submitTrainingInstruction: async (instruction: string, taskContext = {}) => {
    const response = await api.post('/api/v1/ai/training/instruction', {
      instruction,
      task_context: taskContext
    });
    return response.data;
  },
  submitInlineFeedback: async ({ sessionId, messageId, rating, userQuestion, aiResponse }: {
    sessionId: string; messageId: string; rating: number; userQuestion: string; aiResponse: string;
  }) => {
    const response = await api.post('/api/v1/ai/feedback', {
      session_id: sessionId,
      message_id: messageId,
      rating,
      user_question: userQuestion,
      ai_response: aiResponse,
    });
    return response.data;
  },
  submitFeedback: async (feedbackData: any) => {
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
  updateFeedback: async (feedbackId: number, updateData: any) => {
    const response = await api.patch(`/api/v1/ai-feedback/${feedbackId}`, updateData);
    return response.data;
  },
  deleteFeedback: async (feedbackId: number) => {
    const response = await api.delete(`/api/v1/ai-feedback/${feedbackId}`);
    return response.data;
  },
};

export const conversationsAPI = {
  getAll: async (params = {}) => {
    const response = await api.get('/api/v1/conversations', { params });
    return ensureArray(response.data, 'conversations');
  },
  create: async (data: any) => {
    const response = await api.post('/api/v1/conversations/', data);
    return response.data;
  },
};
