import React, { useState, useEffect } from 'react';
import { calendarAPI } from '../services/api';
import './Calendar.css';

function Calendar() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState('month');
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);

  useEffect(() => {
    loadEvents();
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

  const handleAddEvent = async (eventData) => {
    try {
      await calendarAPI.create(eventData);
      loadEvents();
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
    } catch (error) {
      console.error('Failed to delete event:', error);
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

    return { daysInMonth, startingDayOfWeek };
  };

  const { daysInMonth, startingDayOfWeek } = getDaysInMonth(currentDate);

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

  const getEventsForDate = (day) => {
    const dateStart = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
    const dateEnd = new Date(currentDate.getFullYear(), currentDate.getMonth(), day, 23, 59, 59);

    return events.filter(event => {
      const eventDate = new Date(event.start_time);
      return eventDate >= dateStart && eventDate <= dateEnd;
    });
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

      {loading ? (
        <div className="loading">Loading events...</div>
      ) : (
        <div className="calendar-grid">
        <div className="calendar-weekdays">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
            <div key={day} className="weekday-label">{day}</div>
          ))}
        </div>

        <div className="calendar-days">
          {[...Array(startingDayOfWeek)].map((_, index) => (
            <div key={`empty-${index}`} className="calendar-day empty" />
          ))}

          {[...Array(daysInMonth)].map((_, index) => {
            const day = index + 1;
            const dayEvents = getEventsForDate(day);
            const isToday = new Date().toDateString() === new Date(currentDate.getFullYear(), currentDate.getMonth(), day).toDateString();

            return (
              <div
                key={day}
                className={`calendar-day ${isToday ? 'today' : ''}`}
                onClick={() => handleDayClick(day)}
              >
                <div className="day-number">{day}</div>
                {dayEvents.map(event => (
                  <div
                    key={event.id}
                    className={`event event-${event.event_type || 'meeting'}`}
                    onClick={(e) => { e.stopPropagation(); }}
                  >
                    <span>{event.title}</span>
                    <button
                      className="delete-event"
                      onClick={(e) => { e.stopPropagation(); handleDeleteEvent(event.id); }}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
        </div>
      )}

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
