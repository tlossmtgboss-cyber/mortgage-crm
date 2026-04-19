import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { haptics } from '../../services/nativeServices';
import './AriaTabNav.css';

// ============================================================================
// Tab configuration
// ============================================================================

const TABS = [
  {
    key: 'home',
    path: '/dashboard',
    label: 'Home',
  },
  {
    key: 'history',
    path: '/aria-history',
    label: 'History',
  },
  {
    key: 'calendar',
    path: '/mobile-calendar',
    label: 'Calendar',
  },
  {
    key: 'tasks',
    path: '/mobile-tasks',
    label: 'Tasks',
  },
  {
    key: 'profile',
    path: '/settings',
    label: 'Profile',
  },
];

// ============================================================================
// Inline SVG icons
// ============================================================================

const TabIcons = {
  home: (color) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10.5z" />
      <path d="M9 21V14h6v7" />
    </svg>
  ),
  history: (color) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15 15" />
      <path d="M3 12a9 9 0 0 1 9-9" />
    </svg>
  ),
  calendar: (color) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <circle cx="8" cy="14" r="1" fill={color} stroke="none" />
      <circle cx="12" cy="14" r="1" fill={color} stroke="none" />
      <circle cx="16" cy="14" r="1" fill={color} stroke="none" />
    </svg>
  ),
  tasks: (color) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="3" />
      <path d="M8 12l2.5 2.5L16 9" />
    </svg>
  ),
  profile: (color) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-1a6 6 0 0 1 12 0v1" />
      <circle cx="12" cy="12" r="10" />
    </svg>
  ),
};

// ============================================================================
// AriaTabNav component
// ============================================================================

export default function AriaTabNav({
  variant = 'dark',
  activeTab = 'home',
  showFab = false,
  onFabPress,
}) {
  const navigate = useNavigate();

  const handleTabPress = useCallback((tab) => {
    haptics.light();
    navigate(tab.path);
  }, [navigate]);

  const handleFabPress = useCallback(() => {
    haptics.medium();
    if (onFabPress) {
      onFabPress();
    }
  }, [onFabPress]);

  const getColor = (tabKey) => {
    if (tabKey === activeTab) {
      return variant === 'dark' ? '#7EB8F7' : '#1a73e8';
    }
    return variant === 'dark' ? 'rgba(255,255,255,0.3)' : '#999';
  };

  return (
    <nav className={`aria-tab-nav aria-tab-nav--${variant}`}>
      {TABS.map((tab, index) => (
        <React.Fragment key={tab.key}>
          {/* Insert FAB between calendar (index 1) and tasks (index 2) */}
          {showFab && index === 2 && (
            <button
              className="aria-tab-fab"
              onClick={handleFabPress}
              aria-label="Quick action"
              type="button"
            >
              <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                <line x1="11" y1="3" x2="11" y2="19" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
                <line x1="3" y1="11" x2="19" y2="11" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
            </button>
          )}
          <button
            className={`aria-tab-btn ${activeTab === tab.key ? 'aria-tab-btn--active' : ''}`}
            onClick={() => handleTabPress(tab)}
            aria-label={tab.label}
            aria-current={activeTab === tab.key ? 'page' : undefined}
            type="button"
          >
            {TabIcons[tab.key](getColor(tab.key))}
            <span
              className="aria-tab-label"
              style={{ color: getColor(tab.key) }}
            >
              {tab.label}
            </span>
          </button>
        </React.Fragment>
      ))}
    </nav>
  );
}
