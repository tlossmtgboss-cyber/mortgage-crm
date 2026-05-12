import React, { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

const POSContainer = React.lazy(() =>
  import('../../features/pos').then(m => ({ default: m.POSContainer }))
);

import { API_BASE_URL } from '../../services/api';
import './pos-entry.css';

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
      <Suspense fallback={
        <div className="pos-start">
          <div className="pos-start__card" style={{ textAlign: 'center' }}>
            <span className="pos-start__spinner" />
          </div>
        </div>
      }>
        <POSContainer
          loanId={loanId}
          borrowerName={borrowerName}
          userInitials={searchParams.get('initials') || borrowerName.charAt(0).toUpperCase()}
          onAuthError={handleAuthError}
        />
      </Suspense>
    );
  }

  return <AuthGate onStarted={handleStarted} onVerified={handleVerified} loSlug={loSlug} />;
};


/* ─── Auth Gate (Signup / Login tabs) — 4 design variants ─────────── */

type DesignVariant = 'split' | 'personal' | 'journey' | 'luxe' | 'coastal' | 'warm' | 'slate' | 'classic';

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

  const VARIANT_NAMES: Record<DesignVariant, string> = {
    split: 'Split Hero',
    personal: 'Personal',
    journey: 'Journey',
    luxe: 'Premium',
    coastal: 'Coastal',
    warm: 'Warm',
    slate: 'Slate',
    classic: 'Classic',
  };

  const ALL_VARIANTS: DesignVariant[] = ['split', 'personal', 'journey', 'luxe', 'coastal', 'warm', 'slate', 'classic'];

  const showPicker = process.env.NODE_ENV === 'development' || new URLSearchParams(window.location.search).has('design');

  const picker = showPicker ? (
    <div className="pos-picker">
      <span className="pos-picker__label">Design</span>
      {ALL_VARIANTS.map((v, i) => (
        <button
          key={v}
          className={`pos-picker__btn${variant === v ? ' active' : ''}`}
          onClick={() => setVariant(v)}
          type="button"
        >
          {String.fromCharCode(65 + i)}
          <span className="pos-picker__name">{VARIANT_NAMES[v]}</span>
        </button>
      ))}
    </div>
  ) : null;

  /* ── A: Split-screen hero ── */
  if (variant === 'split') {
    return (
      <div className="pos-start pos-start--split">

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

  /* ── E: Coastal / ocean theme ── */
  if (variant === 'coastal') {
    return (
      <div className="pos-start pos-start--coastal">

        <div className="pos-coastal">
          <div className="pos-coastal__header">
            <div className="pos-coastal__wave" />
            <div className="pos-coastal__badge">Begin Your Journey Home</div>
            <h1 className="pos-coastal__title">Mortgage Made<br />Simple</h1>
            <p className="pos-coastal__text">
              Clear waters, clear process. Apply in minutes with
              guidance every step of the way.
            </p>
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

  /* ── F: Warm / terracotta ── */
  if (variant === 'warm') {
    return (
      <div className="pos-start pos-start--warm">

        <div className="pos-warm">
          <div className="pos-warm__hero">
            <div className="pos-warm__content">
              <div className="pos-warm__icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
                </svg>
              </div>
              <h1 className="pos-warm__title">Welcome Home</h1>
              <p className="pos-warm__text">
                Your path to homeownership starts with a simple, guided application.
                We'll walk through everything together.
              </p>
              <div className="pos-warm__stats">
                <div className="pos-warm__stat">
                  <span className="pos-warm__stat-num">10</span>
                  <span className="pos-warm__stat-label">Min to apply</span>
                </div>
                <div className="pos-warm__stat-divider" />
                <div className="pos-warm__stat">
                  <span className="pos-warm__stat-num">24/7</span>
                  <span className="pos-warm__stat-label">AI support</span>
                </div>
                <div className="pos-warm__stat-divider" />
                <div className="pos-warm__stat">
                  <span className="pos-warm__stat-num">100%</span>
                  <span className="pos-warm__stat-label">Secure</span>
                </div>
              </div>
            </div>
          </div>
          <div className="pos-warm__form-side">
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

  /* ── G: Slate / professional ── */
  if (variant === 'slate') {
    return (
      <div className="pos-start pos-start--slate">

        <div className="pos-slate">
          <div className="pos-slate__topbar">
            <div className="pos-start__logo"><PeLogoIcon /></div>
            <span className="pos-slate__topbar-text">Perennia Mortgage</span>
          </div>
          <div className="pos-slate__body">
            <div className="pos-start__card">
              {tabButtons}
              {formContent}
              {trustBadge}
            </div>
            <div className="pos-slate__sidebar">
              <h3 className="pos-slate__sidebar-title">Why apply with us?</h3>
              <div className="pos-slate__sidebar-items">
                <div className="pos-slate__sidebar-item">
                  <div className="pos-slate__sidebar-icon"><CheckCircleIcon /></div>
                  <div>
                    <strong>Competitive Rates</strong>
                    <p>Access to a wide range of loan products and pricing.</p>
                  </div>
                </div>
                <div className="pos-slate__sidebar-item">
                  <div className="pos-slate__sidebar-icon"><CheckCircleIcon /></div>
                  <div>
                    <strong>Fast Pre-Approval</strong>
                    <p>Get your pre-approval letter in as little as 24 hours.</p>
                  </div>
                </div>
                <div className="pos-slate__sidebar-item">
                  <div className="pos-slate__sidebar-icon"><CheckCircleIcon /></div>
                  <div>
                    <strong>Dedicated Support</strong>
                    <p>Your loan officer and AI assistant are always available.</p>
                  </div>
                </div>
                <div className="pos-slate__sidebar-item">
                  <div className="pos-slate__sidebar-icon"><ShieldIcon /></div>
                  <div>
                    <strong>Bank-Level Security</strong>
                    <p>256-bit encryption protects your information.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── H: Classic / navy traditional ── */
  if (variant === 'classic') {
    return (
      <div className="pos-start pos-start--classic">

        <div className="pos-classic">
          <div className="pos-classic__header">
            <div className="pos-classic__logo-row">
              <div className="pos-start__logo"><PeLogoIcon /></div>
              <span className="pos-classic__brand">Perennia</span>
            </div>
            <div className="pos-classic__headline">
              <h1 className="pos-classic__title">Apply for Your Mortgage</h1>
              <p className="pos-classic__subtitle">
                Trusted by borrowers nationwide. Complete your application securely in minutes.
              </p>
            </div>
          </div>
          <div className="pos-classic__card-wrap">
            <div className="pos-start__card">
              {tabButtons}
              {formContent}
            </div>
          </div>
          <div className="pos-classic__footer">
            <div className="pos-classic__footer-items">
              <span><TrustIcon /> NMLS Licensed</span>
              <span className="pos-classic__footer-dot">&middot;</span>
              <span><ShieldIcon /> 256-bit Encrypted</span>
              <span className="pos-classic__footer-dot">&middot;</span>
              <span>Equal Housing Lender</span>
            </div>
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── D: Premium dark / luxe ── */
  return (
    <div className="pos-start pos-start--luxe">

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
              disabled={submitting || countdown.expired}
              aria-label={`Digit ${i + 1} of 6`}
              {...(i === 0 ? { autoComplete: 'one-time-code' } : {})}
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


export default POSEntryPage;
