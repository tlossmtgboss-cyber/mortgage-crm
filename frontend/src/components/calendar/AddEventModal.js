import React, { useState, useEffect } from 'react';

/**
 * AddEventModal -- Modal form for creating new calendar events or scheduled appointments.
 *
 * Supports two modes toggled by tabs: "Calendar Event" (simple event with type, time range,
 * location) and "Appointment" (meeting with mode, duration, attendee info, team assignment).
 * Closes on Escape key press.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {Date} [props.selectedDate] - Pre-selected date for the new event (defaults to now)
 * @param {number|null} [props.selectedTime] - Pre-selected hour from a day/week time slot click
 * @param {Function} props.onClose - Callback() to close the modal
 * @param {Function} props.onAdd - Callback(eventData) to create a calendar event
 * @param {Function} props.onAddAppointment - Callback(appointmentData) to create a scheduled appointment
 * @param {Array<{id: number, full_name: string, email: string}>} props.teamMembers - Team members for the "Assign To" dropdown
 * @returns {React.ReactElement}
 *
 * @example
 * <AddEventModal
 *   selectedDate={new Date()}
 *   selectedTime={14}
 *   onClose={closeModal}
 *   onAdd={handleAddEvent}
 *   onAddAppointment={handleAddAppointment}
 *   teamMembers={team}
 * />
 */
function AddEventModal({ selectedDate, selectedTime, onClose, onAdd, onAddAppointment, teamMembers }) {
  const defaultStart = selectedDate || new Date();
  // If a specific hour was selected (from Day/Week view), use it
  if (selectedTime != null) {
    defaultStart.setHours(selectedTime, 0, 0, 0);
  }
  const defaultEnd = new Date(defaultStart.getTime() + 3600000);

  const [mode, setMode] = useState('event');

  // Close on ESC key
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    event_type: 'meeting',
    location: '',
    all_day: false,
    start_time: defaultStart.toISOString().slice(0, 16),
    end_time: defaultEnd.toISOString().slice(0, 16),
    // Appointment-specific fields
    meeting_mode: 'PHONE',
    duration: '30',
    attendee_name: '',
    attendee_email: '',
    attendee_phone: '',
    team_member_id: '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (mode === 'appointment') {
      const startTime = new Date(formData.start_time);
      onAddAppointment({
        title: formData.title,
        description: formData.description,
        meeting_mode: formData.meeting_mode.toLowerCase(),
        scheduled_start: startTime.toISOString(),
        duration_minutes: parseInt(formData.duration),
        attendee_name: formData.attendee_name || undefined,
        attendee_email: formData.attendee_email || undefined,
        attendee_phone: formData.attendee_phone || undefined,
        assigned_user_id: formData.team_member_id ? parseInt(formData.team_member_id) : undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
    } else {
      onAdd({
        ...formData,
        start_time: new Date(formData.start_time).toISOString(),
        end_time: new Date(formData.end_time).toISOString(),
      });
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" aria-label="Add event" onClick={(e) => e.stopPropagation()}>
        <div className="modal-mode-toggle" role="tablist" aria-label="Event type">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'event'}
            className={mode === 'event' ? 'active' : ''}
            onClick={() => setMode('event')}
          >
            Calendar Event
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'appointment'}
            className={mode === 'appointment' ? 'active' : ''}
            onClick={() => setMode('appointment')}
          >
            Appointment
          </button>
        </div>

        <h3>{mode === 'event' ? 'Add Event' : 'Add Appointment'}</h3>
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

          {mode === 'event' && (
            <>
              <div className="form-group">
                <label>Type</label>
                <select
                  value={formData.event_type}
                  onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}
                >
                  <option value="meeting">Meeting</option>
                  <option value="call">Call</option>
                  <option value="pre_purchase_consultation">Pre-Purchase Consultation</option>
                  <option value="purchase_consultation">Purchase Consultation</option>
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
            </>
          )}

          {mode === 'appointment' && (
            <>
              <div className="form-group">
                <label>Meeting Type</label>
                <div className="meeting-mode-group">
                  {[
                    { value: 'PHONE', label: 'Phone Call' },
                    { value: 'VIDEO', label: 'Video Call' },
                    { value: 'IN_PERSON', label: 'In Person' },
                  ].map(opt => (
                    <div className="meeting-mode-option" key={opt.value}>
                      <input
                        type="radio"
                        id={`add-mode-${opt.value}`}
                        name="add-meeting-mode"
                        value={opt.value}
                        checked={formData.meeting_mode === opt.value}
                        onChange={(e) => setFormData({ ...formData, meeting_mode: e.target.value })}
                      />
                      <label htmlFor={`add-mode-${opt.value}`}>{opt.label}</label>
                    </div>
                  ))}
                </div>
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
                <label>Duration</label>
                <select
                  value={formData.duration}
                  onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
                >
                  <option value="15">15 minutes</option>
                  <option value="30">30 minutes</option>
                  <option value="45">45 minutes</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                  <option value="120">2 hours</option>
                </select>
              </div>
              <div className="attendee-section">
                <h4>Attendee</h4>
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={formData.attendee_name}
                    onChange={(e) => setFormData({ ...formData, attendee_name: e.target.value })}
                    placeholder="Attendee name"
                  />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={formData.attendee_email}
                    onChange={(e) => setFormData({ ...formData, attendee_email: e.target.value })}
                    placeholder="attendee@email.com"
                  />
                </div>
                <div className="form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={formData.attendee_phone}
                    onChange={(e) => setFormData({ ...formData, attendee_phone: e.target.value })}
                    placeholder="(555) 123-4567"
                  />
                </div>
              </div>
              {teamMembers.length > 0 && (
                <div className="form-group">
                  <label>Assign To</label>
                  <select
                    className="team-select"
                    value={formData.team_member_id}
                    onChange={(e) => setFormData({ ...formData, team_member_id: e.target.value })}
                  >
                    <option value="">Myself</option>
                    {teamMembers.map(m => (
                      <option key={m.id} value={m.id}>{m.full_name || m.email}</option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

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
            <button type="submit" className="btn-primary">
              {mode === 'event' ? 'Add Event' : 'Add Appointment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AddEventModal;
