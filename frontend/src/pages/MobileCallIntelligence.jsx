/**
 * MobileCallIntelligence.jsx
 *
 * Full-featured mobile Call Intelligence page for loan officers.
 * Uses callMonitoringAPI from ../services/api directly,
 * Web Speech API for live transcript capture, and haptics for tactile feedback.
 *
 * Three tabs:
 *   Record    — mic button, live transcript, client lookup
 *   Artifacts — AI-generated summaries, action items, risk flags, follow-ups
 *   History   — recent CI sessions
 *
 * Logic extracted into custom hooks:
 *   useCallMonitor       — session lifecycle, timer, client lookup
 *   useCallTranscription  — speech recognition, transcript state, chunk queue
 *   useCallArtifacts      — artifact polling, approve/reject/execute
 *   useCallHistory        — session history list, detail view
 */

import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import { haptics } from '../services/nativeServices';
import useCallMonitor from '../hooks/useCallMonitor';
import useCallTranscription from '../hooks/useCallTranscription';
import useCallArtifacts from '../hooks/useCallArtifacts';
import useCallHistory from '../hooks/useCallHistory';
import './MobileCallIntelligence.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ARTIFACT_TYPE_META = {
  summary: {
    label: 'Summary',
    borderColor: '#3b82f6',
    badgeColor: '#dbeafe',
    badgeText: '#1d4ed8',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
  },
  action_item: {
    label: 'Action Item',
    borderColor: '#10b981',
    badgeColor: '#d1fae5',
    badgeText: '#065f46',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="9 11 12 14 22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
  },
  risk_flag: {
    label: 'Risk Flag',
    borderColor: '#ef4444',
    badgeColor: '#fee2e2',
    badgeText: '#991b1b',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
  },
  follow_up: {
    label: 'Follow-Up',
    borderColor: '#8b5cf6',
    badgeColor: '#ede9fe',
    badgeText: '#5b21b6',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="17 1 21 5 17 9" />
        <path d="M3 11V9a4 4 0 0 1 4-4h14" />
        <polyline points="7 23 3 19 7 15" />
        <path d="M21 13v2a4 4 0 0 1-4 4H3" />
      </svg>
    ),
  },
  follow_up_draft: {
    label: 'Follow-Up Draft',
    borderColor: '#8b5cf6',
    badgeColor: '#ede9fe',
    badgeText: '#5b21b6',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="17 1 21 5 17 9" />
        <path d="M3 11V9a4 4 0 0 1 4-4h14" />
        <polyline points="7 23 3 19 7 15" />
        <path d="M21 13v2a4 4 0 0 1-4 4H3" />
      </svg>
    ),
  },
  document_request: {
    label: 'Document Request',
    borderColor: '#f59e0b',
    badgeColor: '#fef3c7',
    badgeText: '#92400e',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="12" y1="18" x2="12" y2="12" />
        <line x1="9" y1="15" x2="15" y2="15" />
      </svg>
    ),
  },
  pricing_scenario: {
    label: 'Pricing Scenario',
    borderColor: '#10b981',
    badgeColor: '#d1fae5',
    badgeText: '#065f46',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
  },
  condition: {
    label: 'Condition',
    borderColor: '#f59e0b',
    badgeColor: '#fef3c7',
    badgeText: '#92400e',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  },
};

const DEFAULT_ARTIFACT_META = {
  label: 'Insight',
  borderColor: '#6b7280',
  badgeColor: '#f3f4f6',
  badgeText: '#374151',
  icon: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  ),
};

function getArtifactMeta(type) {
  return ARTIFACT_TYPE_META[type] || DEFAULT_ARTIFACT_META;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return 'Yesterday';
  return `${diffDay}d ago`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// ---- Icons ----

function IconMic({ size = 32, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function IconStop({ size = 28, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} stroke="none">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function IconCheck({ size = 20, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function IconX({ size = 20, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function IconPlay({ size = 20, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} stroke="none">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function IconChevronRight({ size = 18, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function IconBack({ size = 22, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function IconRefresh({ size = 18, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

// ---- Skeleton card ----
function SkeletonCard() {
  return (
    <div className="mci-skeleton-card" aria-hidden="true">
      <div className="mci-skeleton-line mci-skeleton-title" />
      <div className="mci-skeleton-line mci-skeleton-body" />
      <div className="mci-skeleton-line mci-skeleton-body mci-skeleton-short" />
    </div>
  );
}

// ---- Artifact action buttons ----
function ArtifactActions({ artifact, onApprove, onReject, onExecute, loading }) {
  const isPending = !artifact.status || artifact.status === 'pending';
  const isApproved = artifact.status === 'approved';
  const isDone = artifact.status === 'executed' || artifact.status === 'rejected';
  if (isDone) return null;

  return (
    <div className="mci-artifact-actions">
      {isPending && (
        <>
          <button
            className="mci-action-btn mci-action-approve"
            onClick={() => onApprove(artifact.id)}
            disabled={loading}
            aria-label="Approve"
            title="Approve"
          >
            <IconCheck size={18} color="#fff" />
          </button>
          <button
            className="mci-action-btn mci-action-reject"
            onClick={() => onReject(artifact.id)}
            disabled={loading}
            aria-label="Reject"
            title="Reject"
          >
            <IconX size={18} color="#fff" />
          </button>
        </>
      )}
      {isApproved && (
        <button
          className="mci-action-btn mci-action-execute"
          onClick={() => onExecute(artifact.id)}
          disabled={loading}
          aria-label="Execute"
          title="Execute"
        >
          <IconPlay size={16} color="#fff" />
        </button>
      )}
    </div>
  );
}

// ---- Artifact card ----
function ArtifactCard({ artifact, onApprove, onReject, onExecute, actionLoading }) {
  const meta = getArtifactMeta(artifact.artifact_type);
  const content = artifact.content || artifact.description || artifact.title || '';
  const status = artifact.status || 'pending';

  return (
    <div
      className="mci-artifact-card"
      style={{ '--artifact-border': meta.borderColor }}
    >
      <div className="mci-artifact-header">
        <span className="mci-artifact-icon" style={{ color: meta.borderColor }}>
          {meta.icon}
        </span>
        <span className="mci-artifact-label">{meta.label}</span>
        <span
          className="mci-artifact-status-badge"
          style={{
            background: meta.badgeColor,
            color: meta.badgeText,
          }}
          data-status={status}
        >
          {status}
        </span>
      </div>
      {artifact.title && (
        <div className="mci-artifact-title">{artifact.title}</div>
      )}
      {content && (
        <div className="mci-artifact-content">{content}</div>
      )}
      <ArtifactActions
        artifact={artifact}
        onApprove={onApprove}
        onReject={onReject}
        onExecute={onExecute}
        loading={actionLoading}
      />
    </div>
  );
}

// ---- History session card ----
function SessionCard({ session, onTap }) {
  const duration = session.duration_seconds
    ? formatDuration(session.duration_seconds)
    : session.ended_at && session.started_at
    ? formatDuration(
        Math.round(
          (new Date(session.ended_at) - new Date(session.started_at)) / 1000
        )
      )
    : null;

  const artifactCount =
    session.artifact_count ??
    session.artifacts?.length ??
    0;

  const clientName =
    session.client_name ||
    session.client?.name ||
    session.metadata?.client_name ||
    null;

  const hasRecording = !!(session.recording_url || session.audio_url);

  return (
    <button className="mci-session-card" onClick={() => onTap(session)}>
      <div className="mci-session-info">
        <div className="mci-session-client">
          {clientName || 'Unknown Client'}
        </div>
        <div className="mci-session-meta">
          <span className="mci-session-date">
            {formatDate(session.started_at || session.created_at)}
          </span>
          {duration && (
            <span className="mci-session-duration">{duration}</span>
          )}
          {hasRecording && (
            <span className="mci-session-has-recording" title="Recording available">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
            </span>
          )}
          {artifactCount > 0 && (
            <span className="mci-session-artifacts">
              {artifactCount} artifact{artifactCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
      <div className="mci-session-right">
        <span
          className="mci-session-status-badge"
          data-status={session.status || 'completed'}
        >
          {session.status || 'completed'}
        </span>
        <IconChevronRight size={16} color="#9ca3af" />
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MobileCallIntelligence() {
  const navigate = useNavigate();

  // Tab state (kept in component -- used to coordinate hooks)
  const [activeTab, setActiveTab] = useState('record');

  // --- Hooks ---
  const monitor = useCallMonitor();

  const transcription = useCallTranscription({
    sessionIdRef: monitor.sessionIdRef,
    attemptClientDetection: monitor.attemptClientDetection,
  });

  const artifactsMgr = useCallArtifacts({
    sessionIdRef: monitor.sessionIdRef,
  });

  const history = useCallHistory({
    activeTab,
  });

  // ---------------------------------------------------------------------------
  // Orchestration: wire hooks together for start/stop
  // ---------------------------------------------------------------------------

  const handleStartRecording = useCallback(() => {
    transcription.resetTranscript();
    artifactsMgr.resetArtifacts();

    monitor.handleStartRecording({
      onSessionCreated: () => {
        // Session created -- transcription + artifacts are ready
      },
      startSpeechRecognition: transcription.startSpeechRecognition,
    });
  }, [monitor, transcription, artifactsMgr]);

  const handleStopRecording = useCallback(() => {
    monitor.handleStopRecording({
      stopSpeechRecognition: transcription.stopSpeechRecognition,
      transcript: transcription.transcript,
      onStopComplete: (sid) => {
        transcription.clearSessionOfflineChunks();
        setActiveTab('artifacts');
        artifactsMgr.beginArtifactFetch(sid);
      },
    });
  }, [monitor, transcription, artifactsMgr]);

  // ---------------------------------------------------------------------------
  // Tab switch
  // ---------------------------------------------------------------------------

  const handleTabChange = (tab) => {
    try {
      haptics.selection();
    } catch {}
    setActiveTab(tab);
  };

  // ---------------------------------------------------------------------------
  // Back navigation
  // ---------------------------------------------------------------------------

  const handleBack = () => {
    if (monitor.isRecording) {
      toast('Stop recording before leaving', { icon: '\u26A0\uFE0F' });
      return;
    }
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate('/');
    }
  };

  // ---------------------------------------------------------------------------
  // Destructure for cleaner JSX
  // ---------------------------------------------------------------------------

  const {
    isRecording, isStarting, isStopping, recordingDuration, statusMsg,
    clientInfo, clientSearchValue, clientSearchLoading,
    setClientSearchValue, handleClientSearch, clearClient,
  } = monitor;

  const { transcript, interimText, transcriptRef, pendingChunksCount } = transcription;

  const {
    artifacts, artifactsLoading, actionLoading,
    handleApprove, handleReject, handleExecute,
    handleApproveAll, handleExecuteAll,
  } = artifactsMgr;

  const {
    sessions, sessionsLoading,
    selectedHistorySession, historyArtifacts, historyArtifactsLoading,
    historyTranscript, historyTranscriptLoading,
    loadHistory, handleSelectHistorySession, handleBackFromHistoryDetail,
  } = history;

  // Collapsible transcript toggle in history detail
  const [historyTranscriptExpanded, setHistoryTranscriptExpanded] = useState(false);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="mci-root">
      {/* ---- Header ---- */}
      <header className="mci-header">
        <button
          className="mci-header-back"
          onClick={handleBack}
          aria-label="Back"
        >
          <IconBack size={22} color="#f1f5f9" />
        </button>
        <span className="mci-header-title">Call Intelligence</span>
        <div className="mci-header-right">
          {isRecording && (
            <div className="mci-header-timer" aria-live="polite">
              <span className="mci-rec-dot" />
              {formatDuration(recordingDuration)}
            </div>
          )}
        </div>
      </header>

      {/* ---- Tab bar ---- */}
      <nav className="mci-tab-bar" role="tablist">
        {['record', 'artifacts', 'history'].map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            className={`mci-tab${activeTab === tab ? ' mci-tab--active' : ''}`}
            onClick={() => handleTabChange(tab)}
          >
            {tab === 'record' && 'Record'}
            {tab === 'artifacts' && (
              <>
                Artifacts
                {artifacts.length > 0 && (
                  <span className="mci-tab-badge">{artifacts.length}</span>
                )}
              </>
            )}
            {tab === 'history' && 'History'}
          </button>
        ))}
      </nav>

      {/* ---- Tab panels ---- */}
      <main className="mci-main">

        {/* ============================================================
            TAB: RECORD
        ============================================================ */}
        {activeTab === 'record' && (
          <div className="mci-tab-panel" role="tabpanel">

            {/* Client lookup */}
            <div className="mci-client-lookup">
              {clientInfo ? (
                <div className="mci-client-detected">
                  <div className="mci-client-detected-avatar">
                    {(clientInfo.name || '?')[0].toUpperCase()}
                  </div>
                  <div className="mci-client-detected-info">
                    <div className="mci-client-detected-name">{clientInfo.name}</div>
                    {clientInfo.phone && (
                      <div className="mci-client-detected-phone">{clientInfo.phone}</div>
                    )}
                  </div>
                  {!isRecording && (
                    <button
                      className="mci-client-clear"
                      onClick={clearClient}
                      aria-label="Clear client"
                    >
                      <IconX size={16} color="#9ca3af" />
                    </button>
                  )}
                </div>
              ) : (
                <div className="mci-client-search-row">
                  <input
                    className="mci-client-search-input"
                    type="text"
                    placeholder="Client name or phone (optional)"
                    value={clientSearchValue}
                    onChange={(e) => setClientSearchValue(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleClientSearch()}
                    disabled={isRecording}
                  />
                  <button
                    className="mci-client-search-btn"
                    onClick={handleClientSearch}
                    disabled={!clientSearchValue.trim() || clientSearchLoading || isRecording}
                    aria-label="Look up client"
                  >
                    {clientSearchLoading ? (
                      <span className="mci-spinner-small" />
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="11" cy="11" r="8" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                      </svg>
                    )}
                  </button>
                </div>
              )}
            </div>

            {/* Mic button area */}
            <div className="mci-record-center">
              <div className={`mci-mic-ring${isRecording ? ' mci-mic-ring--active' : ''}`}>
                <button
                  className={`mci-mic-btn${isRecording ? ' mci-mic-btn--recording' : ''}`}
                  onClick={isRecording ? handleStopRecording : handleStartRecording}
                  disabled={isStarting || isStopping}
                  aria-label={isRecording ? 'Stop recording' : 'Start recording'}
                >
                  {isRecording ? (
                    <IconStop size={32} color="#fff" />
                  ) : (
                    <IconMic size={32} color="#fff" />
                  )}
                </button>
              </div>

              <div className="mci-record-label" aria-live="polite">
                {isStarting && 'Starting...'}
                {isStopping && 'Processing...'}
                {isRecording && !isStopping && 'Tap to stop'}
                {!isRecording && !isStarting && !isStopping && 'Tap to record'}
              </div>

              {statusMsg && !isStarting && !isStopping && (
                <div className="mci-status-msg" aria-live="polite">
                  {statusMsg}
                </div>
              )}
            </div>

            {/* Live transcript */}
            <div className="mci-transcript-container">
              <div className="mci-transcript-header">
                <span className="mci-transcript-title">Live Transcript</span>
                {pendingChunksCount > 0 && (
                  <span className="mci-pending-chunks">
                    {pendingChunksCount} chunk{pendingChunksCount !== 1 ? 's' : ''} pending
                  </span>
                )}
                {isRecording && (
                  <span className="mci-transcript-cursor-label">
                    <span className="mci-blink-cursor" />
                    Listening
                  </span>
                )}
              </div>
              <div
                className="mci-transcript-body"
                ref={transcriptRef}
                aria-live="polite"
                aria-label="Live transcript"
              >
                {!transcript && !interimText && (
                  <p className="mci-transcript-empty">
                    {isRecording
                      ? 'Waiting for speech...'
                      : 'Transcript will appear here during recording.'}
                  </p>
                )}
                {transcript && (
                  <span className="mci-transcript-final">{transcript}</span>
                )}
                {interimText && (
                  <span className="mci-transcript-interim"> {interimText}</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ============================================================
            TAB: ARTIFACTS
        ============================================================ */}
        {activeTab === 'artifacts' && (
          <div className="mci-tab-panel" role="tabpanel">

            {/* Bulk actions */}
            {artifacts.length > 0 && (
              <div className="mci-bulk-actions">
                <button
                  className="mci-bulk-btn mci-bulk-btn--approve"
                  onClick={handleApproveAll}
                  disabled={actionLoading}
                >
                  <IconCheck size={16} color="#fff" />
                  Approve All
                </button>
                <button
                  className="mci-bulk-btn mci-bulk-btn--execute"
                  onClick={handleExecuteAll}
                  disabled={actionLoading}
                >
                  <IconPlay size={14} color="#fff" />
                  Execute All
                </button>
              </div>
            )}

            {/* Loading skeletons */}
            {artifactsLoading && artifacts.length === 0 && (
              <div className="mci-artifact-list">
                {[1, 2, 3].map((i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {/* Empty state */}
            {!artifactsLoading && artifacts.length === 0 && (
              <div className="mci-empty-state">
                <div className="mci-empty-icon">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                  </svg>
                </div>
                <p className="mci-empty-title">No artifacts yet</p>
                <p className="mci-empty-body">
                  Record a call to generate AI summaries, action items, and risk flags.
                </p>
              </div>
            )}

            {/* Artifact list */}
            {artifacts.length > 0 && (
              <div className="mci-artifact-list">
                {artifacts.map((artifact) => (
                  <ArtifactCard
                    key={artifact.id}
                    artifact={artifact}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onExecute={handleExecute}
                    actionLoading={actionLoading}
                  />
                ))}
              </div>
            )}

            {/* Polling indicator */}
            {artifactsLoading && artifacts.length > 0 && (
              <div className="mci-poll-indicator">
                <span className="mci-spinner-small" />
                Checking for new artifacts...
              </div>
            )}
          </div>
        )}

        {/* ============================================================
            TAB: HISTORY
        ============================================================ */}
        {activeTab === 'history' && (
          <div className="mci-tab-panel" role="tabpanel">

            {/* History detail view */}
            {selectedHistorySession ? (
              <div className="mci-history-detail">
                <div className="mci-history-detail-header">
                  <button
                    className="mci-history-back-btn"
                    onClick={() => {
                      setHistoryTranscriptExpanded(false);
                      handleBackFromHistoryDetail();
                    }}
                    aria-label="Back to history"
                  >
                    <IconBack size={20} color="#374151" />
                    Back
                  </button>
                  <div className="mci-history-detail-title">
                    {selectedHistorySession.client_name ||
                      selectedHistorySession.client?.name ||
                      selectedHistorySession.metadata?.client_name ||
                      'Session'}
                  </div>
                  <div className="mci-history-detail-date">
                    {formatDate(
                      selectedHistorySession.started_at ||
                        selectedHistorySession.created_at
                    )}
                  </div>

                  {/* Duration display */}
                  {(selectedHistorySession.duration_seconds ||
                    (selectedHistorySession.ended_at && selectedHistorySession.started_at)) && (
                    <div className="mci-history-detail-duration">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                      <span>
                        {selectedHistorySession.duration_seconds
                          ? formatDuration(selectedHistorySession.duration_seconds)
                          : formatDuration(
                              Math.round(
                                (new Date(selectedHistorySession.ended_at) -
                                  new Date(selectedHistorySession.started_at)) /
                                  1000
                              )
                            )}
                      </span>
                    </div>
                  )}
                </div>

                {/* Audio player */}
                <div className="mci-audio-section">
                  {(selectedHistorySession.recording_url || selectedHistorySession.audio_url) ? (
                    <div className="mci-audio-player">
                      <div className="mci-audio-player-label">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
                        </svg>
                        Call Recording
                      </div>
                      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                      <audio
                        controls
                        preload="metadata"
                        src={selectedHistorySession.recording_url || selectedHistorySession.audio_url}
                        className="mci-audio-element"
                      />
                    </div>
                  ) : (
                    <div className="mci-audio-unavailable">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                        <line x1="23" y1="9" x2="17" y2="15" />
                        <line x1="17" y1="9" x2="23" y2="15" />
                      </svg>
                      No recording available
                    </div>
                  )}
                </div>

                {/* Transcript section */}
                <div className="mci-history-transcript-section">
                  <button
                    className="mci-history-transcript-toggle"
                    onClick={() => setHistoryTranscriptExpanded((prev) => !prev)}
                    disabled={historyTranscriptLoading}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className={`mci-history-transcript-chevron${historyTranscriptExpanded ? ' mci-history-transcript-chevron--open' : ''}`}
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                    <span>Transcript</span>
                    {historyTranscriptLoading && (
                      <span className="mci-spinner-small" />
                    )}
                  </button>
                  {historyTranscriptExpanded && (
                    <div className="mci-history-transcript-body">
                      {historyTranscriptLoading ? (
                        <div className="mci-history-transcript-loading">
                          <span className="mci-spinner-small" />
                          Loading transcript...
                        </div>
                      ) : historyTranscript ? (
                        <p className="mci-history-transcript-text">{historyTranscript}</p>
                      ) : (
                        <p className="mci-history-transcript-empty">No transcript available for this session.</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Open Full Review button */}
                <button
                  className="mci-open-review-btn"
                  onClick={() => navigate(`/call-intelligence/review/${selectedHistorySession.id}`)}
                >
                  Open Full Review
                  <IconChevronRight size={16} color="#fff" />
                </button>

                {/* Artifacts */}
                {historyArtifactsLoading && (
                  <div className="mci-artifact-list">
                    {[1, 2].map((i) => <SkeletonCard key={i} />)}
                  </div>
                )}

                {!historyArtifactsLoading && historyArtifacts.length === 0 && (
                  <div className="mci-empty-state">
                    <p className="mci-empty-title">No artifacts found</p>
                    <p className="mci-empty-body">This session has no recorded artifacts.</p>
                  </div>
                )}

                {historyArtifacts.length > 0 && (
                  <div className="mci-artifact-list">
                    {historyArtifacts.map((artifact) => (
                      <ArtifactCard
                        key={artifact.id}
                        artifact={artifact}
                        onApprove={handleApprove}
                        onReject={handleReject}
                        onExecute={handleExecute}
                        actionLoading={actionLoading}
                      />
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <>
                {/* Refresh button */}
                <div className="mci-history-toolbar">
                  <button
                    className="mci-refresh-btn"
                    onClick={loadHistory}
                    disabled={sessionsLoading}
                    aria-label="Refresh history"
                  >
                    <IconRefresh size={16} color={sessionsLoading ? '#9ca3af' : '#374151'} />
                    {sessionsLoading ? 'Loading...' : 'Refresh'}
                  </button>
                </div>

                {/* Loading skeletons */}
                {sessionsLoading && sessions.length === 0 && (
                  <div className="mci-session-list">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="mci-skeleton-card">
                        <div className="mci-skeleton-line mci-skeleton-title" />
                        <div className="mci-skeleton-line mci-skeleton-body mci-skeleton-short" />
                      </div>
                    ))}
                  </div>
                )}

                {/* Empty state */}
                {!sessionsLoading && sessions.length === 0 && (
                  <div className="mci-empty-state">
                    <div className="mci-empty-icon">
                      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                    </div>
                    <p className="mci-empty-title">No recent sessions</p>
                    <p className="mci-empty-body">Your recorded call sessions will appear here.</p>
                  </div>
                )}

                {/* Session list */}
                {sessions.length > 0 && (
                  <div className="mci-session-list">
                    {sessions.map((session) => (
                      <SessionCard
                        key={session.id}
                        session={session}
                        onTap={handleSelectHistorySession}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
