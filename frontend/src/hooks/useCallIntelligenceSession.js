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
import api from '../services/api';

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
  const [disclosureAudioUrl, setDisclosureAudioUrl] = useState(null);
  const [disclosureText, setDisclosureText] = useState(null);
  const [consentInfo, setConsentInfo] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});
  const [agentEvents, setAgentEvents] = useState([]);
  const [transcript, setTranscript] = useState([]);
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
  // Audio queued while the WS is CONNECTING (~5s worth), flushed on open.
  const pendingAudioRef = useRef([]);
  const droppedChunksRef = useRef(0);

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
      if (typeof window.speechSynthesis !== 'undefined') {
        window.speechSynthesis.cancel();
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
    ws.onopen = () => {
      setWsConnected(true);
      const queued = pendingAudioRef.current.splice(0);
      for (const data of queued) {
        ws.send(JSON.stringify({ type: 'audio_chunk', data }));
      }
      if (queued.length) console.info(`[CI] Flushed ${queued.length} buffered audio chunks`);
    };

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

          case 'transcript_line': {
            const line = {
              id: data.id || data.line_id || ++_eventCounter,
              text: data.text || data.payload?.text || '',
              speaker: data.speaker || data.payload?.speaker || 'unknown',
              is_final: data.is_final ?? data.payload?.is_final ?? true,
              timestamp: data.timestamp || data.payload?.timestamp_seconds || null,
            };
            setTranscript(prev => {
              const idx = prev.findIndex(l => l.id === line.id);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = line;
                return updated;
              }
              return [...prev, line];
            });
            break;
          }

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

  const _playAudioFile = useCallback((audioUrl) => {
    return new Promise((resolve, reject) => {
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audio.onended = () => {
        audioRef.current = null;
        resolve();
      };
      audio.onerror = () => {
        audioRef.current = null;
        reject(new Error('Disclosure audio could not be loaded'));
      };
      audio.play().catch((e) => {
        audioRef.current = null;
        reject(new Error(`Audio play blocked: ${e.message}`));
      });
    });
  }, []);

  const _speakDisclosure = useCallback((text, causeErr) => {
    return new Promise((resolve, reject) => {
      if (!text || typeof window.speechSynthesis === 'undefined') {
        reject(new Error(
          `${causeErr?.message || 'Disclosure audio unavailable'}. Tap to allow audio.`
        ));
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.onend = () => resolve();
      utterance.onerror = () => reject(new Error(
        `${causeErr?.message || 'Disclosure audio unavailable'} and speech synthesis failed. Tap to retry.`
      ));
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });
  }, []);

  const _playBrowserDisclosure = useCallback(
    async (audioUrl, sessId, fallbackText) => {
      try {
        if (!audioUrl) throw new Error('No disclosure audio configured');
        await _playAudioFile(audioUrl);
      } catch (audioErr) {
        // Asset missing/unsupported or autoplay blocked — speak the
        // disclosure with on-device TTS so consent can still be satisfied.
        await _speakDisclosure(fallbackText, audioErr);
      }
      try {
        await api.post(
          '/api/v1/call-intelligence/session/confirm-browser-disclosure',
          { session_id: sessId }
        );
      } catch (e) {
        throw new Error(e.detail || e.message || 'Browser disclosure confirmation failed');
      }
    },
    [_playAudioFile, _speakDisclosure]
  );

  const startSession = useCallback(async () => {
    setSessionState(SESSION_STATES.REQUESTING_CONSENT);
    setErrorMessage(null);
    setAgentEvents([]);
    setAgentStatuses({});
    setTranscript([]);

    try {
      const isBrowserMode = !callControlId;

      const response = await api.post('/api/v1/call-intelligence/session/start', {
        call_control_id: callControlId || null,
        contact_id: contactId || null,
        borrower_state: borrowerState || null,
        loan_officer_id: loanOfficerId || null,
        is_browser_mode: isBrowserMode,
      });

      const data = response.data;
      setSessionId(data.session_id);

      setConsentInfo({
        status: data.consent_status,
        requirement: data.consent_requirement,
        isFelonyState: data.is_felony_state,
        isBrowserMode: data.is_browser_mode,
        message: data.message,
      });

      if (data.consent_status === 'browser_pending' && (data.disclosure_audio_url || data.disclosure_text)) {
        setDisclosureAudioUrl(data.disclosure_audio_url || null);
        setDisclosureText(data.disclosure_text || null);
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);

        try {
          await _playBrowserDisclosure(data.disclosure_audio_url, data.session_id, data.disclosure_text);
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
      setErrorMessage(err.detail || err.message || 'Failed to start session');
      callbacksRef.current.onError?.(err);
    }
  }, [callControlId, contactId, borrowerState, loanOfficerId, _playBrowserDisclosure]);

  const retryDisclosure = useCallback(async () => {
    if (!sessionId) return;

    setSessionState(SESSION_STATES.REQUESTING_CONSENT);
    setErrorMessage(null);

    try {
      const response = await api.post('/api/v1/call-intelligence/session/retry-disclosure', {
        session_id: sessionId,
        call_control_id: callControlId || null,
        is_browser_mode: !callControlId,
      });

      const data = response.data;

      if (data.consent_status === 'browser_pending' && (data.disclosure_audio_url || data.disclosure_text)) {
        setDisclosureAudioUrl(data.disclosure_audio_url || null);
        setDisclosureText(data.disclosure_text || null);
        setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);
        try {
          await _playBrowserDisclosure(data.disclosure_audio_url, sessionId, data.disclosure_text);
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
      setErrorMessage(err.detail || err.message || 'Retry failed');
    }
  }, [sessionId, callControlId, _playBrowserDisclosure]);

  // iOS blocks audio started after an async hop (the POST in startSession
  // breaks the user-gesture chain). This replays the disclosure directly
  // inside a tap handler, where Audio.play() is always allowed.
  const playDisclosureManually = useCallback(async () => {
    if ((!disclosureAudioUrl && !disclosureText) || !sessionIdRef.current) return;
    setSessionState(SESSION_STATES.PLAYING_DISCLOSURE);
    setErrorMessage(null);
    try {
      await _playBrowserDisclosure(disclosureAudioUrl, sessionIdRef.current, disclosureText);
      setSessionState(SESSION_STATES.ACTIVE);
      setConsentInfo((prev) => ({ ...prev, status: CONSENT_STATUSES.DISCLOSED }));
      callbacksRef.current.onConsentCleared?.();
      callbacksRef.current.onSessionActive?.(sessionIdRef.current);
    } catch (audioErr) {
      setSessionState(SESSION_STATES.CONSENT_FAILED);
      setErrorMessage(audioErr.message);
      setConsentInfo((prev) => ({ ...prev, status: CONSENT_STATUSES.FAILED }));
    }
  }, [disclosureAudioUrl, disclosureText, _playBrowserDisclosure]);

  const confirmVerbalDisclosure = useCallback(async () => {
    if (!sessionId) return;

    if (consentInfo?.isFelonyState || consentInfo?.requirement === 'required') {
      setErrorMessage('Manual override blocked in two-party consent states.');
      return;
    }

    try {
      await api.post('/api/v1/call-intelligence/session/manual-consent-override', {
        session_id: sessionId,
        lo_confirmed_verbal_disclosure: true,
      });

      setSessionState(SESSION_STATES.ACTIVE);
      setConsentInfo((prev) => ({
        ...prev,
        status: CONSENT_STATUSES.DISCLOSED,
        manualOverride: true,
      }));
      callbacksRef.current.onConsentCleared?.();
      callbacksRef.current.onSessionActive?.(sessionIdRef.current);
    } catch (err) {
      setErrorMessage(err.detail || err.message || 'Override failed');
    }
  }, [sessionId, consentInfo]);

  const stopSession = useCallback(async () => {
    if (sessionId) {
      await api.post(`/api/v1/call-intelligence/session/${sessionId}/stop`).catch(() => {});
    }
    sessionStateRef.current = SESSION_STATES.COMPLETED;
    setSessionState(SESSION_STATES.COMPLETED);
    wsRef.current?.close();
    clearTimeout(timeoutRef.current);
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (typeof window.speechSynthesis !== 'undefined') {
      window.speechSynthesis.cancel();
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
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'audio_chunk', data: base64Data }));
      return;
    }
    if (ws?.readyState === WebSocket.CONNECTING) {
      if (pendingAudioRef.current.length < 60) {
        pendingAudioRef.current.push(base64Data);
      } else {
        droppedChunksRef.current += 1;
      }
      return;
    }
    droppedChunksRef.current += 1;
    if (droppedChunksRef.current % 20 === 1) {
      console.warn(
        `[CI] Dropped ${droppedChunksRef.current} audio chunks (WS state=${ws ? ws.readyState : 'none'})`
      );
    }
  }, []);

  return {
    sessionState,
    sessionId,
    consentInfo,
    errorMessage,
    agentStatuses,
    agentEvents,
    transcript,
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
    canPlayDisclosure:
      sessionState === SESSION_STATES.CONSENT_FAILED &&
      (!!disclosureAudioUrl || !!disclosureText),
    disclosureAudioUrl,
    disclosureText,

    startSession,
    stopSession,
    retryDisclosure,
    confirmVerbalDisclosure,
    playDisclosureManually,
    sendTranscript,
    sendAudio,
  };
}
