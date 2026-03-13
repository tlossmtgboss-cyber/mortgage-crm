import React from 'react';
import ErrorBoundary from '../common/ErrorBoundary';
import '../common/ErrorBoundary.css';

const isDev = process.env.NODE_ENV === 'development';

/**
 * Calendar-specific error boundary.
 *
 * Wraps the common ErrorBoundary with calendar-tailored fallback UI:
 *   - "Something went wrong loading the calendar" messaging
 *   - "Reload Calendar" resets state and optionally reloads data
 *   - "Switch to List View" as a safe fallback when the grid view crashes
 *   - Logs component stack for debugging
 *
 * Props:
 *   - onReloadCalendar  (function)  Called when user clicks "Reload Calendar"
 *   - onSwitchToList    (function)  Called when user clicks "Switch to List View"
 *   - currentView       (string)    Current calendar view name (for logging)
 *   - children          (ReactNode)
 */
class CalendarErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorTimestamp: null,
    };
    this.handleReset = this.handleReset.bind(this);
    this.handleSwitchToList = this.handleSwitchToList.bind(this);
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      error,
      errorTimestamp: new Date().toLocaleTimeString(),
    };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });

    const view = this.props.currentView || 'unknown';
    console.error(
      `[CalendarErrorBoundary] Error in calendar view="${view}":`,
      error
    );
    if (errorInfo && errorInfo.componentStack) {
      console.error(
        '[CalendarErrorBoundary] Component stack:',
        errorInfo.componentStack
      );
    }
  }

  handleReset() {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorTimestamp: null,
    });

    if (typeof this.props.onReloadCalendar === 'function') {
      this.props.onReloadCalendar();
    }
  }

  handleSwitchToList() {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      errorTimestamp: null,
    });

    if (typeof this.props.onSwitchToList === 'function') {
      this.props.onSwitchToList();
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="ceb-container" role="alert">
          <div className="ceb-card">
            {/* Calendar icon */}
            <svg
              className="ceb-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
              {/* X mark inside calendar to indicate error */}
              <line x1="9" y1="14" x2="15" y2="19" />
              <line x1="15" y1="14" x2="9" y2="19" />
            </svg>

            <h2 className="ceb-title">
              Something went wrong loading the calendar
            </h2>
            <p className="ceb-message">
              An error occurred while rendering the calendar. You can try
              reloading, or switch to the list view.
            </p>
            <p className="ceb-timestamp">
              Error occurred at {this.state.errorTimestamp}
            </p>

            {isDev && this.state.error && (
              <details className="eb-details">
                <summary>Error Details (dev only)</summary>
                <pre className="eb-pre">
                  {this.state.error.toString()}
                </pre>
                {this.state.error.stack && (
                  <pre className="eb-pre eb-stack">
                    {this.state.error.stack}
                  </pre>
                )}
                {this.state.errorInfo?.componentStack && (
                  <pre className="eb-pre eb-stack">
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </details>
            )}

            <div className="eb-btn-group">
              <button
                className="eb-btn eb-btn-primary"
                onClick={this.handleReset}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                Reload Calendar
              </button>
              {typeof this.props.onSwitchToList === 'function' && (
                <button
                  className="eb-btn eb-btn-secondary"
                  onClick={this.handleSwitchToList}
                >
                  Switch to List View
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Thin wrapper around the common ErrorBoundary for calendar widgets/sections.
 *
 * Use this to wrap individual calendar sub-sections (sidebar, mini-calendar, etc.)
 * so that a failure in one widget does not take down the entire calendar page.
 *
 * Props:
 *   - label      (string)     Human-readable name shown in fallback
 *   - onRetry    (function)   Called when user clicks Retry
 *   - children   (ReactNode)
 */
function CalendarWidgetBoundary({ label, onRetry, children }) {
  return (
    <ErrorBoundary
      fallback={(error, resetFn) => (
        <div className="web-container" role="alert">
          <div className="web-inner">
            <svg
              className="web-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>
              {label ? `Failed to load ${label}.` : 'Something went wrong.'}
            </span>
            <button
              className="web-retry"
              onClick={() => {
                resetFn();
                if (typeof onRetry === 'function') onRetry();
              }}
            >
              Retry
            </button>
          </div>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}

export default CalendarErrorBoundary;
export { CalendarWidgetBoundary };
