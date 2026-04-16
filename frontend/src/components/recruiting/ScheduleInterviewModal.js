import React, { useState, useEffect, useCallback } from 'react';
import { bookAppointment, getAvailability } from '../../services/schedulingService';
import './ScheduleInterviewModal.css';
import { getToken } from '../../utils/tokenStore';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Four interview types with unique functionality
const INTERVIEW_TYPES = [
  {
    value: 'phone_screen',
    label: 'Phone Screen',
    icon: '📞',
    duration: 30,
    description: 'Standard phone call with calendar invite',
    mode: 'phone'
  },
  {
    value: 'video_interview',
    label: 'Video Interview',
    icon: '🎥',
    duration: 45,
    description: 'UVIP Smart Video meeting',
    mode: 'video'
  },
  {
    value: 'in_person',
    label: 'In-Person Interview',
    icon: '🏢',
    duration: 60,
    description: 'Meet at the office location',
    mode: 'in_person'
  },
  {
    value: 'panel',
    label: 'Panel Interview',
    icon: '👥',
    duration: 90,
    description: 'Video panel with multiple interviewers',
    mode: 'video_panel'
  }
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
  const [sendSmsReminder, setSendSmsReminder] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [officeLocations, setOfficeLocations] = useState([]);
  const [selectedOffice, setSelectedOffice] = useState('');
  const [availableSlots, setAvailableSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);

  // Get auth headers
  const getAuthHeaders = useCallback(() => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Fetch team members who can be interviewers
  useEffect(() => {
    const fetchInterviewers = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/admin/users`, {
          headers: getAuthHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          // Handle both array and {users: []} response formats
          const users = data.users || data || [];
          setInterviewers(users.map(u => ({
            id: u.id,
            name: u.full_name || u.name || `${u.first_name || ''} ${u.last_name || ''}`.trim(),
            email: u.email
          })));
        }
      } catch (err) {
        console.error('Failed to fetch interviewers:', err);
      }
    };

    const fetchOfficeLocations = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/settings/office-locations`, {
          headers: getAuthHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          setOfficeLocations(data.locations || data || []);
        } else {
          // Default office location if API not available
          setOfficeLocations([
            { id: 'main', name: 'Main Office', address: '123 Business Center Dr, Suite 100' }
          ]);
        }
      } catch (err) {
        console.error('Failed to fetch office locations:', err);
        setOfficeLocations([
          { id: 'main', name: 'Main Office', address: '123 Business Center Dr, Suite 100' }
        ]);
      }
    };

    if (isOpen) {
      fetchInterviewers();
      fetchOfficeLocations();
    }
  }, [isOpen, getAuthHeaders]);

  // Update form when interview type changes
  useEffect(() => {
    const typeConfig = INTERVIEW_TYPES.find(t => t.value === interviewType);
    if (typeConfig) {
      setDuration(typeConfig.duration);

      // Set default location based on interview type
      switch (interviewType) {
        case 'phone_screen':
          setLocation(candidate?.phone || '');
          break;
        case 'video_interview':
          setLocation('UVIP Smart Video (link will be generated)');
          break;
        case 'in_person':
          if (officeLocations.length > 0 && !selectedOffice) {
            setSelectedOffice(officeLocations[0].id);
            setLocation(officeLocations[0].address);
          }
          break;
        case 'panel':
          setLocation('UVIP Smart Video Panel (link will be generated)');
          break;
        default:
          setLocation('');
      }
    }
  }, [interviewType, candidate?.phone, officeLocations, selectedOffice]);

  // Set default date to tomorrow
  useEffect(() => {
    if (isOpen && !scheduledDate) {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      setScheduledDate(tomorrow.toISOString().split('T')[0]);
      setScheduledTime('10:00');
    }
  }, [isOpen, scheduledDate]);

  // Load available slots when date changes
  useEffect(() => {
    const loadSlots = async () => {
      if (!scheduledDate) return;

      setLoadingSlots(true);
      try {
        const startDate = new Date(scheduledDate);
        const endDate = new Date(scheduledDate);
        endDate.setDate(endDate.getDate() + 1);

        const availability = await getAvailability({
          startDate,
          endDate,
          provider: 'smart_scheduler'
        });

        if (availability.success && availability.business_hours) {
          // Generate slots based on business hours
          const slots = generateTimeSlots(availability.business_hours, duration);
          setAvailableSlots(slots);
        }
      } catch (err) {
        console.error('Failed to load available slots:', err);
      } finally {
        setLoadingSlots(false);
      }
    };

    loadSlots();
  }, [scheduledDate, duration]);

  // Generate time slots from business hours
  const generateTimeSlots = (businessHours, durationMinutes) => {
    const slots = [];
    const today = new Date();
    const dayOfWeek = today.toLocaleDateString('en-US', { weekday: 'lowercase' });

    // Default business hours if not configured
    const hours = businessHours?.[dayOfWeek] || { start: '09:00', end: '17:00' };

    let currentTime = hours.start;
    const endTime = hours.end;

    while (currentTime < endTime) {
      slots.push(currentTime);
      // Add duration to get next slot
      const [h, m] = currentTime.split(':').map(Number);
      const totalMinutes = h * 60 + m + durationMinutes;
      const newHours = Math.floor(totalMinutes / 60);
      const newMinutes = totalMinutes % 60;
      currentTime = `${newHours.toString().padStart(2, '0')}:${newMinutes.toString().padStart(2, '0')}`;
    }

    return slots;
  };

  // Handle office location change
  const handleOfficeChange = (officeId) => {
    setSelectedOffice(officeId);
    const office = officeLocations.find(o => o.id === officeId);
    if (office) {
      setLocation(office.address);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const typeConfig = INTERVIEW_TYPES.find(t => t.value === interviewType);
      const candidateName = candidate?.name ||
        `${candidate?.first_name || ''} ${candidate?.last_name || ''}`.trim() ||
        'Candidate';

      // Build interview data based on type
      const interviewData = {
        interview_type: interviewType,
        scheduled_at: `${scheduledDate}T${scheduledTime}:00`,
        duration_minutes: duration,
        location: location,
        title: `${typeConfig?.label || 'Interview'} with ${candidateName}`,
        interviewer_user_ids: selectedInterviewers,
        primary_interviewer_id: selectedInterviewers.length > 0 ? selectedInterviewers[0] : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York',
        notes: notes,
        meeting_mode: typeConfig?.mode || 'phone',
        // Notification preferences
        send_calendar_invite: sendCalendarInvite,
        send_email_reminder: sendEmailReminder,
        send_sms_reminder: sendSmsReminder,
        // Candidate info for notifications
        candidate_email: candidate?.email,
        candidate_phone: candidate?.phone,
        candidate_name: candidateName
      };

      // Add type-specific data
      switch (interviewType) {
        case 'phone_screen':
          interviewData.phone_number = candidate?.phone || location;
          break;
        case 'video_interview':
          interviewData.create_video_room = true;
          interviewData.video_provider = 'uvip';
          break;
        case 'in_person':
          interviewData.office_location_id = selectedOffice;
          interviewData.office_address = location;
          break;
        case 'panel':
          interviewData.create_video_room = true;
          interviewData.video_provider = 'uvip';
          interviewData.is_panel = true;
          interviewData.panel_interviewers = selectedInterviewers;
          break;
        default:
          break;
      }

      // Book through smart calendar
      const appointmentResult = await bookAppointment({
        contactName: candidateName,
        contactEmail: candidate?.email,
        contactPhone: candidate?.phone,
        appointmentTime: new Date(`${scheduledDate}T${scheduledTime}:00`),
        appointmentType: interviewType,
        durationMinutes: duration,
        notes: notes,
        provider: 'smart_scheduler'
      });

      if (appointmentResult.success === false) {
        throw new Error(appointmentResult.error || 'Failed to book appointment');
      }

      // Also create the interview record
      const response = await fetch(`${API_BASE}/api/v1/recruiting/candidates/${candidate?.id}/interviews`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          ...interviewData,
          appointment_id: appointmentResult.id
        })
      });

      const result = await response.json();

      // Check for error response (either HTTP error or success:false in body)
      if (!response.ok || result.success === false) {
        const errorMsg = result.error || result.detail || 'Failed to schedule interview';
        console.error('Interview scheduling failed:', result);
        throw new Error(errorMsg);
      }

      // Send notifications
      await sendInterviewNotifications(interviewData, result);

      await onSuccess({
        ...interviewData,
        ...result,
        appointment: appointmentResult
      });

      onClose();
    } catch (err) {
      setError(err.message || 'Failed to schedule interview');
    } finally {
      setLoading(false);
    }
  };

  // Send notifications to candidate and interviewers
  const sendInterviewNotifications = async (interviewData, interviewResult) => {
    try {
      // Send calendar invite and email to candidate
      if (sendCalendarInvite || sendEmailReminder) {
        await fetch(`${API_BASE}/api/v1/recruiting/interviews/${interviewResult.id}/notify`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            send_calendar: sendCalendarInvite,
            send_email: sendEmailReminder,
            send_sms: sendSmsReminder,
            recipients: ['candidate', 'interviewers']
          })
        });
      }
    } catch (err) {
      console.error('Failed to send notifications:', err);
      // Don't fail the whole operation if notifications fail
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

  const currentType = INTERVIEW_TYPES.find(t => t.value === interviewType);
  const showInterviewerSelection = interviewType === 'panel' || interviewers.length > 0;
  const showOfficeSelection = interviewType === 'in_person';

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
            {currentType && (
              <p className="interview-type-description">{currentType.description}</p>
            )}
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
              {loadingSlots ? (
                <div className="loading-slots">Loading available times...</div>
              ) : availableSlots.length > 0 ? (
                <select
                  value={scheduledTime}
                  onChange={e => setScheduledTime(e.target.value)}
                  required
                >
                  {availableSlots.map(slot => (
                    <option key={slot} value={slot}>
                      {new Date(`2000-01-01T${slot}`).toLocaleTimeString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                        hour12: true
                      })}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="time"
                  value={scheduledTime}
                  onChange={e => setScheduledTime(e.target.value)}
                  required
                />
              )}
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

          {/* Office Location Selection (for in-person) */}
          {showOfficeSelection && officeLocations.length > 0 && (
            <div className="schedule-interview-field">
              <label className="schedule-interview-label">Office Location</label>
              <select
                value={selectedOffice}
                onChange={e => handleOfficeChange(e.target.value)}
              >
                {officeLocations.map(office => (
                  <option key={office.id} value={office.id}>
                    {office.name} - {office.address}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Location / Meeting Link */}
          <div className="schedule-interview-field">
            <label className="schedule-interview-label">
              {interviewType === 'phone_screen' ? 'Phone Number' :
               interviewType === 'in_person' ? 'Office Address' :
               'Meeting Link'}
            </label>
            <input
              type="text"
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder={
                interviewType === 'phone_screen' ? 'Enter phone number...' :
                interviewType === 'in_person' ? 'Enter office address...' :
                'Auto-generated for video meetings'
              }
              readOnly={interviewType === 'video_interview' || interviewType === 'panel'}
              className={interviewType === 'video_interview' || interviewType === 'panel' ? 'readonly-field' : ''}
            />
          </div>

          {/* Interviewers Selection (always show for panel, optional for others) */}
          {showInterviewerSelection && (
            <div className="schedule-interview-section">
              <label className="schedule-interview-label">
                {interviewType === 'panel' ? 'Panel Members (Required)' : 'Interviewers (Optional)'}
                {interviewType === 'panel' && <span className="required-indicator">*</span>}
              </label>
              <p className="field-hint">
                {interviewType === 'panel'
                  ? 'Select team members to join the panel interview'
                  : 'Optionally add other team members to this interview'}
              </p>
              <div className="schedule-interview-interviewers">
                {interviewers.slice(0, 12).map(interviewer => (
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
                    {selectedInterviewers.includes(interviewer.id) && (
                      <span className="selected-check">✓</span>
                    )}
                  </button>
                ))}
              </div>
              {interviewType === 'panel' && selectedInterviewers.length === 0 && (
                <p className="validation-hint">Please select at least one panel member</p>
              )}
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

          {/* Notification Options */}
          <div className="schedule-interview-options">
            <label className="schedule-interview-checkbox">
              <input
                type="checkbox"
                checked={sendCalendarInvite}
                onChange={e => setSendCalendarInvite(e.target.checked)}
              />
              <span>Send calendar invite to all participants</span>
            </label>
            <label className="schedule-interview-checkbox">
              <input
                type="checkbox"
                checked={sendEmailReminder}
                onChange={e => setSendEmailReminder(e.target.checked)}
              />
              <span>Send email notification to candidate</span>
            </label>
            <label className="schedule-interview-checkbox">
              <input
                type="checkbox"
                checked={sendSmsReminder}
                onChange={e => setSendSmsReminder(e.target.checked)}
              />
              <span>Send SMS reminder to candidate (24 hours before)</span>
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
              disabled={loading || !scheduledDate || !scheduledTime || (interviewType === 'panel' && selectedInterviewers.length === 0)}
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
