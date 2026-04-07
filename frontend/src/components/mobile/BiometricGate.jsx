/**
 * BiometricGate Component
 *
 * A wrapper that requires biometric authentication (Face ID / Touch ID) before
 * revealing its children. Used on sensitive screens that display PII such as
 * borrower documents, bank statements, credit reports, and SSN.
 *
 * Behavior:
 * - On native with biometrics: shows verification screen, prompts biometric auth
 * - On web or when biometric unavailable: renders children immediately
 * - Caches auth for 5 minutes (configurable via AUTH_CACHE_MS)
 * - User can disable via preference toggle in Security settings
 * - Rate limited: max 5 attempts per 30 seconds
 *
 * Props:
 * @param {React.ReactNode}  children        - Content to show after authentication
 * @param {string}           reason          - Text shown in the biometric prompt
 * @param {Function}         onAuthenticated - Optional callback fired on successful auth
 * @param {Function}         onFailed        - Optional callback fired on auth failure
 * @param {React.ReactNode}  fallback        - Optional custom loading/checking state
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  useBiometricAuth,
  authenticateWithBiometric,
  getBiometryName,
} from '../../services/biometricAuth';
import { auditLog, AUDIT_EVENTS } from '../../services/mobileAuditLogger';
import './BiometricGate.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AUTH_CACHE_MS = 5 * 60 * 1000; // 5 minutes
const RATE_LIMIT_WINDOW_MS = 30 * 1000; // 30 seconds
const RATE_LIMIT_MAX_ATTEMPTS = 5;

// Inline SVG icons to avoid external dependencies

const FaceIdIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Face ID">
    <rect x="4" y="4" width="16" height="4" rx="2" fill="currentColor" />
    <rect x="4" y="4" width="4" height="16" rx="2" fill="currentColor" />
    <rect x="44" y="4" width="16" height="4" rx="2" fill="currentColor" />
    <rect x="56" y="4" width="4" height="16" rx="2" fill="currentColor" />
    <rect x="4" y="56" width="16" height="4" rx="2" fill="currentColor" />
    <rect x="4" y="44" width="4" height="16" rx="2" fill="currentColor" />
    <rect x="44" y="56" width="16" height="4" rx="2" fill="currentColor" />
    <rect x="56" y="44" width="4" height="16" rx="2" fill="currentColor" />
    <circle cx="24" cy="26" r="3" fill="currentColor" />
    <circle cx="40" cy="26" r="3" fill="currentColor" />
    <rect x="30" y="22" width="4" height="14" rx="2" fill="currentColor" />
    <path d="M22 42C22 42 26 48 32 48C38 48 42 42 42 42" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>
);

const TouchIdIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Touch ID">
    <path d="M32 8C18.745 8 8 18.745 8 32" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <path d="M56 32C56 18.745 45.255 8 32 8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.7" />
    <path d="M32 56C45.255 56 56 45.255 56 32" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.5" />
    <path d="M8 32C8 45.255 18.745 56 32 56" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.3" />
    <path d="M32 16C23.163 16 16 23.163 16 32C16 40.837 23.163 48 32 48" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <path d="M32 16C40.837 16 48 23.163 48 32C48 40.837 40.837 48 32 48" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity="0.6" />
    <path d="M32 24C27.582 24 24 27.582 24 32C24 36.418 27.582 40 32 40C36.418 40 40 36.418 40 32C40 27.582 36.418 24 32 24Z" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <circle cx="32" cy="32" r="4" fill="currentColor" />
  </svg>
);

const LockIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Locked">
    <rect x="16" y="28" width="32" height="28" rx="4" fill="currentColor" opacity="0.15" stroke="currentColor" strokeWidth="3" />
    <path d="M22 28V20C22 14.477 26.477 10 32 10C37.523 10 42 14.477 42 20V28" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <circle cx="32" cy="40" r="4" fill="currentColor" />
    <rect x="30" y="42" width="4" height="6" rx="2" fill="currentColor" />
  </svg>
);

const RetryIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label="Retry">
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map numeric biometryType to a string key used for icon selection and hints.
 * @param {number|string} type - biometryType from checkBiometricAvailability
 * @returns {'faceId'|'touchId'|'unknown'}
 */
function biometryTypeToKey(type) {
  switch (type) {
    case 2: return 'faceId';
    case 1: return 'touchId';
    case 3: // Iris
    case 4: // Multiple — treat like fingerprint
      return 'touchId';
    default: return 'unknown';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function BiometricGate({
  children,
  reason = 'Verify your identity to view sensitive data',
  onAuthenticated,
  onFailed,
  fallback,
}) {
  // Use the existing hook from biometricAuth.js for availability state
  const { available, biometryType, hasCredentials, loading } = useBiometricAuth();

  // Local gate state
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState(null);
  const [lastAuthTime, setLastAuthTime] = useState(null);

  // Rate limiting: track attempt timestamps within the rolling window
  const attemptsRef = useRef([]);

  // Derived display values
  const biometryKey = biometryTypeToKey(biometryType);
  const biometryDisplayName = getBiometryName(biometryType);

  // Whether biometric gate is actually required (native + available + has creds)
  const isRequired = available && hasCredentials;

  // ----------------------------------------------------------
  // Check rate limit
  // ----------------------------------------------------------
  const isRateLimited = useCallback(() => {
    const now = Date.now();
    // Prune attempts outside the window
    attemptsRef.current = attemptsRef.current.filter(
      (t) => now - t < RATE_LIMIT_WINDOW_MS
    );
    return attemptsRef.current.length >= RATE_LIMIT_MAX_ATTEMPTS;
  }, []);

  const recordAttempt = useCallback(() => {
    attemptsRef.current.push(Date.now());
  }, []);

  // ----------------------------------------------------------
  // Authenticate handler
  // ----------------------------------------------------------
  const authenticate = useCallback(async () => {
    if (isRateLimited()) {
      const msg = 'Too many attempts. Please wait 30 seconds and try again.';
      setError(msg);
      auditLog(AUDIT_EVENTS.BIOMETRIC_AUTH, {
        action: 'rate_limited',
        biometryType: biometryKey,
      });
      return;
    }

    recordAttempt();
    setError(null);

    const result = await authenticateWithBiometric();

    if (result.success) {
      const now = Date.now();
      setIsAuthenticated(true);
      setLastAuthTime(now);
      auditLog(AUDIT_EVENTS.BIOMETRIC_AUTH, {
        action: 'success',
        biometryType: biometryKey,
      });
    } else {
      const errMsg = result.error || 'Authentication failed. Please try again.';
      setError(errMsg);
      auditLog(AUDIT_EVENTS.BIOMETRIC_AUTH, {
        action: 'failed',
        biometryType: biometryKey,
        error: errMsg,
      });
    }
  }, [biometryKey, isRateLimited, recordAttempt]);

  // ----------------------------------------------------------
  // On mount: determine if gate is needed and auto-prompt
  // ----------------------------------------------------------
  useEffect(() => {
    // Wait for the useBiometricAuth hook to finish loading
    if (loading) return;

    // If biometric is not required, pass through immediately
    if (!isRequired) {
      setIsAuthenticated(true);
      setIsChecking(false);
      return;
    }

    // Check 5-minute cache
    if (lastAuthTime && Date.now() - lastAuthTime < AUTH_CACHE_MS) {
      setIsAuthenticated(true);
      setIsChecking(false);
      return;
    }

    // Biometric is required -- show the gate and auto-prompt
    setIsChecking(false);
    // Auto-prompt biometric on mount
    authenticate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, isRequired]);

  // ----------------------------------------------------------
  // Fire callback props
  // ----------------------------------------------------------
  useEffect(() => {
    if (isAuthenticated && isRequired && onAuthenticated) {
      onAuthenticated();
    }
  }, [isAuthenticated, isRequired, onAuthenticated]);

  useEffect(() => {
    if (error && onFailed) {
      onFailed(error);
    }
  }, [error, onFailed]);

  // ----------------------------------------------------------
  // Render: checking / loading state
  // ----------------------------------------------------------
  if (isChecking || loading) {
    if (fallback) return fallback;
    return (
      <div className="biometric-gate" role="dialog" aria-modal="true" aria-label="Security check in progress">
        <div className="biometric-gate__container">
          <div className="biometric-gate__icon biometric-gate__icon--pulse">
            <LockIcon />
          </div>
          <p className="biometric-gate__status" aria-live="polite">Checking security...</p>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------------
  // Render: authenticated (or not required) -- show children
  // ----------------------------------------------------------
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // ----------------------------------------------------------
  // Render: gate screen -- biometric required but not verified
  // ----------------------------------------------------------
  const BiometricIcon = biometryKey === 'faceId' ? FaceIdIcon
    : biometryKey === 'touchId' ? TouchIdIcon
    : LockIcon;

  const rateLimited = isRateLimited();

  return (
    <div className="biometric-gate" role="dialog" aria-modal="true" aria-label="Biometric authentication required">
      <div className="biometric-gate__container">
        <div className={`biometric-gate__icon ${error ? 'biometric-gate__icon--error' : ''}`}>
          <BiometricIcon />
        </div>

        <h2 className="biometric-gate__title">Verify Your Identity</h2>

        <p className="biometric-gate__reason" id="biometric-gate-description">{reason}</p>

        <div aria-live="polite" className="biometric-gate__error-region">
          {error && (
            <p className="biometric-gate__error" role="alert">{error}</p>
          )}
        </div>

        <button
          className="biometric-gate__button"
          onClick={authenticate}
          type="button"
          disabled={rateLimited}
          tabIndex={0}
          aria-label={`Authenticate with ${biometryDisplayName} to view sensitive content`}
          aria-describedby="biometric-gate-description"
        >
          <span className="biometric-gate__button-icon">
            {error ? <RetryIcon /> : null}
          </span>
          {rateLimited
            ? 'Please wait...'
            : error
            ? `Retry ${biometryDisplayName}`
            : `Use ${biometryDisplayName}`
          }
        </button>

        <p className="biometric-gate__hint">
          {rateLimited
            ? 'Too many attempts. Please wait 30 seconds.'
            : biometryKey === 'faceId'
            ? 'Look at your device to authenticate'
            : biometryKey === 'touchId'
            ? 'Place your finger on the sensor'
            : 'Authenticate to continue'
          }
        </p>
      </div>
    </div>
  );
}

export default BiometricGate;
