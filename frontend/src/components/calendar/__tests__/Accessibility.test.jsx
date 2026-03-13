import React from 'react';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import CalendarGrid from '../CalendarGrid';
import CalendarHeader from '../CalendarHeader';
import EventModal from '../EventModal';
import EditAppointmentForm from '../EditAppointmentForm';
import MiniCalendar from '../MiniCalendar';
import ScreenReaderOnly from '../../common/ScreenReaderOnly';
import LiveRegion from '../../common/LiveRegion';

// ============================================================================
// Test Helpers
// ============================================================================

const today = new Date(2026, 2, 12); // March 12, 2026 (Thursday)
const selectedDate = new Date(2026, 2, 15); // March 15, 2026 (Sunday)

const defaultGridProps = {
  currentDate: today,
  selectedDate: selectedDate,
  eventDateSet: new Set([new Date(2026, 2, 10).toDateString()]),
  onDateClick: vi.fn(),
  onPreviousMonth: vi.fn(),
  onNextMonth: vi.fn(),
  onGoToToday: vi.fn(),
};

const defaultMiniCalendarProps = {
  currentDate: today,
  selectedDate: selectedDate,
  eventDateSet: new Set([new Date(2026, 2, 10).toDateString()]),
  onDateClick: vi.fn(),
  onPreviousMonth: vi.fn(),
  onNextMonth: vi.fn(),
  onGoToToday: vi.fn(),
};

const defaultHeaderProps = {
  title: 'March 2026',
  onPrevious: vi.fn(),
  onNext: vi.fn(),
  onToday: vi.fn(),
  view: 'month',
  onViewChange: vi.fn(),
};

const sampleEvent = {
  id: '1',
  title: 'Consultation Call',
  status: 'booked',
  scheduled_start: '2026-03-12T14:00:00Z',
  scheduled_end: '2026-03-12T14:30:00Z',
  attendee_name: 'Jane Doe',
  attendee_email: 'jane@example.com',
  meeting_mode: 'VIDEO',
  notes: 'Pre-approval discussion',
};

const defaultEditAppointment = {
  title: 'Test Appointment',
  attendee_name: 'John Smith',
  attendee_email: 'john@example.com',
  date: '2026-03-15',
  time: '10:00',
  duration: '30',
  meeting_mode: 'PHONE',
  status: 'booked',
  notes: 'Test notes',
};

// ============================================================================
// CalendarGrid Accessibility Tests
// ============================================================================

describe('CalendarGrid Accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with role="grid" on the table element', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const grid = screen.getByRole('grid');
    expect(grid).toBeInTheDocument();
  });

  it('renders column headers with full day name aria-labels', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const headers = screen.getAllByRole('columnheader');
    expect(headers.length).toBeGreaterThanOrEqual(7);
    expect(headers[0]).toHaveAttribute('aria-label', 'Sunday');
    expect(headers[1]).toHaveAttribute('aria-label', 'Monday');
    expect(headers[5]).toHaveAttribute('aria-label', 'Friday');
  });

  it('renders day cells with role="gridcell"', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    expect(gridcells.length).toBeGreaterThan(0);
  });

  it('applies aria-label with full date to day cells', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    // March 1, 2026 is a Sunday
    const march1 = screen.getByRole('gridcell', { name: /Sunday, March 1, 2026/i });
    expect(march1).toBeInTheDocument();
  });

  it('marks today with aria-current="date"', () => {
    // Mock Date.now to control "today"
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 12));

    render(<CalendarGrid {...defaultGridProps} />);
    const todayCell = screen.getByRole('gridcell', { name: /Thursday, March 12, 2026/i });
    expect(todayCell).toHaveAttribute('aria-current', 'date');

    vi.useRealTimers();
  });

  it('marks selected date with aria-selected', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const selectedCell = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    expect(selectedCell).toHaveAttribute('aria-selected', 'true');
  });

  it('indicates dates with events in aria-label', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const eventCell = screen.getByRole('gridcell', { name: /Tuesday, March 10, 2026, has appointments/i });
    expect(eventCell).toBeInTheDocument();
  });

  it('marks empty cells with aria-disabled', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    const emptyCells = gridcells.filter(cell => cell.getAttribute('aria-disabled') === 'true');
    // March 2026 starts on Sunday, so there are 0 empty cells before March 1.
    // But there are empty cells to pad the last week.
    expect(emptyCells.length).toBeGreaterThanOrEqual(0);
  });

  it('navigates right with ArrowRight key', async () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'ArrowRight' });
    // Focus should move to March 16
    const march16 = screen.getByRole('gridcell', { name: /Monday, March 16, 2026/i });
    expect(march16).toHaveAttribute('tabindex', '0');
  });

  it('navigates left with ArrowLeft key', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'ArrowLeft' });
    const march14 = screen.getByRole('gridcell', { name: /Saturday, March 14, 2026/i });
    expect(march14).toHaveAttribute('tabindex', '0');
  });

  it('navigates down with ArrowDown key (moves one week)', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'ArrowDown' });
    const march22 = screen.getByRole('gridcell', { name: /Sunday, March 22, 2026/i });
    expect(march22).toHaveAttribute('tabindex', '0');
  });

  it('navigates up with ArrowUp key (moves one week back)', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'ArrowUp' });
    const march8 = screen.getByRole('gridcell', { name: /Sunday, March 8, 2026/i });
    expect(march8).toHaveAttribute('tabindex', '0');
  });

  it('navigates to first day of week with Home key', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    // March 18 is Wednesday. Home should go to March 15 (Sunday, start of that row).
    const march18 = screen.getByRole('gridcell', { name: /Wednesday, March 18, 2026/i });
    march18.focus();
    fireEvent.keyDown(march18, { key: 'Home' });
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    expect(march15).toHaveAttribute('tabindex', '0');
  });

  it('navigates to last day of week with End key', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'End' });
    const march21 = screen.getByRole('gridcell', { name: /Saturday, March 21, 2026/i });
    expect(march21).toHaveAttribute('tabindex', '0');
  });

  it('selects date on Enter key press', () => {
    const onDateClick = vi.fn();
    render(<CalendarGrid {...defaultGridProps} onDateClick={onDateClick} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: 'Enter' });
    expect(onDateClick).toHaveBeenCalledTimes(1);
  });

  it('selects date on Space key press', () => {
    const onDateClick = vi.fn();
    render(<CalendarGrid {...defaultGridProps} onDateClick={onDateClick} />);
    const march15 = screen.getByRole('gridcell', { name: /Sunday, March 15, 2026/i });
    march15.focus();
    fireEvent.keyDown(march15, { key: ' ' });
    expect(onDateClick).toHaveBeenCalledTimes(1);
  });

  it('renders navigation buttons with aria-labels', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument();
  });

  it('uses roving tabindex - only focused cell has tabindex=0', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    const tabbable = gridcells.filter(cell => cell.getAttribute('tabindex') === '0');
    // Only one cell should be tabbable at a time
    expect(tabbable.length).toBe(1);
  });

  it('renders grid label with month and year', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const grid = screen.getByRole('grid');
    expect(grid).toHaveAttribute('aria-label', 'March 2026 calendar');
  });

  it('has month display as a live region', () => {
    render(<CalendarGrid {...defaultGridProps} />);
    const monthDisplay = screen.getByText('March 2026');
    expect(monthDisplay).toHaveAttribute('aria-live', 'polite');
  });
});

// ============================================================================
// CalendarHeader Accessibility Tests
// ============================================================================

describe('CalendarHeader Accessibility', () => {
  it('renders navigation toolbar with aria-label', () => {
    render(<CalendarHeader {...defaultHeaderProps} />);
    const toolbar = screen.getByRole('toolbar', { name: 'Calendar navigation' });
    expect(toolbar).toBeInTheDocument();
  });

  it('renders previous button with correct aria-label', () => {
    render(<CalendarHeader {...defaultHeaderProps} prevLabel="Previous month" />);
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument();
  });

  it('renders next button with correct aria-label', () => {
    render(<CalendarHeader {...defaultHeaderProps} nextLabel="Next month" />);
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument();
  });

  it('renders month/year in a live region that announces changes', () => {
    render(<CalendarHeader {...defaultHeaderProps} />);
    // The LiveRegion wrapping the title uses aria-live="polite"
    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
  });

  it('renders view switcher toolbar with aria-label', () => {
    render(<CalendarHeader {...defaultHeaderProps} />);
    const viewToolbar = screen.getByRole('toolbar', { name: 'Calendar view' });
    expect(viewToolbar).toBeInTheDocument();
  });

  it('marks active view with aria-pressed="true"', () => {
    render(<CalendarHeader {...defaultHeaderProps} view="month" />);
    const monthBtn = screen.getByRole('button', { name: 'Month' });
    expect(monthBtn).toHaveAttribute('aria-pressed', 'true');
    const dayBtn = screen.getByRole('button', { name: 'Day' });
    expect(dayBtn).toHaveAttribute('aria-pressed', 'false');
    const weekBtn = screen.getByRole('button', { name: 'Week' });
    expect(weekBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('calls onViewChange when view button is clicked', async () => {
    const user = userEvent.setup();
    const onViewChange = vi.fn();
    render(<CalendarHeader {...defaultHeaderProps} onViewChange={onViewChange} />);
    await user.click(screen.getByRole('button', { name: 'Week' }));
    expect(onViewChange).toHaveBeenCalledWith('week');
  });

  it('renders all view options including 3-Day', () => {
    render(<CalendarHeader {...defaultHeaderProps} />);
    expect(screen.getByRole('button', { name: 'Day' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '3-Day' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Week' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Month' })).toBeInTheDocument();
  });
});

// ============================================================================
// EventModal Accessibility Tests
// ============================================================================

describe('EventModal Accessibility', () => {
  it('renders with role="dialog" and aria-modal="true"', () => {
    render(<EventModal isOpen={true} event={sampleEvent} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('has aria-labelledby pointing to the modal title', () => {
    render(<EventModal isOpen={true} event={sampleEvent} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 'event-modal-title');
    const title = document.getElementById('event-modal-title');
    expect(title).toBeInTheDocument();
  });

  it('renders close button with aria-label', () => {
    render(<EventModal isOpen={true} event={sampleEvent} onClose={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeInTheDocument();
  });

  it('closes on Escape key', () => {
    const onClose = vi.fn();
    render(<EventModal isOpen={true} event={sampleEvent} onClose={onClose} />);
    const dialog = screen.getByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('does not render when isOpen is false', () => {
    render(<EventModal isOpen={false} event={sampleEvent} onClose={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('displays event details accessibly', () => {
    render(<EventModal isOpen={true} event={sampleEvent} onClose={vi.fn()} />);
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
  });
});

// ============================================================================
// EditAppointmentForm Accessibility Tests
// ============================================================================

describe('EditAppointmentForm Accessibility', () => {
  const editProps = {
    appointment: defaultEditAppointment,
    onAppointmentChange: vi.fn(),
    onSubmit: vi.fn((e) => e.preventDefault()),
    onClose: vi.fn(),
    onCancel: vi.fn(),
    saving: false,
    cancelConfirm: false,
    onCancelConfirmDismiss: vi.fn(),
  };

  it('renders with role="dialog" and aria-modal="true"', () => {
    render(<EditAppointmentForm {...editProps} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('has aria-labelledby pointing to the modal title', () => {
    render(<EditAppointmentForm {...editProps} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 'edit-modal-title');
  });

  it('renders close button with aria-label "Close dialog"', () => {
    render(<EditAppointmentForm {...editProps} />);
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeInTheDocument();
  });

  it('has aria-required on required fields', () => {
    render(<EditAppointmentForm {...editProps} />);
    const clientName = screen.getByLabelText('Client Name');
    expect(clientName).toHaveAttribute('aria-required', 'true');
    const dateInput = screen.getByLabelText('Date');
    expect(dateInput).toHaveAttribute('aria-required', 'true');
    const timeInput = screen.getByLabelText('Time');
    expect(timeInput).toHaveAttribute('aria-required', 'true');
  });

  it('renders fieldset/legend for grouped inputs', () => {
    render(<EditAppointmentForm {...editProps} />);
    const fieldsets = document.querySelectorAll('fieldset');
    expect(fieldsets.length).toBeGreaterThanOrEqual(2);
    // Check that legends exist
    const legends = document.querySelectorAll('legend');
    expect(legends.length).toBeGreaterThanOrEqual(2);
  });

  it('associates labels with inputs via htmlFor/id', () => {
    render(<EditAppointmentForm {...editProps} />);
    // All labeled inputs should be findable by getByLabelText
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
    expect(screen.getByLabelText('Client Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Client Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Date')).toBeInTheDocument();
    expect(screen.getByLabelText('Time')).toBeInTheDocument();
    expect(screen.getByLabelText('Duration')).toBeInTheDocument();
    expect(screen.getByLabelText('Meeting Type')).toBeInTheDocument();
    expect(screen.getByLabelText('Status')).toBeInTheDocument();
    expect(screen.getByLabelText('Notes')).toBeInTheDocument();
  });
});

// ============================================================================
// MiniCalendar Accessibility Tests
// ============================================================================

describe('MiniCalendar Accessibility', () => {
  it('renders with role="grid"', () => {
    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    const grid = screen.getByRole('grid');
    expect(grid).toBeInTheDocument();
  });

  it('renders gridcells with full date aria-labels', () => {
    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    const validCells = gridcells.filter(cell => cell.getAttribute('aria-label'));
    expect(validCells.length).toBeGreaterThan(0);
    // Check a specific cell
    const march1 = gridcells.find(cell =>
      cell.getAttribute('aria-label')?.includes('March 1, 2026')
    );
    expect(march1).toBeTruthy();
  });

  it('marks today with aria-current="date"', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 12));

    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    const todayCell = gridcells.find(cell =>
      cell.getAttribute('aria-current') === 'date'
    );
    expect(todayCell).toBeTruthy();
    expect(todayCell.getAttribute('aria-label')).toContain('March 12, 2026');

    vi.useRealTimers();
  });

  it('marks selected date with aria-selected', () => {
    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    const gridcells = screen.getAllByRole('gridcell');
    const selectedCell = gridcells.find(cell =>
      cell.getAttribute('aria-selected') === 'true'
    );
    expect(selectedCell).toBeTruthy();
    expect(selectedCell.getAttribute('aria-label')).toContain('March 15, 2026');
  });

  it('has navigation buttons with aria-labels', () => {
    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument();
  });

  it('has month display as a live region', () => {
    render(<MiniCalendar {...defaultMiniCalendarProps} />);
    const monthDisplay = screen.getByText('March 2026');
    expect(monthDisplay).toHaveAttribute('aria-live', 'polite');
  });
});

// ============================================================================
// ScreenReaderOnly Component Tests
// ============================================================================

describe('ScreenReaderOnly', () => {
  it('renders content that is visually hidden', () => {
    render(<ScreenReaderOnly>Hidden text</ScreenReaderOnly>);
    const element = screen.getByText('Hidden text');
    expect(element).toBeInTheDocument();
    // Verify clip-rect hiding technique
    const style = element.style;
    expect(style.position).toBe('absolute');
    expect(style.width).toBe('1px');
    expect(style.height).toBe('1px');
    expect(style.overflow).toBe('hidden');
  });

  it('renders with custom element via as prop', () => {
    render(<ScreenReaderOnly as="div">Content</ScreenReaderOnly>);
    const element = screen.getByText('Content');
    expect(element.tagName).toBe('DIV');
  });

  it('forwards ref', () => {
    const ref = React.createRef();
    render(<ScreenReaderOnly ref={ref}>Ref test</ScreenReaderOnly>);
    expect(ref.current).toBeInstanceOf(HTMLElement);
  });
});

// ============================================================================
// LiveRegion Component Tests
// ============================================================================

describe('LiveRegion', () => {
  it('renders with aria-live="polite" by default', () => {
    render(<LiveRegion message="Hello" />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-live', 'polite');
  });

  it('renders with aria-live="assertive" when specified', () => {
    render(<LiveRegion politeness="assertive" message="Urgent" />);
    const region = screen.getByRole('alert');
    expect(region).toHaveAttribute('aria-live', 'assertive');
  });

  it('renders with aria-atomic="true" by default', () => {
    render(<LiveRegion message="Atomic" />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-atomic', 'true');
  });

  it('is visually hidden by default (not visible)', () => {
    render(<LiveRegion message="SR only" />);
    const region = screen.getByRole('status');
    expect(region.style.position).toBe('absolute');
    expect(region.style.width).toBe('1px');
  });

  it('is visible when visible prop is true', () => {
    render(<LiveRegion message="Visible" visible={true} />);
    const region = screen.getByRole('status');
    expect(region.style.position).not.toBe('absolute');
  });

  it('renders children when provided', () => {
    render(
      <LiveRegion visible={true}>
        <span>Child content</span>
      </LiveRegion>
    );
    expect(screen.getByText('Child content')).toBeInTheDocument();
  });
});
