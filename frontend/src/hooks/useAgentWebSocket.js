/**
 * WebSocket hooks for real-time agent updates
 * Provides live metrics, health status, and alerts
 */
import { useEffect, useState, useRef, useCallback } from 'react';

const WS_BASE_URL = process.env.REACT_APP_WS_URL ||
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
  (process.env.REACT_APP_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000');

/**
 * Hook for real-time agent metrics
 * @param {number} agentId - The agent ID to subscribe to
 * @returns {Object} - { metrics, isConnected, error, reconnect }
 */
export function useAgentMetrics(agentId) {
  const [metrics, setMetrics] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    if (!agentId) return;

    const wsUrl = `${WS_BASE_URL}/ws/agents/${agentId}/metrics`;

    try {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log(`[WebSocket] Connected to agent ${agentId} metrics`);
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'metrics_update') {
            setMetrics(data.data);
          }
        } catch (e) {
          console.error('[WebSocket] Error parsing message:', e);
        }
      };

      ws.current.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError('WebSocket connection error');
        setIsConnected(false);
      };

      ws.current.onclose = (event) => {
        console.log(`[WebSocket] Disconnected from agent ${agentId}`, event.code);
        setIsConnected(false);

        // Attempt reconnection with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          console.log(`[WebSocket] Reconnecting in ${delay}ms...`);
          reconnectTimeout.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      };
    } catch (e) {
      console.error('[WebSocket] Connection error:', e);
      setError('Failed to connect');
    }
  }, [agentId]);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectAttempts.current = 0;
    connect();
  }, [connect, disconnect]);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [agentId, connect, disconnect]);

  return { metrics, isConnected, error, reconnect };
}

/**
 * Hook for real-time system health
 * @returns {Object} - { health, isConnected, error, reconnect }
 */
export function useSystemHealth() {
  const [health, setHealth] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    const wsUrl = `${WS_BASE_URL}/ws/system/health`;

    try {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('[WebSocket] Connected to system health');
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'system_health_update') {
            setHealth(data.data);
          }
        } catch (e) {
          console.error('[WebSocket] Error parsing message:', e);
        }
      };

      ws.current.onerror = (event) => {
        console.error('[WebSocket] Error:', event);
        setError('WebSocket connection error');
        setIsConnected(false);
      };

      ws.current.onclose = (event) => {
        console.log('[WebSocket] Disconnected from system health', event.code);
        setIsConnected(false);

        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectTimeout.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      };
    } catch (e) {
      console.error('[WebSocket] Connection error:', e);
      setError('Failed to connect');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    reconnectAttempts.current = 0;
    connect();
  }, [connect, disconnect]);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { health, isConnected, error, reconnect };
}

/**
 * Hook for real-time alerts
 * @returns {Object} - { alerts, isConnected, error, clearAlerts }
 */
export function useAlertsFeed() {
  const [alerts, setAlerts] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);

  const connect = useCallback(() => {
    const wsUrl = `${WS_BASE_URL}/ws/alerts`;

    try {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('[WebSocket] Connected to alerts feed');
        setIsConnected(true);
        setError(null);
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'new_alert') {
            setAlerts(prev => [data.data, ...prev].slice(0, 50)); // Keep last 50 alerts
          }
        } catch (e) {
          console.error('[WebSocket] Error parsing message:', e);
        }
      };

      ws.current.onerror = (event) => {
        console.error('[WebSocket] Alerts error:', event);
        setError('WebSocket connection error');
        setIsConnected(false);
      };

      ws.current.onclose = () => {
        setIsConnected(false);
        // Auto-reconnect after 5 seconds
        reconnectTimeout.current = setTimeout(connect, 5000);
      };
    } catch (e) {
      setError('Failed to connect');
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { alerts, isConnected, error, clearAlerts };
}

/**
 * Connection status indicator component
 * Use this in the UI to show WebSocket status
 */
export function ConnectionStatus({ isConnected, label = 'Live' }) {
  return (
    <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
      <span className="status-dot"></span>
      {isConnected ? label : 'Reconnecting...'}
    </span>
  );
}

export default {
  useAgentMetrics,
  useSystemHealth,
  useAlertsFeed,
  ConnectionStatus
};
