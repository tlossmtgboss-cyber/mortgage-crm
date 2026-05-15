import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

const LOCATION_TYPE_OPTIONS = [
  { value: 'virtual', label: 'Video Call' },
  { value: 'phone', label: 'Phone Call' },
  { value: 'in_person', label: 'In Person' },
];

const DURATION_PRESETS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '1 hour' },
  { value: 90, label: '1.5 hours' },
  { value: 120, label: '2 hours' },
];

const BUFFER_OPTIONS = [
  { value: 0, label: 'None' },
  { value: 5, label: '5 min' },
  { value: 10, label: '10 min' },
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
];

const LOCATION_ICONS = {
  virtual: '\uD83D\uDCF9',
  phone: '\uD83D\uDCDE',
  in_person: '\uD83D\uDCCD',
};

function durationLabel(minutes) {
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? 's' : ''}`;
  }
  return `${minutes} min`;
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Template Card
// ---------------------------------------------------------------------------

function TemplateCard({ template, onEdit, onDuplicate, onDelete, onToggle }) {
  const locationInfo = LOCATION_TYPE_OPTIONS.find(o => o.value === template.location_type) || {};
  const icon = LOCATION_ICONS[template.location_type] || '';

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 16,
        marginBottom: 12,
        opacity: template.is_active ? 1 : 0.55,
        background: template.is_active ? '#fff' : '#f9fafb',
        transition: 'opacity 0.2s',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <strong style={{ fontSize: 15 }}>{template.name}</strong>
            {template.is_default && (
              <span style={{
                padding: '1px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                background: '#dbeafe', color: '#1e40af',
              }}>
                Default
              </span>
            )}
          </div>
          {template.description && (
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 6 }}>
              {template.description}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <label style={{ position: 'relative', display: 'inline-block', width: 40, height: 22, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={template.is_active}
              onChange={() => onToggle(template.id, !template.is_active)}
              style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
              aria-label={`Toggle ${template.name}`}
            />
            <span
              style={{
                position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: template.is_active ? '#3b82f6' : '#d1d5db',
                borderRadius: 22, transition: 'background-color 0.2s',
              }}
            >
              <span
                style={{
                  position: 'absolute', height: 16, width: 16,
                  left: template.is_active ? 20 : 3, bottom: 3,
                  backgroundColor: '#fff', borderRadius: '50%', transition: 'left 0.2s',
                }}
              />
            </span>
          </label>
        </div>
      </div>

      {/* Badges row */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 13, marginBottom: 10 }}>
        <span style={{ padding: '2px 10px', borderRadius: 12, background: '#f3f4f6', color: '#374151', fontWeight: 500 }}>
          {durationLabel(template.duration_minutes)}
        </span>
        <span style={{ padding: '2px 10px', borderRadius: 12, background: '#f0fdf4', color: '#166534', fontWeight: 500 }}>
          {icon} {locationInfo.label || template.location_type}
        </span>
        {template.appointment_type && (
          <span style={{ padding: '2px 10px', borderRadius: 12, background: '#fef3c7', color: '#92400e', fontWeight: 500 }}>
            {template.appointment_type}
          </span>
        )}
        {(template.buffer_before_minutes > 0 || template.buffer_after_minutes > 0) && (
          <span style={{ padding: '2px 10px', borderRadius: 12, background: '#FAF3E5', color: '#6B5424', fontWeight: 500 }}>
            Buffer: {template.buffer_before_minutes}m / {template.buffer_after_minutes}m
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={() => onEdit(template)}
          style={{
            padding: '5px 14px', borderRadius: 6, border: '1px solid #d1d5db',
            background: '#fff', cursor: 'pointer', fontSize: 13,
          }}
        >
          Edit
        </button>
        <button
          onClick={() => onDuplicate(template.id)}
          style={{
            padding: '5px 14px', borderRadius: 6, border: '1px solid #d1d5db',
            background: '#fff', cursor: 'pointer', fontSize: 13,
          }}
        >
          Duplicate
        </button>
        <button
          onClick={() => onDelete(template.id)}
          style={{
            padding: '5px 14px', borderRadius: 6, border: '1px solid #fca5a5',
            background: '#fef2f2', color: '#dc2626', cursor: 'pointer', fontSize: 13,
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Template Editor (slide-out / inline form)
// ---------------------------------------------------------------------------

function TemplateEditor({ template, onSave, onCancel }) {
  const isNew = !template?.id;
  const [form, setForm] = useState({
    name: template?.name || '',
    description: template?.description || '',
    duration_minutes: template?.duration_minutes || 30,
    appointment_type: template?.appointment_type || '',
    location_type: template?.location_type || 'virtual',
    default_location: template?.default_location || '',
    buffer_before_minutes: template?.buffer_before_minutes || 0,
    buffer_after_minutes: template?.buffer_after_minutes || 0,
    intake_form_fields: template?.intake_form_fields || [],
    reminder_config: template?.reminder_config || {},
    is_active: template?.is_active ?? true,
    is_default: template?.is_default ?? false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleChange = useCallback((field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    setError('');
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }

    setSaving(true);
    try {
      await onSave(form);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [form, onSave]);

  const labelStyle = { display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4, color: '#374151' };
  const inputStyle = {
    width: '100%', padding: '8px 12px', borderRadius: 8,
    border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box',
  };
  const selectStyle = { ...inputStyle };

  return (
    <div style={{
      border: '1px solid #3b82f6', borderRadius: 12, padding: 20,
      marginBottom: 16, background: '#f8fafc',
    }}>
      <h4 style={{ marginTop: 0, marginBottom: 16, fontSize: 16 }}>
        {isNew ? 'New Appointment Template' : 'Edit Template'}
      </h4>

      {error && (
        <div style={{
          padding: '8px 12px', background: '#fef2f2', color: '#dc2626',
          borderRadius: 8, marginBottom: 12, fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Name */}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>Template Name *</label>
        <input
          type="text"
          value={form.name}
          onChange={e => handleChange('name', e.target.value)}
          placeholder="e.g. Discovery Call, Document Review"
          style={inputStyle}
          maxLength={200}
        />
      </div>

      {/* Description */}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>Description</label>
        <input
          type="text"
          value={form.description}
          onChange={e => handleChange('description', e.target.value)}
          placeholder="Brief description of when to use this template"
          style={inputStyle}
        />
      </div>

      {/* Duration + Location type */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Duration</label>
          <select
            value={form.duration_minutes}
            onChange={e => handleChange('duration_minutes', parseInt(e.target.value, 10))}
            style={selectStyle}
          >
            {DURATION_PRESETS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Location Type</label>
          <select
            value={form.location_type}
            onChange={e => handleChange('location_type', e.target.value)}
            style={selectStyle}
          >
            {LOCATION_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Appointment type + Default location */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Appointment Type</label>
          <input
            type="text"
            value={form.appointment_type}
            onChange={e => handleChange('appointment_type', e.target.value)}
            placeholder="e.g. discovery_call, closing_walkthrough"
            style={inputStyle}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Default Location</label>
          <input
            type="text"
            value={form.default_location}
            onChange={e => handleChange('default_location', e.target.value)}
            placeholder={
              form.location_type === 'virtual' ? 'Meeting URL' :
              form.location_type === 'phone' ? 'Phone number' :
              'Office address'
            }
            style={inputStyle}
          />
        </div>
      </div>

      {/* Buffer times */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Buffer Before</label>
          <select
            value={form.buffer_before_minutes}
            onChange={e => handleChange('buffer_before_minutes', parseInt(e.target.value, 10))}
            style={selectStyle}
          >
            {BUFFER_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Buffer After</label>
          <select
            value={form.buffer_after_minutes}
            onChange={e => handleChange('buffer_after_minutes', parseInt(e.target.value, 10))}
            style={selectStyle}
          >
            {BUFFER_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Default toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <input
          type="checkbox"
          id="tmpl-is-default"
          checked={form.is_default}
          onChange={e => handleChange('is_default', e.target.checked)}
        />
        <label htmlFor="tmpl-is-default" style={{ fontSize: 13, color: '#374151' }}>
          Set as default template (auto-selected when creating appointments)
        </label>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button
          onClick={onCancel}
          style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid #d1d5db',
            background: '#fff', cursor: 'pointer', fontSize: 14,
          }}
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '8px 20px', borderRadius: 8, border: 'none',
            background: '#3b82f6', color: '#fff',
            cursor: saving ? 'wait' : 'pointer',
            fontSize: 14, fontWeight: 500, opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? 'Saving...' : isNew ? 'Create Template' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Template Quick-Select (compact picker for appointment creation flows)
// ---------------------------------------------------------------------------

export function TemplateQuickSelect({ onSelect, selectedId }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch('/api/v1/scheduler/templates');
        if (!cancelled) setTemplates(data.templates || []);
      } catch (err) {
        // Silently fail -- quick-select is optional enhancement
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading || templates.length === 0) return null;

  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6, color: '#374151' }}>
        Quick-fill from template
      </label>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {templates.map(t => {
          const isSelected = selectedId === t.id;
          const icon = LOCATION_ICONS[t.location_type] || '';
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onSelect(t)}
              style={{
                padding: '6px 14px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
                border: isSelected ? '2px solid #3b82f6' : '1px solid #d1d5db',
                background: isSelected ? '#eff6ff' : '#fff',
                color: isSelected ? '#1e40af' : '#374151',
                fontWeight: isSelected ? 600 : 400,
                transition: 'all 0.15s',
              }}
              title={t.description || `${durationLabel(t.duration_minutes)} - ${t.location_type}`}
            >
              {icon} {t.name} ({durationLabel(t.duration_minutes)})
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Management UI
// ---------------------------------------------------------------------------

export default function AppointmentTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new' | template object
  const [error, setError] = useState('');

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/api/v1/scheduler/templates?include_inactive=true');
      setTemplates(data.templates || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  // Toggle active
  const handleToggle = useCallback(async (id, newActive) => {
    try {
      await apiFetch(`/api/v1/scheduler/templates/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: newActive }),
      });
      setTemplates(prev => prev.map(t => t.id === id ? { ...t, is_active: newActive } : t));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Delete
  const handleDelete = useCallback(async (id) => {
    if (!window.confirm('Delete this appointment template?')) return;
    try {
      await apiFetch(`/api/v1/scheduler/templates/${id}`, { method: 'DELETE' });
      setTemplates(prev => prev.filter(t => t.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Duplicate
  const handleDuplicate = useCallback(async (id) => {
    try {
      const cloned = await apiFetch(`/api/v1/scheduler/templates/${id}/duplicate`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setTemplates(prev => [...prev, cloned]);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Save (create or update)
  const handleSave = useCallback(async (formData) => {
    if (editing && editing !== 'new' && editing.id) {
      const updated = await apiFetch(`/api/v1/scheduler/templates/${editing.id}`, {
        method: 'PUT',
        body: JSON.stringify(formData),
      });
      setTemplates(prev => prev.map(t => t.id === editing.id ? { ...t, ...updated } : t));
    } else {
      const created = await apiFetch('/api/v1/scheduler/templates', {
        method: 'POST',
        body: JSON.stringify(formData),
      });
      setTemplates(prev => [...prev, created]);
    }
    setEditing(null);
  }, [editing]);

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Appointment Templates</h3>
        {!editing && (
          <button
            onClick={() => setEditing('new')}
            style={{
              padding: '8px 16px', borderRadius: 8, border: 'none',
              background: '#3b82f6', color: '#fff', cursor: 'pointer',
              fontSize: 14, fontWeight: 500,
            }}
          >
            + New Template
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '8px 12px', background: '#fef2f2', color: '#dc2626',
          borderRadius: 8, marginBottom: 12, fontSize: 13,
        }}>
          {error}
          <button
            onClick={() => setError('')}
            style={{
              float: 'right', background: 'none', border: 'none',
              cursor: 'pointer', fontWeight: 600, color: '#dc2626',
            }}
          >
            X
          </button>
        </div>
      )}

      {/* Editor (shown above list when creating/editing) */}
      {editing && (
        <TemplateEditor
          template={editing === 'new' ? null : editing}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}

      {/* Template list */}
      {loading ? (
        <div style={{ padding: 20, textAlign: 'center', color: '#6b7280' }}>
          Loading templates...
        </div>
      ) : templates.length === 0 && !editing ? (
        <div style={{
          padding: 32, textAlign: 'center', color: '#6b7280',
          background: '#f9fafb', borderRadius: 12,
        }}>
          <p style={{ fontSize: 15, marginBottom: 12 }}>No appointment templates yet.</p>
          <p style={{ fontSize: 13, marginBottom: 16, color: '#9ca3af' }}>
            Templates let you pre-configure appointment settings like duration, meeting type, and buffer times.
          </p>
          <button
            onClick={() => setEditing('new')}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #3b82f6',
              background: '#eff6ff', color: '#3b82f6', cursor: 'pointer',
              fontSize: 14, fontWeight: 500,
            }}
          >
            Create your first template
          </button>
        </div>
      ) : (
        templates.map(t => (
          <TemplateCard
            key={t.id}
            template={t}
            onEdit={() => setEditing(t)}
            onDuplicate={handleDuplicate}
            onDelete={handleDelete}
            onToggle={handleToggle}
          />
        ))
      )}
    </div>
  );
}
