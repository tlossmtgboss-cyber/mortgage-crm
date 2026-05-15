/**
 * PERENNIA AI — useCallIntelligenceSession (v3 — Enterprise Audit)
 *
 * Full lifecycle: idle → requesting → playing_disclosure → active → completed
 *
 * v3 fixes:
 *   - WebSocket reconnect attaches event handlers
 *   - Stale sessionState in onclose fixed via ref
 *   - Event IDs use monotonic counter
 *   - wsConnected state for UI feedback
 *   - Callbacks stored in refs to avoid stale closures
 *   - Agent event maps backend payload (status/field_count) correctly
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export const SESSION_STATES = {
  IDLE: 'idle',
  REQUESTING_CONSENT: 'requesting_consent',
  PLAYING_DISCLOSURE: 'playing_disclosure',
  CONSENT_FAILED: 'consent_failed',
  ACTIVE: 'active',
  COMPLETED: 'completed',
  ERROR: 'error',
};

export const CONSENT_STATUSES = {
  PENDING: 'pending',
  PLAYING: 'playing',
  DISCLOSED: 'disclosed',
  SKIPPED: 'skipped',
  FAILED: 'failed',
  BROWSER_PENDING: 'browser_pending',
};

export const AGENT_CONFIG = {
  transcription: { label: 'Transcription', icon: '\u{1F4DD}', color: '#7EB8F7' },
  identity:      { label: 'Identity',      icon: '\u{1F464}', color: '#60A5FA' },
  property:      { label: 'Property',      icon: '\u{1F3E0}', color: '#34D399' },
  financial:     { label: 'Financial',     icon: '\u{1F4B0}', color: '#FBBF24' },
  employment:    { label: 'Employment',    icon: '\u{1F4BC}', color: '#D4AD6A' },
  compliance:    { label: 'Compliance',    icon: '⚖️', color: '#F87171' },
  intent:        { label: 'Intent',        icon: '\u{1F3AF}', color: '#FB923C' },
};

export function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function getArtifactIcon(type) {
  const icons = {
    note: '\u{1F4CB}', action_item: '✅', follow_up: '\u{1F4DE}',
    document_request: '\u{1F4C4}', qualification: '\u{1F3E6}', application: '\u{1F4DD}',
  };
  return icons[type] || '\u{1F4CE}';
}

let _eventCounter = 0;

export function useCallIntelligenceSession({
  callControlId,
  contactId,
  borrowerState,
  loanOfficerId,
  websocketUrl,
  onConsentCleared,
  onSessionActive,
  onError,
}) {
  const [sessionState, setSessionState] = useState(SESSION_STATES.IDLE);
  const [sessionId, setSessionId] = useState(null);
  const [consentInfo, setConsentInfo] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});
  const [agentEvents, setAgentEvents] = useState([]);
  const [duration, setDuration] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);

  const wsRef = useRef(null);
  const timeoutRef = useRef(null);
  const reconnectRef = useRef(null);
  const audioRef = useRef(null);
  const durationRef = useRef(null);
  const activeStartRef = useRef(null);
  const sessionStateRef = useRef(sessionState);
  const sessionIdRef = useRef(null);
  const callbacksRef = useRef({ onConsentCleared, onSessionActive, onError });

  sessionStateRef.current = sessionState;
  sessionIdRef.current = sessionId;
  callbacksRef.current = { onConsentCleared, onSessionActive, onError };

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      clearTimeout(timeoutRef.current);
      clearTimeout(reconnectRef.current);
      clearInterval(durationRef.current);
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (sessionState === SESSION_STATES.ACTIVE) {
      activeStartRef.current = Date.now();
      setDuration(0);
      durationRef.current = setInterval(() => {
        setDuration(Math.floor((Date.now() - activeStartRef.current) / 1000));
      }, 1000);
    } else {
      clearInterval(durationRef.current);
    }
    return () => clearInterval(durationRef.current);
  }, [sessionState]);

  const _attachWsHandlers = useCallback((ws, sessId) => {
    ws.onopen = () => setWsConnected(true);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.event) {
          case 'consent_cleared':
            clearTimeout(timeoutRef.current);
            setSessionState(SESSION_STATES.ACTIVE);
            setConsentInfo((prev) => ({
              ...prev,
              status: CONSENT_STATUSES.DISCLOSED,
              manualOverride: data.manual_override || false,
            }));
            callbacksRef.current.onConsentCleared?.();
            callbacksRef.current.onSessionActive?.(sessionIdRef.current);
            break;

          case 'agent_update':
          case 'agent_complete':
          case 'agent_error':
          case 'confidence_flag': {
            const agent = data.agent || data.agent_type || 'system';
            const config = AGENT_CONFIG[agent] || { label: agent, icon: '\u{1F50D}', color: '#94a3b8' };

            const derivedStatus = data.status === 'complete' ? 'agent_complete'
              : data.status === 'error' ? 'agent_error'
              : data.event;

            const message = data.message || data.field_name || data.detail
              || (data.field_count ? `${data.field_count} field(s) extracted` : '')
              || '';

            const eventEntry = {
              id: ++_eventCounter,
              agent,
              label: config.label,
              icon: config.icon,
              color: config.color,
              type: derivedStatus,
              message,
              value: data.value || data.extracted_value || null,
              confidence: data.confidence ?? null,
              fieldCount: data.field_count || 0,
              artifactCount: data.artifact_count || 0,
              timestamp: Date.now(),
            };
            setAgentEvents(prev => [...prev.slice(-100), eventEntry]);
            setAgentStatuses(prev => ({
              ...prev,
              [agent]: {
                status: derivedStatus === 'agent_complete' ? 'complete' :
                        derivedStatus === 'agent_error' ? 'error' : 'active',
                lastMessage: message,
                lastUpdate: Date.now(),
              },
            }));
            break;
          }

          case 'call_status':
            if (data.status === 'completed') {
              setSessionState(SESSION_STATES.COMPLETED);
            }
            break;

          default:
            break;
        }
      } catch (e) {
        console.error('WS message parse error:', e);
      }
    };

    ws.onerror = () => {
      console.error('CI WebSocket error');
      setWsConnected(false);
    };

    ws.onclose = () => {
      setWsConnected(false);
      const currentState = sessionStateRef.current;
      if (
        currentState === SESSION_STATES.ACTIVE ||
        currentState === SESSION_STATES.PLAYING_DISCLOSURE
      ) {
        reconnectRef.current = setTimeout(() => {
          if (wsRef.current?.readyState === WebSocket.CLOSED && sessId) {
            const reconnWs = new WebSocket(`${websocketUrl}/${sessId}/stream`);
            wsRef.current = reconnWs;
            _attachWsHandlers(reconnWs, sessId);
          }
        }, 2000);
      }
    };
  }, [websocketUrl]);

  useEffect(() => {
    if (!sessionId || sessionState === SESSION_STATES.IDLE) return;

    const ws = new WebSocket(`${websocketUrl}/${sessionId}/stream`);
    wsRef.current = ws;
    _attachWsHandlers(ws, sessionId);

    return () => ws.close();
  }, [sessionId, websocketUrl, _attachWsHandlers]);

  const _playBrowserDisclosure = useCallback(
    async (audioUrl, sessId) => {
      return new Promise((resolve, reject) => {
        const audio = new Audio(audioUrl);
        audioRef.current = audio;

        audio.onended = async () => {
          audioRef.current = null;
          try {
            const resp = await fetch(
              '/api/v1/call-intelligence/session/confirm-browser-disclosure',
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessId }),
              }
            );
            if (resp.ok) {
              resolve();
            } else {
              const err = await resp.json();
              reject(new Error(err.detail || 'Browser disclosure confirmation failed'));
            }
          } catch (e) {
            reject(e);
          }
        };

        audio.onerror = () => {
          audioRef.current = null;
          reject(new Error('Failed to play disclosure audio'));
        };

        audio.play().catch((e) => {
          audioRef.current = null;
          reject(new Error(`Audio play blocked: ${e.message}. Tap to allow audio.`));
        });
      });
    },
    []
  );

  const startSession = useCallback(async () => {
    setSessionState(SESSION_STATES.REQUESTING_CONSENT);
    setErrorMessage(null);
    setAgentEvents([]);
    setAgentStatuses({});

    try {
      const isBrowserMode = !callControlId;

      const response = await fetch('/api/v1/call-intelligence/session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          call_control_id: callControlId || null,
          contact_id: contactId || null,
          borrower_state: borrowerState || null,
          loan_officer_id: loanOfficerId || null,
          is_browser_mode: isBrowserMode,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to start session');
      }

      const data = await response.json();
      setSessionId(data.session_id);

      setConsentInfo({
        status: data.consent_status,
        requirement: data.consent_requirement,
        isFelonyState: data.is_felony_state,
        isBrowserMode: data.is_browser_mode,
        message: data.message,
      });

      if (data.consent_status === 'browser_pending' && data.disclosure_audio_url) {
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);

        try {
          await _playBrowserDisclosure(data.disclosure_audio_url, data.session_id);
          setSessionState(SESSION_STATES.ACTIVE);
          setConsentInfo((prev) => ({
            ...prev,
            status: CONSENT_STATUSES.DISCLOSED,
          }));
          callbacksRef.current.onConsentCleared?.();
          callbacksRef.current.onSessionActive?.(sessionIdRef.current);
        } catch (audioErr) {
          setSessionState(SESSION_STATES.CONSENT_FAILED);
          setErrorMessage(audioErr.message);
          setConsentInfo((prev) => ({
            ...prev,
            status: CONSENT_STATUSES.FAILED,
          }));
        }
        return;
      }

      if (data.awaiting_disclosure) {
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);

        timeoutRef.current = setTimeout(() => {
          setSessionState(SESSION_STATES.CONSENT_FAILED);
          setErrorMessage(
            data.consent_requirement === 'required'
              ? 'Disclosure timed out. Cannot proceed in two-party consent state.'
              : 'Disclosure timed out. You may proceed after verbal disclosure.'
          );
          setConsentInfo((prev) => ({
            ...prev,
            status: CONSENT_STATUSES.FAILED,
          }));
        }, 15000);

        return;
      }

      if (data.consent_status === 'failed') {
        setSessionState(SESSION_STATES.CONSENT_FAILED);
        setErrorMessage(data.message);
        return;
      }

      setSessionState(SESSION_STATES.ACTIVE);
      callbacksRef.current.onConsentCleared?.();
      callbacksRef.current.onSessionActive?.(sessionIdRef.current);

    } catch (err) {
      setSessionState(SESSION_STATES.ERROR);
      setErrorMessage(err.message);
      callbacksRef.current.onError?.(err);
    }
  }, [callControlId, contactId, borrowerState, loanOfficerId, _playBrowserDisclosure]);

  const retryDisclosure = useCallback(async () => {
    if (!sessionId) return;

    setSessionState(SESSION_STATES.REQUESTING_CONSENT);
    setErrorMessage(null);

    try {
      const response = await fetch('/api/v1/call-intelligence/session/retry-disclosure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          call_control_id: callControlId || null,
          is_browser_mode: !callControlId,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Retry failed');
      }

      const data = await response.json();

      if (data.consent_status === 'browser_pending' && data.disclosure_audio_url) {
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);
        try {
          await _playBrowserDisclosure(data.disclosure_audio_url, sessionId);
          setSessionState(SESSION_STATES.ACTIVE);
          setConsentInfo((prev) => ({ ...prev, status: CONSENT_STATUSES.DISCLOSED }));
          callbacksRef.current.onConsentCleared?.();
          callbacksRef.current.onSessionActive?.(sessionIdRef.current);
        } catch (audioErr) {
          setSessionState(SESSION_STATES.CONSENT_FAILED);
          setErrorMessage(audioErr.message);
        }
        return;
      }

      if (data.awaiting_disclosure) {
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);
        timeoutRef.current = setTimeout(() => {
          setSessionState(SESSION_STATES.CONSENT_FAILED);
          setErrorMessage('Retry timed out.');
        }, 15000);
      }
    } catch (err) {
      setSessionState(SESSION_STATES.CONSENT_FAILED);
      setErrorMessage(err.message);
    }
  }, [sessionId, callControlId, _playBrowserDisclosure]);

  const confirmVerbalDisclosure = useCallback(async () => {
    if (!sessionId) return;

    if (consentInfo?.isFelonyState || consentInfo?.requirement === 'required') {
      setErrorMessage('Manual override blocked in two-party consent states.');
      return;
    }

    try {
      const response = await fetch('/api/v1/call-intelligence/session/manual-consent-override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          lo_confirmed_verbal_disclosure: true,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Override failed');
      }

      setSessionState(SESSION_STATES.ACTIVE);
      setConsentInfo((prev) => ({
        ...prev,
        status: CONSENT_STATUSES.DISCLOSED,
        manualOverride: true,
      }));
      callbacksRef.current.onConsentCleared?.();
      callbacksRef.current.onSessionActive?.(sessionIdRef.current);
    } catch (err) {
      setErrorMessage(err.message);
    }
  }, [sessionId, consentInfo]);

  const stopSession = useCallback(async () => {
    if (sessionId) {
      await fetch(`/api/v1/call-intelligence/session/${sessionId}/stop`, {
        method: 'POST',
      }).catch(() => {});
    }
    sessionStateRef.current = SESSION_STATES.COMPLETED;
    setSessionState(SESSION_STATES.COMPLETED);
    wsRef.current?.close();
    clearTimeout(timeoutRef.current);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  }, [sessionId]);

  const sendTranscript = useCallback((text, isFinal = true) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'transcript',
        text,
        is_final: isFinal,
      }));
    }
  }, []);

  const sendAudio = useCallback((base64Data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'audio_chunk',
        data: base64Data,
      }));
    }
  }, []);

  return {
    sessionState,
    sessionId,
    consentInfo,
    errorMessage,
    agentStatuses,
    agentEvents,
    duration,
    wsConnected,

    isIdle: sessionState === SESSION_STATES.IDLE,
    isPlayingDisclosure: sessionState === SESSION_STATES.PLAYING_DISCLOSURE,
    isActive: sessionState === SESSION_STATES.ACTIVE,
    isConsentFailed: sessionState === SESSION_STATES.CONSENT_FAILED,
    isCompleted: sessionState === SESSION_STATES.COMPLETED,
    isError: sessionState === SESSION_STATES.ERROR,
    canManualOverride:
      sessionState === SESSION_STATES.CONSENT_FAILED &&
      consentInfo?.requirement !== 'required',
    canRetry: sessionState === SESSION_STATES.CONSENT_FAILED,

    startSession,
    stopSession,
    retryDisclosure,
    confirmVerbalDisclosure,
    sendTranscript,
    sendAudio,
  };
}
