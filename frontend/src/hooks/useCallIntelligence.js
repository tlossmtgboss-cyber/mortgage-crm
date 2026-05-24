// ─────────────────────────────────────────────────────────────
// CALL INTELLIGENCE WEBSOCKET HOOK
// src/hooks/useCallIntelligence.js
//
// Connects to the LangGraph agent WebSocket and dispatches
// each agent's events into a unified state object.
// ─────────────────────────────────────────────────────────────

import { useEffect, useRef, useCallback, useReducer, useState } from 'react';

// ── Initial State (inlined from types) ───────────────────────
export const INITIAL_STATE = {
  session: null,
  note_taker: {
    lines: [],
    word_count: 0,
    key_topics: [],
    summary_draft: '',
  },
  jr_loan_officer: {
    application_id: null,
    fields: {
      borrower_name: null, borrower_email: null, borrower_phone: null,
      borrower_dob: null, marital_status: null, dependents: null,
      employer_name: null, employment_type: null, annual_income: null,
      years_employed: null, loan_type: null, loan_purpose: null,
      purchase_price: null, down_payment_amount: null, down_payment_percent: null,
      property_type: null, property_use: null, estimated_credit_score: null,
      monthly_debt: null, bankruptcy_history: null, target_close_date: null,
      pre_approval_needed: null,
    },
    completion_percent: 0,
    fields_filled: 0,
    fields_total: 22,
    last_field_updated: null,
    last_updated_at: null,
  },
  auditor: {
    flags: [],
    document_requests: [],
    tasks_created: [],
    action_count: 0,
  },
  receptionist: {
    appointments: [],
    last_action: null,
    emails_sent: 0,
    calendar_events_created: 0,
  },
  is_connected: false,
  error: null,
};

// ── Reducer ───────────────────────────────────────────────────
function reducer(state, action) {
  switch (action.type) {
    case 'SET_SESSION':
      return { ...state, session: action.payload };
    case 'SET_CONNECTED':
      return { ...state, is_connected: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };

    // ── NOTE TAKER ────────────────────────────────────────────
    case 'NOTE_TAKER_TRANSCRIPT': {
      const line = action.payload;
      const lines = [...state.note_taker.lines];
      // If partial line already exists, replace it; else append
      const existingIdx = lines.findIndex((l) => l.id === line.id);
      if (existingIdx >= 0) {
        lines[existingIdx] = line;
      } else {
        lines.push(line);
      }
      const wordCount = lines
        .filter((l) => l.is_final)
        .reduce((acc, l) => acc + l.text.split(' ').length, 0);
      return {
        ...state,
        note_taker: { ...state.note_taker, lines, word_count: wordCount },
      };
    }
    case 'NOTE_TAKER_TOPICS':
      return { ...state, note_taker: { ...state.note_taker, key_topics: action.payload } };
    case 'NOTE_TAKER_SUMMARY':
      return { ...state, note_taker: { ...state.note_taker, summary_draft: action.payload } };

    // ── JR. LOAN OFFICER ──────────────────────────────────────
    case 'JRLO_FIELD_UPDATE': {
      const { completion_percent, fields_filled, last_field_updated, ...fieldUpdates } = action.payload;
      return {
        ...state,
        jr_loan_officer: {
          ...state.jr_loan_officer,
          fields: { ...state.jr_loan_officer.fields, ...fieldUpdates },
          completion_percent,
          fields_filled,
          last_field_updated,
          last_updated_at: new Date().toISOString(),
        },
      };
    }
    case 'JRLO_APPLICATION_CREATED':
      return {
        ...state,
        jr_loan_officer: { ...state.jr_loan_officer, application_id: action.payload },
      };

    // ── AUDITOR ───────────────────────────────────────────────
    case 'AUDITOR_FLAG':
      return {
        ...state,
        auditor: {
          ...state.auditor,
          flags: [...state.auditor.flags, action.payload],
          action_count: state.auditor.action_count + 1,
        },
      };
    case 'AUDITOR_DOCUMENT_REQUEST':
      return {
        ...state,
        auditor: {
          ...state.auditor,
          document_requests: [...state.auditor.document_requests, action.payload],
          action_count: state.auditor.action_count + 1,
        },
      };
    case 'AUDITOR_TASK':
      return {
        ...state,
        auditor: {
          ...state.auditor,
          tasks_created: [...state.auditor.tasks_created, action.payload],
          action_count: state.auditor.action_count + 1,
        },
      };

    // ── RECEPTIONIST ──────────────────────────────────────────
    case 'RECEPTIONIST_APPOINTMENT':
      return {
        ...state,
        receptionist: {
          ...state.receptionist,
          appointments: [...state.receptionist.appointments, action.payload],
          calendar_events_created: state.receptionist.calendar_events_created + 1,
          emails_sent: state.receptionist.emails_sent + (action.payload.borrower_invite_sent ? 1 : 0),
        },
      };
    case 'RECEPTIONIST_ACTION':
      return {
        ...state,
        receptionist: { ...state.receptionist, last_action: action.payload },
      };

    case 'RESET':
      return INITIAL_STATE;

    default:
      return state;
  }
}

// ── Connection status ────────────────────────────────────────
export const CONNECTION_STATUS = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
  DISCONNECTED: 'disconnected',
};

const PING_INTERVAL_MS = 30000;
const PONG_TIMEOUT_MS = 10000;
const MAX_BACKOFF_MS = 30000;
const MAX_FAILURES_BEFORE_WARNING = 3;

// ── Hook ──────────────────────────────────────────────────────
export function useCallIntelligence(wsUrl) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const [connectionStatus, setConnectionStatus] = useState(CONNECTION_STATUS.IDLE);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const pingTimer = useRef(null);
  const pongTimer = useRef(null);
  const shouldReconnect = useRef(true);
  const attemptCount = useRef(0);

  const clearAllTimers = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    if (pingTimer.current) clearInterval(pingTimer.current);
    if (pongTimer.current) clearTimeout(pongTimer.current);
  }, []);

  const startPingPong = useCallback(() => {
    clearTimeout(pongTimer.current);
    clearInterval(pingTimer.current);

    pingTimer.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ type: 'ping' }));
        } catch { /* send failed, onclose will fire */ }

        pongTimer.current = setTimeout(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.close();
          }
        }, PONG_TIMEOUT_MS);
      }
    }, PING_INTERVAL_MS);
  }, []);

  const connect = useCallback(() => {
    if (!wsUrl) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

    setConnectionStatus(
      attemptCount.current > 0 ? CONNECTION_STATUS.RECONNECTING : CONNECTION_STATUS.CONNECTING
    );

    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      attemptCount.current = 0;
      dispatch({ type: 'SET_CONNECTED', payload: true });
      dispatch({ type: 'SET_ERROR', payload: null });
      setConnectionStatus(CONNECTION_STATUS.CONNECTED);
      startPingPong();
    };

    wsRef.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'pong') {
          clearTimeout(pongTimer.current);
          return;
        }
        handleAgentMessage(msg, dispatch);
      } catch {
        console.warn('[CallIntelligence] Malformed WS message', event.data);
      }
    };

    wsRef.current.onerror = () => {
      dispatch({ type: 'SET_ERROR', payload: 'Connection error — retrying...' });
    };

    wsRef.current.onclose = () => {
      dispatch({ type: 'SET_CONNECTED', payload: false });
      clearInterval(pingTimer.current);
      clearTimeout(pongTimer.current);

      if (shouldReconnect.current && wsUrl) {
        attemptCount.current += 1;
        const delay = Math.min(1000 * Math.pow(2, attemptCount.current - 1), MAX_BACKOFF_MS);

        if (attemptCount.current >= MAX_FAILURES_BEFORE_WARNING) {
          dispatch({ type: 'SET_ERROR', payload: 'Connection unstable — check your network' });
        }

        setConnectionStatus(CONNECTION_STATUS.RECONNECTING);
        reconnectTimer.current = setTimeout(connect, delay);
      } else {
        setConnectionStatus(CONNECTION_STATUS.DISCONNECTED);
      }
    };
  }, [wsUrl, startPingPong]);

  useEffect(() => {
    if (!wsUrl) return;
    shouldReconnect.current = true;
    attemptCount.current = 0;
    connect();

    return () => {
      // Do NOT close on screen unmount — agents keep working in background
    };
  }, [wsUrl, connect]);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    clearAllTimers();
    wsRef.current?.close();
    wsRef.current = null;
    dispatch({ type: 'SET_CONNECTED', payload: false });
    setConnectionStatus(CONNECTION_STATUS.DISCONNECTED);
  }, [clearAllTimers]);

  const reset = useCallback(() => {
    disconnect();
    dispatch({ type: 'RESET' });
    setConnectionStatus(CONNECTION_STATUS.IDLE);
  }, [disconnect]);

  return { state, disconnect, reset, connectionStatus };
}

// ── Agent message router ──────────────────────────────────────
function handleAgentMessage(msg, dispatch) {
  switch (msg.agent) {
    case 'note_taker':
      handleNoteTaker(msg, dispatch);
      break;
    case 'jr_loan_officer':
      handleJrLoanOfficer(msg, dispatch);
      break;
    case 'auditor':
      handleAuditor(msg, dispatch);
      break;
    case 'receptionist':
      handleReceptionist(msg, dispatch);
      break;
    default:
      break;
  }
}

function handleNoteTaker(msg, dispatch) {
  switch (msg.event) {
    case 'transcript_line':
      dispatch({ type: 'NOTE_TAKER_TRANSCRIPT', payload: msg.payload });
      break;
    case 'topics_updated':
      dispatch({ type: 'NOTE_TAKER_TOPICS', payload: msg.payload.topics });
      break;
    case 'summary_updated':
      dispatch({ type: 'NOTE_TAKER_SUMMARY', payload: msg.payload.summary });
      break;
    default:
      break;
  }
}

function handleJrLoanOfficer(msg, dispatch) {
  switch (msg.event) {
    case 'field_extracted':
      dispatch({ type: 'JRLO_FIELD_UPDATE', payload: msg.payload });
      break;
    case 'application_created':
      dispatch({ type: 'JRLO_APPLICATION_CREATED', payload: msg.payload.application_id });
      break;
    default:
      break;
  }
}

function handleAuditor(msg, dispatch) {
  switch (msg.event) {
    case 'flag_raised':
      dispatch({ type: 'AUDITOR_FLAG', payload: msg.payload });
      break;
    case 'document_request_sent':
      dispatch({ type: 'AUDITOR_DOCUMENT_REQUEST', payload: msg.payload });
      break;
    case 'task_created':
      dispatch({ type: 'AUDITOR_TASK', payload: msg.payload });
      break;
    default:
      break;
  }
}

function handleReceptionist(msg, dispatch) {
  switch (msg.event) {
    case 'appointment_scheduled':
      dispatch({ type: 'RECEPTIONIST_APPOINTMENT', payload: msg.payload });
      break;
    case 'action_taken':
      dispatch({ type: 'RECEPTIONIST_ACTION', payload: msg.payload.description });
      break;
    default:
      break;
  }
}
