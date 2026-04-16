import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { normalizeUTCDate, getUserTimezone } from './calendarUtils';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

// Timing presets in minutes
const TIMING_PRESETS = [
  { label: '15 minutes before', value: 15 },
  { label: '30 minutes before', value: 30 },
  { label: '1 hour before', value: 60 },
  { label: '2 hours before', value: 120 },
  { label: '4 hours before', value: 240 },
  { label: '24 hours before', value: 1440 },
  { label: '48 hours before', value: 2880 },
  { label: '1 week before', value: 10080 },
];

const CHANNEL_OPTIONS = [
  { label: 'Email', value: 'email' },
  { label: 'SMS', value: 'sms' },
  { label: 'Both', value: 'both' },
];

const TEMPLATE_VARIABLES = [
  { key: 'client_name', label: 'Client Name' },
  { key: 'appointment_type', label: 'Appointment Type' },
  { key: 'date', label: 'Date' },
  { key: 'time', label: 'Time' },
  { key: 'lo_name', label: 'LO Name' },
  { key: 'location', label: 'Location' },
  { key: 'join_url', label: 'Join URL' },
  { key: 'cancel_url', label: 'Cancel URL' },
  { key: 'reschedule_url', label: 'Reschedule URL' },
];

const STATUS_COLORS = {
  sent: '#10b981',
  failed: '#ef4444',
  skipped: '#f59e0b',
};

function timingLabel(minutes) {
  if (minutes >= 1440) {
    const days = Math.floor(minutes / 1440);
    return `${days} day${days > 1 ? 's' : ''} before`;
  }
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours} hour${hours > 1 ? 's' : ''} before`;
  }
  return `${minutes} minute${minutes > 1 ? 's' : ''} before`;
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
// Sub-components
// ---------------------------------------------------------------------------

function TemplateCard({ template, onToggle, onEdit, onDelete }) {
  const channelBadge = {
    email: { bg: '#dbeafe', color: '#1e40af', label: 'Email' },
    sms: { bg: '#dcfce7', color: '#166534', label: 'SMS' },
    both: { bg: '#fef3c7', color: '#92400e', label: 'Both' },
  }[template.channel] || { bg: '#f3f4f6', color: '#374151', label: template.channel };

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 16,
        marginBottom: 12,
        opacity: template.is_active ? 1 : 0.6,
        background: template.is_active ? '#fff' : '#f9fafb',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label className="toggle-switch" style={{ position: 'relative', display: 'inline-block', width: 44, height: 24 }}>
            <input
              type="checkbox"
              checked={template.is_active}
              onChange={() => onToggle(template.id, !template.is_active)}
              style={{ opacity: 0, width: 0, height: 0 }}
              aria-label={`Toggle ${template.name}`}
            />
            <span
              style={{
                position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: template.is_active ? '#3b82f6' : '#d1d5db',
                borderRadius: 24, transition: 'background-color 0.2s',
              }}
            >
              <span
                style={{
                  position: 'absolute', height: 18, width: 18, left: template.is_active ? 22 : 3, bottom: 3,
                  backgroundColor: '#fff', borderRadius: '50%', transition: 'left 0.2s',
                }}
              />
            </span>
          </label>
          <strong style={{ fontSize: 15 }}>{template.name}</strong>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={() => onEdit(template)}
            style={{ padding: '4px 12px', borderRadius: 6, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 13 }}
          >
            Edit
          </button>
          <button
            onClick={() => onDelete(template.id)}
            style={{ padding: '4px 12px', borderRadius: 6, border: '1px solid #fca5a5', background: '#fef2f2', color: '#dc2626', cursor: 'pointer', fontSize: 13 }}
          >
            Delete
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 13, color: '#6b7280' }}>
        <span
          style={{
            padding: '2px 8px', borderRadius: 12,
            background: channelBadge.bg, color: channelBadge.color, fontWeight: 500,
          }}
        >
          {channelBadge.label}
        </span>
        <span style={{ padding: '2px 8px', borderRadius: 12, background: '#f3f4f6' }}>
          {template.timing_label || timingLabel(template.timing_minutes)}
        </span>
      </div>
    </div>
  );
}

function TemplateEditor({ template, onSave, onCancel }) {
  const isNew = !template?.id;
  const [form, setForm] = useState({
    name: template?.name || '',
    channel: template?.channel || 'email',
    timing_minutes: template?.timing_minutes || 1440,
    subject_template: template?.subject_template || '',
    body_template: template?.body_template || '',
    is_active: template?.is_active ?? true,
    appointment_type_id: template?.appointment_type_id || null,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleChange = useCallback((field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  }, []);

  const insertVariable = useCallback((varKey) => {
    setForm(prev => ({
      ...prev,
      body_template: prev.body_template + `{${varKey}}`,
    }));
  }, []);

  const handleSave = useCallback(async () => {
    setError('');
    if (!form.name.trim()) { setError('Name is required'); return; }
    if (!form.body_template.trim()) { setError('Message body is required'); return; }

    setSaving(true);
    try {
      await onSave(form);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [form, onSave]);

  // Preview rendering
  const previewVars = useMemo(() => ({
    client_name: 'Jane Doe',
    appointment_type: 'Discovery Call',
    date: 'March 15, 2026',
    time: '2:00 PM',
    lo_name: 'John Smith',
    location: 'Video Call',
    join_url: 'https://meet.example.com/abc123',
    cancel_url: 'https://app.perenniaai.com/appointments/123/cancel',
    reschedule_url: 'https://app.perenniaai.com/appointments/123/reschedule',
  }), []);

  const renderedBody = useMemo(() => {
    let text = form.body_template;
    Object.entries(previewVars).forEach(([key, val]) => {
      text = text.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
    });
    return text;
  }, [form.body_template, previewVars]);

  const renderedSubject = useMemo(() => {
    let text = form.subject_template;
    Object.entries(previewVars).forEach(([key, val]) => {
      text = text.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
    });
    return text;
  }, [form.subject_template, previewVars]);

  return (
    <div style={{ border: '1px solid #3b82f6', borderRadius: 12, padding: 20, marginBottom: 16, background: '#f8fafc' }}>
      <h4 style={{ marginTop: 0, marginBottom: 16 }}>{isNew ? 'New Reminder Template' : 'Edit Template'}</h4>

      {error && (
        <div style={{ padding: '8px 12px', background: '#fef2f2', color: '#dc2626', borderRadius: 8, marginBottom: 12, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Name */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Name</label>
        <input
          type="text"
          value={form.name}
          onChange={e => handleChange('name', e.target.value)}
          placeholder="e.g. 24-Hour Email Reminder"
          style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box' }}
        />
      </div>

      {/* Channel + Timing row */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Channel</label>
          <select
            value={form.channel}
            onChange={e => handleChange('channel', e.target.value)}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14 }}
          >
            {CHANNEL_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Timing</label>
          <select
            value={form.timing_minutes}
            onChange={e => handleChange('timing_minutes', parseInt(e.target.value, 10))}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14 }}
          >
            {TIMING_PRESETS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Subject (email only) */}
      {(form.channel === 'email' || form.channel === 'both') && (
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Email Subject</label>
          <input
            type="text"
            value={form.subject_template}
            onChange={e => handleChange('subject_template', e.target.value)}
            placeholder="Reminder: {appointment_type} at {time}"
            style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box' }}
          />
        </div>
      )}

      {/* Body */}
      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Message Body</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
          {TEMPLATE_VARIABLES.map(v => (
            <button
              key={v.key}
              type="button"
              onClick={() => insertVariable(v.key)}
              style={{
                padding: '2px 8px', borderRadius: 6, border: '1px solid #d1d5db',
                background: '#f9fafb', cursor: 'pointer', fontSize: 12, color: '#374151',
              }}
              title={`Insert {${v.key}}`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <textarea
          value={form.body_template}
          onChange={e => handleChange('body_template', e.target.value)}
          rows={6}
          style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', fontSize: 14, fontFamily: 'inherit', resize: 'vertical', boxSizing: 'border-box' }}
          placeholder="Hi {client_name}, this is a reminder about your upcoming {appointment_type}..."
        />
      </div>

      {/* Preview */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Preview</label>
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, fontSize: 13 }}>
          {renderedSubject && (
            <div style={{ fontWeight: 600, marginBottom: 6, color: '#111827' }}>
              Subject: {renderedSubject}
            </div>
          )}
          <div style={{ whiteSpace: 'pre-wrap', color: '#374151', lineHeight: 1.5 }}>
            {renderedBody}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button
          onClick={onCancel}
          style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: 14 }}
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '8px 20px', borderRadius: 8, border: 'none',
            background: '#3b82f6', color: '#fff', cursor: saving ? 'wait' : 'pointer',
            fontSize: 14, fontWeight: 500, opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? 'Saving...' : isNew ? 'Create Template' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

function StatusBadgeInline({ status }) {
  const color = STATUS_COLORS[status] || '#6b7280';
  return (
    <span
      style={{
        display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 12,
        fontWeight: 500, background: `${color}20`, color,
      }}
    >
      {status}
    </span>
  );
}

function SendHistoryTable({ logs, loading }) {
  if (loading) {
    return <div style={{ padding: 20, textAlign: 'center', color: '#6b7280' }}>Loading history...</div>;
  }
  if (!logs.length) {
    return <div style={{ padding: 20, textAlign: 'center', color: '#6b7280' }}>No reminders sent yet</div>;
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#374151' }}>Date</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#374151' }}>Channel</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#374151' }}>Recipient</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#374151' }}>Status</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: '#374151' }}>Error</th>
          </tr>
        </thead>
        <tbody>
          {logs.map(log => (
            <tr key={log.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <td style={{ padding: '8px 12px', color: '#6b7280' }}>
                {log.sent_at ? new Date(normalizeUTCDate(log.sent_at)).toLocaleString('en-US', { timeZone: getUserTimezone() }) : '-'}
              </td>
              <td style={{ padding: '8px 12px', textTransform: 'uppercase', fontWeight: 500, color: '#374151' }}>
                {log.channel}
              </td>
              <td style={{ padding: '8px 12px', color: '#374151' }}>
                {log.recipient_email || log.recipient_phone || '-'}
              </td>
              <td style={{ padding: '8px 12px' }}>
                <StatusBadgeInline status={log.status} />
              </td>
              <td style={{ padding: '8px 12px', color: '#ef4444', fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {log.error_message || ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ReminderSettings() {
  const [templates, setTemplates] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [loadingLogs, setLoadingLogs] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new' | template object
  const [activeTab, setActiveTab] = useState('templates'); // 'templates' | 'history'
  const [error, setError] = useState('');

  // Fetch templates
  const fetchTemplates = useCallback(async () => {
    setLoadingTemplates(true);
    try {
      const data = await apiFetch('/api/v1/scheduler/reminders/templates?include_inactive=true');
      setTemplates(data.templates || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingTemplates(false);
    }
  }, []);

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    setLoadingLogs(true);
    try {
      const data = await apiFetch('/api/v1/scheduler/reminders/log?limit=100');
      setLogs(data.logs || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingLogs(false);
    }
  }, []);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchLogs();
    }
  }, [activeTab, fetchLogs]);

  // Toggle active
  const handleToggle = useCallback(async (id, newActive) => {
    try {
      await apiFetch(`/api/v1/scheduler/reminders/templates/${id}`, {
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
    if (!window.confirm('Delete this reminder template?')) return;
    try {
      await apiFetch(`/api/v1/scheduler/reminders/templates/${id}`, { method: 'DELETE' });
      setTemplates(prev => prev.filter(t => t.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Save (create or update)
  const handleSave = useCallback(async (formData) => {
    if (editing && editing !== 'new' && editing.id) {
      // Update
      const updated = await apiFetch(`/api/v1/scheduler/reminders/templates/${editing.id}`, {
        method: 'PUT',
        body: JSON.stringify(formData),
      });
      setTemplates(prev => prev.map(t => t.id === editing.id ? { ...t, ...updated } : t));
    } else {
      // Create
      const created = await apiFetch('/api/v1/scheduler/reminders/templates', {
        method: 'POST',
        body: JSON.stringify(formData),
      });
      setTemplates(prev => [...prev, created]);
    }
    setEditing(null);
  }, [editing]);

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Appointment Reminders</h3>
        {activeTab === 'templates' && !editing && (
          <button
            onClick={() => setEditing('new')}
            style={{
              padding: '8px 16px', borderRadius: 8, border: 'none',
              background: '#3b82f6', color: '#fff', cursor: 'pointer',
              fontSize: 14, fontWeight: 500,
            }}
          >
            + Add Reminder
          </button>
        )}
      </div>

      {error && (
        <div style={{ padding: '8px 12px', background: '#fef2f2', color: '#dc2626', borderRadius: 8, marginBottom: 12, fontSize: 13 }}>
          {error}
          <button onClick={() => setError('')} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, color: '#dc2626' }}>
            X
          </button>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 16, borderBottom: '2px solid #e5e7eb' }}>
        {['templates', 'history'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px', border: 'none', cursor: 'pointer', fontSize: 14,
              fontWeight: activeTab === tab ? 600 : 400,
              color: activeTab === tab ? '#3b82f6' : '#6b7280',
              borderBottom: activeTab === tab ? '2px solid #3b82f6' : '2px solid transparent',
              background: 'none', marginBottom: -2,
            }}
          >
            {tab === 'templates' ? 'Templates' : 'Send History'}
          </button>
        ))}
      </div>

      {/* Templates tab */}
      {activeTab === 'templates' && (
        <div>
          {editing && (
            <TemplateEditor
              template={editing === 'new' ? null : editing}
              onSave={handleSave}
              onCancel={() => setEditing(null)}
            />
          )}

          {loadingTemplates ? (
            <div style={{ padding: 20, textAlign: 'center', color: '#6b7280' }}>Loading templates...</div>
          ) : templates.length === 0 && !editing ? (
            <div style={{ padding: 32, textAlign: 'center', color: '#6b7280', background: '#f9fafb', borderRadius: 12 }}>
              <p style={{ fontSize: 15, marginBottom: 12 }}>No reminder templates configured.</p>
              <button
                onClick={() => setEditing('new')}
                style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #3b82f6', background: '#eff6ff', color: '#3b82f6', cursor: 'pointer', fontSize: 14, fontWeight: 500 }}
              >
                Create your first template
              </button>
            </div>
          ) : (
            templates.map(t => (
              <TemplateCard
                key={t.id}
                template={t}
                onToggle={handleToggle}
                onEdit={() => setEditing(t)}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      )}

      {/* History tab */}
      {activeTab === 'history' && (
        <SendHistoryTable logs={logs} loading={loadingLogs} />
      )}
    </div>
  );
}
