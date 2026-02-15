/**
 * Appointment Types Manager
 *
 * CRUD management for meeting/appointment types.
 * Self-contained component with own state, loading, and API calls.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../utils/auth';
import './AppointmentTypesManager.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const DURATION_OPTIONS = [
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 45, label: '45 minutes' },
  { value: 60, label: '60 minutes' },
  { value: 90, label: '90 minutes' },
  { value: 120, label: '2 hours' },
];

const MODE_OPTIONS = [
  { value: 'video', label: 'Video', icon: 'fa-video' },
  { value: 'phone', label: 'Phone', icon: 'fa-phone' },
  { value: 'in_person', label: 'In Person', icon: 'fa-building' },
  { value: 'screen_share', label: 'Screen Share', icon: 'fa-desktop' },
];

const COLOR_PRESETS = [
  '#218D8D', '#3B82F6', '#8B5CF6', '#EC4899',
  '#F59E0B', '#10B981', '#EF4444', '#6366F1',
];

const EMPTY_FORM = {
  type_name: '',
  type_key: '',
  description: '',
  duration_minutes: 30,
  allowed_modes: ['video'],
  color: '#218D8D',
  requires_loan: false,
  requires_lead: false,
  is_public: true,
  is_active: true,
  intake_questions: [],
};

const extractErrorMessage = (err) => {
  if (!err) return 'Unknown error';
  if (typeof err === 'string') return err;
  if (typeof err.message === 'string') return err.message;
  return String(err);
};

const normalizeType = (t) => ({
  ...t,
  duration_minutes: t.duration_minutes || t.default_duration_minutes || 30,
  requires_loan: t.requires_loan ?? t.requires_loan_id ?? false,
  requires_lead: t.requires_lead ?? t.requires_lead_id ?? false,
});

const AppointmentTypesManager = () => {
  const [types, setTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editingType, setEditingType] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [isDefaults, setIsDefaults] = useState(false);

  const seedDefaults = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/seed-defaults`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  const loadTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('Failed to load appointment types');
      const data = await res.json();

      // If defaults returned (no DB records), seed them first
      if (data.source === 'defaults') {
        setIsDefaults(true);
        const seeded = await seedDefaults();
        if (seeded) {
          // Re-fetch now that defaults are seeded in DB
          const res2 = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types?include_inactive=true`, {
            headers: getAuthHeaders(),
          });
          if (res2.ok) {
            const data2 = await res2.json();
            setTypes((data2.appointment_types || []).map(normalizeType));
            setIsDefaults(false);
            return;
          }
        }
        // Fallback: show defaults as read-only
        setTypes((data.appointment_types || []).map(normalizeType));
      } else {
        setIsDefaults(false);
        setTypes((data.appointment_types || data || []).map(normalizeType));
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [seedDefaults]);

  useEffect(() => {
    loadTypes();
  }, [loadTypes]);

  const generateKey = (name) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, '')
      .replace(/\s+/g, '_')
      .substring(0, 50);
  };

  const handleNameChange = (value) => {
    setForm(prev => ({
      ...prev,
      type_name: value,
      type_key: editingType ? prev.type_key : generateKey(value),
    }));
  };

  const toggleMode = (mode) => {
    setForm(prev => {
      const modes = prev.allowed_modes.includes(mode)
        ? prev.allowed_modes.filter(m => m !== mode)
        : [...prev.allowed_modes, mode];
      return { ...prev, allowed_modes: modes.length > 0 ? modes : prev.allowed_modes };
    });
  };

  const addQuestion = () => {
    setForm(prev => ({
      ...prev,
      intake_questions: [...prev.intake_questions, { question: '', required: false }],
    }));
  };

  const updateQuestion = (index, field, value) => {
    setForm(prev => ({
      ...prev,
      intake_questions: prev.intake_questions.map((q, i) =>
        i === index ? { ...q, [field]: value } : q
      ),
    }));
  };

  const removeQuestion = (index) => {
    setForm(prev => ({
      ...prev,
      intake_questions: prev.intake_questions.filter((_, i) => i !== index),
    }));
  };

  const openCreate = () => {
    setEditingType(null);
    setForm({ ...EMPTY_FORM });
    setShowModal(true);
  };

  const openEdit = (type) => {
    if (!type.id) {
      setError('Cannot edit default types. Please save your configuration first.');
      return;
    }
    setEditingType(type);
    setForm({
      type_name: type.type_name || '',
      type_key: type.type_key || '',
      description: type.description || '',
      duration_minutes: type.duration_minutes || type.default_duration_minutes || 30,
      allowed_modes: type.allowed_modes || ['video'],
      color: type.color || '#218D8D',
      requires_loan: type.requires_loan ?? type.requires_loan_id ?? false,
      requires_lead: type.requires_lead ?? type.requires_lead_id ?? false,
      is_public: type.is_public ?? true,
      is_active: type.is_active ?? true,
      intake_questions: type.intake_questions || [],
    });
    setShowModal(true);
  };

  const handleSave = async () => {
    if (!form.type_name.trim()) return;
    setSaving(true);
    try {
      const type_key = form.type_key || generateKey(form.type_name);

      // Map frontend field names to backend field names
      const payload = editingType ? {
        type_name: form.type_name,
        description: form.description,
        default_duration_minutes: form.duration_minutes,
        allowed_modes: form.allowed_modes,
        color: form.color,
        is_active: form.is_active,
        is_public: form.is_public,
        intake_questions: form.intake_questions,
      } : {
        type_key,
        type_name: form.type_name,
        description: form.description,
        default_duration_minutes: form.duration_minutes,
        allowed_modes: form.allowed_modes,
        color: form.color,
        requires_loan_id: form.requires_loan,
        requires_lead_id: form.requires_lead,
        is_public: form.is_public,
        intake_questions: form.intake_questions,
      };

      const url = editingType
        ? `${API_BASE}/api/v1/scheduler/appointment-types/${editingType.id}`
        : `${API_BASE}/api/v1/scheduler/appointment-types`;

      const res = await fetch(url, {
        method: editingType ? 'PUT' : 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const detail = errData.detail;
        const errorMsg = typeof detail === 'string' ? detail
          : Array.isArray(detail) ? detail.map(d => d.msg || String(d)).join(', ')
          : errData.error?.message || 'Failed to save';
        throw new Error(errorMsg);
      }

      setShowModal(false);
      await loadTypes();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (type) => {
    if (!type.id) {
      setError('Cannot modify default types. Please save your configuration first.');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types/${type.id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ is_active: !type.is_active }),
      });
      if (!res.ok) throw new Error('Failed to update appointment type');
      await loadTypes();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleDelete = async (id) => {
    if (!id) {
      setError('Cannot delete default types.');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/appointment-types/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('Failed to delete appointment type');
      setDeleteConfirm(null);
      await loadTypes();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  if (loading) {
    return (
      <div className="atm-container">
        <div className="atm-loading">
          <div className="atm-spinner"></div>
          <p>Loading appointment types...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="atm-container">
      <div className="atm-header">
        <div>
          <h2>Appointment Types</h2>
          <p className="atm-subtitle">Define the types of meetings available for booking.</p>
        </div>
        <button className="atm-btn-primary" onClick={openCreate}>
          <i className="fas fa-plus"></i> New Type
        </button>
      </div>

      {error && (
        <div className="atm-error">
          <i className="fas fa-exclamation-circle"></i>
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {types.length === 0 ? (
        <div className="atm-empty">
          <i className="fas fa-calendar-plus"></i>
          <h3>No Appointment Types</h3>
          <p>Create your first appointment type to get started.</p>
          <button className="atm-btn-primary" onClick={openCreate}>
            <i className="fas fa-plus"></i> Create Appointment Type
          </button>
        </div>
      ) : (
        <div className="atm-list">
          {types.map(type => (
            <div key={type.id} className={`atm-card ${!type.is_active ? 'inactive' : ''}`}>
              <div className="atm-card-accent" style={{ backgroundColor: type.color || '#218D8D' }} />
              <div className="atm-card-body">
                <div className="atm-card-top">
                  <div className="atm-card-info">
                    <h3>{type.type_name}</h3>
                    {type.description && <p className="atm-card-desc">{type.description}</p>}
                  </div>
                  <div className="atm-card-actions">
                    <label className="atm-toggle" title={type.is_active ? 'Active' : 'Inactive'}>
                      <input
                        type="checkbox"
                        checked={type.is_active}
                        onChange={() => handleToggleActive(type)}
                      />
                      <span className="atm-toggle-slider"></span>
                    </label>
                    <button className="atm-btn-icon" onClick={() => openEdit(type)} title="Edit">
                      <i className="fas fa-pen"></i>
                    </button>
                    {deleteConfirm === type.id ? (
                      <span className="atm-delete-confirm">
                        <button className="atm-btn-danger-sm" onClick={() => handleDelete(type.id)}>
                          Confirm
                        </button>
                        <button className="atm-btn-cancel-sm" onClick={() => setDeleteConfirm(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        className="atm-btn-icon danger"
                        onClick={() => setDeleteConfirm(type.id)}
                        title="Delete"
                      >
                        <i className="fas fa-trash"></i>
                      </button>
                    )}
                  </div>
                </div>
                <div className="atm-card-badges">
                  <span className="atm-badge duration">
                    <i className="fas fa-clock"></i> {type.duration_minutes} min
                  </span>
                  {(type.allowed_modes || []).map(mode => (
                    <span key={mode} className="atm-badge mode">
                      <i className={`fas ${MODE_OPTIONS.find(m => m.value === mode)?.icon || 'fa-circle'}`}></i>
                      {MODE_OPTIONS.find(m => m.value === mode)?.label || mode}
                    </span>
                  ))}
                  {type.is_public && <span className="atm-badge public">Public</span>}
                  {!type.is_active && <span className="atm-badge inactive">Inactive</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="scheduler-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="scheduler-modal" onClick={e => e.stopPropagation()}>
            <div className="scheduler-modal-header">
              <h3>{editingType ? 'Edit Appointment Type' : 'New Appointment Type'}</h3>
              <button className="scheduler-modal-close" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="scheduler-modal-body">
              {/* Type Name */}
              <div className="atm-form-group">
                <label>Type Name <span className="required">*</span></label>
                <input
                  type="text"
                  value={form.type_name}
                  onChange={e => handleNameChange(e.target.value)}
                  placeholder="e.g., Initial Consultation"
                />
              </div>

              {/* Type Key */}
              <div className="atm-form-group">
                <label>Type Key</label>
                <input
                  type="text"
                  value={form.type_key}
                  onChange={e => setForm(prev => ({ ...prev, type_key: e.target.value }))}
                  placeholder="auto-generated"
                  className="atm-input-muted"
                />
                <span className="atm-hint">Auto-generated from name. Used for API references.</span>
              </div>

              {/* Description */}
              <div className="atm-form-group">
                <label>Description</label>
                <textarea
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Brief description shown to clients..."
                  rows={2}
                />
              </div>

              {/* Duration */}
              <div className="atm-form-group">
                <label>Duration</label>
                <select
                  value={form.duration_minutes}
                  onChange={e => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
                >
                  {DURATION_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Allowed Modes */}
              <div className="atm-form-group">
                <label>Allowed Modes</label>
                <div className="atm-modes-grid">
                  {MODE_OPTIONS.map(mode => (
                    <label
                      key={mode.value}
                      className={`atm-mode-check ${form.allowed_modes.includes(mode.value) ? 'selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={form.allowed_modes.includes(mode.value)}
                        onChange={() => toggleMode(mode.value)}
                      />
                      <i className={`fas ${mode.icon}`}></i>
                      {mode.label}
                    </label>
                  ))}
                </div>
              </div>

              {/* Color */}
              <div className="atm-form-group">
                <label>Color</label>
                <div className="atm-color-swatches">
                  {COLOR_PRESETS.map(color => (
                    <button
                      key={color}
                      type="button"
                      className={`atm-swatch ${form.color === color ? 'selected' : ''}`}
                      style={{ backgroundColor: color }}
                      onClick={() => setForm(prev => ({ ...prev, color }))}
                    />
                  ))}
                </div>
              </div>

              {/* Options Row */}
              <div className="atm-form-group">
                <label>Options</label>
                <div className="atm-options-row">
                  <label className="atm-checkbox">
                    <input
                      type="checkbox"
                      checked={form.requires_loan}
                      onChange={e => setForm(prev => ({ ...prev, requires_loan: e.target.checked }))}
                    />
                    Requires Loan
                  </label>
                  <label className="atm-checkbox">
                    <input
                      type="checkbox"
                      checked={form.requires_lead}
                      onChange={e => setForm(prev => ({ ...prev, requires_lead: e.target.checked }))}
                    />
                    Requires Lead
                  </label>
                  <label className="atm-checkbox">
                    <input
                      type="checkbox"
                      checked={form.is_public}
                      onChange={e => setForm(prev => ({ ...prev, is_public: e.target.checked }))}
                    />
                    Public
                  </label>
                </div>
              </div>

              {/* Intake Questions */}
              <div className="atm-form-group">
                <label>Intake Questions</label>
                {form.intake_questions.map((q, i) => (
                  <div key={i} className="atm-question-row">
                    <input
                      type="text"
                      value={q.question}
                      onChange={e => updateQuestion(i, 'question', e.target.value)}
                      placeholder="Enter a question..."
                    />
                    <label className="atm-checkbox compact">
                      <input
                        type="checkbox"
                        checked={q.required}
                        onChange={e => updateQuestion(i, 'required', e.target.checked)}
                      />
                      Required
                    </label>
                    <button
                      type="button"
                      className="atm-btn-icon danger"
                      onClick={() => removeQuestion(i)}
                    >
                      <i className="fas fa-times"></i>
                    </button>
                  </div>
                ))}
                <button type="button" className="atm-btn-text" onClick={addQuestion}>
                  <i className="fas fa-plus"></i> Add Question
                </button>
              </div>
            </div>

            <div className="scheduler-modal-footer">
              <button className="atm-btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="atm-btn-primary"
                onClick={handleSave}
                disabled={saving || !form.type_name.trim()}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                ) : (
                  editingType ? 'Save Changes' : 'Create Type'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AppointmentTypesManager;
