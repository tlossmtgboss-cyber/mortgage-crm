import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
  DURATION_OPTIONS,
  MEETING_TYPE_OPTIONS,
  STATUS_OPTIONS,
  EMPTY_APPOINTMENT_FORM,
} from '../calendarUtils';

// ============================================================================
// normalizeUTCDate
// ============================================================================

describe('normalizeUTCDate', () => {
  it('appends Z to a bare datetime string', () => {
    expect(normalizeUTCDate('2026-03-14T10:00:00')).toBe('2026-03-14T10:00:00Z');
  });

  it('does not modify a string that already ends with Z', () => {
    expect(normalizeUTCDate('2026-03-14T10:00:00Z')).toBe('2026-03-14T10:00:00Z');
  });

  it('does not modify a string with a + timezone offset', () => {
    expect(normalizeUTCDate('2026-03-14T10:00:00+05:00')).toBe('2026-03-14T10:00:00+05:00');
  });

  it('does not modify a string with a - timezone offset after position 10', () => {
    expect(normalizeUTCDate('2026-03-14T10:00:00-04:00')).toBe('2026-03-14T10:00:00-04:00');
  });

  it('returns null/undefined as-is', () => {
    expect(normalizeUTCDate(null)).toBe(null);
    expect(normalizeUTCDate(undefined)).toBe(undefined);
  });

  it('returns empty string as-is', () => {
    expect(normalizeUTCDate('')).toBe('');
  });

  it('handles date-only string (no T, has hyphens before pos 10)', () => {
    // '2026-03-14' has hyphens at positions 4 and 7, both before 10
    // The function checks for '-' after position 10, so it will add Z
    expect(normalizeUTCDate('2026-03-14')).toBe('2026-03-14Z');
  });

  it('handles datetime with milliseconds', () => {
    expect(normalizeUTCDate('2026-03-14T10:00:00.000')).toBe('2026-03-14T10:00:00.000Z');
  });
});

// ============================================================================
// formatDateForAPI
// ============================================================================

describe('formatDateForAPI', () => {
  it('formats a date as YYYY-MM-DD', () => {
    expect(formatDateForAPI(new Date(2026, 2, 14))).toBe('2026-03-14');
  });

  it('zero-pads single-digit months', () => {
    expect(formatDateForAPI(new Date(2026, 0, 5))).toBe('2026-01-05');
  });

  it('zero-pads single-digit days', () => {
    expect(formatDateForAPI(new Date(2026, 8, 3))).toBe('2026-09-03');
  });

  it('handles December (month 12)', () => {
    expect(formatDateForAPI(new Date(2026, 11, 25))).toBe('2026-12-25');
  });

  it('handles January 1st', () => {
    expect(formatDateForAPI(new Date(2026, 0, 1))).toBe('2026-01-01');
  });

  it('handles last day of year', () => {
    expect(formatDateForAPI(new Date(2026, 11, 31))).toBe('2026-12-31');
  });

  it('handles leap year date', () => {
    expect(formatDateForAPI(new Date(2028, 1, 29))).toBe('2028-02-29');
  });
});

// ============================================================================
// formatTime
// ============================================================================

describe('formatTime', () => {
  it('formats a UTC ISO string to local time', () => {
    // This tests that the function returns a string matching time format
    const result = formatTime('2026-03-14T15:30:00Z');
    expect(result).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it('formats a bare ISO string (no Z) by appending Z', () => {
    const result = formatTime('2026-03-14T15:30:00');
    expect(result).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it('handles midnight UTC (converts to local time)', () => {
    // normalizeUTCDate treats the input as UTC; toLocaleTimeString converts to local tz
    // We just verify it returns a valid time string rather than asserting a specific time
    // since the test runner's timezone may vary
    const result = formatTime('2026-03-14T00:00:00Z');
    expect(result).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it('handles noon UTC (converts to local time)', () => {
    const result = formatTime('2026-03-14T12:00:00Z');
    expect(result).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });
});

// ============================================================================
// formatDuration
// ============================================================================

describe('formatDuration', () => {
  it('returns minutes for durations under 1 hour', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T10:30:00')).toBe('30m');
  });

  it('returns "1h" for exactly 60 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T11:00:00')).toBe('1h');
  });

  it('returns "1h 30m" for 90 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T11:30:00')).toBe('1h 30m');
  });

  it('returns "2h" for 120 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T12:00:00')).toBe('2h');
  });

  it('returns "15m" for 15 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T10:15:00')).toBe('15m');
  });

  it('returns "45m" for 45 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T10:45:00')).toBe('45m');
  });

  it('returns "2h 15m" for 135 minutes', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T12:15:00')).toBe('2h 15m');
  });

  it('handles durations spanning midnight', () => {
    const result = formatDuration('2026-03-14T23:00:00', '2026-03-15T01:00:00');
    expect(result).toBe('2h');
  });

  it('returns "0m" for zero-length duration', () => {
    expect(formatDuration('2026-03-14T10:00:00', '2026-03-14T10:00:00')).toBe('0m');
  });

  it('handles UTC strings with Z suffix', () => {
    expect(formatDuration('2026-03-14T10:00:00Z', '2026-03-14T10:30:00Z')).toBe('30m');
  });
});

// ============================================================================
// getMeetingModeIcon
// ============================================================================

describe('getMeetingModeIcon', () => {
  it('returns camera icon for VIDEO', () => {
    expect(getMeetingModeIcon('VIDEO')).toBe('\u{1F4F9}');
  });

  it('returns phone icon for PHONE', () => {
    expect(getMeetingModeIcon('PHONE')).toBe('\u{1F4DE}');
  });

  it('returns person icon for IN_PERSON', () => {
    expect(getMeetingModeIcon('IN_PERSON')).toBe('\u{1F464}');
  });

  it('returns calendar icon for unknown mode', () => {
    expect(getMeetingModeIcon('UNKNOWN')).toBe('\u{1F4C5}');
  });

  it('is case-insensitive', () => {
    expect(getMeetingModeIcon('video')).toBe('\u{1F4F9}');
    expect(getMeetingModeIcon('phone')).toBe('\u{1F4DE}');
    expect(getMeetingModeIcon('in_person')).toBe('\u{1F464}');
  });

  it('handles null/undefined input', () => {
    expect(getMeetingModeIcon(null)).toBe('\u{1F4C5}');
    expect(getMeetingModeIcon(undefined)).toBe('\u{1F4C5}');
  });

  it('handles empty string', () => {
    expect(getMeetingModeIcon('')).toBe('\u{1F4C5}');
  });
});

// ============================================================================
// getMeetingModeColor
// ============================================================================

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

  it('returns gray for unknown mode', () => {
    expect(getMeetingModeColor('UNKNOWN')).toBe('#6b7280');
  });

  it('is case-insensitive', () => {
    expect(getMeetingModeColor('video')).toBe('#2563eb');
    expect(getMeetingModeColor('phone')).toBe('#2D7A52');
    expect(getMeetingModeColor('in_person')).toBe('#dc2626');
  });

  it('handles null/undefined input', () => {
    expect(getMeetingModeColor(null)).toBe('#6b7280');
    expect(getMeetingModeColor(undefined)).toBe('#6b7280');
  });

  it('handles empty string', () => {
    expect(getMeetingModeColor('')).toBe('#6b7280');
  });
});

// ============================================================================
// isToday
// ============================================================================

describe('isToday', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 14, 10, 0, 0));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns true for today', () => {
    expect(isToday(new Date(2026, 2, 14))).toBe(true);
  });

  it('returns true for today at different time', () => {
    expect(isToday(new Date(2026, 2, 14, 23, 59, 59))).toBe(true);
  });

  it('returns false for yesterday', () => {
    expect(isToday(new Date(2026, 2, 13))).toBe(false);
  });

  it('returns false for tomorrow', () => {
    expect(isToday(new Date(2026, 2, 15))).toBe(false);
  });

  it('returns false for null', () => {
    expect(isToday(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isToday(undefined)).toBe(false);
  });

  it('returns true for midnight of today', () => {
    expect(isToday(new Date(2026, 2, 14, 0, 0, 0))).toBe(true);
  });
});

// ============================================================================
// Exported constants
// ============================================================================

describe('Exported constants', () => {
  it('MONTH_NAMES has 12 entries', () => {
    expect(MONTH_NAMES).toHaveLength(12);
    expect(MONTH_NAMES[0]).toBe('January');
    expect(MONTH_NAMES[11]).toBe('December');
  });

  it('DAY_NAMES has 7 entries starting with S (Sunday)', () => {
    expect(DAY_NAMES).toHaveLength(7);
    expect(DAY_NAMES[0]).toBe('S');
    expect(DAY_NAMES[6]).toBe('S');
  });

  it('DURATION_OPTIONS contains expected values', () => {
    expect(DURATION_OPTIONS).toHaveLength(6);
    expect(DURATION_OPTIONS[0]).toEqual({ value: '15', label: '15 minutes' });
    expect(DURATION_OPTIONS[3]).toEqual({ value: '60', label: '1 hour' });
  });

  it('MEETING_TYPE_OPTIONS contains 3 options', () => {
    expect(MEETING_TYPE_OPTIONS).toHaveLength(3);
    const values = MEETING_TYPE_OPTIONS.map(o => o.value);
    expect(values).toContain('PHONE');
    expect(values).toContain('VIDEO');
    expect(values).toContain('IN_PERSON');
  });

  it('STATUS_OPTIONS contains expected statuses', () => {
    expect(STATUS_OPTIONS).toHaveLength(4);
    const values = STATUS_OPTIONS.map(o => o.value);
    expect(values).toContain('booked');
    expect(values).toContain('confirmed');
    expect(values).toContain('completed');
    expect(values).toContain('no_show');
  });

  it('EMPTY_APPOINTMENT_FORM has correct default values', () => {
    expect(EMPTY_APPOINTMENT_FORM.title).toBe('');
    expect(EMPTY_APPOINTMENT_FORM.attendee_name).toBe('');
    expect(EMPTY_APPOINTMENT_FORM.attendee_email).toBe('');
    expect(EMPTY_APPOINTMENT_FORM.date).toBe('');
    expect(EMPTY_APPOINTMENT_FORM.time).toBe('10:00');
    expect(EMPTY_APPOINTMENT_FORM.duration).toBe('30');
    expect(EMPTY_APPOINTMENT_FORM.meeting_mode).toBe('PHONE');
    expect(EMPTY_APPOINTMENT_FORM.notes).toBe('');
  });
});
