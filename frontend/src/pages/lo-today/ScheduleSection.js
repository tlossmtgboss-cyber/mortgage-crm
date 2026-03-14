import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { schedulerAPI } from '../../services/api';
import { formatTime, isPast, getModeLabel, LoadingSkeleton } from './helpers';

// =============================================================================
// Section 1: Today's Schedule
// =============================================================================

export function ScheduleSection() {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const today = new Date();
      const startOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate()).toISOString();
      const endOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59, 59).toISOString();

      const data = await schedulerAPI.getAppointments({
        start_date: startOfDay,
        end_date: endOfDay,
      });

      // data is already an array from ensureArray
      const sorted = (Array.isArray(data) ? data : []).sort(
        (a, b) => new Date(a.start_time || a.starts_at || 0) - new Date(b.start_time || b.starts_at || 0)
      );
      setAppointments(sorted);
    } catch (err) {
      console.error('Failed to fetch today appointments:', err);
      setError(err.message || 'Failed to load schedule');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  // Determine which appointment is current/next
  const currentIndex = useMemo(() => {
    const now = new Date();
    for (let i = 0; i < appointments.length; i++) {
      const start = new Date(appointments[i].start_time || appointments[i].starts_at || 0);
      const end = new Date(appointments[i].end_time || appointments[i].ends_at || start.getTime() + 3600000);
      if (now >= start && now <= end) return i; // Currently in meeting
    }
    // Find next upcoming
    for (let i = 0; i < appointments.length; i++) {
      const start = new Date(appointments[i].start_time || appointments[i].starts_at || 0);
      if (start > new Date()) return i;
    }
    return -1;
  }, [appointments]);

  return (
    <div className="lo-today__section">
      <div className="lo-today__section-header">
        <h2 className="lo-today__section-title">
          Today's Schedule
          {appointments.length > 0 && (
            <span className="lo-today__section-badge">{appointments.length}</span>
          )}
        </h2>
        <Link to="/calendar" style={{ fontSize: 13, color: '#3b82f6', textDecoration: 'none' }}>
          View Calendar
        </Link>
      </div>
      <div className="lo-today__section-body">
        {loading ? (
          <LoadingSkeleton rows={4} />
        ) : error ? (
          <div className="lo-today__error">
            <p>{error}</p>
            <button className="lo-today__retry-btn" onClick={fetchAppointments}>Retry</button>
          </div>
        ) : appointments.length === 0 ? (
          <div className="lo-today__empty">
            <div className="lo-today__empty-icon">📅</div>
            <div>No appointments today</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>Your schedule is clear</div>
          </div>
        ) : (
          appointments.map((appt, idx) => {
            const startKey = appt.start_time || appt.starts_at;
            const endKey = appt.end_time || appt.ends_at;
            const isCurrent = idx === currentIndex && !isPast(endKey);
            const isApptPast = isPast(endKey);
            const clientName = appt.client_name || appt.borrower_name || appt.name || 'Client';
            const apptType = appt.appointment_type_name || appt.type || appt.title || '';
            const mode = appt.meeting_mode || appt.mode || appt.location_type || '';

            return (
              <div
                key={appt.id || idx}
                className={`lo-today__timeline-item ${isCurrent ? 'lo-today__timeline-item--current' : ''} ${isApptPast && !isCurrent ? 'lo-today__timeline-item--past' : ''}`}
              >
                <div className="lo-today__timeline-time">
                  <div className="lo-today__timeline-time-text">{formatTime(startKey)}</div>
                  <div className="lo-today__timeline-time-end">{formatTime(endKey)}</div>
                </div>
                <div className="lo-today__timeline-details">
                  <div className="lo-today__timeline-client">{clientName}</div>
                  {apptType && <div className="lo-today__timeline-type">{apptType}</div>}
                  {mode && (
                    <span className="lo-today__timeline-mode">{getModeLabel(mode)}</span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default ScheduleSection;
