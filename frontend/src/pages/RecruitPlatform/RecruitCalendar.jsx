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
  { value: 'follow_up', label: 'Follow-up' },
];

const TYPE_COLORS = {
  phone_screen: '#4f86f7',
  video_interview: '#7c5cbf',
  panel_interview: '#2196f3',
  offer_call: '#27ae60',
  follow_up: '#e67e22',
  milestone: '#27ae60',
  default: '#3498db',
};

// ── Month helpers ──────────────────────────────────────────────────────────────

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

// ── Week helpers ───────────────────────────────────────────────────────────────

function getWeekDays(date) {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(d);
    day.setDate(d.getDate() + i);
    return day;
  });
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// ── Day helpers ────────────────────────────────────────────────────────────────

const HOURS = Array.from({ length: 14 }, (_, i) => i + 7); // 7am–8pm

function getEventHour(event) {
  if (!event.start) return null;
  return new Date(event.start).getHours();
}

function eventsOnDay(events, date) {
  return events.filter(ev => {
    if (!ev.start) return false;
    return sameDay(new Date(ev.start), date);
  });
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function RecruitCalendar() {
  const { recruitToken } = useRecruitPlatform();
  const today = new Date();

  const [view, setView] = useState('month');
  const [cursor, setCursor] = useState(new Date(today));
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

  const viewYear = cursor.getFullYear();
  const viewMonth = cursor.getMonth();

  const fetchEvents = useCallback(async () => {
    if (!recruitToken) return;
    setLoading(true);
    setWarn(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/interviews/calendar?year=${viewYear}&month=${viewMonth + 1}`,
        { headers: { Authorization: `Bearer ${recruitToken}` } }
      );
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      setEvents(data.events || []);
    } catch {
      setWarn('Could not load calendar events for this period.');
    } finally {
      setLoading(false);
    }
  }, [recruitToken, viewYear, viewMonth]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  // ── Navigation ──────────────────────────────────────────────────────────────

  function goToday() { setCursor(new Date(today)); }

  function goPrev() {
    const d = new Date(cursor);
    if (view === 'month') d.setMonth(d.getMonth() - 1);
    else if (view === 'week') d.setDate(d.getDate() - 7);
    else d.setDate(d.getDate() - 1);
    setCursor(d);
  }

  function goNext() {
    const d = new Date(cursor);
    if (view === 'month') d.setMonth(d.getMonth() + 1);
    else if (view === 'week') d.setDate(d.getDate() + 7);
    else d.setDate(d.getDate() + 1);
    setCursor(d);
  }

  function headerLabel() {
    if (view === 'month') return `${MONTH_NAMES[viewMonth]} ${viewYear}`;
    if (view === 'week') {
      const days = getWeekDays(cursor);
      const start = days[0];
      const end = days[6];
      if (start.getMonth() === end.getMonth())
        return `${MONTH_NAMES[start.getMonth()]} ${start.getDate()}–${end.getDate()}, ${start.getFullYear()}`;
      return `${MONTH_NAMES[start.getMonth()]} ${start.getDate()} – ${MONTH_NAMES[end.getMonth()]} ${end.getDate()}, ${start.getFullYear()}`;
    }
    return `${DAYS[cursor.getDay()]}, ${MONTH_NAMES[cursor.getMonth()]} ${cursor.getDate()}, ${cursor.getFullYear()}`;
  }

  // ── Schedule submit ─────────────────────────────────────────────────────────

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
      fetchEvents();
    } catch {
      setWarn('Failed to schedule. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const cells = getMonthCells(viewYear, viewMonth);
  const weekDays = getWeekDays(cursor);

  const hasAnyEvents = events.length > 0;

  return (
    <div className="rp-page">
      <div className="rp-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="rp-page-title">Smart Calendar</h1>
          <p className="rp-page-sub">Interviews, follow-ups, and recruiting milestones</p>
        </div>
        <button className="rp-btn rp-btn-primary" onClick={() => setShowModal(true)}>
          + Schedule
        </button>
      </div>

      {warn && (
        <div style={{ background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 6, padding: '8px 14px', marginBottom: 16, color: '#856404', fontSize: 14 }}>
          {warn}
        </div>
      )}

      <div className="rp-card" style={{ padding: 0, overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid #e8eaed', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={goToday} style={{ padding: '4px 12px', fontSize: 13, border: '1px solid #ddd', borderRadius: 6, background: '#fff', cursor: 'pointer', fontWeight: 500 }}>
              Today
            </button>
            <button onClick={goPrev} style={{ background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 14 }}>&#8592;</button>
            <button onClick={goNext} style={{ background: 'none', border: '1px solid #ddd', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 14 }}>&#8594;</button>
            <span style={{ fontWeight: 600, fontSize: 15, marginLeft: 4 }}>{headerLabel()}</span>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {['month', 'week', 'day'].map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                style={{
                  padding: '4px 14px',
                  fontSize: 13,
                  border: '1px solid #ddd',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: view === v ? 600 : 400,
                  background: view === v ? '#4f46e5' : '#fff',
                  color: view === v ? '#fff' : '#333',
                }}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: '#999', fontSize: 14 }}>Loading…</div>
        ) : (
          <>
            {/* Month view */}
            {view === 'month' && (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', borderBottom: '1px solid #e8eaed' }}>
                  {DAYS.map(d => (
                    <div key={d} style={{ padding: '8px 0', textAlign: 'center', fontSize: 12, fontWeight: 600, color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      {d}
                    </div>
                  ))}
                </div>
                {!hasAnyEvents && (
                  <div style={{ padding: '40px 20px', textAlign: 'center', color: '#bbb', fontSize: 14 }}>
                    No events scheduled — click + Schedule to add your first interview
                  </div>
                )}
                {hasAnyEvents && (
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
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 24,
                            height: 24,
                            borderRadius: '50%',
                            background: isToday ? '#4f46e5' : 'transparent',
                            fontWeight: isToday ? 700 : 400,
                            fontSize: 13,
                            color: isToday ? '#fff' : cell.other ? '#ccc' : '#333',
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
                                background: TYPE_COLORS[ev.interview_type || ev.event_type] || TYPE_COLORS.default,
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
              </>
            )}

            {/* Week view */}
            {view === 'week' && (
              <div style={{ overflowX: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '56px repeat(7, 1fr)', minWidth: 700 }}>
                  <div style={{ borderBottom: '1px solid #e8eaed' }} />
                  {weekDays.map((d, i) => {
                    const isToday = sameDay(d, today);
                    return (
                      <div key={i} style={{
                        padding: '10px 6px',
                        textAlign: 'center',
                        borderBottom: '1px solid #e8eaed',
                        borderLeft: '1px solid #e8eaed',
                        background: isToday ? '#f0edff' : '#fff',
                      }}>
                        <div style={{ fontSize: 11, color: '#888', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{DAYS[d.getDay()]}</div>
                        <div style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 28, height: 28, borderRadius: '50%',
                          background: isToday ? '#4f46e5' : 'transparent',
                          color: isToday ? '#fff' : '#333',
                          fontWeight: isToday ? 700 : 500,
                          fontSize: 16,
                          marginTop: 2,
                        }}>
                          {d.getDate()}
                        </div>
                      </div>
                    );
                  })}
                  {HOURS.map(hour => (
                    <React.Fragment key={hour}>
                      <div style={{ padding: '0 6px', textAlign: 'right', fontSize: 11, color: '#aaa', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'flex-start', paddingTop: 4, height: 56, boxSizing: 'border-box' }}>
                        {hour % 12 === 0 ? 12 : hour % 12}{hour < 12 ? 'am' : 'pm'}
                      </div>
                      {weekDays.map((d, di) => {
                        const hourEvents = eventsOnDay(events, d).filter(ev => getEventHour(ev) === hour);
                        return (
                          <div key={di} style={{
                            borderLeft: '1px solid #e8eaed',
                            borderBottom: '1px solid #f0f0f0',
                            height: 56,
                            padding: '2px 4px',
                            background: sameDay(d, today) ? '#fafaf8' : '#fff',
                            position: 'relative',
                          }}>
                            {hourEvents.map(ev => (
                              <div
                                key={ev.id}
                                title={ev.title}
                                style={{
                                  fontSize: 11,
                                  background: TYPE_COLORS[ev.interview_type || ev.event_type] || TYPE_COLORS.default,
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
                    </React.Fragment>
                  ))}
                </div>
                {!hasAnyEvents && (
                  <div style={{ padding: '40px 20px', textAlign: 'center', color: '#bbb', fontSize: 14 }}>
                    No events this week — click + Schedule to add your first interview
                  </div>
                )}
              </div>
            )}

            {/* Day view */}
            {view === 'day' && (
              <div>
                {HOURS.map(hour => {
                  const hourEvents = eventsOnDay(events, cursor).filter(ev => getEventHour(ev) === hour);
                  return (
                    <div key={hour} style={{ display: 'flex', borderBottom: '1px solid #f0f0f0', minHeight: 56 }}>
                      <div style={{ width: 68, flexShrink: 0, padding: '4px 10px 0', textAlign: 'right', fontSize: 12, color: '#aaa' }}>
                        {hour % 12 === 0 ? 12 : hour % 12}{hour < 12 ? 'am' : 'pm'}
                      </div>
                      <div style={{ flex: 1, padding: '4px 8px', borderLeft: '1px solid #e8eaed' }}>
                        {hourEvents.map(ev => (
                          <div
                            key={ev.id}
                            title={ev.title}
                            style={{
                              fontSize: 13,
                              background: TYPE_COLORS[ev.interview_type || ev.event_type] || TYPE_COLORS.default,
                              color: '#fff',
                              borderRadius: 4,
                              padding: '4px 10px',
                              marginBottom: 3,
                              fontWeight: 500,
                            }}
                          >
                            {ev.title}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {!eventsOnDay(events, cursor).length && (
                  <div style={{ padding: '40px 20px', textAlign: 'center', color: '#bbb', fontSize: 14 }}>
                    No events scheduled for this day
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 14 }}>
        {INTERVIEW_TYPES.map(t => (
          <div key={t.value} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#555' }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: TYPE_COLORS[t.value] }} />
            {t.label}
          </div>
        ))}
      </div>

      {/* Schedule modal */}
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
                  placeholder="e.g. Jane Smith"
                  style={{ width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Type</label>
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
                  placeholder="Optional notes about this interview…"
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
