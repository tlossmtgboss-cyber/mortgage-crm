/**
 * MobileNotificationCenter
 *
 * Full-page notification list for the Perennia AI mobile app.
 * Features: filter tabs, date grouping, swipe-to-dismiss / swipe-to-toggle-read,
 * pull-to-refresh, skeleton loading, and empty state.
 *
 * Route: /aria/notifications  (linked from MobileBottomNav)
 */

import React, { useState, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { haptics } from '../services/nativeServices';
import useNotifications from '../hooks/useNotifications';
import './MobileNotificationCenter.css';

// ============================================================================
// Constants
// ============================================================================

const FILTER_TABS = [
  { key: 'all', label: 'All' },
  { key: 'urgent', label: 'Urgent' },
  { key: 'loan', label: 'Loans' },
  { key: 'lead', label: 'Leads' },
  { key: 'task', label: 'Tasks' },
  { key: 'system', label: 'System' },
];

const SWIPE_THRESHOLD = 70; // px to trigger action

// ============================================================================
// Time formatting
// ============================================================================

function formatRelativeTime(dateString) {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 172800) return 'Yesterday';
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getDateGroup(dateString) {
  if (!dateString) return 'Older';
  const date = new Date(dateString);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const weekStart = new Date(todayStart);
  weekStart.setDate(weekStart.getDate() - 7);

  if (date >= todayStart) return 'Today';
  if (date >= yesterdayStart) return 'Yesterday';
  if (date >= weekStart) return 'This Week';
  return 'Older';
}

// ============================================================================
// Notification type helpers
// ============================================================================

function getNotificationType(notification) {
  const type = (notification.type || notification.category || '').toLowerCase();
  if (type.includes('loan') || type.includes('pipeline') || type.includes('closing') || type.includes('underwriting')) return 'loan';
  if (type.includes('lead') || type.includes('contact') || type.includes('referral')) return 'lead';
  if (type.includes('task') || type.includes('milestone') || type.includes('deadline') || type.includes('reminder')) return 'task';
  if (type.includes('alert') || type.includes('urgent') || type.includes('compliance') || type.includes('sla')) return 'alert';
  return 'system';
}

function isUrgent(notification) {
  const type = (notification.type || '').toLowerCase();
  const priority = (notification.priority || '').toLowerCase();
  return priority === 'urgent' || priority === 'high' || type.includes('urgent') || type.includes('sla') || type.includes('compliance');
}

function getNavigationTarget(notification) {
  // Use the link field from the backend if present
  if (notification.link) return notification.link;

  // Infer from type + entity IDs
  const type = getNotificationType(notification);
  if (type === 'loan' && notification.loan_id) return `/loans/${notification.loan_id}`;
  if (type === 'lead' && notification.lead_id) return `/leads/${notification.lead_id}`;
  if (type === 'task') return '/tasks';
  return null;
}

// ============================================================================
// SVG Icons
// ============================================================================

function BackIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function TypeIcon({ type }) {
  switch (type) {
    case 'loan':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M2 10h20" />
        </svg>
      );
    case 'lead':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case 'task':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 11 12 14 22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      );
    case 'alert':
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      );
    default: // system
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
  }
}

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

// ============================================================================
// Skeleton loader
// ============================================================================

function SkeletonList({ count = 8 }) {
  return Array.from({ length: count }, (_, i) => (
    <div className="mnc-skeleton-item" key={i}>
      <div className="mnc-skeleton-icon" />
      <div className="mnc-skeleton-lines">
        <div className="mnc-skeleton-line medium" />
        <div className="mnc-skeleton-line short" />
        <div className="mnc-skeleton-line tiny" />
      </div>
    </div>
  ));
}

// ============================================================================
// Swipeable notification item
// ============================================================================

function NotificationItem({ notification, onTap, onDismiss, onToggleRead }) {
  const itemRef = useRef(null);
  const touchStartX = useRef(0);
  const touchCurrentX = useRef(0);
  const isSwiping = useRef(false);
  const [offset, setOffset] = useState(0);
  const [dismissing, setDismissing] = useState(false);

  const nType = getNotificationType(notification);

  const handleTouchStart = useCallback((e) => {
    touchStartX.current = e.touches[0].clientX;
    touchCurrentX.current = e.touches[0].clientX;
    isSwiping.current = false;
  }, []);

  const handleTouchMove = useCallback((e) => {
    const deltaX = e.touches[0].clientX - touchStartX.current;
    touchCurrentX.current = e.touches[0].clientX;

    // Start swiping after 10px horizontal move
    if (Math.abs(deltaX) > 10) {
      isSwiping.current = true;
    }

    if (isSwiping.current) {
      // Allow swiping left (negative) and right (positive) but cap it
      const capped = Math.max(-120, Math.min(120, deltaX));
      setOffset(capped);
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (!isSwiping.current) {
      // It was a tap, not a swipe
      return;
    }

    if (offset < -SWIPE_THRESHOLD) {
      // Swiped left -> dismiss
      setDismissing(true);
      haptics.medium().catch(() => {});
      setTimeout(() => onDismiss(notification.id), 300);
    } else if (offset > SWIPE_THRESHOLD) {
      // Swiped right -> toggle read
      haptics.light().catch(() => {});
      onToggleRead(notification.id, notification.is_read);
      setOffset(0);
    } else {
      setOffset(0);
    }

    isSwiping.current = false;
  }, [offset, notification.id, notification.is_read, onDismiss, onToggleRead]);

  const handleClick = useCallback(() => {
    // Only navigate if not swiping
    if (!isSwiping.current) {
      onTap(notification);
    }
  }, [notification, onTap]);

  return (
    <div className="mnc-swipe-container">
      {/* Left swipe background (dismiss) */}
      {offset < 0 && (
        <div className="mnc-swipe-action left">Dismiss</div>
      )}
      {/* Right swipe background (mark read/unread) */}
      {offset > 0 && (
        <div className="mnc-swipe-action right">
          {notification.is_read ? 'Mark Unread' : 'Mark Read'}
        </div>
      )}
      <div
        ref={itemRef}
        className={`mnc-item${notification.is_read ? '' : ' unread'}${isSwiping.current ? ' swiping' : ''}${dismissing ? ' dismissed' : ''}`}
        style={{ transform: `translateX(${offset}px)` }}
        onClick={handleClick}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {!notification.is_read && <div className="mnc-unread-dot" />}
        <div className={`mnc-icon ${nType}`}>
          <TypeIcon type={nType} />
        </div>
        <div className="mnc-content">
          <p className="mnc-item-title">{notification.title || 'Notification'}</p>
          {notification.message && (
            <p className="mnc-item-desc">{notification.message}</p>
          )}
          <span className="mnc-item-time">{formatRelativeTime(notification.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main component
// ============================================================================

export default function MobileNotificationCenter() {
  const navigate = useNavigate();
  const [activeFilter, setActiveFilter] = useState('all');
  const listRef = useRef(null);

  // Pull-to-refresh state
  const [pullRefreshing, setPullRefreshing] = useState(false);
  const pullStartY = useRef(0);
  const isPulling = useRef(false);

  const {
    notifications,
    unreadCount,
    isLoading,
    isFetching,
    isError,
    markAsRead,
    markAllRead,
    dismiss,
    refetch,
  } = useNotifications();

  // ------------------------------------------------------------------
  // Filter notifications by active tab
  // ------------------------------------------------------------------
  const filteredNotifications = useMemo(() => {
    if (activeFilter === 'all') return notifications;
    if (activeFilter === 'urgent') return notifications.filter(isUrgent);
    return notifications.filter((n) => getNotificationType(n) === activeFilter);
  }, [notifications, activeFilter]);

  // ------------------------------------------------------------------
  // Group by date
  // ------------------------------------------------------------------
  const groupedNotifications = useMemo(() => {
    const groups = {};
    const order = ['Today', 'Yesterday', 'This Week', 'Older'];

    for (const n of filteredNotifications) {
      const group = getDateGroup(n.created_at);
      if (!groups[group]) groups[group] = [];
      groups[group].push(n);
    }

    return order
      .filter((g) => groups[g]?.length > 0)
      .map((g) => ({ label: g, items: groups[g] }));
  }, [filteredNotifications]);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------
  const handleBack = useCallback(() => {
    navigate(-1);
  }, [navigate]);

  const handleTap = useCallback(
    (notification) => {
      if (!notification.is_read) {
        markAsRead(notification.id);
      }
      const target = getNavigationTarget(notification);
      if (target) {
        navigate(target);
      }
    },
    [navigate, markAsRead],
  );

  const handleToggleRead = useCallback(
    (id, currentlyRead) => {
      if (!currentlyRead) {
        markAsRead(id);
      }
      // Note: if the backend supports un-reading, we could call a separate mutation here.
      // For now, swipe right only marks as read.
    },
    [markAsRead],
  );

  const handleDismiss = useCallback(
    (id) => {
      dismiss(id);
    },
    [dismiss],
  );

  // ------------------------------------------------------------------
  // Pull-to-refresh (simple scroll-top detection)
  // ------------------------------------------------------------------
  const handleListTouchStart = useCallback((e) => {
    if (listRef.current && listRef.current.scrollTop <= 0) {
      pullStartY.current = e.touches[0].clientY;
      isPulling.current = true;
    }
  }, []);

  const handleListTouchMove = useCallback(() => {
    // Intentionally minimal -- the actual refresh fires on touchEnd
  }, []);

  const handleListTouchEnd = useCallback(
    (e) => {
      if (!isPulling.current) return;
      isPulling.current = false;

      const endY = e.changedTouches?.[0]?.clientY ?? 0;
      const delta = endY - pullStartY.current;

      if (delta > 80 && listRef.current && listRef.current.scrollTop <= 0) {
        setPullRefreshing(true);
        haptics.light().catch(() => {});
        refetch().finally(() => {
          setTimeout(() => setPullRefreshing(false), 400);
        });
      }
    },
    [refetch],
  );

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="mnc">
      {/* Header */}
      <header className="mnc-header">
        <div className="mnc-header-left">
          <button className="mnc-back-btn" onClick={handleBack} aria-label="Back">
            <BackIcon />
          </button>
          <h1 className="mnc-title">
            Notifications
            {unreadCount > 0 && (
              <span className="mnc-unread-badge">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </h1>
        </div>
        {unreadCount > 0 && (
          <button
            className="mnc-mark-all-btn"
            onClick={markAllRead}
            disabled={isFetching}
          >
            Mark all read
          </button>
        )}
      </header>

      {/* Filter tabs */}
      <div className="mnc-filters">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`mnc-filter-tab${activeFilter === tab.key ? ' active' : ''}`}
            onClick={() => {
              setActiveFilter(tab.key);
              haptics.selection().catch(() => {});
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* List area */}
      <div
        ref={listRef}
        className="mnc-list-wrapper"
        onTouchStart={handleListTouchStart}
        onTouchMove={handleListTouchMove}
        onTouchEnd={handleListTouchEnd}
      >
        {/* Pull-to-refresh indicator */}
        {pullRefreshing && (
          <div className="mnc-pull-indicator">
            <div className="mnc-pull-spinner" />
            Refreshing...
          </div>
        )}

        {/* Loading state */}
        {isLoading && <SkeletonList />}

        {/* Error state */}
        {!isLoading && isError && (
          <div className="mnc-error">
            <p className="mnc-error-text">Could not load notifications</p>
            <button className="mnc-retry-btn" onClick={() => refetch()}>
              Try Again
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && filteredNotifications.length === 0 && (
          <div className="mnc-empty">
            <div className="mnc-empty-icon">
              <BellIcon />
            </div>
            <p className="mnc-empty-title">You're all caught up!</p>
            <p className="mnc-empty-subtitle">
              {activeFilter !== 'all'
                ? `No ${activeFilter} notifications right now.`
                : 'No new notifications.'}
            </p>
          </div>
        )}

        {/* Grouped notification items */}
        {!isLoading &&
          !isError &&
          groupedNotifications.map((group) => (
            <React.Fragment key={group.label}>
              <div className="mnc-date-group">{group.label}</div>
              {group.items.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onTap={handleTap}
                  onDismiss={handleDismiss}
                  onToggleRead={handleToggleRead}
                />
              ))}
            </React.Fragment>
          ))}
      </div>
    </div>
  );
}
