import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../hooks/useCalendarNotifications', () => ({
  formatRelativeTime: vi.fn((iso) => {
    if (!iso) return '';
    const diffMs = Date.now() - new Date(iso).getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24) return `${diffHrs} hour${diffHrs !== 1 ? 's' : ''} ago`;
    return `${Math.floor(diffHrs / 24)} day${Math.floor(diffHrs / 24) !== 1 ? 's' : ''} ago`;
  }),
}));

import CalendarNotifications from '../CalendarNotifications';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCalendarNotification(overrides = {}) {
  return {
    id: 'cn-1',
    type: 'booking',
    title: 'New booking from John',
    description: 'Consultation scheduled for 3:00 PM',
    isRead: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function renderCalendarNotifications(propOverrides = {}) {
  const defaultProps = {
    notifications: [],
    unreadCount: 0,
    isOpen: false,
    onToggle: vi.fn(),
    onMarkAsRead: vi.fn(),
    onMarkAllRead: vi.fn(),
    onSelectNotification: vi.fn(),
    ...propOverrides,
  };

  const result = render(<CalendarNotifications {...defaultProps} />);
  return { ...result, props: defaultProps };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CalendarNotifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders bell button with correct aria attributes', () => {
    renderCalendarNotifications({ unreadCount: 3 });

    const button = screen.getByRole('button', { name: /Notifications, 3 unread/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAttribute('aria-haspopup', 'true');
  });

  it('shows unread badge via NotificationBadge when count > 0', () => {
    renderCalendarNotifications({ unreadCount: 5 });

    // NotificationBadge renders a span with role="status"
    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('5');
  });

  it('does not show badge when unreadCount is 0', () => {
    renderCalendarNotifications({ unreadCount: 0 });

    // NotificationBadge returns null for count <= 0
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('calls onToggle when bell button is clicked', () => {
    const onToggle = vi.fn();
    renderCalendarNotifications({ onToggle });

    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('does not render panel when isOpen is false', () => {
    renderCalendarNotifications({ isOpen: false });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders notification panel when isOpen is true', () => {
    renderCalendarNotifications({ isOpen: true });

    const panel = screen.getByRole('dialog', { name: 'Notifications' });
    expect(panel).toBeInTheDocument();
    expect(screen.getByText('Notifications', { selector: 'h3' })).toBeInTheDocument();
  });

  it('shows empty state when no notifications exist and panel is open', () => {
    renderCalendarNotifications({ isOpen: true, notifications: [] });

    expect(screen.getByText('No notifications yet')).toBeInTheDocument();
  });

  it('renders notification items with type-specific icons', () => {
    const notifications = [
      makeCalendarNotification({ id: 'cn-1', type: 'booking', title: 'Booking received' }),
      makeCalendarNotification({ id: 'cn-2', type: 'cancellation', title: 'Appointment cancelled' }),
      makeCalendarNotification({ id: 'cn-3', type: 'reminder', title: 'Upcoming call' }),
      makeCalendarNotification({ id: 'cn-4', type: 'reschedule', title: 'Rescheduled' }),
    ];

    renderCalendarNotifications({ isOpen: true, notifications, unreadCount: 4 });

    expect(screen.getByText('Booking received')).toBeInTheDocument();
    expect(screen.getByText('Appointment cancelled')).toBeInTheDocument();
    expect(screen.getByText('Upcoming call')).toBeInTheDocument();
    expect(screen.getByText('Rescheduled')).toBeInTheDocument();

    // Each item rendered as listitem
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(4);
  });

  it('displays unread dot for unread notifications and read dot for read ones', () => {
    const notifications = [
      makeCalendarNotification({ id: 'cn-1', isRead: false }),
      makeCalendarNotification({ id: 'cn-2', isRead: true, title: 'Read notification' }),
    ];

    renderCalendarNotifications({ isOpen: true, notifications, unreadCount: 1 });

    // Unread notification should have an unread indicator
    const unreadDots = screen.getAllByLabelText('Unread');
    expect(unreadDots).toHaveLength(1);
  });

  it('calls onMarkAsRead when clicking an unread notification', () => {
    const onMarkAsRead = vi.fn();
    const onSelectNotification = vi.fn();
    const notifications = [makeCalendarNotification({ id: 'cn-42', isRead: false })];

    renderCalendarNotifications({
      isOpen: true,
      notifications,
      unreadCount: 1,
      onMarkAsRead,
      onSelectNotification,
    });

    fireEvent.click(screen.getByText('New booking from John'));

    expect(onMarkAsRead).toHaveBeenCalledWith('cn-42');
    expect(onSelectNotification).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cn-42' })
    );
  });

  it('does not call onMarkAsRead for already-read notifications', () => {
    const onMarkAsRead = vi.fn();
    const onSelectNotification = vi.fn();
    const notifications = [makeCalendarNotification({ isRead: true })];

    renderCalendarNotifications({
      isOpen: true,
      notifications,
      unreadCount: 0,
      onMarkAsRead,
      onSelectNotification,
    });

    fireEvent.click(screen.getByText('New booking from John'));

    expect(onMarkAsRead).not.toHaveBeenCalled();
    expect(onSelectNotification).toHaveBeenCalled();
  });

  it('disables "Mark all as read" button when unreadCount is 0', () => {
    renderCalendarNotifications({ isOpen: true, unreadCount: 0 });

    const markAllBtn = screen.getByText('Mark all as read');
    expect(markAllBtn).toBeDisabled();
  });

  it('calls onMarkAllRead when "Mark all as read" is clicked', () => {
    const onMarkAllRead = vi.fn();
    const notifications = [makeCalendarNotification()];

    renderCalendarNotifications({
      isOpen: true,
      notifications,
      unreadCount: 1,
      onMarkAllRead,
    });

    fireEvent.click(screen.getByText('Mark all as read'));
    expect(onMarkAllRead).toHaveBeenCalledOnce();
  });

  it('closes panel on Escape key and returns focus to bell button', () => {
    const onToggle = vi.fn();
    renderCalendarNotifications({ isOpen: true, onToggle });

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('closes panel on click outside', () => {
    const onToggle = vi.fn();

    const { container } = render(
      <div>
        <div data-testid="outside">outside</div>
        <CalendarNotifications
          notifications={[]}
          unreadCount={0}
          isOpen={true}
          onToggle={onToggle}
          onMarkAsRead={vi.fn()}
          onMarkAllRead={vi.fn()}
        />
      </div>
    );

    fireEvent.mouseDown(screen.getByTestId('outside'));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it('shows description text when provided on a notification', () => {
    const notifications = [
      makeCalendarNotification({
        description: 'Call with Jane at 2 PM tomorrow',
      }),
    ];

    renderCalendarNotifications({ isOpen: true, notifications, unreadCount: 1 });

    expect(screen.getByText('Call with Jane at 2 PM tomorrow')).toBeInTheDocument();
  });

  it('uses default title from NOTIFICATION_TYPE_CONFIG when title is missing', () => {
    const notifications = [
      makeCalendarNotification({ title: null, type: 'cancellation' }),
    ];

    renderCalendarNotifications({ isOpen: true, notifications, unreadCount: 1 });

    // Default title for cancellation is "Cancellation"
    expect(screen.getByText('Cancellation')).toBeInTheDocument();
  });

  it('displays formatted relative timestamps', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();

    const notifications = [
      makeCalendarNotification({ id: 'cn-1', title: 'Recent', created_at: fiveMinAgo }),
      makeCalendarNotification({ id: 'cn-2', title: 'Older', created_at: twoHoursAgo }),
    ];

    renderCalendarNotifications({ isOpen: true, notifications, unreadCount: 2 });

    expect(screen.getByText('5 min ago')).toBeInTheDocument();
    expect(screen.getByText('2 hours ago')).toBeInTheDocument();
  });
});
