import React, { useState, useEffect } from 'react';
import { schedulerAPI } from '../../services/api';
import StatusBadge from './StatusBadge';

/**
 * AppointmentTimeline - Visual horizontal timeline showing appointment status progression.
 *
 * Standard flow: [Booked] -> [Confirmed] -> [Reminded] -> [Checked In] -> [Completed]
 *
 * Props:
 *   appointmentId  - ID of the appointment to load timeline for
 *   currentStatus  - Current status string (if known, avoids extra fetch)
 *   compact        - Boolean, renders a compact single-line version for list views
 *   onStatusChange - Callback when user observes a status change
 *   history        - Pre-loaded history array (skips API fetch if provided)
 */

const STANDARD_STEPS = [
  { key: 'booked',     label: 'Booked' },
  { key: 'confirmed',  label: 'Confirmed' },
  { key: 'reminded',   label: 'Reminded' },
  { key: 'checked_in', label: 'Checked In' },
  { key: 'completed',  label: 'Completed' },
];

// Terminal/exception statuses that override the standard flow
const TERMINAL_STATUSES = {
  cancelled:   { icon: 'X',  color: '#dc2626', label: 'Cancelled' },
  no_show:     { icon: 'X',  color: '#dc2626', label: 'No Show' },
  rescheduled: { icon: '->',  color: '#d97706', label: 'Rescheduled' },
};

function formatTimestamp(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  const now = new Date();
  const isThisYear = d.getFullYear() === now.getFullYear();

  const dateStr = d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(isThisYear ? {} : { year: 'numeric' }),
  });
  const timeStr = d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
  return `${dateStr}, ${timeStr}`;
}

function getStepTimestamp(history, stepKey) {
  if (!history || !history.length) return null;
  const entry = history.find(h => h.new_status === stepKey);
  return entry ? entry.changed_at : null;
}

function getStepNotes(history, stepKey) {
  if (!history || !history.length) return null;
  const entry = history.find(h => h.new_status === stepKey);
  return entry ? entry.notes : null;
}

function getStepSource(history, stepKey) {
  if (!history || !history.length) return null;
  const entry = history.find(h => h.new_status === stepKey);
  return entry ? entry.change_source : null;
}

// Determine which steps are completed based on status and history
function getCompletedSteps(currentStatus, history) {
  const statusIndex = STANDARD_STEPS.findIndex(s => s.key === currentStatus);

  // For terminal statuses, figure out how far we got
  if (statusIndex === -1) {
    // Find the last standard step that appeared in history
    let lastStandardIdx = -1;
    if (history && history.length) {
      for (const entry of history) {
        const idx = STANDARD_STEPS.findIndex(s => s.key === entry.new_status);
        if (idx > lastStandardIdx) lastStandardIdx = idx;
      }
    }
    return lastStandardIdx;
  }

  return statusIndex;
}

// ========================================================================
// COMPACT MODE (single-line for list views)
// ========================================================================
function CompactTimeline({ currentStatus, history }) {
  const isTerminal = currentStatus in TERMINAL_STATUSES;
  const completedUpTo = getCompletedSteps(currentStatus, history);
  const terminalConfig = isTerminal ? TERMINAL_STATUSES[currentStatus] : null;

  return (
    <div style={styles.compactContainer} role="group" aria-label="Appointment status timeline">
      <div style={styles.compactTrack}>
        {STANDARD_STEPS.map((step, idx) => {
          const isCompleted = idx <= completedUpTo;
          const isCurrent = !isTerminal && idx === completedUpTo;

          return (
            <React.Fragment key={step.key}>
              {idx > 0 && (
                <div
                  style={{
                    ...styles.compactConnector,
                    backgroundColor: isCompleted ? '#22c55e' : '#e5e7eb',
                  }}
                />
              )}
              <div
                style={{
                  ...styles.compactDot,
                  ...(isCompleted
                    ? styles.compactDotCompleted
                    : styles.compactDotFuture),
                  ...(isCurrent ? styles.compactDotCurrent : {}),
                }}
                title={`${step.label}${getStepTimestamp(history, step.key) ? ': ' + formatTimestamp(getStepTimestamp(history, step.key)) : ''}`}
                aria-label={`${step.label}: ${isCompleted ? 'complete' : isCurrent ? 'current' : 'pending'}`}
              >
                {isCompleted && !isCurrent && (
                  <svg width="8" height="8" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path d="M2 6L5 9L10 3" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </div>
            </React.Fragment>
          );
        })}

        {/* Terminal status indicator */}
        {isTerminal && terminalConfig && (
          <>
            <div style={{ ...styles.compactConnector, backgroundColor: terminalConfig.color }} />
            <div
              style={{
                ...styles.compactDot,
                backgroundColor: terminalConfig.color,
                borderColor: terminalConfig.color,
              }}
              title={terminalConfig.label}
              aria-label={`${terminalConfig.label}`}
            >
              {terminalConfig.icon === 'X' ? (
                <svg width="8" height="8" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2 2L10 10M10 2L2 10" stroke="white" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              ) : (
                <svg width="8" height="8" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2 6H8M6 3L9 6L6 9" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </div>
          </>
        )}
      </div>
      <StatusBadge status={currentStatus} size="sm" />
    </div>
  );
}

// ========================================================================
// FULL MODE (horizontal with labels, timestamps, notes)
// ========================================================================
function FullTimeline({ appointmentId, currentStatus, history, appointmentSummary }) {
  const isTerminal = currentStatus in TERMINAL_STATUSES;
  const completedUpTo = getCompletedSteps(currentStatus, history);
  const terminalConfig = isTerminal ? TERMINAL_STATUSES[currentStatus] : null;

  return (
    <div style={styles.fullContainer} role="group" aria-label="Appointment status timeline">
      {/* Header */}
      <div style={styles.fullHeader}>
        <span style={styles.fullTitle}>Status Timeline</span>
        <StatusBadge status={currentStatus} size="md" />
      </div>

      {/* Timeline track */}
      <div style={styles.fullTrack}>
        {STANDARD_STEPS.map((step, idx) => {
          const isCompleted = idx <= completedUpTo;
          const isCurrent = !isTerminal && idx === completedUpTo;
          const isFuture = idx > completedUpTo;
          const timestamp = getStepTimestamp(history, step.key);
          const notes = getStepNotes(history, step.key);
          const source = getStepSource(history, step.key);

          return (
            <div key={step.key} style={styles.fullStep}>
              {/* Connector line (not on first item) */}
              {idx > 0 && (
                <div
                  style={{
                    ...styles.fullConnector,
                    backgroundColor: isCompleted ? '#22c55e' : '#e5e7eb',
                  }}
                />
              )}

              {/* Dot */}
              <div
                style={{
                  ...styles.fullDot,
                  ...(isCompleted && !isCurrent ? styles.fullDotCompleted : {}),
                  ...(isCurrent ? styles.fullDotCurrent : {}),
                  ...(isFuture ? styles.fullDotFuture : {}),
                }}
              >
                {isCompleted && !isCurrent && (
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M3 8L6.5 11.5L13 4.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
                {isCurrent && (
                  <div style={styles.currentPulse} />
                )}
              </div>

              {/* Label + timestamp */}
              <div style={styles.fullLabelGroup}>
                <span style={{
                  ...styles.fullLabel,
                  color: isFuture ? '#9ca3af' : '#111827',
                  fontWeight: isCurrent ? 600 : 500,
                }}>
                  {step.label}
                </span>
                {timestamp && (
                  <span style={styles.fullTimestamp}>{formatTimestamp(timestamp)}</span>
                )}
                {source && source !== 'manual' && (
                  <span style={styles.sourceTag}>{source}</span>
                )}
                {notes && (
                  <span style={styles.fullNotes}>{notes}</span>
                )}
              </div>
            </div>
          );
        })}

        {/* Terminal status step (if applicable) */}
        {isTerminal && terminalConfig && (
          <div style={styles.fullStep}>
            <div
              style={{
                ...styles.fullConnector,
                backgroundColor: terminalConfig.color,
              }}
            />
            <div
              style={{
                ...styles.fullDot,
                backgroundColor: terminalConfig.color,
                borderColor: terminalConfig.color,
              }}
            >
              {terminalConfig.icon === 'X' ? (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M3 3L13 13M13 3L3 13" stroke="white" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M3 8H11M8 4L12 8L8 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </div>
            <div style={styles.fullLabelGroup}>
              <span style={{ ...styles.fullLabel, color: terminalConfig.color, fontWeight: 600 }}>
                {terminalConfig.label}
              </span>
              {getStepTimestamp(history, currentStatus) && (
                <span style={styles.fullTimestamp}>
                  {formatTimestamp(getStepTimestamp(history, currentStatus))}
                </span>
              )}
              {/* Show cancellation reason or reschedule info */}
              {currentStatus === 'cancelled' && appointmentSummary?.cancellation_reason && (
                <span style={styles.fullNotes}>
                  Reason: {appointmentSummary.cancellation_reason}
                </span>
              )}
              {currentStatus === 'rescheduled' && appointmentSummary?.reschedule_count > 0 && (
                <span style={styles.fullNotes}>
                  Rescheduled {appointmentSummary.reschedule_count} time{appointmentSummary.reschedule_count !== 1 ? 's' : ''}
                </span>
              )}
              {getStepNotes(history, currentStatus) && (
                <span style={styles.fullNotes}>
                  {getStepNotes(history, currentStatus)}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ========================================================================
// MAIN COMPONENT
// ========================================================================
function AppointmentTimeline({
  appointmentId,
  currentStatus: statusProp,
  compact = false,
  history: historyProp,
  onStatusChange,
}) {
  const [timelineData, setTimelineData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const currentStatus = timelineData?.current_status || statusProp || 'booked';
  const history = timelineData?.history || historyProp || [];
  const appointmentSummary = timelineData?.appointment_summary || {};

  useEffect(() => {
    if (!appointmentId || historyProp) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    schedulerAPI.getAppointmentTimeline(appointmentId)
      .then(data => {
        if (!cancelled) {
          setTimelineData(data);
          if (onStatusChange && data.current_status !== statusProp) {
            onStatusChange(data.current_status);
          }
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err.response?.data?.detail || 'Failed to load timeline');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointmentId]);

  if (loading) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.loadingDots}>
          <span style={styles.loadingDot} />
          <span style={{ ...styles.loadingDot, animationDelay: '0.15s' }} />
          <span style={{ ...styles.loadingDot, animationDelay: '0.3s' }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.errorContainer}>
        <span style={styles.errorText}>{error}</span>
      </div>
    );
  }

  if (compact) {
    return <CompactTimeline currentStatus={currentStatus} history={history} />;
  }

  return (
    <FullTimeline
      appointmentId={appointmentId}
      currentStatus={currentStatus}
      history={history}
      appointmentSummary={appointmentSummary}
    />
  );
}

// ========================================================================
// STYLES (inline for portability, uses CSS variables where available)
// ========================================================================
const styles = {
  // Compact mode
  compactContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  compactTrack: {
    display: 'flex',
    alignItems: 'center',
    gap: '0px',
  },
  compactDot: {
    width: '14px',
    height: '14px',
    borderRadius: '50%',
    border: '2px solid #e5e7eb',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    transition: 'all 200ms ease',
  },
  compactDotCompleted: {
    backgroundColor: '#22c55e',
    borderColor: '#22c55e',
  },
  compactDotCurrent: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
    width: '16px',
    height: '16px',
    boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.2)',
  },
  compactDotFuture: {
    backgroundColor: 'white',
    borderColor: '#d1d5db',
  },
  compactConnector: {
    width: '12px',
    height: '2px',
    flexShrink: 0,
  },

  // Full mode
  fullContainer: {
    padding: '16px',
    backgroundColor: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
  },
  fullHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
  },
  fullTitle: {
    fontSize: '14px',
    fontWeight: 600,
    color: '#374151',
  },
  fullTrack: {
    display: 'flex',
    alignItems: 'flex-start',
    position: 'relative',
  },
  fullStep: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    flex: 1,
    position: 'relative',
    minWidth: '0',
  },
  fullConnector: {
    position: 'absolute',
    top: '14px',
    right: '50%',
    width: '100%',
    height: '3px',
    zIndex: 0,
  },
  fullDot: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    border: '3px solid #e5e7eb',
    backgroundColor: 'white',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
    position: 'relative',
    flexShrink: 0,
    transition: 'all 200ms ease',
  },
  fullDotCompleted: {
    backgroundColor: '#22c55e',
    borderColor: '#22c55e',
  },
  fullDotCurrent: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
    width: '32px',
    height: '32px',
    boxShadow: '0 0 0 4px rgba(59, 130, 246, 0.2)',
  },
  fullDotFuture: {
    backgroundColor: 'white',
    borderColor: '#d1d5db',
  },
  currentPulse: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    backgroundColor: 'white',
    animation: 'timeline-pulse 2s ease-in-out infinite',
  },
  fullLabelGroup: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    marginTop: '8px',
    gap: '2px',
    textAlign: 'center',
    maxWidth: '100%',
    overflow: 'hidden',
  },
  fullLabel: {
    fontSize: '12px',
    fontWeight: 500,
    lineHeight: 1.2,
  },
  fullTimestamp: {
    fontSize: '10px',
    color: '#6b7280',
    lineHeight: 1.2,
  },
  sourceTag: {
    fontSize: '9px',
    color: '#B8924A',
    backgroundColor: '#f3e8ff',
    padding: '1px 5px',
    borderRadius: '4px',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
  },
  fullNotes: {
    fontSize: '10px',
    color: '#9ca3af',
    fontStyle: 'italic',
    lineHeight: 1.2,
    maxWidth: '120px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },

  // Loading
  loadingContainer: {
    display: 'flex',
    justifyContent: 'center',
    padding: '12px',
  },
  loadingDots: {
    display: 'flex',
    gap: '6px',
  },
  loadingDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: '#9ca3af',
    animation: 'timeline-loading 0.6s ease-in-out infinite alternate',
  },

  // Error
  errorContainer: {
    padding: '8px 12px',
    backgroundColor: '#fef2f2',
    borderRadius: '6px',
    border: '1px solid #fecaca',
  },
  errorText: {
    fontSize: '12px',
    color: '#991b1b',
  },
};

// Inject keyframes for pulse and loading animations
if (typeof document !== 'undefined') {
  const styleId = 'appointment-timeline-keyframes';
  if (!document.getElementById(styleId)) {
    const styleSheet = document.createElement('style');
    styleSheet.id = styleId;
    styleSheet.textContent = `
      @keyframes timeline-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.6; transform: scale(0.8); }
      }
      @keyframes timeline-loading {
        from { opacity: 0.3; transform: scale(0.8); }
        to { opacity: 1; transform: scale(1); }
      }
      @media (max-width: 640px) {
        [data-timeline-responsive="true"] .timeline-full-track {
          flex-direction: column !important;
          align-items: flex-start !important;
        }
        [data-timeline-responsive="true"] .timeline-full-step {
          flex-direction: row !important;
          align-items: flex-start !important;
          gap: 12px;
          width: 100%;
        }
        [data-timeline-responsive="true"] .timeline-full-connector {
          position: static !important;
          width: 3px !important;
          height: 24px !important;
          margin-left: 13px;
        }
        [data-timeline-responsive="true"] .timeline-full-label-group {
          align-items: flex-start !important;
          text-align: left !important;
          margin-top: 0 !important;
        }
      }
    `;
    document.head.appendChild(styleSheet);
  }
}

export default AppointmentTimeline;
