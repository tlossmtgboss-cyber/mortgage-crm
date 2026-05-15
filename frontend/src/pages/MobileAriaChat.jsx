/**
 * MobileAriaChat
 *
 * Full-screen mobile AI chat interface for Perennia AI.
 * This is the primary interaction surface for loan officers on their phones.
 *
 * Features:
 * - Persistent conversation via session_id
 * - Voice input via useAriaVoice hook (native + Web Speech API fallback)
 * - Inline action cards for executed AI actions
 * - Follow-up suggestion chips
 * - Quick command shortcuts
 * - Context-aware via route params (leadId, leadName)
 * - localStorage session persistence (last 50 messages)
 * - Haptic feedback, safe-area insets, keyboard avoidance
 */

import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
} from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { sendMessage as sendAriaMessage, executeTask, submitMessageFeedback } from '../services/mobileAriaApi';
import api from '../services/api';
import { useAriaVoice } from '../hooks/useAriaVoice';
import { auditLog, AUDIT_EVENTS } from '../services/mobileAuditLogger';
import { toast } from '../utils/toast';
import MobileBottomNav from '../components/mobile/MobileBottomNav';
import './MobileAriaChat.css';

// ── Constants ────────────────────────────────────────────────────────────────

const SESSION_KEY = 'aria_chat_session';
const MESSAGES_KEY = 'aria_chat_messages';
const FEEDBACK_KEY = 'aria_chat_feedback';
const MAX_STORED_MESSAGES = 50;

const QUICK_COMMANDS = [
  { label: 'Send SMS to…', text: 'Send SMS to ' },
  { label: 'Create a task…', text: 'Create a task: ' },
  { label: 'Check my pipeline', text: 'Check my pipeline' },
  { label: 'Rate lock alerts', text: 'Show my rate lock alerts' },
  { label: 'Schedule a call…', text: 'Schedule a call with ' },
  { label: 'Draft an email…', text: 'Draft an email to ' },
  { label: "How's my pipeline?", text: "How's my pipeline doing?" },
  { label: 'Who should I call?', text: 'Who should I call next?' },
];

// Map action types to display config
const ACTION_CONFIG = {
  sms_sent: {
    color: '#2D7A52',
    bg: '#f0fdf4',
    border: '#2D7A52',
    label: 'SMS Sent',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  task_created: {
    color: '#1a73e8',
    bg: '#eff6ff',
    border: '#1a73e8',
    label: 'Task Created',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    ),
  },
  appointment_scheduled: {
    color: '#B8924A',
    bg: '#FDF9F0',
    border: '#B8924A',
    label: 'Appointment Scheduled',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
  },
};

function getActionConfig(actionType) {
  if (!actionType) return null;
  const key = actionType.toLowerCase();
  return ACTION_CONFIG[key] || {
    color: '#6b7280',
    bg: '#f9fafb',
    border: '#6b7280',
    label: actionType.replace(/_/g, ' '),
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  };
}

// Map action types to navigation paths
function getActionRoute(action) {
  if (!action) return null;
  const type = (action.type || '').toLowerCase();
  if (type === 'task_created' && action.task_id) return `/tasks/${action.task_id}`;
  if (type === 'sms_sent' && action.lead_id) return `/leads/${action.lead_id}`;
  if (type === 'appointment_scheduled' && action.appointment_id) return `/calendar`;
  return null;
}

// Attempt haptic feedback silently
async function triggerHaptic(type = 'light') {
  try {
    const { haptics } = await import('../services/nativeServices');
    if (haptics && haptics[type]) {
      await haptics[type]();
    }
  } catch (_) {
    // Haptics unavailable — web or package not loaded
  }
}

// Generate a simple unique ID for messages
let _msgIdCounter = Date.now();
function newId() {
  return `msg_${++_msgIdCounter}`;
}

function formatTime(date) {
  return new Date(date).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

// ── Sub-components ───────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="mac__bubble mac__bubble--aria mac__typing-bubble" aria-label="Aria is typing">
      <div className="mac__typing-dots">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function ActionCard({ action, onNavigate }) {
  const config = getActionConfig(action.type);
  if (!config) return null;

  const route = getActionRoute(action);

  return (
    <div
      className="mac__action-card"
      style={{ '--action-color': config.color, '--action-bg': config.bg, '--action-border': config.border }}
    >
      <span className="mac__action-icon" style={{ color: config.color }}>
        {config.icon}
      </span>
      <div className="mac__action-body">
        <p className="mac__action-label">{config.label}</p>
        {action.recipient && (
          <p className="mac__action-detail">To: {action.recipient}</p>
        )}
        {action.preview && (
          <p className="mac__action-detail mac__action-detail--preview">
            "{action.preview}"
          </p>
        )}
        {action.title && (
          <p className="mac__action-detail">{action.title}</p>
        )}
        {action.due_date && (
          <p className="mac__action-detail">Due: {action.due_date}</p>
        )}
        {action.time && (
          <p className="mac__action-detail">{action.time}</p>
        )}
        {action.contact && (
          <p className="mac__action-detail">With: {action.contact}</p>
        )}
      </div>
      {route && (
        <button
          className="mac__action-view"
          style={{ color: config.color }}
          onClick={() => onNavigate(route)}
        >
          View
        </button>
      )}
    </div>
  );
}

function SuggestionChips({ suggestions, onSelect }) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div className="mac__suggestions">
      {suggestions.map((s, i) => (
        <button
          key={i}
          className="mac__suggestion-chip"
          onClick={() => onSelect(s)}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

// ── Feedback helpers ─────────────────────────────────────────────────────────

function loadFeedbackState() {
  try {
    const stored = localStorage.getItem(FEEDBACK_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch (_) {
    return {};
  }
}

function saveFeedbackState(state) {
  try {
    localStorage.setItem(FEEDBACK_KEY, JSON.stringify(state));
  } catch (_) {
    // Storage quota exceeded — no-op
  }
}

// Inline SVG thumbs icons (small, 14x14)
function ThumbUpIcon({ filled }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" />
      <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
    </svg>
  );
}

function ThumbDownIcon({ filled }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z" />
      <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
    </svg>
  );
}

function MessageFeedback({ messageId, sessionId, feedbackState, onFeedback }) {
  const [showInput, setShowInput] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const currentRating = feedbackState[messageId] || null;

  const handleThumbClick = async (rating) => {
    if (submitting) return;

    // If already rated with the same rating, ignore
    if (currentRating === rating) return;

    // If thumbs down, show text input before submitting
    if (rating === 'negative' && !showInput) {
      // Immediately record the rating visually
      onFeedback(messageId, 'negative');
      setShowInput(true);
      triggerHaptic('light');
      return;
    }

    setSubmitting(true);
    onFeedback(messageId, rating);
    triggerHaptic('light');

    // Fire and forget — don't block UI on API response
    submitMessageFeedback(sessionId, messageId, rating, '').catch(() => {});
    setSubmitting(false);
  };

  const handleNegativeFeedbackSubmit = async () => {
    if (submitting) return;
    setSubmitting(true);

    submitMessageFeedback(sessionId, messageId, 'negative', feedbackText.trim()).catch(() => {});

    setShowInput(false);
    setFeedbackText('');
    setSubmitting(false);
    triggerHaptic('light');
  };

  const handleDismissInput = () => {
    // Already saved as negative, just close the input
    setShowInput(false);
    setFeedbackText('');
    // Still submit the negative feedback without text
    submitMessageFeedback(sessionId, messageId, 'negative', '').catch(() => {});
  };

  return (
    <div className="mac__feedback">
      <div className="mac__feedback-buttons">
        <button
          className={`mac__feedback-btn ${currentRating === 'positive' ? 'mac__feedback-btn--active-positive' : ''} ${currentRating && currentRating !== 'positive' ? 'mac__feedback-btn--muted' : ''}`}
          onClick={() => handleThumbClick('positive')}
          disabled={submitting}
          aria-label="Good response"
          type="button"
        >
          <ThumbUpIcon filled={currentRating === 'positive'} />
        </button>
        <button
          className={`mac__feedback-btn ${currentRating === 'negative' ? 'mac__feedback-btn--active-negative' : ''} ${currentRating && currentRating !== 'negative' ? 'mac__feedback-btn--muted' : ''}`}
          onClick={() => handleThumbClick('negative')}
          disabled={submitting}
          aria-label="Bad response"
          type="button"
        >
          <ThumbDownIcon filled={currentRating === 'negative'} />
        </button>
      </div>
      {showInput && (
        <div className="mac__feedback-input-wrap">
          <input
            className="mac__feedback-input"
            type="text"
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value.slice(0, 200))}
            placeholder="What went wrong? (optional)"
            maxLength={200}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleNegativeFeedbackSubmit();
              }
            }}
          />
          <button
            className="mac__feedback-submit"
            onClick={handleNegativeFeedbackSubmit}
            disabled={submitting}
            type="button"
          >
            Send
          </button>
          <button
            className="mac__feedback-dismiss"
            onClick={handleDismissInput}
            type="button"
            aria-label="Skip feedback"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  );
}

// Message bubble with parent-wired handlers
function MessageBubbleWithHandlers({ msg, onNavigate, onRetry, onSuggestionSelect, sessionId, feedbackState, onFeedback }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`mac__message ${isUser ? 'mac__message--user' : 'mac__message--aria'}`}>
      {!isUser && (
        <div className="mac__avatar" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
            <path d="M12 2C6.477 2 2 6.477 2 12c0 1.89.525 3.66 1.438 5.168L2 22l4.832-1.438A9.953 9.953 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2zm0 18a8 8 0 110-16 8 8 0 010 16zm-1-13h2v6h-2zm0 8h2v2h-2z" />
          </svg>
        </div>
      )}

      <div className="mac__bubble-group">
        <div className={`mac__bubble ${isUser ? 'mac__bubble--user' : 'mac__bubble--aria'} ${msg.isError ? 'mac__bubble--error' : ''}`}>
          {msg.text && <p className="mac__bubble-text">{msg.text}</p>}

          {msg.actions && msg.actions.length > 0 && (
            <div className="mac__action-cards">
              {msg.actions.map((action, i) => (
                <ActionCard key={i} action={action} onNavigate={onNavigate} />
              ))}
            </div>
          )}

          {msg.isError && onRetry && (
            <button className="mac__retry-btn" onClick={() => onRetry(msg.id)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Retry
            </button>
          )}
        </div>

        {!isUser && msg.suggestions && msg.suggestions.length > 0 && (
          <SuggestionChips suggestions={msg.suggestions} onSelect={onSuggestionSelect} />
        )}

        <time className="mac__timestamp" dateTime={msg.timestamp}>
          {formatTime(msg.timestamp)}
        </time>

        {/* Feedback buttons for non-error AI messages */}
        {!isUser && !msg.isError && sessionId && (
          <MessageFeedback
            messageId={msg.id}
            sessionId={sessionId}
            feedbackState={feedbackState}
            onFeedback={onFeedback}
          />
        )}
      </div>
    </div>
  );
}

// Skeleton placeholders shown on initial load
function SkeletonMessages() {
  return (
    <div className="mac__skeleton-list" aria-hidden="true">
      <div className="mac__skeleton mac__skeleton--aria">
        <div className="mac__skeleton-avatar" />
        <div className="mac__skeleton-bubble">
          <div className="mac__skeleton-line mac__skeleton-line--long" />
          <div className="mac__skeleton-line mac__skeleton-line--medium" />
        </div>
      </div>
      <div className="mac__skeleton mac__skeleton--user">
        <div className="mac__skeleton-bubble mac__skeleton-bubble--right">
          <div className="mac__skeleton-line mac__skeleton-line--short" />
        </div>
      </div>
      <div className="mac__skeleton mac__skeleton--aria">
        <div className="mac__skeleton-avatar" />
        <div className="mac__skeleton-bubble">
          <div className="mac__skeleton-line mac__skeleton-line--long" />
          <div className="mac__skeleton-line mac__skeleton-line--medium" />
          <div className="mac__skeleton-line mac__skeleton-line--short" />
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MobileAriaChat() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Route context
  const contextLeadId = searchParams.get('leadId') || null;
  const contextLeadName = searchParams.get('leadName') || null;
  const contextLoanId = searchParams.get('loanId') || null;
  const contextType = searchParams.get('context') || null;

  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [initialLoad, setInitialLoad] = useState(true);

  // Feedback state — keyed by message ID, value is "positive" or "negative"
  const [feedbackState, setFeedbackState] = useState(() => loadFeedbackState());

  // Workflow context for the linked entity
  const [workflowContext, setWorkflowContext] = useState(null);

  // Refs
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const retryPayloadRef = useRef(null); // store last message for retry

  // Voice input via useAriaVoice hook
  const { isRecording, isSupported: voiceSupported, startRecording, stopRecording } = useAriaVoice({
    onFinalTranscript: (text) => {
      if (text) sendMessageToAria(text);
    },
  });

  // ── Session & persistence ──────────────────────────────────────────────────

  useEffect(() => {
    // Restore session from localStorage
    try {
      const savedSession = localStorage.getItem(SESSION_KEY);
      const savedMessages = localStorage.getItem(MESSAGES_KEY);

      if (savedSession) {
        setSessionId(savedSession);
      } else {
        const newSession = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        setSessionId(newSession);
        localStorage.setItem(SESSION_KEY, newSession);
      }

      if (savedMessages) {
        const parsed = JSON.parse(savedMessages);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      }
    } catch (_) {
      // localStorage unavailable — fresh session
      const newSession = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
      setSessionId(newSession);
    }

    // Brief delay so skeleton renders, then clear initial load
    const t = setTimeout(() => setInitialLoad(false), 400);
    return () => clearTimeout(t);
  }, []);

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length === 0) return;
    try {
      const trimmed = messages.slice(-MAX_STORED_MESSAGES);
      localStorage.setItem(MESSAGES_KEY, JSON.stringify(trimmed));
    } catch (_) {
      // Storage quota exceeded — no-op
    }
  }, [messages]);

  // Fetch workflow context for the linked entity (best effort)
  useEffect(() => {
    const controller = new AbortController();

    async function fetchWorkflowContext() {
      try {
        const entityParam = contextLeadId
          ? `lead_id=${contextLeadId}`
          : contextLoanId
          ? `loan_id=${contextLoanId}`
          : null;
        if (!entityParam) return;

        const res = await api.get(`/api/v1/workflow/tasks?${entityParam}&status=pending&limit=10`, {
          signal: controller.signal,
        });
        const tasks = res.data?.tasks || res.data || [];
        if (Array.isArray(tasks) && tasks.length > 0) {
          setWorkflowContext({
            pending_workflow_tasks: tasks.length,
            task_types: [...new Set(tasks.map(t => t.task_type).filter(Boolean))],
            has_escalated: tasks.some(t => (t.escalation_level || 0) > 0),
            summary: tasks.map(t => `${t.task_name || t.title || t.task_type} (${t.status})`).slice(0, 5),
          });
        }
      } catch (err) {
        if (err.name === 'AbortError' || err.name === 'CanceledError') return;
        console.warn('[MobileAriaChat] Workflow context fetch failed:', err?.message || err);
      }
    }
    fetchWorkflowContext();

    return () => controller.abort();
  }, [contextLeadId, contextLoanId]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  // ── API calls ──────────────────────────────────────────────────────────────

  const sendMessageToAria = useCallback(async (text, retryMsgId = null) => {
    if (!text || !text.trim() || isLoading) return;

    const trimmedText = text.trim();

    // Add user message
    const userMsg = {
      id: newId(),
      role: 'user',
      text: trimmedText,
      timestamp: new Date().toISOString(),
      actions: [],
      suggestions: [],
    };

    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);

    // Haptic on send
    triggerHaptic('light');

    // Store payload for retry
    retryPayloadRef.current = trimmedText;

    try {
      let responseData;

      // If we have lead context, use autonomous-task endpoint for richer integration
      if (contextLeadId && (
        trimmedText.toLowerCase().includes('sms') ||
        trimmedText.toLowerCase().includes('task') ||
        trimmedText.toLowerCase().includes('call') ||
        trimmedText.toLowerCase().includes('email')
      )) {
        responseData = await executeTask(trimmedText, {
          lead_id: contextLeadId,
          lead_name: contextLeadName,
          context: contextType,
          ...(workflowContext && { workflow_context: workflowContext }),
        });
      } else {
        // Standard orchestrator chat
        responseData = await sendAriaMessage(trimmedText, sessionId, {
          ...(contextLeadId || contextLoanId ? {
            context: {
              ...(contextLeadId && { lead_id: contextLeadId }),
              ...(contextLeadName && { lead_name: contextLeadName }),
              ...(contextLoanId && { loan_id: contextLoanId }),
              context_type: contextType,
              ...(workflowContext && { workflow_context: workflowContext }),
            },
          } : {}),
        });

        // Persist session_id if returned
        if (responseData.session_id && responseData.session_id !== sessionId) {
          setSessionId(responseData.session_id);
          try {
            localStorage.setItem(SESSION_KEY, responseData.session_id);
          } catch (_) {}
        }
      }

      // Check if the service layer returned an error
      if (responseData.success === false && responseData.error) {
        throw new Error(responseData.error);
      }

      // Build Aria message
      const ariaMsg = {
        id: newId(),
        role: 'aria',
        text: responseData.response || responseData.message || responseData.result || 'Done.',
        timestamp: new Date().toISOString(),
        actions: normalizeActions(responseData),
        suggestions: responseData.follow_up_suggestions || [],
        intent: responseData.intent,
        confidence: responseData.confidence,
      };

      setMessages(prev => {
        // If this was a retry, replace the error message
        if (retryMsgId) {
          return prev.map(m =>
            m.id === retryMsgId ? { ...ariaMsg, id: m.id } : m
          );
        }
        return [...prev, ariaMsg];
      });

      // Haptic on success if actions executed
      if (ariaMsg.actions && ariaMsg.actions.length > 0) {
        triggerHaptic('success');
      }

      auditLog(AUDIT_EVENTS.PII_ACCESSED, { action: 'aria_chat_message', intent: ariaMsg.intent });
    } catch (err) {
      const errText = err.message || 'Something went wrong. Please try again.';

      const errMsg = {
        id: newId(),
        role: 'aria',
        text: errText,
        timestamp: new Date().toISOString(),
        actions: [],
        suggestions: [],
        isError: true,
      };

      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, sessionId, contextLeadId, contextLeadName, contextLoanId, contextType, workflowContext]);

  // Normalize the actions from different response shapes
  function normalizeActions(data) {
    const executed = data.actions_executed || [];
    const pending = data.actions_pending || [];
    const all = [...executed, ...pending];

    // Some endpoints return a flat action object instead of an array
    if (data.action) all.push(data.action);

    return all.map(a => {
      if (typeof a === 'string') return { type: a, label: a };
      return a;
    });
  }

  // ── Retry ──────────────────────────────────────────────────────────────────

  const handleRetry = useCallback((errorMsgId) => {
    if (!retryPayloadRef.current) return;
    // Remove the error message and resend
    setMessages(prev => prev.filter(m => m.id !== errorMsgId));
    sendMessageToAria(retryPayloadRef.current);
  }, [sendMessageToAria]);

  // ── Input handlers ─────────────────────────────────────────────────────────

  const handleSend = useCallback(() => {
    sendMessageToAria(inputText);
  }, [inputText, sendMessageToAria]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleSuggestionSelect = useCallback((suggestion) => {
    sendMessageToAria(suggestion);
  }, [sendMessageToAria]);

  const handleQuickCommand = useCallback((cmd) => {
    setInputText(cmd.text);
    inputRef.current?.focus();
  }, []);

  // ── Clear chat ─────────────────────────────────────────────────────────────

  const handleClearChat = useCallback(() => {
    setMessages([]);
    setFeedbackState({});
    const newSession = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    setSessionId(newSession);
    try {
      localStorage.setItem(SESSION_KEY, newSession);
      localStorage.removeItem(MESSAGES_KEY);
      localStorage.removeItem(FEEDBACK_KEY);
    } catch (_) {}
    triggerHaptic('light');
  }, []);

  // ── Feedback handler ──────────────────────────────────────────────────────

  const handleFeedback = useCallback((messageId, rating) => {
    setFeedbackState(prev => {
      const next = { ...prev, [messageId]: rating };
      saveFeedbackState(next);
      return next;
    });
  }, []);

  // ── Voice input ────────────────────────────────────────────────────────────

  const handleMicToggle = useCallback(() => {
    if (!voiceSupported) {
      toast.info('Voice input is not available on this device.');
      return;
    }
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
      triggerHaptic('light');
    }
  }, [voiceSupported, isRecording, startRecording, stopRecording]);

  // ── Navigation helper ──────────────────────────────────────────────────────

  const handleActionNavigate = useCallback((route) => {
    navigate(route);
  }, [navigate]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const isEmpty = messages.length === 0;
  const showQuickCommands = isEmpty && !isLoading;

  return (
    <>
    <div className="mac">
      {/* ── Header ── */}
      <header className="mac__header">
        <button
          className="mac__header-btn mac__back-btn"
          onClick={() => navigate(-1)}
          aria-label="Go back"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <div className="mac__header-center">
          <div className="mac__aria-indicator" aria-hidden="true" />
          <div>
            <h1 className="mac__header-title">Aria</h1>
            {contextLeadName && (
              <p className="mac__header-context">Chatting about {contextLeadName}</p>
            )}
          </div>
        </div>

        <button
          className="mac__header-btn mac__clear-btn"
          onClick={handleClearChat}
          aria-label="Clear conversation"
          disabled={isEmpty}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      </header>

      {/* ── Workflow context banner ── */}
      {workflowContext && workflowContext.pending_workflow_tasks > 0 && (
        <div
          className="mac__workflow-banner"
          style={{
            padding: '6px 16px',
            background: '#fef3c7',
            fontSize: 12,
            color: '#92400e',
            borderBottom: '1px solid #fde68a',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>
            {workflowContext.pending_workflow_tasks} pending workflow task{workflowContext.pending_workflow_tasks > 1 ? 's' : ''}
            {workflowContext.has_escalated && ' (escalated)'}
          </span>
        </div>
      )}

      {/* ── Messages area ── */}
      <main className="mac__messages" role="log" aria-live="polite" aria-label="Conversation with Aria">
        {initialLoad ? (
          <SkeletonMessages />
        ) : (
          <>
            {/* Welcome / empty state */}
            {isEmpty && (
              <div className="mac__empty-state">
                <div className="mac__empty-icon" aria-hidden="true">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </div>
                <h2 className="mac__empty-title">Hi, I'm Aria</h2>
                <p className="mac__empty-subtitle">
                  {contextLeadName
                    ? `Ask me anything about ${contextLeadName}, or tell me what to do.`
                    : 'Your AI assistant for everything mortgage. What can I help you with?'}
                </p>
              </div>
            )}

            {/* Message list */}
            {messages.map((msg) => (
              <MessageBubbleWithHandlers
                key={msg.id}
                msg={msg}
                onNavigate={handleActionNavigate}
                onRetry={handleRetry}
                onSuggestionSelect={handleSuggestionSelect}
                sessionId={sessionId}
                feedbackState={feedbackState}
                onFeedback={handleFeedback}
              />
            ))}

            {/* Typing indicator */}
            {isLoading && <TypingIndicator />}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </>
        )}
      </main>

      {/* ── Quick commands (shown when empty) ── */}
      {showQuickCommands && (
        <div className="mac__quick-commands" aria-label="Quick commands">
          <div className="mac__quick-commands-scroll">
            {QUICK_COMMANDS.map((cmd) => (
              <button
                key={cmd.label}
                className="mac__quick-chip"
                onClick={() => handleQuickCommand(cmd)}
              >
                {cmd.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Input area ── */}
      <div className="mac__input-area">
        <div className="mac__input-row">
          <input
            ref={inputRef}
            className="mac__input"
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isLoading ? 'Aria is thinking…' : 'Message Aria…'}
            disabled={isLoading}
            autoComplete="off"
            autoCorrect="on"
            autoCapitalize="sentences"
            spellCheck="true"
            aria-label="Message input"
            maxLength={2000}
          />

          {/* Mic button */}
          <button
            className={`mac__mic-btn ${isRecording ? 'mac__mic-btn--recording' : ''}`}
            onClick={handleMicToggle}
            aria-label={isRecording ? 'Stop recording' : 'Start voice input'}
            aria-pressed={isRecording}
            type="button"
          >
            {isRecording ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </button>

          {/* Send button */}
          <button
            className="mac__send-btn"
            onClick={handleSend}
            disabled={!inputText.trim() || isLoading}
            aria-label="Send message"
            type="button"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
    <MobileBottomNav />
    </>
  );
}
