import React from 'react';
import './ErrorBoundary.css';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);

    // Auto-reload on ChunkLoadError (stale chunks after deployment)
    const errorMessage = error?.message || error?.toString() || '';
    if (error?.name === 'ChunkLoadError' ||
        errorMessage.includes('Loading chunk') ||
        errorMessage.includes('Loading CSS chunk') ||
        errorMessage.includes('ChunkLoadError')) {
      console.log('ChunkLoadError detected, auto-reloading...');
      window.location.reload();
      return;
    }

    this.setState({ error, errorInfo });

    // Post to error reporting endpoint if available
    try {
      const token = localStorage.getItem('token');
      const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
        ? 'https://api.perenniaai.com'
        : 'http://localhost:8000';

      fetch(`${API_BASE_URL}/api/v1/client-errors`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          error_message: error?.toString() || 'Unknown error',
          error_stack: error?.stack || '',
          component_stack: errorInfo?.componentStack || '',
          url: window.location.href,
          user_agent: navigator.userAgent,
          timestamp: new Date().toISOString(),
        }),
      }).catch(() => {
        // Silently fail — error reporting should never cause more errors
      });
    } catch {
      // Silently fail
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      const isDev = process.env.NODE_ENV === 'development';

      return (
        <div className="eb-fullpage-container" role="alert">
          <div className="eb-fullpage-card">
            <div className="eb-fullpage-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>

            <h1 className="eb-fullpage-title">Something went wrong</h1>
            <p className="eb-fullpage-message">
              An unexpected error occurred. You can try again or return to the home page.
            </p>

            {isDev && this.state.error && (
              <details className="eb-fullpage-details">
                <summary>Error Details (dev only)</summary>
                <pre className="eb-fullpage-pre">{this.state.error.toString()}</pre>
                {this.state.error.stack && (
                  <pre className="eb-fullpage-pre eb-fullpage-stack">{this.state.error.stack}</pre>
                )}
                {this.state.errorInfo?.componentStack && (
                  <pre className="eb-fullpage-pre eb-fullpage-stack">{this.state.errorInfo.componentStack}</pre>
                )}
              </details>
            )}

            <div className="eb-fullpage-actions">
              <button className="eb-fullpage-btn eb-fullpage-btn-primary" onClick={this.handleReset}>
                Try Again
              </button>
              <button className="eb-fullpage-btn eb-fullpage-btn-secondary" onClick={() => window.location.reload()}>
                Reload Page
              </button>
            </div>

            <a href="/" className="eb-fullpage-home-link" onClick={(e) => { e.preventDefault(); this.handleGoHome(); }}>
              Go Home
            </a>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
