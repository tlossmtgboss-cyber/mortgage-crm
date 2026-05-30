/**
 * useAriaWebSocket
 *
 * WebSocket hook for the Aria conversation engine.
 * Connects to /api/v1/aria/ws, handles auth, streaming responses,
 * confirmation flows, and auto-reconnect.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '../utils/tokenStore';
import { API_BASE_URL } from '../services/api';

const WS_URL = API_BASE_URL.replace(/^http/, 'ws') + '/api/v1/aria/ws';
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export function useAriaWebSocket({ onGreeting, onMessage, onTyping, onConfirmation, onTaskComplete, onError, onDisconnect } = {}) {
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);
  // Messages submitted while the socket wasn't OPEN — flushed once connected
  // so a send during (re)connect isn't silently dropped.
  const pendingMessages = useRef([]);
  const callbacksRef = useRef({ onGreeting, onMessage, onTyping, onConfirmation, onTaskComplete, onError, onDisconnect });

  // Keep callbacks ref current without triggering reconnect
  useEffect(() => {
    callbacksRef.current = { onGreeting, onMessage, onTyping, onConfirmation, onTaskComplete, onError, onDisconnect };
  }, [onGreeting, onMessage, onTyping, onConfirmation, onTaskComplete, onError, onDisconnect]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || connecting) return;

    const token = getToken();
    if (!token) {
      callbacksRef.current.onError?.('Not authenticated. Please log in.');
      return;
    }

    setConnecting(true);
    intentionalClose.current = false;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      // Accumulate chunks into a full message
      let chunkBuffer = '';

      ws.onopen = () => {
        // Send auth as first message (secure — not in URL)
        ws.send(JSON.stringify({ type: 'auth', token }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case 'greeting':
              setConnected(true);
              setConnecting(false);
              reconnectAttempts.current = 0;
              callbacksRef.current.onGreeting?.(data.content);
              // Connection is authenticated and ready — flush any messages the
              // user sent while we were (re)connecting.
              if (pendingMessages.current.length > 0) {
                const queued = pendingMessages.current.splice(0);
                queued.forEach((text) =>
                  ws.send(JSON.stringify({ type: 'message', content: text }))
                );
              }
              break;

            case 'typing':
              callbacksRef.current.onTyping?.();
              break;

            case 'chunk':
              chunkBuffer += data.content || '';
              break;

            case 'done':
              // Full message delivered — use the complete content from done event
              callbacksRef.current.onMessage?.(data.content || chunkBuffer);
              chunkBuffer = '';
              break;

            case 'confirmation_required':
              callbacksRef.current.onConfirmation?.(data.preview);
              break;

            case 'task_complete':
              callbacksRef.current.onTaskComplete?.(data.result);
              break;

            case 'error':
              callbacksRef.current.onError?.(data.message);
              break;

            case 'ping':
              ws.send(JSON.stringify({ type: 'pong' }));
              break;

            default:
              break;
          }
        } catch (e) {
          console.error('[AriaWS] Failed to parse message:', e);
        }
      };

      ws.onclose = (event) => {
        setConnected(false);
        setConnecting(false);
        wsRef.current = null;

        // Always let the UI reset in-flight state (e.g. the "Aria is thinking…"
        // spinner) so a mid-task drop doesn't hang forever.
        callbacksRef.current.onDisconnect?.(event);

        if (event.code === 4001) {
          callbacksRef.current.onError?.('Authentication failed. Please log in again.');
          return;
        }

        // Auto-reconnect unless intentionally closed
        if (!intentionalClose.current && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
        } else if (!intentionalClose.current) {
          // Exhausted reconnect attempts — surface it instead of failing silently.
          callbacksRef.current.onError?.('Lost connection to Aria. Tap to retry.');
        }
      };

      ws.onerror = () => {
        // onclose will fire after this — handle reconnect there
        setConnecting(false);
      };
    } catch (e) {
      setConnecting(false);
      callbacksRef.current.onError?.('Failed to connect to Aria.');
    }
  }, [connecting]);

  const disconnect = useCallback(() => {
    intentionalClose.current = true;
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
    setConnecting(false);
  }, []);

  const sendMessage = useCallback((text) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      // Queue and (re)connect instead of dropping the message. It will be
      // flushed when the 'greeting' event confirms the socket is ready.
      pendingMessages.current.push(text);
      connect();
      return true;
    }
    wsRef.current.send(JSON.stringify({ type: 'message', content: text }));
    return true;
  }, [connect]);

  const sendConfirmation = useCallback((confirmed) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(JSON.stringify({ type: 'confirm', value: confirmed }));
    return true;
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    connected,
    connecting,
    sendMessage,
    sendConfirmation,
    connect,
    disconnect,
  };
}
