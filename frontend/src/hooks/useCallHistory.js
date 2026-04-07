/**
 * useCallHistory - Session history management for mobile Call Intelligence
 *
 * Manages:
 * - Loading recent CI sessions list
 * - Selecting a history session and loading its artifacts
 * - Fetching session transcript for playback/review
 * - Back navigation from history detail view
 *
 * Extracted from MobileCallIntelligence.jsx
 */

import { useState, useCallback, useEffect } from 'react';
import toast from 'react-hot-toast';
import { callMonitoringAPI } from '../services/api';

const useCallHistory = ({ activeTab }) => {
  // History state
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [selectedHistorySession, setSelectedHistorySession] = useState(null);
  const [historyArtifacts, setHistoryArtifacts] = useState([]);
  const [historyArtifactsLoading, setHistoryArtifactsLoading] = useState(false);
  const [historyTranscript, setHistoryTranscript] = useState(null);
  const [historyTranscriptLoading, setHistoryTranscriptLoading] = useState(false);

  // Load history
  const loadHistory = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const result = await callMonitoringAPI.listSessions({ page_size: 10 });
      setSessions(result?.sessions || result?.items || result || []);
    } catch {
      toast.error('Failed to load call history');
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  // Auto-load when history tab is active
  useEffect(() => {
    if (activeTab === 'history') {
      loadHistory();
    }
  }, [activeTab, loadHistory]);

  // Select a history session and load its artifacts + transcript
  const handleSelectHistorySession = useCallback(async (session) => {
    setSelectedHistorySession(session);
    setHistoryArtifactsLoading(true);
    setHistoryTranscript(null);
    setHistoryTranscriptLoading(true);

    // Fetch artifacts and transcript in parallel
    const artifactsPromise = callMonitoringAPI.getArtifacts(session.id)
      .then((result) => result?.artifacts || result || [])
      .catch(() => {
        toast.error('Failed to load session artifacts');
        return [];
      });

    const transcriptPromise = callMonitoringAPI.getTranscript(session.id)
      .then((result) => result?.full_transcript || result?.transcript || null)
      .catch(() => null); // Transcript fetch is best-effort

    const [artifacts, transcript] = await Promise.all([artifactsPromise, transcriptPromise]);

    setHistoryArtifacts(artifacts);
    setHistoryArtifactsLoading(false);
    setHistoryTranscript(transcript);
    setHistoryTranscriptLoading(false);
  }, []);

  // Back from history detail
  const handleBackFromHistoryDetail = useCallback(() => {
    setSelectedHistorySession(null);
    setHistoryArtifacts([]);
    setHistoryTranscript(null);
  }, []);

  return {
    // State
    sessions,
    sessionsLoading,
    selectedHistorySession,
    historyArtifacts,
    historyArtifactsLoading,
    historyTranscript,
    historyTranscriptLoading,

    // Actions
    loadHistory,
    handleSelectHistorySession,
    handleBackFromHistoryDetail,
  };
};

export default useCallHistory;
