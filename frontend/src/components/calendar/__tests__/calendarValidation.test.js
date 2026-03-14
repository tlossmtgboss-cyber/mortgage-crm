import { describe, it, expect } from 'vitest';
import {
  validateWorkingHours,
  validateBookingSlug,
  validateHexColor,
  validateNotifications,
} from '../calendarValidation';

// ============================================================================
// validateWorkingHours
// ============================================================================

describe('validateWorkingHours', () => {
  // ---------- Valid cases ----------

  it('returns valid for a standard Mon-Fri 9-5 schedule', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      tuesday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      wednesday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      thursday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      friday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      saturday: { enabled: false, blocks: [{ start: '09:00', end: '17:00' }] },
      sunday: { enabled: false, blocks: [{ start: '09:00', end: '17:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('returns valid with a single enabled day', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '08:00', end: '12:00' }] },
      tuesday: { enabled: false, blocks: [] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(true);
  });

  it('returns valid with multiple non-overlapping blocks in one day', () => {
    const schedule = {
      monday: {
        enabled: true,
        blocks: [
          { start: '08:00', end: '12:00' },
          { start: '13:00', end: '17:00' },
        ],
      },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('returns valid with blocks that share an exact boundary (12:00-13:00)', () => {
    const schedule = {
      monday: {
        enabled: true,
        blocks: [
          { start: '08:00', end: '12:00' },
          { start: '12:00', end: '17:00' },
        ],
      },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(true);
  });

  // ---------- At least one day ----------

  it('returns error when no days are enabled', () => {
    const schedule = {
      monday: { enabled: false, blocks: [{ start: '09:00', end: '17:00' }] },
      tuesday: { enabled: false, blocks: [{ start: '09:00', end: '17:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('At least one day must be enabled');
  });

  // ---------- End after start ----------

  it('returns error when end time equals start time', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '09:00', end: '09:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('end time must be after start time'))).toBe(true);
  });

  it('returns error when end time is before start time', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '17:00', end: '09:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('end time must be after start time'))).toBe(true);
  });

  // ---------- Overlapping blocks ----------

  it('returns error when blocks overlap within the same day', () => {
    const schedule = {
      monday: {
        enabled: true,
        blocks: [
          { start: '08:00', end: '13:00' },
          { start: '12:00', end: '17:00' },
        ],
      },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('overlap'))).toBe(true);
  });

  it('detects overlap even when blocks are given out of order', () => {
    const schedule = {
      monday: {
        enabled: true,
        blocks: [
          { start: '12:00', end: '17:00' },
          { start: '08:00', end: '13:00' },
        ],
      },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('overlap'))).toBe(true);
  });

  // ---------- Edge cases ----------

  it('returns error for null schedule', () => {
    const result = validateWorkingHours(null);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('Schedule data is required');
  });

  it('returns error for undefined schedule', () => {
    const result = validateWorkingHours(undefined);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('Schedule data is required');
  });

  it('returns error for empty object', () => {
    const result = validateWorkingHours({});
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('Schedule data is required');
  });

  it('returns error when enabled day has no blocks', () => {
    const schedule = {
      monday: { enabled: true, blocks: [] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('at least one time block'))).toBe(true);
  });

  it('returns error when block is missing start time', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: null, end: '17:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('missing start or end'))).toBe(true);
  });

  it('returns error for invalid time format', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: 'abc', end: '17:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('invalid time format'))).toBe(true);
  });

  it('ignores disabled days even if they have invalid blocks', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '09:00', end: '17:00' }] },
      tuesday: { enabled: false, blocks: [{ start: '25:00', end: '01:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(true);
  });

  it('returns error for boundary time 24:00', () => {
    const schedule = {
      monday: { enabled: true, blocks: [{ start: '09:00', end: '24:00' }] },
    };
    const result = validateWorkingHours(schedule);
    expect(result.valid).toBe(false);
  });
});

// ============================================================================
// validateBookingSlug
// ============================================================================

describe('validateBookingSlug', () => {
  // ---------- Valid cases ----------

  it('accepts a simple lowercase slug', () => {
    const result = validateBookingSlug('my-calendar');
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('accepts alphanumeric slug', () => {
    expect(validateBookingSlug('calendar123').valid).toBe(true);
  });

  it('accepts slug with hyphens in the middle', () => {
    expect(validateBookingSlug('my-booking-page').valid).toBe(true);
  });

  it('accepts minimum length slug (3 characters)', () => {
    expect(validateBookingSlug('abc').valid).toBe(true);
  });

  it('accepts 60-character slug', () => {
    const slug = 'a'.repeat(60);
    expect(validateBookingSlug(slug).valid).toBe(true);
  });

  // ---------- Invalid cases ----------

  it('rejects uppercase characters', () => {
    const result = validateBookingSlug('My-Calendar');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('lowercase'))).toBe(true);
  });

  it('rejects spaces', () => {
    const result = validateBookingSlug('my calendar');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('lowercase letters, numbers, and hyphens'))).toBe(true);
  });

  it('rejects special characters', () => {
    const result = validateBookingSlug('my_calendar!');
    expect(result.valid).toBe(false);
  });

  it('rejects slug starting with a hyphen', () => {
    const result = validateBookingSlug('-my-calendar');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('not start or end with a hyphen'))).toBe(true);
  });

  it('rejects slug ending with a hyphen', () => {
    const result = validateBookingSlug('my-calendar-');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('not start or end with a hyphen'))).toBe(true);
  });

  it('rejects consecutive hyphens', () => {
    const result = validateBookingSlug('my--calendar');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('consecutive hyphens'))).toBe(true);
  });

  it('rejects too-short slug (1 character)', () => {
    const result = validateBookingSlug('a');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('at least 3'))).toBe(true);
  });

  it('rejects too-long slug (61 characters)', () => {
    const slug = 'a'.repeat(61);
    const result = validateBookingSlug(slug);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('60 characters'))).toBe(true);
  });

  it('rejects empty string', () => {
    const result = validateBookingSlug('');
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('Booking slug is required');
  });

  it('rejects null', () => {
    const result = validateBookingSlug(null);
    expect(result.valid).toBe(false);
  });

  it('rejects undefined', () => {
    const result = validateBookingSlug(undefined);
    expect(result.valid).toBe(false);
  });
});

// ============================================================================
// validateHexColor
// ============================================================================

describe('validateHexColor', () => {
  // ---------- Valid cases ----------

  it('accepts 6-digit hex color', () => {
    expect(validateHexColor('#218D8D').valid).toBe(true);
  });

  it('accepts 3-digit hex color', () => {
    expect(validateHexColor('#abc').valid).toBe(true);
  });

  it('accepts 8-digit hex color (with alpha)', () => {
    expect(validateHexColor('#218D8DFF').valid).toBe(true);
  });

  it('accepts lowercase hex', () => {
    expect(validateHexColor('#ff0000').valid).toBe(true);
  });

  it('accepts uppercase hex', () => {
    expect(validateHexColor('#FF0000').valid).toBe(true);
  });

  it('accepts mixed case hex', () => {
    expect(validateHexColor('#aAbBcC').valid).toBe(true);
  });

  // ---------- Invalid cases ----------

  it('rejects color without # prefix', () => {
    const result = validateHexColor('218D8D');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('start with #'))).toBe(true);
  });

  it('rejects invalid hex characters', () => {
    const result = validateHexColor('#gggggg');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('valid hex characters'))).toBe(true);
  });

  it('rejects wrong length (4 digits after #)', () => {
    const result = validateHexColor('#1234');
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('3, 6, or 8 hex digits'))).toBe(true);
  });

  it('rejects wrong length (5 digits after #)', () => {
    const result = validateHexColor('#12345');
    expect(result.valid).toBe(false);
  });

  it('rejects empty string', () => {
    const result = validateHexColor('');
    expect(result.valid).toBe(false);
    expect(result.errors).toContain('Color value is required');
  });

  it('rejects null', () => {
    const result = validateHexColor(null);
    expect(result.valid).toBe(false);
  });

  it('rejects just the # symbol', () => {
    const result = validateHexColor('#');
    expect(result.valid).toBe(false);
  });
});

// ============================================================================
// validateNotifications
// ============================================================================

describe('validateNotifications', () => {
  // ---------- Valid cases ----------

  it('returns valid for null settings (notifications are optional)', () => {
    expect(validateNotifications(null).valid).toBe(true);
  });

  it('returns valid for undefined settings', () => {
    expect(validateNotifications(undefined).valid).toBe(true);
  });

  it('returns valid for empty object (no reminders configured)', () => {
    expect(validateNotifications({}).valid).toBe(true);
  });

  it('returns valid with email reminders and no quiet hours', () => {
    const result = validateNotifications({
      email_reminder_24h: true,
      email_reminder_2h: true,
    });
    expect(result.valid).toBe(true);
  });

  it('returns valid with SMS reminders', () => {
    const result = validateNotifications({
      sms_reminder_24h: true,
    });
    expect(result.valid).toBe(true);
  });

  it('returns valid with quiet hours properly configured', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: '22:00',
      quiet_hours_end: '23:00',
      email_reminder_24h: true,
    });
    expect(result.valid).toBe(true);
  });

  // ---------- Quiet hours errors ----------

  it('returns error when quiet hours enabled without start time', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: null,
      quiet_hours_end: '08:00',
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('start and end times are required'))).toBe(true);
  });

  it('returns error when quiet hours enabled without end time', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: '22:00',
      quiet_hours_end: null,
    });
    expect(result.valid).toBe(false);
  });

  it('returns error when quiet hours end is before start', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: '22:00',
      quiet_hours_end: '20:00',
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('end time must be after start time'))).toBe(true);
  });

  it('returns error when quiet hours end equals start', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: '22:00',
      quiet_hours_end: '22:00',
    });
    expect(result.valid).toBe(false);
  });

  it('returns error for invalid quiet hours time format', () => {
    const result = validateNotifications({
      quiet_hours_enabled: true,
      quiet_hours_start: 'abc',
      quiet_hours_end: '08:00',
    });
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.includes('invalid time format'))).toBe(true);
  });

  // ---------- Channel checks ----------

  it('passes when no reminders are enabled (no channel needed)', () => {
    const result = validateNotifications({
      email_reminder_24h: false,
      sms_reminder_24h: false,
    });
    expect(result.valid).toBe(true);
  });

  it('no error when quiet hours are disabled (even with invalid times)', () => {
    const result = validateNotifications({
      quiet_hours_enabled: false,
      quiet_hours_start: 'abc',
      quiet_hours_end: 'xyz',
      email_reminder_24h: true,
    });
    expect(result.valid).toBe(true);
  });
});
