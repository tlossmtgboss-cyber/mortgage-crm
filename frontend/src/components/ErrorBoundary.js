import React from 'react';
import html2canvas from 'html2canvas';
import './ErrorBoundary.css';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      isFixing: false,
      fixStatus: '',
      fixAttempts: 0,
      screenshot: null,
      aiAnalysis: null,
      fixRecommendation: '',
      fixStrategy: '',
      filesAffected: [],
      confidence: ''
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);

    // Check if there's a pre-captured screenshot
    const preErrorScreenshot = window.__preErrorScreenshot;
    if (preErrorScreenshot) {
      console.log('Using pre-captured screenshot');
      this.setState({
        error,
        errorInfo,
        screenshot: preErrorScreenshot
      });
      // Clear it so it doesn't get used again
      window.__preErrorScreenshot = null;
    } else {
      this.setState({
        error,
        errorInfo
      });
    }
  }

  captureScreenshot = async () => {
    try {
      const canvas = await html2canvas(document.body, {
        allowTaint: true,
        useCORS: true,
        logging: false,
        width: window.innerWidth,
        height: window.innerHeight
      });

      return canvas.toDataURL('image/png');
    } catch (error) {
      console.error('Screenshot capture failed:', error);
      return null;
    }
  };

  handleAutoFix = async () => {
    this.setState({ isFixing: true, fixStatus: 'Preparing error analysis...' });

    // Use existing screenshot if already captured, otherwise capture now
    let screenshot = this.state.screenshot;

    if (!screenshot) {
      this.setState({ fixStatus: 'Capturing screenshot...' });
      screenshot = await this.captureScreenshot();

      if (!screenshot) {
        this.setState({
          fixStatus: 'Failed to capture screenshot',
          isFixing: false
        });
        return;
      }

      this.setState({ screenshot });
    }

    this.setState({
      fixStatus: 'Sending error details to AI...',
      fixAttempts: this.state.fixAttempts + 1
    });

    try {
      const token = localStorage.getItem('token');
      const API_BASE_URL = window.location.hostname.includes('vercel.app')
        ? 'https://mortgage-crm-production-7a9a.up.railway.app'
        : 'http://localhost:8000';

      const response = await fetch(`${API_BASE_URL}/api/v1/auto-fix-error`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          error_message: this.state.error?.toString() || 'Unknown error',
          error_stack: this.state.error?.stack || '',
          component_stack: this.state.errorInfo?.componentStack || '',
          screenshot: screenshot,
          attempt_number: this.state.fixAttempts,
          url: window.location.href,
          user_agent: navigator.userAgent
        })
      });

      const data = await response.json();

      if (data.success) {
        this.setState({
          fixStatus: data.message,
          aiAnalysis: data.analysis,
          fixRecommendation: data.recommendation,
          fixStrategy: data.fix_strategy,
          filesAffected: data.files_affected,
          confidence: data.confidence,
          isFixing: false
        });

        // Note: Not auto-reloading because fixes need manual review for safety
      } else {
        this.setState({
          fixStatus: `Fix attempt ${this.state.fixAttempts} failed: ${data.message}`,
          isFixing: false
        });
      }
    } catch (error) {
      console.error('Auto-fix failed:', error);
      this.setState({
        fixStatus: `Error communicating with AI: ${error.message}`,
        isFixing: false
      });
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-container">
          <div className="error-boundary-content">
            <div className="error-boundary-header">
              <h1>⚠️ Something went wrong</h1>
              <p className="error-boundary-subtitle">
                An error has been detected in the application
              </p>
            </div>

            <div className="error-boundary-details">
              <div className="error-message">
                <strong>Error:</strong> {this.state.error?.toString()}
              </div>

              {this.state.error?.stack && (
                <details className="error-stack">
                  <summary>Stack Trace</summary>
                  <pre>{this.state.error.stack}</pre>
                </details>
              )}

              {this.state.errorInfo?.componentStack && (
                <details className="error-component-stack">
                  <summary>Component Stack</summary>
                  <pre>{this.state.errorInfo.componentStack}</pre>
                </details>
              )}
            </div>

            <div className="error-boundary-actions">
              <button
                className="btn-auto-fix"
                onClick={this.handleAutoFix}
                disabled={this.state.isFixing}
              >
                {this.state.isFixing ? '🤖 AI is fixing...' : '🤖 Auto-Fix with AI'}
              </button>

              <button
                className="btn-reload"
                onClick={() => window.location.reload()}
                disabled={this.state.isFixing}
              >
                🔄 Reload Page
              </button>

              <button
                className="btn-dismiss"
                onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
                disabled={this.state.isFixing}
              >
                ✕ Dismiss
              </button>
            </div>

            {this.state.fixStatus && (
              <div className={`fix-status ${this.state.isFixing ? 'fixing' : ''}`}>
                {this.state.fixStatus}
                {this.state.fixAttempts > 1 && (
                  <span className="fix-attempts"> (Attempt {this.state.fixAttempts})</span>
                )}
              </div>
            )}

            {this.state.screenshot && (
              <details className="error-screenshot">
                <summary>Screenshot Captured</summary>
                <img src={this.state.screenshot} alt="Error screenshot" />
              </details>
            )}

            {this.state.aiAnalysis && (
              <div className="ai-analysis-results">
                <h3>🤖 AI Analysis Results</h3>

                <div className="analysis-section">
                  <div className="analysis-badge">
                    Confidence: <strong>{this.state.confidence}</strong>
                  </div>
                </div>

                {this.state.aiAnalysis.root_cause && (
                  <div className="analysis-section">
                    <h4>🔍 Root Cause</h4>
                    <p>{this.state.aiAnalysis.root_cause}</p>
                  </div>
                )}

                {this.state.fixStrategy && (
                  <div className="analysis-section">
                    <h4>💡 Fix Strategy</h4>
                    <p>{this.state.fixStrategy}</p>
                  </div>
                )}

                {this.state.filesAffected && this.state.filesAffected.length > 0 && (
                  <div className="analysis-section">
                    <h4>📁 Files Affected</h4>
                    <ul>
                      {this.state.filesAffected.map((file, index) => (
                        <li key={index}><code>{file}</code></li>
                      ))}
                    </ul>
                  </div>
                )}

                {this.state.fixRecommendation && (
                  <div className="analysis-section recommendation">
                    <h4>⚠️ Recommendation</h4>
                    <p>{this.state.fixRecommendation}</p>
                  </div>
                )}

                <div className="analysis-section">
                  <small style={{ color: '#666' }}>
                    💡 Tip: Share this analysis with your development team to quickly resolve the issue.
                  </small>
                </div>
              </div>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
