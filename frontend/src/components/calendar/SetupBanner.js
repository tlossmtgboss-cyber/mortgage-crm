import React from 'react';
import { Link } from 'react-router-dom';

/**
 * SetupBanner -- Dismissible call-to-action banner prompting new users to complete calendar setup.
 *
 * Links to /calendar/setup and can be dismissed. Renders with a teal gradient background.
 *
 * Used in: Calendar (main page, shown when setup is incomplete)
 *
 * @param {Object} props
 * @param {Function} props.onDismiss - Callback() invoked when the user clicks "Dismiss"
 * @returns {React.ReactElement}
 *
 * @example
 * <SetupBanner onDismiss={() => setShowBanner(false)} />
 */
const SetupBanner = React.memo(function SetupBanner({ onDismiss }) {
  return (
    <div
      className="calendar-setup-banner"
      role="status"
      style={{
        background: 'linear-gradient(135deg, #1F3D2E 0%, #1a7575 100%)',
        color: '#fff',
        padding: '12px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderRadius: '8px',
        margin: '0 0 16px 0',
        boxShadow: '0 2px 8px rgba(33, 141, 141, 0.25)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
        <span style={{ fontWeight: 500 }}>
          Welcome to Smart Calendar! Complete your setup to get started.
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        <Link
          to="/calendar/setup"
          style={{
            background: '#fff',
            color: '#1F3D2E',
            padding: '6px 16px',
            borderRadius: '6px',
            fontWeight: 600,
            fontSize: '13px',
            textDecoration: 'none',
            border: 'none',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Start Setup
        </Link>
        <button
          onClick={onDismiss}
          style={{
            background: 'rgba(255, 255, 255, 0.2)',
            color: '#fff',
            padding: '6px 12px',
            borderRadius: '6px',
            fontWeight: 500,
            fontSize: '13px',
            border: 'none',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
          aria-label="Dismiss setup banner"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
});

export default SetupBanner;
