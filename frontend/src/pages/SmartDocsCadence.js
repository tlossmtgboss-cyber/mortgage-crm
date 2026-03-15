import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import './SmartDocsCadence.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

function getAuthHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Authorization': token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

function handleAuthError(response) {
  if (response.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
    return true;
  }
  return false;
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

const STATUS_COLORS = {
  ACTIVE: '#10b981',
  PAUSED: '#f59e0b',
  COMPLETED: '#6b7280',
  CANCELLED: '#ef4444',
  ESCALATED: '#8b5cf6',
};

// ---------------------------------------------------------------------------
// Cadence Template Form (used for create and edit)
// ---------------------------------------------------------------------------
function CadenceForm({ cadence, onSave, onCancel }) {
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
    ab_test_enabled: false,
    ab_test_name: '',
    ab_test_split_pct: 50,
    ...cadence,
  });
  const [saving, setSaving] = useState(false);

  const updateField = (field, value) => setForm(prev => ({ ...prev, [field]: value }));

  const addStep = () => {
    const lastDay = form.channel_sequence.length > 0
      ? form.channel_sequence[form.channel_sequence.length - 1].day
      : 0;
    setForm(prev => ({
      ...prev,
      channel_sequence: [
        ...prev.channel_sequence,
        { day: lastDay + 2, channel: 'email', template: '' },
      ],
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.cadence_name.trim()) {
      toast.error('Cadence name is required');
      return;
    }
    if (form.channel_sequence.length === 0) {
      toast.error('At least one step is required');
      return;
    }
    setSaving(true);
    try {
      await onSave(form);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="cadence-form" onSubmit={handleSubmit}>
      <div className="form-row">
        <div className="form-group">
          <label>Cadence Name</label>
          <input
            type="text"
            value={form.cadence_name}
            onChange={e => updateField('cadence_name', e.target.value)}
            placeholder="e.g., Missing Document - Urgent"
            required
          />
        </div>
        <div className="form-group">
          <label>Trigger Type</label>
          <select
            value={form.trigger_type}
            onChange={e => updateField('trigger_type', e.target.value)}
          >
            {TRIGGER_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-group">
        <label>Description</label>
        <textarea
          value={form.description || ''}
          onChange={e => updateField('description', e.target.value)}
          placeholder="Describe when and how this cadence is used..."
          rows={2}
        />
      </div>

      <div className="form-section-header">
        <h4>Channel Sequence</h4>
        <button type="button" className="btn-add-step" onClick={addStep}>+ Add Step</button>
      </div>

      <div className="steps-builder">
        {form.channel_sequence.map((step, idx) => (
          <div key={idx} className="step-row">
            <div className="step-number">{idx + 1}</div>
            <div className="step-fields">
              <div className="step-field">
                <label>Day</label>
                <input
                  type="number"
                  min="0"
                  value={step.day}
                  onChange={e => updateStep(idx, 'day', parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="step-field">
                <label>Channel</label>
                <select
                  value={step.channel}
                  onChange={e => updateStep(idx, 'channel', e.target.value)}
                >
                  {CHANNELS.map(c => (
                    <option key={c.value} value={c.value}>{c.icon} {c.label}</option>
                  ))}
                </select>
              </div>
              <div className="step-field step-field-template">
                <label>Template</label>
                <input
                  type="text"
                  value={step.template || ''}
                  onChange={e => updateStep(idx, 'template', e.target.value)}
                  placeholder="template_slug"
                />
              </div>
            </div>
            <button
              type="button"
              className="btn-remove-step"
              onClick={() => removeStep(idx)}
              aria-label="Remove step"
            >
              &times;
            </button>
          </div>
        ))}
      </div>

      <div className="form-section-header">
        <h4>Compliance Settings</h4>
      </div>

      <div className="form-row form-row-4">
        <div className="form-group">
          <label>Max Attempts</label>
          <input type="number" min="1" max="20" value={form.max_attempts}
            onChange={e => updateField('max_attempts', parseInt(e.target.value) || 5)} />
        </div>
        <div className="form-group">
          <label>Escalate After</label>
          <input type="number" min="1" max="20" value={form.escalation_after}
            onChange={e => updateField('escalation_after', parseInt(e.target.value) || 3)} />
        </div>
        <div className="form-group">
          <label>Quiet Start (hour)</label>
          <input type="number" min="0" max="23" value={form.quiet_hours_start}
            onChange={e => updateField('quiet_hours_start', parseInt(e.target.value) || 20)} />
        </div>
        <div className="form-group">
          <label>Quiet End (hour)</label>
          <input type="number" min="0" max="23" value={form.quiet_hours_end}
            onChange={e => updateField('quiet_hours_end', parseInt(e.target.value) || 8)} />
        </div>
      </div>

      <div className="form-row">
        <label className="checkbox-label">
          <input type="checkbox" checked={form.weekend_enabled}
            onChange={e => updateField('weekend_enabled', e.target.checked)} />
          Allow weekend sends
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={form.holiday_aware}
            onChange={e => updateField('holiday_aware', e.target.checked)} />
          Skip federal holidays
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={form.ab_test_enabled}
            onChange={e => updateField('ab_test_enabled', e.target.checked)} />
          Enable A/B testing
        </label>
      </div>

      {form.ab_test_enabled && (
        <div className="form-row">
          <div className="form-group">
            <label>A/B Test Name</label>
            <input type="text" value={form.ab_test_name || ''}
              onChange={e => updateField('ab_test_name', e.target.value)}
              placeholder="e.g., Email Subject Test" />
          </div>
          <div className="form-group">
            <label>Split % (Variant B)</label>
            <input type="number" min="0" max="100" value={form.ab_test_split_pct}
              onChange={e => updateField('ab_test_split_pct', parseFloat(e.target.value) || 50)} />
          </div>
        </div>
      )}

      <div className="form-actions">
        <button type="button" className="btn-cancel" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-save" disabled={saving}>
          {saving ? 'Saving...' : (cadence ? 'Update Cadence' : 'Create Cadence')}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Execution Timeline
// ---------------------------------------------------------------------------
function ExecutionTimeline({ execution }) {
  if (!execution) return null;
  const log = execution.execution_log || [];

  return (
    <div className="execution-timeline">
      <div className="timeline-header">
        <strong>{execution.borrower_name || execution.borrower_email || 'Unknown'}</strong>
        <span className="execution-status" style={{ color: STATUS_COLORS[execution.status] }}>
          {execution.status}
        </span>
      </div>
      <div className="timeline-meta">
        Step {(execution.current_step || 0) + 1} of {execution.total_steps || '?'}
        {execution.attempts_made > 0 && ` \u2022 ${execution.attempts_made} attempts`}
        {execution.response_received && ` \u2022 Responded: ${execution.response_type}`}
      </div>
      <div className="timeline-steps">
        {log.map((entry, idx) => (
          <div key={idx} className={`timeline-step timeline-step--${entry.status || 'pending'}`}>
            <div className="timeline-dot" />
            <div className="timeline-content">
              <div className="timeline-step-label">
                Step {entry.step + 1}: {CHANNELS.find(c => c.value === entry.channel)?.icon} {entry.channel}
              </div>
              <div className="timeline-step-time">
                {entry.sent_at ? new Date(entry.sent_at).toLocaleString() : 'Pending'}
                {entry.status && ` \u2014 ${entry.status}`}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------
export default function SmartDocsCadence() {
  const [activeTab, setActiveTab] = useState('cadences');
  const [cadences, setCadences] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filterTrigger, setFilterTrigger] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingCadence, setEditingCadence] = useState(null);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [executionDetail, setExecutionDetail] = useState(null);

  // Fetch cadences
  const fetchCadences = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterTrigger) params.set('trigger_type', filterTrigger);
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates?${params}`,
        { headers: getAuthHeaders() }
      );
      if (handleAuthError(response)) return;
      if (response.ok) {
        const data = await response.json();
        setCadences(data.cadences || []);
      } else {
        toast.error('Failed to load cadences');
      }
    } catch (err) {
      console.error('Error fetching cadences:', err);
      toast.error('Failed to load cadences');
    } finally {
      setLoading(false);
    }
  }, [filterTrigger]);

  // Fetch executions
  const fetchExecutions = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (filterStatus) params.set('status', filterStatus);
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/executions?${params}`,
        { headers: getAuthHeaders() }
      );
      if (handleAuthError(response)) return;
      if (response.ok) {
        const data = await response.json();
        setExecutions(data.executions || []);
      }
    } catch (err) {
      console.error('Error fetching executions:', err);
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  // Fetch analytics
  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/analytics?days=30`,
        { headers: getAuthHeaders() }
      );
      if (handleAuthError(response)) return;
      if (response.ok) {
        const data = await response.json();
        setAnalytics(data);
      }
    } catch (err) {
      console.error('Error fetching analytics:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch execution timeline
  const fetchExecutionTimeline = useCallback(async (executionId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/executions/${executionId}/timeline`,
        { headers: getAuthHeaders() }
      );
      if (handleAuthError(response)) return;
      if (response.ok) {
        const data = await response.json();
        setExecutionDetail(data);
      }
    } catch (err) {
      console.error('Error fetching timeline:', err);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'cadences') fetchCadences();
    else if (activeTab === 'executions') fetchExecutions();
    else if (activeTab === 'analytics') fetchAnalytics();
  }, [activeTab, fetchCadences, fetchExecutions, fetchAnalytics]);

  // Create cadence
  const handleCreateCadence = async (formData) => {
    try {
      const response = await fetch(`${API_BASE}/api/smart-docs/cadence/templates`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        toast.success('Cadence created successfully');
        setShowForm(false);
        fetchCadences();
      } else {
        const err = await response.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to create cadence');
      }
    } catch (err) {
      toast.error('Failed to create cadence');
    }
  };

  // Update cadence
  const handleUpdateCadence = async (formData) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates/${editingCadence.id}`,
        {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify(formData),
        }
      );
      if (response.ok) {
        toast.success('Cadence updated');
        setEditingCadence(null);
        setShowForm(false);
        fetchCadences();
      } else {
        const err = await response.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to update cadence');
      }
    } catch (err) {
      toast.error('Failed to update cadence');
    }
  };

  // Clone system cadence
  const handleClone = async (cadenceId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates/${cadenceId}/clone`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        toast.success('Cadence cloned to your org');
        fetchCadences();
      } else {
        toast.error('Failed to clone cadence');
      }
    } catch (err) {
      toast.error('Failed to clone cadence');
    }
  };

  // Toggle active/inactive
  const handleToggleActive = async (cadence) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/templates/${cadence.id}`,
        {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({ is_active: !cadence.is_active }),
        }
      );
      if (response.ok) {
        toast.success(cadence.is_active ? 'Cadence deactivated' : 'Cadence activated');
        fetchCadences();
      }
    } catch (err) {
      toast.error('Failed to update cadence');
    }
  };

  // Cancel execution
  const handleCancelExecution = async (executionId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/executions/${executionId}/cancel`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ reason: 'Cancelled from UI' }),
        }
      );
      if (response.ok) {
        toast.success('Execution cancelled');
        fetchExecutions();
      }
    } catch (err) {
      toast.error('Failed to cancel execution');
    }
  };

  // Seed defaults
  const handleSeedDefaults = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/smart-docs/cadence/seed-defaults`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message || 'Defaults seeded');
        fetchCadences();
      }
    } catch (err) {
      toast.error('Failed to seed defaults');
    }
  };

  return (
    <div className="smart-docs-cadence">
      <div className="cadence-page-header">
        <div>
          <h1>Follow-Up Cadence Manager</h1>
          <p className="cadence-subtitle">
            Configure automated borrower outreach sequences for document collection
          </p>
        </div>
        <div className="header-actions">
          {activeTab === 'cadences' && (
            <>
              <button className="btn-seed" onClick={handleSeedDefaults}>
                Seed Defaults
              </button>
              <button className="btn-create" onClick={() => { setEditingCadence(null); setShowForm(true); }}>
                + New Cadence
              </button>
            </>
          )}
        </div>
      </div>

      <div className="cadence-tabs">
        {[
          { key: 'cadences', label: 'Cadence Templates' },
          { key: 'executions', label: 'Active Executions' },
          { key: 'analytics', label: 'Analytics' },
        ].map(tab => (
          <button
            key={tab.key}
            className={`cadence-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Create/Edit Form Modal */}
      {showForm && (
        <div className="cadence-modal-overlay" onClick={() => setShowForm(false)}>
          <div className="cadence-modal" onClick={e => e.stopPropagation()}>
            <h3>{editingCadence ? 'Edit Cadence' : 'Create New Cadence'}</h3>
            <CadenceForm
              cadence={editingCadence}
              onSave={editingCadence ? handleUpdateCadence : handleCreateCadence}
              onCancel={() => { setShowForm(false); setEditingCadence(null); }}
            />
          </div>
        </div>
      )}

      {/* CADENCES TAB */}
      {activeTab === 'cadences' && (
        <div className="cadence-content">
          <div className="cadence-filters">
            <select value={filterTrigger} onChange={e => setFilterTrigger(e.target.value)}>
              <option value="">All Trigger Types</option>
              {TRIGGER_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="cadence-loading">Loading cadences...</div>
          ) : cadences.length === 0 ? (
            <div className="cadence-empty">
              <p>No cadences configured yet.</p>
              <p>Click <strong>"Seed Defaults"</strong> to create the 5 standard cadence templates, or create a custom one.</p>
            </div>
          ) : (
            <div className="cadence-list">
              {cadences.map(cadence => (
                <div key={cadence.id} className={`cadence-card ${!cadence.is_active ? 'inactive' : ''}`}>
                  <div className="cadence-card-header">
                    <div className="cadence-card-title">
                      <h3>{cadence.cadence_name}</h3>
                      {cadence.is_system && <span className="badge badge-system">System</span>}
                      <span className={`badge badge-trigger badge-${cadence.trigger_type?.toLowerCase()}`}>
                        {TRIGGER_TYPES.find(t => t.value === cadence.trigger_type)?.label || cadence.trigger_type}
                      </span>
                    </div>
                    <div className="cadence-card-actions">
                      {cadence.is_system ? (
                        <button className="btn-action btn-clone" onClick={() => handleClone(cadence.id)}>
                          Clone
                        </button>
                      ) : (
                        <>
                          <button
                            className="btn-action btn-edit"
                            onClick={() => { setEditingCadence(cadence); setShowForm(true); }}
                          >
                            Edit
                          </button>
                          <button
                            className={`btn-action ${cadence.is_active ? 'btn-deactivate' : 'btn-activate'}`}
                            onClick={() => handleToggleActive(cadence)}
                          >
                            {cadence.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {cadence.description && (
                    <p className="cadence-card-desc">{cadence.description}</p>
                  )}

                  <div className="cadence-sequence">
                    {(cadence.channel_sequence || []).map((step, idx) => (
                      <React.Fragment key={idx}>
                        {idx > 0 && <div className="sequence-arrow">&rarr;</div>}
                        <div className="sequence-step">
                          <span className="sequence-day">Day {step.day}</span>
                          <span className="sequence-channel">
                            {CHANNELS.find(c => c.value === step.channel)?.icon}{' '}
                            {CHANNELS.find(c => c.value === step.channel)?.label || step.channel}
                          </span>
                        </div>
                      </React.Fragment>
                    ))}
                  </div>

                  <div className="cadence-card-meta">
                    <span>Max attempts: {cadence.max_attempts}</span>
                    <span>Escalate after: {cadence.escalation_after}</span>
                    <span>Quiet: {cadence.quiet_hours_start}:00 - {cadence.quiet_hours_end}:00</span>
                    {cadence.total_executions > 0 && (
                      <span>
                        {cadence.total_executions} runs
                        {cadence.total_responses > 0 && ` \u2022 ${Math.round((cadence.total_responses / cadence.total_executions) * 100)}% response`}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* EXECUTIONS TAB */}
      {activeTab === 'executions' && (
        <div className="cadence-content">
          <div className="cadence-filters">
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="PAUSED">Paused</option>
              <option value="COMPLETED">Completed</option>
              <option value="CANCELLED">Cancelled</option>
              <option value="ESCALATED">Escalated</option>
            </select>
          </div>

          {loading ? (
            <div className="cadence-loading">Loading executions...</div>
          ) : executions.length === 0 ? (
            <div className="cadence-empty">
              <p>No active executions found.</p>
              <p>Executions are created automatically when a cadence is triggered, or manually from a loan's document view.</p>
            </div>
          ) : (
            <div className="executions-list">
              {executions.map(exec => (
                <div
                  key={exec.id}
                  className={`execution-card ${selectedExecution === exec.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedExecution(exec.id);
                    fetchExecutionTimeline(exec.id);
                  }}
                >
                  <div className="execution-card-header">
                    <div>
                      <strong>{exec.borrower_name || exec.borrower_email || `Loan #${exec.loan_id}`}</strong>
                      <span className="execution-cadence-name">{exec.cadence_name}</span>
                    </div>
                    <div className="execution-card-actions">
                      <span
                        className="execution-status-badge"
                        style={{ backgroundColor: STATUS_COLORS[exec.status] + '20', color: STATUS_COLORS[exec.status] }}
                      >
                        {exec.status}
                      </span>
                      {exec.status === 'ACTIVE' && (
                        <button
                          className="btn-action btn-cancel-exec"
                          onClick={e => { e.stopPropagation(); handleCancelExecution(exec.id); }}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="execution-card-meta">
                    <span>Step {(exec.current_step || 0) + 1}</span>
                    <span>{exec.attempts_made || 0} attempts</span>
                    {exec.next_send_at && (
                      <span>Next: {new Date(exec.next_send_at).toLocaleDateString()}</span>
                    )}
                    {exec.response_received && (
                      <span className="response-badge">Responded</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedExecution && executionDetail && (
            <div className="execution-detail-panel">
              <h3>Execution Timeline</h3>
              <ExecutionTimeline execution={executionDetail} />
            </div>
          )}
        </div>
      )}

      {/* ANALYTICS TAB */}
      {activeTab === 'analytics' && (
        <div className="cadence-content">
          {loading ? (
            <div className="cadence-loading">Loading analytics...</div>
          ) : !analytics ? (
            <div className="cadence-empty">
              <p>No analytics data available yet.</p>
            </div>
          ) : (
            <div className="analytics-grid">
              <div className="analytics-card">
                <div className="analytics-value">{analytics.total_executions || 0}</div>
                <div className="analytics-label">Total Executions</div>
              </div>
              <div className="analytics-card">
                <div className="analytics-value">{analytics.total_responses || 0}</div>
                <div className="analytics-label">Responses Received</div>
              </div>
              <div className="analytics-card">
                <div className="analytics-value">
                  {analytics.response_rate != null
                    ? `${Math.round(analytics.response_rate * 100)}%`
                    : '0%'}
                </div>
                <div className="analytics-label">Response Rate</div>
              </div>
              <div className="analytics-card">
                <div className="analytics-value">
                  {analytics.avg_response_time_hours != null
                    ? `${Math.round(analytics.avg_response_time_hours)}h`
                    : 'N/A'}
                </div>
                <div className="analytics-label">Avg Response Time</div>
              </div>
              <div className="analytics-card">
                <div className="analytics-value">{analytics.total_escalations || 0}</div>
                <div className="analytics-label">Escalations</div>
              </div>
              <div className="analytics-card">
                <div className="analytics-value">
                  {analytics.escalation_rate != null
                    ? `${Math.round(analytics.escalation_rate * 100)}%`
                    : '0%'}
                </div>
                <div className="analytics-label">Escalation Rate</div>
              </div>

              {analytics.by_channel && (
                <div className="analytics-section">
                  <h4>Performance by Channel</h4>
                  <div className="channel-stats">
                    {Object.entries(analytics.by_channel).map(([channel, stats]) => (
                      <div key={channel} className="channel-stat-row">
                        <span className="channel-name">
                          {CHANNELS.find(c => c.value === channel)?.icon}{' '}
                          {CHANNELS.find(c => c.value === channel)?.label || channel}
                        </span>
                        <span className="channel-sent">{stats.sent || 0} sent</span>
                        <span className="channel-response">
                          {stats.response_rate != null
                            ? `${Math.round(stats.response_rate * 100)}%`
                            : '0%'} response
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {analytics.by_cadence && analytics.by_cadence.length > 0 && (
                <div className="analytics-section">
                  <h4>Performance by Cadence</h4>
                  <table className="analytics-table">
                    <thead>
                      <tr>
                        <th>Cadence</th>
                        <th>Executions</th>
                        <th>Responses</th>
                        <th>Rate</th>
                        <th>Avg Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.by_cadence.map((row, idx) => (
                        <tr key={idx}>
                          <td>{row.cadence_name}</td>
                          <td>{row.executions}</td>
                          <td>{row.responses}</td>
                          <td>{row.response_rate != null ? `${Math.round(row.response_rate * 100)}%` : '0%'}</td>
                          <td>{row.avg_response_hours ? `${Math.round(row.avg_response_hours)}h` : 'N/A'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
