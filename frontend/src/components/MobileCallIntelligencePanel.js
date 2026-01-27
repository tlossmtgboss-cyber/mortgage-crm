/**
 * MobileCallIntelligencePanel
 *
 * Full-screen mobile-optimized call intelligence panel for iOS.
 * Captures mic audio, streams to Deepgram via backend WebSocket,
 * and runs 6 AI agents in real-time.
 *
 * Uses:
 * - useCallIntelligenceSession (session lifecycle, agents, artifacts)
 * - useMobileAudioCapture (mic → WebSocket → Deepgram → transcript)
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import useCallIntelligenceSession, {
  AGENT_CONFIG,
  getArtifactIcon,
  formatDuration,
} from '../hooks/useCallIntelligenceSession';
import useMobileAudioCapture from '../hooks/useMobileAudioCapture';
import { haptics } from '../services/nativeServices';
import './MobileCallIntelligencePanel.css';

const MobileCallIntelligencePanel = ({ onClose, initialContext = {} }) => {
  const [activeTab, setActiveTab] = useState('transcript');
  const [selectedArtifact, setSelectedArtifact] = useState(null);

  const transcriptRef = useRef(null);

  // Session management
  // skipBackendChunkSend=true because the audio-stream WebSocket already
  // feeds transcript text to the backend's process_transcript_chunk
  const session = useCallIntelligenceSession({
    initialContext,
    skipBackendChunkSend: true,
  });

  // Audio capture (only active when we have a sessionId)
  const audio = useMobileAudioCapture({
    sessionId: session.sessionId,
    onTranscript: useCallback(
      (text) => {
        // appendTranscript feeds text to the session hook which handles
        // client detection and backend transcript chunk forwarding.
        // However, since audio-stream WebSocket already forwards finals
        // to the backend, we only need to accumulate locally here.
        session.appendTranscript(text);
      },
      [session.appendTranscript]
    ),
    enabled: session.isActive,
  });

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [session.transcript, audio.interimText]);

  // Start recording flow
  const handleStart = async () => {
    haptics.medium();

    // 1. Create backend session
    const sid = await session.startSession('mobile_app');
    if (!sid) return;

    // 2. Start audio capture + WebSocket (session hook sets sessionId,
    //    but useMobileAudioCapture needs it passed as prop which updates
    //    on next render. We call startCapture after a tick.)
    // Note: startCapture will be called by useEffect when sessionId changes
  };

  // Auto-start audio capture when session becomes active
  useEffect(() => {
    if (session.sessionId && session.isActive && !audio.isRecording) {
      audio.startCapture();
    }
  }, [session.sessionId, session.isActive]);

  // Stop recording flow
  const handleStop = async () => {
    haptics.heavy();

    // 1. Stop audio capture
    audio.stopCapture();

    // 2. End session (runs final agent processing)
    await session.endSession();
  };

  // Approve artifact with haptic
  const handleApprove = async (artifactId) => {
    haptics.success();
    await session.approveArtifact(artifactId);
  };

  // Execute artifact with haptic
  const handleExecute = async (artifactId) => {
    haptics.light();
    await session.executeArtifact(artifactId);
  };

  // Reject artifact
  const handleReject = async (artifactId) => {
    haptics.warning();
    await session.rejectArtifact(artifactId);
  };

  const error = session.error || audio.error;

  return (
    <div className="mcip">
      {/* Header */}
      <div className="mcip-header">
        <div className="mcip-header-left">
          <button className="mcip-back-btn" onClick={onClose}>
            &#8592;
          </button>
          <span className="mcip-title">Call Intelligence</span>
        </div>
        {session.isActive && (
          <div className="mcip-timer">
            <span className="mcip-timer-dot" />
            {formatDuration(session.duration)}
          </div>
        )}
      </div>

      {/* Error */}
      {error && <div className="mcip-error">{error}</div>}

      {/* Connection status */}
      {session.isActive && (
        <div className="mcip-connection">
          <span className={`mcip-connection-dot ${audio.connectionStatus}`} />
          {audio.connectionStatus === 'connected' && 'Live transcription active'}
          {audio.connectionStatus === 'connecting' && 'Connecting...'}
          {audio.connectionStatus === 'error' && 'Connection error'}
          {audio.connectionStatus === 'disconnected' && 'Disconnected'}
        </div>
      )}

      {/* Permission denied */}
      {audio.hasPermission === false && (
        <div className="mcip-permission">
          <div className="mcip-permission-icon">🎙️</div>
          <div className="mcip-permission-text">
            Microphone access is required for call intelligence.
            Please enable it in Settings &gt; Perennia AI &gt; Microphone.
          </div>
        </div>
      )}

      {/* Record button */}
      {audio.hasPermission !== false && (
        <div className="mcip-record-area">
          {!session.isActive && !session.isStopping ? (
            <>
              <button
                className="mcip-record-btn"
                onClick={handleStart}
                disabled={session.isStarting}
              >
                <div className="mcip-record-inner" />
              </button>
              <div className="mcip-record-label">
                {session.isStarting ? 'Starting...' : 'Tap to Record'}
              </div>
              {!session.isStarting && (
                <div className="mcip-record-hint">
                  Put your phone on speaker. AI agents will automatically
                  transcribe and analyze the call.
                </div>
              )}
            </>
          ) : session.isActive ? (
            <>
              <button
                className="mcip-record-btn recording"
                onClick={handleStop}
              >
                <div className="mcip-record-inner" />
              </button>
              <div className="mcip-record-label">Tap to Stop</div>
            </>
          ) : (
            <div className="mcip-record-label">Processing...</div>
          )}
        </div>
      )}

      {/* Client detection banner */}
      {(session.isActive || session.detectedClient) &&
        session.clientMatchStatus !== 'idle' && (
          <div
            className={`mcip-client-banner ${
              session.clientMatchStatus === 'matched'
                ? 'matched'
                : session.clientMatchStatus === 'new_client'
                ? 'new-client'
                : ''
            }`}
          >
            <span className="mcip-client-icon">
              {session.clientMatchStatus === 'searching' && '🔍'}
              {session.clientMatchStatus === 'matched' && '✓'}
              {session.clientMatchStatus === 'new_client' && '➕'}
            </span>
            <div className="mcip-client-info">
              <div className="mcip-client-name">
                {session.clientMatchStatus === 'searching'
                  ? 'Identifying client...'
                  : session.detectedClient?.name || 'Unknown'}
              </div>
              {session.detectedClient?.phone && (
                <div className="mcip-client-detail">
                  {session.detectedClient.phone}
                </div>
              )}
            </div>
          </div>
        )}

      {/* Tabs */}
      {(session.isActive || session.transcript || session.artifacts.length > 0) && (
        <div className="mcip-tabs">
          <button
            className={`mcip-tab ${activeTab === 'transcript' ? 'active' : ''}`}
            onClick={() => setActiveTab('transcript')}
          >
            Transcript
          </button>
          <button
            className={`mcip-tab ${activeTab === 'agents' ? 'active' : ''}`}
            onClick={() => setActiveTab('agents')}
          >
            Agents
          </button>
          <button
            className={`mcip-tab ${activeTab === 'artifacts' ? 'active' : ''}`}
            onClick={() => setActiveTab('artifacts')}
          >
            Artifacts
            {session.artifacts.length > 0 && (
              <span> ({session.artifacts.length})</span>
            )}
          </button>
        </div>
      )}

      {/* Tab content */}
      <div className="mcip-content" ref={transcriptRef}>
        {/* Live Transcript */}
        {activeTab === 'transcript' && (
          <>
            {session.transcript || audio.interimText ? (
              <div className="mcip-transcript">
                {session.transcript}
                {audio.interimText && (
                  <span className="mcip-transcript-interim">
                    {audio.interimText}
                  </span>
                )}
              </div>
            ) : (
              <div className="mcip-transcript-empty">
                <div className="mcip-transcript-empty-icon">🎙️</div>
                {session.isActive
                  ? 'Listening... Start speaking.'
                  : 'Tap record to begin.'}
              </div>
            )}
          </>
        )}

        {/* Agents Grid */}
        {activeTab === 'agents' && (
          <div className="mcip-agent-grid">
            {AGENT_CONFIG.map((agent) => {
              const status = session.agentStatuses[agent.id];
              const statusLabel = status?.status || 'idle';
              const artifactCount = status?.artifacts?.length || 0;

              return (
                <div
                  key={agent.id}
                  className={`mcip-agent-card ${statusLabel}`}
                  style={{ '--agent-color': agent.color }}
                >
                  <div className="mcip-agent-icon">{agent.icon}</div>
                  <div className="mcip-agent-name">{agent.name}</div>
                  <div className={`mcip-agent-status ${statusLabel}`}>
                    {statusLabel === 'ready' && 'Ready'}
                    {statusLabel === 'listening' && 'Listening'}
                    {statusLabel === 'active' && 'Active'}
                    {statusLabel === 'processing' && 'Processing'}
                    {statusLabel === 'complete' && 'Done'}
                    {statusLabel === 'idle' && 'Idle'}
                  </div>
                  {artifactCount > 0 && (
                    <span className="mcip-agent-badge">
                      {artifactCount} item{artifactCount > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Artifacts */}
        {activeTab === 'artifacts' && (
          <>
            {session.artifacts.length === 0 ? (
              <div className="mcip-artifacts-empty">
                {session.isActive
                  ? 'Artifacts will appear as agents process the call...'
                  : 'No artifacts yet.'}
              </div>
            ) : (
              session.artifacts.map((artifact) => (
                <div
                  key={artifact.id}
                  className="mcip-artifact-card"
                  onClick={() => setSelectedArtifact(artifact)}
                >
                  <div className="mcip-artifact-header">
                    <span className="mcip-artifact-icon">
                      {getArtifactIcon(artifact.artifact_type)}
                    </span>
                    <span className="mcip-artifact-type">
                      {(artifact.artifact_type || '').replace(/_/g, ' ')}
                    </span>
                    <span
                      className={`mcip-artifact-status-badge ${
                        artifact.status || 'pending'
                      }`}
                    >
                      {artifact.status || 'pending'}
                    </span>
                  </div>
                  <div className="mcip-artifact-content">
                    {artifact.content ||
                      artifact.description ||
                      artifact.title ||
                      'View details'}
                  </div>
                  {artifact.status !== 'executed' && (
                    <div className="mcip-artifact-actions">
                      {artifact.status !== 'approved' && (
                        <button
                          className="mcip-artifact-btn approve"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleApprove(artifact.id);
                          }}
                        >
                          Approve
                        </button>
                      )}
                      {artifact.status === 'approved' && (
                        <button
                          className="mcip-artifact-btn execute"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleExecute(artifact.id);
                          }}
                        >
                          Execute
                        </button>
                      )}
                      {artifact.status !== 'approved' &&
                        artifact.status !== 'rejected' && (
                          <button
                            className="mcip-artifact-btn reject"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleReject(artifact.id);
                            }}
                          >
                            Reject
                          </button>
                        )}
                    </div>
                  )}
                </div>
              ))
            )}
          </>
        )}
      </div>

      {/* Artifact detail bottom sheet */}
      {selectedArtifact && (
        <>
          <div
            className="mcip-sheet-overlay"
            onClick={() => setSelectedArtifact(null)}
          />
          <div className="mcip-sheet">
            <div className="mcip-sheet-handle" />
            <div className="mcip-sheet-header">
              <span className="mcip-sheet-title">
                {getArtifactIcon(selectedArtifact.artifact_type)}{' '}
                {(selectedArtifact.artifact_type || '').replace(/_/g, ' ')}
              </span>
              <button
                className="mcip-sheet-close"
                onClick={() => setSelectedArtifact(null)}
              >
                &#10005;
              </button>
            </div>
            <div className="mcip-sheet-body">
              {selectedArtifact.title && (
                <p style={{ fontWeight: 600, fontSize: 16 }}>
                  {selectedArtifact.title}
                </p>
              )}
              <p>
                {selectedArtifact.content ||
                  selectedArtifact.description ||
                  'No details available.'}
              </p>
              {selectedArtifact.data &&
                typeof selectedArtifact.data === 'object' && (
                  <pre
                    style={{
                      fontSize: 12,
                      color: '#94a3b8',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {JSON.stringify(selectedArtifact.data, null, 2)}
                  </pre>
                )}
            </div>
            {selectedArtifact.status !== 'executed' && (
              <div className="mcip-sheet-actions">
                {selectedArtifact.status !== 'approved' && (
                  <button
                    className="mcip-artifact-btn approve"
                    style={{ flex: 1 }}
                    onClick={() => {
                      handleApprove(selectedArtifact.id);
                      setSelectedArtifact({
                        ...selectedArtifact,
                        status: 'approved',
                      });
                    }}
                  >
                    Approve
                  </button>
                )}
                {selectedArtifact.status === 'approved' && (
                  <button
                    className="mcip-artifact-btn execute"
                    style={{ flex: 1 }}
                    onClick={() => {
                      handleExecute(selectedArtifact.id);
                      setSelectedArtifact({
                        ...selectedArtifact,
                        status: 'executed',
                      });
                    }}
                  >
                    Execute
                  </button>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default MobileCallIntelligencePanel;
