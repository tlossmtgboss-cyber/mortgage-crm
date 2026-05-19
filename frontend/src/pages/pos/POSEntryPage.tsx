import React, { Suspense, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../services/api';
import { setPurlToken as setApiPurlToken } from '../../features/pos/api/client';
import './pos-entry.css';

const POSContainer = React.lazy(() =>
  import('../../features/pos').then(m => ({ default: m.POSContainer }))
);

const API_BASE = API_BASE_URL;

interface LOProfile {
  name: string;
  title: string | null;
  headshot_url: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  nmls: string | null;
  company_logo_url: string | null;
  tagline: string | null;
  schedule_url: string | null;
}

type FlowStep = 'checking' | 'auth' | 'verify' | 'app';
type AuthTab = 'signup' | 'login';

interface VerifySession {
  sessionId: string;
  emailMasked: string;
  expiresAt: string;
  flowType: AuthTab;
}

const SESSION_KEY = 'perennia_pos_verify';
const SIGNUP_DRAFT_KEY = 'perennia_pos_signup_draft';

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
  const [loProfile, setLoProfile] = useState<LOProfile | null>(null);

  useEffect(() => {
    if (!loSlug) return;
    fetch(`${API_BASE}/api/v1/pos/lo-profile/${encodeURIComponent(loSlug)}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setLoProfile(data); })
      .catch((err) => { console.error('Failed to load LO profile:', err); });
  }, [loSlug]);

  // Recover verify session if user refreshes mid-flow
  const savedSession = useRef<VerifySession | null>(null);
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) savedSession.current = JSON.parse(raw);
  } catch (err) { console.error('Failed to parse saved verify session:', err); }

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
          setApiPurlToken(token);
          setPurlToken(token);
          if (data.borrower_name) setBorrowerName(data.borrower_name);
          setFlowStep('app');
        } else {
          localStorage.removeItem('perennia_purl_token');
          setApiPurlToken(null);
          setPurlToken(null);
          setFlowStep('auth');
        }
      } catch (err) {
        console.error('Token validation failed:', err);
        localStorage.removeItem('perennia_purl_token');
        setApiPurlToken(null);
        setPurlToken(null);
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

  const [authBounceError, setAuthBounceError] = useState<string | null>(null);

  const handleAuthError = () => {
    localStorage.removeItem('perennia_purl_token');
    setApiPurlToken(null);
    setPurlToken(null);
    setAuthBounceError(
      "We couldn't open your application. Your details below are saved — please try again, or contact your loan officer if this keeps happening.",
    );
    setFlowStep('auth');
  };

  const handleStarted = (session: VerifySession) => {
    setVerifySession(session);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    setFlowStep('verify');
  };

  const handleVerified = (token: string, name?: string) => {
    localStorage.setItem('perennia_purl_token', token);
    setApiPurlToken(token);
    setPurlToken(token);
    if (name) setBorrowerName(name);
    setAuthBounceError(null);
    setFlowStep('app');
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SIGNUP_DRAFT_KEY);
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

  return (
    <AuthGate
      onStarted={handleStarted}
      onVerified={handleVerified}
      loSlug={loSlug}
      loProfile={loProfile}
      bounceError={authBounceError}
      onClearBounceError={() => setAuthBounceError(null)}
    />
  );
};


/* ─── Auth Gate (Signup / Login tabs) — 4 design variants ─────────── */

type DesignVariant = 'split' | 'social' | 'conversational' | 'dashboard' | 'rate' | 'minimal' | 'personal' | 'timeline';

function AuthGate({
  onStarted,
  onVerified,
  loSlug,
  loProfile,
  bounceError,
  onClearBounceError,
}: {
  onStarted: (session: VerifySession) => void;
  onVerified: (token: string, name?: string) => void;
  loSlug?: string | null;
  loProfile?: LOProfile | null;
  bounceError?: string | null;
  onClearBounceError?: () => void;
}) {
  const [tab, setTab] = useState<AuthTab>('signup');
  const [variant, setVariant] = useState<DesignVariant>('conversational');

  useEffect(() => {
    if (loProfile && variant === 'conversational') setVariant('conversational');
  }, [loProfile]);

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
    <SignupForm
      onStarted={onStarted}
      onVerified={onVerified}
      onSwitchToLogin={() => setTab('login')}
      loSlug={loSlug}
      bounceError={bounceError ?? null}
      onClearBounceError={onClearBounceError}
    />
  ) : (
    <LoginForm onStarted={onStarted} onVerified={onVerified} onSwitchToSignup={() => setTab('signup')} />
  );

  const trustBadge = (
    <div className="pos-start__trust">
      <TrustIcon />
      <span>256-bit encryption · NMLS compliant · Equal Housing Lender</span>
    </div>
  );

  const VARIANT_META: Record<DesignVariant, { label: string; icon: string }> = {
    personal:      { label: 'My LO',       icon: '👤' },
    split:         { label: 'Hero',        icon: '◧' },
    social:        { label: 'Proof',       icon: '★' },
    rate:          { label: 'Rates',       icon: '↘' },
    conversational:{ label: 'Chat',        icon: '💬' },
    minimal:       { label: 'Clean',       icon: '◻' },
    dashboard:     { label: 'Preview',     icon: '▦' },
    timeline:      { label: 'Steps',       icon: '⋮' },
  };

  const VARIANT_ORDER: DesignVariant[] = ['conversational', 'split', 'social', 'rate', 'personal', 'minimal', 'dashboard', 'timeline'];

  const showPicker = process.env.NODE_ENV === 'development' || new URLSearchParams(window.location.search).has('design');

  const picker = showPicker ? (
    <div className="pos-picker" role="toolbar" aria-label="Design variant picker">
      <span className="pos-picker__label">Layout</span>
      {VARIANT_ORDER.map(v => {
        const meta = VARIANT_META[v];
        const isActive = variant === v;
        return (
          <button
            key={v}
            className={`pos-picker__btn${isActive ? ' pos-picker__btn--active' : ''}`}
            onClick={() => setVariant(v)}
            type="button"
            aria-pressed={isActive}
            title={meta.label}
          >
            <span className="pos-picker__icon">{meta.icon}</span>
            <span className="pos-picker__name">{meta.label}</span>
          </button>
        );
      })}
    </div>
  ) : null;

  /* ── A: Split Hero ── */
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

  /* ── B: Social Proof ── */
  if (variant === 'social') {
    return (
      <div className="pos-start pos-start--social">
        <div className="pos-social">
          <div className="pos-social__stats">
            <div className="pos-social__stat">
              <span className="pos-social__stat-num">2,500+</span>
              <span className="pos-social__stat-label">Loans Closed</span>
            </div>
            <div className="pos-social__stat-divider" />
            <div className="pos-social__stat">
              <span className="pos-social__stat-num">4.9<span className="pos-social__star">&#9733;</span></span>
              <span className="pos-social__stat-label">Borrower Rating</span>
            </div>
            <div className="pos-social__stat-divider" />
            <div className="pos-social__stat">
              <span className="pos-social__stat-num">10 min</span>
              <span className="pos-social__stat-label">Avg. Application</span>
            </div>
          </div>

          <div className="pos-social__testimonials">
            <div className="pos-social__testimonial">
              <div className="pos-social__avatar">SM</div>
              <div className="pos-social__quote">&ldquo;Closed on our first home in 28 days. The AI kept us informed every step.&rdquo;</div>
              <div className="pos-social__author">Sarah M. &middot; First-Time Buyer</div>
            </div>
            <div className="pos-social__testimonial">
              <div className="pos-social__avatar">JR</div>
              <div className="pos-social__quote">&ldquo;Refinanced and saved $340/mo. The process was shockingly simple.&rdquo;</div>
              <div className="pos-social__author">James R. &middot; Refinance</div>
            </div>
            <div className="pos-social__testimonial">
              <div className="pos-social__avatar">KP</div>
              <div className="pos-social__quote">&ldquo;Pre-approved in 24 hours. My realtor couldn&rsquo;t believe how fast it was.&rdquo;</div>
              <div className="pos-social__author">Kim P. &middot; Purchase</div>
            </div>
          </div>

          <div className="pos-social__form-wrap">
            <h2 className="pos-social__cta">Join them. Start your application.</h2>
            <div className="pos-start__card">
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

  /* ── C: Conversational — primary landing page ── */
  if (variant === 'conversational') {
    const lo = loProfile;
    const initials = lo?.name
      ? lo.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
      : 'LO';
    const displayName = lo?.name || 'Your Loan Officer';
    const nmlsLine = [lo?.nmls ? `NMLS #${lo.nmls}` : null, lo?.title].filter(Boolean).join(' · ');

    return (
      <div className="pos-start pos-start--convo">
        {/* Top bar: company logo left, LO info right */}
        <header className="pos-convo__topbar">
          <div className="pos-convo__logo-area">
            {lo?.company_logo_url ? (
              <img src={lo.company_logo_url} alt="Company" className="pos-convo__company-logo" />
            ) : (
              <div className="pos-convo__logo-fallback"><PeLogoIcon /></div>
            )}
          </div>
          {lo && (
            <div className="pos-convo__lo-bar">
              {lo.headshot_url ? (
                <img src={lo.headshot_url} alt={displayName} className="pos-convo__lo-avatar pos-convo__lo-avatar--img" />
              ) : (
                <div className="pos-convo__lo-avatar">{initials}</div>
              )}
              <div className="pos-convo__lo-info">
                <span className="pos-convo__lo-name">{displayName}</span>
                {nmlsLine && <span className="pos-convo__lo-detail">{nmlsLine}</span>}
              </div>
              {lo.phone && (
                <a href={`tel:${lo.phone.replace(/\D/g, '')}`} className="pos-convo__lo-action">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" /></svg>
                  {lo.phone}
                </a>
              )}
              {lo.email && (
                <a href={`mailto:${lo.email}`} className="pos-convo__lo-action">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
                  {lo.email}
                </a>
              )}
            </div>
          )}
        </header>

        {/* Main form area */}
        <div className="pos-convo__body">
          <h1 className="pos-convo__headline">
            Let&rsquo;s find your home<span className="pos-convo__cursor">|</span>
          </h1>
          <p className="pos-convo__sub">No complicated forms. Just a few quick steps to get started.</p>
          <div className="pos-convo__bubble">
            <div className="pos-convo__bubble-arrow" />
            <div className="pos-start__card">
              {tabButtons}
              {formContent}
              {trustBadge}
            </div>
          </div>
        </div>

        {/* Compliance footer */}
        <footer className="pos-convo__footer">
          <div className="pos-convo__compliance">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
            <span>256-bit encryption · NMLS compliant · Equal Housing Lender</span>
            <svg className="pos-convo__ehl" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3L4 9v12h16V9l-8-6zm0 2.2L18 10v9H6v-9l6-4.8zM11 13h2v4h-2v-4zm0-3h2v2h-2v-2z"/></svg>
          </div>
          {lo?.address && <p className="pos-convo__address">{lo.address}</p>}
          {lo?.nmls && <p className="pos-convo__nmls-footer">NMLS #{lo.nmls}</p>}
        </footer>

        {picker}
      </div>
    );
  }

  /* ── D: Dashboard Preview ── */
  if (variant === 'dashboard') {
    return (
      <div className="pos-start pos-start--dash">
        <div className="pos-dash__bg">
          <div className="pos-dash__sidebar-mock">
            <div className="pos-dash__sb-logo" />
            <div className="pos-dash__sb-item pos-dash__sb-item--active" />
            <div className="pos-dash__sb-item" />
            <div className="pos-dash__sb-item" />
            <div className="pos-dash__sb-item" />
            <div className="pos-dash__sb-item" />
          </div>
          <div className="pos-dash__main-mock">
            <div className="pos-dash__topbar-mock">
              <div className="pos-dash__tb-search" />
              <div className="pos-dash__tb-avatar" />
            </div>
            <div className="pos-dash__cards-mock">
              <div className="pos-dash__card-mock">
                <div className="pos-dash__cm-title" />
                <div className="pos-dash__cm-bar" />
                <div className="pos-dash__cm-bar pos-dash__cm-bar--short" />
              </div>
              <div className="pos-dash__card-mock">
                <div className="pos-dash__cm-title" />
                <div className="pos-dash__cm-chart" />
              </div>
              <div className="pos-dash__card-mock">
                <div className="pos-dash__cm-title" />
                <div className="pos-dash__cm-rows">
                  <div className="pos-dash__cm-row" />
                  <div className="pos-dash__cm-row" />
                  <div className="pos-dash__cm-row" />
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="pos-dash__overlay">
          <h1 className="pos-dash__title">Your dashboard is ready</h1>
          <p className="pos-dash__sub">Track your loan, upload documents, and message your loan officer — all in one place.</p>
          <div className="pos-start__card">
            <div className="pos-start__logo"><PeLogoIcon /></div>
            {tabButtons}
            {formContent}
            {trustBadge}
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── E: Rate Teaser ── */
  if (variant === 'rate') {
    return (
      <div className="pos-start pos-start--rate">
        <div className="pos-rate">
          <div className="pos-rate__hero">
            <div className="pos-rate__hero-content">
              <div className="pos-rate__label">Today&rsquo;s Rates</div>
              <div className="pos-rate__number">6.25<span className="pos-rate__pct">%</span></div>
              <div className="pos-rate__details">Purchase &middot; 30yr Fixed &middot; 740+ FICO</div>
              <div className="pos-rate__ticker">
                <TimerIcon /> Updated 2 min ago
              </div>
              <div className="pos-rate__other-rates">
                <div className="pos-rate__other">
                  <span className="pos-rate__other-type">15yr Fixed</span>
                  <span className="pos-rate__other-num">5.75%</span>
                </div>
                <div className="pos-rate__other-divider" />
                <div className="pos-rate__other">
                  <span className="pos-rate__other-type">FHA 30yr</span>
                  <span className="pos-rate__other-num">5.99%</span>
                </div>
                <div className="pos-rate__other-divider" />
                <div className="pos-rate__other">
                  <span className="pos-rate__other-type">VA 30yr</span>
                  <span className="pos-rate__other-num">5.50%</span>
                </div>
              </div>
            </div>
          </div>
          <div className="pos-rate__form-wrap">
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

  /* ── F: Minimal ── */
  if (variant === 'minimal') {
    return (
      <div className="pos-start pos-start--minimal">
        <div className="pos-minimal">
          <div className="pos-start__logo"><PeLogoIcon /></div>
          <p className="pos-minimal__tagline">Apply for your mortgage. It takes 10 minutes.</p>
          <div className="pos-start__card">
            {tabButtons}
            {formContent}
          </div>
          <div className="pos-minimal__footer">
            <TrustIcon /> <span>256-bit encryption &middot; NMLS compliant</span>
          </div>
        </div>
        {picker}
      </div>
    );
  }

  /* ── G: Personal — data from CRM signature ── */
  if (variant === 'personal') {
    const lo = loProfile;
    const initials = lo?.name
      ? lo.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
      : 'LO';
    const displayName = lo?.name || 'Your Loan Officer';
    const nmlsLine = [lo?.nmls ? `NMLS #${lo.nmls}` : null, lo?.title].filter(Boolean).join(' · ');

    return (
      <div className="pos-start pos-start--personal">
        <div className="pos-personal">
          <div className="pos-personal__header">
            {lo?.headshot_url ? (
              <img src={lo.headshot_url} alt={displayName} className="pos-personal__photo pos-personal__photo--img" />
            ) : (
              <div className="pos-personal__photo">{initials}</div>
            )}
            <h1 className="pos-personal__name">Apply with {displayName}</h1>
            {nmlsLine && <p className="pos-personal__nmls">{nmlsLine}</p>}
            {lo?.tagline && (
              <blockquote className="pos-personal__quote">
                &ldquo;{lo.tagline}&rdquo;
              </blockquote>
            )}
            <div className="pos-personal__contact">
              {lo?.phone && (
                <a href={`tel:${lo.phone.replace(/\D/g, '')}`} className="pos-personal__contact-item">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" /></svg>
                  {lo.phone}
                </a>
              )}
              {lo?.email && (
                <a href={`mailto:${lo.email}`} className="pos-personal__contact-item">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
                  {lo.email}
                </a>
              )}
              {lo?.address && (
                <span className="pos-personal__contact-item pos-personal__contact-item--address">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
                  {lo.address}
                </span>
              )}
            </div>
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

  /* ── H: Milestone Timeline ── */
  return (
    <div className="pos-start pos-start--timeline">
      <div className="pos-timeline">
        <div className="pos-timeline__track">
          <div className="pos-timeline__line" />
          {[
            { icon: 'account', label: 'Create Account', desc: 'Quick sign-up with email verification', active: true },
            { icon: 'form', label: 'Complete Application', desc: 'AI-guided questions, auto-save progress', active: false },
            { icon: 'check', label: 'Get Pre-Approved', desc: 'Receive your pre-approval letter', active: false },
            { icon: 'home', label: 'Close on Your Home', desc: 'We handle the rest through closing day', active: false },
          ].map((step, i) => (
            <div key={i} className={`pos-timeline__milestone${step.active ? ' pos-timeline__milestone--active' : ''}`}>
              <div className="pos-timeline__dot">
                {step.icon === 'account' && (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                )}
                {step.icon === 'form' && (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg>
                )}
                {step.icon === 'check' && <CheckCircleIcon />}
                {step.icon === 'home' && (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>
                )}
              </div>
              <div className="pos-timeline__text">
                <div className="pos-timeline__label">{step.label}</div>
                <div className="pos-timeline__desc">{step.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="pos-timeline__form-area">
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
  onVerified,
  onSwitchToLogin,
  loSlug,
  bounceError,
  onClearBounceError,
}: {
  onStarted: (session: VerifySession) => void;
  onVerified: (token: string, name?: string) => void;
  onSwitchToLogin: () => void;
  loSlug?: string | null;
  bounceError?: string | null;
  onClearBounceError?: () => void;
}) {
  // Hydrate from sessionStorage so values survive a bounce back from a failed
  // post-signup auth (POSContainer can unmount this form via onAuthError).
  const draft = (() => {
    try {
      const raw = sessionStorage.getItem(SIGNUP_DRAFT_KEY);
      if (raw) return JSON.parse(raw) as { firstName?: string; lastName?: string; email?: string; phone?: string };
    } catch { /* ignore parse error */ }
    return {} as { firstName?: string; lastName?: string; email?: string; phone?: string };
  })();

  const [firstName, setFirstName] = useState(draft.firstName || '');
  const [lastName, setLastName] = useState(draft.lastName || '');
  const [email, setEmail] = useState(draft.email || '');
  const [phone, setPhone] = useState(draft.phone || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    try {
      sessionStorage.setItem(
        SIGNUP_DRAFT_KEY,
        JSON.stringify({ firstName, lastName, email, phone }),
      );
    } catch { /* storage full or disabled — fine */ }
  }, [firstName, lastName, email, phone]);

  const isValid = firstName.trim() && lastName.trim() && email.trim();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setError('');
    onClearBounceError?.();
    setSubmitting(true);

    try {
      const phoneDigits = unformatPhone(phone);
      const resp = await fetch(`${API_BASE}/api/v1/pos/start-demo`, {
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

      onVerified(data.token, data.borrower_name);
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
        Begin your mortgage application in minutes.
        Your progress saves automatically.
      </p>

      {bounceError && !error && (
        <div className="pos-start__error" role="alert">{bounceError}</div>
      )}
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
              <span className="pos-start__spinner" /> Starting...
            </span>
          ) : (
            'Start Application'
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
      const resp = await fetch(`${API_BASE}/api/v1/pos/login-demo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || 'No account found. Please create a new account.');
      }

      onVerified(data.token, data.borrower_name);
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
        Enter the email address associated with your application to continue.
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
              <span className="pos-start__spinner" /> Signing in...
            </span>
          ) : (
            'Continue'
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
