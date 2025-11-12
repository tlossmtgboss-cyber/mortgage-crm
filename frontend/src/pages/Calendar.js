import React, { useState, useEffect } from 'react';
import { calendarAPI } from '../services/api';
import './Calendar.css';

function Calendar() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState('month');
  const [events, setEvents] = useState([]);
  const [allEvents, setAllEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [calendarOffset, setCalendarOffset] = useState(0); // Month offset for mini calendar scrolling

  useEffect(() => {
    loadEvents();
    loadAllEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDate]);

  const loadEvents = async () => {
    try {
      setLoading(true);
      // Get events for current month
      const startDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const endDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0, 23, 59, 59);

      const data = await calendarAPI.getAll({
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
      });
      setEvents(data);
    } catch (error) {
      console.error('Failed to load events:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadAllEvents = async () => {
    try {
      // Load all events (6 months past and 6 months future)
      const startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 6);
      const endDate = new Date();
      endDate.setMonth(endDate.getMonth() + 6);

      const data = await calendarAPI.getAll({
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
      });
      setAllEvents(data || []);
    } catch (error) {
      console.error('Failed to load all events:', error);
      setAllEvents([]);
    }
  };

  const handleAddEvent = async (eventData) => {
    try {
      await calendarAPI.create(eventData);
      loadEvents();
      loadAllEvents();
      setShowAddModal(false);
    } catch (error) {
      console.error('Failed to create event:', error);
      alert('Failed to create event. Please try again.');
    }
  };

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm('Delete this event?')) return;
    try {
      await calendarAPI.delete(eventId);
      loadEvents();
      loadAllEvents();
    } catch (error) {
      console.error('Failed to delete event:', error);
    }
  };

  // Sort and group events by date
  const getSortedEvents = () => {
    const sorted = [...allEvents].sort((a, b) => {
      return new Date(a.start_time) - new Date(b.start_time);
    });
    return sorted;
  };

  const formatEventTime = (startTime, endTime) => {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const endStr = end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    const duration = Math.round((end - start) / (1000 * 60)); // duration in minutes
    return { startStr, endStr, duration };
  };

  const formatEventDate = (dateStr) => {
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return 'Tomorrow';
    } else {
      const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
      const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
      return `${dayNames[date.getDay()]} • ${monthNames[date.getMonth()]} ${date.getDate()}`;
    }
  };

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const getDaysInMonth = (date) => {
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = firstDay.getDay();

    return { daysInMonth, startingDayOfWeek, year, month };
  };

  // Get data for displayed months (based on offset)
  const displayDate = new Date();
  displayDate.setMonth(displayDate.getMonth() + calendarOffset);
  const currentMonthData = getDaysInMonth(displayDate);

  const nextMonthDate = new Date(displayDate.getFullYear(), displayDate.getMonth() + 1, 1);
  const nextMonthData = getDaysInMonth(nextMonthDate);

  // Scroll calendar months
  const handleScrollUp = () => {
    setCalendarOffset(calendarOffset - 1);
  };

  const handleScrollDown = () => {
    setCalendarOffset(calendarOffset + 1);
  };

  const handlePrevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1));
  };

  const handleNextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1));
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  const handleDayClick = (day) => {
    const date = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
    setSelectedDate(date);
    setShowAddModal(true);
  };

  const getEventsForDate = (day, year, month) => {
    const dateStart = new Date(year, month, day);
    const dateEnd = new Date(year, month, day, 23, 59, 59);

    return allEvents.filter(event => {
      const eventDate = new Date(event.start_time);
      return eventDate >= dateStart && eventDate <= dateEnd;
    });
  };

  // Render a mini calendar for a specific month
  const renderMiniCalendar = (monthData, isNextMonth = false) => {
    const { daysInMonth, startingDayOfWeek, year, month } = monthData;
    const monthDate = new Date(year, month, 1);

    return (
      <div className="mini-calendar">
        <div className="mini-calendar-header">
          <h3>{monthNames[month]} {year}</h3>
        </div>

        <div className="mini-calendar-weekdays">
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, idx) => (
            <div key={idx} className="mini-weekday-label">{day}</div>
          ))}
        </div>

        <div className="mini-calendar-days">
          {[...Array(startingDayOfWeek)].map((_, index) => (
            <div key={`empty-${index}`} className="mini-calendar-day empty" />
          ))}

          {[...Array(daysInMonth)].map((_, index) => {
            const day = index + 1;
            const dayEvents = getEventsForDate(day, year, month);
            const dayDate = new Date(year, month, day);
            const isToday = new Date().toDateString() === dayDate.toDateString();

            return (
              <div
                key={day}
                className={`mini-calendar-day ${isToday ? 'today' : ''} ${dayEvents.length > 0 ? 'has-events' : ''}`}
                onClick={() => {
                  setSelectedDate(dayDate);
                  setShowAddModal(true);
                }}
              >
                <div className="mini-day-number">{day}</div>
                {dayEvents.length > 0 && (
                  <div className="event-dots">
                    {dayEvents.slice(0, 3).map((event, idx) => (
                      <div
                        key={idx}
                        className={`event-dot event-dot-${event.event_type || 'meeting'}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="calendar-page">
      <div className="calendar-header">
        <div>
          <h1>Calendar</h1>
          <p>{monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}</p>
        </div>
        <div className="calendar-controls">
          <div className="view-switcher">
            <button
              className={view === 'day' ? 'active' : ''}
              onClick={() => setView('day')}
            >
              Day
            </button>
            <button
              className={view === 'week' ? 'active' : ''}
              onClick={() => setView('week')}
            >
              Week
            </button>
            <button
              className={view === 'month' ? 'active' : ''}
              onClick={() => setView('month')}
            >
              Month
            </button>
          </div>
          <div className="month-navigation">
            <button onClick={handlePrevMonth}>←</button>
            <button onClick={handleToday}>Today</button>
            <button onClick={handleNextMonth}>→</button>
            <button className="btn-add-event" onClick={() => { setSelectedDate(new Date()); setShowAddModal(true); }}>
              + Add Event
            </button>
          </div>
        </div>
      </div>

      <div className="calendar-content">
        {/* Appointments Sidebar */}
        <div className="appointments-sidebar">
          <div className="appointments-sidebar-header">
            <h2>Appointments</h2>
            <button
              className="btn-add-appointment"
              onClick={() => { setSelectedDate(new Date()); setShowAddModal(true); }}
              title="Add new appointment"
            >
              + Add
            </button>
          </div>
          <div className="appointments-list">
            {getSortedEvents().length === 0 ? (
              <div className="empty-appointments">
                <p>No appointments scheduled</p>
              </div>
            ) : (
              getSortedEvents().map((event, index) => {
                const { startStr, duration } = formatEventTime(event.start_time, event.end_time);
                const dateLabel = formatEventDate(event.start_time);
                const showDateHeader = index === 0 || formatEventDate(getSortedEvents()[index - 1].start_time) !== dateLabel;

                return (
                  <div key={event.id}>
                    {showDateHeader && (
                      <div className="appointment-date-header">{dateLabel}</div>
                    )}
                    <div className={`appointment-item appointment-${event.event_type || 'meeting'}`}>
                      <div className="appointment-time">
                        <div className="time-start">{startStr}</div>
                        <div className="time-duration">{duration}m</div>
                      </div>
                      <div className="appointment-details">
                        <div className="appointment-title">{event.title}</div>
                        {event.location && (
                          <div className="appointment-location">{event.location}</div>
                        )}
                        {event.description && (
                          <div className="appointment-description">{event.description}</div>
                        )}
                      </div>
                      <button
                        className="delete-appointment"
                        onClick={() => handleDeleteEvent(event.id)}
                        title="Delete event"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Two-Month Mini Calendar View */}
        <div className="calendar-main">
          {loading ? (
            <div className="loading">Loading events...</div>
          ) : (
            <div className="calendar-scroll-container">
              {/* Scroll Up Button */}
              <button
                className="calendar-scroll-btn scroll-up"
                onClick={handleScrollUp}
                title="Previous month"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="18 15 12 9 6 15"></polyline>
                </svg>
              </button>

              {/* Two Month View */}
              <div className="two-month-view">
                {renderMiniCalendar(currentMonthData)}
                {renderMiniCalendar(nextMonthData, true)}
              </div>

              {/* Scroll Down Button */}
              <button
                className="calendar-scroll-btn scroll-down"
                onClick={handleScrollDown}
                title="Next month"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>

      {showAddModal && (
        <AddEventModal
          selectedDate={selectedDate}
          onClose={() => setShowAddModal(false)}
          onAdd={handleAddEvent}
        />
      )}
    </div>
  );
}

function AddEventModal({ selectedDate, onClose, onAdd }) {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    event_type: 'meeting',
    location: '',
    all_day: false,
    start_time: selectedDate ? selectedDate.toISOString().slice(0, 16) : '',
    end_time: selectedDate ? new Date(selectedDate.getTime() + 3600000).toISOString().slice(0, 16) : '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onAdd({
      ...formData,
      start_time: new Date(formData.start_time).toISOString(),
      end_time: new Date(formData.end_time).toISOString(),
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h3>Add Event</h3>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Title *</label>
            <input
              type="text"
              required
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Type</label>
            <select
              value={formData.event_type}
              onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}
            >
              <option value="meeting">Meeting</option>
              <option value="call">Call</option>
              <option value="appraisal">Appraisal</option>
              <option value="closing">Closing</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="form-group">
            <label>Start Time *</label>
            <input
              type="datetime-local"
              required
              value={formData.start_time}
              onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>End Time *</label>
            <input
              type="datetime-local"
              required
              value={formData.end_time}
              onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Location</label>
            <input
              type="text"
              value={formData.location}
              onChange={(e) => setFormData({ ...formData, location: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
            />
          </div>
          <div className="form-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Add Event</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Calendar;
