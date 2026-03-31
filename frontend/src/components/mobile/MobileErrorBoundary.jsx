import React from 'react';

/**
 * Error Boundary for mobile pages.
 * Catches render errors and shows a recovery UI with retry and dashboard fallback.
 */
class MobileErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[MobileErrorBoundary] Caught render error:', error);
    console.error('[MobileErrorBoundary] Component stack:', errorInfo?.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.content}>
            <div style={styles.iconWrapper}>
              <svg
                width="56"
                height="56"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#ef4444"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h2 style={styles.title}>Something went wrong</h2>
            <p style={styles.message}>
              An unexpected error occurred. You can try again or return to the dashboard.
            </p>
            <button
              onClick={this.handleRetry}
              style={styles.retryButton}
            >
              Tap to retry
            </button>
            <a
              href="/mobile-home"
              style={styles.dashboardLink}
            >
              Go to Dashboard
            </a>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100vh',
    backgroundColor: '#f9fafb',
    padding: '24px',
    boxSizing: 'border-box',
  },
  content: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
    maxWidth: '360px',
    width: '100%',
  },
  iconWrapper: {
    marginBottom: '20px',
  },
  title: {
    fontSize: '20px',
    fontWeight: '600',
    color: '#111827',
    margin: '0 0 8px 0',
  },
  message: {
    fontSize: '15px',
    color: '#6b7280',
    lineHeight: '1.5',
    margin: '0 0 28px 0',
  },
  retryButton: {
    display: 'block',
    width: '100%',
    padding: '14px 24px',
    fontSize: '16px',
    fontWeight: '600',
    color: '#ffffff',
    backgroundColor: '#3b82f6',
    border: 'none',
    borderRadius: '12px',
    cursor: 'pointer',
    marginBottom: '12px',
    minHeight: '48px',
    WebkitTapHighlightColor: 'transparent',
  },
  dashboardLink: {
    display: 'block',
    width: '100%',
    padding: '14px 24px',
    fontSize: '16px',
    fontWeight: '500',
    color: '#3b82f6',
    backgroundColor: 'transparent',
    border: '1.5px solid #3b82f6',
    borderRadius: '12px',
    textDecoration: 'none',
    textAlign: 'center',
    minHeight: '48px',
    boxSizing: 'border-box',
    WebkitTapHighlightColor: 'transparent',
  },
};

export default MobileErrorBoundary;
