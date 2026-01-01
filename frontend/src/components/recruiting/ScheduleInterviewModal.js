import React, { useState, useEffect } from 'react';
import './ScheduleInterviewModal.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const INTERVIEW_TYPES = [
  { value: 'phone_screen', label: 'Phone Screen', icon: '📞', duration: 30 },
  { value: 'video_interview', label: 'Video Interview', icon: '💻', duration: 45 },
  { value: 'in_person', label: 'In-Person Interview', icon: '🤝', duration: 60 },
  { value: 'panel', label: 'Panel Interview', icon: '👥', duration: 90 },
  { value: 'technical', label: 'Technical Assessment', icon: '🧪', duration: 60 },
  { value: 'final', label: 'Final Interview', icon: '🎯', duration: 45 }
];

const ScheduleInterviewModal = ({ isOpen, onClose, candidate, onSuccess }) => {
  const [interviewType, setInterviewType] = useState('phone_screen');
  const [scheduledDate, setScheduledDate] = useState('');
  const [scheduledTime, setScheduledTime] = useState('');
  const [duration, setDuration] = useState(30);
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');
  const [interviewers, setInterviewers] = useState([]);
  const [selectedInterviewers, setSelectedInterviewers] = useState([]);
  const [sendCalendarInvite, setSendCalendarInvite] = useState(true);
  const [sendEmailReminder, setSendEmailReminder] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch team members who can be interviewers
  useEffect(() => {
    const fetchInterviewers = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE}/api/v1/team/members`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setInterviewers(data.members || data || []);
        }
      } catch (err) {
        console.error('Failed to fetch interviewers:', err);
      }
    };
    if (isOpen) {
      fetchInterviewers();
    }
  }, [isOpen]);

  // Update duration when interview type changes
  useEffect(() => {
    const typeConfig = INTERVIEW_TYPES.find(t => t.value === interviewType);
    if (typeConfig) {
      setDuration(typeConfig.duration);
      // Set default location for video interviews
      if (interviewType === 'video_interview') {
        setLocation('Google Meet / Zoom (link will be generated)');
      } else if (interviewType === 'phone_screen') {
        setLocation(`Phone: ${candidate?.phone || 'TBD'}`);
      } else {
        setLocation('');
      }
    }
  }, [interviewType, candidate?.phone]);

  // Set default date to tomorrow
  useEffect(() => {
    if (isOpen && !scheduledDate) {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      setScheduledDate(tomorrow.toISOString().split('T')[0]);
      setScheduledTime('10:00');
    }
  }, [isOpen, scheduledDate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const interviewData = {
        interview_type: interviewType,
        scheduled_at: `${scheduledDate}T${scheduledTime}:00`,
        duration_minutes: duration,
        location: location,
        title: `${INTERVIEW_TYPES.find(t => t.value === interviewType)?.label || 'Interview'} with ${candidateName}`,
        interviewer_user_ids: selectedInterviewers,
        primary_interviewer_id: selectedInterviewers.length > 0 ? selectedInterviewers[0] : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York'
      };

      await onSuccess(interviewData);
    } catch (err) {
      setError(err.message || 'Failed to schedule interview');
    } finally {
      setLoading(false);
    }
  };

  const handleInterviewerToggle = (interviewerId) => {
    setSelectedInterviewers(prev =>
      prev.includes(interviewerId)
        ? prev.filter(id => id !== interviewerId)
        : [...prev, interviewerId]
    );
  };

  if (!isOpen) return null;

  const candidateName = candidate?.name ||
    `${candidate?.first_name || ''} ${candidate?.last_name || ''}`.trim() ||
    'Candidate';

  return (
    <div className="schedule-interview-modal-overlay" onClick={onClose}>
      <div className="schedule-interview-modal" onClick={e => e.stopPropagation()}>
        <div className="schedule-interview-header">
          <h2>Schedule Interview</h2>
          <p className="schedule-interview-subtitle">with {candidateName}</p>
          <button className="schedule-interview-close" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="schedule-interview-form">
          {error && (
            <div className="schedule-interview-error">
              {error}
            </div>
          )}

          {/* Interview Type Selection */}
          <div className="schedule-interview-section">
            <label className="schedule-interview-label">Interview Type</label>
            <div className="schedule-interview-types">
              {INTERVIEW_TYPES.map(type => (
                <button
                  key={type.value}
                  type="button"
                  className={`schedule-interview-type-btn ${interviewType === type.value ? 'active' : ''}`}
                  onClick={() => setInterviewType(type.value)}
                >
                  <span className="type-icon">{type.icon}</span>
                  <span className="type-label">{type.label}</span>
                  <span className="type-duration">{type.duration} min</span>
                </button>
              ))}
            </div>
          </div>

          {/* Date & Time */}
          <div className="schedule-interview-row">
            <div className="schedule-interview-field">
              <label className="schedule-interview-label">Date</label>
              <input
                type="date"
                value={scheduledDate}
                onChange={e => setScheduledDate(e.target.value)}
                min={new Date().toISOString().split('T')[0]}
                required
              />
            </div>
            <div className="schedule-interview-field">
              <label className="schedule-interview-label">Time</label>
              <input
                type="time"
                value={scheduledTime}
                onChange={e => setScheduledTime(e.target.value)}
                required
              />
            </div>
            <div className="schedule-interview-field">
              <label className="schedule-interview-label">Duration</label>
              <select value={duration} onChange={e => setDuration(Number(e.target.value))}>
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
                <option value={60}>1 hour</option>
                <option value={90}>1.5 hours</option>
                <option value={120}>2 hours</option>
              </select>
            </div>
          </div>

          {/* Location */}
          <div className="schedule-interview-field">
            <label className="schedule-interview-label">Location / Meeting Link</label>
            <input
              type="text"
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder="Enter location or meeting link..."
            />
          </div>

          {/* Interviewers */}
          {interviewers.length > 0 && (
            <div className="schedule-interview-section">
              <label className="schedule-interview-label">Interviewers</label>
              <div className="schedule-interview-interviewers">
                {interviewers.slice(0, 8).map(interviewer => (
                  <button
                    key={interviewer.id}
                    type="button"
                    className={`schedule-interviewer-btn ${selectedInterviewers.includes(interviewer.id) ? 'selected' : ''}`}
                    onClick={() => handleInterviewerToggle(interviewer.id)}
                  >
                    <span className="interviewer-avatar">
                      {(interviewer.name || interviewer.email || '?').charAt(0).toUpperCase()}
                    </span>
                    <span className="interviewer-name">{interviewer.name || interviewer.email}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          <div className="schedule-interview-field">
            <label className="schedule-interview-label">Notes / Agenda</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Add interview agenda, talking points, or special instructions..."
              rows={3}
            />
          </div>

          {/* Options */}
          <div className="schedule-interview-options">
            <label className="schedule-interview-checkbox">
              <input
                type="checkbox"
                checked={sendCalendarInvite}
                onChange={e => setSendCalendarInvite(e.target.checked)}
              />
              <span>Send calendar invite to candidate</span>
            </label>
            <label className="schedule-interview-checkbox">
              <input
                type="checkbox"
                checked={sendEmailReminder}
                onChange={e => setSendEmailReminder(e.target.checked)}
              />
              <span>Send email reminder 24 hours before</span>
            </label>
          </div>

          {/* Actions */}
          <div className="schedule-interview-actions">
            <button
              type="button"
              className="schedule-interview-btn-cancel"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="schedule-interview-btn-submit"
              disabled={loading || !scheduledDate || !scheduledTime}
            >
              {loading ? 'Scheduling...' : 'Schedule Interview'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ScheduleInterviewModal;
