/**
 * SSOLoginButton
 *
 * Enterprise SSO login component for the Perennia AI mobile app.
 *
 * Provides:
 * - Email input with domain-based SSO detection
 * - "Sign in with {Provider}" button when SSO is detected
 * - Fallback to standard email/password form when SSO is not available
 * - Loading and error states throughout the SSO flow
 *
 * Place this component above the standard login form. When the user's
 * email domain matches a configured SSO provider, SSO takes precedence.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  checkSSOConfig,
  initiateSSO,
  getProviderDisplayName,
  getProviderColor,
} from '../../services/enterpriseSSO';
import './SSOLoginButton.css';

// Debounce delay for SSO discovery after email input (ms)
const DISCOVERY_DEBOUNCE_MS = 600;

// Provider SVG icons (inline to avoid external dependencies)
const ProviderIcon = ({ provider, size = 20 }) => {
  const style = { width: size, height: size, flexShrink: 0 };

  switch (provider) {
    case 'okta':
      return (
        <svg viewBox="0 0 24 24" style={style} fill="none">
          <circle cx="12" cy="12" r="10" fill="#007dc1" />
          <circle cx="12" cy="12" r="5" fill="#fff" />
        </svg>
      );

    case 'azure_ad':
      return (
        <svg viewBox="0 0 24 24" style={style} fill="none">
          <path d="M2 4l8.5-1.5v9H2V4z" fill="#f25022" />
          <path d="M11.5 2.3L22 1v10.5H11.5V2.3z" fill="#7fba00" />
          <path d="M2 12.5h8.5v9L2 20v-7.5z" fill="#00a4ef" />
          <path d="M11.5 12.5H22V23l-10.5-1.7V12.5z" fill="#ffb900" />
        </svg>
      );

    case 'google':
      return (
        <svg viewBox="0 0 24 24" style={style}>
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
      );

    case 'auth0':
      return (
        <svg viewBox="0 0 24 24" style={style} fill="none">
          <path d="M17.34 7.76l-2.6-4.5a3.07 3.07 0 00-5.48 0l-2.6 4.5 5.34 3.08 5.34-3.08z" fill="#eb5424" />
          <path d="M6.66 7.76H1.5a3.07 3.07 0 00-1.5 2.64v0a3.07 3.07 0 001.5 2.64l5.16-5.28z" fill="#eb5424" />
          <path d="M17.34 7.76h5.16a3.07 3.07 0 011.5 2.64v0a3.07 3.07 0 01-1.5 2.64l-5.16-5.28z" fill="#eb5424" />
          <path d="M6.66 16.24l2.6 4.5a3.07 3.07 0 005.48 0l2.6-4.5-5.34-3.08-5.34 3.08z" fill="#eb5424" />
        </svg>
      );

    default:
      // Generic SSO / shield icon
      return (
        <svg viewBox="0 0 24 24" style={style} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <polyline points="9 12 11 14 15 10" />
        </svg>
      );
  }
};

/**
 * SSOLoginButton component
 *
 * @param {object} props
 * @param {function} [props.onSSOSuccess] - Called with { token, user } on successful SSO login.
 * @param {function} [props.onSSOError] - Called with error message on SSO failure.
 * @param {function} [props.onNoSSO] - Called with email when domain has no SSO (show password form).
 * @param {string} [props.initialEmail] - Pre-populate the email field.
 * @param {boolean} [props.compact] - Use compact layout (less padding).
 * @param {string} [props.className] - Additional CSS class name.
 */
export default function SSOLoginButton({
  onSSOSuccess,
  onSSOError,
  onNoSSO,
  initialEmail = '',
  compact = false,
  className = '',
}) {
  const [email, setEmail] = useState(initialEmail);
  const [phase, setPhase] = useState('email'); // 'email' | 'checking' | 'sso_found' | 'no_sso' | 'authenticating' | 'error'
  const [ssoConfig, setSsoConfig] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const debounceRef = useRef(null);
  const emailInputRef = useRef(null);

  // Clean up debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // Auto-check SSO when initialEmail is provided
  useEffect(() => {
    if (initialEmail && initialEmail.includes('@')) {
      handleCheckSSO(initialEmail);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialEmail]);

  /**
   * Check SSO config for an email address.
   */
  const handleCheckSSO = useCallback(async (emailToCheck) => {
    const targetEmail = emailToCheck || email;
    if (!targetEmail || !targetEmail.includes('@')) return;

    setPhase('checking');
    setErrorMessage('');

    try {
      const config = await checkSSOConfig(targetEmail);

      if (config.hasSso) {
        setSsoConfig(config);
        setPhase('sso_found');
      } else {
        setSsoConfig(null);
        setPhase('no_sso');
        if (onNoSSO) onNoSSO(targetEmail);
      }
    } catch (err) {
      console.error('SSO check failed:', err);
      // On discovery failure, fall back to password login
      setPhase('no_sso');
      if (onNoSSO) onNoSSO(targetEmail);
    }
  }, [email, onNoSSO]);

  /**
   * Handle email input changes with debounced SSO check.
   */
  const handleEmailChange = useCallback((e) => {
    const value = e.target.value;
    setEmail(value);

    // Reset to email phase if user is editing
    if (phase === 'sso_found' || phase === 'no_sso' || phase === 'error') {
      setPhase('email');
      setSsoConfig(null);
      setErrorMessage('');
    }

    // Debounced SSO check after user finishes typing
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (value.includes('@') && value.split('@')[1].includes('.')) {
      debounceRef.current = setTimeout(() => {
        handleCheckSSO(value);
      }, DISCOVERY_DEBOUNCE_MS);
    }
  }, [phase, handleCheckSSO]);

  /**
   * Handle form submit (Continue button).
   */
  const handleSubmit = useCallback((e) => {
    e.preventDefault();

    if (!email || !email.includes('@')) {
      setErrorMessage('Please enter a valid email address.');
      return;
    }

    if (phase === 'sso_found' && ssoConfig) {
      // Initiate SSO
      handleSSOLogin();
    } else {
      // Check SSO config
      handleCheckSSO(email);
    }
  }, [email, phase, ssoConfig, handleCheckSSO]);

  /**
   * Initiate the SSO login flow.
   */
  const handleSSOLogin = useCallback(async () => {
    if (!ssoConfig || !ssoConfig.authUrl) {
      setErrorMessage('SSO configuration is incomplete. Contact your administrator.');
      setPhase('error');
      return;
    }

    setPhase('authenticating');
    setErrorMessage('');

    try {
      await initiateSSO(ssoConfig.authUrl, {
        onSuccess: (result) => {
          setPhase('email'); // Reset phase
          if (onSSOSuccess) onSSOSuccess(result);
        },
        onError: (errorMsg) => {
          setErrorMessage(errorMsg || 'SSO authentication failed. Try again or contact your admin.');
          setPhase('error');
          if (onSSOError) onSSOError(errorMsg);
        },
      });
    } catch (err) {
      setErrorMessage(err.message || 'Failed to start SSO login. Please try again.');
      setPhase('error');
      if (onSSOError) onSSOError(err.message);
    }
  }, [ssoConfig, onSSOSuccess, onSSOError]);

  /**
   * Reset to initial email entry state.
   */
  const handleReset = useCallback(() => {
    setPhase('email');
    setSsoConfig(null);
    setErrorMessage('');
    if (emailInputRef.current) emailInputRef.current.focus();
  }, []);

  const providerName = ssoConfig ? getProviderDisplayName(ssoConfig.providerName) : '';
  const providerColor = ssoConfig ? getProviderColor(ssoConfig.providerName) : '#1a73e8';

  return (
    <div className={`sso-login ${compact ? 'sso-login--compact' : ''} ${className}`.trim()}>
      {/* Email input form */}
      <form onSubmit={handleSubmit} className="sso-login__form">
        <div className="sso-login__input-group">
          <label htmlFor="sso-email" className="sso-login__label">
            Work email
          </label>
          <div className="sso-login__input-wrap">
            <svg
              className="sso-login__input-icon"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path d="M3 4a2 2 0 00-2 2v1.161l8.441 4.221a1.25 1.25 0 001.118 0L19 7.162V6a2 2 0 00-2-2H3z" />
              <path d="M19 8.839l-7.77 3.885a2.75 2.75 0 01-2.46 0L1 8.839V14a2 2 0 002 2h14a2 2 0 002-2V8.839z" />
            </svg>
            <input
              ref={emailInputRef}
              id="sso-email"
              type="email"
              className="sso-login__input"
              placeholder="you@company.com"
              value={email}
              onChange={handleEmailChange}
              disabled={phase === 'authenticating'}
              autoComplete="email"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck="false"
              inputMode="email"
            />
            {phase === 'checking' && (
              <div className="sso-login__spinner" aria-label="Checking SSO configuration" />
            )}
          </div>
        </div>

        {/* Phase: email entry — show Continue button */}
        {(phase === 'email' || phase === 'checking') && (
          <button
            type="submit"
            className="sso-login__continue-btn"
            disabled={!email || !email.includes('@') || phase === 'checking'}
          >
            {phase === 'checking' ? 'Checking...' : 'Continue'}
          </button>
        )}
      </form>

      {/* Phase: SSO found — show provider button */}
      {phase === 'sso_found' && ssoConfig && (
        <div className="sso-login__sso-section">
          {ssoConfig.organizationName && (
            <p className="sso-login__org-name">
              {ssoConfig.organizationName}
            </p>
          )}

          <button
            type="button"
            className="sso-login__sso-btn"
            style={{ '--sso-brand-color': providerColor }}
            onClick={handleSSOLogin}
          >
            <ProviderIcon provider={ssoConfig.providerName} size={20} />
            <span>Sign in with {providerName}</span>
          </button>

          <button
            type="button"
            className="sso-login__alt-link"
            onClick={() => {
              setPhase('no_sso');
              if (onNoSSO) onNoSSO(email);
            }}
          >
            Use password instead
          </button>
        </div>
      )}

      {/* Phase: no SSO — message and defer to password form */}
      {phase === 'no_sso' && (
        <div className="sso-login__no-sso">
          <p className="sso-login__no-sso-msg">
            No SSO configured for this domain. Please sign in with your password.
          </p>
        </div>
      )}

      {/* Phase: authenticating — show loading state */}
      {phase === 'authenticating' && (
        <div className="sso-login__authenticating">
          <div className="sso-login__auth-spinner" />
          <p className="sso-login__auth-msg">
            Connecting to {providerName || 'SSO provider'}...
          </p>
          <p className="sso-login__auth-sub">
            A sign-in window will open. Complete authentication there.
          </p>
        </div>
      )}

      {/* Phase: error — show error and retry */}
      {phase === 'error' && (
        <div className="sso-login__error-section">
          <div className="sso-login__error-icon">
            <svg viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <p className="sso-login__error-msg">
            {errorMessage || 'SSO authentication failed. Try again or contact your admin.'}
          </p>
          <div className="sso-login__error-actions">
            <button
              type="button"
              className="sso-login__retry-btn"
              onClick={handleSSOLogin}
            >
              Try again
            </button>
            <button
              type="button"
              className="sso-login__alt-link"
              onClick={handleReset}
            >
              Use a different email
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
