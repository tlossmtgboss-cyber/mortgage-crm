/**
 * useCallArtifacts - Artifact management for mobile Call Intelligence
 *
 * Manages:
 * - Artifact list state and loading indicators
 * - Artifact polling (3s interval after session ends)
 * - Approve / reject / execute individual artifacts
 * - Bulk approve / execute all artifacts
 *
 * Extracted from MobileCallIntelligence.jsx
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { toast } from '../utils/toast';
import { callMonitoringAPI } from '../services/api';
import { haptics } from '../services/nativeServices';

const useCallArtifacts = ({ sessionIdRef }) => {
  // Artifact state
  const [artifacts, setArtifacts] = useState([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Polling ref
  const artifactPollRef = useRef(null);

  // Start polling for artifacts
  const startArtifactPolling = useCallback((sid) => {
    clearInterval(artifactPollRef.current);
    let pollCount = 0;
    const MAX_POLLS = 40; // 2 minutes at 3s interval

    const poll = async () => {
      pollCount++;
      try {
        const result = await callMonitoringAPI.getArtifacts(sid);
        const fetched = result?.artifacts || result || [];
        setArtifacts(fetched);

        // Stop when all are actioned or max polls reached
        const allActioned =
          fetched.length > 0 &&
          fetched.every((a) =>
            ['approved', 'rejected', 'executed'].includes(a.status)
          );
        if (allActioned || pollCount >= MAX_POLLS) {
          clearInterval(artifactPollRef.current);
        }
      } catch {
        // Non-fatal
      }
    };

    poll(); // immediate first fetch
    artifactPollRef.current = setInterval(poll, 3000);
  }, []);

  const stopArtifactPolling = useCallback(() => {
    clearInterval(artifactPollRef.current);
  }, []);

  // Begin loading + polling (called after session ends)
  const beginArtifactFetch = useCallback((sid) => {
    setArtifactsLoading(true);
    startArtifactPolling(sid);
    // Loading indicator cleared after initial poll completes
    // (using setTimeout to ensure at least a brief skeleton display)
    setTimeout(() => setArtifactsLoading(false), 500);
  }, [startArtifactPolling]);

  // Individual artifact actions
  const handleApprove = useCallback(async (artifactId) => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    setActionLoading(true);
    try {
      haptics.success();
    } catch {}
    try {
      await callMonitoringAPI.approveArtifacts(sid, [artifactId]);
      setArtifacts((prev) =>
        prev.map((a) => (a.id === artifactId ? { ...a, status: 'approved' } : a))
      );
    } catch {
      toast.error('Failed to approve artifact');
    } finally {
      setActionLoading(false);
    }
  }, [sessionIdRef]);

  const handleReject = useCallback(async (artifactId, reason = '') => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    setActionLoading(true);
    try {
      haptics.warning();
    } catch {}
    try {
      await callMonitoringAPI.rejectArtifacts(sid, [artifactId], reason);
      setArtifacts((prev) =>
        prev.map((a) => (a.id === artifactId ? { ...a, status: 'rejected' } : a))
      );
    } catch {
      toast.error('Failed to reject artifact');
    } finally {
      setActionLoading(false);
    }
  }, [sessionIdRef]);

  const handleExecute = useCallback(async (artifactId) => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    setActionLoading(true);
    try {
      haptics.light();
    } catch {}
    try {
      await callMonitoringAPI.executeArtifacts(sid, [artifactId]);
      setArtifacts((prev) =>
        prev.map((a) => (a.id === artifactId ? { ...a, status: 'executed' } : a))
      );
      toast.success('Artifact executed');
    } catch {
      toast.error('Failed to execute artifact');
    } finally {
      setActionLoading(false);
    }
  }, [sessionIdRef]);

  // Bulk actions
  const handleApproveAll = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    const pending = artifacts.filter(
      (a) => !a.status || a.status === 'pending'
    );
    if (pending.length === 0) return;
    setActionLoading(true);
    try {
      await callMonitoringAPI.approveArtifacts(
        sid,
        pending.map((a) => a.id)
      );
      setArtifacts((prev) =>
        prev.map((a) =>
          pending.some((p) => p.id === a.id) ? { ...a, status: 'approved' } : a
        )
      );
      toast.success(`Approved ${pending.length} artifacts`);
    } catch {
      toast.error('Bulk approve failed');
    } finally {
      setActionLoading(false);
    }
  }, [sessionIdRef, artifacts]);

  const handleExecuteAll = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    const approved = artifacts.filter((a) => a.status === 'approved');
    if (approved.length === 0) {
      toast('No approved artifacts to execute', { icon: '\u2139\uFE0F' });
      return;
    }
    setActionLoading(true);
    try {
      await callMonitoringAPI.executeArtifacts(
        sid,
        approved.map((a) => a.id)
      );
      setArtifacts((prev) =>
        prev.map((a) =>
          approved.some((p) => p.id === a.id) ? { ...a, status: 'executed' } : a
        )
      );
      toast.success(`Executed ${approved.length} artifacts`);
    } catch {
      toast.error('Bulk execute failed');
    } finally {
      setActionLoading(false);
    }
  }, [sessionIdRef, artifacts]);

  // Reset artifacts (for new sessions)
  const resetArtifacts = useCallback(() => {
    setArtifacts([]);
    setArtifactsLoading(false);
    setActionLoading(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopArtifactPolling();
    };
  }, [stopArtifactPolling]);

  return {
    // State
    artifacts,
    artifactsLoading,
    actionLoading,

    // Actions
    handleApprove,
    handleReject,
    handleExecute,
    handleApproveAll,
    handleExecuteAll,
    beginArtifactFetch,
    stopArtifactPolling,
    resetArtifacts,
  };
};

export default useCallArtifacts;
