/**
 * Hook for managing Power Dialer sessions
 * @fileoverview React hook for dialer session state management
 */

import { useState, useEffect, useCallback } from 'react';
import { useDialerWebSocket } from './useDialerWebSocket';
import axios from 'axios';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * Hook for managing a dialer session
 * @param {string} agentId - Agent ID for the session
 * @returns {Object} Session state and controls
 */
export function useDialerSession(agentId) {
  const [session, setSession] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showDispositionModal, setShowDispositionModal] = useState(false);
  const [currentCallData, setCurrentCallData] = useState(null);

  // Get auth token
  const getAuthHeader = useCallback(() => ({
    Authorization: `Bearer ${getToken()}`
  }), []);

  // Handle WebSocket messages
  const handleWebSocketMessage = useCallback((event) => {
    console.log('Dialer WebSocket event:', event);

    switch (event.type) {
      case 'dialer.status':
        setSession(prev => prev ? {
          ...prev,
          status: event.status,
          completed_tasks: event.completed_tasks,
          total_tasks: event.total_tasks
        } : null);
        break;

      case 'dialer.call.started':
        setSession(prev => prev ? {
          ...prev,
          current_task: {
            task_id: event.task_id,
            name: event.contact?.name,
            phone: event.contact?.phone,
            context: event.contact?.context,
            call_sid: event.call_sid
          }
        } : null);
        break;

      case 'dialer.call.completed':
      case 'call_status_update':
        setCurrentCallData(event);
        if (event.show_disposition_modal) {
          setShowDispositionModal(true);
        }
        // Update session state
        setSession(prev => prev ? {
          ...prev,
          current_task: null
        } : null);
        break;

      case 'click_to_dial_status':
        // For standalone click-to-dial calls
        setCurrentCallData(event);
        if (event.show_disposition_modal) {
          setShowDispositionModal(true);
        }
        break;

      case 'disposition_saved':
        // Disposition was saved, close modal
        setShowDispositionModal(false);
        setCurrentCallData(null);
        // Refresh session to get updated counts
        if (session?.session_id) {
          fetchSession(session.session_id);
        }
        break;

      default:
        console.log('Unhandled dialer event:', event.type);
    }
  }, [session?.session_id]);

  // WebSocket connection
  const { isConnected, send } = useDialerWebSocket(agentId, {
    onMessage: handleWebSocketMessage,
    onConnect: () => console.log('Dialer WebSocket connected'),
    onDisconnect: () => console.log('Dialer WebSocket disconnected')
  });

  // Fetch session details
  const fetchSession = useCallback(async (sessionId) => {
    try {
      const response = await axios.get(
        `${API_BASE}/api/v1/dialer/sessions/${sessionId}`,
        { headers: getAuthHeader() }
      );
      setSession(response.data);
      return response.data;
    } catch (err) {
      console.error('Error fetching session:', err);
      return null;
    }
  }, [getAuthHeader]);

  // Start a new session
  const startSession = useCallback(async (taskIds) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await axios.post(
        `${API_BASE}/api/v1/dialer/sessions`,
        { task_ids: taskIds },
        { headers: getAuthHeader() }
      );

      if (response.data.success && response.data.session_id) {
        // Fetch full session details
        const sessionData = await fetchSession(response.data.session_id);
        return sessionData;
      } else {
        throw new Error(response.data.error || 'Failed to start session');
      }
    } catch (err) {
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to start session';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [getAuthHeader, fetchSession]);

  // Pause session
  const pauseSession = useCallback(async () => {
    if (!session?.session_id) return;

    try {
      await axios.post(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/pause`,
        {},
        { headers: getAuthHeader() }
      );
      setSession(prev => prev ? { ...prev, status: 'PAUSED' } : null);
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Failed to pause session';
      setError(errorMessage);
    }
  }, [session?.session_id, getAuthHeader]);

  // Resume session
  const resumeSession = useCallback(async () => {
    if (!session?.session_id) return;

    try {
      await axios.post(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/resume`,
        {},
        { headers: getAuthHeader() }
      );
      setSession(prev => prev ? { ...prev, status: 'ACTIVE' } : null);
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Failed to resume session';
      setError(errorMessage);
    }
  }, [session?.session_id, getAuthHeader]);

  // Stop session
  const stopSession = useCallback(async () => {
    if (!session?.session_id) return;

    try {
      await axios.post(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/stop`,
        {},
        { headers: getAuthHeader() }
      );
      setSession(null);
      setCurrentCallData(null);
      setShowDispositionModal(false);
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Failed to stop session';
      setError(errorMessage);
    }
  }, [session?.session_id, getAuthHeader]);

  // Skip current task
  const skipCurrentTask = useCallback(async (reason = 'manual_skip') => {
    if (!session?.session_id || !session?.current_task?.task_id) return;

    try {
      await axios.post(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/tasks/${session.current_task.task_id}/skip`,
        { reason },
        { headers: getAuthHeader() }
      );
      // Refresh session
      await fetchSession(session.session_id);
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Failed to skip task';
      setError(errorMessage);
    }
  }, [session?.session_id, session?.current_task?.task_id, getAuthHeader, fetchSession]);

  // Initiate call for a task
  const initiateCall = useCallback(async (taskId) => {
    if (!session?.session_id) return;

    try {
      const response = await axios.post(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/call/${taskId}`,
        {},
        { headers: getAuthHeader() }
      );
      return response.data;
    } catch (err) {
      const errorMessage = err.response?.data?.detail || 'Failed to initiate call';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  }, [session?.session_id, getAuthHeader]);

  // Get next task
  const getNextTask = useCallback(async () => {
    if (!session?.session_id) return null;

    try {
      const response = await axios.get(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/next-task`,
        { headers: getAuthHeader() }
      );
      return response.data.next_task;
    } catch (err) {
      console.error('Error getting next task:', err);
      return null;
    }
  }, [session?.session_id, getAuthHeader]);

  // Check for active session on mount
  const checkActiveSession = useCallback(async () => {
    try {
      const response = await axios.get(
        `${API_BASE}/api/v1/dialer/sessions/active`,
        { headers: getAuthHeader() }
      );

      if (response.data.active_session) {
        setSession(response.data.active_session);
      }
    } catch (err) {
      console.error('Error checking active session:', err);
    }
  }, [getAuthHeader]);

  // Check for active session on mount
  useEffect(() => {
    if (agentId) {
      checkActiveSession();
    }
  }, [agentId, checkActiveSession]);

  // Clear error after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return {
    // State
    session,
    isLoading,
    error,
    isConnected,
    showDispositionModal,
    currentCallData,

    // Setters
    setShowDispositionModal,
    setError,

    // Actions
    startSession,
    pauseSession,
    resumeSession,
    stopSession,
    skipCurrentTask,
    initiateCall,
    getNextTask,
    checkActiveSession,
    refreshSession: () => session?.session_id && fetchSession(session.session_id)
  };
}

export default useDialerSession;
