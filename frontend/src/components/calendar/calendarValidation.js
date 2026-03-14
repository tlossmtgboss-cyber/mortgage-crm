/**
 * Perennia AI - Calendar Validation Utilities
 *
 * Pure validation functions for calendar setup data.
 * Used by setup wizard steps and calendar settings forms.
 */

// ============================================================================
// Working Hours Validation
// ============================================================================

/**
 * Parse "HH:MM" to total minutes since midnight.
 */
function timeToMinutes(time) {
  if (!time || typeof time !== 'string') return NaN;
  const parts = time.split(':');
  if (parts.length !== 2) return NaN;
  const [h, m] = parts.map(Number);
  if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) return NaN;
  return h * 60 + m;
}

/**
 * Validate working hours configuration.
 *
 * Rules:
 *   - At least one day must be enabled
 *   - End time must be after start time for every block
 *   - Time blocks within the same day must not overlap
 *
 * @param {Object} schedule - Keys are day names, values are { enabled, blocks: [{ start, end }] }
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateWorkingHours(schedule) {
  const errors = [];

  if (!schedule || typeof schedule !== 'object') {
    return { valid: false, errors: ['Schedule data is required'] };
  }

  const days = Object.keys(schedule);
  if (days.length === 0) {
    return { valid: false, errors: ['Schedule data is required'] };
  }

  const enabledDays = days.filter(d => schedule[d] && schedule[d].enabled);

  if (enabledDays.length === 0) {
    errors.push('At least one day must be enabled');
  }

  for (const day of enabledDays) {
    const dayData = schedule[day];
    const blocks = dayData.blocks;

    if (!blocks || !Array.isArray(blocks) || blocks.length === 0) {
      errors.push(`${day}: at least one time block is required`);
      continue;
    }

    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i];
      if (!block || !block.start || !block.end) {
        errors.push(`${day}: block ${i + 1} is missing start or end time`);
        continue;
      }

      const startMin = timeToMinutes(block.start);
      const endMin = timeToMinutes(block.end);

      if (isNaN(startMin) || isNaN(endMin)) {
        errors.push(`${day}: block ${i + 1} has invalid time format`);
        continue;
      }

      if (endMin <= startMin) {
        errors.push(`${day}: block ${i + 1} end time must be after start time`);
      }
    }

    // Check for overlapping blocks
    if (blocks.length > 1) {
      const sorted = blocks
        .map((b, idx) => ({ ...b, idx }))
        .filter(b => b.start && b.end)
        .sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));

      for (let i = 0; i < sorted.length - 1; i++) {
        const currentEnd = timeToMinutes(sorted[i].end);
        const nextStart = timeToMinutes(sorted[i + 1].start);

        if (currentEnd > nextStart) {
          errors.push(`${day}: time blocks overlap`);
          break;
        }
      }
    }
  }

  return { valid: errors.length === 0, errors };
}

// ============================================================================
// Booking Slug Validation
// ============================================================================

/**
 * Validate a booking page slug.
 *
 * Rules:
 *   - Must be lowercase
 *   - Only alphanumeric characters and hyphens allowed
 *   - Must not start or end with a hyphen
 *   - Must be between 3 and 60 characters
 *   - No consecutive hyphens
 *
 * @param {string} slug
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateBookingSlug(slug) {
  const errors = [];

  if (!slug || typeof slug !== 'string') {
    return { valid: false, errors: ['Booking slug is required'] };
  }

  if (slug.length < 3) {
    errors.push('Slug must be at least 3 characters');
  }

  if (slug.length > 60) {
    errors.push('Slug must be 60 characters or fewer');
  }

  if (slug !== slug.toLowerCase()) {
    errors.push('Slug must be lowercase');
  }

  if (!/^[a-z0-9-]+$/.test(slug)) {
    errors.push('Slug may only contain lowercase letters, numbers, and hyphens');
  }

  if (slug.startsWith('-') || slug.endsWith('-')) {
    errors.push('Slug must not start or end with a hyphen');
  }

  if (/--/.test(slug)) {
    errors.push('Slug must not contain consecutive hyphens');
  }

  return { valid: errors.length === 0, errors };
}

// ============================================================================
// Hex Color Validation
// ============================================================================

/**
 * Validate a hex color code.
 *
 * Accepts:
 *   - 3-digit hex: #abc
 *   - 6-digit hex: #aabbcc
 *   - 8-digit hex with alpha: #aabbccdd
 *   - Case insensitive
 *
 * @param {string} color
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateHexColor(color) {
  const errors = [];

  if (!color || typeof color !== 'string') {
    return { valid: false, errors: ['Color value is required'] };
  }

  if (!color.startsWith('#')) {
    errors.push('Color must start with #');
  }

  const hex = color.slice(1);
  if (![3, 6, 8].includes(hex.length)) {
    errors.push('Color must be 3, 6, or 8 hex digits after #');
  }

  if (!/^#[0-9a-fA-F]+$/.test(color)) {
    errors.push('Color must contain only valid hex characters (0-9, a-f)');
  }

  return { valid: errors.length === 0, errors };
}

// ============================================================================
// Notifications Validation
// ============================================================================

/**
 * Validate notification settings.
 *
 * Rules:
 *   - If quiet hours are enabled, end must be after start
 *   - At least one channel (email or sms) should be configured if any reminders are active
 *
 * @param {Object} settings
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateNotifications(settings) {
  const errors = [];

  if (!settings || typeof settings !== 'object') {
    return { valid: true, errors: [] }; // Notifications are optional
  }

  // Check quiet hours
  if (settings.quiet_hours_enabled) {
    if (!settings.quiet_hours_start || !settings.quiet_hours_end) {
      errors.push('Quiet hours start and end times are required when enabled');
    } else {
      const startMin = timeToMinutes(settings.quiet_hours_start);
      const endMin = timeToMinutes(settings.quiet_hours_end);

      if (isNaN(startMin) || isNaN(endMin)) {
        errors.push('Quiet hours have invalid time format');
      } else if (endMin <= startMin) {
        errors.push('Quiet hours end time must be after start time');
      }
    }
  }

  // Check channels: if any reminders are enabled, at least one channel should be on
  const hasAnyReminder =
    settings.email_reminder_24h ||
    settings.email_reminder_2h ||
    settings.email_reminder_15m ||
    settings.sms_reminder_24h ||
    settings.sms_reminder_2h ||
    settings.sms_reminder_15m;

  if (hasAnyReminder) {
    const hasEmailChannel =
      settings.email_reminder_24h ||
      settings.email_reminder_2h ||
      settings.email_reminder_15m;
    const hasSmsChannel =
      settings.sms_reminder_24h ||
      settings.sms_reminder_2h ||
      settings.sms_reminder_15m;

    if (!hasEmailChannel && !hasSmsChannel) {
      errors.push('At least one notification channel must be configured');
    }
  }

  return { valid: errors.length === 0, errors };
}
