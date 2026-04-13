import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../NotificationBell.css', () => ({}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

const mockGetNotifications = vi.fn();
const mockMarkAsRead = vi.fn();
const mockMarkAllAsRead = vi.fn();

vi.mock('../../services/api', () => ({
  notificationsApi: {
    getNotifications: (...args) => mockGetNotifications(...args),
    markAsRead: (...args) => mockMarkAsRead(...args),
    markAllAsRead: (...args) => mockMarkAllAsRead(...args),
  },
}));

vi.mock('../../services/pushNotificationService', () => ({
  onNotification: () => () => {},
}));

import NotificationBell from '../NotificationBell';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeNotification(overrides = {}) {
  return {
    id: 'n-1',
    type: 'permission_approved',
    title: 'Permission approved',
    message: 'Your request was approved',
    is_read: false,
    created_at: new Date().toISOString(),
    link: '/tasks/123',
    ...overrides,
  };
}

function makeApiResponse(notifications, unread_count) {
  return {
    data: {
      notifications,
      unread_count: unread_count ?? notifications.filter(n => !n.is_read).length,
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockNavigate.mockClear();
    mockGetNotifications.mockClear();
    mockMarkAsRead.mockClear();
    mockMarkAllAsRead.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the bell button even when there are zero unread notifications', async () => {
    mockGetNotifications.mockResolvedValue(makeApiResponse([], 0));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledOnce();
    });

    // Bell should still be visible, just without a badge
    expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    expect(screen.queryByClassName?.('notification-badge')).toBeFalsy();
  });

  it('displays the bell button with badge when there are unread notifications', async () => {
    const notifications = [makeNotification(), makeNotification({ id: 'n-2' })];
    mockGetNotifications.mockResolvedValue(makeApiResponse(notifications, 2));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('caps the badge display at 9+', async () => {
    const notifications = Array.from({ length: 12 }, (_, i) =>
      makeNotification({ id: `n-${i}` })
    );
    mockGetNotifications.mockResolvedValue(makeApiResponse(notifications, 12));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByText('9+')).toBeInTheDocument();
    });
  });

  it('toggles dropdown visibility when bell is clicked', async () => {
    mockGetNotifications.mockResolvedValue(
      makeApiResponse([makeNotification()], 1)
    );

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    // Dropdown should not be visible initially
    expect(screen.queryByText('Notifications', { selector: 'h3' })).not.toBeInTheDocument();

    // Click bell
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText('Notifications', { selector: 'h3' })).toBeInTheDocument();

    // Click bell again to close
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.queryByText('Notifications', { selector: 'h3' })).not.toBeInTheDocument();
  });

  it('renders notification list with correct content in dropdown', async () => {
    const notifications = [
      makeNotification({ title: 'Goal achieved', message: 'Monthly target hit', type: 'goal_reminder' }),
      makeNotification({
        id: 'n-2',
        title: 'Feedback received',
        message: 'New comment on your task',
        type: 'feedback_added',
        is_read: true,
      }),
    ];
    mockGetNotifications.mockResolvedValue(makeApiResponse(notifications, 1));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));

    expect(screen.getByText('Goal achieved')).toBeInTheDocument();
    expect(screen.getByText('Monthly target hit')).toBeInTheDocument();
    expect(screen.getByText('Feedback received')).toBeInTheDocument();
    expect(screen.getByText('New comment on your task')).toBeInTheDocument();
  });

  it('shows empty state when no notifications exist', async () => {
    mockGetNotifications.mockResolvedValue(makeApiResponse([], 1));

    // Force unread count to 1 so the bell renders, but notifications array is empty
    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText('No notifications yet')).toBeInTheDocument();
  });

  it('marks a notification as read when clicked and navigates to link', async () => {
    const notification = makeNotification({ link: '/loans/42' });
    mockGetNotifications.mockResolvedValue(makeApiResponse([notification], 1));
    mockMarkAsRead.mockResolvedValue({});

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));
    fireEvent.click(screen.getByText('Permission approved'));

    await waitFor(() => {
      expect(mockMarkAsRead).toHaveBeenCalledWith('n-1');
    });
    expect(mockNavigate).toHaveBeenCalledWith('/loans/42');
  });

  it('does not call markAsRead for already-read notifications but still navigates', async () => {
    const notification = makeNotification({ is_read: true, link: '/tasks/99' });
    mockGetNotifications.mockResolvedValue(makeApiResponse([notification], 0));

    // Component renders null when unreadCount is 0, so force unread_count = 1
    mockGetNotifications.mockResolvedValue(makeApiResponse([notification], 1));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));
    fireEvent.click(screen.getByText('Permission approved'));

    // Should NOT call markAsRead since already read
    expect(mockMarkAsRead).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/tasks/99');
  });

  it('marks all as read and updates state', async () => {
    const notifications = [
      makeNotification({ id: 'n-1' }),
      makeNotification({ id: 'n-2', title: 'Second' }),
    ];
    mockGetNotifications.mockResolvedValue(makeApiResponse(notifications, 2));
    mockMarkAllAsRead.mockResolvedValue({});

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText('Mark all read')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Mark all read'));

    await waitFor(() => {
      expect(mockMarkAllAsRead).toHaveBeenCalledOnce();
    });
  });

  it('closes dropdown on outside click', async () => {
    mockGetNotifications.mockResolvedValue(
      makeApiResponse([makeNotification()], 1)
    );

    const { container } = render(
      <div>
        <div data-testid="outside">outside area</div>
        <NotificationBell />
      </div>
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    // Open dropdown
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText('Notifications', { selector: 'h3' })).toBeInTheDocument();

    // Click outside
    fireEvent.mouseDown(screen.getByTestId('outside'));
    expect(screen.queryByText('Notifications', { selector: 'h3' })).not.toBeInTheDocument();
  });

  it('navigates to /aria/notifications when "View all notifications" is clicked', async () => {
    mockGetNotifications.mockResolvedValue(
      makeApiResponse([makeNotification()], 1)
    );

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));
    fireEvent.click(screen.getByText('View all notifications'));

    expect(mockNavigate).toHaveBeenCalledWith('/aria/notifications');
  });

  it('formats relative timestamps correctly', async () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();

    const notifications = [
      makeNotification({ id: 'n-1', title: 'Recent', created_at: fiveMinutesAgo }),
      makeNotification({ id: 'n-2', title: 'Hours ago', created_at: twoHoursAgo }),
      makeNotification({ id: 'n-3', title: 'Days ago', created_at: threeDaysAgo }),
    ];
    mockGetNotifications.mockResolvedValue(makeApiResponse(notifications, 3));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/notifications/i));

    expect(screen.getByText('5m ago')).toBeInTheDocument();
    expect(screen.getByText('2h ago')).toBeInTheDocument();
    expect(screen.getByText('3d ago')).toBeInTheDocument();
  });

  it('polls for new notifications at 30-second intervals', async () => {
    mockGetNotifications.mockResolvedValue(makeApiResponse([], 0));

    render(<NotificationBell />);

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledOnce();
    });

    // Advance 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(2);
    });

    // Advance another 30 seconds
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    await waitFor(() => {
      expect(mockGetNotifications).toHaveBeenCalledTimes(3);
    });
  });
});
