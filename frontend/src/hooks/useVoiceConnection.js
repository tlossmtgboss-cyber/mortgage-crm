import { useState, useRef, useCallback, useEffect } from 'react';
import { getItem, STORAGE_KEYS } from '../utils/storage';
import { toast } from '../utils/toast';

// WebSocket reconnect constants
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY = 1000; // 1 second

// Heartbeat constants
const PING_INTERVAL_MS = 25000; // 25 seconds
const PONG_TIMEOUT_MS = 35000; // 35 seconds without any message = dead

/**
 * Custom hook for WebSocket voice connection lifecycle.
 * Handles connect/disconnect, reconnect with exponential backoff,
 * online/offline listeners, Capacitor foreground resume, and heartbeat ping/pong.
 *
 * @param {Object} options
 * @param {Function} options.onTranscript - Called with transcript data messages
 * @param {Function} options.onResponse - Called with response text messages
 * @param {Function} options.onAudio - Called with base64 audio data
 * @param {Function} options.onAction - Called with (action, params) for CRM actions
 * @param {Function} options.onWorkflowStatus - Called with workflow status data
 * @param {Function} options.onError - Called with error message string
 * @param {Function} options.onReady - Called when WS is ready (after 'ready' message)
 * @param {Function} [options.onCISessionStarted] - Called when a Call Intelligence session starts
 * @param {Function} [options.onCIArtifactGenerated] - Called when a CI artifact is generated
 * @param {Function} [options.onCIProcessingComplete] - Called when CI processing completes
 * @param {Function} options.startAudioCapture - Called after WS open to begin mic capture
 * @param {Function} options.stopAudioCapture - Called on disconnect to stop mic
 * @param {string} options.assistantName - Voice assistant display name
 */
const useVoiceConnection = ({
  onTranscript,
  onResponse,
  onAudio,
  onAction,
  onWorkflowStatus,
  onError,
  onReady,
  onCISessionStarted,
  onCIArtifactGenerated,
  onCIProcessingComplete,
  startAudioCapture,
  stopAudioCapture,
  assistantName = 'Aria',
}) => {
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [showFallback, setShowFallback] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const wsRef = useRef(null);
  const wsFailCountRef = useRef(0);
  const userDisconnectedRef = useRef(false);
  // Track whether user was connected before backgrounding (for M-8 foreground resume)
  const wasConnectedRef = useRef(false);

  // Heartbeat refs
  const pingIntervalRef = useRef(null);
  const lastPongTimeRef = useRef(Date.now());
  const pongCheckIntervalRef = useRef(null);

  // Determine API URLs based on environment
  const isLocalDev =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1' ||
      window.location.hostname.startsWith('192.168.'));

  const API_BASE_URL = isLocalDev
    ? 'http://192.168.1.240:8000'
    : 'https://api.perenniaai.com';
  const WS_BASE_URL = isLocalDev
    ? 'ws://192.168.1.240:8000'
    : 'wss://api.perenniaai.com';

  // --- Heartbeat helpers ---
  const startHeartbeat = useCallback(() => {
    // Clear any existing intervals
    if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
    if (pongCheckIntervalRef.current) clearInterval(pongCheckIntervalRef.current);

    lastPongTimeRef.current = Date.now();

    // Send pings every 25 seconds
    pingIntervalRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, PING_INTERVAL_MS);

    // Check for stale connection every 5 seconds
    pongCheckIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - lastPongTimeRef.current;
      if (elapsed > PONG_TIMEOUT_MS && wsRef.current) {
        console.log(`[${assistantName}] Heartbeat timeout (${elapsed}ms without message) — reconnecting`);
        // Force-close the dead socket so onclose fires reconnect
        wsRef.current.close();
      }
    }, 5000);
  }, [assistantName]);

  const stopHeartbeat = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (pongCheckIntervalRef.current) {
      clearInterval(pongCheckIntervalRef.current);
      pongCheckIntervalRef.current = null;
    }
  }, []);

  // --- Disconnect ---
  const disconnect = useCallback(() => {
    userDisconnectedRef.current = true;
    wasConnectedRef.current = false;
    setReconnectAttempt(0);
    stopHeartbeat();
    stopAudioCapture();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('idle');
    setError(null);
  }, [stopAudioCapture, stopHeartbeat]);

  // --- Connect ---
  const connect = useCallback(async () => {
    setStatus('connecting');
    setError(null);
    userDisconnectedRef.current = false;

    try {
      // C-5: Use secure storage instead of raw localStorage
      const token = await getItem(STORAGE_KEYS.TOKEN);
      if (!token) {
        setError('Please log in first');
        setStatus('error');
        return;
      }

      // Security: Token sent as first message after connect, not in URL query
      // string, to avoid leaking JWT into server/proxy logs and browser history.
      const wsUrl = `${WS_BASE_URL}/api/v1/voice/ws/browser-voice`;
      console.log(`[${assistantName}] Connecting to:`, wsUrl);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
        console.log(`[${assistantName}] WebSocket connected`);
        setReconnectAttempt(0);
        wasConnectedRef.current = true;

        // Send initial config with CRM context
        ws.send(
          JSON.stringify({
            type: 'config',
            agent_name: assistantName,
            system_prompt: `You are ${assistantName}, an AI voice assistant for a mortgage CRM. You can help users:
- Query leads, loans, and client information
- Send pre-approval letters
- Send SMS messages and emails
- Complete and manage tasks
- Check pipeline status and metrics
- Schedule appointments
- Look up borrower information

Be conversational, helpful, and concise. When users ask to perform actions, confirm the details before executing.`,
            voice: 'nova',
            language: 'en-US',
          }),
        );

        // Start heartbeat
        startHeartbeat();

        // Begin microphone capture
        startAudioCapture();
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(`[${assistantName}] Message:`, data.type);

        // Update last pong time on ANY message received (heartbeat tracking)
        lastPongTimeRef.current = Date.now();

        switch (data.type) {
          case 'ready':
            setStatus('listening');
            wsFailCountRef.current = 0;
            setShowFallback(false);
            if (onReady) onReady();
            break;
          case 'transcript':
            if (onTranscript) onTranscript(data);
            if (data.is_final) {
              setStatus('processing');
            }
            break;
          case 'response':
            if (onResponse) onResponse(data);
            break;
          case 'audio':
            if (onAudio) onAudio(data.data);
            break;
          case 'action':
            if (onAction) onAction(data.action, data.params);
            break;
          case 'workflow_status':
            if (onWorkflowStatus) onWorkflowStatus(data);
            break;
          case 'pong':
            // Explicit pong — already handled by lastPongTimeRef update above
            break;
          case 'error':
            setError(data.message);
            setStatus('error');
            if (onError) onError(data.message);
            break;
          // Call Intelligence events
          case 'ci_session_started':
            onCISessionStarted?.(data);
            break;
          case 'ci_artifact_generated':
            onCIArtifactGenerated?.(data);
            break;
          case 'ci_processing_complete':
            onCIProcessingComplete?.(data);
            break;
          default:
            break;
        }
      };

      ws.onerror = (err) => {
        console.error(`[${assistantName}] WebSocket error:`, err);
        wsFailCountRef.current += 1;
        setError('Voice connection unavailable');
        setStatus('error');
        if (wsFailCountRef.current >= 1) {
          setShowFallback(true);
        }
      };

      ws.onclose = (event) => {
        console.log(`[${assistantName}] WebSocket closed (code: ${event.code})`);
        stopHeartbeat();
        setStatus((prev) => (prev !== 'idle' ? 'idle' : prev));

        // Only auto-reconnect if close was unexpected (not user-initiated, not normal close)
        if (event.code !== 1000 && !userDisconnectedRef.current) {
          setReconnectAttempt((prev) => {
            if (prev < MAX_RECONNECT_ATTEMPTS) {
              const delay = BASE_RECONNECT_DELAY * Math.pow(2, prev);
              console.log(
                `[${assistantName}] Reconnecting in ${delay}ms (attempt ${prev + 1}/${MAX_RECONNECT_ATTEMPTS})`,
              );
              setTimeout(() => {
                connect();
              }, delay);
              return prev + 1;
            }
            console.log(`[${assistantName}] Max reconnect attempts reached`);
            setShowFallback(true);
            return prev;
          });
        }
      };
    } catch (err) {
      console.error(`[${assistantName}] Connection error:`, err);
      setError(err.message);
      setStatus('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [WS_BASE_URL, assistantName, startAudioCapture, startHeartbeat, stopHeartbeat]);

  // Send a message over the WebSocket (e.g., text commands)
  const sendMessage = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      return true;
    }
    return false;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopHeartbeat();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [stopHeartbeat]);

  // Online/offline listeners — reconnect when network is restored
  useEffect(() => {
    const handleOnline = () => {
      toast.info('Connection restored');
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setReconnectAttempt(0);
        connect();
      }
    };
    const handleOffline = () => {
      toast.warning('Connection lost — voice commands unavailable');
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [connect]);

  // Capacitor app state change — pause on background, resume on foreground (M-8)
  useEffect(() => {
    let appListener;
    try {
      import('@capacitor/app')
        .then(({ App }) => {
          appListener = App.addListener('appStateChange', ({ isActive }) => {
            if (!isActive) {
              // App went to background — stop listening to save battery/resources
              if (
                wsRef.current?.readyState === WebSocket.OPEN
              ) {
                // Mark that we were connected so we can resume
                wasConnectedRef.current = true;
                disconnect();
              }
            } else {
              // M-8: App returned to foreground — auto-reconnect if previously connected
              if (wasConnectedRef.current) {
                wasConnectedRef.current = false;
                userDisconnectedRef.current = false;
                setReconnectAttempt(0);
                connect();
              }
            }
          });
        })
        .catch(() => {
          // Not running in Capacitor — skip
        });
    } catch (e) {
      // Not in Capacitor environment
    }
    return () => {
      if (appListener) appListener.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disconnect, connect]);

  return {
    status,
    setStatus,
    error,
    showFallback,
    setShowFallback,
    reconnectAttempt,
    connect,
    disconnect,
    sendMessage,
    wsRef,
    wsFailCountRef,
    API_BASE_URL,
  };
};

export default useVoiceConnection;
