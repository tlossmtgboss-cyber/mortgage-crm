/**
 * useCallTranscription - Real-time transcription for mobile Call Intelligence
 *
 * Manages:
 * - Speech recognition start/stop (via speechService)
 * - Live transcript accumulation (final + interim text)
 * - Transcript chunk queue (batched sends to backend)
 * - Offline buffering (localStorage) for failed chunk sends
 * - Auto-scroll ref for transcript container
 *
 * Extracted from MobileCallIntelligence.jsx
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { callMonitoringAPI } from '../services/api';

// ---------------------------------------------------------------------------
// localStorage helpers for offline chunk buffering
// ---------------------------------------------------------------------------
const OFFLINE_KEY_PREFIX = 'ci_offline_chunks_';

function getOfflineSessionKeys() {
  const keys = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(OFFLINE_KEY_PREFIX)) {
      keys.push(key);
    }
  }
  return keys;
}

function readOfflineChunks(sessionId) {
  try {
    const raw = localStorage.getItem(`${OFFLINE_KEY_PREFIX}${sessionId}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeOfflineChunks(sessionId, chunks) {
  try {
    if (chunks.length === 0) {
      localStorage.removeItem(`${OFFLINE_KEY_PREFIX}${sessionId}`);
    } else {
      localStorage.setItem(`${OFFLINE_KEY_PREFIX}${sessionId}`, JSON.stringify(chunks));
    }
  } catch {
    // localStorage full or unavailable -- nothing we can do
  }
}

function storeOfflineChunk(sessionId, chunk) {
  const existing = readOfflineChunks(sessionId);
  existing.push(chunk);
  writeOfflineChunks(sessionId, existing);
}

function clearOfflineChunks(sessionId) {
  try {
    localStorage.removeItem(`${OFFLINE_KEY_PREFIX}${sessionId}`);
  } catch {
    // Ignore
  }
}

function countAllOfflineChunks() {
  let total = 0;
  for (const key of getOfflineSessionKeys()) {
    try {
      const chunks = JSON.parse(localStorage.getItem(key) || '[]');
      total += chunks.length;
    } catch {
      // skip malformed entries
    }
  }
  return total;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
const useCallTranscription = ({ sessionIdRef, attemptClientDetection }) => {
  // Transcript state
  const [transcript, setTranscript] = useState('');
  const [interimText, setInterimText] = useState('');
  const [pendingChunksCount, setPendingChunksCount] = useState(0);
  const transcriptRef = useRef(null); // DOM ref for auto-scroll

  // Speech recognition ref
  const recognitionRef = useRef(null);

  // Transcript chunk queue refs
  const transcriptQueueRef = useRef([]);
  const transcriptSendingRef = useRef(false);

  // Guard to prevent concurrent flushOfflineChunks runs
  const offlineFlushingRef = useRef(false);

  // Refresh the pending count from localStorage
  const refreshPendingCount = useCallback(() => {
    setPendingChunksCount(countAllOfflineChunks());
  }, []);

  // ------------------------------------------------------------------
  // flushOfflineChunks — drain localStorage buffer for ALL sessions
  // ------------------------------------------------------------------
  const flushOfflineChunks = useCallback(async () => {
    if (offlineFlushingRef.current) return;
    offlineFlushingRef.current = true;

    try {
      const keys = getOfflineSessionKeys();
      for (const key of keys) {
        const sid = key.slice(OFFLINE_KEY_PREFIX.length);
        let chunks = readOfflineChunks(sid);
        if (chunks.length === 0) continue;

        const remaining = [];
        for (const chunk of chunks) {
          try {
            await callMonitoringAPI.appendTranscriptChunk(chunk.sessionId, {
              text: chunk.text,
              speaker_label: chunk.speaker_label,
              timestamp: chunk.timestamp,
              process_realtime: true,
            });
          } catch {
            // Still offline or server error — keep for next attempt
            remaining.push(chunk);
          }
        }
        writeOfflineChunks(sid, remaining);
      }
    } finally {
      offlineFlushingRef.current = false;
      refreshPendingCount();
    }
  }, [refreshPendingCount]);

  // Auto-scroll transcript container
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript, interimText]);

  // ------------------------------------------------------------------
  // On mount: flush any leftover offline chunks + listen for 'online'
  // ------------------------------------------------------------------
  useEffect(() => {
    // Rehydrate count immediately
    refreshPendingCount();
    // Attempt to flush any leftovers from previous sessions
    flushOfflineChunks();

    const handleOnline = () => {
      flushOfflineChunks();
    };
    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('online', handleOnline);
    };
  }, [flushOfflineChunks, refreshPendingCount]);

  // Transcript chunk sender (batched / queued)
  const flushTranscriptQueue = useCallback(async () => {
    if (transcriptSendingRef.current) return;
    if (transcriptQueueRef.current.length === 0) return;
    const sid = sessionIdRef.current;
    if (!sid) return;

    transcriptSendingRef.current = true;
    const chunk = transcriptQueueRef.current.shift();
    const timestamp = new Date().toISOString();
    try {
      await callMonitoringAPI.appendTranscriptChunk(sid, {
        text: chunk,
        speaker_label: 'user',
        timestamp,
        process_realtime: true,
      });
      // Success — piggyback: try to flush any offline chunks too
      flushOfflineChunks();
    } catch {
      // Network failure — buffer to localStorage instead of dropping
      storeOfflineChunk(sid, {
        text: chunk,
        speaker_label: 'user',
        timestamp,
        sessionId: sid,
      });
      refreshPendingCount();
    } finally {
      transcriptSendingRef.current = false;
      // Drain the rest
      if (transcriptQueueRef.current.length > 0) {
        flushTranscriptQueue();
      }
    }
  }, [sessionIdRef, flushOfflineChunks, refreshPendingCount]);

  const enqueueTranscriptChunk = useCallback(
    (text) => {
      transcriptQueueRef.current.push(text);
      flushTranscriptQueue();
    },
    [flushTranscriptQueue]
  );

  // Start speech recognition (native Capacitor + Web Speech API fallback)
  const startSpeechRecognition = useCallback(async () => {
    try {
      const speechService = await import('../services/speechService');
      const available = await speechService.isAvailable();
      if (!available) {
        const { toast: t } = await import('../utils/toast');
        t.error('Speech recognition is not supported on this device.');
        return false;
      }

      await speechService.requestPermission();

      const controller = await speechService.startListening({
        language: 'en-US',
        partialResults: true,
        onPartialResult: (text) => {
          setInterimText(text);
        },
        onResult: (finalText) => {
          if (finalText) {
            setTranscript((prev) => (prev ? prev + ' ' + finalText : finalText));
            enqueueTranscriptChunk(finalText);
            attemptClientDetection(finalText);
          }
          setInterimText('');
        },
        onError: (error) => {
          console.warn('Speech recognition error:', error);
        },
        onEnd: () => {
          setInterimText('');
          // Auto-restart if still recording
          if (sessionIdRef.current && recognitionRef.current) {
            startSpeechRecognition();
          }
        },
      });

      recognitionRef.current = controller;
      return true;
    } catch (err) {
      console.error('Could not start speech recognition:', err);
      return false;
    }
  }, [enqueueTranscriptChunk, attemptClientDetection, sessionIdRef]);

  const stopSpeechRecognition = useCallback(async () => {
    if (recognitionRef.current) {
      try {
        await recognitionRef.current.stop();
      } catch {
        // Ignore
      }
      recognitionRef.current = null;
    }
    setInterimText('');
  }, []);

  // Reset transcript state (for new sessions)
  const resetTranscript = useCallback(() => {
    setTranscript('');
    setInterimText('');
    transcriptQueueRef.current = [];
  }, []);

  // Clear offline chunks for the current session (call on successful session end)
  const clearSessionOfflineChunks = useCallback(() => {
    const sid = sessionIdRef.current;
    if (sid) {
      clearOfflineChunks(sid);
      refreshPendingCount();
    }
  }, [sessionIdRef, refreshPendingCount]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopSpeechRecognition();
    };
  }, [stopSpeechRecognition]);

  return {
    // State
    transcript,
    interimText,
    pendingChunksCount,
    transcriptRef, // DOM ref for the scrollable container

    // Actions
    startSpeechRecognition,
    stopSpeechRecognition,
    resetTranscript,
    clearSessionOfflineChunks,
  };
};

export default useCallTranscription;
