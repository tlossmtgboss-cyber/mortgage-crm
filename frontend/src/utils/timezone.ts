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
import { getToken } from '../utils/tokenStore';

const TIMEZONE_STORAGE_KEY = 'schedulerTimezone';
const TIMEZONE_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const TIMEZONE_LAST_FETCH_KEY = 'schedulerTimezoneLastFetch';

/**
 * Get the user's configured timezone synchronously.
 * Reads from localStorage cache first, falls back to browser timezone.
 * Call refreshTimezoneCache() on app init or when settings change to keep it fresh.
 */
export function getUserTimezone(): string {
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
export function setUserTimezone(timezone: string): void {
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
function isValidTimezone(tz: string): boolean {
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
export async function refreshTimezoneCache(): Promise<string> {
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
    const token = getToken();
    if (!token) return getUserTimezone();

    const response = await fetch(`${API_BASE_URL}/api/v1/smart-scheduler-settings`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (response.ok) {
      const data = await response.json();
      const tz = data?.data?.timezone as string | undefined;
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
export function normalizeUTCDate(dateString: string): string {
  if (!dateString) return dateString;
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    return dateString + 'Z';
  }
  return dateString;
}

/**
 * Format a date/datetime in the user's configured timezone.
 */
export function formatInUserTimezone(
  date: Date | string,
  options: Intl.DateTimeFormatOptions = {}
): string {
  const d = date instanceof Date ? date : new Date(normalizeUTCDate(date));
  const tz = getUserTimezone();
  return d.toLocaleString('en-US', { ...options, timeZone: tz });
}

/**
 * Format just the time portion of a UTC date string in the user's timezone.
 */
export function formatTimeInUserTimezone(dateString: string): string {
  return formatInUserTimezone(dateString, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a date (no time) in the user's timezone.
 */
export function formatDateInUserTimezone(
  date: Date | string,
  options: Intl.DateTimeFormatOptions = {}
): string {
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
 */
export function toUserTimezone(utcDate: Date | string): Date {
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

  const get = (type: Intl.DateTimeFormatPartTypes): number => {
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
 */
export function fromUserTimezone(localDate: Date | string): string {
  const tz = getUserTimezone();

  if (typeof localDate === 'string') {
    const naive = new Date(localDate);
    if (isNaN(naive.getTime())) {
      return localDate; // can't parse, return as-is
    }
    return convertNaiveToTimezone(naive, tz).toISOString();
  }

  if (localDate instanceof Date) {
    return convertNaiveToTimezone(localDate, tz).toISOString();
  }

  return new Date(localDate as unknown as string).toISOString();
}

/**
 * Given a Date whose local-time fields represent wall-clock time in the BROWSER's
 * timezone, re-interpret those same wall-clock values as if they were in `targetTz`
 * and return the corresponding UTC Date.
 */
function convertNaiveToTimezone(date: Date, targetTz: string): Date {
  // Step 1: extract the wall-clock components from the Date
  const year = date.getFullYear();
  const month = date.getMonth(); // 0-indexed
  const day = date.getDate();
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const seconds = date.getSeconds();

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

  const get = (type: Intl.DateTimeFormatPartTypes): number => {
    const part = targetLocal.find(p => p.type === type);
    return part ? parseInt(part.value, 10) : 0;
  };

  const tzHour = get('hour') === 24 ? 0 : get('hour');
  const tzMin = get('minute');

  const wantedMinutes = hours * 60 + minutes;
  const gotMinutes = tzHour * 60 + tzMin;
  let diffMinutes = wantedMinutes - gotMinutes;

  // Handle day boundary wrap
  if (diffMinutes > 720) diffMinutes -= 1440;
  if (diffMinutes < -720) diffMinutes += 1440;

  // Adjust the UTC equivalent by the difference
  return new Date(utcEquivalent.getTime() + diffMinutes * 60000);
}

/**
 * Get a date string (YYYY-MM-DD) representing "today" in the user's timezone.
 */
export function getTodayInUserTimezone(): string {
  const now = new Date();
  const tz = getUserTimezone();
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(now);
  return parts; // en-CA uses YYYY-MM-DD format
}

/**
 * Check whether a UTC date string falls on the same calendar day as a local Date
 * in the user's configured timezone.
 */
export function isSameDayInUserTimezone(utcDateString: string, localDate: Date): boolean {
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
export function getTimezoneAbbreviation(timezone: string | null = null): string {
  const tz = timezone || getUserTimezone();
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

// ---------------------------------------------------------------------------
// Standardized public API for calendar components
// ---------------------------------------------------------------------------

/**
 * Get the user's browser timezone (always returns the browser's own timezone,
 * ignoring any configured/cached scheduler timezone).
 */
export function getBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Format a UTC ISO string to a localized display time in the given timezone.
 */
export function formatLocalTime(isoString: string, timezone: string | null = null): string {
  if (!isoString) return '';
  const d = new Date(normalizeUTCDate(isoString));
  const tz = timezone || getUserTimezone();
  return d.toLocaleString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: tz,
  });
}

/**
 * Format a date for display with an explicit timezone abbreviation appended.
 */
export function formatTimeWithZone(isoString: string, timezone: string | null = null): string {
  if (!isoString) return '';
  const d = new Date(normalizeUTCDate(isoString));
  const tz = timezone || getUserTimezone();
  return d.toLocaleString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: tz,
    timeZoneName: 'short',
  });
}

/**
 * Convert a local date string and time string (as selected by a user in their
 * timezone) into a UTC ISO string suitable for API submission.
 */
export function localToUTC(
  dateStr: string,
  timeStr: string,
  timezone: string | null = null
): string {
  if (!dateStr || !timeStr) return '';
  const tz = timezone || getUserTimezone();
  const naive = new Date(`${dateStr}T${timeStr}`);
  if (isNaN(naive.getTime())) return '';
  return convertNaiveToTimezone(naive, tz).toISOString();
}

/**
 * Format a start/end time range with a single timezone abbreviation.
 */
export function formatTimeRange(
  startISO: string,
  endISO: string,
  timezone: string | null = null
): string {
  if (!startISO || !endISO) return '';
  const tz = timezone || getUserTimezone();
  const startDate = new Date(normalizeUTCDate(startISO));
  const endDate = new Date(normalizeUTCDate(endISO));

  // Format start time without timezone name
  const startStr = startDate.toLocaleString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: tz,
  });

  // Format end time with timezone abbreviation
  const endStr = endDate.toLocaleString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: tz,
    timeZoneName: 'short',
  });

  return `${startStr} - ${endStr}`;
}
