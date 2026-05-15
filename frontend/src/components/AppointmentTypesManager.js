/**
 * Appointment Types Manager
 *
 * Full CRUD management for meeting/appointment types with:
 * - Drag-to-reorder support
 * - Slide-out editor panel
 * - Duplicate/clone functionality
 * - Buffer time, max per day, and default mode configuration
 * - Intake question builder
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import './AppointmentTypesManager.css';

const DURATION_OPTIONS = [
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 45, label: '45 minutes' },
  { value: 60, label: '1 hour' },
  { value: 90, label: '1.5 hours' },
  { value: 120, label: '2 hours' },
  { value: 180, label: '3 hours' },
  { value: 240, label: '4 hours' },
];

const BUFFER_OPTIONS = [
  { value: 0, label: 'None' },
  { value: 5, label: '5 min' },
  { value: 10, label: '10 min' },
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '60 min' },
];

const MODE_OPTIONS = [
  { value: 'video', label: 'Video', icon: 'fa-video' },
  { value: 'phone', label: 'Phone', icon: 'fa-phone' },
  { value: 'in_person', label: 'In Person', icon: 'fa-building' },
  { value: 'screen_share', label: 'Screen Share', icon: 'fa-desktop' },
];

const COLOR_PRESETS = [
  '#1F3D2E', '#3B82F6', '#B8924A', '#EC4899',
  '#F59E0B', '#2D7A52', '#EF4444', '#B8924A',
  '#14B8A6', '#F97316', '#84CC16', '#06B6D4',
];

const EMPTY_FORM = {
  type_name: '',
  type_key: '',
  description: '',
  duration_minutes: 30,
  allowed_modes: ['video'],
  default_mode: 'video',
  buffer_before: 0,
  buffer_after: 0,
  max_per_day: '',
  color: '#1F3D2E',
  requires_loan: false,
  requires_lead: false,
  is_public: true,
  is_active: true,
  intake_questions: [],
};

const extractErrorMessage = (err) => {
  if (!err) return 'Unknown error';
  if (err?.response?.data?.detail) return err.response.data.detail;
  if (typeof err === 'string') return err;
  if (typeof err.message === 'string') return err.message;
  return String(err);
};

const normalizeType = (t) => ({
  ...t,
  duration_minutes: t.duration_minutes || t.default_duration_minutes || 30,
  requires_loan: t.requires_loan ?? t.requires_loan_id ?? false,
  requires_lead: t.requires_lead ?? t.requires_lead_id ?? false,
  buffer_before: t.buffer_before || 0,
  buffer_after: t.buffer_after || 0,
  default_mode: t.default_mode || (t.allowed_modes && t.allowed_modes[0]) || 'video',
  max_per_day: t.max_per_day || null,
});

// ============================================================================
// TypeCard sub-component
// ============================================================================
const TypeCard = ({
  type, onEdit, onToggle, onDuplicate, onDelete, deleteConfirm, setDeleteConfirm,
  onDragStart, onDragOver, onDragEnd, onDrop, isDragging,
}) => (
  <div
    className={`atm-card ${!type.is_active ? 'inactive' : ''} ${isDragging ? 'dragging' : ''}`}
    draggable={!!type.id}
    onDragStart={onDragStart}
    onDragOver={onDragOver}
    onDragEnd={onDragEnd}
    onDrop={onDrop}
  >
    <div className="atm-card-drag-handle" title="Drag to reorder">
      <i className="fas fa-grip-vertical"></i>
    </div>
    <div className="atm-card-accent" style={{ backgroundColor: type.color || '#1F3D2E' }} />
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
              onChange={() => onToggle(type)}
              aria-label={`${type.is_active ? 'Deactivate' : 'Activate'} ${type.type_name}`}
            />
            <span className="atm-toggle-slider"></span>
          </label>
          <button className="atm-btn-icon" onClick={() => onEdit(type)} title="Edit" aria-label="Edit">
            <i className="fas fa-pen"></i>
          </button>
          <button className="atm-btn-icon" onClick={() => onDuplicate(type)} title="Duplicate" aria-label="Duplicate">
            <i className="fas fa-copy"></i>
          </button>
          {deleteConfirm === type.id ? (
            <span className="atm-delete-confirm">
              <button className="atm-btn-danger-sm" onClick={() => onDelete(type.id)}>Confirm</button>
              <button className="atm-btn-cancel-sm" onClick={() => setDeleteConfirm(null)}>Cancel</button>
            </span>
          ) : (
            <button
              className="atm-btn-icon danger"
              onClick={() => setDeleteConfirm(type.id)}
              title="Delete"
              aria-label="Delete"
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
        {(type.allowed_modes || []).map(mode => {
          const opt = MODE_OPTIONS.find(m => m.value === mode);
          return (
            <span key={mode} className={`atm-badge mode ${mode === type.default_mode ? 'default-mode' : ''}`}>
              <i className={`fas ${opt?.icon || 'fa-circle'}`}></i>
              {opt?.label || mode}
              {mode === type.default_mode && <span className="atm-badge-default">default</span>}
            </span>
          );
        })}
        {type.max_per_day && (
          <span className="atm-badge capacity">
            <i className="fas fa-layer-group"></i> Max {type.max_per_day}/day
          </span>
        )}
        {type.is_public && <span className="atm-badge public">Public</span>}
        {!type.is_active && <span className="atm-badge inactive-badge">Inactive</span>}
      </div>
    </div>
  </div>
);

// ============================================================================
// TypeEditor slide-out panel sub-component
// ============================================================================
const TypeEditor = ({ isOpen, editingType, form, setForm, onSave, onClose, saving }) => {
  const panelRef = useRef(null);

  // Focus trap + escape to close
  useEffect(() => {
    if (!isOpen) return;
    const panel = panelRef.current;
    if (!panel) return;

    const previousFocus = document.activeElement;
    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') { onClose(); return; }
      if (e.key !== 'Tab') return;
      const focusable = panel.querySelectorAll(focusableSelector);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };

    panel.addEventListener('keydown', handleKeyDown);
    // Focus first input after animation
    const timer = setTimeout(() => {
      const firstInput = panel.querySelector('input[type="text"]');
      firstInput?.focus();
    }, 200);

    return () => {
      panel.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
      previousFocus?.focus();
    };
  }, [isOpen, onClose]);

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
      if (modes.length === 0) return prev;
      // If default_mode is being removed, switch default to first remaining mode
      const newDefault = modes.includes(prev.default_mode) ? prev.default_mode : modes[0];
      return { ...prev, allowed_modes: modes, default_mode: newDefault };
    });
  };

  const addQuestion = () => {
    setForm(prev => ({
      ...prev,
      intake_questions: [...prev.intake_questions, { key: `q${Date.now()}`, question: '', type: 'text', required: false }],
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

  if (!isOpen) return null;

  return (
    <>
      <div className="atm-panel-overlay" onClick={onClose} />
      <div className="atm-panel" ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="atm-panel-title">
        <div className="atm-panel-header">
          <h3 id="atm-panel-title">{editingType ? 'Edit Appointment Type' : 'New Appointment Type'}</h3>
          <button className="atm-panel-close" onClick={onClose} aria-label="Close panel">
            <i className="fas fa-times"></i>
          </button>
        </div>

        <div className="atm-panel-body">
          {/* Type Name */}
          <div className="atm-form-group">
            <label htmlFor="atm-name">Name <span className="required">*</span></label>
            <input
              id="atm-name"
              type="text"
              value={form.type_name}
              onChange={e => handleNameChange(e.target.value)}
              placeholder="e.g., Initial Consultation"
            />
          </div>

          {/* Type Key */}
          {!editingType && (
            <div className="atm-form-group">
              <label htmlFor="atm-slug">Type Key</label>
              <input
                id="atm-slug"
                type="text"
                value={form.type_key}
                onChange={e => setForm(prev => ({ ...prev, type_key: e.target.value }))}
                placeholder="auto-generated"
                className="atm-input-muted"
              />
              <span className="atm-hint">Auto-generated from name. Used for API references.</span>
            </div>
          )}

          {/* Description */}
          <div className="atm-form-group">
            <label htmlFor="atm-description">Description</label>
            <textarea
              id="atm-description"
              value={form.description}
              onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
              placeholder="Brief description shown to clients..."
              rows={2}
            />
          </div>

          {/* Duration */}
          <div className="atm-form-group">
            <label htmlFor="atm-duration">Duration</label>
            <select
              id="atm-duration"
              value={form.duration_minutes}
              onChange={e => setForm(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) }))}
            >
              {DURATION_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Buffer Times */}
          <div className="atm-form-row">
            <div className="atm-form-group half">
              <label htmlFor="atm-buffer-before">Buffer Before</label>
              <select
                id="atm-buffer-before"
                value={form.buffer_before}
                onChange={e => setForm(prev => ({ ...prev, buffer_before: parseInt(e.target.value) }))}
              >
                {BUFFER_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <span className="atm-hint">Padding before the meeting</span>
            </div>
            <div className="atm-form-group half">
              <label htmlFor="atm-buffer-after">Buffer After</label>
              <select
                id="atm-buffer-after"
                value={form.buffer_after}
                onChange={e => setForm(prev => ({ ...prev, buffer_after: parseInt(e.target.value) }))}
              >
                {BUFFER_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <span className="atm-hint">Padding after the meeting</span>
            </div>
          </div>

          {/* Max Per Day */}
          <div className="atm-form-group">
            <label htmlFor="atm-max-per-day">Max Per Day</label>
            <input
              id="atm-max-per-day"
              type="number"
              min="1"
              max="50"
              value={form.max_per_day}
              onChange={e => setForm(prev => ({ ...prev, max_per_day: e.target.value === '' ? '' : parseInt(e.target.value) || '' }))}
              placeholder="No limit"
            />
            <span className="atm-hint">Maximum number of this meeting type per day. Leave empty for unlimited.</span>
          </div>

          {/* Allowed Modes */}
          <div className="atm-form-group">
            <label id="atm-meeting-mode-label">Meeting Modes</label>
            <div className="atm-modes-grid" role="group" aria-labelledby="atm-meeting-mode-label">
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

          {/* Default Mode */}
          {form.allowed_modes.length > 1 && (
            <div className="atm-form-group">
              <label htmlFor="atm-default-mode">Default Mode</label>
              <select
                id="atm-default-mode"
                value={form.default_mode}
                onChange={e => setForm(prev => ({ ...prev, default_mode: e.target.value }))}
              >
                {form.allowed_modes.map(mode => {
                  const opt = MODE_OPTIONS.find(m => m.value === mode);
                  return <option key={mode} value={mode}>{opt?.label || mode}</option>;
                })}
              </select>
            </div>
          )}

          {/* Color */}
          <div className="atm-form-group">
            <label id="atm-color-label">Color</label>
            <div className="atm-color-swatches" role="group" aria-labelledby="atm-color-label">
              {COLOR_PRESETS.map(color => (
                <button
                  key={color}
                  type="button"
                  className={`atm-swatch ${form.color === color ? 'selected' : ''}`}
                  style={{ backgroundColor: color }}
                  onClick={() => setForm(prev => ({ ...prev, color }))}
                  aria-label={`Select color ${color}`}
                  aria-pressed={form.color === color}
                />
              ))}
            </div>
          </div>

          {/* Options */}
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
            {form.intake_questions.length === 0 && (
              <p className="atm-hint" style={{ marginBottom: 8 }}>No intake questions yet. Add questions that clients answer when booking.</p>
            )}
            {form.intake_questions.map((q, i) => (
              <div key={i} className="atm-question-row">
                <input
                  type="text"
                  value={q.question}
                  onChange={e => updateQuestion(i, 'question', e.target.value)}
                  placeholder="Enter a question..."
                />
                <select
                  value={q.type || 'text'}
                  onChange={e => updateQuestion(i, 'type', e.target.value)}
                  className="atm-question-type"
                >
                  <option value="text">Text</option>
                  <option value="boolean">Yes/No</option>
                  <option value="select">Select</option>
                  <option value="date">Date</option>
                </select>
                <label className="atm-checkbox compact">
                  <input
                    type="checkbox"
                    checked={q.required}
                    onChange={e => updateQuestion(i, 'required', e.target.checked)}
                  />
                  Req
                </label>
                <button type="button" className="atm-btn-icon danger" onClick={() => removeQuestion(i)}>
                  <i className="fas fa-times"></i>
                </button>
              </div>
            ))}
            <button type="button" className="atm-btn-text" onClick={addQuestion}>
              <i className="fas fa-plus"></i> Add Question
            </button>
          </div>
        </div>

        <div className="atm-panel-footer">
          <button className="atm-btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="atm-btn-primary"
            onClick={onSave}
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
    </>
  );
};

// ============================================================================
// Main AppointmentTypesManager component
// ============================================================================
const AppointmentTypesManager = () => {
  const [types, setTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingType, setEditingType] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // Drag state
  const dragItem = useRef(null);
  const dragOverItem = useRef(null);

  const showSuccess = (msg) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const seedDefaults = useCallback(async () => {
    try {
      await api.post('/api/v1/scheduler/seed-defaults');
      return true;
    } catch {
      return false;
    }
  }, []);

  const loadTypes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/api/v1/scheduler/appointment-types', { params: { include_inactive: true } });
      const data = res.data;

      if (data.source === 'defaults') {
        const seeded = await seedDefaults();
        if (seeded) {
          const res2 = await api.get('/api/v1/scheduler/appointment-types', { params: { include_inactive: true } });
          setTypes((res2.data.appointment_types || []).map(normalizeType));
          return;
        }
        setTypes((data.appointment_types || []).map(normalizeType));
      } else {
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

  // ---- Key generation ----
  const generateKey = (name) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, '')
      .replace(/\s+/g, '_')
      .substring(0, 50);
  };

  // ---- CRUD handlers ----
  const openCreate = () => {
    setEditingType(null);
    setForm({ ...EMPTY_FORM });
    setPanelOpen(true);
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
      default_mode: type.default_mode || (type.allowed_modes && type.allowed_modes[0]) || 'video',
      buffer_before: type.buffer_before || 0,
      buffer_after: type.buffer_after || 0,
      max_per_day: type.max_per_day || '',
      color: type.color || '#1F3D2E',
      requires_loan: type.requires_loan ?? type.requires_loan_id ?? false,
      requires_lead: type.requires_lead ?? type.requires_lead_id ?? false,
      is_public: type.is_public ?? true,
      is_active: type.is_active ?? true,
      intake_questions: type.intake_questions || [],
    });
    setPanelOpen(true);
  };

  const handleSave = async () => {
    if (!form.type_name.trim()) return;
    setSaving(true);
    try {
      const type_key = form.type_key || generateKey(form.type_name);

      const payload = editingType ? {
        type_name: form.type_name,
        description: form.description,
        default_duration_minutes: form.duration_minutes,
        allowed_modes: form.allowed_modes,
        default_mode: form.default_mode,
        buffer_before: form.buffer_before,
        buffer_after: form.buffer_after,
        max_per_day: form.max_per_day || null,
        color: form.color,
        is_active: form.is_active,
        is_public: form.is_public,
        intake_questions: form.intake_questions.map((q, i) => ({
          key: q.key || `q${i}`,
          question: q.question,
          type: q.type || 'text',
          required: q.required || false,
          ...(q.options ? { options: q.options } : {}),
        })),
      } : {
        type_key,
        type_name: form.type_name,
        description: form.description,
        default_duration_minutes: form.duration_minutes,
        allowed_modes: form.allowed_modes,
        default_mode: form.default_mode,
        buffer_before: form.buffer_before,
        buffer_after: form.buffer_after,
        max_per_day: form.max_per_day || null,
        color: form.color,
        requires_loan_id: form.requires_loan,
        requires_lead_id: form.requires_lead,
        is_public: form.is_public,
        intake_questions: form.intake_questions.map((q, i) => ({
          key: q.key || `q${i}`,
          question: q.question,
          type: q.type || 'text',
          required: q.required || false,
          ...(q.options ? { options: q.options } : {}),
        })),
      };

      if (editingType) {
        await api.put(`/api/v1/scheduler/appointment-types/${editingType.id}`, payload);
        showSuccess('Appointment type updated');
      } else {
        await api.post('/api/v1/scheduler/appointment-types', payload);
        showSuccess('Appointment type created');
      }

      setPanelOpen(false);
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
      await api.put(`/api/v1/scheduler/appointment-types/${type.id}`, { is_active: !type.is_active });
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
      await api.delete(`/api/v1/scheduler/appointment-types/${id}`);
      setDeleteConfirm(null);
      showSuccess('Appointment type deactivated');
      await loadTypes();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  const handleDuplicate = async (type) => {
    if (!type.id) {
      setError('Cannot duplicate default types.');
      return;
    }
    try {
      const res = await api.post(`/api/v1/scheduler/appointment-types/${type.id}/duplicate`);
      showSuccess(`Duplicated as "${res.data.type_name}"`);
      await loadTypes();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  // ---- Drag-to-reorder handlers ----
  const handleDragStart = (index) => {
    dragItem.current = index;
  };

  const handleDragOver = (e, index) => {
    e.preventDefault();
    dragOverItem.current = index;
  };

  const handleDragEnd = async () => {
    if (dragItem.current === null || dragOverItem.current === null) return;
    if (dragItem.current === dragOverItem.current) {
      dragItem.current = null;
      dragOverItem.current = null;
      return;
    }

    const reordered = [...types];
    const [removed] = reordered.splice(dragItem.current, 1);
    reordered.splice(dragOverItem.current, 0, removed);

    setTypes(reordered);
    dragItem.current = null;
    dragOverItem.current = null;

    // Persist reorder to backend
    const orderedIds = reordered.filter(t => t.id).map(t => t.id);
    if (orderedIds.length > 0) {
      try {
        await api.put('/api/v1/scheduler/appointment-types/reorder', { ordered_ids: orderedIds });
      } catch (err) {
        setError(extractErrorMessage(err));
        await loadTypes(); // Revert on error
      }
    }
  };

  // ---- Render ----
  if (loading) {
    return (
      <div className="atm-container">
        <div className="atm-loading" role="status">
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
          <p className="atm-subtitle">
            Define the types of meetings available for booking.
            {types.length > 1 && ' Drag to reorder.'}
          </p>
        </div>
        <button className="atm-btn-primary" onClick={openCreate} aria-label="Create new appointment type">
          <i className="fas fa-plus"></i> New Type
        </button>
      </div>

      {error && (
        <div className="atm-error" role="alert">
          <i className="fas fa-exclamation-circle"></i>
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss error">&times;</button>
        </div>
      )}

      {successMsg && (
        <div className="atm-success" role="status">
          <i className="fas fa-check-circle"></i>
          {successMsg}
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
          {types.map((type, index) => (
            <TypeCard
              key={type.id || index}
              type={type}
              onEdit={openEdit}
              onToggle={handleToggleActive}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
              deleteConfirm={deleteConfirm}
              setDeleteConfirm={setDeleteConfirm}
              onDragStart={() => handleDragStart(index)}
              onDragOver={(e) => handleDragOver(e, index)}
              onDragEnd={handleDragEnd}
              onDrop={handleDragEnd}
              isDragging={dragItem.current === index}
            />
          ))}
        </div>
      )}

      {/* Slide-out Editor Panel */}
      <TypeEditor
        isOpen={panelOpen}
        editingType={editingType}
        form={form}
        setForm={setForm}
        onSave={handleSave}
        onClose={() => setPanelOpen(false)}
        saving={saving}
      />
    </div>
  );
};

export default AppointmentTypesManager;
