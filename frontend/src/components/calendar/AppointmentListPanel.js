import React, { useMemo } from 'react';
import './AppointmentListPanel.css';

const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function formatDateHeader(dateStr) {
  const d = new Date(dateStr);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
  return `${dayNames[d.getDay()]} • ${monthNames[d.getMonth()]} ${d.getDate()}`;
}

function getEventColor(event) {
  const type = (event.event_type || event.meeting_type || '').toLowerCase();
  if (type.includes('consultation') || type.includes('discovery')) return '#1F3D2E';
  if (type.includes('closing') || type.includes('review')) return '#ed8936';
  if (type.includes('application') || type.includes('walkthrough')) return '#48bb78';
  if (type.includes('rate') || type.includes('lock')) return '#e53e3e';
  if (type.includes('document') || type.includes('doc')) return '#9f7aea';
  return '#4299e1';
}

function getModeIcon(event) {
  const mode = (event.meeting_mode || '').toUpperCase();
  if (mode === 'VIDEO') return '📹';
  if (mode === 'PHONE') return '📞';
  if (mode === 'IN_PERSON') return '🏢';
  return '📅';
}

function AppointmentListPanel({ events, selectedId, onSelect, onAddClick, searchQuery, onSearchChange }) {
  const grouped = useMemo(() => {
    const sorted = [...events].sort((a, b) =>
      new Date(a.start_time || 0) - new Date(b.start_time || 0)
    );

    const filtered = searchQuery
      ? sorted.filter(e => {
          const q = searchQuery.toLowerCase();
          return (e.title || '').toLowerCase().includes(q)
            || (e.attendee_name || '').toLowerCase().includes(q)
            || (e.event_type || '').toLowerCase().includes(q);
        })
      : sorted;

    const groups = [];
    let lastDate = '';
    for (const event of filtered) {
      const date = (event.start_time || '').split('T')[0];
      if (date !== lastDate) {
        groups.push({ type: 'header', date, label: formatDateHeader(event.start_time) });
        lastDate = date;
      }
      groups.push({ type: 'event', event });
    }
    return groups;
  }, [events, searchQuery]);

  const totalCount = events.filter(e => e.isAppointment).length;

  return (
    <div className="appt-list-panel">
      <div className="appt-list-header">
        <div className="appt-list-header-left">
          <h2>Appointments</h2>
          <span className="appt-list-count">{totalCount}</span>
        </div>
        <button className="appt-list-add-btn" onClick={onAddClick} title="Add appointment">
          + Add
        </button>
      </div>

      <div className="appt-list-search">
        <input
          type="text"
          placeholder="Search appointments..."
          value={searchQuery || ''}
          onChange={e => onSearchChange(e.target.value)}
          className="appt-list-search-input"
        />
      </div>

      <div className="appt-list-body">
        {grouped.length === 0 ? (
          <div className="appt-list-empty">
            <div className="appt-list-empty-icon">{'📅'}</div>
            <div className="appt-list-empty-title">
              {searchQuery ? 'No matching appointments' : 'No appointments'}
            </div>
            <div className="appt-list-empty-sub">
              {searchQuery ? 'Try a different search' : 'Click + Add to create one'}
            </div>
          </div>
        ) : (
          grouped.map((item, idx) => {
            if (item.type === 'header') {
              return (
                <div key={`h-${item.date}`} className="appt-list-date-header">
                  {item.label}
                </div>
              );
            }
            const e = item.event;
            const isSelected = selectedId === e.id;
            const color = getEventColor(e);
            const icon = getModeIcon(e);
            const time = formatTime(e.start_time);
            const name = e.attendee_name || '';
            const title = e.title || 'Appointment';

            return (
              <div
                key={e.id || idx}
                className={`appt-list-item${isSelected ? ' appt-list-item--selected' : ''}`}
                onClick={() => onSelect(e)}
                role="button"
                tabIndex={0}
                onKeyDown={ev => { if (ev.key === 'Enter') onSelect(e); }}
              >
                <div className="appt-list-item-color" style={{ backgroundColor: color }} />
                <div className="appt-list-item-icon">{icon}</div>
                <div className="appt-list-item-body">
                  <div className="appt-list-item-title">{title}</div>
                  {name && <div className="appt-list-item-attendee">{name}</div>}
                </div>
                <div className="appt-list-item-time">{time}</div>
                <div className="appt-list-item-status-dot" data-status={e.status || 'scheduled'} />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default React.memo(AppointmentListPanel);
