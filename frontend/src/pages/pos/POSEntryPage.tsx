import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const API_BASE = '';

type FlowStep = 'start' | 'verify' | 'app';

interface VerifySession {
  sessionId: string;
  phoneMasked: string;
  expiresAt: string;
}

const SESSION_KEY = 'perennia_pos_verify';

const POSEntryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const tokenParam = searchParams.get('token');
  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;

  const [purlToken, setPurlToken] = useState<string | null>(
    tokenParam || localStorage.getItem('perennia_purl_token'),
  );

  // Recover verify session if user refreshes mid-flow
  const savedSession = useRef<VerifySession | null>(null);
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) savedSession.current = JSON.parse(raw);
  } catch {}

  const [flowStep, setFlowStep] = useState<FlowStep>(
    purlToken ? 'app' : savedSession.current ? 'verify' : 'start',
  );
  const [verifySession, setVerifySession] = useState<VerifySession | null>(savedSession.current);

  useEffect(() => {
    if (tokenParam) {
      localStorage.setItem('perennia_purl_token', tokenParam);
      (window as any).__PURL_TOKEN__ = tokenParam;
      setPurlToken(tokenParam);
      setFlowStep('app');
      sessionStorage.removeItem(SESSION_KEY);
    }
  }, [tokenParam]);

  const handleAuthError = () => {
    localStorage.removeItem('perennia_purl_token');
    delete (window as any).__PURL_TOKEN__;
    setPurlToken(null);
    setFlowStep('start');
  };

  const handleStarted = (session: VerifySession) => {
    setVerifySession(session);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setFlowStep('verify');
  };

  const handleVerified = (token: string) => {
    localStorage.setItem('perennia_purl_token', token);
    (window as any).__PURL_TOKEN__ = token;
    setPurlToken(token);
    setSearchParams({ token });
    setFlowStep('app');
    sessionStorage.removeItem(SESSION_KEY);
  };

  const handleBack = () => {
    sessionStorage.removeItem(SESSION_KEY);
    setVerifySession(null);
    setFlowStep('start');
  };

  if (flowStep === 'verify' && verifySession) {
    return (
      <VerifyCodeForm
        session={verifySession}
        onVerified={handleVerified}
        onBack={handleBack}
        onSessionUpdate={s => {
          setVerifySession(s);
          sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
        }}
      />
    );
  }

  if (flowStep === 'app' && purlToken) {
    return (
      <POSContainer
        loanId={loanId}
        borrowerName={searchParams.get('name') || 'there'}
        userInitials={searchParams.get('initials') || ''}
        onAuthError={handleAuthError}
      />
    );
  }

  return <StartForm onStarted={handleStarted} />;
};


/* ─── Phone Formatting ───────────────────────────────────────────── */

function formatPhone(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function unformatPhone(value: string): string {
  return value.replace(/\D/g, '');
}


/* ─── Countdown Hook ─────────────────────────────────────────────── */

function useCountdown(expiresAt: string | null): { minutes: number; seconds: number; expired: boolean } {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!expiresAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  if (!expiresAt) return { minutes: 0, seconds: 0, expired: true };

  const diff = Math.max(0, new Date(expiresAt).getTime() - now);
  const totalSec = Math.floor(diff / 1000);
  return {
    minutes: Math.floor(totalSec / 60),
    seconds: totalSec % 60,
    expired: totalSec <= 0,
  };
}


/* ─── Start Form ─────────────────────────────────────────────────── */

function StartForm({ onStarted }: { onStarted: (session: VerifySession) => void }) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const phoneDigits = unformatPhone(phone);
  const isValid = firstName.trim() && lastName.trim() && email.trim() && phoneDigits.length === 10 && consent;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setError('');
    setSubmitting(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          phone: phoneDigits,
          sms_consent: true,
        }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'Failed to start application');
      }

      onStarted({
        sessionId: data.session_id,
        phoneMasked: data.phone_masked,
        expiresAt: data.expires_at,
      });
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="pos-start">
      <style>{styles}</style>

      <div className="pos-start__card">
        <div className="pos-start__logo">
          <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
            <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#F5F2E9" />
            <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
          </svg>
        </div>

        <h1 className="pos-start__title">Start Your Application</h1>
        <p className="pos-start__subtitle">
          Begin your mortgage application in minutes. Your progress saves
          automatically — step away anytime.
        </p>

        {error && <div className="pos-start__error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="pos-start__row">
            <div className="pos-start__field">
              <label className="pos-start__label" htmlFor="pos-fname">First name</label>
              <input
                id="pos-fname"
                className="pos-start__input"
                value={firstName}
                onChange={e => setFirstName(e.target.value)}
                required
                autoFocus
                autoComplete="given-name"
              />
            </div>
            <div className="pos-start__field">
              <label className="pos-start__label" htmlFor="pos-lname">Last name</label>
              <input
                id="pos-lname"
                className="pos-start__input"
                value={lastName}
                onChange={e => setLastName(e.target.value)}
                required
                autoComplete="family-name"
              />
            </div>
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label" htmlFor="pos-email">Email address</label>
            <input
              id="pos-email"
              className="pos-start__input"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label" htmlFor="pos-phone">Mobile phone number</label>
            <input
              id="pos-phone"
              className="pos-start__input"
              type="tel"
              value={phone}
              onChange={e => setPhone(formatPhone(e.target.value))}
              required
              placeholder="(555) 123-4567"
              autoComplete="tel"
            />
          </div>

          <label className="pos-start__consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={e => setConsent(e.target.checked)}
              className="pos-start__checkbox"
            />
            <span className="pos-start__consent-text">
              I agree to receive a one-time SMS verification code at the number
              provided. Message and data rates may apply.
            </span>
          </label>

          <button
            className="pos-start__btn"
            type="submit"
            disabled={submitting || !isValid}
          >
            {submitting ? (
              <span className="pos-start__btn-loading">
                <span className="pos-start__spinner" /> Sending code...
              </span>
            ) : (
              'Send Verification Code'
            )}
          </button>
        </form>

        <div className="pos-start__footer-links">
          <p className="pos-start__footer">
            Already have a link? Check your email for your personalized access.
          </p>
        </div>

        <div className="pos-start__trust">
          <TrustIcon />
          <span>256-bit encryption · NMLS compliant · Equal Housing Lender</span>
        </div>
      </div>
    </div>
  );
}


/* ─── Verify Code Form ───────────────────────────────────────────── */

function VerifyCodeForm({
  session,
  onVerified,
  onBack,
  onSessionUpdate,
}: {
  session: VerifySession;
  onVerified: (token: string) => void;
  onBack: () => void;
  onSessionUpdate: (s: VerifySession) => void;
}) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const submitGuard = useRef(false);

  const countdown = useCountdown(session.expiresAt);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const id = setInterval(() => setResendCooldown(p => Math.max(0, p - 1)), 1000);
    return () => clearInterval(id);
  }, [resendCooldown]);

  const handleDigitChange = (index: number, value: string) => {
    if (value.length > 1) value = value.slice(-1);
    if (value && !/^\d$/.test(value)) return;

    const next = [...digits];
    next[index] = value;
    setDigits(next);
    setError('');

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    if (next.every(d => d !== '') && !submitGuard.current) {
      submitGuard.current = true;
      handleSubmit(next.join(''));
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pasted.length === 6) {
      e.preventDefault();
      const next = pasted.split('');
      setDigits(next);
      inputRefs.current[5]?.focus();
      if (!submitGuard.current) {
        submitGuard.current = true;
        handleSubmit(pasted);
      }
    }
  };

  const handleSubmit = async (code?: string) => {
    const finalCode = code || digits.join('');
    if (finalCode.length !== 6) return;

    setError('');
    setSubmitting(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.sessionId, code: finalCode }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'Verification failed');
      }

      onVerified(data.token);
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } finally {
      setSubmitting(false);
      submitGuard.current = false;
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setResending(true);
    setError('');
    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.sessionId }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'Failed to resend');
      }
      setResent(true);
      setResendCooldown(data.cooldown_seconds || 60);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
      onSessionUpdate({ ...session, expiresAt: data.expires_at });
      setTimeout(() => setResent(false), 4000);
    } catch (err: any) {
      setError(err.message || 'Could not resend code');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="pos-start">
      <style>{styles}</style>

      <div className="pos-start__card">
        <div className="pos-start__logo">
          <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
            <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#F5F2E9" />
            <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
          </svg>
        </div>

        <h1 className="pos-start__title">Verify Your Phone</h1>
        <p className="pos-start__subtitle">
          We sent a 6-digit code to <strong>{session.phoneMasked}</strong>.
        </p>

        {countdown.expired ? (
          <div className="pos-start__error">
            Code expired. Please request a new one.
          </div>
        ) : (
          <div className="pos-start__timer">
            <TimerIcon />
            Code expires in {countdown.minutes}:{String(countdown.seconds).padStart(2, '0')}
          </div>
        )}

        {error && <div className="pos-start__error">{error}</div>}
        {resent && <div className="pos-start__success">New code sent!</div>}

        <div className="pos-start__code-row" onPaste={handlePaste}>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={el => { inputRefs.current[i] = el; }}
              className={`pos-start__code-input${d ? ' has-value' : ''}`}
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={1}
              value={d}
              onChange={e => handleDigitChange(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              autoFocus={i === 0}
              disabled={submitting || countdown.expired}
              aria-label={`Digit ${i + 1} of 6`}
            />
          ))}
        </div>

        {submitting && (
          <p className="pos-start__verifying">
            <span className="pos-start__spinner" /> Verifying...
          </p>
        )}

        <div className="pos-start__resend-row">
          <span className="pos-start__resend-label">Didn't receive a code?</span>
          {resendCooldown > 0 ? (
            <span className="pos-start__resend-wait">
              Resend in {resendCooldown}s
            </span>
          ) : (
            <button
              type="button"
              className="pos-start__resend-btn"
              onClick={handleResend}
              disabled={resending}
            >
              {resending ? 'Sending...' : 'Resend Code'}
            </button>
          )}
        </div>

        <button
          type="button"
          className="pos-start__back-btn"
          onClick={onBack}
        >
          ← Use a different number
        </button>

        <div className="pos-start__trust">
          <TrustIcon />
          <span>256-bit encryption · NMLS compliant · Equal Housing Lender</span>
        </div>
      </div>
    </div>
  );
}


/* ─── Icons ──────────────────────────────────────────────────────── */

const TrustIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

const TimerIcon: React.FC = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
  </svg>
);


/* ─── Shared Styles ──────────────────────────────────────────────── */

const styles = `
  .pos-start {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #f8f7f4 0%, #eef0eb 100%);
    font-family: system-ui, -apple-system, sans-serif;
    padding: 24px;
  }
  .pos-start__card {
    width: 100%;
    max-width: 440px;
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 4px 24px rgba(31,61,46,0.08);
    padding: 40px;
  }
  .pos-start__logo {
    width: 48px; height: 48px; border-radius: 12px;
    background: #1F3D2E; display: flex;
    align-items: center; justify-content: center;
    margin-bottom: 24px;
  }
  .pos-start__title {
    font-size: 24px; font-weight: 600; color: #1F3D2E;
    margin: 0 0 6px;
  }
  .pos-start__subtitle {
    font-size: 15px; color: #6B7B75; margin: 0 0 24px;
    line-height: 1.5;
  }
  .pos-start__field { margin-bottom: 16px; }
  .pos-start__label {
    display: block; font-size: 13px; font-weight: 500;
    color: #1F3D2E; margin-bottom: 6px;
  }
  .pos-start__input {
    width: 100%; padding: 10px 14px; border: 1px solid #d4d9d6;
    border-radius: 8px; font-size: 15px; font-family: inherit;
    outline: none; transition: border-color 0.2s, box-shadow 0.2s;
    box-sizing: border-box; color: #1F3D2E;
  }
  .pos-start__input:focus {
    border-color: #1F3D2E;
    box-shadow: 0 0 0 3px rgba(31,61,46,0.08);
  }
  .pos-start__row { display: flex; gap: 12px; }
  .pos-start__row .pos-start__field { flex: 1; }

  /* Consent checkbox */
  .pos-start__consent {
    display: flex; align-items: flex-start; gap: 10px;
    margin: 20px 0 20px; cursor: pointer;
  }
  .pos-start__checkbox {
    width: 18px; height: 18px; margin-top: 1px;
    accent-color: #1F3D2E; flex-shrink: 0; cursor: pointer;
  }
  .pos-start__consent-text {
    font-size: 12px; color: #6B7B75; line-height: 1.5;
  }

  /* Primary button */
  .pos-start__btn {
    width: 100%; padding: 13px; border: none;
    border-radius: 10px; font-size: 15px; font-weight: 600;
    cursor: pointer; font-family: inherit;
    background: #1F3D2E; color: #F5F2E9;
    transition: background 0.2s, opacity 0.2s, transform 0.1s;
  }
  .pos-start__btn:hover:not(:disabled) { background: #2a5440; }
  .pos-start__btn:active:not(:disabled) { transform: scale(0.99); }
  .pos-start__btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pos-start__btn-loading {
    display: flex; align-items: center; justify-content: center; gap: 8px;
  }

  /* Spinner */
  .pos-start__spinner {
    display: inline-block; width: 16px; height: 16px;
    border: 2px solid rgba(245,242,233,0.3);
    border-top-color: #F5F2E9; border-radius: 50%;
    animation: pos-spin 0.6s linear infinite;
  }
  @keyframes pos-spin { to { transform: rotate(360deg); } }

  /* Messages */
  .pos-start__error {
    background: #fef2f2; color: #b91c1c; padding: 10px 14px;
    border-radius: 8px; font-size: 13px; margin-bottom: 16px;
    border: 1px solid #fecaca;
  }
  .pos-start__success {
    background: #f0fdf4; color: #15803d; padding: 10px 14px;
    border-radius: 8px; font-size: 13px; margin-bottom: 16px;
    border: 1px solid #bbf7d0;
  }
  .pos-start__timer {
    display: flex; align-items: center; gap: 6px;
    background: #fefce8; color: #854d0e; padding: 10px 14px;
    border-radius: 8px; font-size: 13px; font-weight: 500;
    margin-bottom: 16px; border: 1px solid #fef08a;
  }

  /* Footer */
  .pos-start__footer-links { margin-top: 20px; }
  .pos-start__footer {
    text-align: center; font-size: 13px; color: #9CA8A2; margin: 0;
  }
  .pos-start__trust {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-top: 20px; padding-top: 16px;
    border-top: 1px solid #eef0eb;
    font-size: 11px; color: #b0b8b4;
  }

  /* Code input */
  .pos-start__code-row {
    display: flex; gap: 8px; justify-content: center;
    margin: 8px 0 24px;
  }
  .pos-start__code-input {
    width: 48px; height: 56px; text-align: center;
    font-size: 24px; font-weight: 600; font-family: inherit;
    border: 2px solid #d4d9d6; border-radius: 10px;
    outline: none; transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
    color: #1F3D2E; background: #fff;
  }
  .pos-start__code-input:focus {
    border-color: #1F3D2E;
    box-shadow: 0 0 0 3px rgba(31,61,46,0.08);
  }
  .pos-start__code-input.has-value {
    background: #f0fdf4; border-color: #86efac;
  }
  .pos-start__code-input:disabled { background: #f4f5f3; opacity: 0.6; }
  .pos-start__verifying {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    font-size: 14px; color: #6B7B75; margin: 0 0 16px;
  }
  .pos-start__resend-row {
    display: flex; align-items: center; justify-content: center;
    gap: 8px; margin-top: 16px;
  }
  .pos-start__resend-label {
    font-size: 13px; color: #9CA8A2;
  }
  .pos-start__resend-btn {
    background: none; border: none; color: #1F3D2E;
    font-size: 13px; font-weight: 600; cursor: pointer;
    text-decoration: underline; font-family: inherit; padding: 0;
  }
  .pos-start__resend-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pos-start__resend-wait {
    font-size: 13px; color: #9CA8A2; font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .pos-start__back-btn {
    display: block; width: 100%; margin-top: 16px;
    background: none; border: 1px solid #d4d9d6;
    border-radius: 10px; padding: 10px; font-size: 14px;
    color: #6B7B75; cursor: pointer; font-family: inherit;
    transition: border-color 0.2s, color 0.2s;
  }
  .pos-start__back-btn:hover { border-color: #1F3D2E; color: #1F3D2E; }

  /* Mobile */
  @media (max-width: 480px) {
    .pos-start { padding: 16px; }
    .pos-start__card { padding: 28px 20px; }
    .pos-start__code-input { width: 42px; height: 50px; font-size: 20px; }
    .pos-start__code-row { gap: 6px; }
  }
`;

export default POSEntryPage;
