/**
 * useCallTranscription - Real-time transcription for mobile Call Intelligence
 *
 * Manages:
 * - Speech recognition start/stop (via speechService)
 * - Live transcript accumulation (final + interim text)
 * - Transcript chunk queue (batched sends to backend)
 * - Auto-scroll ref for transcript container
 *
 * Extracted from MobileCallIntelligence.jsx
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { callMonitoringAPI } from '../services/api';

const useCallTranscription = ({ sessionIdRef, attemptClientDetection }) => {
  // Transcript state
  const [transcript, setTranscript] = useState('');
  const [interimText, setInterimText] = useState('');
  const transcriptRef = useRef(null); // DOM ref for auto-scroll

  // Speech recognition ref
  const recognitionRef = useRef(null);

  // Transcript chunk queue refs
  const transcriptQueueRef = useRef([]);
  const transcriptSendingRef = useRef(false);

  // Auto-scroll transcript container
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript, interimText]);

  // Transcript chunk sender (batched / queued)
  const flushTranscriptQueue = useCallback(async () => {
    if (transcriptSendingRef.current) return;
    if (transcriptQueueRef.current.length === 0) return;
    const sid = sessionIdRef.current;
    if (!sid) return;

    transcriptSendingRef.current = true;
    const chunk = transcriptQueueRef.current.shift();
    try {
      await callMonitoringAPI.appendTranscriptChunk(sid, {
        text: chunk,
        speaker_label: 'user',
        timestamp: new Date().toISOString(),
        process_realtime: true,
      });
    } catch {
      // Non-fatal -- transcript chunk dropped; recording continues
    } finally {
      transcriptSendingRef.current = false;
      // Drain the rest
      if (transcriptQueueRef.current.length > 0) {
        flushTranscriptQueue();
      }
    }
  }, [sessionIdRef]);

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
        const toast = (await import('react-hot-toast')).default;
        toast.error('Speech recognition is not supported on this device.');
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
    transcriptRef, // DOM ref for the scrollable container

    // Actions
    startSpeechRecognition,
    stopSpeechRecognition,
    resetTranscript,
  };
};

export default useCallTranscription;
