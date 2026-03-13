import { useState, useEffect, useCallback, useRef } from 'react';
import { schedulerAPI } from '../services/api';

const STORAGE_KEY = 'perennia_calendar_notifications_read';
const POLL_INTERVAL_MS = 60_000; // 60 seconds

/**
 * Load read notification IDs from localStorage.
 */
function loadReadIds() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw));
  } catch {
    return new Set();
  }
}

/**
 * Persist read notification IDs to localStorage.
 */
function saveReadIds(readSet) {
  try {
    // Keep only the most recent 500 IDs to avoid unbounded growth
    const ids = Array.from(readSet).slice(-500);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // localStorage may be full or unavailable; silently ignore
  }
}

/**
 * Format a relative timestamp (e.g., "5 min ago", "2 hours ago").
 */
export function formatRelativeTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60_000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs} hour${diffHrs !== 1 ? 's' : ''} ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Request browser notification permission if not yet decided.
 * Returns the permission state.
 */
async function requestBrowserNotificationPermission() {
  if (!('Notification' in window)) return 'denied';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  try {
    const result = await Notification.requestPermission();
    return result;
  } catch {
    return 'denied';
  }
}

/**
 * Show a browser notification for urgent/critical items.
 */
function showBrowserNotification(notification) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    const n = new Notification(notification.title, {
      body: notification.description || '',
      icon: '/favicon.ico',
      tag: `calendar-notif-${notification.id}`,
      requireInteraction: false,
    });
    // Auto-close after 8 seconds
    setTimeout(() => n.close(), 8_000);
  } catch {
    // Browser may block notification creation in some contexts
  }
}

/**
 * useCalendarNotifications - Hook for calendar notification state and polling.
 *
 * Returns:
 *   notifications   - Array of notification objects with `isRead` flag
 *   unreadCount     - Number of unread notifications
 *   markAsRead      - Function(id) to mark a single notification as read
 *   markAllRead     - Function() to mark all current notifications as read
 *   loading         - Boolean indicating first load
 *   error           - Error string or null
 */
export default function useCalendarNotifications() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const readIdsRef = useRef(loadReadIds());
  const knownIdsRef = useRef(new Set());
  const permissionRequestedRef = useRef(false);

  // Fetch notifications from the API
  const fetchNotifications = useCallback(async (isInitial = false) => {
    try {
      const data = await schedulerAPI.getNotifications();
      const items = data.notifications || [];
      const readIds = readIdsRef.current;

      // Detect truly new notifications (not seen in previous poll)
      if (!isInitial) {
        for (const item of items) {
          if (!knownIdsRef.current.has(item.id) && !readIds.has(item.id)) {
            // Show browser notification for new booking or cancellation
            if (item.type === 'booking' || item.type === 'cancellation') {
              showBrowserNotification(item);
            }
          }
        }
      }

      // Update known IDs
      knownIdsRef.current = new Set(items.map(n => n.id));

      // Merge read state from localStorage
      const merged = items.map(n => ({
        ...n,
        isRead: readIds.has(n.id),
      }));

      setNotifications(merged);
      setError(null);
    } catch (err) {
      // Only set error on initial load; subsequent poll failures are silent
      if (isInitial) {
        setError('Unable to load notifications');
      }
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  }, []);

  // Initial fetch + polling
  useEffect(() => {
    fetchNotifications(true);

    const interval = setInterval(() => {
      fetchNotifications(false);
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Request browser notification permission on first render
  useEffect(() => {
    if (!permissionRequestedRef.current) {
      permissionRequestedRef.current = true;
      requestBrowserNotificationPermission();
    }
  }, []);

  // Mark a single notification as read
  const markAsRead = useCallback((id) => {
    readIdsRef.current.add(id);
    saveReadIds(readIdsRef.current);

    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, isRead: true } : n)
    );

    // Fire-and-forget to persist on server
    schedulerAPI.markNotificationRead(id).catch(() => {});
  }, []);

  // Mark all notifications as read
  const markAllRead = useCallback(() => {
    setNotifications(prev => {
      for (const n of prev) {
        readIdsRef.current.add(n.id);
      }
      saveReadIds(readIdsRef.current);
      return prev.map(n => ({ ...n, isRead: true }));
    });

    // Fire-and-forget to persist on server
    schedulerAPI.markAllNotificationsRead().catch(() => {});
  }, []);

  const unreadCount = notifications.filter(n => !n.isRead).length;

  return {
    notifications,
    unreadCount,
    markAsRead,
    markAllRead,
    loading,
    error,
  };
}
