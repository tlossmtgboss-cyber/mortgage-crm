import React, { useState, useEffect, useRef, useCallback } from 'react';
import './LiveCallWhisper.css';

// Whisper type icons and labels
const WHISPER_TYPES = {
  talking_point: { icon: '💬', label: 'Talking Point', color: '#3b82f6' },
  objection_handler: { icon: '🛡️', label: 'Handle Objection', color: '#ef4444' },
  product_recommendation: { icon: '📦', label: 'Recommend Product', color: '#B8924A' },
  compliance_reminder: { icon: '⚖️', label: 'Compliance', color: '#f59e0b' },
  next_action: { icon: '➡️', label: 'Next Step', color: '#2D7A52' },
  rate_info: { icon: '📊', label: 'Rate Info', color: '#06b6d4' },
  question_prompt: { icon: '❓', label: 'Ask This', color: '#B8924A' },
  closing_technique: { icon: '🎯', label: 'Close', color: '#ec4899' },
  rapport_builder: { icon: '🤝', label: 'Build Rapport', color: '#14b8a6' },
  warning: { icon: '⚠️', label: 'Warning', color: '#dc2626' },
};

const PRIORITY_STYLES = {
  critical: { borderColor: '#dc2626', glow: true },
  high: { borderColor: '#f59e0b', glow: false },
  medium: { borderColor: '#3b82f6', glow: false },
  low: { borderColor: '#6b7280', glow: false },
};

// WebSocket connection states
const WS_STATE = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error',
};

export function LiveCallWhisper({ callId, leadId, loanId, callerInfo, onCallEnd }) {
  const [wsState, setWsState] = useState(WS_STATE.DISCONNECTED);
  const [whispers, setWhispers] = useState([]);
  const [callContext, setCallContext] = useState(null);
  const [askPrompt, setAskPrompt] = useState('');
  const [isAskingAI, setIsAskingAI] = useState(false);
  const [showAskInput, setShowAskInput] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
  const WS_BASE = API_BASE.replace('https://', 'wss://').replace('http://', 'ws://');

  // Connect to WebSocket
  const connectWebSocket = useCallback(() => {
    if (!callId) return;

    setWsState(WS_STATE.CONNECTING);

    try {
      const ws = new WebSocket(`${WS_BASE}/api/v1/call-whisper/ws/${callId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('Whisper WebSocket connected');
        setWsState(WS_STATE.CONNECTED);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setWsState(WS_STATE.ERROR);
      };

      ws.onclose = () => {
        console.log('WebSocket closed');
        setWsState(WS_STATE.DISCONNECTED);
        // Attempt reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          if (callId) connectWebSocket();
        }, 3000);
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setWsState(WS_STATE.ERROR);
    }
  }, [callId, WS_BASE]);

  // Handle WebSocket messages
  const handleWebSocketMessage = (message) => {
    switch (message.type) {
      case 'connected':
        console.log('Call session connected:', message.call_id);
        break;
      case 'whisper':
        setWhispers((prev) => {
          // Add new whisper if not already present
          if (!prev.find((w) => w.id === message.data.id)) {
            return [message.data, ...prev];
          }
          return prev;
        });
        break;
      case 'dismissed':
        setWhispers((prev) =>
          prev.map((w) =>
            w.id === message.whisper_id ? { ...w, dismissed: true } : w
          )
        );
        break;
      case 'marked_used':
        setWhispers((prev) =>
          prev.map((w) =>
            w.id === message.whisper_id ? { ...w, used: true } : w
          )
        );
        break;
      case 'pong':
        // Heartbeat response
        break;
      default:
        console.log('Unknown message type:', message.type);
    }
  };

  // Start call session
  const startCall = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/call-whisper/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          call_id: callId,
          lead_id: leadId,
          loan_id: loanId,
          caller_name: callerInfo?.name,
          caller_type: callerInfo?.type || 'prospect',
          loan_purpose: callerInfo?.loanPurpose,
          loan_type: callerInfo?.loanType,
          loan_amount: callerInfo?.loanAmount,
          credit_score: callerInfo?.creditScore,
        }),
      });

      if (response.ok) {
        const context = await response.json();
        setCallContext(context);
        connectWebSocket();
      }
    } catch (err) {
      console.error('Failed to start call:', err);
    }
  };

  // Send transcript segment
  const sendTranscript = (speaker, text) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'transcript',
          speaker,
          text,
          confidence: 1.0,
        })
      );
      setTranscript((prev) => [
        ...prev,
        { speaker, text, timestamp: new Date().toISOString() },
      ]);
    }
  };

  // Dismiss whisper
  const dismissWhisper = (whisperId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'dismiss',
          whisper_id: whisperId,
        })
      );
    }
    setWhispers((prev) =>
      prev.map((w) => (w.id === whisperId ? { ...w, dismissed: true } : w))
    );
  };

  // Mark whisper as used
  const markWhisperUsed = (whisperId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: 'used',
          whisper_id: whisperId,
        })
      );
    }
    setWhispers((prev) =>
      prev.map((w) => (w.id === whisperId ? { ...w, used: true } : w))
    );
  };

  // Ask AI for whisper
  const askAI = async () => {
    if (!askPrompt.trim()) return;

    setIsAskingAI(true);
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'ask',
            prompt: askPrompt,
          })
        );
      } else {
        // Fallback to REST API
        const response = await fetch(
          `${API_BASE}/api/v1/call-whisper/${callId}/ask`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: askPrompt }),
          }
        );
        if (response.ok) {
          const whisper = await response.json();
          setWhispers((prev) => [whisper, ...prev]);
        }
      }
      setAskPrompt('');
      setShowAskInput(false);
    } catch (err) {
      console.error('Failed to ask AI:', err);
    } finally {
      setIsAskingAI(false);
    }
  };

  // End call
  const endCall = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/call-whisper/${callId}/end`,
        { method: 'POST' }
      );
      if (response.ok) {
        const summary = await response.json();
        if (onCallEnd) onCallEnd(summary);
      }
    } catch (err) {
      console.error('Failed to end call:', err);
    }

    // Cleanup
    if (wsRef.current) {
      wsRef.current.close();
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
  };

  // Heartbeat to keep connection alive
  useEffect(() => {
    const heartbeatInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    return () => clearInterval(heartbeatInterval);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  // Auto-start call when component mounts
  useEffect(() => {
    if (callId && !callContext) {
      startCall();
    }
  }, [callId]);

  // Filter active whispers
  const activeWhispers = whispers.filter((w) => !w.dismissed);
  const usedWhispers = whispers.filter((w) => w.used);

  return (
    <div className="live-call-whisper">
      {/* Header */}
      <div className="whisper-header">
        <div className="header-left">
          <h2>Live Call Coaching</h2>
          <div className={`connection-status ${wsState}`}>
            <span className="status-dot"></span>
            {wsState === WS_STATE.CONNECTED ? 'Live' : wsState}
          </div>
        </div>
        <div className="header-right">
          <button
            className="ask-ai-btn"
            onClick={() => setShowAskInput(!showAskInput)}
          >
            🤖 Ask AI
          </button>
          <button className="end-call-btn" onClick={endCall}>
            End Call
          </button>
        </div>
      </div>

      {/* Ask AI Input */}
      {showAskInput && (
        <div className="ask-ai-input">
          <input
            type="text"
            placeholder="What do you need help with? (e.g., 'How should I handle rate objection?')"
            value={askPrompt}
            onChange={(e) => setAskPrompt(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && askAI()}
            autoFocus
          />
          <button onClick={askAI} disabled={isAskingAI || !askPrompt.trim()}>
            {isAskingAI ? 'Thinking...' : 'Get Suggestion'}
          </button>
        </div>
      )}

      {/* Call Context */}
      {callContext && (
        <div className="call-context">
          <div className="context-item">
            <span className="label">Caller:</span>
            <span className="value">{callContext.caller_name || 'Unknown'}</span>
          </div>
          <div className="context-item">
            <span className="label">Stage:</span>
            <span className={`value stage-${callContext.call_stage}`}>
              {callContext.call_stage}
            </span>
          </div>
          <div className="context-item">
            <span className="label">Sentiment:</span>
            <span className={`value sentiment-${callContext.sentiment}`}>
              {callContext.sentiment}
            </span>
          </div>
          <div className="context-item">
            <span className="label">Duration:</span>
            <span className="value">
              {Math.floor((callContext.duration_seconds || 0) / 60)}:
              {String((callContext.duration_seconds || 0) % 60).padStart(2, '0')}
            </span>
          </div>
        </div>
      )}

      {/* Whispers */}
      <div className="whispers-container">
        {activeWhispers.length === 0 ? (
          <div className="no-whispers">
            <div className="listening-indicator">
              <span className="pulse"></span>
              <span className="pulse delay-1"></span>
              <span className="pulse delay-2"></span>
            </div>
            <p>Listening for conversation cues...</p>
            <p className="hint">
              AI coaching suggestions will appear here based on the conversation
            </p>
          </div>
        ) : (
          <div className="whispers-list">
            {activeWhispers.map((whisper) => (
              <WhisperCard
                key={whisper.id}
                whisper={whisper}
                onDismiss={() => dismissWhisper(whisper.id)}
                onUse={() => markWhisperUsed(whisper.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Stats Footer */}
      <div className="whisper-footer">
        <div className="stat">
          <span className="stat-value">{activeWhispers.length}</span>
          <span className="stat-label">Active</span>
        </div>
        <div className="stat">
          <span className="stat-value">{usedWhispers.length}</span>
          <span className="stat-label">Used</span>
        </div>
        <div className="stat">
          <span className="stat-value">{transcript.length}</span>
          <span className="stat-label">Segments</span>
        </div>
      </div>
    </div>
  );
}

// Individual Whisper Card
function WhisperCard({ whisper, onDismiss, onUse }) {
  const typeConfig = WHISPER_TYPES[whisper.type] || WHISPER_TYPES.talking_point;
  const priorityConfig = PRIORITY_STYLES[whisper.priority] || PRIORITY_STYLES.medium;

  return (
    <div
      className={`whisper-card priority-${whisper.priority} ${whisper.used ? 'used' : ''} ${priorityConfig.glow ? 'glow' : ''}`}
      style={{ '--border-color': priorityConfig.borderColor }}
    >
      <div className="whisper-header-row">
        <div className="whisper-type" style={{ color: typeConfig.color }}>
          <span className="type-icon">{typeConfig.icon}</span>
          <span className="type-label">{typeConfig.label}</span>
        </div>
        <div className="whisper-actions">
          {!whisper.used && (
            <button className="use-btn" onClick={onUse} title="Mark as used">
              ✓
            </button>
          )}
          <button className="dismiss-btn" onClick={onDismiss} title="Dismiss">
            ×
          </button>
        </div>
      </div>

      <div className="whisper-title">{whisper.title}</div>
      <div className="whisper-content">{whisper.content}</div>

      {whisper.context && (
        <div className="whisper-context">
          <span className="context-label">Context:</span> {whisper.context}
        </div>
      )}

      <div className="whisper-timestamp">
        {new Date(whisper.timestamp).toLocaleTimeString()}
      </div>
    </div>
  );
}

// Compact widget for embedding in other pages
export function LiveCallWhisperWidget({ callId, onStartCall }) {
  const [isActive, setIsActive] = useState(false);

  if (isActive && callId) {
    return (
      <div className="whisper-widget-active">
        <LiveCallWhisper
          callId={callId}
          onCallEnd={() => setIsActive(false)}
        />
      </div>
    );
  }

  return (
    <div className="whisper-widget-idle">
      <div className="widget-content">
        <div className="widget-icon">🎧</div>
        <h3>Live Call Coaching</h3>
        <p>Get real-time AI suggestions during calls</p>
        <button
          className="start-coaching-btn"
          onClick={() => {
            if (onStartCall) onStartCall();
            setIsActive(true);
          }}
        >
          Start Coaching Session
        </button>
      </div>
      <div className="widget-features">
        <div className="feature">
          <span className="feature-icon">🛡️</span>
          <span>Objection Handling</span>
        </div>
        <div className="feature">
          <span className="feature-icon">📊</span>
          <span>Rate Info</span>
        </div>
        <div className="feature">
          <span className="feature-icon">⚖️</span>
          <span>Compliance</span>
        </div>
        <div className="feature">
          <span className="feature-icon">🎯</span>
          <span>Closing Tips</span>
        </div>
      </div>
    </div>
  );
}

// Demo component for testing
export function LiveCallWhisperDemo() {
  const [callId] = useState(`demo-${Date.now()}`);
  const [demoTranscript, setDemoTranscript] = useState('');
  const [speaker, setSpeaker] = useState('caller');

  return (
    <div className="whisper-demo">
      <div className="demo-controls">
        <h3>Demo Mode - Simulate Conversation</h3>
        <div className="demo-input">
          <select value={speaker} onChange={(e) => setSpeaker(e.target.value)}>
            <option value="caller">Caller</option>
            <option value="agent">Agent</option>
          </select>
          <input
            type="text"
            placeholder="Enter transcript text..."
            value={demoTranscript}
            onChange={(e) => setDemoTranscript(e.target.value)}
          />
          <button onClick={() => {
            // In demo mode, this would send to the backend
            setDemoTranscript('');
          }}>
            Send
          </button>
        </div>
        <div className="demo-suggestions">
          <p>Try saying:</p>
          <ul>
            <li>"Your rates seem too high" (rate objection)</li>
            <li>"I'm not ready to decide yet" (timing objection)</li>
            <li>"What's the process?" (question)</li>
            <li>"I'm frustrated with this" (negative sentiment)</li>
          </ul>
        </div>
      </div>
      <LiveCallWhisper
        callId={callId}
        callerInfo={{ name: 'Demo Caller', type: 'prospect' }}
      />
    </div>
  );
}

export default LiveCallWhisper;
