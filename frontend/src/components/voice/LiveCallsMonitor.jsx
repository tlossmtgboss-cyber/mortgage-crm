/**
 * Live Calls Monitor Component
 *
 * Real-time dashboard for monitoring active Voice OS calls.
 * Features:
 * - Active calls list with real-time updates
 * - Call details (duration, status, agent)
 * - Live transcript streaming
 * - Call control actions (listen, join, transfer)
 * - Performance metrics
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './LiveCallsMonitor.css';

const CALL_STATUS = {
  RINGING: 'ringing',
  IN_PROGRESS: 'in_progress',
  ON_HOLD: 'on_hold',
  TRANSFERRING: 'transferring',
  ENDED: 'ended',
};

const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatTime = (date) => {
  return new Date(date).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

const CallCard = ({ call, onSelect, isSelected }) => {
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (call.status === CALL_STATUS.IN_PROGRESS && call.startTime) {
      const interval = setInterval(() => {
        setDuration(Math.floor((Date.now() - new Date(call.startTime).getTime()) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [call.status, call.startTime]);

  return (
    <div
      className={`call-card ${isSelected ? 'selected' : ''} status-${call.status}`}
      onClick={() => onSelect(call)}
    >
      <div className="call-header">
        <span className={`status-indicator ${call.status}`} />
        <span className="caller-name">{call.callerName || 'Unknown Caller'}</span>
        <span className="call-duration">{formatDuration(duration)}</span>
      </div>

      <div className="call-info">
        <span className="phone-number">{call.phoneNumber}</span>
        <span className="agent-name">Agent: {call.agentName || 'AI Receptionist'}</span>
      </div>

      <div className="call-meta">
        <span className="call-type">{call.direction === 'inbound' ? 'Inbound' : 'Outbound'}</span>
        <span className="start-time">Started: {formatTime(call.startTime)}</span>
      </div>

      {call.currentTool && (
        <div className="active-tool">
          Using: <strong>{call.currentTool}</strong>
        </div>
      )}
    </div>
  );
};

const TranscriptPanel = ({ call }) => {
  const transcriptRef = useRef(null);
  const [transcript, setTranscript] = useState([]);

  useEffect(() => {
    if (!call) return;

    // Initialize with existing transcript
    setTranscript(call.transcript || []);

    // Connect to WebSocket for live updates
    const ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/voice/calls/${call.id}/stream`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'transcript') {
        setTranscript(prev => [...prev, data.entry]);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, [call]);

  useEffect(() => {
    // Auto-scroll to bottom
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript]);

  if (!call) {
    return (
      <div className="transcript-panel empty">
        <p>Select a call to view live transcript</p>
      </div>
    );
  }

  return (
    <div className="transcript-panel">
      <div className="panel-header">
        <h3>Live Transcript</h3>
        <span className="call-id">Call ID: {call.id}</span>
      </div>

      <div className="transcript-content" ref={transcriptRef}>
        {transcript.length === 0 ? (
          <div className="no-transcript">Waiting for conversation...</div>
        ) : (
          transcript.map((entry, index) => (
            <div key={index} className={`transcript-entry ${entry.speaker}`}>
              <div className="entry-header">
                <span className="speaker-label">
                  {entry.speaker === 'caller' ? call.callerName || 'Caller' : 'AI Agent'}
                </span>
                <span className="entry-time">{formatTime(entry.timestamp)}</span>
              </div>
              <div className="entry-text">{entry.text}</div>
              {entry.tool && (
                <div className="tool-usage">
                  <span className="tool-icon">*</span>
                  Tool: {entry.tool}
                  {entry.toolResult && (
                    <span className="tool-result">
                      {entry.toolResult.success ? ' Success' : ' Failed'}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const MetricsPanel = ({ metrics }) => {
  return (
    <div className="metrics-panel">
      <h3>Live Metrics</h3>
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-value">{metrics.activeCalls || 0}</span>
          <span className="metric-label">Active Calls</span>
        </div>
        <div className="metric-card">
          <span className="metric-value">{metrics.queuedCalls || 0}</span>
          <span className="metric-label">In Queue</span>
        </div>
        <div className="metric-card">
          <span className="metric-value">{metrics.avgWaitTime || '0:00'}</span>
          <span className="metric-label">Avg Wait</span>
        </div>
        <div className="metric-card">
          <span className="metric-value">{metrics.callsToday || 0}</span>
          <span className="metric-label">Calls Today</span>
        </div>
        <div className="metric-card success">
          <span className="metric-value">{metrics.successRate || '0'}%</span>
          <span className="metric-label">Success Rate</span>
        </div>
        <div className="metric-card">
          <span className="metric-value">{metrics.avgDuration || '0:00'}</span>
          <span className="metric-label">Avg Duration</span>
        </div>
      </div>

      {metrics.alerts && metrics.alerts.length > 0 && (
        <div className="alerts-section">
          <h4>Active Alerts</h4>
          {metrics.alerts.map((alert, index) => (
            <div key={index} className={`alert-item ${alert.severity}`}>
              <span className="alert-icon">!</span>
              <span className="alert-message">{alert.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const LiveCallsMonitor = () => {
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [metrics, setMetrics] = useState({});
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);

  const fetchCalls = useCallback(async () => {
    try {
      const response = await fetch('/api/voice/calls?status=active');
      if (response.ok) {
        const data = await response.json();
        setCalls(data.calls || []);
      }
    } catch (err) {
      console.error('Failed to fetch calls:', err);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const response = await fetch('/api/voice/metrics/live');
      if (response.ok) {
        const data = await response.json();
        setMetrics(data);
      }
    } catch (err) {
      console.error('Failed to fetch metrics:', err);
    }
  }, []);

  useEffect(() => {
    // Initial fetch
    Promise.all([fetchCalls(), fetchMetrics()]).finally(() => setLoading(false));

    // Connect to WebSocket for live updates
    const connectWebSocket = () => {
      const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/voice/monitor`;
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setWsConnected(true);
        console.log('Connected to call monitor');
      };

      wsRef.current.onmessage = (event) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'call_started':
            setCalls(prev => [...prev, data.call]);
            break;
          case 'call_updated':
            setCalls(prev => prev.map(c => c.id === data.call.id ? { ...c, ...data.call } : c));
            if (selectedCall?.id === data.call.id) {
              setSelectedCall(prev => ({ ...prev, ...data.call }));
            }
            break;
          case 'call_ended':
            setCalls(prev => prev.filter(c => c.id !== data.callId));
            if (selectedCall?.id === data.callId) {
              setSelectedCall(null);
            }
            break;
          case 'metrics_update':
            setMetrics(data.metrics);
            break;
          default:
            break;
        }
      };

      wsRef.current.onclose = () => {
        setWsConnected(false);
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    };

    connectWebSocket();

    // Fallback polling
    const pollInterval = setInterval(() => {
      if (!wsConnected) {
        fetchCalls();
        fetchMetrics();
      }
    }, 5000);

    return () => {
      clearInterval(pollInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [fetchCalls, fetchMetrics, wsConnected, selectedCall]);

  const handleCallAction = async (callId, action) => {
    try {
      const response = await fetch(`/api/voice/calls/${callId}/${action}`, {
        method: 'POST',
      });

      if (!response.ok) {
        console.error(`Failed to ${action} call`);
      }
    } catch (err) {
      console.error(`Error performing ${action}:`, err);
    }
  };

  const filteredCalls = calls.filter(call => {
    if (filter === 'all') return true;
    if (filter === 'inbound') return call.direction === 'inbound';
    if (filter === 'outbound') return call.direction === 'outbound';
    return call.status === filter;
  });

  if (loading) {
    return (
      <div className="live-calls-monitor loading">
        <div className="loading-spinner">Loading live calls...</div>
      </div>
    );
  }

  return (
    <div className="live-calls-monitor">
      <div className="monitor-header">
        <div className="header-left">
          <h1>Live Calls Monitor</h1>
          <span className={`connection-status ${wsConnected ? 'connected' : 'disconnected'}`}>
            {wsConnected ? 'Live' : 'Connecting...'}
          </span>
        </div>

        <div className="header-controls">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Calls</option>
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
            <option value="in_progress">In Progress</option>
            <option value="on_hold">On Hold</option>
          </select>

          <button onClick={fetchCalls} className="refresh-btn">
            Refresh
          </button>
        </div>
      </div>

      <div className="monitor-content">
        <div className="calls-section">
          <div className="section-header">
            <h2>Active Calls ({filteredCalls.length})</h2>
          </div>

          <div className="calls-list">
            {filteredCalls.length === 0 ? (
              <div className="no-calls">
                <p>No active calls</p>
                <span>Calls will appear here in real-time</span>
              </div>
            ) : (
              filteredCalls.map(call => (
                <CallCard
                  key={call.id}
                  call={call}
                  onSelect={setSelectedCall}
                  isSelected={selectedCall?.id === call.id}
                />
              ))
            )}
          </div>
        </div>

        <div className="details-section">
          {selectedCall && (
            <div className="call-actions">
              <button
                onClick={() => handleCallAction(selectedCall.id, 'listen')}
                className="action-btn listen"
              >
                Listen
              </button>
              <button
                onClick={() => handleCallAction(selectedCall.id, 'whisper')}
                className="action-btn whisper"
              >
                Whisper
              </button>
              <button
                onClick={() => handleCallAction(selectedCall.id, 'join')}
                className="action-btn join"
              >
                Join Call
              </button>
              <button
                onClick={() => handleCallAction(selectedCall.id, 'transfer')}
                className="action-btn transfer"
              >
                Transfer
              </button>
              <button
                onClick={() => handleCallAction(selectedCall.id, 'end')}
                className="action-btn end"
              >
                End Call
              </button>
            </div>
          )}

          <TranscriptPanel call={selectedCall} />
        </div>

        <div className="metrics-section">
          <MetricsPanel metrics={metrics} />
        </div>
      </div>
    </div>
  );
};

export default LiveCallsMonitor;
