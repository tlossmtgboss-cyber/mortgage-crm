import React from 'react';

/**
 * RouteErrorBoundary -- Error boundary for route-level isolation.
 *
 * Wraps individual page components so a crash in one route does not bring down
 * Navigation, sidebars, or the rest of the application. Shows an inline error
 * card with "Try Again" and "Go to Dashboard" actions.
 *
 * Differences from the top-level ErrorBoundary:
 *   - Renders *inside* the app layout (navigation stays visible)
 *   - Auto-reloads on ChunkLoadError (stale deploy chunks)
 *   - Logs to console; does not report to backend (the top-level boundary handles that)
 *
 * Props:
 *   - fallback  (ReactNode)  Optional custom fallback UI
 *   - children  (ReactNode)
 */
class RouteErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[RouteErrorBoundary] Caught error:', error, errorInfo);

    // Auto-reload on ChunkLoadError (stale chunks after deployment)
    const errorMessage = error?.message || error?.toString() || '';
    if (
      error?.name === 'ChunkLoadError' ||
      errorMessage.includes('Loading chunk') ||
      errorMessage.includes('Loading CSS chunk') ||
      errorMessage.includes('ChunkLoadError')
    ) {
      console.log('[RouteErrorBoundary] ChunkLoadError detected, auto-reloading...');
      window.location.reload();
      return;
    }

    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleGoToDashboard = () => {
    window.location.href = '/dashboard';
  };

  render() {
    if (this.state.hasError) {
      // Allow custom fallback UI via prop
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const isDev = process.env.NODE_ENV === 'development';

      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '60vh',
            padding: '40px 20px',
            fontFamily: 'var(--font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif)',
          }}
        >
          <div
            style={{
              maxWidth: '460px',
              width: '100%',
              background: 'var(--color-bg-surface, #fff)',
              border: '1px solid var(--color-border, rgba(139, 92, 68, 0.15))',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '32px 24px',
              textAlign: 'center',
              boxShadow: 'var(--shadow-md, 0 4px 6px rgba(0, 0, 0, 0.07))',
            }}
          >
            {/* Warning icon */}
            <div style={{ marginBottom: '16px', color: 'var(--color-error, #C0152F)' }}>
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>

            <h2
              style={{
                margin: '0 0 8px',
                fontSize: 'var(--font-xl, 20px)',
                fontWeight: 'var(--weight-bold, 600)',
                color: 'var(--color-text-primary, #1a1a1a)',
              }}
            >
              Something went wrong
            </h2>
            <p
              style={{
                margin: '0 0 24px',
                fontSize: 'var(--font-base, 14px)',
                color: 'var(--color-text-secondary, #666)',
                lineHeight: 'var(--line-normal, 1.5)',
              }}
            >
              This page encountered an error. You can try again or navigate to the dashboard.
            </p>

            {/* Dev-only error details */}
            {isDev && this.state.error && (
              <details
                style={{
                  textAlign: 'left',
                  marginBottom: '20px',
                  padding: '12px',
                  background: '#1e1e2e',
                  borderRadius: 'var(--radius-sm, 6px)',
                  fontSize: '12px',
                }}
              >
                <summary
                  style={{
                    cursor: 'pointer',
                    color: '#cdd6f4',
                    fontWeight: 550,
                    userSelect: 'none',
                  }}
                >
                  Error Details (dev only)
                </summary>
                <pre
                  style={{
                    margin: '8px 0 0',
                    color: '#f38ba8',
                    fontFamily: 'var(--font-mono, monospace)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    lineHeight: 1.5,
                  }}
                >
                  {this.state.error.toString()}
                </pre>
                {this.state.error.stack && (
                  <pre
                    style={{
                      margin: '8px 0 0',
                      color: '#a6adc8',
                      fontFamily: 'var(--font-mono, monospace)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      lineHeight: 1.5,
                      maxHeight: '180px',
                      overflowY: 'auto',
                    }}
                  >
                    {this.state.error.stack}
                  </pre>
                )}
                {this.state.errorInfo?.componentStack && (
                  <pre
                    style={{
                      margin: '8px 0 0',
                      color: '#a6adc8',
                      fontFamily: 'var(--font-mono, monospace)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      lineHeight: 1.5,
                      maxHeight: '120px',
                      overflowY: 'auto',
                    }}
                  >
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </details>
            )}

            {/* Action buttons */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                justifyContent: 'center',
                flexWrap: 'wrap',
              }}
            >
              <button
                onClick={this.handleReset}
                type="button"
                style={{
                  padding: '10px 24px',
                  background: 'var(--color-primary, #218d8d)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 'var(--radius-base, 8px)',
                  fontSize: 'var(--font-base, 14px)',
                  fontWeight: 550,
                  cursor: 'pointer',
                }}
              >
                Try Again
              </button>
              <button
                onClick={this.handleGoToDashboard}
                type="button"
                style={{
                  padding: '10px 24px',
                  background: 'var(--color-bg-secondary, rgba(139, 92, 68, 0.05))',
                  color: 'var(--color-text-primary, #1a1a1a)',
                  border: '1px solid var(--color-border, rgba(139, 92, 68, 0.15))',
                  borderRadius: 'var(--radius-base, 8px)',
                  fontSize: 'var(--font-base, 14px)',
                  fontWeight: 550,
                  cursor: 'pointer',
                }}
              >
                Go to Dashboard
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default RouteErrorBoundary;
