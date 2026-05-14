// Utility functions and constants for Video Meetings

export const formatDateTime = (dateStr) => {
  if (!dateStr) return 'Not scheduled';
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
};

export const getStatusBadge = (status) => {
  const statusColors = {
    scheduled: { bg: '#dbeafe', color: '#1e40af' },
    active: { bg: '#dcfce7', color: '#166534' },
    waiting: { bg: '#fef3c7', color: '#92400e' },
    ended: { bg: '#f3f4f6', color: '#374151' },
    cancelled: { bg: '#fee2e2', color: '#991b1b' }
  };
  const style = statusColors[status] || statusColors.scheduled;
  return (
    <span
      className="status-badge"
      style={{ backgroundColor: style.bg, color: style.color }}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
};

export const getTemplateIcon = (icon) => {
  const icons = {
    phone: '\u{1F4DE}',
    document: '\u{1F4C4}',
    folder: '\u{1F4C1}',
    lock: '\u{1F512}',
    clipboard: '\u{1F4CB}',
    users: '\u{1F465}',
    video: '\u{1F3A5}',
    home: '\u{1F3E0}',
    calendar: '\u{1F4C5}'
  };
  return icons[icon] || '\u{1F3A5}';
};

// Generate time options for select dropdowns (5:00 AM to 10:00 PM)
export const timeOptions = (() => {
  const options = [];
  for (let h = 5; h <= 22; h++) {
    for (let m = 0; m < 60; m += 30) {
      const hour = h.toString().padStart(2, '0');
      const minute = m.toString().padStart(2, '0');
      const time24 = `${hour}:${minute}`;
      const hour12 = h > 12 ? h - 12 : (h === 0 ? 12 : h);
      const ampm = h >= 12 ? 'PM' : 'AM';
      const label = `${hour12}:${minute.padStart(2, '0')} ${ampm}`;
      options.push({ value: time24, label });
    }
  }
  return options;
})();

// Helper function to get video embed URL
export const getVideoEmbedUrl = (url, type) => {
  if (!url) return null;

  if (type === 'youtube') {
    const match = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    return match ? `https://www.youtube.com/embed/${match[1]}` : null;
  } else if (type === 'vimeo') {
    const match = url.match(/vimeo\.com\/(\d+)/);
    return match ? `https://player.vimeo.com/video/${match[1]}` : null;
  } else if (type === 'loom') {
    const match = url.match(/loom\.com\/share\/([a-zA-Z0-9]+)/);
    return match ? `https://www.loom.com/embed/${match[1]}` : null;
  }
  return url;
};

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
export const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');
