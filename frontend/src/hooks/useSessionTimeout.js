/**
 * useSessionTimeout Hook
 *
 * React hook that provides session timeout state and actions.
 * Wraps the sessionManager service with reactive state updates.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  initSession,
  getSessionState,
  extendSession as extendSessionAction,
  lockSession as lockSessionAction,
  unlockWithBiometrics,
  unlockWithPassword,
  onSessionStateChange,
} from '../services/sessionManager';

/**
 * Hook for session timeout management.
 *
 * @returns {Object} Session timeout state and actions
 * @returns {boolean} isWarning - True when within 2 min of expiry
 * @returns {number} timeRemaining - Seconds until timeout
 * @returns {boolean} isLocked - Session has expired / is locked
 * @returns {number} failedAttempts - Number of failed unlock attempts
 * @returns {Function} extendSession - Reset inactivity timer
 * @returns {Function} lock - Manually lock session
 * @returns {Function} unlockBiometric - Unlock with biometrics
 * @returns {Function} unlockPassword - Unlock with password
 */
export function useSessionTimeout() {
  const [sessionState, setSessionState] = useState(() => getSessionState());
  const countdownRef = useRef(null);

  // Initialize session manager on mount
  useEffect(() => {
    initSession();

    // Subscribe to session state changes from the manager
    const unsubscribe = onSessionStateChange((state) => {
      setSessionState(state);
    });

    return () => {
      unsubscribe();
    };
    // Note: we do NOT destroy the session here because the session should
    // persist across component re-mounts. destroySession() is called on logout.
  }, []);

  // Countdown timer for the warning state — updates every second
  useEffect(() => {
    if (sessionState.isWarning && !sessionState.isLocked) {
      countdownRef.current = setInterval(() => {
        setSessionState((prev) => {
          const state = getSessionState();
          return {
            ...prev,
            timeRemaining: state.timeRemaining,
            isLocked: state.isLocked,
            isWarning: state.isWarning,
          };
        });
      }, 1000);
    } else {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    }

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, [sessionState.isWarning, sessionState.isLocked]);

  // Actions
  const extendSession = useCallback(() => {
    const result = extendSessionAction();
    if (result) {
      setSessionState(getSessionState());
    }
    return result;
  }, []);

  const lock = useCallback(() => {
    lockSessionAction();
    setSessionState(getSessionState());
  }, []);

  const unlockBiometric = useCallback(async () => {
    const result = await unlockWithBiometrics();
    setSessionState(getSessionState());
    return result;
  }, []);

  const unlockPassword = useCallback(async (password) => {
    const result = await unlockWithPassword(password);
    setSessionState(getSessionState());
    return result;
  }, []);

  return {
    // State
    isWarning: sessionState.isWarning,
    timeRemaining: sessionState.timeRemaining,
    isLocked: sessionState.isLocked,
    failedAttempts: sessionState.failedAttempts,

    // Actions
    extendSession,
    lock,
    unlockBiometric,
    unlockPassword,
  };
}

export default useSessionTimeout;
