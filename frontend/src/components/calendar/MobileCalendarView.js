import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useSwipeGesture } from '../../hooks/useMediaQuery';
import './MobileCalendarView.css';

const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const dayAbbreviations = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

const formatEventTime = (startTime, endTime) => {
  const start = new Date(startTime);
  const end = new Date(endTime);
  const startStr = start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  const endStr = end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  const duration = Math.round((end - start) / (1000 * 60));
  return { startStr, endStr, duration };
};

const getEventTypeColor = (eventType) => {
  const colors = {
    meeting: 'var(--color-primary, #217f8d)',
    call: 'var(--color-info, #64748b)',
    appraisal: 'var(--color-warning, #a84b2f)',
    closing: '#22c55e',
    pre_purchase_consultation: '#8b5cf6',
    purchase_consultation: '#6366f1',
  };
  return colors[eventType] || '#94a3b8';
};

const getMeetingModeIcon = (mode) => {
  switch (mode) {
    case 'PHONE': return 'tel';
    case 'VIDEO': return 'vid';
    case 'IN_PERSON': return 'loc';
    default: return '';
  }
};

/**
 * MobileCalendarView - Agenda/list view optimized for mobile devices.
 *
 * Features:
 *  - Scrollable agenda cards for the selected day
 *  - Swipe left/right to change day
 *  - Sticky header with date and nav arrows
 *  - Floating action button for quick appointment creation
 *  - Bottom sheet modal for creating appointments (minimal fields)
 *  - Full-screen slide-over for appointment details
 */
export default function MobileCalendarView({
  currentDate,
  allEvents,
  onDateChange,
  onEditAppointment,
  onDeleteEvent,
  onAddEvent,
  onAddAppointment,
  teamMembers,
  activeTab,
  onTabChange,
  tabConfig,
  searchQuery,
  onSearchChange,
  getFilteredEvents,
  loading,
}) {
  const [showDetailSlideOver, setShowDetailSlideOver] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [showBottomSheet, setShowBottomSheet] = useState(false);
  const [slideDirection, setSlideDirection] = useState(null); // 'left' | 'right' | null
  const agendaRef = useRef(null);

  // Quick-add form state (minimal fields for bottom sheet)
  const [quickForm, setQuickForm] = useState({
    title: '',
    meeting_mode: 'PHONE',
    date: '',
    time: '09:00',
    duration: '30',
    attendee_name: '',
    attendee_email: '',
  });

  // Reset quick form when bottom sheet opens
  useEffect(() => {
    if (showBottomSheet) {
      setQuickForm({
        title: '',
        meeting_mode: 'PHONE',
        date: currentDate.toISOString().split('T')[0],
        time: '09:00',
        duration: '30',
        attendee_name: '',
        attendee_email: '',
      });
    }
  }, [showBottomSheet, currentDate]);

  // Navigate day with swipe
  const goToPrevDay = useCallback(() => {
    setSlideDirection('right');
    const prev = new Date(currentDate);
    prev.setDate(prev.getDate() - 1);
    onDateChange(prev);
  }, [currentDate, onDateChange]);

  const goToNextDay = useCallback(() => {
    setSlideDirection('left');
    const next = new Date(currentDate);
    next.setDate(next.getDate() + 1);
    onDateChange(next);
  }, [currentDate, onDateChange]);

  // Clear animation class after transition
  useEffect(() => {
    if (slideDirection) {
      const timer = setTimeout(() => setSlideDirection(null), 300);
      return () => clearTimeout(timer);
    }
  }, [slideDirection]);

  const swipeHandlers = useSwipeGesture({
    onSwipeLeft: goToNextDay,
    onSwipeRight: goToPrevDay,
    threshold: 50,
  });

  // Filter events for the current day
  const dayEvents = useMemo(() => {
    const filtered = getFilteredEvents ? getFilteredEvents(allEvents) : allEvents;
    return filtered
      .filter((event) => {
        const eventDate = new Date(event.start_time);
        return isSameDay(eventDate, currentDate);
      })
      .filter((event) => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
          (event.title || '').toLowerCase().includes(q) ||
          (event.attendee_name || '').toLowerCase().includes(q) ||
          (event.location || '').toLowerCase().includes(q)
        );
      })
      .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [allEvents, currentDate, getFilteredEvents, searchQuery]);

  // Relative date label
  const getDateLabel = () => {
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (isSameDay(currentDate, today)) return 'Today';
    if (isSameDay(currentDate, tomorrow)) return 'Tomorrow';
    if (isSameDay(currentDate, yesterday)) return 'Yesterday';
    return `${dayNames[currentDate.getDay()]}, ${monthNames[currentDate.getMonth()]} ${currentDate.getDate()}`;
  };

  const handleEventTap = (event) => {
    setSelectedEvent(event);
    setShowDetailSlideOver(true);
  };

  const handleQuickSubmit = (e) => {
    e.preventDefault();
    if (!quickForm.title.trim()) return;

    const startTime = new Date(`${quickForm.date}T${quickForm.time}`);
    onAddAppointment({
      title: quickForm.title,
      meeting_mode: quickForm.meeting_mode.toLowerCase(),
      scheduled_start: startTime.toISOString(),
      duration_minutes: parseInt(quickForm.duration),
      attendee_name: quickForm.attendee_name || undefined,
      attendee_email: quickForm.attendee_email || undefined,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
    setShowBottomSheet(false);
  };

  const handleGoToToday = () => {
    onDateChange(new Date());
  };

  const isToday = isSameDay(currentDate, new Date());

  return (
    <div className="mobile-calendar" {...swipeHandlers}>
      {/* ===== STICKY HEADER ===== */}
      <div className="mobile-calendar-header">
        <div className="mobile-header-nav">
          <button
            className="mobile-nav-arrow"
            onClick={goToPrevDay}
            aria-label="Previous day"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <div className="mobile-header-date" onClick={handleGoToToday}>
            <span className="mobile-date-label">{getDateLabel()}</span>
            <span className="mobile-date-full">
              {monthNames[currentDate.getMonth()]} {currentDate.getDate()}, {currentDate.getFullYear()}
            </span>
          </div>
          <button
            className="mobile-nav-arrow"
            onClick={goToNextDay}
            aria-label="Next day"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        {/* Horizontal day strip - quick week overview */}
        <div className="mobile-day-strip">
          {Array.from({ length: 7 }, (_, i) => {
            const d = new Date(currentDate);
            d.setDate(d.getDate() - 3 + i);
            const dayIsToday = isSameDay(d, new Date());
            const dayIsSelected = isSameDay(d, currentDate);
            const dayHasEvents = allEvents.some((ev) => isSameDay(new Date(ev.start_time), d));
            return (
              <button
                key={i}
                className={`mobile-day-chip ${dayIsSelected ? 'selected' : ''} ${dayIsToday ? 'today' : ''}`}
                onClick={() => onDateChange(new Date(d))}
              >
                <span className="mobile-day-chip-name">{dayAbbreviations[d.getDay()]}</span>
                <span className="mobile-day-chip-num">{d.getDate()}</span>
                {dayHasEvents && <span className="mobile-day-chip-dot" />}
              </button>
            );
          })}
        </div>

        {/* Filter tabs - horizontally scrollable */}
        <div className="mobile-filter-tabs">
          {tabConfig.map((tab) => (
            <button
              key={tab.key}
              className={`mobile-filter-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => onTabChange(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ===== AGENDA LIST ===== */}
      <div
        ref={agendaRef}
        className={`mobile-agenda ${slideDirection ? `slide-${slideDirection}` : ''}`}
      >
        {loading ? (
          <div className="mobile-agenda-empty">
            <div className="mobile-loading-spinner" />
            <p>Loading events...</p>
          </div>
        ) : dayEvents.length === 0 ? (
          <div className="mobile-agenda-empty">
            <div className="mobile-empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <p>No appointments {isToday ? 'today' : 'on this day'}</p>
            <button
              className="mobile-empty-add-btn"
              onClick={() => setShowBottomSheet(true)}
            >
              Schedule one
            </button>
          </div>
        ) : (
          dayEvents.map((event) => {
            const { startStr, endStr, duration } = formatEventTime(event.start_time, event.end_time);
            const typeColor = getEventTypeColor(event.event_type);

            return (
              <div
                key={event.id}
                className="mobile-event-card"
                style={{ borderLeftColor: typeColor }}
                onClick={() => handleEventTap(event)}
              >
                <div className="mobile-event-time-col">
                  <span className="mobile-event-start">{startStr}</span>
                  <span className="mobile-event-duration">{duration}m</span>
                </div>
                <div className="mobile-event-info">
                  <div className="mobile-event-title">{event.title}</div>
                  {event.attendee_name && (
                    <div className="mobile-event-attendee">{event.attendee_name}</div>
                  )}
                  {event.location && (
                    <div className="mobile-event-location">{event.location}</div>
                  )}
                  {event.meeting_mode && (
                    <span
                      className="mobile-event-mode-badge"
                      style={{ borderColor: typeColor, color: typeColor }}
                    >
                      {getMeetingModeIcon(event.meeting_mode)} {event.meeting_mode === 'PHONE' ? 'Phone' : event.meeting_mode === 'VIDEO' ? 'Video' : 'In Person'}
                    </span>
                  )}
                </div>
                <div className="mobile-event-type-indicator" style={{ backgroundColor: typeColor }} />
              </div>
            );
          })
        )}
      </div>

      {/* ===== FLOATING ACTION BUTTON ===== */}
      <button
        className="mobile-fab"
        onClick={() => setShowBottomSheet(true)}
        aria-label="Add appointment"
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {/* ===== BOTTOM SHEET - Quick Add ===== */}
      {showBottomSheet && (
        <div className="mobile-bottom-sheet-overlay" onClick={() => setShowBottomSheet(false)}>
          <div
            className="mobile-bottom-sheet"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-bottom-sheet-handle" />
            <h3>Quick Add Appointment</h3>
            <form onSubmit={handleQuickSubmit}>
              <div className="mobile-form-group">
                <input
                  type="text"
                  placeholder="Appointment title *"
                  value={quickForm.title}
                  onChange={(e) => setQuickForm({ ...quickForm, title: e.target.value })}
                  required
                  autoFocus
                  className="mobile-input"
                />
              </div>

              <div className="mobile-form-row">
                <div className="mobile-form-group mobile-form-half">
                  <label>Date</label>
                  <input
                    type="date"
                    value={quickForm.date}
                    onChange={(e) => setQuickForm({ ...quickForm, date: e.target.value })}
                    required
                    className="mobile-input"
                  />
                </div>
                <div className="mobile-form-group mobile-form-half">
                  <label>Time</label>
                  <input
                    type="time"
                    value={quickForm.time}
                    onChange={(e) => setQuickForm({ ...quickForm, time: e.target.value })}
                    required
                    className="mobile-input"
                  />
                </div>
              </div>

              <div className="mobile-form-row">
                <div className="mobile-form-group mobile-form-half">
                  <label>Duration</label>
                  <select
                    value={quickForm.duration}
                    onChange={(e) => setQuickForm({ ...quickForm, duration: e.target.value })}
                    className="mobile-input"
                  >
                    <option value="15">15 min</option>
                    <option value="30">30 min</option>
                    <option value="45">45 min</option>
                    <option value="60">1 hour</option>
                    <option value="90">1.5 hours</option>
                  </select>
                </div>
                <div className="mobile-form-group mobile-form-half">
                  <label>Type</label>
                  <div className="mobile-mode-selector">
                    {['PHONE', 'VIDEO', 'IN_PERSON'].map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        className={`mobile-mode-btn ${quickForm.meeting_mode === mode ? 'active' : ''}`}
                        onClick={() => setQuickForm({ ...quickForm, meeting_mode: mode })}
                      >
                        {mode === 'PHONE' ? 'Ph' : mode === 'VIDEO' ? 'Vid' : 'Loc'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mobile-form-group">
                <input
                  type="text"
                  placeholder="Attendee name"
                  value={quickForm.attendee_name}
                  onChange={(e) => setQuickForm({ ...quickForm, attendee_name: e.target.value })}
                  className="mobile-input"
                />
              </div>

              <div className="mobile-form-group">
                <input
                  type="email"
                  placeholder="Attendee email"
                  value={quickForm.attendee_email}
                  onChange={(e) => setQuickForm({ ...quickForm, attendee_email: e.target.value })}
                  className="mobile-input"
                />
              </div>

              <div className="mobile-bottom-sheet-actions">
                <button
                  type="button"
                  className="mobile-btn-cancel"
                  onClick={() => setShowBottomSheet(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="mobile-btn-submit">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===== FULL-SCREEN SLIDE-OVER - Event Detail ===== */}
      {showDetailSlideOver && selectedEvent && (
        <div className="mobile-slide-over-overlay" onClick={() => setShowDetailSlideOver(false)}>
          <div
            className="mobile-slide-over"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-slide-over-header">
              <button
                className="mobile-slide-back"
                onClick={() => setShowDetailSlideOver(false)}
                aria-label="Close details"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
              <h3>Appointment Details</h3>
              <div style={{ width: 44 }} />
            </div>

            <div className="mobile-slide-over-body">
              <div
                className="mobile-detail-color-bar"
                style={{ backgroundColor: getEventTypeColor(selectedEvent.event_type) }}
              />

              <h2 className="mobile-detail-title">{selectedEvent.title}</h2>

              <div className="mobile-detail-row">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                <div>
                  <div className="mobile-detail-label">Time</div>
                  <div className="mobile-detail-value">
                    {formatEventTime(selectedEvent.start_time, selectedEvent.end_time).startStr}
                    {' - '}
                    {formatEventTime(selectedEvent.start_time, selectedEvent.end_time).endStr}
                    {' '}
                    ({formatEventTime(selectedEvent.start_time, selectedEvent.end_time).duration}m)
                  </div>
                </div>
              </div>

              <div className="mobile-detail-row">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <div>
                  <div className="mobile-detail-label">Date</div>
                  <div className="mobile-detail-value">
                    {dayNames[new Date(selectedEvent.start_time).getDay()]},{' '}
                    {monthNames[new Date(selectedEvent.start_time).getMonth()]}{' '}
                    {new Date(selectedEvent.start_time).getDate()},{' '}
                    {new Date(selectedEvent.start_time).getFullYear()}
                  </div>
                </div>
              </div>

              {selectedEvent.attendee_name && (
                <div className="mobile-detail-row">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  <div>
                    <div className="mobile-detail-label">Attendee</div>
                    <div className="mobile-detail-value">{selectedEvent.attendee_name}</div>
                    {selectedEvent.attendee_email && (
                      <div className="mobile-detail-sub">{selectedEvent.attendee_email}</div>
                    )}
                    {selectedEvent.attendee_phone && (
                      <div className="mobile-detail-sub">{selectedEvent.attendee_phone}</div>
                    )}
                  </div>
                </div>
              )}

              {selectedEvent.location && (
                <div className="mobile-detail-row">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                  <div>
                    <div className="mobile-detail-label">Location</div>
                    <div className="mobile-detail-value">{selectedEvent.location}</div>
                  </div>
                </div>
              )}

              {selectedEvent.meeting_mode && (
                <div className="mobile-detail-row">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="7" width="20" height="15" rx="2" ry="2" />
                    <polyline points="17 2 12 7 7 2" />
                  </svg>
                  <div>
                    <div className="mobile-detail-label">Meeting Type</div>
                    <div className="mobile-detail-value">
                      {selectedEvent.meeting_mode === 'PHONE' ? 'Phone Call' : selectedEvent.meeting_mode === 'VIDEO' ? 'Video Call' : 'In Person'}
                    </div>
                  </div>
                </div>
              )}

              {selectedEvent.description && (
                <div className="mobile-detail-row">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="17" y1="10" x2="3" y2="10" />
                    <line x1="21" y1="6" x2="3" y2="6" />
                    <line x1="21" y1="14" x2="3" y2="14" />
                    <line x1="17" y1="18" x2="3" y2="18" />
                  </svg>
                  <div>
                    <div className="mobile-detail-label">Notes</div>
                    <div className="mobile-detail-value">{selectedEvent.description}</div>
                  </div>
                </div>
              )}
            </div>

            <div className="mobile-slide-over-actions">
              {selectedEvent.isAppointment && (
                <>
                  <button
                    className="mobile-action-btn mobile-action-edit"
                    onClick={() => {
                      setShowDetailSlideOver(false);
                      onEditAppointment(selectedEvent);
                    }}
                  >
                    Edit / Reschedule
                  </button>
                  <button
                    className="mobile-action-btn mobile-action-delete"
                    onClick={() => {
                      setShowDetailSlideOver(false);
                      onDeleteEvent(selectedEvent);
                    }}
                  >
                    Cancel Appointment
                  </button>
                </>
              )}
              {!selectedEvent.isAppointment && (
                <button
                  className="mobile-action-btn mobile-action-delete"
                  onClick={() => {
                    setShowDetailSlideOver(false);
                    onDeleteEvent(selectedEvent);
                  }}
                >
                  Delete Event
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
