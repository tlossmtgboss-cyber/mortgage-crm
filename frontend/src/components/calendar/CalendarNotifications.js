import React, { useRef, useEffect, useCallback } from 'react';
import NotificationBadge from './NotificationBadge';
import { formatRelativeTime } from '../../hooks/useCalendarNotifications';

/**
 * NOTIFICATION_TYPE_CONFIG - Icon and styling config per notification type.
 */
const NOTIFICATION_TYPE_CONFIG = {
  booking: {
    icon: '\u{1F4C5}',  // calendar emoji
    iconClass: 'notification-icon-booking',
    defaultTitle: 'New booking',
  },
  cancellation: {
    icon: '\u{274C}',   // cross mark
    iconClass: 'notification-icon-cancellation',
    defaultTitle: 'Cancellation',
  },
  reminder: {
    icon: '\u{23F0}',   // alarm clock
    iconClass: 'notification-icon-reminder',
    defaultTitle: 'Upcoming appointment',
  },
  reschedule: {
    icon: '\u{1F504}',  // arrows circle
    iconClass: 'notification-icon-reschedule',
    defaultTitle: 'Reschedule request',
  },
};

/**
 * CalendarNotifications - Bell icon button with dropdown notification panel.
 *
 * Props:
 *   notifications  - Array of notification objects
 *   unreadCount    - Number of unread notifications
 *   isOpen         - Whether the panel is currently open
 *   onToggle       - Callback to toggle panel open/closed
 *   onMarkAsRead   - Callback(id) to mark one notification as read
 *   onMarkAllRead  - Callback() to mark all as read
 *   onSelectNotification - Callback(notification) when a notification is clicked
 */
const CalendarNotifications = React.memo(function CalendarNotifications({
  notifications = [],
  unreadCount = 0,
  isOpen = false,
  onToggle,
  onMarkAsRead,
  onMarkAllRead,
  onSelectNotification,
}) {
  const panelRef = useRef(null);
  const buttonRef = useRef(null);

  // Close panel on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e) => {
      if (
        panelRef.current && !panelRef.current.contains(e.target) &&
        buttonRef.current && !buttonRef.current.contains(e.target)
      ) {
        onToggle();
      }
    };

    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onToggle();
        buttonRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onToggle]);

  const handleNotificationClick = useCallback((notification) => {
    if (!notification.isRead && onMarkAsRead) {
      onMarkAsRead(notification.id);
    }
    if (onSelectNotification) {
      onSelectNotification(notification);
    }
  }, [onMarkAsRead, onSelectNotification]);

  return (
    <div className="notification-panel-wrapper">
      {/* Bell button */}
      <button
        ref={buttonRef}
        className="btn-calendar-notifications"
        onClick={onToggle}
        aria-label={
          unreadCount > 0
            ? `Notifications, ${unreadCount} unread`
            : 'Notifications'
        }
        aria-expanded={isOpen}
        aria-haspopup="true"
        type="button"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        <NotificationBadge count={unreadCount} variant="count" />
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div
          ref={panelRef}
          className="notification-panel"
          role="dialog"
          aria-label="Notifications"
        >
          <div className="notification-panel-header">
            <h3>Notifications</h3>
            <button
              className="notification-mark-all-btn"
              onClick={onMarkAllRead}
              disabled={unreadCount === 0}
              type="button"
            >
              Mark all as read
            </button>
          </div>

          <div className="notification-list" role="list">
            {notifications.length === 0 ? (
              <div className="notification-empty">
                <div className="notification-empty-icon" aria-hidden="true">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                </div>
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map((notification) => {
                const config = NOTIFICATION_TYPE_CONFIG[notification.type] || NOTIFICATION_TYPE_CONFIG.booking;
                return (
                  <button
                    key={notification.id}
                    className={`notification-item${!notification.isRead ? ' notification-item-unread' : ''}`}
                    onClick={() => handleNotificationClick(notification)}
                    role="listitem"
                    type="button"
                    aria-label={`${notification.isRead ? '' : 'Unread: '}${notification.title || config.defaultTitle}`}
                  >
                    <div className={`notification-icon ${config.iconClass}`} aria-hidden="true">
                      {config.icon}
                    </div>
                    <div className="notification-content">
                      <p className="notification-title">
                        {notification.title || config.defaultTitle}
                      </p>
                      {notification.description && (
                        <p className="notification-description">
                          {notification.description}
                        </p>
                      )}
                      <span className="notification-timestamp">
                        {formatRelativeTime(notification.created_at)}
                      </span>
                    </div>
                    {notification.isRead ? (
                      <span className="notification-read-dot" />
                    ) : (
                      <span className="notification-unread-dot" aria-label="Unread" />
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default CalendarNotifications;
