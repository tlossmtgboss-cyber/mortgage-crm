/**
 * useAriaCallIntelligence — Bridge hook connecting Aria voice state to CI session.
 *
 * Wraps useCallIntelligenceSession with Aria-specific behavior:
 * - Coordinated start/stop with voice recording
 * - Voice command callbacks (approve all, execute all)
 * - Artifact count tracking for the CI button badge
 * - Event callbacks for the Aria UI
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useCallIntelligenceSession } from './useCallIntelligenceSession';

const useAriaCallIntelligence = ({ onArtifactsReady, onSessionStarted, onSessionEnded } = {}) => {
  const [isStarting, setIsStarting] = useState(false);

  // Core CI session hook — skipBackendChunkSend=false since we want
  // the hook to handle transcript forwarding when used from Aria
  const ciSession = useCallIntelligenceSession({
    initialContext: { source: 'aria_voice_app' },
    skipBackendChunkSend: false,
  });

  // Track previous artifact count for "new artifacts" callback
  const prevArtifactCount = useRef(0);

  useEffect(() => {
    const currentCount = ciSession.artifacts?.length || 0;
    if (currentCount > prevArtifactCount.current && prevArtifactCount.current > 0) {
      onArtifactsReady?.(ciSession.artifacts);
    }
    prevArtifactCount.current = currentCount;
  }, [ciSession.artifacts?.length]);

  // Start CI recording
  const startRecording = useCallback(async () => {
    if (ciSession.isActive || isStarting) return null;

    setIsStarting(true);
    try {
      const sessionId = await ciSession.startSession('mobile_app');
      if (sessionId) {
        onSessionStarted?.(sessionId);
      }
      return sessionId;
    } catch (err) {
      console.error('[AriaCI] Failed to start recording:', err);
      return null;
    } finally {
      setIsStarting(false);
    }
  }, [ciSession.isActive, ciSession.startSession, isStarting, onSessionStarted]);

  // Stop CI recording
  const stopRecording = useCallback(async () => {
    if (!ciSession.isActive) return;

    try {
      await ciSession.endSession();
      onSessionEnded?.();
    } catch (err) {
      console.error('[AriaCI] Failed to stop recording:', err);
    }
  }, [ciSession.isActive, ciSession.endSession, onSessionEnded]);

  // Voice command: approve all pending artifacts
  const approveAll = useCallback(async () => {
    const pending = (ciSession.artifacts || []).filter(
      a => a.approval_status === 'pending'
    );

    const results = [];
    for (const artifact of pending) {
      try {
        await ciSession.approveArtifact(artifact.id);
        results.push({ id: artifact.id, success: true });
      } catch (err) {
        results.push({ id: artifact.id, success: false, error: err.message });
      }
    }

    return {
      approved: results.filter(r => r.success).length,
      failed: results.filter(r => !r.success).length,
      total: pending.length,
    };
  }, [ciSession.artifacts, ciSession.approveArtifact]);

  // Voice command: execute all approved artifacts
  const executeAll = useCallback(async () => {
    const approved = (ciSession.artifacts || []).filter(
      a => a.approval_status === 'approved' && a.execution_status === 'pending'
    );

    const results = [];
    for (const artifact of approved) {
      try {
        await ciSession.executeArtifact(artifact.id);
        results.push({ id: artifact.id, success: true });
      } catch (err) {
        results.push({ id: artifact.id, success: false, error: err.message });
      }
    }

    return {
      executed: results.filter(r => r.success).length,
      failed: results.filter(r => !r.success).length,
      total: approved.length,
    };
  }, [ciSession.artifacts, ciSession.executeArtifact]);

  // Computed values
  const pendingCount = useMemo(() => {
    return (ciSession.artifacts || []).filter(
      a => a.approval_status === 'pending'
    ).length;
  }, [ciSession.artifacts]);

  const approvedCount = useMemo(() => {
    return (ciSession.artifacts || []).filter(
      a => a.approval_status === 'approved'
    ).length;
  }, [ciSession.artifacts]);

  const hasArtifacts = (ciSession.artifacts || []).length > 0;

  return {
    // Pass through CI session state
    sessionId: ciSession.sessionId,
    isActive: ciSession.isActive,
    isStopping: ciSession.isStopping,
    isStarting,
    duration: ciSession.duration,
    transcript: ciSession.transcript,
    agentStatuses: ciSession.agentStatuses,
    artifacts: ciSession.artifacts || [],
    detectedClient: ciSession.detectedClient,

    // Aria-specific actions
    startRecording,
    stopRecording,
    approveAll,
    executeAll,

    // Computed
    hasArtifacts,
    pendingCount,
    approvedCount,
    totalArtifactCount: (ciSession.artifacts || []).length,

    // Pass through for direct access
    approveArtifact: ciSession.approveArtifact,
    rejectArtifact: ciSession.rejectArtifact,
    appendTranscript: ciSession.appendTranscript,
  };
};

export default useAriaCallIntelligence;
