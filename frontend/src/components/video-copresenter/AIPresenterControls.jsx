/**
 * AI Presenter Controls
 * LO control panel for AI voice co-presenter
 */
import React, { useState } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const AI_MODES = [
  { id: 'passive', label: 'Passive', description: 'AI listens but does not speak', icon: '👂' },
  { id: 'copilot', label: 'Co-Pilot', description: 'AI suggests, LO approves', icon: '🤝' },
  { id: 'presenter', label: 'Presenter', description: 'AI speaks automatically', icon: '🎤' }
];

const QUICK_TOPICS = [
  { id: 'rate_explanation', label: 'Explain Rates', icon: '📊' },
  { id: 'process_overview', label: 'Process Overview', icon: '📋' },
  { id: 'closing_costs', label: 'Closing Costs', icon: '💰' },
  { id: 'compare_scenarios', label: 'Compare Options', icon: '⚖️' },
  { id: 'next_steps', label: 'Next Steps', icon: '➡️' },
  { id: 'faq_answer', label: 'Answer FAQ', icon: '❓' }
];

const AIPresenterControls = ({
  callSessionId,
  aiState = {},
  pendingActions = [],
  onModeChange,
  onMuteToggle,
  onActionApprove,
  onActionReject,
  onTopicTrigger
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [selectedMode, setSelectedMode] = useState(aiState.mode || 'copilot');
  const [isMuted, setIsMuted] = useState(aiState.muted || false);
  const [isLoading, setIsLoading] = useState(false);

  const handleModeChange = async (mode) => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/mode`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ mode })
        }
      );

      if (response.ok) {
        setSelectedMode(mode);
        onModeChange?.(mode);
      }
    } catch (err) {
      console.error('Error changing AI mode:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleMuteToggle = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/mute`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ muted: !isMuted })
        }
      );

      if (response.ok) {
        setIsMuted(!isMuted);
        onMuteToggle?.(!isMuted);
      }
    } catch (err) {
      console.error('Error toggling mute:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTopicTrigger = async (topicId) => {
    try {
      const token = localStorage.getItem('token');
      await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/ai/explain-tab`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ topic: topicId })
        }
      );
      onTopicTrigger?.(topicId);
    } catch (err) {
      console.error('Error triggering topic:', err);
    }
  };

  const handleApprove = async (actionId) => {
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
      onActionApprove?.(actionId);
    } catch (err) {
      console.error('Error approving action:', err);
    }
  };

  const handleReject = async (actionId) => {
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
      onActionReject?.(actionId);
    } catch (err) {
      console.error('Error rejecting action:', err);
    }
  };

  return (
    <div style={{
      backgroundColor: '#fff',
      borderRadius: '12px',
      border: '1px solid #e5e7eb',
      overflow: 'hidden',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
    }}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          width: '100%',
          padding: '12px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#f9fafb',
          border: 'none',
          borderBottom: isExpanded ? '1px solid #e5e7eb' : 'none',
          cursor: 'pointer'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '18px' }}>🤖</span>
          <span style={{ fontSize: '14px', fontWeight: '600', color: '#111827' }}>
            AI Co-Presenter
          </span>
          {aiState.is_speaking && (
            <span style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              backgroundColor: '#dcfce7',
              borderRadius: '9999px',
              fontSize: '11px',
              color: '#15803d'
            }}>
              <span style={{
                width: '6px',
                height: '6px',
                backgroundColor: '#22c55e',
                borderRadius: '50%',
                animation: 'pulse 1.5s ease-in-out infinite'
              }} />
              Speaking
            </span>
          )}
          {pendingActions.length > 0 && (
            <span style={{
              padding: '2px 8px',
              backgroundColor: '#fef3c7',
              borderRadius: '9999px',
              fontSize: '11px',
              fontWeight: '600',
              color: '#d97706'
            }}>
              {pendingActions.length} pending
            </span>
          )}
        </div>
        <span style={{
          transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s ease',
          color: '#9ca3af'
        }}>
          ▼
        </span>
      </button>

      {isExpanded && (
        <div style={{ padding: '16px' }}>
          {/* Mode Selector */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{
              fontSize: '12px',
              fontWeight: '600',
              color: '#6b7280',
              marginBottom: '8px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em'
            }}>
              AI Mode
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              {AI_MODES.map(mode => (
                <button
                  key={mode.id}
                  onClick={() => handleModeChange(mode.id)}
                  disabled={isLoading}
                  title={mode.description}
                  style={{
                    flex: 1,
                    padding: '10px 8px',
                    backgroundColor: selectedMode === mode.id ? '#2563eb' : '#fff',
                    color: selectedMode === mode.id ? '#fff' : '#374151',
                    border: `1px solid ${selectedMode === mode.id ? '#2563eb' : '#d1d5db'}`,
                    borderRadius: '8px',
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    opacity: isLoading ? 0.6 : 1,
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <span style={{ fontSize: '16px' }}>{mode.icon}</span>
                  <span style={{ fontSize: '11px', fontWeight: '500' }}>{mode.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Mute Control */}
          <div style={{ marginBottom: '16px' }}>
            <button
              onClick={handleMuteToggle}
              disabled={isLoading}
              style={{
                width: '100%',
                padding: '10px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                backgroundColor: isMuted ? '#fef2f2' : '#f0fdf4',
                color: isMuted ? '#dc2626' : '#16a34a',
                border: `1px solid ${isMuted ? '#fecaca' : '#bbf7d0'}`,
                borderRadius: '8px',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.6 : 1,
                fontSize: '13px',
                fontWeight: '500'
              }}
            >
              <span style={{ fontSize: '16px' }}>{isMuted ? '🔇' : '🔊'}</span>
              {isMuted ? 'AI Voice Muted' : 'AI Voice Active'}
            </button>
          </div>

          {/* Quick Topics */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{
              fontSize: '12px',
              fontWeight: '600',
              color: '#6b7280',
              marginBottom: '8px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em'
            }}>
              Quick Topics
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '8px'
            }}>
              {QUICK_TOPICS.map(topic => (
                <button
                  key={topic.id}
                  onClick={() => handleTopicTrigger(topic.id)}
                  style={{
                    padding: '8px',
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '4px',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f9fafb';
                    e.currentTarget.style.borderColor = '#2563eb';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#fff';
                    e.currentTarget.style.borderColor = '#e5e7eb';
                  }}
                >
                  <span style={{ fontSize: '16px' }}>{topic.icon}</span>
                  <span style={{ fontSize: '10px', color: '#6b7280', textAlign: 'center' }}>
                    {topic.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Pending Actions */}
          {pendingActions.length > 0 && (
            <div>
              <div style={{
                fontSize: '12px',
                fontWeight: '600',
                color: '#6b7280',
                marginBottom: '8px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Pending Approval
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {pendingActions.map(action => (
                  <div
                    key={action.id}
                    style={{
                      padding: '12px',
                      backgroundColor: '#fffbeb',
                      border: '1px solid #fcd34d',
                      borderRadius: '8px'
                    }}
                  >
                    <div style={{
                      fontSize: '12px',
                      fontWeight: '600',
                      color: '#92400e',
                      marginBottom: '4px',
                      textTransform: 'capitalize'
                    }}>
                      {action.action_type.replace('_', ' ')}
                    </div>
                    <div style={{
                      fontSize: '13px',
                      color: '#374151',
                      marginBottom: '8px'
                    }}>
                      {action.description || 'AI wants to perform this action'}
                    </div>
                    {action.preview_text && (
                      <div style={{
                        fontSize: '12px',
                        color: '#6b7280',
                        fontStyle: 'italic',
                        marginBottom: '8px',
                        padding: '8px',
                        backgroundColor: '#fff',
                        borderRadius: '4px',
                        border: '1px solid #e5e7eb'
                      }}>
                        "{action.preview_text.slice(0, 100)}..."
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => handleApprove(action.id)}
                        style={{
                          flex: 1,
                          padding: '8px 12px',
                          backgroundColor: '#059669',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: '500',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '4px'
                        }}
                      >
                        <span>✓</span> Approve
                      </button>
                      <button
                        onClick={() => handleReject(action.id)}
                        style={{
                          flex: 1,
                          padding: '8px 12px',
                          backgroundColor: '#fff',
                          color: '#dc2626',
                          border: '1px solid #dc2626',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: '500',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '4px'
                        }}
                      >
                        <span>✗</span> Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Status */}
          <div style={{
            marginTop: '16px',
            padding: '10px 12px',
            backgroundColor: '#f9fafb',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: aiState.is_speaking ? '#22c55e' : '#9ca3af',
                animation: aiState.is_speaking ? 'pulse 1.5s ease-in-out infinite' : 'none'
              }} />
              <span style={{ fontSize: '12px', color: '#6b7280' }}>
                {aiState.is_speaking ? 'AI is speaking...' : 'AI is listening'}
              </span>
            </div>
            <span style={{
              fontSize: '11px',
              color: '#9ca3af',
              padding: '2px 6px',
              backgroundColor: '#e5e7eb',
              borderRadius: '4px'
            }}>
              {selectedMode}
            </span>
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

export default AIPresenterControls;
export { AIPresenterControls };
