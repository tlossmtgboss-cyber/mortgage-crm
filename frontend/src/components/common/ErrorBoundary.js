import React from 'react';
import './ErrorBoundary.css';

const isDev = process.env.NODE_ENV === 'development';

/**
 * General-purpose React Error Boundary.
 *
 * Props:
 *   - fallback      (ReactNode | function(error, resetFn))  Custom fallback UI
 *   - onError        (function(error, errorInfo))             Callback when error is caught
 *   - resetKeys      (Array)  Values that, when changed, reset the boundary (e.g. route path)
 *   - children       (ReactNode)
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
    this.resetErrorState = this.resetErrorState.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });

    // Log error with component stack trace
    console.error('[ErrorBoundary] Caught error:', error);
    if (errorInfo && errorInfo.componentStack) {
      console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
    }

    // Invoke optional callback
    if (typeof this.props.onError === 'function') {
      this.props.onError(error, errorInfo);
    }
  }

  componentDidUpdate(prevProps) {
    // Auto-reset when resetKeys change (e.g. on route navigation)
    if (this.state.hasError && this.props.resetKeys) {
      const prevKeys = prevProps.resetKeys || [];
      const nextKeys = this.props.resetKeys || [];
      const changed = nextKeys.length !== prevKeys.length ||
        nextKeys.some((key, i) => key !== prevKeys[i]);
      if (changed) {
        this.resetErrorState();
      }
    }
  }

  resetErrorState() {
    this.setState({ hasError: false, error: null, errorInfo: null });
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback: function or element
      if (this.props.fallback) {
        if (typeof this.props.fallback === 'function') {
          return this.props.fallback(this.state.error, this.resetErrorState);
        }
        return this.props.fallback;
      }

      // Default fallback
      return (
        <div className="eb-container" role="alert">
          <div className="eb-card">
            <div className="eb-icon-wrapper">
              <svg className="eb-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h2 className="eb-title">Something went wrong</h2>
            <p className="eb-message">
              An unexpected error occurred. Please try again.
            </p>

            {isDev && this.state.error && (
              <details className="eb-details">
                <summary>Error Details (dev only)</summary>
                <pre className="eb-pre">{this.state.error.toString()}</pre>
                {this.state.error.stack && (
                  <pre className="eb-pre eb-stack">{this.state.error.stack}</pre>
                )}
                {this.state.errorInfo?.componentStack && (
                  <pre className="eb-pre eb-stack">{this.state.errorInfo.componentStack}</pre>
                )}
              </details>
            )}

            <button className="eb-btn eb-btn-primary" onClick={this.resetErrorState}>
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
