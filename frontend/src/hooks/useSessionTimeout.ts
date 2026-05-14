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

export interface SessionState {
  isWarning: boolean;
  timeRemaining: number;
  isLocked: boolean;
  failedAttempts: number;
}

export interface UseSessionTimeoutReturn {
  // State
  isWarning: boolean;
  timeRemaining: number;
  isLocked: boolean;
  failedAttempts: number;
  // Actions
  extendSession: () => boolean;
  lock: () => void;
  unlockBiometric: () => Promise<boolean>;
  unlockPassword: (password: string) => Promise<boolean>;
}

/**
 * Hook for session timeout management.
 */
export function useSessionTimeout(): UseSessionTimeoutReturn {
  const [sessionState, setSessionState] = useState<SessionState>(() => getSessionState());
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Initialize session manager on mount
  useEffect(() => {
    initSession();

    // Subscribe to session state changes from the manager
    const unsubscribe = onSessionStateChange((state: SessionState) => {
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
  const extendSession = useCallback((): boolean => {
    const result = extendSessionAction();
    if (result) {
      setSessionState(getSessionState());
    }
    return result;
  }, []);

  const lock = useCallback((): void => {
    lockSessionAction();
    setSessionState(getSessionState());
  }, []);

  const unlockBiometric = useCallback(async (): Promise<boolean> => {
    const result = await unlockWithBiometrics();
    setSessionState(getSessionState());
    return result;
  }, []);

  const unlockPassword = useCallback(async (password: string): Promise<boolean> => {
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
