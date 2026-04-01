/**
 * useMobileAudioCapture - Audio capture + WebSocket streaming for mobile CI
 *
 * Captures microphone audio via getUserMedia (works in iOS WKWebView),
 * streams PCM16 base64 chunks over WebSocket to the backend, which
 * forwards them to Deepgram for real-time transcription.
 *
 * Audio flow:
 *   getUserMedia (16kHz mono) → ScriptProcessor → PCM16 → base64
 *   → WebSocket → backend → Deepgram → transcript text → WebSocket back
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';

const SAMPLE_RATE = 16000;

// Build WebSocket base URL from API base
const WS_BASE_URL = API_BASE_URL
  .replace('https://', 'wss://')
  .replace('http://', 'ws://');

const useMobileAudioCapture = ({ sessionId, onTranscript, enabled = true }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState(null);
  const [error, setError] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('disconnected'); // disconnected, connecting, connected, error
  const [interimText, setInterimText] = useState('');

  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const wsRef = useRef(null);
  const recordingRef = useRef(false);

  // Convert Float32 to Int16 PCM
  const floatTo16BitPCM = useCallback((float32Array) => {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
  }, []);

  // Initialize AudioContext
  const initAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE,
      });
    }
    return audioContextRef.current;
  }, []);

  // Connect WebSocket to backend audio stream endpoint
  const connectWebSocket = useCallback((sid) => {
    return new Promise((resolve, reject) => {
      const token = localStorage.getItem('token');
      // Security: Browser WebSocket API does not support Authorization headers; token in URL is the only option.
      const url = `${WS_BASE_URL}/api/v1/call-monitoring/sessions/${sid}/audio-stream?token=${token}`;

      setConnectionStatus('connecting');
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('[MobileAudioCapture] WebSocket connected');
        setConnectionStatus('connected');
        resolve(ws);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'transcript') {
            if (data.is_final) {
              setInterimText('');
              onTranscript?.(data.text);
            } else {
              setInterimText(data.text);
            }
          } else if (data.type === 'error') {
            console.error('[MobileAudioCapture] Server error:', data.message);
            setError(data.message);
          } else if (data.type === 'connected') {
            console.log('[MobileAudioCapture] Session confirmed:', data.session_id);
          }
        } catch (e) {
          console.error('[MobileAudioCapture] Message parse error:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('[MobileAudioCapture] WebSocket error:', event);
        setConnectionStatus('error');
        setError('Connection to transcription service failed');
        reject(new Error('WebSocket connection failed'));
      };

      ws.onclose = (event) => {
        console.log('[MobileAudioCapture] WebSocket closed:', event.code);
        setConnectionStatus('disconnected');
        wsRef.current = null;
      };

      wsRef.current = ws;
    });
  }, [onTranscript]);

  // Start capture
  const startCapture = useCallback(async () => {
    if (!enabled || !sessionId) return;

    setError(null);

    try {
      // Connect WebSocket first
      await connectWebSocket(sessionId);

      // Request microphone
      console.log('[MobileAudioCapture] Requesting microphone access...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      setHasPermission(true);
      mediaStreamRef.current = stream;

      const audioContext = initAudioContext();
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      recordingRef.current = true;

      processor.onaudioprocess = (e) => {
        if (recordingRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
          const float32Data = e.inputBuffer.getChannelData(0);
          const int16Data = floatTo16BitPCM(float32Data);
          const base64Audio = btoa(
            String.fromCharCode(...new Uint8Array(int16Data.buffer))
          );

          wsRef.current.send(
            JSON.stringify({ type: 'audio', data: base64Audio })
          );
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setIsRecording(true);
      console.log('[MobileAudioCapture] Recording started');
    } catch (err) {
      console.error('[MobileAudioCapture] Error starting:', err);

      if (err.name === 'NotAllowedError') {
        setHasPermission(false);
        setError('Microphone access denied. Please allow microphone access in Settings.');
      } else if (err.name === 'NotFoundError') {
        setError('No microphone found.');
      } else {
        setError(`Failed to start recording: ${err.message}`);
      }

      // Cleanup WebSocket if mic failed
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    }
  }, [enabled, sessionId, connectWebSocket, initAudioContext, floatTo16BitPCM]);

  // Stop capture
  const stopCapture = useCallback(() => {
    console.log('[MobileAudioCapture] Stopping capture...');

    recordingRef.current = false;
    setIsRecording(false);
    setInterimText('');

    // Stop audio processing
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    // Send stop signal and close WebSocket
    if (wsRef.current) {
      try {
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'stop' }));
        }
        wsRef.current.close();
      } catch (e) {
        // ignore close errors
      }
      wsRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recordingRef.current = false;

      if (processorRef.current) {
        processorRef.current.disconnect();
      }
      if (sourceRef.current) {
        sourceRef.current.disconnect();
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (e) {}
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  return {
    isRecording,
    hasPermission,
    error,
    connectionStatus,
    interimText,
    startCapture,
    stopCapture,
  };
};

export default useMobileAudioCapture;
