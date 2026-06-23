import React, { useState, useEffect, useCallback } from 'react';
import './RecruitSmartCalendar.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function toDateStr(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function isToday(date) {
  const t = new Date();
  return date.toDateString() === t.toDateString();
}

function isPast(date) {
  const t = new Date();
  t.setHours(0, 0, 0, 0);
  return date < t;
}

const DAY_NAMES = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
const MON_NAMES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

export default function RecruitSmartCalendar({
  candidateName,
  candidateEmail,
  candidatePhone,
  candidateId,
  orgId,
  recruiterId,
  recruiterName,
  onClose,
  onSuccess,
}) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [weekStart, setWeekStart] = useState(today);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState('');
  const [meetingMode, setMeetingMode] = useState('phone');
  const [slots, setSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(null);

  const weekDates = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const fetchSlots = useCallback(async (dateStr) => {
    if (!dateStr || !orgId) return;
    setLoadingSlots(true);
    setSlots([]);
    setSelectedTime('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/scheduling/availability?org_id=${orgId}&date=${dateStr}`);
      if (res.ok) {
        const data = await res.json();
        setSlots(data.slots || []);
        if (data.slots?.length > 0) setSelectedTime(data.slots[0].value);
      }
    } catch {
      // availability unavailable — show empty
    } finally {
      setLoadingSlots(false);
    }
  }, [orgId]);

  useEffect(() => {
    if (selectedDate) fetchSlots(toDateStr(selectedDate));
  }, [selectedDate, fetchSlots]);

  const handleSubmit = async () => {
    if (!selectedDate || !selectedTime) return;
    setSubmitting(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/scheduling/appointments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: orgId,
          candidate_id: candidateId,
          candidate_name: candidateName,
          candidate_email: candidateEmail,
          candidate_phone: candidatePhone,
          recruiter_id: recruiterId,
          recruiter_name: recruiterName,
          date: toDateStr(selectedDate),
          time: selectedTime,
          type: meetingMode,
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || 'Failed to book appointment. Please try again.');
        return;
      }
      const data = await res.json();
      setSuccess(data);
      if (onSuccess) onSuccess(data);
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="rsc-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="rsc-modal">
          <button className="rsc-close" onClick={onClose}>×</button>
          <div className="rsc-success">
            <div className="rsc-success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h3>Appointment Scheduled</h3>
            <p>
              {candidateEmail
                ? `A confirmation will be sent to ${candidateEmail}.`
                : 'The appointment has been booked.'}
            </p>
            <div className="rsc-success-code">{success.confirmation_code}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rsc-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="rsc-modal">
        <button className="rsc-close" onClick={onClose}>×</button>
        <h2>Pick a date</h2>

        {/* Week nav */}
        <div className="rsc-week-nav">
          <button
            className="rsc-week-arrow"
            onClick={() => setWeekStart(d => addDays(d, -7))}
            disabled={addDays(weekStart, -1) < today}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>

          <div className="rsc-days">
            {weekDates.map((date, i) => {
              const past = isPast(date);
              const sel = selectedDate && date.toDateString() === selectedDate.toDateString();
              return (
                <button
                  key={i}
                  className={`rsc-day-btn ${sel ? 'selected' : ''} ${isToday(date) && !sel ? 'today' : ''}`}
                  onClick={() => !past && setSelectedDate(date)}
                  disabled={past}
                >
                  <span className="rsc-day-name">{DAY_NAMES[date.getDay()]}</span>
                  <span className="rsc-day-num">{date.getDate()}</span>
                  <span className="rsc-day-mon">{MON_NAMES[date.getMonth()]}</span>
                </button>
              );
            })}
          </div>

          <button
            className="rsc-week-arrow"
            onClick={() => setWeekStart(d => addDays(d, 7))}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* Time picker */}
        <div className="rsc-time-section">
          <h3>Pick a time</h3>
          <p className="rsc-time-hint">Choose your preferred time. Reschedule anytime.</p>
          <div className="rsc-dropdown-wrap">
            <select
              value={selectedTime}
              onChange={e => setSelectedTime(e.target.value)}
              disabled={loadingSlots || !selectedDate}
            >
              {!selectedDate ? (
                <option value="">Select a date first</option>
              ) : loadingSlots ? (
                <option value="">Loading available times...</option>
              ) : slots.length === 0 ? (
                <option value="">No times available</option>
              ) : (
                slots.map(s => (
                  <option key={s.value} value={s.value}>{s.display}</option>
                ))
              )}
            </select>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </div>

          <div className="rsc-mode-toggle">
            <button
              className={`rsc-mode-btn ${meetingMode === 'phone' ? 'active' : ''}`}
              onClick={() => setMeetingMode('phone')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
              </svg>
              Phone call
            </button>
            <button
              className={`rsc-mode-btn ${meetingMode === 'video' ? 'active' : ''}`}
              onClick={() => setMeetingMode('video')}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="5" width="14" height="14" rx="2" />
                <path d="M22 7l-6 4 6 4V7z" />
              </svg>
              Video call
            </button>
          </div>
        </div>

        {/* Appointment with */}
        {recruiterName && (
          <div className="rsc-team-section">
            <h3>Appointment with</h3>
            <select defaultValue={recruiterId || ''} disabled>
              <option value={recruiterId || ''}>{recruiterName}</option>
            </select>
          </div>
        )}

        {/* Scheduling for */}
        <div className="rsc-info-section">
          <strong>Scheduling for:</strong> {candidateName}<br />
          {candidateEmail && <><strong>Email:</strong> {candidateEmail}</>}
        </div>

        {error && <div className="rsc-error">{error}</div>}

        <button
          className="rsc-submit"
          onClick={handleSubmit}
          disabled={submitting || !selectedDate || !selectedTime}
        >
          {submitting ? 'Scheduling...' : 'Submit'}
        </button>
      </div>
    </div>
  );
}
