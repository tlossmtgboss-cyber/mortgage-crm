import React from 'react';

// Check if Sentry is available (will be loaded in production)
const getSentry = () => {
  if (typeof window !== 'undefined' && window.Sentry) {
    return window.Sentry;
  }
  return null;
};

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      eventId: null
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);

    // Auto-reload on ChunkLoadError (stale chunks after deployment)
    if (error.name === 'ChunkLoadError' ||
        (error.message && error.message.includes('Loading chunk')) ||
        (error.message && error.message.includes('Loading CSS chunk'))) {
      // Clear cache and reload
      window.location.reload();
      return;
    }

    // Report to Sentry if available
    const Sentry = getSentry();
    if (Sentry) {
      Sentry.withScope(scope => {
        scope.setExtras(errorInfo);
        const eventId = Sentry.captureException(error);
        this.setState({ eventId });
      });
    }

    this.setState({
      error,
      errorInfo
    });
  }

  handleReportFeedback = () => {
    const Sentry = getSentry();
    if (Sentry && this.state.eventId) {
      Sentry.showReportDialog({ eventId: this.state.eventId });
    }
  };

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, eventId: null });
  };

  render() {
    if (this.state.hasError) {
      const isProduction = process.env.NODE_ENV === 'production';
      const Sentry = getSentry();

      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
          backgroundColor: '#f9fafb'
        }}>
          <div style={{
            maxWidth: '500px',
            width: '100%',
            backgroundColor: 'white',
            borderRadius: '12px',
            padding: '32px',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)'
          }}>
            {/* Error Icon */}
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: '#fef2f2',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px'
            }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </div>

            <h1 style={{
              margin: '0 0 12px',
              fontSize: '24px',
              fontWeight: '600',
              color: '#111827',
              textAlign: 'center'
            }}>
              Something went wrong
            </h1>

            <p style={{
              margin: '0 0 24px',
              fontSize: '14px',
              color: '#6b7280',
              textAlign: 'center',
              lineHeight: '1.5'
            }}>
              We're sorry, but something unexpected happened. Our team has been notified and is working on a fix.
            </p>

            {/* Action Buttons */}
            <div style={{
              display: 'flex',
              gap: '12px',
              justifyContent: 'center',
              flexWrap: 'wrap'
            }}>
              <button
                onClick={this.handleRetry}
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#2563eb'}
                onMouseOut={(e) => e.target.style.backgroundColor = '#3b82f6'}
              >
                Try Again
              </button>

              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: '10px 20px',
                  backgroundColor: 'white',
                  color: '#374151',
                  border: '1px solid #d1d5db',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '500',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
                onMouseOver={(e) => e.target.style.backgroundColor = '#f9fafb'}
                onMouseOut={(e) => e.target.style.backgroundColor = 'white'}
              >
                Reload Page
              </button>

              {Sentry && this.state.eventId && (
                <button
                  onClick={this.handleReportFeedback}
                  style={{
                    padding: '10px 20px',
                    backgroundColor: 'white',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: '500',
                    cursor: 'pointer'
                  }}
                >
                  Report Issue
                </button>
              )}
            </div>

            {/* Error Details (Development Only) */}
            {!isProduction && this.state.error && (
              <details style={{
                marginTop: '24px',
                padding: '16px',
                backgroundColor: '#fef2f2',
                borderRadius: '8px',
                fontSize: '12px'
              }}>
                <summary style={{
                  cursor: 'pointer',
                  color: '#991b1b',
                  fontWeight: '500',
                  marginBottom: '8px'
                }}>
                  Error Details (Development Only)
                </summary>
                <pre style={{
                  margin: '8px 0 0',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  color: '#7f1d1d',
                  fontFamily: 'monospace'
                }}>
                  {this.state.error.toString()}
                  {this.state.errorInfo && this.state.errorInfo.componentStack}
                </pre>
              </details>
            )}

            {/* Support Link */}
            <p style={{
              margin: '24px 0 0',
              fontSize: '12px',
              color: '#9ca3af',
              textAlign: 'center'
            }}>
              If this problem persists, please contact{' '}
              <a
                href="mailto:support@perenniaai.com"
                style={{ color: '#3b82f6', textDecoration: 'none' }}
              >
                support@perenniaai.com
              </a>
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
