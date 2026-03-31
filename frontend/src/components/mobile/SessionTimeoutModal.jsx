/**
 * SessionTimeoutModal
 *
 * Displays a warning before session expiry and a lock screen
 * when the session has expired. Supports biometric and password unlock.
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useSessionTimeout } from '../../hooks/useSessionTimeout';
import { biometrics, isNative, haptics } from '../../services/nativeServices';
import { destroySession } from '../../services/sessionManager';
import './SessionTimeoutModal.css';

const MAX_ATTEMPTS = 3;

export default function SessionTimeoutModal() {
  const {
    isWarning,
    timeRemaining,
    isLocked,
    failedAttempts,
    extendSession,
    unlockBiometric,
    unlockPassword,
  } = useSessionTimeout();

  const [password, setPassword] = useState('');
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [authError, setAuthError] = useState('');
  const [biometricAvailable, setBiometricAvailable] = useState(false);
  const [biometryType, setBiometryType] = useState('none');
  const passwordRef = useRef(null);

  // Check biometric availability
  useEffect(() => {
    async function checkBiometrics() {
      const result = await biometrics.isAvailable();
      setBiometricAvailable(result.available);
      setBiometryType(result.biometryType);
    }
    checkBiometrics();
  }, []);

  // Auto-trigger biometric on lock (native only)
  useEffect(() => {
    if (isLocked && biometricAvailable && isNative) {
      // Small delay for the lock screen to render
      const timer = setTimeout(() => {
        handleBiometricUnlock();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isLocked]); // eslint-disable-line react-hooks/exhaustive-deps

  // Focus password field when locked without biometrics
  useEffect(() => {
    if (isLocked && !biometricAvailable && passwordRef.current) {
      passwordRef.current.focus();
    }
  }, [isLocked, biometricAvailable]);

  // Format time remaining as M:SS
  const formatTime = useCallback((seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }, []);

  const getBiometricLabel = useCallback(() => {
    switch (biometryType) {
      case 'faceId': return 'Face ID';
      case 'touchId': return 'Touch ID';
      case 'fingerprint': return 'Fingerprint';
      default: return 'Biometrics';
    }
  }, [biometryType]);

  const getBiometricIcon = useCallback(() => {
    switch (biometryType) {
      case 'faceId':
        return (
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect x="6" y="6" width="36" height="36" rx="8" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <circle cx="18" cy="20" r="2" fill="currentColor" />
            <circle cx="30" cy="20" r="2" fill="currentColor" />
            <path d="M18 30 C20 33 28 33 30 30" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
          </svg>
        );
      case 'touchId':
      case 'fingerprint':
        return (
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M24 6 C15 6 8 13 8 22 L8 26" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M24 12 C18 12 14 17 14 22 L14 30" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M24 18 C21 18 20 20 20 22 L20 34" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M24 18 C27 18 28 20 28 22 L28 30 C28 34 30 36 32 36" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M24 6 C33 6 40 13 40 22 L40 28 C40 32 38 34 36 36" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
            <path d="M34 22 L34 26 C34 30 35 32 37 34" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
          </svg>
        );
      default:
        return (
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect x="10" y="20" width="28" height="22" rx="4" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <path d="M16 20 L16 14 C16 9.6 19.6 6 24 6 C28.4 6 32 9.6 32 14 L32 20" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" />
            <circle cx="24" cy="31" r="3" fill="currentColor" />
          </svg>
        );
    }
  }, [biometryType]);

  const handleBiometricUnlock = useCallback(async () => {
    if (isAuthenticating) return;

    setIsAuthenticating(true);
    setAuthError('');

    try {
      const success = await unlockBiometric();
      if (success) {
        if (isNative) haptics.success();
        setPassword('');
        setAuthError('');
      } else {
        if (isNative) haptics.error();
        setAuthError('Authentication failed. Try again or use your password.');
      }
    } catch (err) {
      if (isNative) haptics.error();
      setAuthError('Authentication error. Please use your password.');
    } finally {
      setIsAuthenticating(false);
    }
  }, [isAuthenticating, unlockBiometric]);

  const handlePasswordUnlock = useCallback(async (e) => {
    e.preventDefault();
    if (isAuthenticating || !password.trim()) return;

    setIsAuthenticating(true);
    setAuthError('');

    try {
      const success = await unlockPassword(password);
      if (success) {
        if (isNative) haptics.success();
        setPassword('');
        setAuthError('');
      } else {
        if (isNative) haptics.error();
        const remaining = MAX_ATTEMPTS - (failedAttempts + 1);
        if (remaining > 0) {
          setAuthError(`Incorrect password. ${remaining} ${remaining === 1 ? 'attempt' : 'attempts'} remaining.`);
        }
        setPassword('');
      }
    } catch (err) {
      if (isNative) haptics.error();
      setAuthError('Authentication error. Please try again.');
      setPassword('');
    } finally {
      setIsAuthenticating(false);
    }
  }, [isAuthenticating, password, unlockPassword, failedAttempts]);

  const handleStayLoggedIn = useCallback(() => {
    if (isNative) haptics.light();
    extendSession();
  }, [extendSession]);

  const handleForgotPassword = useCallback(() => {
    destroySession();
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login?forgot=1';
  }, []);

  const handleFullLogout = useCallback(() => {
    destroySession();
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }, []);

  // Do not render if neither warning nor locked
  if (!isWarning && !isLocked) {
    return null;
  }

  // --- WARNING STATE ---
  if (isWarning && !isLocked) {
    return (
      <div className="session-timeout-overlay session-timeout-overlay--warning" role="alertdialog" aria-label="Session expiring soon">
        <div className="session-timeout-modal session-timeout-modal--warning">
          <div className="session-timeout-modal__icon session-timeout-modal__icon--warning">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2" fill="none" />
              <path d="M16 8 L16 18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M16 18 L22 18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
          <h2 className="session-timeout-modal__title">Session Expiring</h2>
          <p className="session-timeout-modal__message">
            Your session will expire in <strong>{formatTime(timeRemaining)}</strong> due to inactivity.
          </p>
          <div className="session-timeout-modal__actions">
            <button
              className="session-timeout-btn session-timeout-btn--primary"
              onClick={handleStayLoggedIn}
              type="button"
            >
              Stay Logged In
            </button>
            <button
              className="session-timeout-btn session-timeout-btn--secondary"
              onClick={handleFullLogout}
              type="button"
            >
              Log Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- LOCKED STATE ---
  return (
    <div className="session-timeout-overlay session-timeout-overlay--locked" role="dialog" aria-label="Session locked">
      <div className="session-timeout-locked">
        {/* Logo */}
        <div className="session-timeout-locked__logo">
          <div className="session-timeout-locked__logo-icon">
            <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <circle cx="22" cy="22" r="20" stroke="currentColor" strokeWidth="2" fill="none" />
              <text x="22" y="28" textAnchor="middle" fill="currentColor" fontSize="18" fontWeight="700" fontFamily="system-ui">P</text>
            </svg>
          </div>
          <span className="session-timeout-locked__logo-text">Perennia AI</span>
        </div>

        {/* Status */}
        <h2 className="session-timeout-locked__title">Session Locked</h2>
        <p className="session-timeout-locked__subtitle">
          Your session expired due to inactivity. Please authenticate to continue.
        </p>

        {/* Biometric unlock button */}
        {biometricAvailable && (
          <button
            className="session-timeout-biometric-btn"
            onClick={handleBiometricUnlock}
            disabled={isAuthenticating}
            type="button"
            aria-label={`Unlock with ${getBiometricLabel()}`}
          >
            <span className="session-timeout-biometric-btn__icon">
              {getBiometricIcon()}
            </span>
            <span className="session-timeout-biometric-btn__label">
              {isAuthenticating ? 'Verifying...' : `Unlock with ${getBiometricLabel()}`}
            </span>
          </button>
        )}

        {/* Divider */}
        {biometricAvailable && (
          <div className="session-timeout-locked__divider">
            <span>or use password</span>
          </div>
        )}

        {/* Password form */}
        <form className="session-timeout-locked__form" onSubmit={handlePasswordUnlock}>
          <div className="session-timeout-locked__field">
            <input
              ref={passwordRef}
              type="password"
              className="session-timeout-locked__input"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isAuthenticating}
              autoComplete="current-password"
              aria-label="Password"
            />
          </div>

          {authError && (
            <p className="session-timeout-locked__error" role="alert">{authError}</p>
          )}

          <button
            className="session-timeout-btn session-timeout-btn--primary session-timeout-btn--full"
            type="submit"
            disabled={isAuthenticating || !password.trim()}
          >
            {isAuthenticating ? 'Verifying...' : 'Unlock'}
          </button>
        </form>

        {/* Footer links */}
        <div className="session-timeout-locked__footer">
          <button
            className="session-timeout-link"
            onClick={handleForgotPassword}
            type="button"
          >
            Forgot password?
          </button>
          <button
            className="session-timeout-link"
            onClick={handleFullLogout}
            type="button"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  );
}
