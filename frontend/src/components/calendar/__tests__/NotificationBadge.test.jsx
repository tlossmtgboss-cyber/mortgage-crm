import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import NotificationBadge from '../NotificationBadge';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NotificationBadge', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when count is 0', () => {
    const { container } = render(<NotificationBadge count={0} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when count is negative', () => {
    const { container } = render(<NotificationBadge count={-1} />);
    expect(container.innerHTML).toBe('');
  });

  it('displays the count in "count" variant', () => {
    render(<NotificationBadge count={5} variant="count" />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveTextContent('5');
    expect(badge.className).toContain('notification-badge-count');
  });

  it('caps display at max (default 99)', () => {
    render(<NotificationBadge count={150} />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveTextContent('99+');
  });

  it('uses custom max value', () => {
    render(<NotificationBadge count={20} max={10} />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveTextContent('10+');
  });

  it('displays exact count when equal to max', () => {
    render(<NotificationBadge count={99} max={99} />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveTextContent('99');
    expect(badge.textContent).not.toContain('+');
  });

  it('renders dot variant without count text', () => {
    render(<NotificationBadge count={3} variant="dot" />);

    const badge = screen.getByRole('status');
    expect(badge.className).toContain('notification-badge-dot');
    // Dot variant should not show the number
    expect(badge.textContent).toBe('');
  });

  it('provides correct aria-label for singular count', () => {
    render(<NotificationBadge count={1} />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', '1 unread notification');
  });

  it('provides correct aria-label for plural count', () => {
    render(<NotificationBadge count={7} />);

    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', '7 unread notifications');
  });

  it('triggers pulse animation when count increases', () => {
    const { rerender } = render(<NotificationBadge count={3} />);

    const badge = screen.getByRole('status');
    expect(badge.className).not.toContain('notification-badge-pulse');

    // Increase count
    rerender(<NotificationBadge count={5} />);

    const updatedBadge = screen.getByRole('status');
    expect(updatedBadge.className).toContain('notification-badge-pulse');

    // Pulse should disappear after 300ms
    act(() => {
      vi.advanceTimersByTime(300);
    });

    const afterPulse = screen.getByRole('status');
    expect(afterPulse.className).not.toContain('notification-badge-pulse');
  });

  it('does not trigger pulse when count decreases', () => {
    const { rerender } = render(<NotificationBadge count={5} />);

    rerender(<NotificationBadge count={2} />);

    const badge = screen.getByRole('status');
    expect(badge.className).not.toContain('notification-badge-pulse');
  });

  it('does not trigger pulse when count stays the same', () => {
    const { rerender } = render(<NotificationBadge count={3} />);

    rerender(<NotificationBadge count={3} />);

    const badge = screen.getByRole('status');
    expect(badge.className).not.toContain('notification-badge-pulse');
  });
});
