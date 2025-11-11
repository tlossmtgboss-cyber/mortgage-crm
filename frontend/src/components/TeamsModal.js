import React, { useState } from 'react';
import './TeamsModal.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function TeamsModal({ isOpen, onClose, lead }) {
  const [meetingType, setMeetingType] = useState('consultation');
  const [meetingDate, setMeetingDate] = useState('');
  const [meetingTime, setMeetingTime] = useState('');
  const [duration, setDuration] = useState('30');
  const [subject, setSubject] = useState('');
  const [attendees, setAttendees] = useState('');
  const [notes, setNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState(null);

  const meetingTypes = [
    { id: 'consultation', name: 'Initial Consultation', duration: '30' },
    { id: 'followup', name: 'Follow-Up Meeting', duration: '15' },
    { id: 'documentation', name: 'Document Review', duration: '45' },
    { id: 'closing', name: 'Closing Meeting', duration: '60' },
    { id: 'custom', name: 'Custom Meeting', duration: '30' }
  ];

  const handleTypeChange = (type) => {
    setMeetingType(type);
    const selected = meetingTypes.find(t => t.id === type);
    if (selected) {
      setDuration(selected.duration);

      // Auto-fill subject based on type
      if (lead) {
        const subjects = {
          consultation: `Initial Consultation - ${lead.first_name} ${lead.last_name}`,
          followup: `Follow-Up - ${lead.first_name} ${lead.last_name}`,
          documentation: `Document Review - ${lead.first_name} ${lead.last_name}`,
          closing: `Closing Meeting - ${lead.first_name} ${lead.last_name}`,
          custom: ''
        };
        setSubject(subjects[type] || '');
      }
    }
  };

  const createTeamsMeeting = async () => {
    if (!meetingDate || !meetingTime || !subject) {
      setResult({ status: 'error', message: 'Please fill in all required fields' });
      return;
    }

    setCreating(true);
    setResult(null);

    try {
      // Combine date and time
      const startDateTime = `${meetingDate}T${meetingTime}:00`;

      const response = await fetch(`${API_BASE_URL}/api/v1/teams/create-meeting`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          subject: subject,
          start_time: startDateTime,
          duration_minutes: parseInt(duration),
          attendees: attendees.split(',').map(email => email.trim()).filter(e => e),
          lead_id: lead?.id,
          notes: notes
        })
      });

      const data = await response.json();

      if (response.ok) {
        setResult({
          status: 'success',
          message: 'Teams meeting created successfully!',
          details: data
        });

        // Reset form
        setTimeout(() => {
          onClose();
        }, 2000);
      } else {
        setResult({
          status: 'error',
          message: data.detail || 'Failed to create Teams meeting'
        });
      }
    } catch (error) {
      setResult({
        status: 'error',
        message: `Error: ${error.message}`
      });
    } finally {
      setCreating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="teams-modal-overlay" onClick={onClose}>
      <div className="teams-modal" onClick={(e) => e.stopPropagation()}>
        <div className="teams-modal-header">
          <div className="header-info">
            <h2>📅 Create Teams Meeting</h2>
            {lead && (
              <p className="recipient-info">
                For: <strong>{lead.first_name} {lead.last_name}</strong>
                {lead.email && ` (${lead.email})`}
              </p>
            )}
          </div>
          <button className="btn-close-modal" onClick={onClose}>×</button>
        </div>

        <div className="teams-modal-body">
          {/* Meeting Type */}
          <div className="form-group">
            <label>Meeting Type *</label>
            <select
              value={meetingType}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="meeting-type-select"
              disabled={creating}
            >
              {meetingTypes.map(type => (
                <option key={type.id} value={type.id}>
                  {type.name} ({type.duration} min)
                </option>
              ))}
            </select>
          </div>

          {/* Subject */}
          <div className="form-group">
            <label>Meeting Subject *</label>
            <input
              type="text"
              className="meeting-input"
              placeholder="Enter meeting subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={creating}
            />
          </div>

          {/* Date and Time */}
          <div className="form-row">
            <div className="form-group">
              <label>Date *</label>
              <input
                type="date"
                className="meeting-input"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                min={new Date().toISOString().split('T')[0]}
                disabled={creating}
              />
            </div>
            <div className="form-group">
              <label>Time *</label>
              <input
                type="time"
                className="meeting-input"
                value={meetingTime}
                onChange={(e) => setMeetingTime(e.target.value)}
                disabled={creating}
              />
            </div>
            <div className="form-group">
              <label>Duration (min) *</label>
              <input
                type="number"
                className="meeting-input"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                min="15"
                max="480"
                step="15"
                disabled={creating}
              />
            </div>
          </div>

          {/* Attendees */}
          <div className="form-group">
            <label>Additional Attendees (optional)</label>
            <input
              type="text"
              className="meeting-input"
              placeholder="Enter email addresses, separated by commas"
              value={attendees}
              onChange={(e) => setAttendees(e.target.value)}
              disabled={creating}
            />
            <span className="input-hint">Example: john@example.com, jane@example.com</span>
          </div>

          {/* Notes */}
          <div className="form-group">
            <label>Meeting Notes (optional)</label>
            <textarea
              className="meeting-textarea"
              placeholder="Add any notes or agenda items..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows="4"
              disabled={creating}
            />
          </div>

          {/* Result Message */}
          {result && (
            <div className={`result-message ${result.status}`}>
              <span className="result-icon">
                {result.status === 'success' ? '✅' : '❌'}
              </span>
              <div className="result-content">
                <span>{result.message}</span>
                {result.details?.join_url && (
                  <a
                    href={result.details.join_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="meeting-link"
                  >
                    🔗 Join Meeting
                  </a>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="teams-modal-footer">
          <button
            className="btn-secondary"
            onClick={onClose}
            disabled={creating}
          >
            Cancel
          </button>
          <button
            className="btn-primary-teams"
            onClick={createTeamsMeeting}
            disabled={creating || !meetingDate || !meetingTime || !subject}
          >
            {creating ? (
              <>
                <span className="spinner"></span>
                Creating...
              </>
            ) : (
              <>
                <span>📅</span>
                Create Meeting
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default TeamsModal;
