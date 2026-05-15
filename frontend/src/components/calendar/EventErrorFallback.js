import React from 'react';

/**
 * Lightweight fallback rendered in place of a single event card when it
 * throws during render.  Keeps the rest of the calendar grid intact.
 *
 * This is NOT a class-based error boundary itself -- it is meant to be used
 * as the fallback UI rendered by a small ErrorBoundary wrapping each event.
 *
 * Props:
 *   - event       (object)    The event data (may be partially invalid)
 *   - error       (Error)     The error that was caught
 *   - onRetry     (function)  Called when user clicks Retry; should reset the
 *                              parent boundary so the event re-renders
 */
function EventErrorFallback({ event, error, onRetry }) {
  const timeLabel = formatSafeTime(event);

  return (
    <div
      className="event-error-fallback"
      role="alert"
      title={error ? error.message : 'Error loading event'}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '4px 8px',
        fontSize: '12px',
        color: '#991b1b',
        background: '#fef2f2',
        border: '1px solid #fecaca',
        borderRadius: '4px',
        minHeight: '24px',
        lineHeight: '1.4',
      }}
    >
      {/* Warning icon */}
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ flexShrink: 0 }}
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>

      <span style={{ flex: 1 }}>
        {timeLabel ? `${timeLabel} - ` : ''}Error loading event
      </span>

      {typeof onRetry === 'function' && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRetry();
          }}
          style={{
            background: 'none',
            border: 'none',
            color: '#1F3D2E',
            fontWeight: 600,
            fontSize: '12px',
            cursor: 'pointer',
            padding: '0 2px',
            textDecoration: 'underline',
            textUnderlineOffset: '2px',
            whiteSpace: 'nowrap',
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Tiny error boundary that wraps a single event card.
 *
 * Usage:
 *   <EventBoundary event={event}>
 *     <DayEvent event={event} ... />
 *   </EventBoundary>
 *
 * If the child throws, EventErrorFallback is rendered instead,
 * keeping the rest of the calendar grid stable.
 */
class EventBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleRetry = this.handleRetry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    const eventId = this.props.event?.id || 'unknown';
    console.error(
      `[EventBoundary] Failed to render event id=${eventId}:`,
      error
    );
    if (errorInfo?.componentStack) {
      console.error('[EventBoundary] Component stack:', errorInfo.componentStack);
    }
  }

  handleRetry() {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <EventErrorFallback
          event={this.props.event}
          error={this.state.error}
          onRetry={this.handleRetry}
        />
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Attempt to extract a displayable time string from event data
 * without throwing if the data is malformed.
 */
function formatSafeTime(event) {
  if (!event) return '';
  try {
    const raw = event.start_time || event.scheduled_start;
    if (!raw) return '';
    const d = new Date(raw);
    if (isNaN(d.getTime())) return '';
    const hours = d.getHours();
    const minutes = d.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const h = hours % 12 || 12;
    const m = minutes.toString().padStart(2, '0');
    return `${h}:${m} ${ampm}`;
  } catch {
    return '';
  }
}

export default EventErrorFallback;
export { EventBoundary };
