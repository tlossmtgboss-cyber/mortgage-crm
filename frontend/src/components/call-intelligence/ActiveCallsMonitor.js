/**
 * Active Calls Monitor Component
 *
 * Real-time monitoring of active calls with:
 * - Grid of active call cards
 * - Live call assistant panel
 * - Real-time transcript streaming
 * - AI suggestions during call
 */

import React, { useState, useEffect, useCallback } from 'react';
import { callMonitoringAPI } from '../../services/api';
import LiveCallAssistant from './LiveCallAssistant';

const ActiveCallsMonitor = ({
  sessions,
  onSelectSession,
  selectedSession,
  onRefresh,
}) => {
  const [liveTranscript, setLiveTranscript] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [isPolling, setIsPolling] = useState(false);

  // Format duration from seconds
  const formatDuration = (seconds) => {
    if (!seconds) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Calculate live duration
  const calculateLiveDuration = (startedAt) => {
    if (!startedAt) return '00:00';
    const start = new Date(startedAt);
    const now = new Date();
    const diffSeconds = Math.floor((now - start) / 1000);
    return formatDuration(diffSeconds);
  };

  // Fetch live transcript for selected session
  const fetchLiveTranscript = useCallback(async () => {
    if (!selectedSession?.id) return;

    try {
      const data = await callMonitoringAPI.getTranscript(selectedSession.id);
      setLiveTranscript(data.full_transcript || '');
    } catch (error) {
      console.error('Error fetching live transcript:', error);
    }
  }, [selectedSession?.id]);

  // Poll for updates when a session is selected
  useEffect(() => {
    if (!selectedSession?.id) {
      setLiveTranscript('');
      setSuggestions([]);
      return;
    }

    // Initial fetch
    fetchLiveTranscript();

    // Start polling
    setIsPolling(true);
    const interval = setInterval(() => {
      fetchLiveTranscript();
    }, 5000); // Every 5 seconds

    return () => {
      clearInterval(interval);
      setIsPolling(false);
    };
  }, [selectedSession?.id, fetchLiveTranscript]);

  // Generate mock suggestions based on transcript
  useEffect(() => {
    if (!liveTranscript) {
      setSuggestions([]);
      return;
    }

    // Simple keyword-based suggestions (in production, this would come from AI)
    const newSuggestions = [];
    const lowerTranscript = liveTranscript.toLowerCase();

    if (lowerTranscript.includes('rate') && !lowerTranscript.includes('explained rate')) {
      newSuggestions.push({
        type: 'question',
        text: 'Ask: "Are you comparing rates from multiple lenders?"',
        priority: 'high',
      });
    }

    if (lowerTranscript.includes('credit') && !lowerTranscript.includes('credit score')) {
      newSuggestions.push({
        type: 'question',
        text: 'Ask: "Do you know your approximate credit score?"',
        priority: 'medium',
      });
    }

    if (lowerTranscript.includes('down payment') || lowerTranscript.includes('downpayment')) {
      newSuggestions.push({
        type: 'info',
        text: 'Mention FHA option: 3.5% minimum down payment',
        priority: 'medium',
      });
    }

    if (lowerTranscript.includes('timeline') || lowerTranscript.includes('when')) {
      newSuggestions.push({
        type: 'compliance',
        text: 'Remind: Collect intent to proceed within 10 days of LE',
        priority: 'low',
      });
    }

    if (lowerTranscript.includes('income') && !lowerTranscript.includes('employment')) {
      newSuggestions.push({
        type: 'question',
        text: 'Follow up: "What type of employment - W2, self-employed, or 1099?"',
        priority: 'high',
      });
    }

    setSuggestions(newSuggestions);
  }, [liveTranscript]);

  // Get status display
  const getStatusDisplay = (status) => {
    switch (status) {
      case 'active':
        return { label: 'Active', class: 'status-active' };
      case 'capturing':
        return { label: 'Recording', class: 'status-capturing' };
      default:
        return { label: status, class: '' };
    }
  };

  // Get mode icon
  const getModeIcon = (mode) => {
    switch (mode) {
      case 'mobile_app':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="5" y="2" width="14" height="20" rx="2" ry="2" />
            <line x1="12" y1="18" x2="12.01" y2="18" />
          </svg>
        );
      case 'crm_web_call':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
        );
      case 'ambient_mic':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        );
      case 'video_call':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polygon points="23 7 16 12 23 17 23 7" />
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          </svg>
        );
      default:
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
          </svg>
        );
    }
  };

  if (sessions.length === 0) {
    return (
      <div className="active-calls-monitor">
        <div className="acm-empty">
          <div className="acm-empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
            </svg>
          </div>
          <h3>No Active Calls</h3>
          <p>Active calls will appear here for real-time monitoring and AI assistance.</p>
          <button className="acm-refresh-btn" onClick={onRefresh}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="active-calls-monitor">
      <div className="acm-layout">
        {/* Active Calls Grid */}
        <div className="acm-calls-panel">
          <div className="acm-panel-header">
            <h3>
              <span className="live-dot"></span>
              Active Calls ({sessions.length})
            </h3>
            <button className="acm-refresh-btn" onClick={onRefresh}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
              </svg>
            </button>
          </div>

          <div className="acm-calls-grid">
            {sessions.map(session => {
              const statusInfo = getStatusDisplay(session.status);
              const isSelected = selectedSession?.id === session.id;

              return (
                <div
                  key={session.id}
                  className={`acm-call-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectSession(session)}
                >
                  <div className="acm-card-header">
                    <div className="acm-mode-icon">
                      {getModeIcon(session.capture_mode)}
                    </div>
                    <span className={`acm-status ${statusInfo.class}`}>
                      <span className="status-dot"></span>
                      {statusInfo.label}
                    </span>
                  </div>

                  <div className="acm-card-body">
                    <div className="acm-caller-name">
                      {session.metadata?.caller_name || 'Active Call'}
                    </div>
                    {session.metadata?.phone && (
                      <div className="acm-phone">{session.metadata.phone}</div>
                    )}
                    <div className="acm-duration">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12 6 12 12 16 14" />
                      </svg>
                      {calculateLiveDuration(session.started_at)}
                    </div>
                  </div>

                  <div className="acm-card-footer">
                    <span className="acm-mode-label">
                      {session.capture_mode?.replace('_', ' ')}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Live Assistant Panel */}
        {selectedSession && (
          <LiveCallAssistant
            session={selectedSession}
            transcript={liveTranscript}
            suggestions={suggestions}
            isPolling={isPolling}
          />
        )}
      </div>
    </div>
  );
};

export default ActiveCallsMonitor;
