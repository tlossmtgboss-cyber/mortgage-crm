import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGetNotifications = vi.fn();
const mockMarkNotificationRead = vi.fn();
const mockMarkAllNotificationsRead = vi.fn();

vi.mock('../../services/api', () => ({
  schedulerAPI: {
    getNotifications: (...args) => mockGetNotifications(...args),
    markNotificationRead: (...args) => mockMarkNotificationRead(...args),
    markAllNotificationsRead: (...args) => mockMarkAllNotificationsRead(...args),
  },
}));

// We need to import AFTER the mock is set up
import useCalendarNotifications, { formatRelativeTime } from '../useCalendarNotifications';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeNotification(overrides = {}) {
  return {
    id: 'notif-1',
    type: 'booking',
    title: 'New booking',
    description: 'Consultation at 3 PM',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests: formatRelativeTime
// ---------------------------------------------------------------------------

describe('formatRelativeTime', () => {
  it('returns empty string for null/undefined input', () => {
    expect(formatRelativeTime(null)).toBe('');
    expect(formatRelativeTime(undefined)).toBe('');
  });

  it('returns "Just now" for timestamps less than 1 minute old', () => {
    const justNow = new Date().toISOString();
    expect(formatRelativeTime(justNow)).toBe('Just now');
  });

  it('returns minutes ago for timestamps under 1 hour', () => {
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(formatRelativeTime(tenMinAgo)).toBe('10 min ago');
  });

  it('returns hours ago with pluralization', () => {
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();

    expect(formatRelativeTime(oneHourAgo)).toBe('1 hour ago');
    expect(formatRelativeTime(threeHoursAgo)).toBe('3 hours ago');
  });

  it('returns days ago for timestamps under 1 week', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(twoDaysAgo)).toBe('2 days ago');
  });

  it('returns formatted date for timestamps over 1 week', () => {
    const twoWeeksAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
    const result = formatRelativeTime(twoWeeksAgo);
    // Should be a locale-formatted date like "Mar 4" (not a relative time)
    expect(result).not.toContain('ago');
    expect(result).not.toBe('Just now');
  });
});

// ---------------------------------------------------------------------------
// Tests: useCalendarNotifications hook
// ---------------------------------------------------------------------------

describe('useCalendarNotifications', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();

    // Clear localStorage between tests
    localStorage.clear();

    // Mock Notification API
    Object.defineProperty(globalThis, 'Notification', {
      value: {
        permission: 'denied',
        requestPermission: vi.fn().mockResolvedValue('denied'),
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns loading=true initially, then loading=false after fetch', async () => {
    mockGetNotifications.mockResolvedValue({ notifications: [] });

    const { result } = renderHook(() => useCalendarNotifications());

    // Initially loading
    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it('fetches notifications on mount and populates state', async () => {
    const notifications = [
      makeNotification({ id: 'n1' }),
      makeNotification({ id: 'n2' }),
    ];
    mockGetNotifications.mockResolvedValue({ notifications });

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.notifications).toHaveLength(2);
    expect(result.current.notifications[0].id).toBe('n1');
    expect(result.current.notifications[1].id).toBe('n2');
  });

  it('sets error on initial fetch failure', async () => {
    mockGetNotifications.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Unable to load notifications');
    expect(result.current.notifications).toHaveLength(0);
  });

  it('computes unreadCount from notifications without read IDs in localStorage', async () => {
    const notifications = [
      makeNotification({ id: 'n1' }),
      makeNotification({ id: 'n2' }),
      makeNotification({ id: 'n3' }),
    ];
    mockGetNotifications.mockResolvedValue({ notifications });

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // All should be unread since nothing in localStorage
    expect(result.current.unreadCount).toBe(3);
  });

  it('marks notifications as read from localStorage on load', async () => {
    // Pre-populate localStorage with read IDs
    localStorage.setItem(
      'perennia_calendar_notifications_read',
      JSON.stringify(['n1', 'n3'])
    );

    const notifications = [
      makeNotification({ id: 'n1' }),
      makeNotification({ id: 'n2' }),
      makeNotification({ id: 'n3' }),
    ];
    mockGetNotifications.mockResolvedValue({ notifications });

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.unreadCount).toBe(1); // only n2 is unread
    expect(result.current.notifications.find(n => n.id === 'n1').isRead).toBe(true);
    expect(result.current.notifications.find(n => n.id === 'n2').isRead).toBe(false);
    expect(result.current.notifications.find(n => n.id === 'n3').isRead).toBe(true);
  });

  it('markAsRead updates state and persists to localStorage', async () => {
    const notifications = [makeNotification({ id: 'n1' })];
    mockGetNotifications.mockResolvedValue({ notifications });
    mockMarkNotificationRead.mockResolvedValue({});

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.unreadCount).toBe(1);

    act(() => {
      result.current.markAsRead('n1');
    });

    expect(result.current.unreadCount).toBe(0);
    expect(result.current.notifications[0].isRead).toBe(true);

    // Should persist to localStorage
    const stored = JSON.parse(localStorage.getItem('perennia_calendar_notifications_read'));
    expect(stored).toContain('n1');

    // Should fire API call
    expect(mockMarkNotificationRead).toHaveBeenCalledWith('n1');
  });

  it('markAllRead updates all notifications and persists', async () => {
    const notifications = [
      makeNotification({ id: 'n1' }),
      makeNotification({ id: 'n2' }),
    ];
    mockGetNotifications.mockResolvedValue({ notifications });
    mockMarkAllNotificationsRead.mockResolvedValue({});

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.unreadCount).toBe(2);

    act(() => {
      result.current.markAllRead();
    });

    expect(result.current.unreadCount).toBe(0);
    expect(result.current.notifications.every(n => n.isRead)).toBe(true);

    // Should persist both IDs
    const stored = JSON.parse(localStorage.getItem('perennia_calendar_notifications_read'));
    expect(stored).toContain('n1');
    expect(stored).toContain('n2');

    // Should fire API call
    expect(mockMarkAllNotificationsRead).toHaveBeenCalledOnce();
  });

  it('polls for new notifications at 60-second intervals', async () => {
    mockGetNotifications.mockResolvedValue({ notifications: [] });

    renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(1);
    });

    // Advance 60 seconds
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(2);
    });

    // Advance another 60 seconds
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(3);
    });
  });

  it('silently ignores errors during polling (non-initial fetch)', async () => {
    // Initial fetch succeeds
    mockGetNotifications.mockResolvedValueOnce({
      notifications: [makeNotification({ id: 'n1' })],
    });
    // Subsequent poll fails
    mockGetNotifications.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Initial data is present and no error
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.error).toBeNull();

    // Advance to trigger poll
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });

    // Error should NOT be set for non-initial failures
    expect(result.current.error).toBeNull();
  });

  it('cleans up interval on unmount', async () => {
    mockGetNotifications.mockResolvedValue({ notifications: [] });

    const { unmount } = renderHook(() => useCalendarNotifications());

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(1);
    });

    unmount();

    // Advance well past poll interval -- should not trigger more calls
    await act(async () => {
      vi.advanceTimersByTime(120000);
    });

    // Only the initial call
    expect(mockGetNotifications).toHaveBeenCalledTimes(1);
  });
});
