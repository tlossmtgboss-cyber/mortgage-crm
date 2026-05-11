import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

import { API_BASE_URL } from '../../services/api';

const API_BASE = API_BASE_URL;

type FlowStep = 'checking' | 'auth' | 'verify' | 'app';
type AuthTab = 'signup' | 'login';

interface VerifySession {
  sessionId: string;
  emailMasked: string;
  expiresAt: string;
  flowType: AuthTab;
}

const SESSION_KEY = 'perennia_pos_verify';

const POSEntryPage: React.FC = () => {
  const [searchParams] = useSearchParams();

  const tokenParam = searchParams.get('token');
  const loSlug = searchParams.get('lo');
  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;

  const [purlToken, setPurlToken] = useState<string | null>(null);
  const [borrowerName, setBorrowerName] = useState(
    searchParams.get('name') || 'there',
  );

  // Recover verify session if user refreshes mid-flow
  const savedSession = useRef<VerifySession | null>(null);
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) savedSession.current = JSON.parse(raw);
  } catch {}

  const [flowStep, setFlowStep] = useState<FlowStep>(
    savedSession.current ? 'verify' : 'checking',
  );
  const [verifySession, setVerifySession] = useState<VerifySession | null>(savedSession.current);

  // On mount: validate existing token or handle URL token
  useEffect(() => {
    if (savedSession.current) return; // mid-verify, don't interfere

    const validateToken = async (token: string) => {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/pos/check-token`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
        });
        const data = await resp.json().catch(() => ({ valid: false }));
        if (data.valid) {
          localStorage.setItem('perennia_purl_token', token);
          (window as any).__PURL_TOKEN__ = token;
          setPurlToken(token);
          if (data.borrower_name) setBorrowerName(data.borrower_name);
          setFlowStep('app');
        } else {
          localStorage.removeItem('perennia_purl_token');
          delete (window as any).__PURL_TOKEN__;
          setFlowStep('auth');
        }
      } catch {
        localStorage.removeItem('perennia_purl_token');
        delete (window as any).__PURL_TOKEN__;
        setFlowStep('auth');
      }
    };

    if (tokenParam) {
      // Clean token from URL
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      window.history.replaceState({}, '', url.toString());
      validateToken(tokenParam);
    } else {
      const stored = localStorage.getItem('perennia_purl_token');
      if (stored) {
        validateToken(stored);
      } else {
        setFlowStep('auth');
      }
    }
  }, [tokenParam]);

  const handleAuthError = () => {
    localStorage.removeItem('perennia_purl_token');
    delete (window as any).__PURL_TOKEN__;
    setPurlToken(null);
    setFlowStep('auth');
  };

  const handleStarted = (session: VerifySession) => {
    setVerifySession(session);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setFlowStep('verify');
  };

  const handleVerified = (token: string, name?: string) => {
    localStorage.setItem('perennia_purl_token', token);
    (window as any).__PURL_TOKEN__ = token;
    setPurlToken(token);
    if (name) setBorrowerName(name);
    setFlowStep('app');
    sessionStorage.removeItem(SESSION_KEY);
  };

  const handleBack = () => {
    sessionStorage.removeItem(SESSION_KEY);
    setVerifySession(null);
    setFlowStep('auth');
  };

  if (flowStep === 'checking') {
    return (
      <div className="pos-start">
        <style>{styles}</style>
        <div className="pos-start__card" style={{ textAlign: 'center' }}>
          <div className="pos-start__logo">
            <PeLogoIcon />
          </div>
          <p style={{ color: '#6B7B75', fontSize: 15 }}>
            <span className="pos-start__spinner" style={{ marginRight: 8 }} />
            Loading...
          </p>
        </div>
      </div>
    );
  }

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
        borrowerName={borrowerName}
        userInitials={searchParams.get('initials') || borrowerName.charAt(0).toUpperCase()}
        onAuthError={handleAuthError}
      />
    );
  }

  return <AuthGate onStarted={handleStarted} onVerified={handleVerified} loSlug={loSlug} />;
};


/* ─── Auth Gate (Signup / Login tabs) — 4 design variants ─────────── */

type DesignVariant = 'split' | 'personal' | 'journey' | 'luxe';

function AuthGate({
  onStarted,
  onVerified,
  loSlug,
}: {
  onStarted: (session: VerifySession) => void;
  onVerified: (token: string, name?: string) => void;
  loSlug?: string | null;
}) {
  const [tab, setTab] = useState<AuthTab>('signup');
  const [variant, setVariant] = useState<DesignVariant>('split');

  const tabButtons = (
    <div className="pos-start__tabs">
      <button
        className={`pos-start__tab${tab === 'signup' ? ' active' : ''}`}
        onClick={() => setTab('signup')}
        type="button"
      >
        Create Account
      </button>
      <button
        className={`pos-start__tab${tab === 'login' ? ' active' : ''}`}
        onClick={() => setTab('login')}
        type="button"
      >
        Sign In
      </button>
    </div>
  );

  const formContent = tab === 'signup' ? (
    <SignupForm onStarted={onStarted} onSwitchToLogin={() => setTab('login')} loSlug={loSlug} />
  ) : (
    <LoginForm onStarted={onStarted} onVerified={onVerified} onSwitchToSignup={() => setTab('signup')} />
  );

  const trustBadge = (
    <div className="pos-start__trust">
      <TrustIcon />
      <span>256-bit encryption · NMLS compliant · Equal Housing Lender</span>
    </div>
  );

  const picker = (
    <div className="pos-picker">
      <span className="pos-picker__label">Design</span>
      {(['split', 'personal', 'journey', 'luxe'] as const).map((v, i) => (
        <button
          key={v}
          className={`pos-picker__btn${variant === v ? ' active' : ''}`}
          onClick={() => setVariant(v)}
          type="button"
        >
          {String.fromCharCode(65 + i)}
          <span className="pos-picker__name">
            {v === 'split' ? 'Split Hero' : v === 'personal' ? 'Personal' : v === 'journey' ? 'Journey' : 'Premium'}
          </span>
        </button>
      ))}
    </div>
  );

  /* ── A: Split-screen hero ── */
  if (variant === 'split') {
    return (
      <div className="pos-start pos-start--split">
        <style>{styles}</style>
        <div className="pos-split">
          <div className="pos-split__hero">
            <div className="pos-split__content">
              <div className="pos-split__badge">Perennia Mortgage</div>
              <h1 className="pos-split__title">Your Dream Home<br />Starts Here</h1>
              <p className="pos-split__text">
                Join thousands who've streamlined their mortgage journey
                with our AI-powered platform.
              </p>
              <div className="pos-split__features">
                <div className="pos-split__feat"><CheckCircleIcon /> Complete in under 10 minutes</div>
                <div className="pos-split__feat"><CheckCircleIcon /> AI assistant available 24/7</div>
                <div className="pos-split__feat"><CheckCircleIcon /> Real-time application updates</div>
                <div className="pos-split__feat"><CheckCircleIcon /> Bank-level 256-bit encryption</div>
              </div>
              <div className="pos-split__testimonial">
                <div className="pos-split__stars">&#9733;&#9733;&#9733;&#9733;&#9733;</div>
                <p>&ldquo;The easiest mortgage application I&rsquo;ve ever completed. Had my pre-approval in days!&rdquo;</p>
                <span className="pos-split__author">&mdash; Sarah M., First-Time Buyer</span>
              </div>
            </div>
          </div>
          <div className="pos-split__form-side">
            <div className="pos-start__card">
              <div className="pos-start__logo"><PeLogoIcon /></div>
              {tabButtons}
              {formContent}
              {trustBadge}
            </div>
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── B: Personal LO welcome ── */
  if (variant === 'personal') {
    return (
      <div className="pos-start pos-start--personal">
        <style>{styles}</style>
        <div className="pos-personal">
          <div className="pos-personal__header">
            <div className="pos-personal__avatar">TL</div>
            <h2 className="pos-personal__name">Timothy Loss</h2>
            <p className="pos-personal__role">Senior Loan Officer &middot; NMLS #123456</p>
            <blockquote className="pos-personal__quote">
              &ldquo;I&rsquo;m here to make your mortgage process simple and stress-free.
              Let&rsquo;s find the right loan for you.&rdquo;
            </blockquote>
          </div>
          <div className="pos-start__card">
            {tabButtons}
            {formContent}
            {trustBadge}
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── C: Journey / steps preview ── */
  if (variant === 'journey') {
    return (
      <div className="pos-start pos-start--journey">
        <style>{styles}</style>
        <div className="pos-journey">
          <div className="pos-journey__steps">
            {[
              { num: '1', label: 'Create\nAccount', active: true },
              { num: '2', label: 'Complete\nApplication', active: false },
              { num: '3', label: 'Schedule\nCall', active: false },
              { num: '4', label: 'Get\nApproved', active: false },
            ].map((step, i) => (
              <React.Fragment key={i}>
                {i > 0 && <div className="pos-journey__line" />}
                <div className={`pos-journey__step${step.active ? ' pos-journey__step--active' : ''}`}>
                  <div className="pos-journey__num">{step.num}</div>
                  <div className="pos-journey__label">{step.label.split('\n').map((l, j) => (
                    <React.Fragment key={j}>{j > 0 && <br />}{l}</React.Fragment>
                  ))}</div>
                </div>
              </React.Fragment>
            ))}
          </div>
          <div className="pos-start__card">
            {tabButtons}
            {formContent}
            <div className="pos-journey__estimate">
              <TimerIcon /> Most applicants complete this in under 10 minutes
            </div>
            {trustBadge}
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── D: Premium dark / luxe ── */
  return (
    <div className="pos-start pos-start--luxe">
      <style>{styles}</style>
      <div className="pos-luxe">
        <div className="pos-start__card">
          <div className="pos-luxe__badge">
            <SparkleIcon /> Exclusive Application Portal
          </div>
          <div className="pos-start__logo"><PeLogoIcon /></div>
          {tabButtons}
          {formContent}
          {trustBadge}
        </div>
        <div className="pos-luxe__features">
          <div className="pos-luxe__feat">
            <ShieldIcon />
            <span>Bank-Level<br />Security</span>
          </div>
          <div className="pos-luxe__feat-divider" />
          <div className="pos-luxe__feat">
            <SparkleIcon />
            <span>AI-Powered<br />Experience</span>
          </div>
          <div className="pos-luxe__feat-divider" />
          <div className="pos-luxe__feat">
            <TimerIcon />
            <span>10-Minute<br />Process</span>
          </div>
        </div>
      </div>
      {picker}
    </div>
  );
}


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


/* ─── Signup Form ──────────────────────────────────────────────────── */

function SignupForm({
  onStarted,
  onSwitchToLogin,
  loSlug,
}: {
  onStarted: (session: VerifySession) => void;
  onSwitchToLogin: () => void;
  loSlug?: string | null;
}) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isValid = firstName.trim() && lastName.trim() && email.trim();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setError('');
    setSubmitting(true);

    try {
      const phoneDigits = unformatPhone(phone);
      const resp = await fetch(`${API_BASE}/api/v1/pos/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          phone: phoneDigits || '',
          lo_slug: loSlug || undefined,
        }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'Failed to start application');
      }

      onStarted({
        sessionId: data.session_id,
        emailMasked: data.email_masked,
        expiresAt: data.expires_at,
        flowType: 'signup',
      });
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <h1 className="pos-start__title">Start Your Application</h1>
      <p className="pos-start__subtitle">
        Begin your mortgage application in minutes. We'll send a verification
        code to your email. Your progress saves automatically.
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
          <label className="pos-start__label" htmlFor="pos-phone">Mobile phone number <span style={{ color: '#9CA8A2', fontWeight: 400 }}>(optional)</span></label>
          <input
            id="pos-phone"
            className="pos-start__input"
            type="tel"
            value={phone}
            onChange={e => setPhone(formatPhone(e.target.value))}
            placeholder="(555) 123-4567"
            autoComplete="tel"
          />
        </div>

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
          Already have an account?{' '}
          <button type="button" className="pos-start__link-btn" onClick={onSwitchToLogin}>
            Sign in
          </button>
        </p>
      </div>
    </>
  );
}


/* ─── Login Form ───────────────────────────────────────────────────── */

function LoginForm({
  onStarted,
  onVerified,
  onSwitchToSignup,
}: {
  onStarted: (session: VerifySession) => void;
  onVerified: (token: string, name?: string) => void;
  onSwitchToSignup: () => void;
}) {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isValid = email.trim().length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setError('');
    setSubmitting(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        if (resp.status === 404) {
          throw new Error('No account found with this email address. Please create a new account.');
        }
        throw new Error(data.detail || 'Failed to sign in');
      }

      if (data.trusted_device && data.token) {
        onVerified(data.token, data.borrower_name);
        return;
      }

      onStarted({
        sessionId: data.session_id,
        emailMasked: data.email_masked,
        expiresAt: data.expires_at,
        flowType: 'login',
      });
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <h1 className="pos-start__title">Welcome Back</h1>
      <p className="pos-start__subtitle">
        Enter the email address associated with your application. We'll send a
        verification code to confirm your identity.
      </p>

      {error && <div className="pos-start__error">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="pos-start__field">
          <label className="pos-start__label" htmlFor="pos-login-email">Email address</label>
          <input
            id="pos-login-email"
            className="pos-start__input"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            autoFocus
            placeholder="you@example.com"
            autoComplete="email"
          />
        </div>

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
          Don't have an account?{' '}
          <button type="button" className="pos-start__link-btn" onClick={onSwitchToSignup}>
            Create one
          </button>
        </p>
      </div>
    </>
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
  onVerified: (token: string, name?: string) => void;
  onBack: () => void;
  onSessionUpdate: (s: VerifySession) => void;
}) {
  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [rememberDevice, setRememberDevice] = useState(false);
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
        body: JSON.stringify({
          session_id: session.sessionId,
          code: finalCode,
          remember_device: rememberDevice,
        }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'Verification failed');
      }

      onVerified(data.token, data.borrower_name);
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
          <PeLogoIcon />
        </div>

        <h1 className="pos-start__title">Verify Your Email</h1>
        <p className="pos-start__subtitle">
          We sent a 6-digit code to <strong>{session.emailMasked}</strong>.
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

        <label className="pos-start__remember">
          <input
            type="checkbox"
            checked={rememberDevice}
            onChange={e => setRememberDevice(e.target.checked)}
            className="pos-start__checkbox"
          />
          <span className="pos-start__remember-text">
            Remember this device — skip verification next time
          </span>
        </label>

        <button
          type="button"
          className="pos-start__back-btn"
          onClick={onBack}
        >
          ← Back
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

const PeLogoIcon: React.FC = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
    <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#F5F2E9" />
    <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
  </svg>
);

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

const CheckCircleIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const ShieldIcon: React.FC = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const SparkleIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0L14.59 8.41L23 11L14.59 13.59L12 22L9.41 13.59L1 11L9.41 8.41Z" />
  </svg>
);


/* ─── Shared Styles ──────────────────────────────────────────────── */

const styles = `
  /* ═══════ BASE (used by all variants + verify page) ═══════ */

  .pos-start {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #f8f7f4 0%, #eef0eb 100%);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
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
    box-sizing: border-box; color: #1F3D2E; background: #fff;
  }
  .pos-start__input:focus {
    border-color: #1F3D2E;
    box-shadow: 0 0 0 3px rgba(31,61,46,0.08);
  }
  .pos-start__row { display: flex; gap: 12px; }
  .pos-start__row .pos-start__field { flex: 1; }

  .pos-start__tabs {
    display: flex; gap: 0; margin-bottom: 24px;
    border: 1px solid #d4d9d6; border-radius: 10px;
    overflow: hidden;
  }
  .pos-start__tab {
    flex: 1; padding: 11px 16px; border: none;
    background: #f8f7f4; font-size: 14px; font-weight: 500;
    color: #6B7B75; cursor: pointer; font-family: inherit;
    transition: background 0.2s, color 0.2s;
  }
  .pos-start__tab:first-child { border-right: 1px solid #d4d9d6; }
  .pos-start__tab.active { background: #1F3D2E; color: #F5F2E9; }
  .pos-start__tab:hover:not(.active) { background: #eef0eb; }

  .pos-start__consent {
    display: flex; align-items: flex-start; gap: 10px;
    margin: 20px 0 20px; cursor: pointer;
  }
  .pos-start__checkbox {
    width: 18px; height: 18px; margin-top: 1px;
    accent-color: #1F3D2E; flex-shrink: 0; cursor: pointer;
  }
  .pos-start__consent-text { font-size: 12px; color: #6B7B75; line-height: 1.5; }

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

  .pos-start__spinner {
    display: inline-block; width: 16px; height: 16px;
    border: 2px solid rgba(245,242,233,0.3);
    border-top-color: #F5F2E9; border-radius: 50%;
    animation: pos-spin 0.6s linear infinite;
  }
  @keyframes pos-spin { to { transform: rotate(360deg); } }

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

  .pos-start__footer-links { margin-top: 20px; }
  .pos-start__footer {
    text-align: center; font-size: 13px; color: #9CA8A2; margin: 0;
  }
  .pos-start__link-btn {
    background: none; border: none; color: #1F3D2E;
    font-size: 13px; font-weight: 600; cursor: pointer;
    text-decoration: underline; font-family: inherit; padding: 0;
  }
  .pos-start__trust {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-top: 20px; padding-top: 16px;
    border-top: 1px solid #eef0eb;
    font-size: 11px; color: #b0b8b4;
  }

  .pos-start__code-row {
    display: flex; gap: 8px; justify-content: center; margin: 8px 0 24px;
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
  .pos-start__code-input.has-value { background: #f0fdf4; border-color: #86efac; }
  .pos-start__code-input:disabled { background: #f4f5f3; opacity: 0.6; }
  .pos-start__verifying {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    font-size: 14px; color: #6B7B75; margin: 0 0 16px;
  }
  .pos-start__resend-row {
    display: flex; align-items: center; justify-content: center;
    gap: 8px; margin-top: 16px;
  }
  .pos-start__resend-label { font-size: 13px; color: #9CA8A2; }
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
  .pos-start__remember {
    display: flex; align-items: center; gap: 10px;
    margin-top: 20px; cursor: pointer;
  }
  .pos-start__remember-text { font-size: 13px; color: #6B7B75; line-height: 1.4; }
  .pos-start__back-btn {
    display: block; width: 100%; margin-top: 16px;
    background: none; border: 1px solid #d4d9d6;
    border-radius: 10px; padding: 10px; font-size: 14px;
    color: #6B7B75; cursor: pointer; font-family: inherit;
    transition: border-color 0.2s, color 0.2s;
  }
  .pos-start__back-btn:hover { border-color: #1F3D2E; color: #1F3D2E; }

  @media (max-width: 480px) {
    .pos-start { padding: 16px; }
    .pos-start__card { padding: 28px 20px; }
    .pos-start__code-input { width: 42px; height: 50px; font-size: 20px; }
    .pos-start__code-row { gap: 6px; }
  }


  /* ═══════ A: SPLIT HERO ═══════ */

  .pos-start--split {
    background: #f0f2ee;
    padding: 0;
  }
  .pos-split {
    display: flex;
    width: 100%;
    min-height: 100vh;
  }
  .pos-split__hero {
    flex: 1;
    background: linear-gradient(135deg, #1a2f23 0%, #2d5a3f 50%, #1f3d2e 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 60px 48px;
    position: relative;
    overflow: hidden;
  }
  .pos-split__hero::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at 30% 70%, rgba(184,146,74,0.15) 0%, transparent 60%);
    pointer-events: none;
  }
  .pos-split__hero::after {
    content: '';
    position: absolute;
    top: -50%;
    right: -30%;
    width: 600px;
    height: 600px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(184,146,74,0.08) 0%, transparent 70%);
    pointer-events: none;
  }
  .pos-split__content {
    position: relative;
    max-width: 460px;
    color: #fff;
  }
  .pos-split__badge {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 20px;
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(8px);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #D4A853;
    margin-bottom: 28px;
    border: 1px solid rgba(212,168,83,0.2);
  }
  .pos-split__title {
    font-size: 44px;
    font-weight: 700;
    line-height: 1.12;
    margin: 0 0 20px;
    letter-spacing: -0.025em;
  }
  .pos-split__text {
    font-size: 17px;
    line-height: 1.65;
    color: rgba(255,255,255,0.7);
    margin: 0 0 36px;
  }
  .pos-split__features {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-bottom: 40px;
  }
  .pos-split__feat {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 15px;
    color: rgba(255,255,255,0.88);
  }
  .pos-split__feat svg {
    color: #D4A853;
    flex-shrink: 0;
  }
  .pos-split__testimonial {
    padding: 20px 24px;
    background: rgba(255,255,255,0.05);
    border-radius: 14px;
    border-left: 3px solid #B8924A;
  }
  .pos-split__stars {
    color: #D4A853;
    font-size: 16px;
    letter-spacing: 3px;
    margin-bottom: 10px;
  }
  .pos-split__testimonial p {
    font-size: 14.5px;
    font-style: italic;
    color: rgba(255,255,255,0.8);
    margin: 0 0 10px;
    line-height: 1.55;
  }
  .pos-split__author {
    font-size: 12px;
    color: rgba(255,255,255,0.45);
  }
  .pos-split__form-side {
    flex: 0 0 520px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 48px;
    background: #fff;
  }
  .pos-start--split .pos-start__card {
    box-shadow: none;
    max-width: 420px;
    padding: 0;
  }


  /* ═══════ B: PERSONAL LO WELCOME ═══════ */

  .pos-start--personal {
    background: linear-gradient(160deg, #f7f2e8 0%, #e8ede5 50%, #dde4d8 100%);
    position: relative;
    overflow: hidden;
  }
  .pos-start--personal::before {
    content: '';
    position: absolute;
    top: -200px;
    right: -200px;
    width: 500px;
    height: 500px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(45,90,63,0.06) 0%, transparent 70%);
    pointer-events: none;
  }
  .pos-personal {
    max-width: 480px;
    width: 100%;
    position: relative;
  }
  .pos-personal__header {
    text-align: center;
    margin-bottom: 28px;
  }
  .pos-personal__avatar {
    width: 88px;
    height: 88px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1F3D2E, #2d5a3f);
    color: #F5F2E9;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    font-weight: 600;
    margin: 0 auto 18px;
    box-shadow: 0 8px 32px rgba(31,61,46,0.2), 0 0 0 4px #fff;
    letter-spacing: 0.02em;
  }
  .pos-personal__name {
    font-size: 24px;
    font-weight: 700;
    color: #1F3D2E;
    margin: 0 0 4px;
    letter-spacing: -0.01em;
  }
  .pos-personal__role {
    font-size: 14px;
    color: #6B7B75;
    margin: 0 0 20px;
    font-weight: 500;
  }
  .pos-personal__quote {
    font-size: 15.5px;
    font-style: italic;
    color: #4a5c55;
    line-height: 1.65;
    margin: 0;
    padding: 0 8px;
    border: none;
  }
  .pos-start--personal .pos-start__card {
    border-radius: 20px;
    box-shadow: 0 12px 48px rgba(31,61,46,0.1), 0 2px 8px rgba(31,61,46,0.04);
  }
  .pos-start--personal .pos-start__logo { display: none; }


  /* ═══════ C: JOURNEY STEPS ═══════ */

  .pos-start--journey {
    background: linear-gradient(180deg, #1F3D2E 0%, #1F3D2E 200px, #f4f5f2 200px);
    flex-direction: column;
    padding-top: 0;
    gap: 0;
  }
  .pos-journey {
    max-width: 560px;
    width: 100%;
  }
  .pos-journey__steps {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 44px 20px 52px;
  }
  .pos-journey__step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }
  .pos-journey__num {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: rgba(255,255,255,0.12);
    color: rgba(255,255,255,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 17px;
    font-weight: 700;
    transition: all 0.3s ease;
  }
  .pos-journey__step--active .pos-journey__num {
    background: #D4A853;
    color: #fff;
    box-shadow: 0 0 0 5px rgba(212,168,83,0.25), 0 4px 16px rgba(212,168,83,0.3);
  }
  .pos-journey__label {
    font-size: 11.5px;
    color: rgba(255,255,255,0.4);
    text-align: center;
    line-height: 1.35;
    font-weight: 500;
  }
  .pos-journey__step--active .pos-journey__label {
    color: #fff;
    font-weight: 600;
  }
  .pos-journey__line {
    width: 52px;
    height: 2px;
    background: rgba(255,255,255,0.15);
    margin: 22px 10px 0;
    border-radius: 1px;
  }
  .pos-journey__estimate {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 16px;
    margin-top: 16px;
    background: linear-gradient(135deg, #f0fdf4, #ecfdf5);
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 500;
    color: #15803d;
  }
  .pos-start--journey .pos-start__card {
    max-width: 520px;
    margin: 0 auto;
    border-radius: 20px;
    box-shadow: 0 16px 56px rgba(31,61,46,0.12), 0 2px 8px rgba(31,61,46,0.04);
  }
  .pos-start--journey .pos-start__logo { display: none; }


  /* ═══════ D: PREMIUM DARK / LUXE ═══════ */

  .pos-start--luxe {
    background: linear-gradient(160deg, #0a0f0d 0%, #162019 40%, #0f1a15 100%);
    position: relative;
    overflow: hidden;
  }
  .pos-start--luxe::before {
    content: '';
    position: absolute;
    top: 10%;
    left: 50%;
    transform: translateX(-50%);
    width: 800px;
    height: 800px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(184,146,74,0.07) 0%, transparent 60%);
    pointer-events: none;
  }
  .pos-luxe {
    max-width: 480px;
    width: 100%;
    position: relative;
  }
  .pos-luxe__badge {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #D4A853;
    margin-bottom: 24px;
  }
  .pos-luxe__badge svg { color: #D4A853; }
  .pos-start--luxe .pos-start__card {
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 20px;
    box-shadow: 0 20px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
  }
  .pos-start--luxe .pos-start__logo {
    background: linear-gradient(135deg, #B8924A, #D4A853);
    box-shadow: 0 4px 16px rgba(184,146,74,0.25);
  }
  .pos-start--luxe .pos-start__title { color: #F5F2E9; }
  .pos-start--luxe .pos-start__subtitle { color: rgba(245,242,233,0.55); }
  .pos-start--luxe .pos-start__label { color: rgba(245,242,233,0.65); }
  .pos-start--luxe .pos-start__input {
    background: rgba(255,255,255,0.05);
    border-color: rgba(255,255,255,0.1);
    color: #F5F2E9;
  }
  .pos-start--luxe .pos-start__input:focus {
    border-color: #B8924A;
    box-shadow: 0 0 0 3px rgba(184,146,74,0.12);
  }
  .pos-start--luxe .pos-start__input::placeholder { color: rgba(245,242,233,0.25); }
  .pos-start--luxe .pos-start__tabs { border-color: rgba(255,255,255,0.1); }
  .pos-start--luxe .pos-start__tab {
    background: rgba(255,255,255,0.03);
    color: rgba(245,242,233,0.45);
  }
  .pos-start--luxe .pos-start__tab:first-child { border-right-color: rgba(255,255,255,0.1); }
  .pos-start--luxe .pos-start__tab.active {
    background: linear-gradient(135deg, #B8924A, #D4A853);
    color: #0a0f0d;
    font-weight: 600;
  }
  .pos-start--luxe .pos-start__tab:hover:not(.active) { background: rgba(255,255,255,0.06); }
  .pos-start--luxe .pos-start__btn {
    background: linear-gradient(135deg, #B8924A, #D4A853);
    color: #0a0f0d;
    font-weight: 700;
  }
  .pos-start--luxe .pos-start__btn:hover:not(:disabled) {
    background: linear-gradient(135deg, #c9a35b, #e0b964);
  }
  .pos-start--luxe .pos-start__footer { color: rgba(245,242,233,0.35); }
  .pos-start--luxe .pos-start__link-btn { color: #D4A853; }
  .pos-start--luxe .pos-start__trust {
    border-top-color: rgba(255,255,255,0.06);
    color: rgba(245,242,233,0.25);
  }
  .pos-luxe__features {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin-top: 36px;
    padding: 20px 0;
  }
  .pos-luxe__feat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 0 32px;
    color: rgba(245,242,233,0.45);
    font-size: 12px;
    text-align: center;
    line-height: 1.35;
    font-weight: 500;
  }
  .pos-luxe__feat svg { color: #D4A853; }
  .pos-luxe__feat-divider {
    width: 1px;
    height: 40px;
    background: rgba(255,255,255,0.08);
  }


  /* ═══════ DESIGN PICKER ═══════ */

  .pos-picker {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    background: rgba(10,15,13,0.92);
    backdrop-filter: blur(16px);
    border-radius: 16px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.06);
    z-index: 9999;
  }
  .pos-picker__label {
    font-size: 10px;
    font-weight: 600;
    color: rgba(255,255,255,0.4);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-right: 8px;
  }
  .pos-picker__btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 10px 16px;
    border: none;
    border-radius: 11px;
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.55);
    font-size: 17px;
    font-weight: 700;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s ease;
    border: 1px solid transparent;
  }
  .pos-picker__btn:hover {
    background: rgba(255,255,255,0.12);
    color: #fff;
  }
  .pos-picker__btn.active {
    background: linear-gradient(135deg, #B8924A, #D4A853);
    color: #0a0f0d;
    border-color: rgba(212,168,83,0.3);
    box-shadow: 0 4px 16px rgba(184,146,74,0.3);
  }
  .pos-picker__name {
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.02em;
    opacity: 0.75;
  }


  /* ═══════ RESPONSIVE ═══════ */

  @media (max-width: 960px) {
    .pos-split {
      flex-direction: column;
    }
    .pos-split__hero {
      padding: 48px 32px;
      min-height: auto;
    }
    .pos-split__title { font-size: 32px; }
    .pos-split__form-side {
      flex: none;
      padding: 32px 24px;
    }
    .pos-split__testimonial { display: none; }
  }
  @media (max-width: 480px) {
    .pos-split__features { display: none; }
    .pos-split__title { font-size: 28px; }
    .pos-split__form-side { padding: 24px 16px; }
    .pos-journey__steps { padding: 28px 8px 40px; }
    .pos-journey__line { width: 20px; margin: 22px 4px 0; }
    .pos-journey__label { font-size: 10px; }
    .pos-journey__num { width: 38px; height: 38px; font-size: 15px; }
    .pos-luxe__features { flex-wrap: wrap; gap: 16px; }
    .pos-luxe__feat-divider { display: none; }
    .pos-luxe__feat { padding: 0 16px; }
    .pos-personal__quote { padding: 0; font-size: 14px; }
    .pos-personal__avatar { width: 72px; height: 72px; font-size: 24px; }
    .pos-picker { bottom: 12px; padding: 6px 10px; gap: 4px; }
    .pos-picker__btn { padding: 8px 12px; font-size: 15px; }
    .pos-picker__name { font-size: 8px; }
    .pos-picker__label { display: none; }
  }
`;

export default POSEntryPage;