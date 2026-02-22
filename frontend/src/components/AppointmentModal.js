import React, { useState } from 'react';
import './AppointmentModal.css';
import { toast } from '../utils/toast';

function AppointmentModal({ isOpen, onClose, lead, onAppointmentCreated }) {
  const [title, setTitle] = useState('');
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [duration, setDuration] = useState('30');
  const [notes, setNotes] = useState('');
  const [appointmentType, setAppointmentType] = useState('phone_call');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!title.trim()) {
      setError('Please enter an appointment title');
      return;
    }

    if (!date || !time) {
      setError('Please select date and time');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      const startDateTime = new Date(`${date}T${time}`);
      const endDateTime = new Date(startDateTime.getTime() + parseInt(duration) * 60000);

      const response = await fetch('/api/v1/calendar/events', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: title.trim(),
          description: notes.trim(),
          start_time: startDateTime.toISOString(),
          end_time: endDateTime.toISOString(),
          event_type: appointmentType,
          lead_id: lead?.id,
          attendee_name: lead?.name || lead?.first_name,
          attendee_email: lead?.email,
          attendee_phone: lead?.phone,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create appointment');
      }

      const data = await response.json();

      // Reset form
      setTitle('');
      setDate('');
      setTime('');
      setDuration('30');
      setNotes('');
      setAppointmentType('phone_call');

      if (onAppointmentCreated) {
        onAppointmentCreated(data);
      }

      toast.success('Appointment scheduled successfully!');
      onClose();
    } catch (err) {
      console.error('Error creating appointment:', err);
      setError('Failed to schedule appointment. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  // Get tomorrow's date as minimum
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const minDate = tomorrow.toISOString().split('T')[0];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content appointment-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Schedule Appointment</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="appointment-modal-form">
          {lead && (
            <div className="lead-info">
              <strong>With:</strong> {lead.name || lead.first_name || 'Unknown'}
              {lead.phone && <span> | {lead.phone}</span>}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Appointment Title *</label>
            <input
              type="text"
              className="form-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Initial Consultation"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Type</label>
            <select
              className="form-select"
              value={appointmentType}
              onChange={(e) => setAppointmentType(e.target.value)}
            >
              <option value="phone_call">Phone Call</option>
              <option value="video_call">Video Call</option>
              <option value="in_person">In Person</option>
              <option value="consultation">Consultation</option>
              <option value="document_review">Document Review</option>
            </select>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Date *</label>
              <input
                type="date"
                className="form-input"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                min={minDate}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Time *</label>
              <input
                type="time"
                className="form-input"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Duration</label>
            <select
              className="form-select"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            >
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="45">45 minutes</option>
              <option value="60">1 hour</option>
              <option value="90">1.5 hours</option>
              <option value="120">2 hours</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea
              className="form-textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add any notes for this appointment..."
              rows="3"
            />
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="cancel-button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="submit-button"
              disabled={isSubmitting || !title.trim() || !date || !time}
            >
              {isSubmitting ? 'Scheduling...' : 'Schedule Appointment'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AppointmentModal;
