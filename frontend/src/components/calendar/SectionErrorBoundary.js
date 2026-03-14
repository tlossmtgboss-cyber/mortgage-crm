import React from 'react';

/**
 * SectionErrorBoundary -- Lightweight React error boundary for individual calendar/dashboard sections.
 *
 * Isolates crashes to a single UI section so sibling panels remain functional.
 * Shows a minimal fallback with a "Try Again" button that resets the boundary
 * and re-mounts the child tree.
 *
 * Used in: Calendar, CalendarSettings, and any page wrapping independent sections
 *
 * @param {Object} props
 * @param {string} [props.sectionName='Section'] - Human-readable section name for error logging
 * @param {Function} [props.onError] - Optional callback(error, errorInfo) invoked when an error is caught
 * @param {React.ReactNode|Function} [props.fallback] - Custom fallback UI; if a function, receives { error, reset }
 * @param {React.ReactNode} props.children - Child components to wrap with error protection
 * @returns {React.ReactElement}
 *
 * @example
 * <SectionErrorBoundary sectionName="Upcoming Appointments">
 *   <UpcomingAppointments />
 * </SectionErrorBoundary>
 *
 * @example
 * <SectionErrorBoundary
 *   sectionName="Task List"
 *   fallback={({ error, reset }) => <MyFallback onRetry={reset} />}
 * >
 *   <TaskList />
 * </SectionErrorBoundary>
 */
class SectionErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleReset = this.handleReset.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    const name = this.props.sectionName || 'Section';
    console.error(`[${name}] Error:`, error, errorInfo);

    if (typeof this.props.onError === 'function') {
      try {
        this.props.onError(error, errorInfo);
      } catch {
        // Prevent callback errors from causing further issues
      }
    }
  }

  handleReset() {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback (ReactNode or render function)
      const { fallback } = this.props;

      if (typeof fallback === 'function') {
        return fallback({ error: this.state.error, reset: this.handleReset });
      }

      if (fallback) {
        return fallback;
      }

      // Default fallback
      return (
        <div
          className="cal-section-error"
          role="alert"
          aria-live="assertive"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '20px 16px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '6px',
            color: '#991b1b',
            fontSize: '13px',
            lineHeight: '1.5',
            minHeight: '64px',
          }}
        >
          {/* Warning icon */}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            style={{ flexShrink: 0 }}
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>

          <p style={{ margin: 0, flex: 1 }}>
            {this.props.sectionName
              ? `${this.props.sectionName} encountered an error.`
              : 'This section encountered an error.'}
          </p>

          <button
            onClick={this.handleReset}
            type="button"
            aria-label="Try again"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 14px',
              fontSize: '12px',
              fontWeight: 600,
              color: '#991b1b',
              background: '#fff',
              border: '1px solid #fecaca',
              borderRadius: '4px',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              lineHeight: 1,
              transition: 'background 150ms ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#fef2f2'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#fff'; }}
          >
            {/* Refresh icon */}
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default SectionErrorBoundary;
