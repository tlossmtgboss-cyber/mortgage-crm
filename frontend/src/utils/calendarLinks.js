/**
 * Calendar link generators for booking confirmations.
 *
 * Generates:
 *  - Google Calendar event URLs
 *  - Outlook Web event URLs
 *  - ICS file blobs for Apple Calendar / Outlook desktop download
 *
 * All functions accept an appointment object with:
 *   title, startTime (ISO string or Date), endTime (ISO string or Date),
 *   description, location, attendeeName, attendeeEmail
 */

/**
 * Format a Date to Google Calendar's required format: YYYYMMDDTHHmmSSZ
 * @param {Date|string} dt
 * @returns {string}
 */
function toGoogleDateFormat(dt) {
  const d = dt instanceof Date ? dt : new Date(dt);
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
}

/**
 * Format a Date to Outlook Web's required format: YYYY-MM-DDTHH:mm:SSZ
 * @param {Date|string} dt
 * @returns {string}
 */
function toOutlookDateFormat(dt) {
  const d = dt instanceof Date ? dt : new Date(dt);
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/**
 * Format a Date to ICS format: YYYYMMDDTHHmmSS (UTC with trailing Z)
 * @param {Date|string} dt
 * @returns {string}
 */
function toICSDateFormat(dt) {
  const d = dt instanceof Date ? dt : new Date(dt);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getUTCFullYear().toString() +
    pad(d.getUTCMonth() + 1) +
    pad(d.getUTCDate()) +
    'T' +
    pad(d.getUTCHours()) +
    pad(d.getUTCMinutes()) +
    pad(d.getUTCSeconds()) +
    'Z'
  );
}

/**
 * Escape special characters for ICS text fields (RFC 5545).
 * @param {string} text
 * @returns {string}
 */
function escapeICSText(text) {
  if (!text) return '';
  return text
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\n/g, '\\n');
}

/**
 * Fold long lines at 75 octets per RFC 5545.
 * @param {string} line
 * @returns {string}
 */
function foldLine(line) {
  if (line.length <= 75) return line;
  const parts = [];
  parts.push(line.substring(0, 75));
  let remaining = line.substring(75);
  while (remaining.length > 0) {
    parts.push(' ' + remaining.substring(0, 74));
    remaining = remaining.substring(74);
  }
  return parts.join('\r\n');
}

/**
 * Generate a Google Calendar "add event" URL.
 *
 * @param {object} appointment
 * @param {string} appointment.title
 * @param {string|Date} appointment.startTime
 * @param {string|Date} appointment.endTime
 * @param {string} [appointment.description]
 * @param {string} [appointment.location]
 * @returns {string} Google Calendar URL
 */
export function generateGoogleCalendarUrl(appointment) {
  const { title, startTime, endTime, description, location } = appointment;

  const startStr = toGoogleDateFormat(startTime);
  const endStr = toGoogleDateFormat(endTime);

  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: title || 'Mortgage Appointment',
    dates: `${startStr}/${endStr}`,
    details: description || '',
    location: location || '',
  });

  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

/**
 * Generate an Outlook Web "compose event" URL.
 *
 * @param {object} appointment
 * @param {string} appointment.title
 * @param {string|Date} appointment.startTime
 * @param {string|Date} appointment.endTime
 * @param {string} [appointment.description]
 * @param {string} [appointment.location]
 * @returns {string} Outlook Web URL
 */
export function generateOutlookUrl(appointment) {
  const { title, startTime, endTime, description, location } = appointment;

  const startStr = toOutlookDateFormat(startTime);
  const endStr = toOutlookDateFormat(endTime);

  const params = new URLSearchParams({
    path: '/calendar/action/compose',
    subject: title || 'Mortgage Appointment',
    startdt: startStr,
    enddt: endStr,
    body: description || '',
    location: location || '',
  });

  return `https://outlook.live.com/calendar/0/deeplink/compose?${params.toString()}`;
}

/**
 * Generate an ICS file as a Blob for download (Apple Calendar / Outlook desktop).
 *
 * @param {object} appointment
 * @param {string} appointment.title
 * @param {string|Date} appointment.startTime
 * @param {string|Date} appointment.endTime
 * @param {string} [appointment.description]
 * @param {string} [appointment.location]
 * @param {string} [appointment.attendeeName]
 * @param {string} [appointment.attendeeEmail]
 * @param {string} [appointment.organizerName]
 * @param {string} [appointment.organizerEmail]
 * @param {number} [appointment.appointmentId]
 * @returns {Blob} ICS file blob
 */
export function generateICSFile(appointment) {
  const {
    title,
    startTime,
    endTime,
    description,
    location,
    attendeeName,
    attendeeEmail,
    organizerName,
    organizerEmail,
    appointmentId,
  } = appointment;

  const now = toICSDateFormat(new Date());
  const uid = appointmentId
    ? `appt-${appointmentId}@perenniaai.com`
    : `${now}-${Math.random().toString(36).substring(2, 10)}@perenniaai.com`;

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Perennia AI//Booking//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:REQUEST',
    'BEGIN:VEVENT',
    foldLine(`UID:${uid}`),
    `DTSTAMP:${now}`,
    `DTSTART:${toICSDateFormat(startTime)}`,
    `DTEND:${toICSDateFormat(endTime)}`,
    foldLine(`SUMMARY:${escapeICSText(title || 'Mortgage Appointment')}`),
  ];

  if (description) {
    lines.push(foldLine(`DESCRIPTION:${escapeICSText(description)}`));
  }

  if (location) {
    lines.push(foldLine(`LOCATION:${escapeICSText(location)}`));
  }

  if (organizerEmail) {
    const orgName = organizerName || 'Perennia AI';
    lines.push(foldLine(`ORGANIZER;CN=${escapeICSText(orgName)}:mailto:${organizerEmail}`));
  }

  if (attendeeEmail) {
    const attName = attendeeName || 'Attendee';
    lines.push(
      foldLine(
        `ATTENDEE;CN=${escapeICSText(attName)};RSVP=TRUE:mailto:${attendeeEmail}`
      )
    );
  }

  // Reminder: 15 minutes before
  lines.push('BEGIN:VALARM');
  lines.push('TRIGGER:-PT15M');
  lines.push('ACTION:DISPLAY');
  lines.push(foldLine(`DESCRIPTION:${escapeICSText(title || 'Mortgage Appointment')} starts in 15 minutes`));
  lines.push('END:VALARM');

  lines.push('END:VEVENT');
  lines.push('END:VCALENDAR');

  const icsContent = lines.join('\r\n');
  return new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
}

/**
 * Trigger a download of an ICS file blob.
 *
 * @param {Blob} blob - ICS file blob from generateICSFile
 * @param {string} [filename] - Download filename (default: "appointment.ics")
 */
export function downloadICSFile(blob, filename = 'appointment.ics') {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
