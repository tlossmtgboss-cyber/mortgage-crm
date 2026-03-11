// Shared utilities for calendar components

// Helper to normalize UTC date strings from backend
// Backend returns UTC times without Z suffix, so we need to add it
export const normalizeUTCDate = (dateString) => {
  if (!dateString) return dateString;
  // If no timezone indicator, assume UTC and add Z
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    return dateString + 'Z';
  }
  return dateString;
};

// Helper to format date as YYYY-MM-DD for API
export const formatDateForAPI = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const formatTime = (dateString) => {
  const date = new Date(normalizeUTCDate(dateString));
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
};

export const formatDuration = (start, end) => {
  const startDate = new Date(normalizeUTCDate(start));
  const endDate = new Date(normalizeUTCDate(end));
  const diffMs = endDate - startDate;
  const diffMins = Math.round(diffMs / 60000);

  if (diffMins >= 60) {
    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${diffMins}m`;
};

export const getMeetingModeIcon = (mode) => {
  const normalized = (mode || '').toUpperCase();
  switch (normalized) {
    case 'VIDEO':
      return '\u{1F4F9}';
    case 'PHONE':
      return '\u{1F4DE}';
    case 'IN_PERSON':
      return '\u{1F464}';
    default:
      return '\u{1F4C5}';
  }
};

export const getMeetingModeColor = (mode) => {
  const normalized = (mode || '').toUpperCase();
  switch (normalized) {
    case 'VIDEO':
      return '#2563eb'; // Blue
    case 'PHONE':
      return '#059669'; // Green
    case 'IN_PERSON':
      return '#dc2626'; // Red
    default:
      return '#6b7280'; // Gray
  }
};

export const isToday = (date) => {
  if (!date) return false;
  const today = new Date();
  return date.toDateString() === today.toDateString();
};

export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export const DAY_NAMES = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

export const DURATION_OPTIONS = [
  { value: '15', label: '15 minutes' },
  { value: '30', label: '30 minutes' },
  { value: '45', label: '45 minutes' },
  { value: '60', label: '1 hour' },
  { value: '90', label: '1.5 hours' },
  { value: '120', label: '2 hours' },
];

export const MEETING_TYPE_OPTIONS = [
  { value: 'PHONE', label: '\u{1F4DE} Phone Call' },
  { value: 'VIDEO', label: '\u{1F4F9} Video Call' },
  { value: 'IN_PERSON', label: '\u{1F464} In Person' },
];

export const STATUS_OPTIONS = [
  { value: 'booked', label: 'Scheduled' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'completed', label: 'Completed' },
  { value: 'no_show', label: 'No Show' },
];

// Default empty appointment form
export const EMPTY_APPOINTMENT_FORM = {
  title: '',
  attendee_name: '',
  attendee_email: '',
  date: '',
  time: '10:00',
  duration: '30',
  meeting_mode: 'PHONE',
  notes: ''
};
