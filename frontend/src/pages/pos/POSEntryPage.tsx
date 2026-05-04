import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const API_BASE = '';

type FlowStep = 'start' | 'verify' | 'app';

const POSEntryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const tokenParam = searchParams.get('token');
  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;

  const [purlToken, setPurlToken] = useState<string | null>(
    tokenParam || localStorage.getItem('perennia_purl_token'),
  );
  const [flowStep, setFlowStep] = useState<FlowStep>(purlToken ? 'app' : 'start');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [phone, setPhone] = useState('');

  useEffect(() => {
    if (tokenParam) {
      localStorage.setItem('perennia_purl_token', tokenParam);
      (window as any).__PURL_TOKEN__ = tokenParam;
      setPurlToken(tokenParam);
      setFlowStep('app');
    }
  }, [tokenParam]);

  const handleAuthError = () => {
    localStorage.removeItem('perennia_purl_token');
    delete (window as any).__PURL_TOKEN__;
    setPurlToken(null);
    setFlowStep('start');
  };

  const handleStarted = (sid: string, ph: string) => {
    setSessionId(sid);
    setPhone(ph);
    setFlowStep('verify');
  };

  const handleVerified = (token: string) => {
    localStorage.setItem('perennia_purl_token', token);
    (window as any).__PURL_TOKEN__ = token;
    setPurlToken(token);
    setSearchParams({ token });
    setFlowStep('app');
  };

  if (flowStep === 'verify' && sessionId) {
    return (
      <VerifyCodeForm
        sessionId={sessionId}
        phone={phone}
        onVerified={handleVerified}
        onBack={() => setFlowStep('start')}
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


/* ─── Start Form ─────────────────────────────────────────────────── */

function StartForm({ onStarted }: { onStarted: (sessionId: string, phone: string) => void }) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
          phone: phone.trim(),
        }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to start application');
      }

      const data = await resp.json();
      onStarted(data.session_id, phone.trim());
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
          Begin your loan application in minutes. We'll send a verification
          code to your phone to get started.
        </p>

        {error && <div className="pos-start__error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="pos-start__row">
            <div className="pos-start__field">
              <label className="pos-start__label">First name</label>
              <input
                className="pos-start__input"
                value={firstName}
                onChange={e => setFirstName(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="pos-start__field">
              <label className="pos-start__label">Last name</label>
              <input
                className="pos-start__input"
                value={lastName}
                onChange={e => setLastName(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label">Email</label>
            <input
              className="pos-start__input"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label">Phone number</label>
            <input
              className="pos-start__input"
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              required
              placeholder="(555) 123-4567"
            />
            <p className="pos-start__hint">
              You'll receive a text message with a verification code.
            </p>
          </div>

          <button className="pos-start__btn" type="submit" disabled={submitting}>
            {submitting ? 'Sending code...' : 'Send Verification Code'}
          </button>
        </form>

        <p className="pos-start__footer">
          Already have a link? Check your email for your personalized access.
        </p>
      </div>
    </div>
  );
}


/* ─── Verify Code Form ───────────────────────────────────────────── */

function VerifyCodeForm({
  sessionId,
  phone,
  onVerified,
  onBack,
}: {
  sessionId: string;
  phone: string;
  onVerified: (token: string) => void;
  onBack: () => void;
}) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const maskedPhone = phone.length >= 4
    ? `(***) ***-${phone.replace(/\D/g, '').slice(-4)}`
    : phone;

  const handleDigitChange = (index: number, value: string) => {
    if (value.length > 1) value = value.slice(-1);
    if (value && !/^\d$/.test(value)) return;

    const next = [...digits];
    next[index] = value;
    setDigits(next);

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    if (next.every(d => d !== '')) {
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
      handleSubmit(pasted);
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
        body: JSON.stringify({ session_id: sessionId, code: finalCode }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Verification failed');
      }

      const data = await resp.json();
      onVerified(data.token);
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError('');
    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to resend');
      }
      setResent(true);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
      setTimeout(() => setResent(false), 5000);
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

        <h1 className="pos-start__title">Enter Verification Code</h1>
        <p className="pos-start__subtitle">
          We sent a 6-digit code to <strong>{maskedPhone}</strong>.
          Enter it below to continue.
        </p>

        {error && <div className="pos-start__error">{error}</div>}
        {resent && <div className="pos-start__success">New code sent!</div>}

        <div className="pos-start__code-row" onPaste={handlePaste}>
          {digits.map((d, i) => (
            <input
              key={i}
              ref={el => { inputRefs.current[i] = el; }}
              className="pos-start__code-input"
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={d}
              onChange={e => handleDigitChange(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              autoFocus={i === 0}
              disabled={submitting}
            />
          ))}
        </div>

        {submitting && (
          <p className="pos-start__verifying">Verifying...</p>
        )}

        <div className="pos-start__resend-row">
          <span className="pos-start__resend-label">Didn't receive a code?</span>
          <button
            type="button"
            className="pos-start__resend-btn"
            onClick={handleResend}
            disabled={resending}
          >
            {resending ? 'Sending...' : 'Resend Code'}
          </button>
        </div>

        <button
          type="button"
          className="pos-start__back-btn"
          onClick={onBack}
        >
          &larr; Back
        </button>
      </div>
    </div>
  );
}


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
    font-size: 15px; color: #6B7B75; margin: 0 0 28px;
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
    outline: none; transition: border-color 0.15s;
    box-sizing: border-box;
  }
  .pos-start__input:focus { border-color: #1F3D2E; }
  .pos-start__hint {
    font-size: 12px; color: #9CA8A2; margin: 6px 0 0;
    line-height: 1.4;
  }
  .pos-start__row { display: flex; gap: 12px; }
  .pos-start__row .pos-start__field { flex: 1; }
  .pos-start__btn {
    width: 100%; padding: 12px; border: none;
    border-radius: 10px; font-size: 15px; font-weight: 600;
    cursor: pointer; font-family: inherit;
    background: #1F3D2E; color: #F5F2E9;
    transition: background 0.15s; margin-top: 8px;
  }
  .pos-start__btn:hover { background: #2a5440; }
  .pos-start__btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .pos-start__error {
    background: #fef2f2; color: #b91c1c; padding: 10px 14px;
    border-radius: 8px; font-size: 13px; margin-bottom: 16px;
  }
  .pos-start__success {
    background: #f0fdf4; color: #15803d; padding: 10px 14px;
    border-radius: 8px; font-size: 13px; margin-bottom: 16px;
  }
  .pos-start__footer {
    text-align: center; margin-top: 20px; font-size: 13px; color: #9CA8A2;
  }

  /* Code input */
  .pos-start__code-row {
    display: flex; gap: 10px; justify-content: center;
    margin: 8px 0 24px;
  }
  .pos-start__code-input {
    width: 48px; height: 56px; text-align: center;
    font-size: 24px; font-weight: 600; font-family: inherit;
    border: 2px solid #d4d9d6; border-radius: 10px;
    outline: none; transition: border-color 0.15s;
    color: #1F3D2E;
  }
  .pos-start__code-input:focus { border-color: #1F3D2E; }
  .pos-start__code-input:disabled { background: #f8f7f4; }
  .pos-start__verifying {
    text-align: center; font-size: 14px; color: #6B7B75;
    margin: 0 0 16px;
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
    text-decoration: underline; font-family: inherit;
    padding: 0;
  }
  .pos-start__resend-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pos-start__back-btn {
    display: block; width: 100%; margin-top: 16px;
    background: none; border: 1px solid #d4d9d6;
    border-radius: 10px; padding: 10px; font-size: 14px;
    color: #6B7B75; cursor: pointer; font-family: inherit;
    transition: border-color 0.15s;
  }
  .pos-start__back-btn:hover { border-color: #1F3D2E; color: #1F3D2E; }
`;

export default POSEntryPage;
