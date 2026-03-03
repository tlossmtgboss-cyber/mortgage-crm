/**
 * Blocked Time Manager
 *
 * Manage PTO, holidays, focus blocks, and custom blocked time periods.
 * Self-contained component with own state, loading, and API calls.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './BlockedTimeManager.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const BLOCK_TYPES = [
  { value: 'pto', label: 'PTO', icon: 'fa-umbrella-beach', color: '#0d9488' },
  { value: 'holiday', label: 'Holiday', icon: 'fa-gift', color: '#dc2626' },
  { value: 'focus', label: 'Focus Time', icon: 'fa-bullseye', color: '#7c3aed' },
  { value: 'custom', label: 'Custom', icon: 'fa-clock', color: '#64748b' },
];

const RECURRENCE_OPTIONS = [
  { value: 'none', label: 'No Recurrence' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
];

const formatDateRange = (start, end, allDay) => {
  if (!start) return '';
  const opts = allDay
    ? { month: 'short', day: 'numeric', year: 'numeric' }
    : { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' };

  const startDate = new Date(start);
  const endDate = end ? new Date(end) : null;

  const startStr = startDate.toLocaleDateString('en-US', opts);
  if (!endDate) return startStr;

  // Same day check
  if (startDate.toDateString() === endDate.toDateString()) {
    if (allDay) return startStr;
    return `${startStr} - ${endDate.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
  }

  return `${startStr} - ${endDate.toLocaleDateString('en-US', opts)}`;
};

const BlockedTimeManager = () => {
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [viewFilter, setViewFilter] = useState('upcoming');
  const [typeFilter, setTypeFilter] = useState(null);
  const [form, setForm] = useState({
    title: '',
    block_type: 'pto',
    all_day: true,
    start_time: '',
    end_time: '',
    start_date: '',
    end_date: '',
    description: '',
    applies_to_all: false,
    is_recurring: false,
    recurrence_pattern: 'none',
  });

  const loadBlocks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/blocked-times`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('Failed to load blocked times');
      const data = await res.json();
      setBlocks(data.blocked_times || data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBlocks();
  }, [loadBlocks]);

  const getFilteredBlocks = () => {
    let filtered = [...blocks];

    // View filter
    if (viewFilter === 'upcoming') {
      const now = new Date().toISOString();
      filtered = filtered.filter(b => (b.end_time || b.end_date || b.start_time || b.start_date) >= now);
    }

    // Type filter
    if (typeFilter) {
      filtered = filtered.filter(b => b.block_type === typeFilter);
    }

    // Sort by start date
    filtered.sort((a, b) => {
      const aDate = a.start_time || a.start_date || '';
      const bDate = b.start_time || b.start_date || '';
      return aDate.localeCompare(bDate);
    });

    return filtered;
  };

  const getTypeCounts = () => {
    const counts = {};
    blocks.forEach(b => {
      counts[b.block_type] = (counts[b.block_type] || 0) + 1;
    });
    return counts;
  };

  const openCreate = () => {
    const today = new Date().toISOString().split('T')[0];
    setForm({
      title: '',
      block_type: 'pto',
      all_day: true,
      start_time: '',
      end_time: '',
      start_date: today,
      end_date: today,
      description: '',
      applies_to_all: false,
      is_recurring: false,
      recurrence_pattern: 'none',
    });
    setShowModal(true);
  };

  const handleSave = async () => {
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        block_type: form.block_type,
        all_day: form.all_day,
        description: form.description || null,
        applies_to_all: form.applies_to_all,
        is_recurring: form.is_recurring,
        recurrence_pattern: form.is_recurring ? form.recurrence_pattern : null,
      };

      if (form.all_day) {
        payload.start_time = form.start_date ? `${form.start_date}T00:00:00` : null;
        payload.end_time = form.end_date ? `${form.end_date}T23:59:59` : null;
      } else {
        payload.start_time = form.start_time || null;
        payload.end_time = form.end_time || null;
      }

      const res = await fetch(`${API_BASE}/api/v1/scheduler/blocked-times`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.error?.message || 'Failed to create blocked time');
      }

      setShowModal(false);
      await loadBlocks();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/blocked-times/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('Failed to delete');
      setDeleteConfirm(null);
      await loadBlocks();
    } catch (err) {
      setError(err.message);
    }
  };

  const typeCounts = getTypeCounts();
  const filteredBlocks = getFilteredBlocks();

  if (loading) {
    return (
      <div className="btm-container">
        <div className="btm-loading">
          <div className="btm-spinner"></div>
          <p>Loading blocked times...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="btm-container">
      <div className="btm-header">
        <div>
          <h2>Blocked Time</h2>
          <p className="btm-subtitle">Manage PTO, holidays, focus time, and other blocked periods.</p>
        </div>
        <button className="btm-btn-primary" onClick={openCreate} aria-label="Create new blocked time period">
          <i className="fas fa-plus"></i> Block Time
        </button>
      </div>

      {error && (
        <div className="btm-error" role="alert">
          <i className="fas fa-exclamation-circle"></i>
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Filters */}
      <div className="btm-filters">
        <div className="btm-view-toggle">
          <button
            className={`btm-filter-btn ${viewFilter === 'upcoming' ? 'active' : ''}`}
            onClick={() => setViewFilter('upcoming')}
            aria-label="Show upcoming blocked times"
          >
            Upcoming
          </button>
          <button
            className={`btm-filter-btn ${viewFilter === 'all' ? 'active' : ''}`}
            onClick={() => setViewFilter('all')}
            aria-label="Show all blocked times"
          >
            All
          </button>
        </div>
        <div className="btm-type-filters">
          <button
            className={`btm-pill ${!typeFilter ? 'active' : ''}`}
            onClick={() => setTypeFilter(null)}
            aria-label="Filter by All types"
          >
            All ({blocks.length})
          </button>
          {BLOCK_TYPES.map(bt => (
            <button
              key={bt.value}
              className={`btm-pill ${typeFilter === bt.value ? 'active' : ''}`}
              onClick={() => setTypeFilter(typeFilter === bt.value ? null : bt.value)}
              style={typeFilter === bt.value ? { borderColor: bt.color, color: bt.color } : {}}
              aria-label={`Filter by ${bt.label}`}
            >
              <i className={`fas ${bt.icon}`}></i>
              {bt.label} ({typeCounts[bt.value] || 0})
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      {filteredBlocks.length === 0 ? (
        <div className="btm-empty">
          <i className="fas fa-calendar-times"></i>
          <h3>No Blocked Times</h3>
          <p>{typeFilter ? `No ${typeFilter} blocks found.` : 'No blocked time periods scheduled.'}</p>
          <button className="btm-btn-primary" onClick={openCreate}>
            <i className="fas fa-plus"></i> Block Time
          </button>
        </div>
      ) : (
        <div className="btm-list">
          {filteredBlocks.map(block => {
            const typeInfo = BLOCK_TYPES.find(t => t.value === block.block_type) || BLOCK_TYPES[3];
            return (
              <div key={block.id} className="btm-card">
                <div className="btm-card-icon" style={{ backgroundColor: `${typeInfo.color}15`, color: typeInfo.color }}>
                  <i className={`fas ${typeInfo.icon}`}></i>
                </div>
                <div className="btm-card-body">
                  <div className="btm-card-top">
                    <div className="btm-card-info">
                      <h3>{block.title}</h3>
                      <p className="btm-card-date">
                        {formatDateRange(
                          block.start_time || block.start_date,
                          block.end_time || block.end_date,
                          block.all_day
                        )}
                      </p>
                    </div>
                    <div className="btm-card-actions">
                      {deleteConfirm === block.id ? (
                        <span className="btm-delete-confirm">
                          <button className="btm-btn-danger-sm" onClick={() => handleDelete(block.id)}>
                            Delete
                          </button>
                          <button className="btm-btn-cancel-sm" onClick={() => setDeleteConfirm(null)}>
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          className="btm-btn-icon danger"
                          onClick={() => setDeleteConfirm(block.id)}
                          title="Delete"
                          aria-label="Delete this blocked time"
                        >
                          <i className="fas fa-trash"></i>
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="btm-card-badges">
                    {block.all_day && <span className="btm-badge all-day">All Day</span>}
                    {block.is_recurring && (
                      <span className="btm-badge recurring">
                        <i className="fas fa-redo"></i> Recurring
                      </span>
                    )}
                    {block.applies_to_all && (
                      <span className="btm-badge company">
                        <i className="fas fa-users"></i> Company-wide
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="scheduler-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
            <div className="scheduler-modal-header">
              <h3>Block Time</h3>
              <button className="scheduler-modal-close" onClick={() => setShowModal(false)} aria-label="Close">
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="scheduler-modal-body">
              {/* Title */}
              <div className="btm-form-group">
                <label htmlFor="btm-title">Title <span className="required">*</span></label>
                <input
                  id="btm-title"
                  type="text"
                  value={form.title}
                  onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="e.g., Vacation, Team Offsite"
                />
              </div>

              {/* Block Type */}
              <div className="btm-form-group">
                <label htmlFor="btm-type">Block Type</label>
                <div className="btm-type-cards" id="btm-type" role="radiogroup" aria-label="Block Type">
                  {BLOCK_TYPES.map(bt => (
                    <label
                      key={bt.value}
                      className={`btm-type-card ${form.block_type === bt.value ? 'selected' : ''}`}
                      style={form.block_type === bt.value ? { borderColor: bt.color } : {}}
                    >
                      <input
                        type="radio"
                        name="block_type"
                        value={bt.value}
                        checked={form.block_type === bt.value}
                        onChange={e => setForm(prev => ({ ...prev, block_type: e.target.value }))}
                      />
                      <i className={`fas ${bt.icon}`} style={{ color: bt.color }}></i>
                      <span>{bt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* All Day Toggle */}
              <div className="btm-form-group">
                <label className="btm-checkbox">
                  <input
                    type="checkbox"
                    checked={form.all_day}
                    onChange={e => setForm(prev => ({ ...prev, all_day: e.target.checked }))}
                  />
                  All Day
                </label>
              </div>

              {/* Date/Time Inputs */}
              {form.all_day ? (
                <div className="btm-date-row">
                  <div className="btm-form-group">
                    <label htmlFor="btm-start-date">Start Date</label>
                    <input
                      id="btm-start-date"
                      type="date"
                      value={form.start_date}
                      onChange={e => setForm(prev => ({ ...prev, start_date: e.target.value }))}
                    />
                  </div>
                  <div className="btm-form-group">
                    <label htmlFor="btm-end-date">End Date</label>
                    <input
                      id="btm-end-date"
                      type="date"
                      value={form.end_date}
                      onChange={e => setForm(prev => ({ ...prev, end_date: e.target.value }))}
                    />
                  </div>
                </div>
              ) : (
                <div className="btm-date-row">
                  <div className="btm-form-group">
                    <label htmlFor="btm-start-time">Start</label>
                    <input
                      id="btm-start-time"
                      type="datetime-local"
                      value={form.start_time}
                      onChange={e => setForm(prev => ({ ...prev, start_time: e.target.value }))}
                    />
                  </div>
                  <div className="btm-form-group">
                    <label htmlFor="btm-end-time">End</label>
                    <input
                      id="btm-end-time"
                      type="datetime-local"
                      value={form.end_time}
                      onChange={e => setForm(prev => ({ ...prev, end_time: e.target.value }))}
                    />
                  </div>
                </div>
              )}

              {/* Description */}
              <div className="btm-form-group">
                <label htmlFor="btm-reason">Description</label>
                <textarea
                  id="btm-reason"
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Optional notes..."
                  rows={2}
                />
              </div>

              {/* Options */}
              <div className="btm-form-group">
                <label className="btm-checkbox" htmlFor="btm-all-users">
                  <input
                    id="btm-all-users"
                    type="checkbox"
                    checked={form.applies_to_all}
                    onChange={e => setForm(prev => ({ ...prev, applies_to_all: e.target.checked }))}
                  />
                  Applies to All Users
                </label>
              </div>

              <div className="btm-form-group">
                <label className="btm-checkbox" htmlFor="btm-recurring">
                  <input
                    id="btm-recurring"
                    type="checkbox"
                    checked={form.is_recurring}
                    onChange={e => setForm(prev => ({ ...prev, is_recurring: e.target.checked }))}
                  />
                  Recurring
                </label>
                {form.is_recurring && (
                  <select
                    id="btm-recurrence-pattern"
                    className="btm-recurrence-select"
                    value={form.recurrence_pattern}
                    onChange={e => setForm(prev => ({ ...prev, recurrence_pattern: e.target.value }))}
                    aria-label="Recurrence pattern"
                  >
                    {RECURRENCE_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            <div className="scheduler-modal-footer">
              <button className="btm-btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="btm-btn-primary"
                onClick={handleSave}
                disabled={saving || !form.title.trim()}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                ) : (
                  'Block Time'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BlockedTimeManager;
