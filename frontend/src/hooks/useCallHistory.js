/**
 * useCallHistory - Session history management for mobile Call Intelligence
 *
 * Manages:
 * - Loading recent CI sessions list
 * - Selecting a history session and loading its artifacts
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

  // Select a history session and load its artifacts
  const handleSelectHistorySession = useCallback(async (session) => {
    setSelectedHistorySession(session);
    setHistoryArtifactsLoading(true);
    try {
      const result = await callMonitoringAPI.getArtifacts(session.id);
      setHistoryArtifacts(result?.artifacts || result || []);
    } catch {
      toast.error('Failed to load session artifacts');
    } finally {
      setHistoryArtifactsLoading(false);
    }
  }, []);

  // Back from history detail
  const handleBackFromHistoryDetail = useCallback(() => {
    setSelectedHistorySession(null);
    setHistoryArtifacts([]);
  }, []);

  return {
    // State
    sessions,
    sessionsLoading,
    selectedHistorySession,
    historyArtifacts,
    historyArtifactsLoading,

    // Actions
    loadHistory,
    handleSelectHistorySession,
    handleBackFromHistoryDetail,
  };
};

export default useCallHistory;
