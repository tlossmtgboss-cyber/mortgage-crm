/**
 * Conversation Intelligence React Hooks
 *
 * Custom hooks for the voice call analysis platform:
 * - useRecordings: Manage call recordings
 * - useTranscription: Transcription status and polling
 * - useAnalysis: Call analysis
 * - useQAScoring: QA scorecards
 * - useRealTimeAssist: WebSocket-based real-time coaching
 * - useCoaching: Clips and assignments
 * - useDashboard: Dashboard metrics
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  recordingsApi,
  transcriptionApi,
  analysisApi,
  qaApi,
  realTimeApi,
  coachingApi,
  dashboardApi,
} from '../services/conversationIntelligenceApi';

// =============================================================================
// USE RECORDINGS HOOK
// =============================================================================

export function useRecordings(filters = {}) {
  const [recordings, setRecordings] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRecordings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await recordingsApi.list(filters);
      setRecordings(response.recordings);
      setTotal(response.total);
    } catch (err) {
      setError(err.message || 'Failed to fetch recordings');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    fetchRecordings();
  }, [fetchRecordings]);

  const createRecording = async (data) => {
    try {
      const recording = await recordingsApi.create(data);
      setRecordings(prev => [recording, ...prev]);
      setTotal(prev => prev + 1);
      return recording;
    } catch (err) {
      setError(err.message || 'Failed to create recording');
      return null;
    }
  };

  const uploadAudio = async (recordingId, file) => {
    try {
      await recordingsApi.uploadAudio(recordingId, file);
      await fetchRecordings();
      return true;
    } catch (err) {
      setError(err.message || 'Failed to upload audio');
      return false;
    }
  };

  return {
    recordings,
    total,
    loading,
    error,
    refetch: fetchRecordings,
    createRecording,
    uploadAudio,
  };
}

// =============================================================================
// USE RECORDING DETAIL HOOK
// =============================================================================

export function useRecordingDetail(recordingId) {
  const [recording, setRecording] = useState(null);
  const [transcription, setTranscription] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [scorecards, setScorecards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!recordingId) return;

    setLoading(true);
    setError(null);

    try {
      // Fetch recording
      const rec = await recordingsApi.get(recordingId);
      setRecording(rec);

      // Try to fetch transcription
      try {
        const trans = await transcriptionApi.get(recordingId);
        setTranscription(trans);
      } catch {
        setTranscription(null);
      }

      // Try to fetch analysis
      try {
        const anal = await analysisApi.get(recordingId);
        setAnalysis(anal);
      } catch {
        setAnalysis(null);
      }

      // Try to fetch scorecards
      try {
        const sc = await qaApi.getScorecards(recordingId);
        setScorecards(sc.scorecards);
      } catch {
        setScorecards([]);
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch recording details');
    } finally {
      setLoading(false);
    }
  }, [recordingId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const startTranscription = async (request) => {
    if (!recordingId) return false;
    try {
      const trans = await transcriptionApi.transcribe(recordingId, request);
      setTranscription(trans);
      return true;
    } catch (err) {
      setError(err.message || 'Failed to start transcription');
      return false;
    }
  };

  const startAnalysis = async (request = {}) => {
    if (!recordingId) return false;
    try {
      const anal = await analysisApi.analyze(recordingId, request);
      setAnalysis(anal);
      return true;
    } catch (err) {
      setError(err.message || 'Failed to start analysis');
      return false;
    }
  };

  const createScorecard = async (request = {}) => {
    if (!recordingId) return null;
    try {
      const scorecard = await qaApi.createScorecard(recordingId, request);
      setScorecards(prev => [scorecard, ...prev]);
      return scorecard;
    } catch (err) {
      setError(err.message || 'Failed to create scorecard');
      return null;
    }
  };

  return {
    recording,
    transcription,
    analysis,
    scorecards,
    loading,
    error,
    refetch: fetchData,
    startTranscription,
    startAnalysis,
    createScorecard,
  };
}

// =============================================================================
// USE TRANSCRIPTION POLLING HOOK
// =============================================================================

export function useTranscriptionPolling(recordingId, autoStart = false) {
  const [transcription, setTranscription] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const startPolling = useCallback(() => {
    if (!recordingId || isPolling) return;

    setIsPolling(true);
    setError(null);

    const poll = async () => {
      try {
        const trans = await transcriptionApi.get(recordingId);
        setTranscription(trans);

        if (trans.status === 'completed' || trans.status === 'failed') {
          stopPolling();
          if (trans.status === 'failed') {
            setError(trans.errorMessage || 'Transcription failed');
          }
        }
      } catch (err) {
        setError(err.message || 'Failed to fetch transcription');
        stopPolling();
      }
    };

    // Initial fetch
    poll();

    // Start polling every 2 seconds
    pollingRef.current = setInterval(poll, 2000);
  }, [recordingId, isPolling, stopPolling]);

  useEffect(() => {
    if (autoStart && recordingId) {
      startPolling();
    }
    return () => stopPolling();
  }, [recordingId, autoStart, startPolling, stopPolling]);

  return {
    transcription,
    isPolling,
    error,
    startPolling,
    stopPolling,
  };
}

// =============================================================================
// USE REAL-TIME ASSIST HOOK
// =============================================================================

export function useRealTimeAssist() {
  const [session, setSession] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsConnecting(false);
  }, []);

  const connectWebSocket = useCallback((sessionId) => {
    cleanup();
    setIsConnecting(true);

    const ws = realTimeApi.createWebSocket(sessionId);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[RealTimeAssist] WebSocket connected');
      setIsConnected(true);
      setIsConnecting(false);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        switch (message.type) {
          case 'connected':
            console.log('[RealTimeAssist] Session confirmed:', message.sessionId);
            break;

          case 'suggestion':
            if (message.data) {
              setSuggestions(prev => [message.data, ...prev]);
            }
            break;

          case 'session_ended':
            console.log('[RealTimeAssist] Session ended');
            cleanup();
            break;

          case 'error':
            setError(message.message || 'WebSocket error');
            break;

          default:
            break;
        }
      } catch (e) {
        console.error('[RealTimeAssist] Error parsing message:', e);
      }
    };

    ws.onerror = (event) => {
      console.error('[RealTimeAssist] WebSocket error:', event);
      setError('Connection error');
      setIsConnected(false);
    };

    ws.onclose = (event) => {
      console.log('[RealTimeAssist] WebSocket closed:', event.code);
      setIsConnected(false);
      setIsConnecting(false);

      // Attempt reconnect if unexpected close
      if (session && event.code !== 1000) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connectWebSocket(session.sessionId);
        }, 3000);
      }
    };
  }, [cleanup, session]);

  const startSession = async (request) => {
    try {
      setError(null);
      const newSession = await realTimeApi.createSession(request);
      setSession(newSession);
      setSuggestions([]);
      connectWebSocket(newSession.sessionId);
      return true;
    } catch (err) {
      setError(err.message || 'Failed to start session');
      return false;
    }
  };

  const endSession = async () => {
    if (!session) return;

    try {
      // Send end message through WebSocket
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'end_call' }));
      }

      // Also call API endpoint
      await realTimeApi.endSession(session.sessionId);
    } catch (err) {
      console.error('[RealTimeAssist] Error ending session:', err);
    } finally {
      cleanup();
      setSession(null);
      setSuggestions([]);
    }
  };

  const sendTranscriptUpdate = (text, speaker) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'transcript_update',
        text,
        speaker,
        timestamp: Date.now() / 1000,
      }));
    }
  };

  const acknowledgeSuggestion = (suggestionId) => {
    setSuggestions(prev =>
      prev.map(s =>
        s.id === suggestionId
          ? { ...s, acknowledged: true, acknowledgedAt: new Date().toISOString() }
          : s
      )
    );
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  return {
    session,
    suggestions,
    isConnected,
    isConnecting,
    error,
    startSession,
    endSession,
    sendTranscriptUpdate,
    acknowledgeSuggestion,
  };
}

// =============================================================================
// USE QA RUBRICS HOOK
// =============================================================================

export function useQARubrics() {
  const [rubrics, setRubrics] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRubrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await qaApi.listRubrics();
      setRubrics(response.rubrics);
    } catch (err) {
      setError(err.message || 'Failed to fetch rubrics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRubrics();
  }, [fetchRubrics]);

  return { rubrics, loading, error, refetch: fetchRubrics };
}

// =============================================================================
// USE COACHING CLIPS HOOK
// =============================================================================

export function useCoachingClips(filters = {}) {
  const [clips, setClips] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchClips = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await coachingApi.listClips(filters);
      setClips(response.clips);
    } catch (err) {
      setError(err.message || 'Failed to fetch clips');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    fetchClips();
  }, [fetchClips]);

  const createClip = async (data) => {
    try {
      const clip = await coachingApi.createClip(data);
      setClips(prev => [clip, ...prev]);
      return clip;
    } catch (err) {
      setError(err.message || 'Failed to create clip');
      return null;
    }
  };

  return { clips, loading, error, refetch: fetchClips, createClip };
}

// =============================================================================
// USE COACHING ASSIGNMENTS HOOK
// =============================================================================

export function useCoachingAssignments(filters = {}) {
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchAssignments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await coachingApi.listAssignments(filters);
      setAssignments(response.assignments);
    } catch (err) {
      setError(err.message || 'Failed to fetch assignments');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    fetchAssignments();
  }, [fetchAssignments]);

  const createAssignment = async (data) => {
    try {
      const assignment = await coachingApi.createAssignment(data);
      setAssignments(prev => [assignment, ...prev]);
      return assignment;
    } catch (err) {
      setError(err.message || 'Failed to create assignment');
      return null;
    }
  };

  const completeAssignment = async (assignmentId) => {
    try {
      await coachingApi.completeAssignment(assignmentId);
      setAssignments(prev =>
        prev.map(a =>
          a.assignmentId === assignmentId
            ? { ...a, status: 'completed', completedAt: new Date().toISOString() }
            : a
        )
      );
      return true;
    } catch (err) {
      setError(err.message || 'Failed to complete assignment');
      return false;
    }
  };

  return {
    assignments,
    loading,
    error,
    refetch: fetchAssignments,
    createAssignment,
    completeAssignment,
  };
}

// =============================================================================
// USE TEAM DASHBOARD HOOK
// =============================================================================

export function useTeamDashboard(filters = {}) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.getTeamDashboard(filters);
      setDashboard(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch team dashboard');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return { dashboard, loading, error, refetch: fetchDashboard };
}

// =============================================================================
// USE AGENT DASHBOARD HOOK
// =============================================================================

export function useAgentDashboard(agentId, filters = {}) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDashboard = useCallback(async () => {
    if (!agentId) return;

    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.getAgentDashboard(agentId, filters);
      setDashboard(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch agent dashboard');
    } finally {
      setLoading(false);
    }
  }, [agentId, JSON.stringify(filters)]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return { dashboard, loading, error, refetch: fetchDashboard };
}

// =============================================================================
// USE COMPLIANCE DASHBOARD HOOK
// =============================================================================

export function useComplianceDashboard(filters = {}) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.getComplianceDashboard(filters);
      setDashboard(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch compliance dashboard');
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(filters)]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return { dashboard, loading, error, refetch: fetchDashboard };
}
