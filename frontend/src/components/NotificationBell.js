import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { notificationsApi } from '../services/api';
import { onNotification as onPushNotification } from '../services/pushNotificationService';
import './NotificationBell.css';

const NotificationBell = () => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);

  const loadNotifications = useCallback(async () => {
    try {
      const response = await notificationsApi.getNotifications(false, 10);
      setNotifications(response.data.notifications || []);
      setUnreadCount(response.data.unread_count || 0);
    } catch (err) {
      console.error('Error loading notifications:', err);
    }
  }, []);

  useEffect(() => {
    loadNotifications();

    // Auto-refresh every 30 seconds
    const interval = setInterval(loadNotifications, 30000);

    // Click outside to close dropdown
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);

    // Listen for push notifications to refresh the list immediately
    const unsubscribePush = onPushNotification(() => {
      loadNotifications();
    });

    return () => {
      clearInterval(interval);
      document.removeEventListener('mousedown', handleClickOutside);
      unsubscribePush();
    };
  }, [loadNotifications]);

  const handleBellClick = () => {
    setShowDropdown(!showDropdown);
  };

  const handleNotificationClick = async (notification) => {
    // Mark as read
    if (!notification.is_read) {
      try {
        await notificationsApi.markAsRead(notification.id);
        // Update local state
        setNotifications(notifications.map(n =>
          n.id === notification.id ? { ...n, is_read: true } : n
        ));
        setUnreadCount(Math.max(0, unreadCount - 1));
      } catch (err) {
        console.error('Error marking notification as read:', err);
      }
    }

    // Navigate to link
    if (notification.link) {
      navigate(notification.link);
      setShowDropdown(false);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      setLoading(true);
      await notificationsApi.markAllAsRead();
      // Update all notifications to read
      setNotifications(notifications.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (err) {
      console.error('Error marking all as read:', err);
    } finally {
      setLoading(false);
    }
  };

  const getNotificationIcon = (type) => {
    const icons = {
      'LOAN_UPDATE': '📋',
      'LEAD_NEW': '👤',
      'TASK_DUE': '📅',
      'RATE_LOCK_EXPIRING': '🔒',
      'DOCUMENT_NEEDED': '📄',
      'CLOSING_REMINDER': '🏠',
      'COMPLIANCE_ALERT': '⚠️',
      'permission_approved': '✅',
      'permission_denied': '❌',
      'milestone_due': '📅',
      'assessment_reminder': '📊',
      'goal_reminder': '🎯',
      'feedback_added': '💬'
    };
    return icons[type] || '🔔';
  };

  const getTimeAgo = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="notification-bell-container" ref={dropdownRef}>
      <button
        className="notification-bell-button"
        onClick={handleBellClick}
        aria-label={unreadCount > 0 ? `${unreadCount} unread notifications` : 'Notifications'}
      >
        <svg
          className="bell-icon-svg"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      {showDropdown && (
        <div className="notification-dropdown">
          <div className="notification-dropdown-header">
            <h3>Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="mark-all-read-btn"
                disabled={loading}
              >
                {loading ? 'Marking...' : 'Mark all read'}
              </button>
            )}
          </div>

          <div className="notifications-list">
            {notifications.length === 0 ? (
              <div className="no-notifications">
                <span className="no-notifications-icon">📭</span>
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map(notification => (
                <div
                  key={notification.id}
                  className={`notification-item ${!notification.is_read ? 'unread' : ''}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="notification-icon">
                    {getNotificationIcon(notification.type)}
                  </div>
                  <div className="notification-content">
                    <div className="notification-title">{notification.title}</div>
                    <div className="notification-message">{notification.message}</div>
                    <div className="notification-time">{getTimeAgo(notification.created_at)}</div>
                  </div>
                  {!notification.is_read && <div className="unread-dot"></div>}
                </div>
              ))
            )}
          </div>

          {notifications.length > 0 && (
            <div className="notification-dropdown-footer">
              <button onClick={() => {
                navigate('/aria/notifications');
                setShowDropdown(false);
              }} className="view-all-btn">
                View all notifications
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
