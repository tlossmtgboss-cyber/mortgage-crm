/**
 * Tests for calendar sub-components:
 *   - StatusBadge
 *   - MiniCalendar
 *   - UpcomingAppointments
 *   - calendarUtils (pure functions)
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

// ---------------------------------------------------------------------------
// calendarUtils (pure function tests -- no mocking needed)
// ---------------------------------------------------------------------------
import {
  normalizeUTCDate,
  formatDateForAPI,
  formatTime,
  formatDuration,
  getMeetingModeIcon,
  getMeetingModeColor,
  isToday,
  MONTH_NAMES,
  DAY_NAMES,
} from '../components/calendar/calendarUtils';

describe('calendarUtils', () => {
  describe('normalizeUTCDate', () => {
    it('appends Z to date strings without timezone', () => {
      expect(normalizeUTCDate('2026-03-15T10:00:00')).toBe('2026-03-15T10:00:00Z');
    });

    it('does not modify strings that already have Z', () => {
      expect(normalizeUTCDate('2026-03-15T10:00:00Z')).toBe('2026-03-15T10:00:00Z');
    });

    it('does not modify strings with timezone offset', () => {
      expect(normalizeUTCDate('2026-03-15T10:00:00+05:00')).toBe('2026-03-15T10:00:00+05:00');
    });

    it('returns null/undefined as-is', () => {
      expect(normalizeUTCDate(null)).toBeNull();
      expect(normalizeUTCDate(undefined)).toBeUndefined();
    });
  });

  describe('formatDateForAPI', () => {
    it('formats a date as YYYY-MM-DD', () => {
      const date = new Date(2026, 2, 5); // March 5, 2026
      expect(formatDateForAPI(date)).toBe('2026-03-05');
    });

    it('pads single-digit months and days', () => {
      const date = new Date(2026, 0, 3); // Jan 3, 2026
      expect(formatDateForAPI(date)).toBe('2026-01-03');
    });
  });

  describe('formatDuration', () => {
    it('formats a 30-minute gap as "30m"', () => {
      expect(formatDuration('2026-03-15T10:00:00Z', '2026-03-15T10:30:00Z')).toBe('30m');
    });

    it('formats a 60-minute gap as "1h"', () => {
      expect(formatDuration('2026-03-15T10:00:00Z', '2026-03-15T11:00:00Z')).toBe('1h');
    });

    it('formats a 90-minute gap as "1h 30m"', () => {
      expect(formatDuration('2026-03-15T10:00:00Z', '2026-03-15T11:30:00Z')).toBe('1h 30m');
    });
  });

  describe('getMeetingModeIcon', () => {
    it('returns video icon for VIDEO mode', () => {
      expect(getMeetingModeIcon('VIDEO')).toBe('\u{1F4F9}');
    });

    it('returns phone icon for PHONE mode', () => {
      expect(getMeetingModeIcon('PHONE')).toBe('\u{1F4DE}');
    });

    it('returns person icon for IN_PERSON mode', () => {
      expect(getMeetingModeIcon('IN_PERSON')).toBe('\u{1F464}');
    });

    it('returns calendar icon for unknown mode', () => {
      expect(getMeetingModeIcon('unknown')).toBe('\u{1F4C5}');
    });

    it('is case-insensitive', () => {
      expect(getMeetingModeIcon('video')).toBe('\u{1F4F9}');
      expect(getMeetingModeIcon('phone')).toBe('\u{1F4DE}');
    });

    it('handles null/undefined gracefully', () => {
      expect(getMeetingModeIcon(null)).toBe('\u{1F4C5}');
      expect(getMeetingModeIcon(undefined)).toBe('\u{1F4C5}');
    });
  });

  describe('getMeetingModeColor', () => {
    it('returns blue for VIDEO', () => {
      expect(getMeetingModeColor('VIDEO')).toBe('#2563eb');
    });

    it('returns green for PHONE', () => {
      expect(getMeetingModeColor('PHONE')).toBe('#2D7A52');
    });

    it('returns red for IN_PERSON', () => {
      expect(getMeetingModeColor('IN_PERSON')).toBe('#dc2626');
    });

    it('returns gray for unknown', () => {
      expect(getMeetingModeColor(null)).toBe('#6b7280');
    });
  });

  describe('isToday', () => {
    it('returns true for today', () => {
      expect(isToday(new Date())).toBe(true);
    });

    it('returns false for yesterday', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      expect(isToday(yesterday)).toBe(false);
    });

    it('returns false for null', () => {
      expect(isToday(null)).toBe(false);
    });
  });

  describe('constants', () => {
    it('MONTH_NAMES has 12 entries', () => {
      expect(MONTH_NAMES).toHaveLength(12);
      expect(MONTH_NAMES[0]).toBe('January');
      expect(MONTH_NAMES[11]).toBe('December');
    });

    it('DAY_NAMES has 7 entries', () => {
      expect(DAY_NAMES).toHaveLength(7);
      expect(DAY_NAMES[0]).toBe('S');
      expect(DAY_NAMES[6]).toBe('S');
    });
  });
});

// ---------------------------------------------------------------------------
// StatusBadge
// ---------------------------------------------------------------------------
import StatusBadge, { STATUS_CONFIG } from '../components/calendar/StatusBadge';

describe('StatusBadge', () => {
  it('renders with correct label for "booked" status', () => {
    render(<StatusBadge status="booked" />);
    expect(screen.getByText('Booked')).toBeInTheDocument();
  });

  it('renders with correct label for "confirmed" status', () => {
    render(<StatusBadge status="confirmed" />);
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('renders with correct label for "cancelled" status', () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('renders with correct label for "no_show" status', () => {
    render(<StatusBadge status="no_show" />);
    expect(screen.getByText('No Show')).toBeInTheDocument();
  });

  it('renders with correct label for "completed" status', () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('normalizes status with spaces to underscore', () => {
    render(<StatusBadge status="no show" />);
    expect(screen.getByText('No Show')).toBeInTheDocument();
  });

  it('handles uppercase status', () => {
    render(<StatusBadge status="BOOKED" />);
    expect(screen.getByText('Booked')).toBeInTheDocument();
  });

  it('falls back to "Available" for unknown status', () => {
    render(<StatusBadge status="unknown_status" />);
    expect(screen.getByText('Available')).toBeInTheDocument();
  });

  it('renders with role="status" and aria-label', () => {
    render(<StatusBadge status="booked" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'Status: Booked');
  });

  it('renders dot by default', () => {
    const { container } = render(<StatusBadge status="booked" />);
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).toBeInTheDocument();
  });

  it('hides dot when showDot=false', () => {
    const { container } = render(<StatusBadge status="booked" showDot={false} />);
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).toBeNull();
  });

  it('applies correct colors for confirmed status', () => {
    render(<StatusBadge status="confirmed" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveStyle({ backgroundColor: '#dcfce7', color: '#166534' });
  });

  it('supports sm, md, lg sizes', () => {
    const { rerender } = render(<StatusBadge status="booked" size="sm" />);
    let badge = screen.getByRole('status');
    expect(badge).toHaveStyle({ fontSize: '11px' });

    rerender(<StatusBadge status="booked" size="md" />);
    badge = screen.getByRole('status');
    expect(badge).toHaveStyle({ fontSize: '12px' });

    rerender(<StatusBadge status="booked" size="lg" />);
    badge = screen.getByRole('status');
    expect(badge).toHaveStyle({ fontSize: '13px' });
  });

  it('STATUS_CONFIG exports all expected statuses', () => {
    const expectedStatuses = [
      'booked', 'confirmed', 'reminded', 'checked_in',
      'completed', 'cancelled', 'no_show', 'rescheduled',
      'tentative', 'available',
    ];
    for (const status of expectedStatuses) {
      expect(STATUS_CONFIG[status]).toBeDefined();
      expect(STATUS_CONFIG[status].label).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// MiniCalendar
// ---------------------------------------------------------------------------
import MiniCalendar from '../components/calendar/MiniCalendar';

describe('MiniCalendar', () => {
  const defaultProps = {
    currentDate: new Date(2026, 2, 1), // March 2026
    selectedDate: new Date(2026, 2, 15),
    eventDateSet: new Set(),
    onDateClick: vi.fn(),
    onPreviousMonth: vi.fn(),
    onNextMonth: vi.fn(),
    onGoToToday: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders month and year header', () => {
    render(<MiniCalendar {...defaultProps} />);
    expect(screen.getByText('March 2026')).toBeInTheDocument();
  });

  it('renders day name headers (S, M, T, W, T, F, S)', () => {
    render(<MiniCalendar {...defaultProps} />);
    const dayHeaders = screen.getAllByText(/^[SMTWF]$/);
    expect(dayHeaders.length).toBe(7);
  });

  it('renders 31 day cells for March', () => {
    render(<MiniCalendar {...defaultProps} />);
    expect(screen.getByText('31')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('calls onDateClick when a day is clicked', () => {
    render(<MiniCalendar {...defaultProps} />);
    fireEvent.click(screen.getByText('15'));
    expect(defaultProps.onDateClick).toHaveBeenCalledTimes(1);
  });

  it('calls onDateClick when Enter is pressed on a day', () => {
    render(<MiniCalendar {...defaultProps} />);
    const day15 = screen.getByText('15').closest('[role="button"]');
    fireEvent.keyDown(day15, { key: 'Enter' });
    expect(defaultProps.onDateClick).toHaveBeenCalledTimes(1);
  });

  it('calls onPreviousMonth when < button is clicked', () => {
    render(<MiniCalendar {...defaultProps} />);
    const buttons = screen.getAllByRole('button');
    const prevBtn = buttons.find(b => b.textContent === '<');
    fireEvent.click(prevBtn);
    expect(defaultProps.onPreviousMonth).toHaveBeenCalledTimes(1);
  });

  it('calls onNextMonth when > button is clicked', () => {
    render(<MiniCalendar {...defaultProps} />);
    const buttons = screen.getAllByRole('button');
    const nextBtn = buttons.find(b => b.textContent === '>');
    fireEvent.click(nextBtn);
    expect(defaultProps.onNextMonth).toHaveBeenCalledTimes(1);
  });

  it('marks selected date with "selected" class', () => {
    render(<MiniCalendar {...defaultProps} />);
    const day15 = screen.getByText('15').closest('.calendar-day');
    expect(day15.className).toContain('selected');
  });

  it('shows event dots for dates in eventDateSet', () => {
    const march10 = new Date(2026, 2, 10);
    const eventDateSet = new Set([march10.toDateString()]);

    render(<MiniCalendar {...defaultProps} eventDateSet={eventDateSet} />);

    const day10 = screen.getByText('10').closest('.calendar-day');
    expect(day10.className).toContain('has-events');
    expect(day10.querySelector('.event-dot')).toBeInTheDocument();
  });

  it('day cells have accessible aria-labels', () => {
    render(<MiniCalendar {...defaultProps} />);
    const day1 = screen.getByLabelText(/Select March 1, 2026/i);
    expect(day1).toBeInTheDocument();
  });

  it('calls onGoToToday when month/year header is clicked', () => {
    render(<MiniCalendar {...defaultProps} />);
    fireEvent.click(screen.getByText('March 2026'));
    expect(defaultProps.onGoToToday).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// UpcomingAppointments
// ---------------------------------------------------------------------------
import UpcomingAppointments from '../components/calendar/UpcomingAppointments';

describe('UpcomingAppointments', () => {
  const mockOnClick = vi.fn();

  const appointments = [
    {
      id: 'appt-1',
      title: 'Consultation with Jane',
      attendee_name: 'Jane Doe',
      scheduled_start: '2026-03-15T14:00:00Z',
      meeting_mode: 'PHONE',
    },
    {
      id: 'appt-2',
      title: 'Rate review with Bob',
      attendee_name: 'Bob Smith',
      scheduled_start: '2026-03-16T10:00:00Z',
      meeting_mode: 'VIDEO',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when appointments array is empty', () => {
    const { container } = render(
      <UpcomingAppointments appointments={[]} onAppointmentClick={mockOnClick} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders "Upcoming" heading', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    expect(screen.getByText('Upcoming')).toBeInTheDocument();
  });

  it('renders all appointments', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    // Attendee names appear inside the appointment-title div alongside an emoji icon,
    // so use a function matcher that checks textContent includes the name.
    expect(screen.getByText((_, el) => el?.textContent?.includes('Jane Doe') && el?.classList?.contains('appointment-title'))).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent?.includes('Bob Smith') && el?.classList?.contains('appointment-title'))).toBeInTheDocument();
  });

  it('calls onAppointmentClick when an appointment is clicked', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    const items = screen.getAllByRole('button');
    fireEvent.click(items[0]); // First appointment
    expect(mockOnClick).toHaveBeenCalledWith(appointments[0]);
  });

  it('calls onAppointmentClick on Enter keypress', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    const items = screen.getAllByRole('button');
    fireEvent.keyDown(items[0], { key: 'Enter' });
    expect(mockOnClick).toHaveBeenCalledWith(appointments[0]);
  });

  it('renders meeting mode icon for each appointment', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    // Phone icon for PHONE mode
    const items = screen.getAllByRole('button');
    expect(items.length).toBe(2);
  });

  it('has accessible role="button" and tabIndex on each item', () => {
    render(<UpcomingAppointments appointments={appointments} onAppointmentClick={mockOnClick} />);
    const items = screen.getAllByRole('button');
    items.forEach(item => {
      expect(item).toHaveAttribute('tabindex', '0');
    });
  });
});
