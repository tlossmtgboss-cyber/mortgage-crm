/**
 * useAriaVoice — Speech recognition hook for mobile Aria voice input.
 *
 * Uses native Capacitor speech recognition on iOS/Android,
 * falls back to Web Speech API on browsers.
 *
 * Usage:
 *   const { isRecording, isSupported, transcript, startRecording, stopRecording, toggleRecording }
 *     = useAriaVoice({ onTranscript, onFinalTranscript });
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { isAvailable, startListening } from '../services/speechService';

export function useAriaVoice({ onTranscript, onFinalTranscript, language = 'en-US' } = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isSupported, setIsSupported] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState(null);

  const controllerRef = useRef(null);
  const shouldBeRecordingRef = useRef(false);
  const onTranscriptRef = useRef(onTranscript);
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef(null);
  const lastSpeechRef = useRef(0);
  const silenceIntervalRef = useRef(null);

  const MAX_RETRIES = 3;
  const SILENCE_TIMEOUT_MS = 10000; // 10s silence → stop listening, back to tap-to-speak

  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onFinalTranscriptRef.current = onFinalTranscript; }, [onFinalTranscript]);

  // Check availability on mount
  useEffect(() => {
    let cancelled = false;
    isAvailable().then((available) => {
      if (!cancelled) setIsSupported(available);
    });
    return () => { cancelled = true; };
  }, []);

  const doStart = useCallback(async () => {
    if (!isSupported) return;

    // Stop any previous controller before starting a new one to prevent leaks
    if (controllerRef.current) {
      try { await controllerRef.current.stop(); } catch { /* already stopped */ }
      controllerRef.current = null;
    }

    try {
      const controller = await startListening({
        language,
        partialResults: true,
        onPartialResult: (text) => {
          setTranscript(text);
          onTranscriptRef.current?.(text);
          lastSpeechRef.current = Date.now();
        },
        onResult: (text) => {
          setTranscript(text);
          onTranscriptRef.current?.(text);
          onFinalTranscriptRef.current?.(text);
          retryCountRef.current = 0;
          // Final result received — stop recording, return to tap-to-speak
          shouldBeRecordingRef.current = false;
          clearInterval(silenceIntervalRef.current);
        },
        onError: (err) => {
          console.error('[useAriaVoice] Speech error:', err);
          if (err === 'not-allowed' || err === 'permission-denied') {
            shouldBeRecordingRef.current = false;
            setIsRecording(false);
            setTranscript('');
            setError('Microphone access denied. Please enable it in Settings.');
          } else {
            setError('Speech recognition error. Tap to try again.');
          }
        },
        onEnd: () => {
          // Auto-restart with backoff if user still intends to record
          if (shouldBeRecordingRef.current && retryCountRef.current < MAX_RETRIES) {
            const delay = Math.pow(2, retryCountRef.current) * 1000; // 1s, 2s, 4s
            retryCountRef.current++;
            retryTimerRef.current = setTimeout(() => {
              if (shouldBeRecordingRef.current) {
                doStart();
              }
            }, delay);
          } else if (retryCountRef.current >= MAX_RETRIES) {
            // Circuit breaker: stop after max retries
            shouldBeRecordingRef.current = false;
            setIsRecording(false);
            clearInterval(silenceIntervalRef.current);
            setError('Speech recognition stopped. Tap the mic to try again.');
          } else {
            // Result was submitted or user stopped — clean up recording state
            setIsRecording(false);
            clearInterval(silenceIntervalRef.current);
          }
        },
      });

      controllerRef.current = controller;
    } catch (err) {
      console.error('[useAriaVoice] Failed to start:', err);
      shouldBeRecordingRef.current = false;
      setIsRecording(false);
      controllerRef.current = null;
    }
  }, [isSupported, language]);

  const startRecording = useCallback(() => {
    if (!isSupported || shouldBeRecordingRef.current) return;

    setTranscript('');
    setError(null);
    shouldBeRecordingRef.current = true;
    retryCountRef.current = 0;
    setIsRecording(true);
    lastSpeechRef.current = Date.now();

    // 10-second silence timeout — returns to tap-to-speak if no speech detected
    clearInterval(silenceIntervalRef.current);
    silenceIntervalRef.current = setInterval(() => {
      if (shouldBeRecordingRef.current && Date.now() - lastSpeechRef.current > SILENCE_TIMEOUT_MS) {
        clearInterval(silenceIntervalRef.current);
        shouldBeRecordingRef.current = false;
        if (controllerRef.current) {
          controllerRef.current.stop().catch(() => {});
          controllerRef.current = null;
        }
        setIsRecording(false);
        setTranscript('');
      }
    }, 1000);

    doStart();
  }, [isSupported, doStart]);

  const stopRecording = useCallback(async () => {
    shouldBeRecordingRef.current = false;
    clearTimeout(retryTimerRef.current);
    clearInterval(silenceIntervalRef.current);

    if (controllerRef.current) {
      try {
        await controllerRef.current.stop();
      } catch {
        // stop() can throw if already ended
      }
      controllerRef.current = null;
    }

    setIsRecording(false);
    setTranscript('');
  }, []);

  const toggleRecording = useCallback(() => {
    if (shouldBeRecordingRef.current) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [startRecording, stopRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      shouldBeRecordingRef.current = false;
      clearTimeout(retryTimerRef.current);
      clearInterval(silenceIntervalRef.current);
      if (controllerRef.current) {
        try { controllerRef.current.stop(); } catch {}
        controllerRef.current = null;
      }
    };
  }, []);

  return {
    isRecording,
    isSupported,
    transcript,
    error,
    startRecording,
    stopRecording,
    toggleRecording,
  };
}

export default useAriaVoice;
