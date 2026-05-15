/**
 * Call Timeline Component
 *
 * Displays a chronological list of call sessions for a client.
 */

import React from 'react';

const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const formatDuration = (seconds) => {
  if (!seconds) return '';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const CallTimeline = ({ calls, selectedCall, onSelectCall }) => {
  if (!calls || calls.length === 0) {
    return (
      <div className="call-timeline">
        <p className="no-calls">No calls recorded yet</p>
      </div>
    );
  }

  return (
    <div className="call-timeline">
      <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151' }}>
        Call History ({calls.length})
      </h4>

      {calls.map((call) => (
        <div
          key={call.id}
          className={`call-timeline-item ${selectedCall?.id === call.id ? 'selected' : ''}`}
          onClick={() => onSelectCall(call)}
        >
          <div className="call-date">
            {formatDate(call.started_at || call.created_at)}
          </div>

          <div className="call-title">
            {call.participants?.length > 0
              ? call.participants.map(p => p.name || p.role).filter(Boolean).join(', ')
              : 'Call Recording'}
          </div>

          <div className="call-meta">
            <span className={`call-badge status-${call.status}`}>
              {call.status?.replace('_', ' ')}
            </span>

            <span className={`call-badge mode-${call.capture_mode}`}>
              {call.capture_mode?.replace('_', ' ')}
            </span>

            {call.duration_seconds && (
              <span className="call-badge" style={{ background: '#f3f4f6', color: '#374151' }}>
                {formatDuration(call.duration_seconds)}
              </span>
            )}

            {call.artifact_count > 0 && (
              <span className="call-badge" style={{ background: '#F5EDD9', color: '#3730a3' }}>
                {call.artifact_count} items
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default CallTimeline;
