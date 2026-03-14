import React, { useCallback, useMemo } from 'react';

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const handleInteractiveKeyDown = (e, onClick) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onClick(e);
  }
};

/**
 * AppointmentSidebar -- Sidebar panel with tabbed filters, search, and date-grouped event list.
 *
 * Used in: Calendar (main page, legacy sidebar mode)
 *
 * @param {Object} props
 * @param {Array<{key: string, label: string, filterType: string}>} props.tabConfig - Tab definitions for appointment filters
 * @param {string} props.activeTab - Currently selected tab key
 * @param {Function} props.onTabChange - Callback(tabKey) when a tab is selected
 * @param {string} props.searchQuery - Current search filter string
 * @param {Function} props.onSearchChange - Callback(query) when the search input changes
 * @param {Array} props.sortedEvents - Pre-sorted array of events/appointments to display
 * @param {Function} props.onAddClick - Callback() to open the add event modal
 * @param {Function} props.onEventClick - Callback(event) when an appointment row is clicked
 * @param {Function} props.onDeleteEvent - Callback(event) when the delete/cancel button is clicked
 * @param {Function} props.formatEventTime - Function(startTime, endTime) => { startStr: string, duration: number }
 * @returns {React.ReactElement}
 *
 * @example
 * <AppointmentSidebar
 *   tabConfig={[{ key: 'upcoming', label: 'Upcoming', filterType: 'upcoming' }]}
 *   activeTab="upcoming"
 *   onTabChange={setTab}
 *   searchQuery={query}
 *   onSearchChange={setQuery}
 *   sortedEvents={events}
 *   onAddClick={openModal}
 *   onEventClick={handleEdit}
 *   onDeleteEvent={handleDelete}
 *   formatEventTime={formatFn}
 * />
 */
const AppointmentSidebar = React.memo(function AppointmentSidebar({
  tabConfig,
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  sortedEvents,
  onAddClick,
  onEventClick,
  onDeleteEvent,
  formatEventTime,
}) {
  const formatEventDate = useCallback((dateStr) => {
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return 'Tomorrow';
    } else {
      return `${dayNames[date.getDay()]} \u2022 ${monthNames[date.getMonth()]} ${date.getDate()}`;
    }
  }, []);

  const activeTabLabel = useMemo(() => {
    return tabConfig.find(t => t.key === activeTab)?.label || 'Appointments';
  }, [tabConfig, activeTab]);

  return (
    <div className="appointments-sidebar">
      <div className="appointments-sidebar-header">
        <h2>{activeTabLabel}</h2>
        <button
          className="btn-add-appointment"
          onClick={onAddClick}
          title="Add new appointment"
        >
          + Add
        </button>
      </div>
      <div className="calendar-tabs" role="tablist" aria-label="Appointment filters">
        {tabConfig.map(tab => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`calendar-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => onTabChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="search-container">
        <label htmlFor="calendar-search" className="sr-only">Search events</label>
        <input
          id="calendar-search"
          type="text"
          className="search-input"
          placeholder="Search events..."
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <div className="appointments-list">
        {sortedEvents.length === 0 ? (
          <div className="empty-appointments">
            <p>{searchQuery ? 'No matching events' : 'No appointments scheduled'}</p>
          </div>
        ) : (
          sortedEvents.map((event, index) => {
            const { startStr, duration } = formatEventTime(event.start_time, event.end_time);
            const dateLabel = formatEventDate(event.start_time);
            const showDateHeader = index === 0 || formatEventDate(sortedEvents[index - 1].start_time) !== dateLabel;

            return (
              <div key={event.id}>
                {showDateHeader && (
                  <div className="appointment-date-header">{dateLabel}</div>
                )}
                <div
                  className={`appointment-item appointment-${event.event_type || 'meeting'} ${event.isAppointment ? 'clickable' : ''}`}
                  role={event.isAppointment ? 'button' : undefined}
                  tabIndex={event.isAppointment ? 0 : undefined}
                  aria-label={event.isAppointment ? `Edit appointment: ${event.title}` : undefined}
                  onClick={() => event.isAppointment && onEventClick(event)}
                  onKeyDown={event.isAppointment ? (e) => handleInteractiveKeyDown(e, () => onEventClick(event)) : undefined}
                  style={{ cursor: event.isAppointment ? 'pointer' : 'default' }}
                >
                  <div className="appointment-time">
                    <div className="time-start">{startStr}</div>
                    <div className="time-duration">{duration}m</div>
                  </div>
                  <div className="appointment-details">
                    <div className="appointment-title" title={event.title}>{event.title}</div>
                    {event.attendee_name && (
                      <div className="appointment-attendee" title={event.attendee_name}>{event.attendee_name}</div>
                    )}
                    {event.location && (
                      <div className="appointment-location" title={event.location}>{event.location}</div>
                    )}
                    {event.description && (
                      <div className="appointment-description" title={event.description}>{event.description}</div>
                    )}
                    {event.isAppointment && (
                      <div className="appointment-edit-hint">Click to edit/reschedule</div>
                    )}
                  </div>
                  <button
                    className="delete-appointment"
                    onClick={(e) => { e.stopPropagation(); onDeleteEvent(event); }}
                    title={event.isAppointment ? "Cancel appointment" : "Delete event"}
                    aria-label={event.isAppointment ? `Cancel appointment: ${event.title}` : `Delete event: ${event.title}`}
                  >
                    &times;
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
});

export default AppointmentSidebar;
