import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken } from '../../utils/tokenStore';
import { API_BASE_URL } from '../../services/api';
import RecruitingPlatformLayout from './RecruitingPlatformLayout';
import './RecruitingPlatform.css';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

const INTERVIEW_TYPE_LABELS = {
  phone_screen: 'Phone Screen',
  video_interview: 'Video Interview',
  panel_interview: 'Panel Interview',
  culture_fit: 'Culture Fit',
  reference_check: 'Reference Check',
  offer_call: 'Offer Call',
  technical: 'Technical',
};

function getMonthDays(year, month) {
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays = new Date(year, month, 0).getDate();
  const cells = [];

  for (let i = firstDay - 1; i >= 0; i--) {
    cells.push({ day: prevDays - i, month: month - 1, year, other: true });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, month, year, other: false });
  }
  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    cells.push({ day: d, month: month + 1, year, other: true });
  }
  return cells;
}

export default function InterviewCalendar() {
  const navigate = useNavigate();
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  const fetchInterviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/interviews/calendar?year=${viewYear}&month=${viewMonth + 1}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error('Failed to load interviews');
      const data = await res.json();
      setEvents(data.events || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [viewYear, viewMonth]);

  useEffect(() => { fetchInterviews(); }, [fetchInterviews]);

  const cells = getMonthDays(viewYear, viewMonth);

  const eventsByDate = {};
  events.forEach(ev => {
    if (!ev.start) return;
    const d = new Date(ev.start);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!eventsByDate[key]) eventsByDate[key] = [];
    eventsByDate[key].push(ev);
  });

  const prevMonth = () => {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  };

  const nextMonth = () => {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  };

  const monthLabel = new Date(viewYear, viewMonth, 1)
    .toLocaleString('default', { month: 'long', year: 'numeric' });

  return (
    <RecruitingPlatformLayout>
      <div className="rp-page-header">
        <div>
          <div className="rp-page-title">Interview Calendar</div>
          <div className="rp-page-sub">All scheduled interviews across your recruiting pipeline</div>
        </div>
        <button
          className="rp-btn rp-btn--primary"
          onClick={() => navigate('/recruiting/interviews/new')}
        >
          + Schedule Interview
        </button>
      </div>

      {error && <div className="rp-error">{error}</div>}

      <div className="rp-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button className="rp-btn rp-btn--secondary" onClick={prevMonth}>←</button>
          <span style={{ fontSize: 16, fontWeight: 700, flex: 1, textAlign: 'center' }}>
            {monthLabel}
          </span>
          <button className="rp-btn rp-btn--secondary" onClick={nextMonth}>→</button>
        </div>

        {loading ? (
          <div className="rp-loading">Loading interviews...</div>
        ) : (
          <div className="rp-cal-grid">
            {DAYS.map(d => (
              <div key={d} className="rp-cal-day-header">{d}</div>
            ))}
            {cells.map((cell, idx) => {
              const key = `${cell.year}-${cell.month}-${cell.day}`;
              const cellEvents = eventsByDate[key] || [];
              const isToday =
                cell.day === today.getDate() &&
                cell.month === today.getMonth() &&
                cell.year === today.getFullYear();

              return (
                <div
                  key={idx}
                  className={`rp-cal-cell${isToday ? ' rp-cal-cell--today' : ''}${cell.other ? ' rp-cal-cell--other-month' : ''}`}
                >
                  <div className="rp-cal-date">{cell.day}</div>
                  {cellEvents.slice(0, 3).map(ev => (
                    <div
                      key={ev.id}
                      className={`rp-cal-event rp-cal-event--${ev.interview_type || 'default'}`}
                      onClick={() => setSelected(ev)}
                      title={ev.title}
                    >
                      {new Date(ev.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      {' '}{INTERVIEW_TYPE_LABELS[ev.interview_type] || ev.interview_type || 'Interview'}
                    </div>
                  ))}
                  {cellEvents.length > 3 && (
                    <div style={{ fontSize: 10, color: '#9ca3af', paddingLeft: 4 }}>
                      +{cellEvents.length - 3} more
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {selected && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={() => setSelected(null)}
        >
          <div
            className="rp-card"
            style={{ width: 380, margin: 0 }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div className="rp-card-title" style={{ margin: 0 }}>{selected.title}</div>
              <button onClick={() => setSelected(null)} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 18, color: '#9ca3af' }}>×</button>
            </div>
            <div style={{ fontSize: 13, color: '#374151', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div><strong>Type:</strong> {INTERVIEW_TYPE_LABELS[selected.interview_type] || selected.interview_type}</div>
              <div><strong>Time:</strong> {selected.start ? new Date(selected.start).toLocaleString() : '—'}</div>
              <div><strong>Status:</strong> {selected.status}</div>
              <div><strong>Outcome:</strong> {selected.outcome || 'Pending'}</div>
              {selected.candidate_id && (
                <div><strong>Candidate ID:</strong> #{selected.candidate_id}</div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button
                className="rp-btn rp-btn--secondary"
                style={{ flex: 1 }}
                onClick={() => {
                  setSelected(null);
                  navigate(`/recruiting/interviews/${selected.id}`);
                }}
              >
                View Details
              </button>
            </div>
          </div>
        </div>
      )}
    </RecruitingPlatformLayout>
  );
}
