/**
 * Stacked Notes Component
 *
 * Chronological notes view across ALL calls for a client.
 *
 * Features:
 * - Notes sorted newest first (new notes on top, prior notes pushed down)
 * - Date/time stamp with call mode badge
 * - Source indicator (Scribe/JR LO/Underwriter)
 * - Visual timeline connector between notes
 */

import React, { useState, useEffect } from 'react';
import { sanitizeHTML } from '../../../utils/sanitize';

const SOURCE_CONFIG = {
  scribe: {
    label: 'Scribe',
    color: '#3b82f6',
    bgColor: '#eff6ff',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
    ),
  },
  jrlo: {
    label: 'JR LO',
    color: '#B8924A',
    bgColor: '#FDF9F0',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="12" y1="1" x2="12" y2="23" />
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
  },
  underwriter: {
    label: 'Underwriter',
    color: '#dc2626',
    bgColor: '#fef2f2',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
        <line x1="4" y1="22" x2="4" y2="15" />
      </svg>
    ),
  },
  unknown: {
    label: 'Note',
    color: '#6b7280',
    bgColor: '#f9fafb',
    icon: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
      </svg>
    ),
  },
};

const CALL_MODE_CONFIG = {
  phone: { label: 'Phone Call', icon: '📞' },
  video: { label: 'Video Call', icon: '📹' },
  computer: { label: 'Computer Call', icon: '💻' },
  inbound: { label: 'Inbound', icon: '📥' },
  outbound: { label: 'Outbound', icon: '📤' },
};

const StackedNotes = ({ clientId, notes, loading, onRefresh }) => {
  const [expandedNotes, setExpandedNotes] = useState(new Set());

  const toggleExpand = (noteId) => {
    setExpandedNotes(prev => {
      const next = new Set(prev);
      if (next.has(noteId)) {
        next.delete(noteId);
      } else {
        next.add(noteId);
      }
      return next;
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatTime = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  if (loading) {
    return (
      <div className="stacked-notes">
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
          <div className="loading-spinner" style={{
            width: '40px',
            height: '40px',
            border: '3px solid #e5e7eb',
            borderTopColor: '#3b82f6',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 16px',
          }} />
          Loading notes...
        </div>
      </div>
    );
  }

  if (!notes || notes.length === 0) {
    return (
      <div className="stacked-notes">
        <div style={{
          textAlign: 'center',
          padding: '40px',
          color: '#6b7280',
          background: '#f9fafb',
          borderRadius: '8px',
        }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ margin: '0 auto 16px', opacity: 0.5 }}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <p style={{ margin: 0 }}>No notes yet for this client.</p>
          <p style={{ margin: '8px 0 0', fontSize: '0.875rem' }}>
            Notes will appear here after calls are analyzed.
          </p>
        </div>
      </div>
    );
  }

  // Group notes by date
  const notesByDate = notes.reduce((acc, note) => {
    const dateKey = formatDate(note.created_at);
    if (!acc[dateKey]) {
      acc[dateKey] = [];
    }
    acc[dateKey].push(note);
    return acc;
  }, {});

  return (
    <div className="stacked-notes">
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px',
      }}>
        <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Call Notes History ({notes.length})
        </h4>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{
              padding: '6px 12px',
              background: 'none',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Refresh
          </button>
        )}
      </div>

      {/* Timeline */}
      <div className="notes-timeline">
        {Object.entries(notesByDate).map(([dateKey, dateNotes], dateIndex) => (
          <div key={dateKey} className="date-group">
            {/* Date Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              marginBottom: '12px',
              marginTop: dateIndex > 0 ? '24px' : 0,
            }}>
              <div style={{
                padding: '4px 12px',
                background: '#111827',
                color: '#fff',
                borderRadius: '20px',
                fontSize: '0.75rem',
                fontWeight: '600',
              }}>
                {dateKey}
              </div>
              <div style={{
                flex: 1,
                height: '1px',
                background: '#e5e7eb',
              }} />
            </div>

            {/* Notes for this date */}
            {dateNotes.map((note, noteIndex) => {
              const source = note.source || note.structured_data?.source || 'unknown';
              const sourceConfig = SOURCE_CONFIG[source] || SOURCE_CONFIG.unknown;
              const callMode = note.call_mode;
              const callModeConfig = CALL_MODE_CONFIG[callMode];
              const isExpanded = expandedNotes.has(note.id);
              const isLastInDate = noteIndex === dateNotes.length - 1;

              return (
                <div
                  key={note.id}
                  className="stacked-note-card"
                  style={{
                    display: 'flex',
                    gap: '12px',
                    marginBottom: isLastInDate ? 0 : '12px',
                  }}
                >
                  {/* Timeline connector */}
                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    width: '24px',
                  }}>
                    <div style={{
                      width: '12px',
                      height: '12px',
                      borderRadius: '50%',
                      background: sourceConfig.color,
                      border: '2px solid #fff',
                      boxShadow: '0 0 0 2px ' + sourceConfig.color,
                    }} />
                    {!isLastInDate && (
                      <div style={{
                        flex: 1,
                        width: '2px',
                        background: '#e5e7eb',
                        marginTop: '4px',
                      }} />
                    )}
                  </div>

                  {/* Note content */}
                  <div
                    style={{
                      flex: 1,
                      background: '#fff',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                      borderLeft: `3px solid ${sourceConfig.color}`,
                      overflow: 'hidden',
                    }}
                  >
                    {/* Note header */}
                    <div
                      onClick={() => toggleExpand(note.id)}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '12px',
                        background: sourceConfig.bgColor,
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 8px',
                          background: sourceConfig.color,
                          color: '#fff',
                          borderRadius: '4px',
                          fontSize: '0.7rem',
                          fontWeight: '600',
                        }}>
                          {sourceConfig.icon}
                          {sourceConfig.label}
                        </span>

                        {callModeConfig && (
                          <span style={{
                            fontSize: '0.75rem',
                            color: '#6b7280',
                          }}>
                            {callModeConfig.icon} {callModeConfig.label}
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                          {formatTime(note.created_at)}
                        </span>
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="#6b7280"
                          strokeWidth="2"
                          style={{
                            transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                            transition: 'transform 0.2s ease',
                          }}
                        >
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </div>
                    </div>

                    {/* Note body */}
                    <div style={{
                      padding: '12px',
                      maxHeight: isExpanded ? '1000px' : '80px',
                      overflow: 'hidden',
                      transition: 'max-height 0.3s ease',
                    }}>
                      <div
                        style={{
                          fontSize: '0.875rem',
                          color: '#374151',
                          lineHeight: '1.6',
                          whiteSpace: 'pre-wrap',
                        }}
                        dangerouslySetInnerHTML={{
                          __html: sanitizeHTML(
                            note.content?.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                              .replace(/\n/g, '<br/>') || '',
                            { allowedTags: ['strong', 'br', 'em', 'b', 'i'] }
                          )
                        }}
                      />

                      {/* Key points */}
                      {note.structured_data?.key_points && note.structured_data.key_points.length > 0 && (
                        <div style={{ marginTop: '12px' }}>
                          <span style={{
                            fontSize: '0.75rem',
                            fontWeight: '600',
                            color: '#6b7280',
                            textTransform: 'uppercase',
                          }}>
                            Key Points:
                          </span>
                          <ul style={{
                            margin: '8px 0 0',
                            paddingLeft: '20px',
                            fontSize: '0.8rem',
                            color: '#4b5563',
                          }}>
                            {note.structured_data.key_points.slice(0, isExpanded ? undefined : 3).map((point, i) => (
                              <li key={i} style={{ marginBottom: '4px' }}>{point}</li>
                            ))}
                            {!isExpanded && note.structured_data.key_points.length > 3 && (
                              <li style={{ color: '#9ca3af', fontStyle: 'italic' }}>
                                +{note.structured_data.key_points.length - 3} more...
                              </li>
                            )}
                          </ul>
                        </div>
                      )}

                      {/* Call outcome badge */}
                      {note.structured_data?.call_outcome && (
                        <div style={{ marginTop: '12px' }}>
                          <span style={{
                            padding: '4px 10px',
                            borderRadius: '20px',
                            fontSize: '0.7rem',
                            fontWeight: '600',
                            background: getOutcomeBackground(note.structured_data.call_outcome),
                            color: getOutcomeColor(note.structured_data.call_outcome),
                          }}>
                            Call: {note.structured_data.call_outcome.replace('_', ' ')}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Expand hint */}
                    {!isExpanded && note.content && note.content.length > 200 && (
                      <div style={{
                        padding: '8px 12px',
                        borderTop: '1px solid #e5e7eb',
                        fontSize: '0.75rem',
                        color: '#6b7280',
                        textAlign: 'center',
                        cursor: 'pointer',
                      }}
                      onClick={() => toggleExpand(note.id)}
                      >
                        Click to expand...
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

// Helper functions
const getOutcomeBackground = (outcome) => {
  const backgrounds = {
    positive: '#dcfce7',
    neutral: '#f3f4f6',
    needs_follow_up: '#fef3c7',
    negative: '#fee2e2',
  };
  return backgrounds[outcome] || '#f3f4f6';
};

const getOutcomeColor = (outcome) => {
  const colors = {
    positive: '#166534',
    neutral: '#4b5563',
    needs_follow_up: '#92400e',
    negative: '#991b1b',
  };
  return colors[outcome] || '#4b5563';
};

export default StackedNotes;
