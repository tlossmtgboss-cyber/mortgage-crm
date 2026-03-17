/**
 * Timezone utility for consistent timezone handling across calendar components.
 *
 * The configured timezone is loaded from:
 *   1. localStorage cache (schedulerTimezone) -- for immediate access
 *   2. Smart Scheduler Settings API -- the authoritative source
 *   3. Fallback: Intl.DateTimeFormat().resolvedOptions().timeZone (browser default)
 *
 * CalendarSettings writes the timezone to the API on save.
 * This module caches it in localStorage so other components can read it
 * synchronously without waiting for an API call.
 */

import { API_BASE_URL } from '../services/api';

const TIMEZONE_STORAGE_KEY = 'schedulerTimezone';
const TIMEZONE_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const TIMEZONE_LAST_FETCH_KEY = 'schedulerTimezoneLastFetch';

/**
 * Get the user's configured timezone synchronously.
 * Reads from localStorage cache first, falls back to browser timezone.
 * Call refreshTimezoneCache() on app init or when settings change to keep it fresh.
 */
export function getUserTimezone() {
  try {
    const cached = localStorage.getItem(TIMEZONE_STORAGE_KEY);
    if (cached && isValidTimezone(cached)) {
      return cached;
    }
  } catch {
    // localStorage unavailable
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Set the timezone in localStorage cache.
 * Called by CalendarSettings when the user saves, and by refreshTimezoneCache.
 */
export function setUserTimezone(timezone) {
  try {
    if (timezone && isValidTimezone(timezone)) {
      localStorage.setItem(TIMEZONE_STORAGE_KEY, timezone);
      localStorage.setItem(TIMEZONE_LAST_FETCH_KEY, String(Date.now()));
    }
  } catch {
    // localStorage unavailable
  }
}

/**
 * Validate that a string is a recognized IANA timezone identifier.
 */
function isValidTimezone(tz) {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

/**
 * Fetch timezone from the API and update the localStorage cache.
 * Safe to call on app boot -- will not throw.
 */
export async function refreshTimezoneCache() {
  try {
    // Skip if recently fetched
    const lastFetch = parseInt(localStorage.getItem(TIMEZONE_LAST_FETCH_KEY) || '0', 10);
    if (Date.now() - lastFetch < TIMEZONE_CACHE_TTL_MS) {
      return getUserTimezone();
    }
  } catch {
    // continue
  }

  try {
    const token = localStorage.getItem('token');
    if (!token) return getUserTimezone();

    const response = await fetch(`${API_BASE_URL}/api/v1/smart-scheduler-settings`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      const data = await response.json();
      const tz = data?.data?.timezone;
      if (tz) {
        setUserTimezone(tz);
        return tz;
      }
    }
  } catch {
    // API unavailable -- keep existing cache
  }

  return getUserTimezone();
}

// ---------------------------------------------------------------------------
// Date formatting and conversion helpers
// ---------------------------------------------------------------------------

/**
 * Normalize a UTC date string from the backend.
 * Backend often returns datetime strings without a Z suffix -- this adds it
 * so the browser's Date constructor interprets them as UTC.
 */
export function normalizeUTCDate(dateString) {
  if (!dateString) return dateString;
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    return dateString + 'Z';
  }
  return dateString;
}

/**
 * Format a date/datetime in the user's configured timezone.
 *
 * @param {Date|string} date - A Date object or ISO string (UTC)
 * @param {Intl.DateTimeFormatOptions} options - Intl formatting options
 *   (e.g. { hour: 'numeric', minute: '2-digit', hour12: true })
 * @returns {string} Formatted date string in the user's timezone
 */
export function formatInUserTimezone(date, options = {}) {
  const d = date instanceof Date ? date : new Date(normalizeUTCDate(date));
  const tz = getUserTimezone();
  return d.toLocaleString('en-US', { ...options, timeZone: tz });
}

/**
 * Format just the time portion of a UTC date string in the user's timezone.
 *
 * @param {string} dateString - ISO datetime string from backend
 * @returns {string} e.g. "2:30 PM"
 */
export function formatTimeInUserTimezone(dateString) {
  return formatInUserTimezone(dateString, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a date (no time) in the user's timezone.
 *
 * @param {Date|string} date
 * @param {object} options - Additional Intl options
 * @returns {string} e.g. "Mon, Mar 9"
 */
export function formatDateInUserTimezone(date, options = {}) {
  return formatInUserTimezone(date, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...options,
  });
}

/**
 * Convert a UTC date to the user's timezone and return a Date-like object
 * with the correct local year/month/day/hour values.
 *
 * This creates a new Date whose UTC values represent the wall-clock time
 * in the user's configured timezone.  Useful for comparisons like
 * "is this event on the same calendar day as selectedDate?"
 *
 * @param {Date|string} utcDate
 * @returns {Date}
 */
export function toUserTimezone(utcDate) {
  const d = utcDate instanceof Date ? utcDate : new Date(normalizeUTCDate(utcDate));
  const tz = getUserTimezone();

  // Use Intl to get the parts in the target timezone
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);

  const get = (type) => {
    const part = parts.find(p => p.type === type);
    return part ? parseInt(part.value, 10) : 0;
  };

  return new Date(
    get('year'),
    get('month') - 1,
    get('day'),
    get('hour') === 24 ? 0 : get('hour'),
    get('minute'),
    get('second')
  );
}

/**
 * Convert a "local" date/time (as entered by the user in their configured
 * timezone) to a UTC ISO string suitable for sending to the API.
 *
 * @param {Date|string} localDate - Date representing wall-clock time in user's tz.
 *   If a string like "2026-03-09T14:00", it is interpreted as being in the
 *   user's configured timezone.
 * @returns {string} ISO 8601 UTC string (e.g. "2026-03-09T20:00:00.000Z")
 */
export function fromUserTimezone(localDate) {
  const tz = getUserTimezone();

  if (typeof localDate === 'string') {
    // Build an Intl formatter to figure out the UTC offset for this moment
    // in the target timezone, then construct the correct Date.
    //
    // Strategy: parse the string as-is into a Date (interpreted as local browser time),
    // then adjust for the difference between browser TZ and configured TZ.
    const naive = new Date(localDate);
    if (isNaN(naive.getTime())) {
      return localDate; // can't parse, return as-is
    }
    return convertNaiveToTimezone(naive, tz).toISOString();
  }

  if (localDate instanceof Date) {
    // If the Date was constructed from form inputs (e.g. new Date("2026-03-09T14:00")),
    // the browser already interpreted it in the browser's local timezone.
    // We need to re-interpret it as if it were in the user's configured timezone.
    return convertNaiveToTimezone(localDate, tz).toISOString();
  }

  return new Date(localDate).toISOString();
}

/**
 * Given a Date whose local-time fields (getFullYear, getMonth, getDate, getHours, etc.)
 * represent wall-clock time in the BROWSER's timezone, re-interpret those same
 * wall-clock values as if they were in `targetTz` and return the corresponding UTC Date.
 *
 * For example, if the browser is in America/New_York and the user's configured TZ is
 * America/Chicago, and the Date says 2:00 PM (NY), we want to produce the UTC instant
 * corresponding to 2:00 PM Chicago time (which is 8:00 PM UTC, not 7:00 PM UTC).
 */
function convertNaiveToTimezone(date, targetTz) {
  // Step 1: extract the wall-clock components from the Date
  const year = date.getFullYear();
  const month = date.getMonth(); // 0-indexed
  const day = date.getDate();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();

  // Step 2: format those same components in the target timezone to find the offset
  // We construct a reference UTC date and see what the target TZ shows.
  // But it's simpler to use the inverse approach: create a UTC date from the components
  // and then adjust.

  // Create a Date in UTC with the same wall-clock values
  const utcEquivalent = new Date(Date.UTC(year, month, day, hours, minutes, seconds));

  // Find out what offset the target timezone has at this UTC instant
  const targetLocal = new Intl.DateTimeFormat('en-US', {
    timeZone: targetTz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(utcEquivalent);

  const get = (type) => {
    const part = targetLocal.find(p => p.type === type);
    return part ? parseInt(part.value, 10) : 0;
  };

  const tzHour = get('hour') === 24 ? 0 : get('hour');
  const tzMin = get('minute');

  // The difference between what we wanted (hours:minutes) and what the tz shows
  // tells us the offset adjustment needed.
  const wantedMinutes = hours * 60 + minutes;
  const gotMinutes = tzHour * 60 + tzMin;
  let diffMinutes = wantedMinutes - gotMinutes;

  // Handle day boundary wrap (e.g., wanted 23:00, got 01:00 next day means diff = -120 but should be +1320)
  if (diffMinutes > 720) diffMinutes -= 1440;
  if (diffMinutes < -720) diffMinutes += 1440;

  // Adjust the UTC equivalent by the difference
  return new Date(utcEquivalent.getTime() + diffMinutes * 60000);
}

/**
 * Get a date string (YYYY-MM-DD) representing "today" in the user's timezone.
 */
export function getTodayInUserTimezone() {
  const now = new Date();
  const tz = getUserTimezone();
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(now);
  return parts; // en-CA uses YYYY-MM-DD format
}

/**
 * Check whether a UTC date string falls on the same calendar day as a local Date
 * in the user's configured timezone.
 *
 * @param {string} utcDateString - ISO date string from backend
 * @param {Date} localDate - A local Date to compare against
 * @returns {boolean}
 */
export function isSameDayInUserTimezone(utcDateString, localDate) {
  const converted = toUserTimezone(utcDateString);
  return (
    converted.getFullYear() === localDate.getFullYear() &&
    converted.getMonth() === localDate.getMonth() &&
    converted.getDate() === localDate.getDate()
  );
}

/**
 * Get a short timezone abbreviation for display (e.g., "CT", "ET", "PT").
 */
export function getTimezoneAbbreviation() {
  const tz = getUserTimezone();
  try {
    const formatted = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'short',
    }).format(new Date());
    // Extract the timezone abbreviation (last word)
    const parts = formatted.split(' ');
    return parts[parts.length - 1]; // e.g., "CDT", "CST", "EST"
  } catch {
    return '';
  }
}
