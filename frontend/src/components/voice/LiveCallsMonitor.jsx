// Voice OS Live Calls Monitor - Real-time call monitoring dashboard
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';




const LiveCallsMonitor = ({
  agentId,
  onCallSelect,
  refreshInterval = 2000
}) => {
  const [calls, setCalls] = useState([]);
  const [metrics, setMetrics] = useState({
    totalActiveCalls: 0,
    avgDuration: 0,
    avgWaitTime: 0,
    escalationRate: 0
  });
  const [selectedCall, setSelectedCall] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const intervalRef = useRef(null);

  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  const WS_BASE_URL = API_BASE_URL.replace('http', 'ws');

  // Fetch calls via REST API
  const fetchCalls = useCallback(async () => {
    try {
      const token = getToken();
      const url = agentId
        ? `${API_BASE_URL}/api/v1/voice/calls/live?agent_id=${agentId}`
        : `${API_BASE_URL}/api/v1/voice/calls/live`;

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch calls');
      }

      const data = await response.json();
      setCalls(data.calls || []);
      setMetrics(data.metrics || metrics);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching live calls:', err);
      // Demo data for development
      setCalls([
        {
          id: 'call-1',
          callSid: 'CA12345',
          agentId: 'default-sam',
          agentName: 'Sam - AI Receptionist',
          direction: 'inbound',
          fromNumber: '+1 (555) 123-4567',
          toNumber: '+1 (832) 648-2297',
          status: 'in_progress',
          startTime: new Date(Date.now() - 185000).toISOString(),
          durationSeconds: 185,
          contactName: 'John Smith',
          contactId: 'contact-123',
          emotionState: 'neutral',
          lastTranscript: "I'm interested in refinancing my mortgage",
          sentiment: 'positive',
          actionsCount: 2
        }
      ]);
      setMetrics({
        totalActiveCalls: 1,
        avgDuration: 185,
        avgWaitTime: 3,
        escalationRate: 5
      });
      setLoading(false);
    }
  }, [API_BASE_URL, agentId, metrics]);

  // Connect to WebSocket for real-time updates
  const connectWebSocket = useCallback(() => {
    try {
      const token = getToken();
      // Security: Token sent as first message after connect, not in URL query
      // string, to avoid leaking JWT into server/proxy logs and browser history.
      const ws = new WebSocket(`${WS_BASE_URL}/api/v1/voice/calls/ws`);

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
        console.log('Live calls WebSocket connected');
        setConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'call_started':
            setCalls(prev => [...prev, data.call]);
            break;

          case 'call_updated':
            setCalls(prev => prev.map(c =>
              c.id === data.call.id ? { ...c, ...data.call } : c
            ));
            break;

          case 'call_ended':
            setCalls(prev => prev.filter(c => c.id !== data.callId));
            break;

          case 'transcript':
            setCalls(prev => prev.map(c =>
              c.id === data.callId
                ? { ...c, lastTranscript: data.text }
                : c
            ));
            break;

          case 'emotion_update':
            setCalls(prev => prev.map(c =>
              c.id === data.callId
                ? { ...c, emotionState: data.emotion }
                : c
            ));
            break;

          case 'metrics':
            setMetrics(data.metrics);
            break;

          default:
            console.log('Unknown message type:', data.type);
        }
      };

      ws.onclose = () => {
        console.log('Live calls WebSocket disconnected');
        setConnected(false);
        // Reconnect after delay
        setTimeout(connectWebSocket, 5000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnected(false);
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('Failed to connect WebSocket:', err);
      setConnected(false);
    }
  }, [WS_BASE_URL]);

  useEffect(() => {
    fetchCalls();
    connectWebSocket();

    // Poll for updates as fallback
    intervalRef.current = setInterval(fetchCalls, refreshInterval);

    // Update durations every second
    const durationInterval = setInterval(() => {
      setCalls(prev => prev.map(call => ({
        ...call,
        durationSeconds: Math.floor((Date.now() - new Date(call.startTime).getTime()) / 1000)
      })));
    }, 1000);

    return () => {
      wsRef.current?.close();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      clearInterval(durationInterval);
    };
  }, [fetchCalls, connectWebSocket, refreshInterval]);

  const handleCallClick = (call) => {
    setSelectedCall(call);
    onCallSelect?.(call);
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getEmotionIcon = (emotion) => {
    const icons = {
      neutral: '😐',
      happy: '😊',
      frustrated: '😤',
      confused: '😕',
      urgent: '⚠️'
    };
    return icons[emotion] || '😐';
  };

  const getStatusColor = (status) => {
    const colors = {
      ringing: '#f59e0b',
      in_progress: '#22c55e',
      on_hold: '#6b7280',
      transferring: '#3b82f6'
    };
    return colors[status] || '#6b7280';
  };

  if (loading) {
    return (
      <div className="live-calls-loading">
        <div className="spinner"></div>
        <p>Connecting to live calls...</p>
      </div>
    );
  }

  return (
    <div className="live-calls-monitor">
      <div className="monitor-header">
        <div className="header-left">
          <h1>Live Calls</h1>
          <div className="connection-status">
            <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`}></span>
            {connected ? 'Live' : 'Reconnecting...'}
          </div>
        </div>
        <button className="btn-refresh" onClick={fetchCalls}>
          Refresh
        </button>
      </div>

      <div className="metrics-bar">
        <div className="metric">
          <span className="metric-value">{metrics.totalActiveCalls}</span>
          <span className="metric-label">Active Calls</span>
        </div>
        <div className="metric">
          <span className="metric-value">{formatDuration(metrics.avgDuration)}</span>
          <span className="metric-label">Avg Duration</span>
        </div>
        <div className="metric">
          <span className="metric-value">{metrics.avgWaitTime}s</span>
          <span className="metric-label">Avg Wait Time</span>
        </div>
        <div className="metric">
          <span className="metric-value">{metrics.escalationRate}%</span>
          <span className="metric-label">Escalation Rate</span>
        </div>
      </div>

      {calls.length === 0 ? (
        <div className="no-calls">
          <div className="no-calls-icon">📞</div>
          <h3>No Active Calls</h3>
          <p>Calls will appear here in real-time when they start</p>
        </div>
      ) : (
        <div className="calls-list">
          {calls.map((call) => (
            <div
              key={call.id}
              className={`call-card ${selectedCall?.id === call.id ? 'selected' : ''}`}
              onClick={() => handleCallClick(call)}
            >
              <div className="call-header">
                <div className="call-status">
                  <span
                    className="status-indicator"
                    style={{ backgroundColor: getStatusColor(call.status) }}
                  ></span>
                  <span className="status-text">{call.status.replace('_', ' ')}</span>
                </div>
                <div className="call-duration">{formatDuration(call.durationSeconds)}</div>
              </div>

              <div className="call-info">
                <div className="caller-info">
                  <span className="direction-icon">
                    {call.direction === 'inbound' ? '📥' : '📤'}
                  </span>
                  <div className="caller-details">
                    <span className="caller-name">
                      {call.contactName || call.fromNumber}
                    </span>
                    {call.contactName && (
                      <span className="caller-phone">{call.fromNumber}</span>
                    )}
                  </div>
                </div>

                <div className="agent-info">
                  <span className="agent-label">Agent:</span>
                  <span className="agent-name">{call.agentName}</span>
                </div>
              </div>

              <div className="call-emotion">
                <span className="emotion-icon">{getEmotionIcon(call.emotionState)}</span>
                <span className="emotion-label">{call.emotionState}</span>
                {call.sentiment && (
                  <span className={`sentiment-badge ${call.sentiment}`}>
                    {call.sentiment}
                  </span>
                )}
              </div>

              {call.lastTranscript && (
                <div className="last-transcript">
                  <span className="transcript-label">Last:</span>
                  <span className="transcript-text">"{call.lastTranscript}"</span>
                </div>
              )}

              <div className="call-actions">
                <span className="actions-count">{call.actionsCount} actions</span>
                <div className="quick-actions">
                  <button
                    className="btn-action"
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log('Listen to call:', call.id);
                    }}
                    title="Listen"
                  >
                    🎧
                  </button>
                  <button
                    className="btn-action"
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log('Whisper to agent:', call.id);
                    }}
                    title="Whisper"
                  >
                    🗣️
                  </button>
                  <button
                    className="btn-action warning"
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log('Take over call:', call.id);
                    }}
                    title="Take Over"
                  >
                    ⚡
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <style>{`
        .live-calls-monitor {
          padding: 24px;
          max-width: 1200px;
          margin: 0 auto;
        }

        .monitor-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .header-left h1 {
          margin: 0;
          font-size: 24px;
        }

        .connection-status {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          color: #666;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .status-dot.connected {
          background: #22c55e;
          animation: pulse 2s infinite;
        }

        .status-dot.disconnected {
          background: #ef4444;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .btn-refresh {
          background: #f3f4f6;
          border: 1px solid #d1d5db;
          padding: 8px 16px;
          border-radius: 8px;
          cursor: pointer;
        }

        .metrics-bar {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }

        .metric {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 16px;
          text-align: center;
        }

        .metric-value {
          display: block;
          font-size: 28px;
          font-weight: 600;
          color: #111;
        }

        .metric-label {
          font-size: 13px;
          color: #666;
        }

        .no-calls {
          text-align: center;
          padding: 60px 20px;
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
        }

        .no-calls-icon {
          font-size: 48px;
          margin-bottom: 16px;
        }

        .no-calls h3 {
          margin: 0 0 8px 0;
          color: #111;
        }

        .no-calls p {
          margin: 0;
          color: #666;
        }

        .calls-list {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .call-card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 16px;
          cursor: pointer;
          transition: all 0.2s;
        }

        .call-card:hover {
          border-color: #2563eb;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .call-card.selected {
          border-color: #2563eb;
          background: #f0f7ff;
        }

        .call-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .call-status {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-indicator {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }

        .status-text {
          text-transform: capitalize;
          font-weight: 500;
        }

        .call-duration {
          font-size: 20px;
          font-weight: 600;
          font-family: monospace;
        }

        .call-info {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .caller-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .direction-icon {
          font-size: 20px;
        }

        .caller-details {
          display: flex;
          flex-direction: column;
        }

        .caller-name {
          font-weight: 500;
          font-size: 16px;
        }

        .caller-phone {
          font-size: 13px;
          color: #666;
        }

        .agent-info {
          text-align: right;
        }

        .agent-label {
          color: #666;
          font-size: 13px;
        }

        .agent-name {
          display: block;
          font-weight: 500;
        }

        .call-emotion {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
        }

        .emotion-icon {
          font-size: 20px;
        }

        .emotion-label {
          text-transform: capitalize;
          color: #666;
        }

        .sentiment-badge {
          margin-left: auto;
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 12px;
          text-transform: capitalize;
        }

        .sentiment-badge.positive {
          background: #dcfce7;
          color: #16a34a;
        }

        .sentiment-badge.neutral {
          background: #f3f4f6;
          color: #6b7280;
        }

        .sentiment-badge.negative {
          background: #fef2f2;
          color: #dc2626;
        }

        .last-transcript {
          background: #f9fafb;
          padding: 10px 12px;
          border-radius: 8px;
          margin-bottom: 12px;
          font-size: 14px;
        }

        .transcript-label {
          color: #666;
          margin-right: 8px;
        }

        .transcript-text {
          font-style: italic;
          color: #374151;
        }

        .call-actions {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .actions-count {
          font-size: 13px;
          color: #666;
        }

        .quick-actions {
          display: flex;
          gap: 8px;
        }

        .btn-action {
          background: #f3f4f6;
          border: none;
          padding: 8px;
          border-radius: 6px;
          cursor: pointer;
          font-size: 16px;
          transition: all 0.2s;
        }

        .btn-action:hover {
          background: #e5e7eb;
        }

        .btn-action.warning:hover {
          background: #fef2f2;
        }

        .live-calls-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 400px;
        }

        .spinner {
          width: 40px;
          height: 40px;
          border: 3px solid #f3f4f6;
          border-top-color: #2563eb;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default LiveCallsMonitor;
