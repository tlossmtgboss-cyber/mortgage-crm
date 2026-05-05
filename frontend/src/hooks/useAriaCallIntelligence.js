/**
 * useAriaCallIntelligence — Bridge hook connecting Aria voice state to CI session.
 *
 * Wraps useCallIntelligenceSession with Aria-specific behavior:
 * - Coordinated start/stop with voice recording
 * - Browser speech recognition → WebSocket transcript forwarding
 * - Event callbacks for the Aria UI
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { useCallIntelligenceSession } from './useCallIntelligenceSession';

const API_BASE_URL = (process.env.REACT_APP_API_URL || 'https://api.perenniaai.com').replace(/\/+$/, '');
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

const useAriaCallIntelligence = ({ onSessionStarted, onSessionEnded } = {}) => {
  const [isStarting, setIsStarting] = useState(false);
  const onSessionStartedRef = useRef(onSessionStarted);
  const onSessionEndedRef = useRef(onSessionEnded);
  const recognitionRef = useRef(null);
  onSessionStartedRef.current = onSessionStarted;
  onSessionEndedRef.current = onSessionEnded;

  const ciSession = useCallIntelligenceSession({
    websocketUrl: `${WS_BASE_URL}/api/v1/call-intelligence`,
    onSessionActive: (sessId) => {
      onSessionStartedRef.current?.(sessId);
    },
  });

  useEffect(() => {
    if (!ciSession.isActive || !ciSession.wsConnected) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0].transcript;
        if (result.isFinal && text.trim()) {
          ciSession.sendTranscript(text.trim(), true);
        }
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        console.error('[AriaCI] Speech recognition error:', event.error);
      }
    };

    recognition.onend = () => {
      if (ciSession.isActive && recognitionRef.current) {
        try { recognition.start(); } catch (_) {}
      }
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
    } catch (e) {
      console.error('[AriaCI] Failed to start speech recognition:', e);
    }

    return () => {
      recognition.stop();
      recognitionRef.current = null;
    };
  }, [ciSession.isActive, ciSession.wsConnected, ciSession.sendTranscript]);

  const startRecording = useCallback(async () => {
    if (ciSession.isActive || isStarting) return null;

    setIsStarting(true);
    try {
      await ciSession.startSession();
    } catch (err) {
      console.error('[AriaCI] Failed to start recording:', err);
    } finally {
      setIsStarting(false);
    }
  }, [ciSession.isActive, ciSession.startSession, isStarting]);

  const stopRecording = useCallback(async () => {
    if (!ciSession.isActive) return;

    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }

    try {
      await ciSession.stopSession();
      onSessionEndedRef.current?.();
    } catch (err) {
      console.error('[AriaCI] Failed to stop recording:', err);
    }
  }, [ciSession.isActive, ciSession.stopSession]);

  return {
    sessionId: ciSession.sessionId,
    sessionState: ciSession.sessionState,
    isActive: ciSession.isActive,
    isStarting,
    duration: ciSession.duration || 0,
    agentStatuses: ciSession.agentStatuses || {},
    agentEvents: ciSession.agentEvents || [],
    wsConnected: ciSession.wsConnected || false,

    startRecording,
    stopRecording,
    sendTranscript: ciSession.sendTranscript,

    consentInfo: ciSession.consentInfo,
    errorMessage: ciSession.errorMessage,
    isConsentFailed: ciSession.isConsentFailed,
    retryDisclosure: ciSession.retryDisclosure,
    confirmVerbalDisclosure: ciSession.confirmVerbalDisclosure,
  };
};

export default useAriaCallIntelligence;
