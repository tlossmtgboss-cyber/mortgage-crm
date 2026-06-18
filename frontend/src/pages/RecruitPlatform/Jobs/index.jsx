import React, { useState, useEffect } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './Jobs.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

const EMPTY_JOB = {
  title: '', department: '', location: '', is_remote: false,
  description: '', status: 'active',
};

function JobModal({ job, recruitToken, onClose, onSaved }) {
  const isEdit = Boolean(job?.id);
  const [form, setForm] = useState(isEdit ? { ...job } : { ...EMPTY_JOB });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (field) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm(f => ({ ...f, [field]: val }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const url = isEdit
        ? `${API_BASE}/api/v1/recruit-platform/jobs/${job.id}`
        : `${API_BASE}/api/v1/recruit-platform/jobs`;
      const res = await fetch(url, {
        method: isEdit ? 'PATCH' : 'POST',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save job');
      onSaved(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="jobs-modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="jobs-modal">
        <div className="jobs-modal-header">
          <h3>{isEdit ? 'Edit Job' : 'New Job Posting'}</h3>
          <button className="jobs-modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="jobs-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="jobs-form-grid">
            <div className="jobs-form-group full">
              <label>Job Title *</label>
              <input type="text" required value={form.title} onChange={set('title')} placeholder="e.g. Senior Loan Officer" />
            </div>
            <div className="jobs-form-group">
              <label>Department</label>
              <input type="text" value={form.department} onChange={set('department')} placeholder="e.g. Sales" />
            </div>
            <div className="jobs-form-group">
              <label>Location</label>
              <input type="text" value={form.location} onChange={set('location')} placeholder="e.g. Dallas, TX" />
            </div>
            <div className="jobs-form-group">
              <label>Status</label>
              <select value={form.status} onChange={set('status')}>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="closed">Closed</option>
              </select>
            </div>
            <div className="jobs-form-group" style={{ alignSelf: 'end' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={form.is_remote} onChange={set('is_remote')} />
                Remote / Hybrid
              </label>
            </div>
            <div className="jobs-form-group full">
              <label>Description</label>
              <textarea value={form.description} onChange={set('description')} rows={5} placeholder="Role description, requirements, etc." />
            </div>
          </div>
          <div className="jobs-modal-actions">
            <button type="button" className="jobs-btn jobs-btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={loading} className="jobs-btn jobs-btn-primary">
              {loading ? 'Saving...' : isEdit ? 'Update Job' : 'Create Job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Jobs() {
  const { recruitToken, recruitUser } = useRecruitPlatform();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editJob, setEditJob] = useState(null);
  const [copied, setCopied] = useState(null);

  const orgSlug = recruitUser?.org_slug || '';

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/recruit-platform/jobs`, {
      headers: { Authorization: `Bearer ${recruitToken}` },
    })
      .then(r => r.ok ? r.json() : [])
      .then(data => setJobs(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, [recruitToken]);

  const handleSaved = (job) => {
    setJobs(prev => {
      const idx = prev.findIndex(j => j.id === job.id);
      if (idx >= 0) { const next = [...prev]; next[idx] = job; return next; }
      return [job, ...prev];
    });
    setShowModal(false);
    setEditJob(null);
  };

  const copyUrl = (job) => {
    const url = `https://recruit.perenniaai.com/apply/${orgSlug}?job=${job.id}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopied(job.id);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const formatDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—';

  return (
    <div className="jobs-layout">
      <div className="jobs-topbar">
        <h1 className="jobs-title">Job Postings</h1>
        <button className="jobs-btn jobs-btn-primary" onClick={() => { setEditJob(null); setShowModal(true); }}>
          + New Job
        </button>
      </div>

      {loading ? (
        <div className="jobs-loading">Loading jobs...</div>
      ) : (
        <div className="jobs-table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Department</th>
                <th>Location</th>
                <th>Remote</th>
                <th>Applicants</th>
                <th>Status</th>
                <th>Created</th>
                <th>Public URL</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr><td colSpan={8} className="jobs-empty">No job postings yet. Create your first one.</td></tr>
              ) : jobs.map(job => (
                <tr key={job.id} className="jobs-row" onClick={() => { setEditJob(job); setShowModal(true); }}>
                  <td className="jobs-td-title">{job.title}</td>
                  <td>{job.department || '—'}</td>
                  <td>{job.location || '—'}</td>
                  <td>
                    {job.is_remote && (
                      <span className="jobs-badge jobs-badge-remote">Remote</span>
                    )}
                  </td>
                  <td>{job.applicant_count || 0}</td>
                  <td>
                    <span className={`jobs-badge ${job.status === 'active' ? 'jobs-badge-active' : 'jobs-badge-inactive'}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>{formatDate(job.created_at)}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className={`jobs-copy-btn ${copied === job.id ? 'copied' : ''}`}
                      onClick={() => copyUrl(job)}
                    >
                      {copied === job.id ? '✓ Copied' : 'Copy URL'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <JobModal
          job={editJob}
          recruitToken={recruitToken}
          onClose={() => { setShowModal(false); setEditJob(null); }}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
