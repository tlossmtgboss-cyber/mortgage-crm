import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Capacitor } from '@capacitor/core';
import { haptics } from '../../services/nativeServices';
import { OfflineSyncStatus } from './OfflineSyncStatus';
import './MobileBottomNav.css';

// ============================================================================
// Tab configuration
// ============================================================================

const TABS = [
  {
    key: 'home',
    path: '/mobile-home',
    label: 'Home',
    matchPaths: ['/mobile-home', '/dashboard'],
  },
  {
    key: 'pipeline',
    path: '/mobile/pipeline',
    label: 'Pipeline',
    matchPaths: ['/mobile/pipeline', '/loans'],
    badgeKey: 'pipeline',
  },
  {
    key: 'aria',
    path: '/mobile-aria',
    label: 'Aria',
    isCenter: true,
    matchPaths: ['/mobile-aria'],
  },
  {
    key: 'contacts',
    path: '/mobile/leads',
    label: 'Contacts',
    matchPaths: ['/mobile/leads', '/leads'],
    badgeKey: 'contacts',
  },
  {
    key: 'more',
    path: null,
    label: 'More',
    isMore: true,
  },
];

// Speed dial actions for the FAB
const SPEED_DIAL_ACTIONS = [
  {
    key: 'add-lead',
    label: 'Add Lead',
    path: '/leads?action=new',
    color: '#2D7A52',
  },
  {
    key: 'upload-doc',
    label: 'Upload Doc',
    path: '/smart-docs?action=upload',
    color: '#B8924A',
  },
  {
    key: 'make-call',
    label: 'Make Call',
    path: '/dialer',
    color: '#f59e0b',
  },
  {
    key: 'new-task',
    label: 'New Task',
    path: '/tasks?action=new',
    color: '#ef4444',
  },
  {
    key: 'notifications',
    label: 'Notifications',
    path: '/aria/notifications',
    color: '#B8924A',
  },
];

// ============================================================================
// SVG Icons — inline, no library dependency
// ============================================================================

function HomeIcon({ active }) {
  if (active) {
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="#1F3D2E" stroke="none">
        <path d="M12 2.1L1 12h3v9h6v-6h4v6h6v-9h3L12 2.1z" />
      </svg>
    );
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function PipelineIcon({ active }) {
  if (active) {
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="#1F3D2E" stroke="none">
        <path d="M3 4h18v2H3V4zm2 5h14v2H5V9zm3 5h8v2H8v-2zm2 5h4v2h-4v-2z" />
      </svg>
    );
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 4h18v2H3V4zm2 5h14v2H5V9zm3 5h8v2H8v-2zm2 5h4v2h-4v-2z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </svg>
  );
}

function AriaSparkleIcon({ active }) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {/* Large center star */}
      <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" fill="#fff" stroke="none" />
      {/* Small top-right sparkle */}
      <path d="M18 3 L18.6 5.4 L21 6 L18.6 6.6 L18 9 L17.4 6.6 L15 6 L17.4 5.4 Z" fill="#fff" stroke="none" opacity="0.85" />
      {/* Tiny bottom-left sparkle */}
      <path d="M5 17 L5.4 18.6 L7 19 L5.4 19.4 L5 21 L4.6 19.4 L3 19 L4.6 18.6 Z" fill="#fff" stroke="none" opacity="0.7" />
    </svg>
  );
}

function ContactsIcon({ active }) {
  if (active) {
    return (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="#1F3D2E" stroke="none">
        <circle cx="9" cy="7" r="4" />
        <path d="M17 21v-2c0-2.21-3.58-4-8-4s-8 1.79-8 4v2h16z" />
        <circle cx="19" cy="7" r="3" />
        <path d="M24 21v-1.5c0-1.5-2-2.7-4.5-3.2" />
      </svg>
    );
  }
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function MoreIcon({ active }) {
  const color = active ? '#1F3D2E' : '#6b7280';
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill={color} stroke="none">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

// Speed dial action icons
function AddLeadIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="8.5" cy="7" r="4" />
      <line x1="20" y1="8" x2="20" y2="14" />
      <line x1="17" y1="11" x2="23" y2="11" />
    </svg>
  );
}

function UploadDocIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="12" y1="18" x2="12" y2="12" />
      <line x1="9" y1="15" x2="12" y2="12" />
      <line x1="15" y1="15" x2="12" y2="12" />
    </svg>
  );
}

function MakeCallIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

function NewTaskIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 11 12 14 22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  );
}

function NotificationsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

const SPEED_DIAL_ICONS = {
  'add-lead': AddLeadIcon,
  'upload-doc': UploadDocIcon,
  'make-call': MakeCallIcon,
  'new-task': NewTaskIcon,
  'notifications': NotificationsIcon,
};

// ============================================================================
// Scroll direction hook
// ============================================================================

function useScrollDirection(threshold = 10) {
  const [hidden, setHidden] = useState(false);
  const lastScrollY = useRef(0);
  const ticking = useRef(false);

  useEffect(() => {
    const onScroll = () => {
      if (ticking.current) return;
      ticking.current = true;

      window.requestAnimationFrame(() => {
        const currentY = window.scrollY;
        const diff = currentY - lastScrollY.current;

        if (Math.abs(diff) > threshold) {
          setHidden(diff > 0 && currentY > 56);
        }

        lastScrollY.current = currentY;
        ticking.current = false;
      });
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [threshold]);

  return hidden;
}

// ============================================================================
// Component
// ============================================================================

export default function MobileBottomNav({
  badges = {},
  onMorePress,
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [fabOpen, setFabOpen] = useState(false);
  const hidden = useScrollDirection(10);
  const overlayRef = useRef(null);
  const longPressTimer = useRef(null);
  const isNative = Capacitor.isNativePlatform();

  // Close speed dial on route change
  useEffect(() => {
    setFabOpen(false);
  }, [location.pathname]);

  // Close speed dial on outside tap
  const handleOverlayTap = useCallback(() => {
    haptics.light();
    setFabOpen(false);
  }, []);

  // Only render on native platforms — after all hooks
  if (!isNative) return null;

  // ---- Active tab detection ----
  const isTabActive = (tab) => {
    if (tab.key === 'more') return false;
    if (tab.matchPaths) {
      return tab.matchPaths.some((p) =>
        location.pathname === p || location.pathname.startsWith(p + '/')
      );
    }
    return location.pathname === tab.path;
  };

  // ---- Long-press handlers for Aria center button (opens speed dial) ----
  const handleAriaPointerDown = useCallback(() => {
    longPressTimer.current = setTimeout(() => {
      haptics.medium();
      setFabOpen(true);
    }, 500);
  }, []);

  const handleAriaPointerUp = useCallback(() => {
    clearTimeout(longPressTimer.current);
  }, []);

  // ---- Handlers ----
  const handleTabPress = (tab) => {
    haptics.light();

    if (tab.key === 'aria') {
      // Short tap: navigate to Aria chat
      if (!fabOpen) {
        setFabOpen(false);
        navigate('/mobile-aria');
      } else {
        setFabOpen(false);
      }
      return;
    }

    if (tab.key === 'more') {
      if (onMorePress) onMorePress();
      else navigate('/settings');
      return;
    }

    if (tab.path && location.pathname !== tab.path) {
      setFabOpen(false);
      navigate(tab.path);
    }
  };

  const handleSpeedDialAction = (action) => {
    haptics.medium();
    setFabOpen(false);
    navigate(action.path);
  };

  // ---- Render helpers ----
  const renderIcon = (tab, active) => {
    switch (tab.key) {
      case 'home':
        return <HomeIcon active={active} />;
      case 'pipeline':
        return <PipelineIcon active={active} />;
      case 'aria':
        return <AriaSparkleIcon active={active} />;
      case 'contacts':
        return <ContactsIcon active={active} />;
      case 'more':
        return <MoreIcon active={active} />;
      default:
        return null;
    }
  };

  const renderBadge = (tab) => {
    if (!tab.badgeKey) return null;
    const count = badges[tab.badgeKey];
    if (!count) return null;
    return (
      <span className="mbn-badge" aria-label={`${count} notifications`}>
        {count > 99 ? '99+' : count}
      </span>
    );
  };

  return (
    <>
      {/* Offline sync queue status — sits above bottom nav */}
      <OfflineSyncStatus />

      {/* Speed dial overlay */}
      {fabOpen && (
        <div
          ref={overlayRef}
          className="mbn-overlay"
          onClick={handleOverlayTap}
          aria-hidden="true"
        />
      )}

      {/* Speed dial actions */}
      <div className={`mbn-speed-dial ${fabOpen ? 'mbn-speed-dial--open' : ''}`} aria-label="Quick actions">
        {SPEED_DIAL_ACTIONS.map((action, index) => {
          const Icon = SPEED_DIAL_ICONS[action.key];
          return (
            <button
              key={action.key}
              className="mbn-speed-dial__action"
              style={{
                '--dial-index': index,
                '--dial-color': action.color,
              }}
              onClick={() => handleSpeedDialAction(action)}
              aria-label={action.label}
            >
              <span className="mbn-speed-dial__action-circle">
                <Icon />
              </span>
              <span className="mbn-speed-dial__action-label">{action.label}</span>
            </button>
          );
        })}
      </div>

      {/* Bottom nav bar */}
      <nav
        className={`mbn ${hidden && !fabOpen ? 'mbn--hidden' : ''}`}
        role="tablist"
        aria-label="Main navigation"
      >
        {TABS.map((tab) => {
          const active = isTabActive(tab);

          // Aria center button (replaces FAB)
          if (tab.isCenter) {
            return (
              <button
                key="aria"
                className="mbn__tab mbn__fab"
                onClick={() => handleTabPress(tab)}
                onPointerDown={handleAriaPointerDown}
                onPointerUp={handleAriaPointerUp}
                onPointerLeave={handleAriaPointerUp}
                aria-label={fabOpen ? 'Close quick actions' : 'Ask Aria'}
                aria-expanded={fabOpen}
              >
                <div className={`mbn__fab-circle mbn__fab-circle--aria ${fabOpen ? 'mbn__fab-circle--open' : ''}`}>
                  {fabOpen ? <CloseIcon /> : <AriaSparkleIcon />}
                </div>
              </button>
            );
          }

          // Regular tab
          return (
            <button
              key={tab.key}
              className={`mbn__tab ${active ? 'mbn__tab--active' : ''}`}
              onClick={() => handleTabPress(tab)}
              role="tab"
              aria-selected={active}
              aria-label={tab.label}
            >
              <span className="mbn__tab-icon">
                {renderIcon(tab, active)}
                {renderBadge(tab)}
              </span>
              {active && <span className="mbn__tab-label">{tab.label}</span>}
            </button>
          );
        })}
      </nav>
    </>
  );
}
