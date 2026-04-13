/**
 * useCallMonitor - Call session lifecycle management for mobile Call Intelligence
 *
 * Manages:
 * - Session creation/ending via callMonitoringAPI
 * - Recording state (isRecording, isStarting, isStopping)
 * - Duration timer
 * - Status messaging
 * - Client lookup (manual search + auto-detection from transcript)
 *
 * Extracted from MobileCallIntelligence.jsx
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from '../utils/toast';
import { callMonitoringAPI } from '../services/api';
import { haptics } from '../services/nativeServices';
import { auditLog, AUDIT_EVENTS } from '../services/mobileAuditLogger';

function extractClientNameFromTranscript(text) {
  const patterns = [
    /my name is ([A-Z][a-z]+ [A-Z][a-z]+)/i,
    /i'm ([A-Z][a-z]+ [A-Z][a-z]+)/i,
    /this is ([A-Z][a-z]+ [A-Z][a-z]+)/i,
    /i am ([A-Z][a-z]+ [A-Z][a-z]+)/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m) return m[1];
  }
  return null;
}

const useCallMonitor = () => {
  // Session state
  const [sessionId, setSessionId] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');

  // Client info state
  const [clientInfo, setClientInfo] = useState(null);
  const [clientSearchValue, setClientSearchValue] = useState('');
  const [clientSearchLoading, setClientSearchLoading] = useState(false);
  const clientDetectedRef = useRef(false);

  // Refs
  const timerRef = useRef(null);
  const sessionIdRef = useRef(null);

  // Keep ref in sync
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Duration timer
  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        setRecordingDuration((d) => d + 1);
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [isRecording]);

  // Client detection from transcript
  const attemptClientDetection = useCallback(async (text) => {
    if (clientDetectedRef.current) return;
    const name = extractClientNameFromTranscript(text);
    if (!name) return;
    clientDetectedRef.current = true;
    try {
      const result = await callMonitoringAPI.searchClients({ name: name, limit: 1 });
      const first = result?.clients?.[0] || result?.results?.[0] || result?.[0];
      if (first) {
        setClientInfo({ id: first.id, name: first.name || first.full_name, phone: first.phone });
        setStatusMsg(`Client identified: ${first.name || first.full_name}`);
      }
    } catch {
      // Best-effort
    }
  }, []);

  // Manual client lookup
  const handleClientSearch = useCallback(async () => {
    const query = clientSearchValue.trim();
    if (!query) return;
    setClientSearchLoading(true);
    try {
      const isPhone = /^[\d\s\-().+]{7,}$/.test(query);
      let result;
      if (isPhone) {
        result = await callMonitoringAPI.lookupCaller(query.replace(/\D/g, ''));
        if (result?.client || result?.id) {
          const c = result.client || result;
          setClientInfo({ id: c.id, name: c.name || c.full_name, phone: c.phone });
          setClientSearchValue('');
          toast.success(`Found: ${c.name || c.full_name}`);
          return;
        }
      }
      result = await callMonitoringAPI.searchClients({ name: query, limit: 1 });
      const first = result?.clients?.[0] || result?.results?.[0] || result?.[0];
      if (first) {
        setClientInfo({ id: first.id, name: first.name || first.full_name, phone: first.phone });
        setClientSearchValue('');
        toast.success(`Found: ${first.name || first.full_name}`);
      } else {
        setClientInfo({ id: null, name: query, phone: null });
        setClientSearchValue('');
        toast(`Using "${query}" as client name`, { icon: '\u2139\uFE0F' });
      }
    } catch (err) {
      toast.error('Client lookup failed');
    } finally {
      setClientSearchLoading(false);
    }
  }, [clientSearchValue]);

  const clearClient = useCallback(() => {
    setClientInfo(null);
    clientDetectedRef.current = false;
  }, []);

  // Start recording session
  const handleStartRecording = useCallback(async ({
    onSessionCreated,
    startSpeechRecognition,
  }) => {
    if (isStarting || isRecording) return;
    setIsStarting(true);
    setStatusMsg('Starting session...');

    try {
      haptics.medium();
    } catch {}

    try {
      const sessionData = await callMonitoringAPI.createSession({
        capture_mode: 'mobile_app',
        metadata: {
          source: 'mobile',
          realtime_processing: true,
          client_name: clientInfo?.name || null,
        },
      });

      const sid = sessionData?.id || sessionData?.session_id;
      if (!sid) throw new Error('No session ID returned');

      setSessionId(sid);
      setRecordingDuration(0);
      clientDetectedRef.current = !!clientInfo;

      if (onSessionCreated) onSessionCreated(sid);

      const started = startSpeechRecognition();
      // Still create session even if speech recognition fails

      setIsRecording(true);
      setStatusMsg('Listening...');
      auditLog(AUDIT_EVENTS.PII_ACCESSED, { action: 'call_recording_started', sessionId: sid });

      try {
        haptics.success();
      } catch {}
    } catch (err) {
      toast.error('Failed to start recording session');
      setStatusMsg('');
      console.error('Start recording error:', err);
    } finally {
      setIsStarting(false);
    }
  }, [isStarting, isRecording, clientInfo]);

  // Stop recording session
  const handleStopRecording = useCallback(async ({
    stopSpeechRecognition,
    transcript,
    onStopComplete,
  }) => {
    if (isStopping || !isRecording) return;
    setIsStopping(true);
    setStatusMsg('Processing...');

    try {
      haptics.heavy();
    } catch {}

    stopSpeechRecognition();
    setIsRecording(false);

    const sid = sessionIdRef.current;
    if (!sid) {
      setIsStopping(false);
      setStatusMsg('');
      return;
    }

    try {
      await callMonitoringAPI.endSession(sid, {
        run_agents: true,
        client_id: clientInfo?.id || null,
        final_transcript: transcript,
        instructions: {
          generate_tasks: true,
          generate_follow_ups: true,
        },
      });

      setStatusMsg('Analysis complete');
      if (onStopComplete) onStopComplete(sid);

      try {
        haptics.success();
      } catch {}
    } catch (err) {
      toast.error('Failed to end session -- artifacts may still be generated');
      console.error('End session error:', err);
      setStatusMsg('');
    } finally {
      setIsStopping(false);
    }
  }, [isStopping, isRecording, clientInfo]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
    };
  }, []);

  return {
    // Session state
    sessionId,
    sessionIdRef,
    isRecording,
    isStarting,
    isStopping,
    recordingDuration,
    statusMsg,

    // Client state
    clientInfo,
    clientSearchValue,
    clientSearchLoading,
    setClientSearchValue,
    handleClientSearch,
    clearClient,
    attemptClientDetection,

    // Actions
    handleStartRecording,
    handleStopRecording,
  };
};

export default useCallMonitor;
