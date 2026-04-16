/**
 * Follow-Up Cadence Section — Calendar Settings
 *
 * Embeds the cadence template manager directly in Calendar Settings so LOs
 * can configure automated follow-up sequences (email, SMS, call) from the
 * same place they manage their calendar.
 *
 * This is a self-contained section — it manages its own data fetching
 * and doesn't participate in the parent's save/load cycle.
 */

import { useState, useEffect, useCallback } from 'react';
import { toast } from '../../utils/toast';
import { clearTokens, getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

function getAuthHeaders() {
  const token = getToken();
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

const TRIGGER_TYPES = [
  { value: 'DOC_REQUESTED', label: 'Document Requested' },
  { value: 'DOC_OVERDUE', label: 'Document Overdue' },
  { value: 'DOC_EXPIRING', label: 'Document Expiring' },
  { value: 'CONDITION_ADDED', label: 'Condition Added' },
  { value: 'DOC_REJECTED', label: 'Document Rejected' },
  { value: 'MANUAL', label: 'Manual Trigger' },
];

const CHANNELS = [
  { value: 'email', label: 'Email', icon: '\u2709' },
  { value: 'sms', label: 'SMS', icon: '\uD83D\uDCF1' },
  { value: 'call', label: 'Phone Call', icon: '\uD83D\uDCDE' },
  { value: 'escalate', label: 'Escalate to LO', icon: '\u26A0' },
  { value: 'portal', label: 'Portal Notification', icon: '\uD83D\uDD14' },
  { value: 'in_app', label: 'In-App Notification', icon: '\uD83D\uDCE2' },
];

export default function FollowUpCadenceSection() {
  const [cadences, setCadences] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingCadence, setEditingCadence] = useState(null);
  const [filterTrigger, setFilterTrigger] = useState('');

  // Form state
  const [form, setForm] = useState({
    cadence_name: '',
    trigger_type: 'DOC_REQUESTED',
    description: '',
    channel_sequence: [{ day: 0, channel: 'email', template: 'initial_request' }],
    max_attempts: 5,
    escalation_after: 3,
    quiet_hours_start: 20,
    quiet_hours_end: 8,
    weekend_enabled: false,
    holiday_aware: true,
  });

  const fetchCadences = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterTrigger) params.set('trigger_type', filterTrigger);
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates?${params}`,
        { headers: getAuthHeaders() }
      );
      if (response.status === 401) {
        await clearTokens();
        window.location.href = '/login';
        return;
      }
      if (response.ok) {
        const data = await response.json();
        setCadences(data.cadences || []);
      }
    } catch (err) {
      console.error('Error fetching cadences:', err);
    } finally {
      setLoading(false);
    }
  }, [filterTrigger]);

  useEffect(() => {
    fetchCadences();
  }, [fetchCadences]);

  const openCreateForm = () => {
    setEditingCadence(null);
    setForm({
      cadence_name: '',
      trigger_type: 'DOC_REQUESTED',
      description: '',
      channel_sequence: [{ day: 0, channel: 'email', template: 'initial_request' }],
      max_attempts: 5,
      escalation_after: 3,
      quiet_hours_start: 20,
      quiet_hours_end: 8,
      weekend_enabled: false,
      holiday_aware: true,
    });
    setShowForm(true);
  };

  const openEditForm = (cadence) => {
    setEditingCadence(cadence);
    setForm({ ...cadence });
    setShowForm(true);
  };

  const updateField = (field, value) => setForm(prev => ({ ...prev, [field]: value }));

  const addStep = () => {
    const lastDay = form.channel_sequence.length > 0
      ? form.channel_sequence[form.channel_sequence.length - 1].day
      : 0;
    setForm(prev => ({
      ...prev,
      channel_sequence: [...prev.channel_sequence, { day: lastDay + 2, channel: 'sms', template: '' }],
    }));
  };

  const updateStep = (idx, field, value) => {
    setForm(prev => {
      const seq = [...prev.channel_sequence];
      seq[idx] = { ...seq[idx], [field]: value };
      return { ...prev, channel_sequence: seq };
    });
  };

  const removeStep = (idx) => {
    setForm(prev => ({
      ...prev,
      channel_sequence: prev.channel_sequence.filter((_, i) => i !== idx),
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.cadence_name.trim()) {
      toast.error('Cadence name is required');
      return;
    }
    try {
      const url = editingCadence
        ? `${API_BASE}/api/smart-docs/cadence/templates/${editingCadence.id}`
        : `${API_BASE}/api/smart-docs/cadence/templates`;
      const response = await fetch(url, {
        method: editingCadence ? 'PUT' : 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(form),
      });
      if (response.ok) {
        toast.success(editingCadence ? 'Cadence updated' : 'Cadence created');
        setShowForm(false);
        fetchCadences();
      } else {
        const err = await response.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to save cadence');
      }
    } catch (err) {
      toast.error('Failed to save cadence');
    }
  };

  const handleClone = async (cadenceId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates/${cadenceId}/clone`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        toast.success('Cadence cloned to your org');
        fetchCadences();
      }
    } catch (err) {
      toast.error('Failed to clone cadence');
    }
  };

  const handleSeedDefaults = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/seed-defaults`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || 'Default cadences seeded');
        fetchCadences();
      }
    } catch (err) {
      toast.error('Failed to seed defaults');
    }
  };

  return (
    <div className="settings-section followup-cadence-section">
      <div className="section-header-block">
        <div>
          <h2>Follow-Up Cadence</h2>
          <p className="section-desc">
            Configure automated outreach sequences for document collection.
            Define when and how AI follows up with borrowers via email, SMS, and phone.
          </p>
        </div>
        <div className="section-header-actions">
          <button className="btn-secondary-sm" onClick={handleSeedDefaults}>
            Seed Defaults
          </button>
          <button className="btn-primary-sm" onClick={openCreateForm}>
            + New Cadence
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="cadence-filter-bar">
        <select value={filterTrigger} onChange={e => setFilterTrigger(e.target.value)}>
          <option value="">All Trigger Types</option>
          {TRIGGER_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Cadence list */}
      {loading ? (
        <div className="cadence-loading-inline">Loading cadences...</div>
      ) : cadences.length === 0 ? (
        <div className="cadence-empty-inline">
          <p>No follow-up cadences configured yet.</p>
          <p>Click <strong>Seed Defaults</strong> to create 5 standard templates, or create a custom cadence.</p>
        </div>
      ) : (
        <div className="cadence-cards-inline">
          {cadences.map(cadence => (
            <div key={cadence.id} className={`cadence-card-inline ${!cadence.is_active ? 'inactive' : ''}`}>
              <div className="cadence-card-top">
                <div className="cadence-card-info">
                  <strong>{cadence.cadence_name}</strong>
                  {cadence.is_system && <span className="badge-sm badge-system-sm">System</span>}
                  <span className="badge-sm badge-trigger-sm">
                    {TRIGGER_TYPES.find(t => t.value === cadence.trigger_type)?.label || cadence.trigger_type}
                  </span>
                </div>
                <div className="cadence-card-btns">
                  {cadence.is_system ? (
                    <button className="btn-xs" onClick={() => handleClone(cadence.id)}>Clone</button>
                  ) : (
                    <button className="btn-xs" onClick={() => openEditForm(cadence)}>Edit</button>
                  )}
                </div>
              </div>
              {cadence.description && (
                <p className="cadence-card-desc-sm">{cadence.description}</p>
              )}
              <div className="cadence-sequence-inline">
                {(cadence.channel_sequence || []).map((step, idx) => (
                  <span key={idx} className="sequence-chip">
                    {idx > 0 && <span className="seq-arrow">&rarr;</span>}
                    <span className="seq-day">D{step.day}</span>
                    <span className="seq-ch">
                      {CHANNELS.find(c => c.value === step.channel)?.icon}{' '}
                      {CHANNELS.find(c => c.value === step.channel)?.label || step.channel}
                    </span>
                  </span>
                ))}
              </div>
              <div className="cadence-card-footer-sm">
                <span>Max: {cadence.max_attempts} attempts</span>
                <span>Escalate after: {cadence.escalation_after}</span>
                <span>Quiet: {cadence.quiet_hours_start}:00-{cadence.quiet_hours_end}:00</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit form modal */}
      {showForm && (
        <div className="cadence-form-overlay" onClick={() => setShowForm(false)}>
          <div className="cadence-form-modal" onClick={e => e.stopPropagation()}>
            <h3>{editingCadence ? 'Edit Cadence' : 'New Follow-Up Cadence'}</h3>
            <form onSubmit={handleSave}>
              <div className="form-row-2">
                <div className="form-field">
                  <label>Name</label>
                  <input
                    type="text"
                    value={form.cadence_name}
                    onChange={e => updateField('cadence_name', e.target.value)}
                    placeholder="e.g., Missing Document - Urgent"
                    required
                  />
                </div>
                <div className="form-field">
                  <label>Trigger</label>
                  <select value={form.trigger_type} onChange={e => updateField('trigger_type', e.target.value)}>
                    {TRIGGER_TYPES.map(t => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-field">
                <label>Description</label>
                <textarea
                  value={form.description || ''}
                  onChange={e => updateField('description', e.target.value)}
                  rows={2}
                  placeholder="When and how this cadence is used..."
                />
              </div>

              <div className="form-field">
                <div className="field-header-row">
                  <label>Channel Sequence</label>
                  <button type="button" className="btn-add-sm" onClick={addStep}>+ Step</button>
                </div>
                {form.channel_sequence.map((step, idx) => (
                  <div key={idx} className="step-row-inline">
                    <span className="step-num">{idx + 1}</span>
                    <div className="step-field-sm">
                      <label>Day</label>
                      <input
                        type="number"
                        min="0"
                        value={step.day}
                        onChange={e => updateStep(idx, 'day', parseInt(e.target.value) || 0)}
                        style={{ width: 60 }}
                      />
                    </div>
                    <div className="step-field-sm">
                      <label>Channel</label>
                      <select value={step.channel} onChange={e => updateStep(idx, 'channel', e.target.value)}>
                        {CHANNELS.map(c => (
                          <option key={c.value} value={c.value}>{c.icon} {c.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="step-field-sm" style={{ flex: 1 }}>
                      <label>Template</label>
                      <input
                        type="text"
                        value={step.template || ''}
                        onChange={e => updateStep(idx, 'template', e.target.value)}
                        placeholder="template_slug"
                      />
                    </div>
                    <button type="button" className="btn-remove-xs" onClick={() => removeStep(idx)}>&times;</button>
                  </div>
                ))}
              </div>

              <div className="form-row-4">
                <div className="form-field">
                  <label>Max Attempts</label>
                  <input type="number" min="1" max="20" value={form.max_attempts}
                    onChange={e => updateField('max_attempts', parseInt(e.target.value) || 5)} />
                </div>
                <div className="form-field">
                  <label>Escalate After</label>
                  <input type="number" min="1" max="20" value={form.escalation_after}
                    onChange={e => updateField('escalation_after', parseInt(e.target.value) || 3)} />
                </div>
                <div className="form-field">
                  <label>Quiet Start</label>
                  <input type="number" min="0" max="23" value={form.quiet_hours_start}
                    onChange={e => updateField('quiet_hours_start', parseInt(e.target.value) || 20)} />
                </div>
                <div className="form-field">
                  <label>Quiet End</label>
                  <input type="number" min="0" max="23" value={form.quiet_hours_end}
                    onChange={e => updateField('quiet_hours_end', parseInt(e.target.value) || 8)} />
                </div>
              </div>

              <div className="form-row-checks">
                <label><input type="checkbox" checked={form.weekend_enabled}
                  onChange={e => updateField('weekend_enabled', e.target.checked)} /> Weekend sends</label>
                <label><input type="checkbox" checked={form.holiday_aware}
                  onChange={e => updateField('holiday_aware', e.target.checked)} /> Skip holidays</label>
              </div>

              <div className="form-actions-row">
                <button type="button" className="btn-secondary-sm" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn-primary-sm">
                  {editingCadence ? 'Update' : 'Create Cadence'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
