// WebSocket hook for voice conversation with Aria
import { useState, useRef, useCallback, useEffect } from 'react';
import { getToken } from '../../../utils/tokenStore';

const useVoiceWebSocket = ({ onTranscript, onAudio, onStatusChange, onError, onSessionInfo }) => {
  const [status, setStatus] = useState('idle'); // idle, connecting, connected, listening, processing, speaking, error
  const [sessionId, setSessionId] = useState(null);
  const [sttEnabled, setSttEnabled] = useState(false);

  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;

  // API base URL
  const isLocalDev = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );
  const WS_BASE_URL = isLocalDev ? 'ws://localhost:8000' : 'wss://api.perenniaai.com';
  const WS_ENDPOINT = '/api/v1/mobile-voice/ws/voice';

  // Update status and notify parent
  const updateStatus = useCallback((newStatus) => {
    setStatus(newStatus);
    onStatusChange?.(newStatus);
  }, [onStatusChange]);

  // Connect to WebSocket
  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[useVoiceWebSocket] Already connected');
      return;
    }

    updateStatus('connecting');

    try {
      const token = getToken();
      // Security: Browser WebSocket API does not support Authorization headers; token in URL is the only option.
      const wsUrl = `${WS_BASE_URL}${WS_ENDPOINT}?token=${token}`;

      console.log('[useVoiceWebSocket] Connecting to:', wsUrl);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[useVoiceWebSocket] Connected');
        reconnectAttempts.current = 0;
        updateStatus('connected');
      };

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[useVoiceWebSocket] Received:', data.type);

          switch (data.type) {
            case 'session_started':
              setSessionId(data.session_id);
              setSttEnabled(data.stt_enabled || false);
              updateStatus('connected');
              onSessionInfo?.({ sttEnabled: data.stt_enabled || false, ttsEnabled: data.tts_enabled || false });
              break;

            case 'listening':
              updateStatus('listening');
              break;

            case 'transcript':
              onTranscript?.({
                text: data.text,
                isFinal: data.is_final,
                role: 'user'
              });
              break;

            case 'processing':
              updateStatus('processing');
              break;

            case 'speaking':
              updateStatus('speaking');
              onTranscript?.({
                text: data.text,
                isFinal: true,
                role: 'assistant'
              });
              break;

            case 'audio':
              onAudio?.({
                data: data.data,
                format: data.format || 'mp3'
              });
              break;

            case 'speech_complete':
              updateStatus('listening');
              break;

            case 'interrupted':
              updateStatus('listening');
              break;

            case 'pong':
              // Heartbeat response
              break;

            case 'error':
              console.error('[useVoiceWebSocket] Server error:', data.message);
              onError?.(data.message);
              updateStatus('error');
              break;

            default:
              console.log('[useVoiceWebSocket] Unhandled message type:', data.type);
          }
        } catch (err) {
          console.error('[useVoiceWebSocket] Error parsing message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('[useVoiceWebSocket] WebSocket error:', err);
        onError?.('Connection error');
        updateStatus('error');
      };

      ws.onclose = (event) => {
        console.log('[useVoiceWebSocket] WebSocket closed:', event.code, event.reason);

        // Attempt reconnect if not intentionally closed
        if (reconnectAttempts.current < maxReconnectAttempts && status !== 'idle') {
          reconnectAttempts.current++;
          console.log(`[useVoiceWebSocket] Reconnecting... (attempt ${reconnectAttempts.current})`);
          setTimeout(() => connect(), 2000);
        } else {
          updateStatus('idle');
        }
      };

    } catch (err) {
      console.error('[useVoiceWebSocket] Connection error:', err);
      onError?.(err.message);
      updateStatus('error');
    }
  }, [WS_BASE_URL, updateStatus, onTranscript, onAudio, onError, status]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    console.log('[useVoiceWebSocket] Disconnecting...');
    reconnectAttempts.current = maxReconnectAttempts; // Prevent reconnect

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setSessionId(null);
    updateStatus('idle');
  }, [updateStatus]);

  // Send message to WebSocket
  const send = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    console.warn('[useVoiceWebSocket] Cannot send - not connected');
    return false;
  }, []);

  // Start listening for audio
  const startListening = useCallback(() => {
    return send({ type: 'start_listening' });
  }, [send]);

  // Stop listening
  const stopListening = useCallback(() => {
    return send({ type: 'stop_listening' });
  }, [send]);

  // Send audio data
  const sendAudio = useCallback((base64Audio) => {
    return send({ type: 'audio', data: base64Audio });
  }, [send]);

  // Send text input (fallback)
  const sendText = useCallback((text) => {
    return send({ type: 'text_input', text });
  }, [send]);

  // Interrupt AI speaking
  const interrupt = useCallback(() => {
    return send({ type: 'interrupt' });
  }, [send]);

  // Heartbeat to keep connection alive
  useEffect(() => {
    if (status !== 'idle' && wsRef.current?.readyState === WebSocket.OPEN) {
      const interval = setInterval(() => {
        send({ type: 'ping' });
      }, 30000);

      return () => clearInterval(interval);
    }
  }, [status, send]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    status,
    sessionId,
    sttEnabled,
    connect,
    disconnect,
    startListening,
    stopListening,
    sendAudio,
    sendText,
    interrupt,
    isConnected: status !== 'idle' && status !== 'error' && status !== 'connecting'
  };
};

export default useVoiceWebSocket;
