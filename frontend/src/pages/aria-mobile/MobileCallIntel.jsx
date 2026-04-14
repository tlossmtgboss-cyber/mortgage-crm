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

// ── Helpers ──────────────────────────────────────────────────
function formatDuration(s) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ── Component ────────────────────────────────────────────────
export default function MobileCallIntel() {
  const navigate = useNavigate();

  const [sessionId, setSessionId] = useState(null);
  const [callActive, setCallActive] = useState(false);
  const [startingCall, setStartingCall] = useState(false);
  const [duration, setDuration] = useState(0);
  const [wsUrl, setWsUrl] = useState(null);

  const timerRef = useRef(null);

  // All 4 agent states managed by this hook
  const { state: ciState, disconnect, reset } = useCallIntelligence(wsUrl);

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
  const handleStartCall = useCallback(async () => {
    // In production: open a dialer sheet to pick a borrower + phone number
    const confirmed = window.confirm(
      'Start Call Intelligence\n\n' +
      'In production, this opens your contacts/borrower search to select who to call. ' +
      'The dialer initiates via Telnyx and all 4 agents activate automatically.\n\n' +
      'Click OK to simulate a dev call.'
    );
    if (!confirmed) return;

    setStartingCall(true);
    try {
      const userId = getCurrentUserId();
      const result = await CallIntelligenceApi.startCall({
        borrower_phone: '+16514141454',
        borrower_name: 'Kevin Mercer',
        borrower_email: 'kevinmercer@gmail.com',
        appointment_type: 'Initial Discovery',
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

  // ── End call ──────────────────────────────────────────────
  const handleEndCall = useCallback(() => {
    const confirmed = window.confirm(
      'End Call\n\n' +
      'Ending the call will save the transcript, application draft, tasks, and appointments. Continue?'
    );
    if (!confirmed) return;

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
  }, [sessionId, disconnect, reset]);

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
    </div>
  );
}
