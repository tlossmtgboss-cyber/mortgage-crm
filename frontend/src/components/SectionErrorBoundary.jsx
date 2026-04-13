import React from 'react';

/**
 * SectionErrorBoundary -- Lightweight error boundary for individual page sections.
 *
 * Isolates crashes to a single UI section so the rest of the page stays functional.
 * Shows an inline error message with a "Try Again" button.
 *
 * Props:
 *   - sectionName  (string)   Human-readable name for error messages (default: "This section")
 *   - onError      (function) Optional callback(error, errorInfo)
 *   - children     (ReactNode)
 *
 * @example
 * <SectionErrorBoundary sectionName="Pipeline Chart">
 *   <PipelineChart />
 * </SectionErrorBoundary>
 */
class SectionErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    const name = this.props.sectionName || 'Section';
    console.error(`[SectionErrorBoundary:${name}]`, error, errorInfo);

    if (typeof this.props.onError === 'function') {
      try {
        this.props.onError(error, errorInfo);
      } catch {
        // Prevent callback errors from cascading
      }
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const label = this.props.sectionName || 'This section';

      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '16px',
            background: 'var(--color-bg-secondary, rgba(139, 92, 68, 0.05))',
            border: '1px solid var(--color-border, rgba(139, 92, 68, 0.15))',
            borderRadius: 'var(--radius-base, 8px)',
            color: 'var(--color-text-secondary, #666)',
            fontSize: 'var(--font-sm, 13px)',
            lineHeight: '1.5',
          }}
        >
          {/* Warning icon */}
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--color-error, #C0152F)"
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

          <span style={{ flex: 1 }}>
            {label} encountered an error.
          </span>

          <button
            onClick={this.handleReset}
            type="button"
            style={{
              padding: '6px 14px',
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--color-primary, #218d8d)',
              background: 'var(--color-bg-surface, #fff)',
              border: '1px solid var(--color-border, rgba(139, 92, 68, 0.15))',
              borderRadius: 'var(--radius-sm, 6px)',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default SectionErrorBoundary;
