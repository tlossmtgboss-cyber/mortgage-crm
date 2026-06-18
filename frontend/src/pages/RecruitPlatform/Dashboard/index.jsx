import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './Dashboard.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

const COLUMNS = [
  { key: 'applied', label: 'Applied' },
  { key: 'reviewing', label: 'Reviewing' },
  { key: 'phone_screen', label: 'Phone Screen' },
  { key: 'interview', label: 'Interview' },
  { key: 'offer', label: 'Offer' },
  { key: 'hired', label: 'Hired' },
  { key: 'rejected', label: 'Rejected' },
];

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ─── Applicant Detail Drawer ───────────────────────────────────────────────────
function ApplicantDetail({ applicant, recruitToken, onClose, onStatusChange }) {
  const [status, setStatus] = useState(applicant.status);
  const [notes, setNotes] = useState(applicant.notes || []);
  const [noteText, setNoteText] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);

  const handleStatusChange = async (e) => {
    const newStatus = e.target.value;
    setStatus(newStatus);
    setUpdatingStatus(true);
    try {
      await fetch(`${API_BASE}/api/v1/recruit-platform/applicants/${applicant.id}/status`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      onStatusChange(applicant.id, newStatus);
    } catch {
      setStatus(applicant.status);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!noteText.trim()) return;
    setSavingNote(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/applicants/${applicant.id}/notes`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: noteText }),
      });
      if (res.ok) {
        const note = await res.json();
        setNotes(prev => [note, ...prev]);
        setNoteText('');
      }
    } finally {
      setSavingNote(false);
    }
  };

  return (
    <div className="rd-drawer-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="rd-drawer">
        <div className="rd-drawer-header">
          <div>
            <div className="rd-drawer-name">{applicant.first_name} {applicant.last_name}</div>
            <div className="rd-drawer-email">{applicant.email}</div>
          </div>
          <button className="rd-drawer-close" onClick={onClose}>×</button>
        </div>

        <div className="rd-drawer-body">
          {/* Contact info */}
          <div className="rd-detail-section">
            <div className="rd-detail-label">Contact Info</div>
            <div className="rd-detail-row"><span className="rd-detail-key">Phone</span>{applicant.phone || '—'}</div>
            {applicant.nmls_number && (
              <div className="rd-detail-row"><span className="rd-detail-key">NMLS #</span>{applicant.nmls_number}</div>
            )}
            <div className="rd-detail-row"><span className="rd-detail-key">Employer</span>{applicant.current_employer || '—'}</div>
            <div className="rd-detail-row"><span className="rd-detail-key">Experience</span>{applicant.years_experience || '—'}</div>
            <div className="rd-detail-row"><span className="rd-detail-key">Production</span>{applicant.annual_production || '—'}</div>
            <div className="rd-detail-row"><span className="rd-detail-key">Source</span>{applicant.source || '—'}</div>
            {applicant.linkedin_url && (
              <div className="rd-detail-row">
                <span className="rd-detail-key">LinkedIn</span>
                <a href={applicant.linkedin_url} target="_blank" rel="noopener noreferrer" style={{ color: '#1d4ed8' }}>Profile →</a>
              </div>
            )}
            {applicant.resume_url && (
              <div className="rd-detail-row">
                <span className="rd-detail-key">Resume</span>
                <a href={applicant.resume_url} target="_blank" rel="noopener noreferrer" style={{ color: '#1d4ed8' }}>View →</a>
              </div>
            )}
            <div className="rd-detail-row"><span className="rd-detail-key">Applied</span>{formatDate(applicant.created_at)}</div>
          </div>

          {/* Status */}
          <div className="rd-detail-section">
            <div className="rd-detail-label">Status</div>
            <select
              className="rd-status-select"
              value={status}
              onChange={handleStatusChange}
              disabled={updatingStatus}
            >
              {COLUMNS.map(c => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>

          {/* Message */}
          {applicant.message && (
            <div className="rd-detail-section">
              <div className="rd-detail-label">Message</div>
              <div style={{ fontSize: 13.5, color: '#374151', lineHeight: 1.6, background: '#f8fafc', padding: '10px 12px', borderRadius: 8 }}>
                {applicant.message}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="rd-detail-section">
            <div className="rd-detail-label">Actions</div>
            <div className="rd-actions">
              <a href={`/recruiting/interviews?candidate_id=${applicant.id}`}
                className="rd-btn rd-btn-secondary" style={{ textDecoration: 'none' }}>
                Schedule Interview
              </a>
              <a href={`/recruiting/offers?candidate_id=${applicant.id}`}
                className="rd-btn rd-btn-secondary" style={{ textDecoration: 'none' }}>
                Create Offer
              </a>
            </div>
          </div>

          {/* Notes */}
          <div className="rd-detail-section">
            <div className="rd-detail-label">Notes</div>
            <form onSubmit={handleAddNote} className="rd-note-form" style={{ marginBottom: 14 }}>
              <textarea
                className="rd-note-input"
                placeholder="Add a note..."
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
              />
              <div>
                <button type="submit" disabled={savingNote || !noteText.trim()} className="rd-btn rd-btn-primary">
                  {savingNote ? 'Saving...' : 'Add Note'}
                </button>
              </div>
            </form>
            <div className="rd-notes-list">
              {notes.length === 0 && <div style={{ fontSize: 13, color: '#94a3b8' }}>No notes yet.</div>}
              {notes.map((note, i) => (
                <div key={note.id || i} className="rd-note">
                  <div>{note.text}</div>
                  <div className="rd-note-meta">
                    {note.author && `${note.author} · `}
                    {formatDate(note.created_at)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────────
export default function RecruitDashboard() {
  const { recruitToken } = useRecruitPlatform();
  const navigate = useNavigate();
  const [applicants, setApplicants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [stats, setStats] = useState(null);
  const [upcomingInterviews, setUpcomingInterviews] = useState([]);

  const fetchApplicants = useCallback(() => {
    setLoading(true);
    fetch(`${API_BASE}/api/v1/recruit-platform/applicants`, {
      headers: { Authorization: `Bearer ${recruitToken}` },
    })
      .then(r => r.ok ? r.json() : [])
      .then(data => setApplicants(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => setApplicants([]))
      .finally(() => setLoading(false));
  }, [recruitToken]);

  useEffect(() => { fetchApplicants(); }, [fetchApplicants]);

  useEffect(() => {
    if (!recruitToken) return;
    const today = new Date();
    const headers = { Authorization: `Bearer ${recruitToken}` };
    Promise.allSettled([
      fetch(`${API_BASE}/api/v1/recruit-calendar/interviews/calendar?year=${today.getFullYear()}&month=${today.getMonth() + 1}`, { headers }).then(r => r.json()),
      fetch(`${API_BASE}/api/v1/recruit-calendar/milestones/upcoming?days=7`, { headers }).then(r => r.json()),
    ]).then(([iRes, mRes]) => {
      const evts = iRes.status === 'fulfilled' ? (iRes.value.events || []) : [];
      const mils = mRes.status === 'fulfilled' ? mRes.value : {};
      setStats({
        interviews_this_month: evts.length,
        milestones_overdue: (mils.overdue || []).length,
        milestones_this_week: (mils.this_week || []).length,
      });
      const now = new Date();
      setUpcomingInterviews(
        evts.filter(e => e.start && new Date(e.start) >= now)
          .sort((a, b) => new Date(a.start) - new Date(b.start))
          .slice(0, 5)
      );
    });
  }, [recruitToken]);

  const handleStatusChange = (id, newStatus) => {
    setApplicants(prev => prev.map(a => a.id === id ? { ...a, status: newStatus } : a));
    if (selected?.id === id) setSelected(prev => ({ ...prev, status: newStatus }));
  };

  const filtered = applicants.filter(a => {
    const q = search.toLowerCase();
    const matchSearch = !q ||
      `${a.first_name} ${a.last_name}`.toLowerCase().includes(q) ||
      (a.email || '').toLowerCase().includes(q);
    const matchStatus = !statusFilter || a.status === statusFilter;
    const matchSource = !sourceFilter || a.source === sourceFilter;
    return matchSearch && matchStatus && matchSource;
  });

  const byCols = COLUMNS.reduce((acc, col) => {
    acc[col.key] = filtered.filter(a => (a.status || 'applied') === col.key);
    return acc;
  }, {});

  const sources = [...new Set(applicants.map(a => a.source).filter(Boolean))];

  return (
    <div className="rd-layout">
      {/* Stats row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, padding: '16px 20px 0', background: '#f8fafc', borderBottom: '1px solid #e8eaed' }}>
          {[
            { label: 'Interviews This Month', value: stats.interviews_this_month, onClick: () => navigate('/recruit/interviews') },
            { label: 'Milestones Overdue', value: stats.milestones_overdue, warn: stats.milestones_overdue > 0, onClick: () => navigate('/recruit/milestones') },
            { label: 'Milestones This Week', value: stats.milestones_this_week, onClick: () => navigate('/recruit/milestones') },
            { label: 'Total Applicants', value: applicants.length },
            { label: 'Active (not rejected)', value: applicants.filter(a => a.status !== 'rejected').length },
          ].map(s => (
            <div key={s.label} onClick={s.onClick} style={{ background: '#fff', border: `1px solid ${s.warn ? '#fca5a5' : '#e8eaed'}`, borderRadius: 8, padding: '10px 14px', cursor: s.onClick ? 'pointer' : 'default' }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: s.warn ? '#b91c1c' : '#1a1f2e' }}>{s.value ?? '—'}</div>
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}
      {upcomingInterviews.length > 0 && (
        <div style={{ padding: '10px 20px', background: '#f8fafc', borderBottom: '1px solid #e8eaed', display: 'flex', gap: 8, overflowX: 'auto', alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', whiteSpace: 'nowrap' }}>UPCOMING:</span>
          {upcomingInterviews.map(ev => (
            <div key={ev.id} onClick={() => navigate('/recruit/interviews')} style={{ background: '#fff', border: '1px solid #e8eaed', borderRadius: 6, padding: '4px 10px', fontSize: 12, whiteSpace: 'nowrap', cursor: 'pointer', color: '#374151' }}>
              <span style={{ color: '#B8924A', fontWeight: 600 }}>
                {new Date(ev.start).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              </span>
              {' · '}{ev.title}
            </div>
          ))}
        </div>
      )}

      {/* Top bar */}
      <div className="rd-topbar">
        <span className="rd-topbar-title">Pipeline</span>
        <input
          className="rd-search"
          type="text"
          placeholder="Search applicants..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="rd-filter-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {COLUMNS.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <select className="rd-filter-select" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
          <option value="">All sources</option>
          {sources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button
          className="rd-export-btn"
          onClick={() => alert('CSV export coming soon')}
        >
          Export CSV
        </button>
      </div>

      {/* Board */}
      {loading ? (
        <div className="rd-loading">Loading applicants...</div>
      ) : (
        <div className="rd-board">
          {COLUMNS.map(col => {
            const cards = byCols[col.key] || [];
            return (
              <div key={col.key} className="rd-column">
                <div className="rd-col-header">
                  <span className="rd-col-title">{col.label}</span>
                  <span className="rd-col-count">{cards.length}</span>
                </div>
                <div className="rd-col-cards">
                  {cards.length === 0 ? (
                    <div className="rd-empty-col">No applicants</div>
                  ) : cards.map(a => (
                    <div key={a.id} className="rd-card" onClick={() => setSelected(a)}>
                      <div className="rd-card-name">{a.first_name} {a.last_name}</div>
                      <div className="rd-card-email">{a.email}</div>
                      {a.phone && <div className="rd-card-phone">{a.phone}</div>}
                      <div className="rd-card-footer">
                        {a.source && <span className="rd-source-badge">{a.source}</span>}
                        {a.nmls_number && <span className="rd-nmls-badge">NMLS</span>}
                        <span className="rd-card-date">{formatDate(a.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selected && (
        <ApplicantDetail
          applicant={selected}
          recruitToken={recruitToken}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
        />
      )}
    </div>
  );
}
