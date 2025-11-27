/**
 * WebSocket hook for Power Dialer real-time updates
 * @fileoverview React hook for managing WebSocket connection to dialer backend
 */

import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * @typedef {Object} UseDialerWebSocketOptions
 * @property {function} [onMessage] - Callback when message received
 * @property {function} [onConnect] - Callback when connected
 * @property {function} [onDisconnect] - Callback when disconnected
 * @property {number} [reconnectInterval] - Reconnect interval in ms (default: 3000)
 * @property {number} [maxReconnectAttempts] - Max reconnect attempts (default: 5)
 */

/**
 * Hook for managing WebSocket connection to the dialer backend
 * @param {string} agentId - Agent ID for WebSocket connection
 * @param {UseDialerWebSocketOptions} options - Hook options
 * @returns {Object} WebSocket state and controls
 */
export function useDialerWebSocket(agentId, options = {}) {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Determine WebSocket URL based on environment
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.REACT_APP_API_URL
      ? new URL(process.env.REACT_APP_API_URL).host
      : window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/dialer/ws/${agentId}`;

    console.log('Connecting to WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Dialer WebSocket connected');
      setIsConnected(true);
      setReconnectAttempts(0);
      onConnect?.();

      // Send ping every 30 seconds to keep connection alive
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      // Handle pong response
      if (event.data === 'pong') {
        return;
      }

      try {
        const data = JSON.parse(event.data);
        setLastEvent(data);
        onMessage?.(data);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('Dialer WebSocket error:', error);
    };

    ws.onclose = (event) => {
      console.log('Dialer WebSocket disconnected:', event.code, event.reason);
      setIsConnected(false);
      wsRef.current = null;

      // Clear ping interval
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      onDisconnect?.();

      // Attempt to reconnect if not intentionally closed
      if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
        console.log(`Attempting to reconnect (${reconnectAttempts + 1}/${maxReconnectAttempts})...`);
        reconnectTimeoutRef.current = setTimeout(() => {
          setReconnectAttempts(prev => prev + 1);
          connect();
        }, reconnectInterval);
      }
    };

    wsRef.current = ws;
  }, [agentId, reconnectAttempts, maxReconnectAttempts, reconnectInterval, onConnect, onDisconnect, onMessage]);

  const disconnect = useCallback(() => {
    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Clear ping interval
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }

    setIsConnected(false);
    setReconnectAttempts(0);
  }, []);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      wsRef.current.send(message);
      return true;
    }
    console.warn('WebSocket not connected, cannot send message');
    return false;
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (agentId) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [agentId]); // Only reconnect if agentId changes

  return {
    isConnected,
    reconnectAttempts,
    lastEvent,
    send,
    disconnect,
    reconnect: connect
  };
}

/**
 * Hook for handling specific dialer events
 * @param {string} agentId - Agent ID
 * @param {Object} handlers - Event handlers
 * @returns {Object} WebSocket state
 */
export function useDialerEvents(agentId, handlers = {}) {
  const {
    onCallStarted,
    onCallCompleted,
    onCallStatusUpdate,
    onClickToDialStatus,
    onDispositionSaved,
    onSessionUpdate
  } = handlers;

  const handleMessage = useCallback((event) => {
    switch (event.type) {
      case 'dialer.call.started':
        onCallStarted?.(event);
        break;
      case 'dialer.call.completed':
        onCallCompleted?.(event);
        break;
      case 'call_status_update':
        onCallStatusUpdate?.(event);
        break;
      case 'click_to_dial_status':
        onClickToDialStatus?.(event);
        break;
      case 'disposition_saved':
        onDispositionSaved?.(event);
        break;
      case 'dialer.status':
        onSessionUpdate?.(event);
        break;
      default:
        console.log('Unknown dialer event:', event.type, event);
    }
  }, [onCallStarted, onCallCompleted, onCallStatusUpdate, onClickToDialStatus, onDispositionSaved, onSessionUpdate]);

  return useDialerWebSocket(agentId, { onMessage: handleMessage });
}

export default useDialerWebSocket;
