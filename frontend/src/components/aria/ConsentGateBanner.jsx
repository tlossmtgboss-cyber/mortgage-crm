/**
 * PERENNIA AI — ConsentGateBanner (v2 — Audit Fixes)
 *
 * FIXES:
 *   1. Retry button on failed state (both one-party and two-party)
 *   2. Browser-mode indicator when disclosure plays through speakers
 *   3. "Contact Support" link on hard-block (two-party failure)
 *   4. Proper auto-dismiss only after active confirmation
 */

import React, { useEffect, useState } from 'react';

const COLORS = {
  background: '#060A10',
  blue: '#7EB8F7',
  green: '#4ADE80',
  amber: '#FBBF24',
  red: '#F87171',
  textPrimary: 'rgba(255, 255, 255, 0.95)',
  textSecondary: 'rgba(255, 255, 255, 0.6)',
};

const baseStyles = {
  banner: {
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '16px',
    backdropFilter: 'blur(12px)',
    fontFamily: "'DM Sans', sans-serif",
    transition: 'all 0.3s ease',
  },
  title: {
    fontSize: '13px',
    fontWeight: 600,
    marginBottom: '6px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  message: {
    fontSize: '12px',
    color: COLORS.textSecondary,
    lineHeight: '1.5',
    margin: 0,
  },
  buttonRow: {
    display: 'flex',
    gap: '8px',
    marginTop: '12px',
    flexWrap: 'wrap',
  },
  button: (color) => ({
    padding: '8px 16px',
    borderRadius: '8px',
    border: `1px solid ${color}`,
    background: `${color}18`,
    color,
    fontSize: '12px',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: "'DM Sans', sans-serif",
    transition: 'background 0.2s ease',
  }),
  linkButton: {
    padding: '8px 16px',
    borderRadius: '8px',
    border: '1px solid rgba(255,255,255,0.15)',
    background: 'rgba(255,255,255,0.05)',
    color: COLORS.textSecondary,
    fontSize: '12px',
    fontWeight: 500,
    cursor: 'pointer',
    fontFamily: "'DM Sans', sans-serif",
    textDecoration: 'none',
  },
};

const WAVE_CSS = `
  @keyframes consentWave {
    0%, 100% { height: 4px; opacity: 0.4; }
    50% { height: 14px; opacity: 1; }
  }
  @keyframes consentFadeIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes consentFadeOut {
    from { opacity: 1; }
    to { opacity: 0; transform: translateY(-4px); }
  }
`;

function AudioWave() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '2px', height: '16px' }}>
      {[0, 0.15, 0.3, 0.45, 0.6].map((delay, i) => (
        <div
          key={i}
          style={{
            width: '3px',
            borderRadius: '2px',
            background: COLORS.blue,
            animation: `consentWave 1s ease-in-out ${delay}s infinite`,
          }}
        />
      ))}
    </div>
  );
}

export default function ConsentGateBanner({
  sessionState,
  consentInfo,
  errorMessage,
  canManualOverride,
  canRetry,
  onConfirmVerbalDisclosure,
  onRetryDisclosure,
}) {
  const [visible, setVisible] = useState(true);
  const [dismissing, setDismissing] = useState(false);

  useEffect(() => {
    if (sessionState === 'active' && consentInfo?.status === 'disclosed') {
      const timer = setTimeout(() => {
        setDismissing(true);
        setTimeout(() => setVisible(false), 300);
      }, 3000);
      return () => clearTimeout(timer);
    }
    setVisible(true);
    setDismissing(false);
  }, [sessionState, consentInfo?.status]);

  if (sessionState === 'idle' || !visible) return null;

  const animStyle = {
    animation: dismissing
      ? 'consentFadeOut 0.3s ease forwards'
      : 'consentFadeIn 0.3s ease',
  };

  if (sessionState === 'requesting_consent') {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(126, 184, 247, 0.06)',
            border: '1px solid rgba(126, 184, 247, 0.15)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.blue }}>
            Initializing Call Intelligence...
          </div>
          <p style={baseStyles.message}>Checking recording consent requirements.</p>
        </div>
      </>
    );
  }

  if (sessionState === 'playing_disclosure') {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(126, 184, 247, 0.08)',
            border: '1px solid rgba(126, 184, 247, 0.25)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.blue }}>
            <AudioWave />
            Playing Recording Disclosure
          </div>
          <p style={baseStyles.message}>
            {consentInfo?.isBrowserMode
              ? 'A recording notice is playing through your device speakers. '
              : 'A recording notice is playing to both parties on the call. '}
            Call intelligence will activate automatically when complete.
          </p>
          {consentInfo?.isBrowserMode && (
            <p
              style={{
                ...baseStyles.message,
                marginTop: '6px',
                fontSize: '11px',
                fontStyle: 'italic',
                color: 'rgba(126, 184, 247, 0.7)',
              }}
            >
              Make sure your phone speaker is on so the borrower can hear the disclosure.
            </p>
          )}
        </div>
      </>
    );
  }

  if (sessionState === 'consent_failed' && canManualOverride) {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(251, 191, 36, 0.08)',
            border: '1px solid rgba(251, 191, 36, 0.25)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.amber }}>
            ⚠ Disclosure Playback Failed
          </div>
          <p style={baseStyles.message}>
            {errorMessage || 'The recording disclosure could not be played.'}
          </p>
          <p style={{ ...baseStyles.message, marginTop: '6px' }}>
            You can retry the disclosure, or proceed after verbally informing
            the borrower that this call is being recorded.
          </p>
          <div style={baseStyles.buttonRow}>
            {canRetry && (
              <button
                style={baseStyles.button(COLORS.blue)}
                onClick={onRetryDisclosure}
              >
                Retry Disclosure
              </button>
            )}
            <button
              style={baseStyles.button(COLORS.amber)}
              onClick={onConfirmVerbalDisclosure}
            >
              I Verbally Disclosed Recording
            </button>
          </div>
        </div>
      </>
    );
  }

  if (sessionState === 'consent_failed' && !canManualOverride) {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(248, 113, 113, 0.08)',
            border: '1px solid rgba(248, 113, 113, 0.25)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.red }}>
            ✕ Cannot Activate — Consent Required
          </div>
          <p style={baseStyles.message}>
            {consentInfo?.isFelonyState
              ? 'Recording without consent is a felony in this state. '
              : ''}
            Audio disclosure is legally required in two-party consent states
            and could not be played.
          </p>
          <div style={baseStyles.buttonRow}>
            {canRetry && (
              <button
                style={baseStyles.button(COLORS.blue)}
                onClick={onRetryDisclosure}
              >
                Retry Disclosure
              </button>
            )}
            <a
              href="mailto:support@perennia.ai?subject=Call%20Intelligence%20Disclosure%20Issue"
              style={baseStyles.linkButton}
            >
              Contact Support
            </a>
          </div>
        </div>
      </>
    );
  }

  if (sessionState === 'active' && consentInfo?.status === 'disclosed') {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(74, 222, 128, 0.08)',
            border: '1px solid rgba(74, 222, 128, 0.25)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.green }}>
            ✓ Call Intelligence Active
          </div>
          <p style={baseStyles.message}>
            Recording disclosure complete.
            {consentInfo?.manualOverride ? ' (Verbal disclosure confirmed)' : ''}
            {' '}Agents are now listening.
          </p>
        </div>
      </>
    );
  }

  if (sessionState === 'error') {
    return (
      <>
        <style>{WAVE_CSS}</style>
        <div
          style={{
            ...baseStyles.banner,
            background: 'rgba(248, 113, 113, 0.06)',
            border: '1px solid rgba(248, 113, 113, 0.15)',
            ...animStyle,
          }}
        >
          <div style={{ ...baseStyles.title, color: COLORS.red }}>
            Error
          </div>
          <p style={baseStyles.message}>{errorMessage || 'Something went wrong.'}</p>
        </div>
      </>
    );
  }

  return null;
}
