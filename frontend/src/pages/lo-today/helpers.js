import React from 'react';

// =============================================================================
// Helpers
// =============================================================================

export function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

export function formatTime(isoString) {
  if (!isoString) return '';
  return new Date(isoString).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

export function formatFullDate(date) {
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

export function daysBetween(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now - d;
  return Math.floor(diffMs / (1000 * 60 * 60 * 24));
}

export function isToday(isoString) {
  if (!isoString) return false;
  const d = new Date(isoString);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function isPast(isoString) {
  if (!isoString) return false;
  return new Date(isoString) < new Date();
}

export function getUserName() {
  try {
    const userData = localStorage.getItem('user');
    if (userData) {
      const user = JSON.parse(userData);
      return user.first_name || user.name || '';
    }
  } catch (e) {
    // ignore
  }
  return '';
}

// Meeting mode icon text
export function getModeLabel(mode) {
  switch (mode) {
    case 'video':
      return 'Video';
    case 'phone':
      return 'Phone';
    case 'in_person':
    case 'in-person':
      return 'In Person';
    default:
      return mode || 'Meeting';
  }
}

// =============================================================================
// Constants
// =============================================================================

// SLA targets in days for each stage (mirrors backend SLA_TARGETS)
export const SLA_TARGETS_BY_STAGE = {
  APPLICATION: 3,
  DISCLOSED: 7,
  PROCESSING: 7,
  SUBMITTED: 2,
  UNDERWRITING: 5,
  UW_RECEIVED: 5,
  CONDITIONAL_APPROVAL: 3,
  APPROVED: 3,
  CLEAR_TO_CLOSE: 3,
  CTC: 3,
  DOCS: 5,
  DOCS_OUT: 5,
  CLOSING: 5,
};

export const ACTIVE_STAGES = Object.keys(SLA_TARGETS_BY_STAGE);

// =============================================================================
// Section Error Boundary
// =============================================================================

export class SectionErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error(`LOTodayView section error [${this.props.sectionName}]:`, error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="lo-today__error">
          <p>This section encountered an error.</p>
          <button
            className="lo-today__retry-btn"
            onClick={() => this.setState({ hasError: false })}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// =============================================================================
// Loading Skeleton
// =============================================================================

export function LoadingSkeleton({ rows = 4 }) {
  return (
    <div className="lo-today__skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="lo-today__skeleton-row" />
      ))}
    </div>
  );
}
