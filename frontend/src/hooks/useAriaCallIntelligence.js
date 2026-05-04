/**
 * useAriaCallIntelligence — Bridge hook connecting Aria voice state to CI session.
 *
 * Wraps useCallIntelligenceSession with Aria-specific behavior:
 * - Coordinated start/stop with voice recording
 * - Event callbacks for the Aria UI
 */

import { useState, useCallback } from 'react';
import { useCallIntelligenceSession } from './useCallIntelligenceSession';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

const useAriaCallIntelligence = ({ onSessionStarted, onSessionEnded } = {}) => {
  const [isStarting, setIsStarting] = useState(false);

  const ciSession = useCallIntelligenceSession({
    websocketUrl: `${WS_BASE_URL}/api/v1/call-intelligence/session`,
  });

  const startRecording = useCallback(async () => {
    if (ciSession.isActive || isStarting) return null;

    setIsStarting(true);
    try {
      await ciSession.startSession();
      if (ciSession.sessionId) {
        onSessionStarted?.(ciSession.sessionId);
      }
      return ciSession.sessionId;
    } catch (err) {
      console.error('[AriaCI] Failed to start recording:', err);
      return null;
    } finally {
      setIsStarting(false);
    }
  }, [ciSession.isActive, ciSession.startSession, ciSession.sessionId, isStarting, onSessionStarted]);

  const stopRecording = useCallback(async () => {
    if (!ciSession.isActive) return;

    try {
      await ciSession.stopSession();
      onSessionEnded?.();
    } catch (err) {
      console.error('[AriaCI] Failed to stop recording:', err);
    }
  }, [ciSession.isActive, ciSession.stopSession, onSessionEnded]);

  return {
    sessionId: ciSession.sessionId,
    sessionState: ciSession.sessionState,
    isActive: ciSession.isActive,
    isStarting,
    duration: ciSession.duration || 0,
    agentStatuses: ciSession.agentStatuses || {},
    agentEvents: ciSession.agentEvents || [],

    startRecording,
    stopRecording,

    // Consent state pass-through
    consentInfo: ciSession.consentInfo,
    errorMessage: ciSession.errorMessage,
    isConsentFailed: ciSession.isConsentFailed,
    retryDisclosure: ciSession.retryDisclosure,
    confirmVerbalDisclosure: ciSession.confirmVerbalDisclosure,
  };
};

export default useAriaCallIntelligence;
