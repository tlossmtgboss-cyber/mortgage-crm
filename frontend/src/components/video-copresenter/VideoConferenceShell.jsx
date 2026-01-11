/**
 * Video Conference Shell
 * Main container component for AI Voice Co-Presenter video conference
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { NavigationBar } from './NavigationBar';
import { TabContent } from './TabContent';
import { AIPresenterControls } from './AIPresenterControls';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const VideoConferenceShell = ({
  callSessionId,
  clientId,
  userRole = 'lo', // 'lo' | 'borrower' | 'realtor'
  onClose
}) => {
  // State
  const [session, setSession] = useState(null);
  const [activeTab, setActiveTab] = useState('process');
  const [tabState, setTabState] = useState({});
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiMode, setAiMode] = useState('silent');
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [aiText, setAiText] = useState('');
  const [pendingActions, setPendingActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [participants, setParticipants] = useState([]);

  // Refs
  const wsRef = useRef(null);
  const videoContainerRef = useRef(null);

  // Fetch session data
  const fetchSession = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch session: ${response.status}`);
      }

      const data = await response.json();
      setSession(data);
      setActiveTab(data.active_tab || 'process');
      setAiEnabled(data.ai_enabled || false);
      setAiMode(data.ai_mode || 'silent');
      setParticipants(data.participants || []);
      setTabState(data.state_snapshot || {});
      setLoading(false);
    } catch (err) {
      console.error('Error fetching session:', err);
      setError(err.message);
      setLoading(false);
    }
  }, [callSessionId]);

  // Initialize WebSocket connection
  const initWebSocket = useCallback(() => {
    const wsUrl = API_BASE_URL.replace('http', 'ws');
    const token = localStorage.getItem('token');
    const ws = new WebSocket(`${wsUrl}/api/v1/voice-copresenter/calls/${callSessionId}/ws?token=${token}`);

    ws.onopen = () => {
      console.log('[VideoConference] WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      console.log('[VideoConference] WebSocket disconnected');
      // Attempt reconnection after 3 seconds
      setTimeout(() => {
        if (wsRef.current === ws) {
          initWebSocket();
        }
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('[VideoConference] WebSocket error:', err);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [callSessionId]);

  // Handle WebSocket messages
  const handleWebSocketMessage = (data) => {
    switch (data.type) {
      case 'TAB_CHANGED':
        setActiveTab(data.active_tab);
        break;

      case 'TAB_STATE_UPDATED':
        setTabState(data.tab_state);
        break;

      case 'STATE_UPDATED':
        if (data.active_tab) setActiveTab(data.active_tab);
        if (data.ai_enabled !== undefined) setAiEnabled(data.ai_enabled);
        if (data.ai_mode) setAiMode(data.ai_mode);
        break;

      case 'AI_SPEAKING':
        setAiSpeaking(true);
        setAiText(data.text);
        break;

      case 'AI_STOPPED':
        setAiSpeaking(false);
        setAiText('');
        break;

      case 'ACTION_PROPOSED':
        setPendingActions(prev => [...prev, data.action]);
        break;

      case 'ACTION_APPROVED':
      case 'ACTION_REJECTED':
        setPendingActions(prev => prev.filter(a => a.action_id !== data.action_id));
        break;

      case 'CALL_ENDED':
        if (onClose) onClose();
        break;

      case 'PONG':
        // Heartbeat response
        break;

      default:
        console.log('[VideoConference] Unknown message type:', data.type);
    }
  };

  // Send WebSocket message
  const sendMessage = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Tab change handler (LO only)
  const handleTabChange = async (newTab) => {
    if (userRole !== 'lo') return;

    setActiveTab(newTab);

    // Broadcast to all participants
    sendMessage({
      type: 'TAB_CHANGED',
      active_tab: newTab
    });

    // Update backend
    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ active_tab: newTab })
      });
    } catch (err) {
      console.error('Error updating tab:', err);
    }
  };

  // AI controls
  const handleAIToggle = async (enabled) => {
    setAiEnabled(enabled);

    try {
      const token = localStorage.getItem('token');
      await fetch(`${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ai_enabled: enabled })
      });
    } catch (err) {
      console.error('Error toggling AI:', err);
    }
  };

  const handleExplainTab = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/explain-tab`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to trigger AI explanation');
      }
    } catch (err) {
      console.error('Error triggering AI explanation:', err);
    }
  };

  const handleSummarize = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/summarize`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to trigger AI summary');
      }
    } catch (err) {
      console.error('Error triggering AI summary:', err);
    }
  };

  const handleMuteAI = async () => {
    try {
      const token = localStorage.getItem('token');
      await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/mute`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      setAiSpeaking(false);
      setAiText('');
    } catch (err) {
      console.error('Error muting AI:', err);
    }
  };

  const handleApproveAction = async (actionId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/pending-actions/${actionId}/approve`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      setPendingActions(prev => prev.filter(a => a.action_id !== actionId));
    } catch (err) {
      console.error('Error approving action:', err);
    }
  };

  const handleRejectAction = async (actionId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/pending-actions/${actionId}/reject`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      setPendingActions(prev => prev.filter(a => a.action_id !== actionId));
    } catch (err) {
      console.error('Error rejecting action:', err);
    }
  };

  // Lifecycle
  useEffect(() => {
    fetchSession();
    const cleanup = initWebSocket();

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      sendMessage({ type: 'PING' });
    }, 30000);

    return () => {
      cleanup();
      clearInterval(pingInterval);
    };
  }, [fetchSession, initWebSocket, sendMessage]);

  // Loading state
  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#f9fafb'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '48px',
            height: '48px',
            margin: '0 auto 16px',
            border: '4px solid #e5e7eb',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }} />
          <p style={{ color: '#6b7280' }}>Connecting to call...</p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#f9fafb'
      }}>
        <div style={{
          textAlign: 'center',
          padding: '32px',
          backgroundColor: '#fff',
          borderRadius: '8px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
        }}>
          <p style={{ color: '#ef4444', marginBottom: '16px' }}>{error}</p>
          <button
            onClick={fetchSession}
            style={{
              padding: '8px 16px',
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      backgroundColor: '#f9fafb'
    }}>
      {/* Navigation Bar */}
      <NavigationBar
        tabs={['process', 'programs', 'rates', 'comparison', 'closing_costs']}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        userRole={userRole}
      />

      {/* Main Content Area */}
      <div style={{
        flex: 1,
        display: 'flex',
        gap: '16px',
        padding: '16px',
        overflow: 'hidden'
      }}>
        {/* Video Container */}
        <div
          ref={videoContainerRef}
          style={{
            width: '320px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '8px'
          }}
        >
          {/* Video tiles would go here - typically integrated with Daily.co or similar */}
          <div style={{
            aspectRatio: '4/3',
            backgroundColor: '#1f2937',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: '14px'
          }}>
            Loan Officer Video
          </div>
          <div style={{
            aspectRatio: '4/3',
            backgroundColor: '#374151',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: '14px'
          }}>
            Borrower Video
          </div>

          {/* Participants List */}
          <div style={{
            backgroundColor: '#fff',
            borderRadius: '8px',
            padding: '12px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
          }}>
            <h4 style={{ margin: '0 0 8px', fontSize: '12px', color: '#6b7280', textTransform: 'uppercase' }}>
              Participants
            </h4>
            {participants.length === 0 ? (
              <p style={{ fontSize: '14px', color: '#9ca3af', margin: 0 }}>Waiting for participants...</p>
            ) : (
              <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {participants.map((p, i) => (
                  <li key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '4px 0',
                    fontSize: '14px'
                  }}>
                    <span style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: '#10b981'
                    }} />
                    {p.display_name || p.role}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Tab Content */}
        <div style={{
          flex: 1,
          backgroundColor: '#fff',
          borderRadius: '12px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          padding: '24px',
          overflow: 'auto'
        }}>
          <TabContent
            tab={activeTab}
            state={tabState}
            clientId={clientId}
            callSessionId={callSessionId}
            userRole={userRole}
          />
        </div>
      </div>

      {/* AI Speaking Indicator */}
      {aiSpeaking && (
        <div style={{
          position: 'fixed',
          bottom: '100px',
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: '#2563eb',
          color: '#fff',
          padding: '12px 24px',
          borderRadius: '8px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
          maxWidth: '600px',
          textAlign: 'center',
          zIndex: 1000
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: '#fff',
              animation: 'pulse 1s infinite'
            }} />
            <span>{aiText}</span>
          </div>
          <style>{`
            @keyframes pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.5; }
            }
          `}</style>
        </div>
      )}

      {/* Pending Actions Toast */}
      {pendingActions.length > 0 && userRole === 'lo' && (
        <div style={{
          position: 'fixed',
          top: '80px',
          right: '20px',
          backgroundColor: '#fef3c7',
          border: '1px solid #f59e0b',
          borderRadius: '8px',
          padding: '16px',
          maxWidth: '350px',
          zIndex: 1000
        }}>
          <h4 style={{ margin: '0 0 8px', color: '#92400e', fontSize: '14px' }}>
            AI Proposed Action
          </h4>
          {pendingActions.map(action => (
            <div key={action.action_id} style={{ marginBottom: '12px' }}>
              <p style={{ margin: '0 0 8px', fontSize: '14px', color: '#78350f' }}>
                {action.description}
              </p>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => handleApproveAction(action.action_id)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#10b981',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px'
                  }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handleRejectAction(action.action_id)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#ef4444',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px'
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* AI Presenter Controls (LO Only) */}
      {userRole === 'lo' && (
        <AIPresenterControls
          callSessionId={callSessionId}
          enabled={aiEnabled}
          speaking={aiSpeaking}
          onToggle={handleAIToggle}
          onExplainTab={handleExplainTab}
          onSummarize={handleSummarize}
          onMute={handleMuteAI}
        />
      )}
    </div>
  );
};

export default VideoConferenceShell;
export { VideoConferenceShell };
