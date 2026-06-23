import React, { useState, useEffect, useCallback } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import RecruitSmartCalendar from '../components/RecruitSmartCalendar';
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
function ApplicantDetail({ applicant, recruitToken, recruitUser, onClose, onStatusChange }) {
  const [status, setStatus] = useState(applicant.status);
  const [notes, setNotes] = useState(applicant.notes || []);
  const [noteText, setNoteText] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);

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
              <button
                className="rd-btn rd-btn-secondary"
                onClick={() => setShowCalendar(true)}
              >
                Schedule Call
              </button>
            </div>
          </div>

          {showCalendar && (
            <RecruitSmartCalendar
              candidateName={`${applicant.first_name} ${applicant.last_name}`}
              candidateEmail={applicant.email}
              candidatePhone={applicant.phone}
              candidateId={applicant.id}
              orgId={recruitUser?.organization_id}
              recruiterId={recruitUser?.id || recruitUser?.user_id}
              recruiterName={recruitUser ? `${recruitUser.first_name || ''} ${recruitUser.last_name || ''}`.trim() || recruitUser.email : ''}
              onClose={() => setShowCalendar(false)}
              onSuccess={() => setShowCalendar(false)}
            />
          )}

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

// ─── Add Candidate Modal ───────────────────────────────────────────────────────
const EMPTY_FORM = { first_name: '', last_name: '', email: '', phone: '', status: 'applied', nmls_number: '', notes: '' };

function AddCandidateModal({ onClose, onAdded }) {
  const { fetchWithAuth } = useRecruitPlatform();
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  const handlePhoneChange = (e) => {
    const digits = e.target.value.replace(/\D/g, '').slice(0, 10);
    let formatted = digits;
    if (digits.length > 6) formatted = `(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`;
    else if (digits.length > 3) formatted = `(${digits.slice(0,3)}) ${digits.slice(3)}`;
    else if (digits.length > 0) formatted = `(${digits}`;
    set('phone', formatted);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.first_name.trim() || !form.last_name.trim() || !form.email.trim()) {
      setError('First name, last name, and email are required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/applicants/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          email: form.email.trim(),
          phone: form.phone.trim() || null,
          status: form.status,
          nmls_number: form.nmls_number.trim() || null,
          notes: form.notes.trim() || null,
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || 'Failed to add candidate.');
        return;
      }
      const created = await res.json();
      onAdded(created);
      onClose();
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rd-modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="rd-modal">
        <div className="rd-modal-header">
          <span className="rd-modal-title">Add Candidate</span>
          <button className="rd-drawer-close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit} className="rd-modal-body">
          <div className="rd-modal-row">
            <div className="rd-modal-field">
              <label className="rd-field-label">First Name *</label>
              <input className="rd-input" value={form.first_name} onChange={e => set('first_name', e.target.value)} required />
            </div>
            <div className="rd-modal-field">
              <label className="rd-field-label">Last Name *</label>
              <input className="rd-input" value={form.last_name} onChange={e => set('last_name', e.target.value)} required />
            </div>
          </div>
          <div className="rd-modal-field">
            <label className="rd-field-label">Email *</label>
            <input className="rd-input" type="email" value={form.email} onChange={e => set('email', e.target.value)} required />
          </div>
          <div className="rd-modal-row">
            <div className="rd-modal-field">
              <label className="rd-field-label">Phone</label>
              <input className="rd-input" type="tel" value={form.phone} onChange={handlePhoneChange} placeholder="(843) 555-1234" />
            </div>
            <div className="rd-modal-field">
              <label className="rd-field-label">NMLS #</label>
              <input className="rd-input" value={form.nmls_number} onChange={e => set('nmls_number', e.target.value)} />
            </div>
          </div>
          <div className="rd-modal-field">
            <label className="rd-field-label">Stage</label>
            <select className="rd-input" value={form.status} onChange={e => set('status', e.target.value)}>
              {COLUMNS.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>
          <div className="rd-modal-field">
            <label className="rd-field-label">Notes</label>
            <textarea className="rd-input" rows={3} value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>
          {error && <div className="rd-modal-error">{error}</div>}
          <div className="rd-modal-actions">
            <button type="button" className="rd-btn rd-btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="rd-btn rd-btn-primary" disabled={saving}>
              {saving ? 'Adding...' : 'Add Candidate'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────────
export default function RecruitDashboard() {
  const { recruitToken, recruitUser, fetchWithAuth } = useRecruitPlatform();
  const [applicants, setApplicants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);

  const fetchApplicants = useCallback(() => {
    if (!recruitToken) return;
    setLoading(true);
    fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/applicants/`)
      .then(r => r.ok ? r.json() : [])
      .then(data => setApplicants(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => setApplicants([]))
      .finally(() => setLoading(false));
  }, [recruitToken, fetchWithAuth]);

  useEffect(() => { fetchApplicants(); }, [fetchApplicants]);

  const handleStatusChange = (id, newStatus) => {
    setApplicants(prev => prev.map(a => a.id === id ? { ...a, status: newStatus } : a));
    if (selected?.id === id) setSelected(prev => ({ ...prev, status: newStatus }));
  };

  const handleCandidateAdded = (candidate) => {
    setApplicants(prev => [candidate, ...prev]);
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
        <button className="rd-add-btn" onClick={() => setShowAddModal(true)}>
          + Add Candidate
        </button>
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
          recruitUser={recruitUser}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
        />
      )}

      {showAddModal && (
        <AddCandidateModal
          onClose={() => setShowAddModal(false)}
          onAdded={handleCandidateAdded}
        />
      )}
    </div>
  );
}
