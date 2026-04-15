/**
 * MobileCallIntel — Call Intelligence Screen for Perennia AI.
 *
 * Activated when LO starts a call with Call Intelligence enabled.
 * All 4 AI agents work in real time during the call:
 *   - Note Taker: live transcription + topic extraction
 *   - Jr. Loan Officer: auto-fills loan application from conversation
 *   - Auditor: flags red flags, requests documents, creates tasks
 *   - Receptionist: schedules appointments, sends invites
 *
 * Idle state shows agent list + start button.
 * Active state shows live banner + 4 agent cards.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';

import { CallIntelligenceApi } from '../../services/callIntelligenceApi';
import { useCallIntelligence } from '../../hooks/useCallIntelligence';
import { getCurrentUserId } from '../../utils/auth';

import NoteTakerCard from '../../components/callIntelligence/NoteTakerCard';
import JrLoanOfficerCard from '../../components/callIntelligence/JrLoanOfficerCard';
import AuditorCard from '../../components/callIntelligence/AuditorCard';
import ReceptionistCard from '../../components/callIntelligence/ReceptionistCard';
import LiveWaveform from '../../components/callIntelligence/LiveWaveform';

import './MobileCallIntel.css';

// ── Agent descriptions for idle state ────────────────────────
const AGENTS = [
  { color: '#7EB8F7', name: 'Note Taker',       desc: 'Live call transcription & topic extraction' },
  { color: '#9B7FE8', name: 'Jr. Loan Officer',  desc: 'Auto-fills loan application from the conversation' },
  { color: '#FBBC04', name: 'Auditor',            desc: 'Flags red flags, requests documents, creates tasks' },
  { color: '#34A853', name: 'Receptionist',        desc: 'Schedules appointments, sends invites to both calendars' },
];

// ── Inline ConfirmModal ─────────────────────────────────────
function ConfirmModal({ open, title, message, confirmLabel, cancelLabel, destructive, onConfirm, onCancel }) {
  const confirmBtnRef = useRef(null);
  const cancelBtnRef = useRef(null);
  const overlayRef = useRef(null);

  // Focus the cancel button when modal opens; trap focus within modal
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    if (cancelBtnRef.current) cancelBtnRef.current.focus();

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCancel();
        return;
      }
      if (e.key === 'Tab') {
        const focusable = [cancelBtnRef.current, confirmBtnRef.current].filter(Boolean);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      if (prev && prev.focus) prev.focus();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="mci-confirm-overlay"
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onCancel(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="mci-confirm-title"
    >
      <div className="mci-confirm-box">
        <h2 id="mci-confirm-title" className="mci-confirm-title">{title}</h2>
        <p className="mci-confirm-message">{message}</p>
        <div className="mci-confirm-actions">
          <button
            ref={cancelBtnRef}
            className="mci-confirm-cancel-btn"
            onClick={onCancel}
            type="button"
          >
            {cancelLabel || 'Cancel'}
          </button>
          <button
            ref={confirmBtnRef}
            className={`mci-confirm-ok-btn ${destructive ? 'mci-confirm-ok-btn--destructive' : ''}`}
            onClick={onConfirm}
            type="button"
          >
            {confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────
function formatDuration(s) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ── Component ────────────────────────────────────────────────
export default function MobileCallIntel({ borrowerContext }) {
  const navigate = useNavigate();

  const [sessionId, setSessionId] = useState(null);
  const [callActive, setCallActive] = useState(false);
  const [startingCall, setStartingCall] = useState(false);
  const [duration, setDuration] = useState(0);
  const [wsUrl, setWsUrl] = useState(null);

  // Confirmation modal state
  const [confirmModal, setConfirmModal] = useState({ open: false, title: '', message: '', confirmLabel: '', destructive: false, onConfirm: null });

  const timerRef = useRef(null);

  // All 4 agent states managed by this hook
  const { state: ciState, disconnect, reset } = useCallIntelligence(wsUrl);

  const closeModal = useCallback(() => {
    setConfirmModal((prev) => ({ ...prev, open: false, onConfirm: null }));
  }, []);

  // Check for existing active session on mount
  useEffect(() => {
    (async () => {
      const userId = getCurrentUserId();
      if (!userId) return;
      const active = await CallIntelligenceApi.getActiveSession(userId);
      if (active) {
        setSessionId(active.session_id);
        setCallActive(true);
        setWsUrl(CallIntelligenceApi.getWebSocketUrl(active.session_id));
        setDuration(active.duration_seconds || 0);
      }
    })();
  }, []);

  // Duration timer
  useEffect(() => {
    if (callActive) {
      timerRef.current = setInterval(() => setDuration((d) => d + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [callActive]);

  // ── Start a new call with all agents ──────────────────────
  const startCall = useCallback(async (borrower) => {
    setStartingCall(true);
    try {
      const userId = getCurrentUserId();
      const result = await CallIntelligenceApi.startCall({
        borrower_phone: borrower.phone,
        borrower_name: borrower.name,
        borrower_email: borrower.email,
        appointment_type: borrower.appointmentType || 'Initial Discovery',
        lo_user_id: userId ?? '',
      });
      setSessionId(result.session_id);
      setCallActive(true);
      setDuration(0);
      setWsUrl(CallIntelligenceApi.getWebSocketUrl(result.session_id));
    } catch (e) {
      toast.error('Failed to start call. Check API connection.');
    } finally {
      setStartingCall(false);
    }
  }, []);

  const handleStartCall = useCallback(() => {
    // Require borrower context — no hardcoded fallback
    if (!borrowerContext || !borrowerContext.phone || !borrowerContext.name || !borrowerContext.email) {
      toast.error('Select a borrower to start call monitoring');
      return;
    }

    setConfirmModal({
      open: true,
      title: 'Start Call Intelligence',
      message: `Start a call with ${borrowerContext.name}? All 4 AI agents will activate automatically once the call connects.`,
      confirmLabel: 'Start Call',
      destructive: false,
      onConfirm: () => {
        closeModal();
        startCall(borrowerContext);
      },
    });
  }, [borrowerContext, startCall, closeModal]);

  // ── End call ──────────────────────────────────────────────
  const handleEndCall = useCallback(() => {
    setConfirmModal({
      open: true,
      title: 'End Call',
      message: 'Ending the call will save the transcript, application draft, tasks, and appointments. Continue?',
      confirmLabel: 'End Call',
      destructive: true,
      onConfirm: () => {
        closeModal();
        (async () => {
          try {
            if (sessionId) await CallIntelligenceApi.endCall(sessionId);
          } catch (e) {
            console.error('[MobileCallIntel] endCall error:', e);
          }
          disconnect();
          setCallActive(false);
          setSessionId(null);
          setWsUrl(null);
          setDuration(0);
          reset();
          toast.success('Call ended. Your transcript, application draft, tasks, and appointments have been saved.');
        })();
      },
    });
  }, [sessionId, disconnect, reset, closeModal]);

  // ── View full application (opened by Jr LO card) ──────────
  const handleViewApplication = () => {
    toast.info('Coming soon: Opens the full 1003 loan application pre-filled by the Jr. Loan Officer agent.');
  };

  // ── Render ────────────────────────────────────────────────
  return (
    <div className="mci-screen">
      {/* Safe-area padding */}
      <div className="mci-status-bar" />

      {/* Background glow */}
      <div className="mci-glow" />

      {/* Top bar */}
      <div className="mci-top-bar">
        <button
          className="mci-back-btn"
          onClick={() => navigate('/aria-voice')}
          type="button"
        >
          <svg width="11" height="18" viewBox="0 0 10 16" fill="none">
            <path d="M8 2L2 8l6 6" stroke="#7EB8F7" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Back</span>
        </button>

        {callActive && (
          <button className="mci-end-call-btn" onClick={handleEndCall} type="button">
            End Call
          </button>
        )}
      </div>

      {/* Active call banner */}
      {callActive && ciState.session ? (
        <div className="mci-live-banner">
          <div className="mci-banner-top">
            <span className="mci-banner-name">
              {ciState.session.borrower_name} &mdash; {ciState.session.appointment_type}
            </span>
            <div className="mci-live-pill">
              <span className="mci-live-dot mci-live-dot--animated" />
              <span className="mci-live-txt">LIVE</span>
            </div>
          </div>
          <p className="mci-banner-meta">
            {formatDuration(duration)} elapsed &middot; {ciState.session.borrower_phone} &middot; 4 agents active
          </p>
          <LiveWaveform isActive={ciState.is_connected} />
        </div>
      ) : (
        /* Idle state -- no active call */
        <div className="mci-idle-header">
          <h1 className="mci-title">Call Intelligence</h1>
          <p className="mci-subtitle">
            {callActive ? '4 AI agents working' : 'Tap below to activate on your next call'}
          </p>
        </div>
      )}

      {/* Error banner */}
      {ciState.error && (
        <div className="mci-error-banner">
          <span className="mci-error-text">{ciState.error}</span>
        </div>
      )}

      {/* AGENT CARDS -- shown during active call */}
      {callActive && sessionId ? (
        <div className="mci-body mci-body--cards">
          <NoteTakerCard
            state={ciState.note_taker}
            callDurationSeconds={duration}
          />
          <JrLoanOfficerCard
            state={ciState.jr_loan_officer}
            onViewApplication={handleViewApplication}
          />
          <AuditorCard
            state={ciState.auditor}
            sessionId={sessionId}
          />
          <ReceptionistCard
            state={ciState.receptionist}
          />
        </div>
      ) : (
        /* Idle -- show explainer + start button */
        <div className="mci-idle-body">
          <div className="mci-agent-list">
            {AGENTS.map((agent) => (
              <div key={agent.name} className="mci-agent-row">
                <div
                  className="mci-agent-dot"
                  style={{ backgroundColor: agent.color }}
                />
                <div className="mci-agent-info">
                  <span className="mci-agent-row-name">{agent.name}</span>
                  <span className="mci-agent-row-desc">{agent.desc}</span>
                </div>
              </div>
            ))}
          </div>

          <button
            className={`mci-start-btn ${startingCall ? 'mci-start-btn--disabled' : ''}`}
            onClick={handleStartCall}
            disabled={startingCall}
            type="button"
          >
            {startingCall ? (
              <span className="mci-start-btn-spinner" />
            ) : (
              <>
                <span className="mci-start-btn-dot" />
                <span className="mci-start-btn-text">Start Call with Intelligence</span>
              </>
            )}
          </button>

          <p className="mci-start-hint">
            All 4 agents activate the moment your call connects
          </p>
        </div>
      )}

      {/* Confirmation modal */}
      <ConfirmModal
        open={confirmModal.open}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        destructive={confirmModal.destructive}
        onConfirm={confirmModal.onConfirm}
        onCancel={closeModal}
      />
    </div>
  );
}
