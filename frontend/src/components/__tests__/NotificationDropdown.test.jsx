import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../Portal/NotificationDropdown.css', () => ({}));

import NotificationDropdown from '../Portal/NotificationDropdown';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeNotification(overrides = {}) {
  return {
    id: 'notif-1',
    type: 'document_request',
    title: 'Upload paystubs',
    message: 'Please upload your most recent paystubs',
    read: false,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function renderDropdown(propOverrides = {}) {
  const defaultProps = {
    notifications: [],
    unreadCount: 0,
    onMarkAsRead: vi.fn(),
    onMarkAllAsRead: vi.fn(),
    onNotificationClick: vi.fn(),
    onLoadMore: vi.fn(),
    hasMore: false,
    loading: false,
    ...propOverrides,
  };

  const result = render(<NotificationDropdown {...defaultProps} />);
  return { ...result, props: defaultProps };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NotificationDropdown (Portal)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the trigger button with aria attributes', () => {
    renderDropdown({ unreadCount: 3 });

    const trigger = screen.getByRole('button', { name: /Notifications.*3 unread/i });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveAttribute('aria-haspopup', 'true');
  });

  it('shows unread badge only when unreadCount > 0', () => {
    const { rerender } = render(
      <NotificationDropdown notifications={[]} unreadCount={0} />
    );

    expect(screen.queryByText('5')).not.toBeInTheDocument();

    rerender(
      <NotificationDropdown notifications={[]} unreadCount={5} />
    );

    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('caps badge at 99+', () => {
    renderDropdown({ unreadCount: 150 });
    expect(screen.getByText('99+')).toBeInTheDocument();
  });

  it('toggles panel open and closed on button click', () => {
    renderDropdown({ unreadCount: 1 });

    const trigger = screen.getByRole('button', { name: /Notifications/i });

    // Open
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByText('Notifications', { selector: 'h3' })).toBeInTheDocument();

    // Close
    fireEvent.click(trigger);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('shows empty state when notifications list is empty', () => {
    renderDropdown({ unreadCount: 0 });

    // Open panel
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    expect(screen.getByText('No notifications yet')).toBeInTheDocument();
  });

  it('renders notification items with correct structure', () => {
    const notifications = [
      makeNotification({ id: 'n1', title: 'Upload W2', message: 'We need your W2', type: 'document_request' }),
      makeNotification({ id: 'n2', title: 'Loan approved', message: 'Congratulations!', type: 'approval', read: true }),
    ];

    renderDropdown({ notifications, unreadCount: 1 });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    expect(screen.getByText('Upload W2')).toBeInTheDocument();
    expect(screen.getByText('We need your W2')).toBeInTheDocument();
    expect(screen.getByText('Loan approved')).toBeInTheDocument();

    // Unread item should have menuitem role
    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(2);
  });

  it('applies unread class to unread notifications', () => {
    const notifications = [
      makeNotification({ id: 'n1', read: false }),
      makeNotification({ id: 'n2', read: true, title: 'Read item' }),
    ];

    renderDropdown({ notifications, unreadCount: 1 });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    const items = screen.getAllByRole('menuitem');
    expect(items[0].className).toContain('unread');
    expect(items[1].className).not.toContain('unread');
  });

  it('shows unread indicator for unread items', () => {
    const notifications = [makeNotification({ read: false })];

    renderDropdown({ notifications, unreadCount: 1 });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    expect(screen.getByLabelText('Unread')).toBeInTheDocument();
  });

  it('calls onMarkAsRead and onNotificationClick when clicking an unread notification', () => {
    const onMarkAsRead = vi.fn();
    const onNotificationClick = vi.fn();
    const notifications = [makeNotification({ id: 'abc', read: false })];

    renderDropdown({ notifications, unreadCount: 1, onMarkAsRead, onNotificationClick });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    fireEvent.click(screen.getByText('Upload paystubs'));

    expect(onMarkAsRead).toHaveBeenCalledWith('abc');
    expect(onNotificationClick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'abc' })
    );
  });

  it('does not call onMarkAsRead for already-read notifications', () => {
    const onMarkAsRead = vi.fn();
    const onNotificationClick = vi.fn();
    const notifications = [makeNotification({ read: true })];

    renderDropdown({ notifications, unreadCount: 0, onMarkAsRead, onNotificationClick });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    fireEvent.click(screen.getByText('Upload paystubs'));

    expect(onMarkAsRead).not.toHaveBeenCalled();
    expect(onNotificationClick).toHaveBeenCalled();
  });

  it('shows "Mark all as read" button only when there are unread items', () => {
    const onMarkAllAsRead = vi.fn();

    const { rerender } = render(
      <NotificationDropdown
        notifications={[makeNotification({ read: true })]}
        unreadCount={0}
        onMarkAllAsRead={onMarkAllAsRead}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    expect(screen.queryByText('Mark all as read')).not.toBeInTheDocument();

    // Close and re-render with unread
    rerender(
      <NotificationDropdown
        notifications={[makeNotification({ read: false })]}
        unreadCount={1}
        onMarkAllAsRead={onMarkAllAsRead}
      />
    );

    // Re-open (rerender keeps the closed state, so click again)
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    fireEvent.click(screen.getByText('Mark all as read'));
    expect(onMarkAllAsRead).toHaveBeenCalledOnce();
  });

  it('shows "Load more" button when hasMore is true and calls onLoadMore', () => {
    const onLoadMore = vi.fn();
    const notifications = [makeNotification()];

    renderDropdown({ notifications, unreadCount: 1, hasMore: true, onLoadMore });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    const loadMore = screen.getByText('Load more');
    expect(loadMore).toBeInTheDocument();

    fireEvent.click(loadMore);
    expect(onLoadMore).toHaveBeenCalledOnce();
  });

  it('shows loading state on Load more button', () => {
    const notifications = [makeNotification()];

    renderDropdown({ notifications, unreadCount: 1, hasMore: true, loading: true });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    const loadingBtn = screen.getByText('Loading...');
    expect(loadingBtn).toBeInTheDocument();
    expect(loadingBtn).toBeDisabled();
  });

  it('closes panel on Escape key', () => {
    renderDropdown({ unreadCount: 1 });

    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('closes panel on click outside', () => {
    const { container } = render(
      <div>
        <div data-testid="outside">outside</div>
        <NotificationDropdown notifications={[makeNotification()]} unreadCount={1} />
      </div>
    );

    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId('outside'));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('renders correct icon for each notification type', () => {
    const types = ['document_request', 'status_change', 'message', 'approval', 'reminder'];
    const notifications = types.map((type, i) =>
      makeNotification({ id: `t-${i}`, type, title: `${type} notif` })
    );

    renderDropdown({ notifications, unreadCount: 5 });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    // Each notification renders an SVG icon
    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(5);
    items.forEach(item => {
      expect(item.querySelector('svg')).toBeInTheDocument();
    });
  });

  it('formats time correctly for recent and older timestamps', () => {
    const justNow = new Date().toISOString();
    const minutesAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    const hoursAgo = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString();
    const daysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();

    const notifications = [
      makeNotification({ id: 'now', title: 'Now', created_at: justNow }),
      makeNotification({ id: 'min', title: 'Minutes', created_at: minutesAgo }),
      makeNotification({ id: 'hrs', title: 'Hours', created_at: hoursAgo }),
      makeNotification({ id: 'day', title: 'Days', created_at: daysAgo }),
    ];

    renderDropdown({ notifications, unreadCount: 4 });
    fireEvent.click(screen.getByRole('button', { name: /Notifications/i }));

    expect(screen.getByText('Just now')).toBeInTheDocument();
    expect(screen.getByText('10m ago')).toBeInTheDocument();
    expect(screen.getByText('4h ago')).toBeInTheDocument();
    expect(screen.getByText('2d ago')).toBeInTheDocument();
  });
});
