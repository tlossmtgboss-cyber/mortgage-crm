import React, { useState, useEffect, useCallback } from 'react';
import { useRecruitPlatform } from '../../contexts/RecruitPlatformContext';
import { API_BASE_URL } from '../../services/api';
import './RecruitingPlatform.css';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const INTERVIEW_TYPES = [
  { value: 'phone_screen', label: 'Phone Screen' },
  { value: 'video_interview', label: 'Video Interview' },
  { value: 'panel_interview', label: 'Panel Interview' },
  { value: 'offer_call', label: 'Offer Call' },
];

const TYPE_COLORS = {
  phone_screen: '#4f86f7',
  video_interview: '#7c5cbf',
  panel_interview: '#e67e22',
  offer_call: '#27ae60',
  default: '#3498db',
};

function getMonthCells(year, month) {
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

function isSameDay(event, cell) {
  if (!event.start) return false;
  const d = new Date(event.start);
  return d.getFullYear() === cell.year && d.getMonth() === cell.month && d.getDate() === cell.day;
}

export default function RecruitInterviewCalendar() {
  const { recruitToken } = useRecruitPlatform();
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [warn, setWarn] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    candidateName: '',
    interviewType: 'phone_screen',
    date: '',
    time: '10:00',
    duration: 60,
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  const fetchInterviews = useCallback(async () => {
    if (!recruitToken) return;
    setLoading(true);
    setWarn(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/interviews/calendar?year=${viewYear}&month=${viewMonth + 1}`,
        { headers: { Authorization: `Bearer ${recruitToken}` } }
      );
      if (!res.ok) throw new Error('Failed to load interviews');
      const data = await res.json();
      setEvents(data.events || []);
    } catch {
      setWarn('Could not load interviews for this month.');
    } finally {
      setLoading(false);
    }
  }, [recruitToken, viewYear, viewMonth]);

  useEffect(() => { fetchInterviews(); }, [fetchInterviews]);

  function prevMonth() {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  }
  function nextMonth() {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  }

  async function handleSchedule(e) {
    e.preventDefault();
    if (!recruitToken) return;
    setSaving(true);
    try {
      const start = new Date(`${form.date}T${form.time}`);
      const end = new Date(start.getTime() + form.duration * 60000);
      const res = await fetch(`${API_BASE_URL}/api/v1/recruit-calendar/interviews`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${recruitToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: `${INTERVIEW_TYPES.find(t => t.value === form.interviewType)?.label} — ${form.candidateName}`,
          attendee_name: form.candidateName,
          interview_type: form.interviewType,
          scheduled_start: start.toISOString(),
          scheduled_end: end.toISOString(),
          notes: form.notes,
        }),
      });
      if (!res.ok) throw new Error('Failed to schedule');
      setShowModal(false);
      setForm({ candidateName: '', interviewType: 'phone_screen', date: '', time: '10:00', duration: 60, notes: '' });
      fetchInterviews();
    } catch {
      alert('Failed to schedule interview. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const cells = getMonthCells(viewYear, viewMonth);

  return (
    <div className="rp-page">
      <div className="rp-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="rp-page-title">Interview Calendar</h1>
          <p className="rp-page-sub">All scheduled interviews across your recruiting pipeline</p>
        </div>
        <button className="rp-btn rp-btn-primary" onClick={() => setShowModal(true)}>
          + Schedule Interview
        </button>
      </div>

      {warn && (
        <div style={{ background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 6, padding: '8px 14px', marginBottom: 16, color: '#856404', fontSize: 14 }}>
          {warn}
        </div>
      )}

      <div className="rp-card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #e8eaed' }}>
          <button onClick={prevMonth} style={{ background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}>&#8592;</button>
          <span style={{ fontWeight: 600, fontSize: 16 }}>{MONTH_NAMES[viewMonth]} {viewYear}</span>
          <button onClick={nextMonth} style={{ background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}>&#8594;</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', borderBottom: '1px solid #e8eaed' }}>
          {DAYS.map(d => (
            <div key={d} style={{ padding: '8px 0', textAlign: 'center', fontSize: 12, fontWeight: 600, color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {d}
            </div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#999' }}>Loading…</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>
            {cells.map((cell, i) => {
              const cellEvents = events.filter(ev => isSameDay(ev, cell));
              const isToday = !cell.other && cell.day === today.getDate() && cell.month === today.getMonth() && cell.year === today.getFullYear();
              return (
                <div
                  key={i}
                  style={{
                    minHeight: 90,
                    padding: '6px 8px',
                    borderRight: (i + 1) % 7 !== 0 ? '1px solid #e8eaed' : 'none',
                    borderBottom: i < 35 ? '1px solid #e8eaed' : 'none',
                    background: isToday ? '#fffbeb' : cell.other ? '#fafafa' : '#fff',
                  }}
                >
                  <div style={{
                    fontWeight: isToday ? 700 : 400,
                    fontSize: 13,
                    color: cell.other ? '#bbb' : isToday ? '#e67e22' : '#333',
                    marginBottom: 4,
                  }}>
                    {cell.day}
                  </div>
                  {cellEvents.map(ev => (
                    <div
                      key={ev.id}
                      title={ev.title}
                      style={{
                        fontSize: 11,
                        background: TYPE_COLORS[ev.interview_type] || TYPE_COLORS.default,
                        color: '#fff',
                        borderRadius: 3,
                        padding: '2px 5px',
                        marginBottom: 2,
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {ev.title}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#fff', borderRadius: 10, padding: 28, width: 440, maxWidth: '95vw', boxShadow: '0 8px 32px rgba(0,0,0,0.18)' }}>
            <h2 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 600 }}>Schedule Interview</h2>
            <form onSubmit={handleSchedule}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Candidate Name</label>
                <input
                  required
                  value={form.candidateName}
                  onChange={e => setForm(f => ({ ...f, candidateName: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Interview Type</label>
                <select
                  value={form.interviewType}
                  onChange={e => setForm(f => ({ ...f, interviewType: e.target.value }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14 }}
                >
                  {INTERVIEW_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Date</label>
                  <input
                    type="date"
                    required
                    value={form.date}
                    onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Time</label>
                  <input
                    type="time"
                    required
                    value={form.time}
                    onChange={e => setForm(f => ({ ...f, time: e.target.value }))}
                    style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }}
                  />
                </div>
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Duration</label>
                <select
                  value={form.duration}
                  onChange={e => setForm(f => ({ ...f, duration: Number(e.target.value) }))}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14 }}
                >
                  <option value={30}>30 minutes</option>
                  <option value={60}>60 minutes</option>
                  <option value={90}>90 minutes</option>
                </select>
              </div>
              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Notes</label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  rows={3}
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, resize: 'vertical', boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button type="button" onClick={() => setShowModal(false)} style={{ padding: '8px 18px', border: '1px solid #ddd', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 14 }}>
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="rp-btn rp-btn-primary" style={{ padding: '8px 18px' }}>
                  {saving ? 'Scheduling…' : 'Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
