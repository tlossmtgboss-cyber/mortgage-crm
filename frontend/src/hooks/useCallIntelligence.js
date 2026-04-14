// ─────────────────────────────────────────────────────────────
// CALL INTELLIGENCE WEBSOCKET HOOK
// src/hooks/useCallIntelligence.js
//
// Connects to the LangGraph agent WebSocket and dispatches
// each agent's events into a unified state object.
// ─────────────────────────────────────────────────────────────

import { useEffect, useRef, useCallback, useReducer } from 'react';

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

// ── Hook ──────────────────────────────────────────────────────
export function useCallIntelligence(wsUrl) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const shouldReconnect = useRef(true);

  const connect = useCallback(() => {
    if (!wsUrl || wsRef.current?.readyState === WebSocket.OPEN) return;

    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      dispatch({ type: 'SET_CONNECTED', payload: true });
      dispatch({ type: 'SET_ERROR', payload: null });
    };

    wsRef.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleAgentMessage(msg, dispatch);
      } catch {
        console.warn('[CallIntelligence] Malformed WS message', event.data);
      }
    };

    wsRef.current.onerror = () => {
      dispatch({ type: 'SET_ERROR', payload: 'Connection error \u2014 retrying\u2026' });
    };

    wsRef.current.onclose = () => {
      dispatch({ type: 'SET_CONNECTED', payload: false });
      // Auto-reconnect after 3s if call is still active
      if (shouldReconnect.current && wsUrl) {
        reconnectTimer.current = setTimeout(connect, 3000);
      }
    };
  }, [wsUrl]);

  useEffect(() => {
    if (!wsUrl) return;
    shouldReconnect.current = true;
    connect();

    return () => {
      // Do NOT close on screen unmount — agents keep working in background
    };
  }, [wsUrl, connect]);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
    wsRef.current = null;
    dispatch({ type: 'SET_CONNECTED', payload: false });
  }, []);

  const reset = useCallback(() => {
    disconnect();
    dispatch({ type: 'RESET' });
  }, [disconnect]);

  return { state, disconnect, reset };
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
