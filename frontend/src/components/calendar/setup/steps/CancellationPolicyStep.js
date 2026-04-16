import React, { useState, useEffect, useCallback } from 'react';
import './CancellationPolicyStep.css';
import { getToken } from '../../../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

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
// Preset policy definitions
// ---------------------------------------------------------------------------

const DEFAULT_REASONS = [
  'Schedule conflict',
  'No longer interested',
  'Working with another lender',
  'Documentation not ready',
  'Rate changed',
  'Other',
];

const DEFAULT_LATE_MESSAGE =
  'This appointment is within the required notice period. Late cancellations may be tracked and could affect future booking availability.';

const PRESET_POLICIES = {
  flexible: {
    key: 'flexible',
    name: 'Flexible',
    description: 'No restrictions, borrowers can cancel anytime',
    iconLabel: 'F',
    values: {
      min_notice_hours: 0,
      max_cancellations_per_borrower: 0, // 0 = unlimited
      allow_borrower_cancel: true,
      require_reason: false,
    },
    tags: ['No notice required', 'Unlimited cancellations'],
  },
  moderate: {
    key: 'moderate',
    name: 'Moderate',
    recommended: true,
    description: '24-hour notice required, max 3 cancellations per month',
    iconLabel: 'M',
    values: {
      min_notice_hours: 24,
      max_cancellations_per_borrower: 3,
      allow_borrower_cancel: true,
      require_reason: true,
    },
    tags: ['24h notice', '3 per month', 'Reason required'],
  },
  strict: {
    key: 'strict',
    name: 'Strict',
    description: '48-hour notice, max 2 cancellations per month',
    iconLabel: 'S',
    values: {
      min_notice_hours: 48,
      max_cancellations_per_borrower: 2,
      allow_borrower_cancel: true,
      require_reason: true,
    },
    tags: ['48h notice', '2 per month', 'Reason required'],
  },
  custom: {
    key: 'custom',
    name: 'Custom',
    description: 'Configure your own cancellation rules',
    iconLabel: 'C',
    values: null, // uses current form values
    tags: ['Your rules'],
  },
};

const PRESET_ORDER = ['flexible', 'moderate', 'strict', 'custom'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Determine which preset matches the current config, if any. */
function detectPreset(config) {
  if (!config) return 'moderate';
  for (const key of ['flexible', 'moderate', 'strict']) {
    const preset = PRESET_POLICIES[key];
    const v = preset.values;
    if (
      config.min_notice_hours === v.min_notice_hours &&
      config.max_cancellations_per_borrower === v.max_cancellations_per_borrower &&
      config.allow_borrower_cancel === v.allow_borrower_cancel &&
      config.require_reason === v.require_reason
    ) {
      return key;
    }
  }
  return 'custom';
}

function formatNoticeHours(hours) {
  if (hours === 0) return 'None';
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  const remaining = hours % 24;
  if (remaining === 0) return `${days} day${days > 1 ? 's' : ''}`;
  return `${days}d ${remaining}h`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="cancel-step-toggle">
      <span className="toggle-track">
        <input
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          aria-label={label}
        />
        <span className={`toggle-track-bg ${checked ? 'on' : 'off'}`}>
          <span className={`toggle-thumb ${checked ? 'on' : 'off'}`} />
        </span>
      </span>
      <span className="toggle-text">
        <span className="toggle-label">{label}</span>
        {hint && <span className="toggle-hint">{hint}</span>}
      </span>
    </label>
  );
}

function ReasonsList({ reasons, onChange }) {
  const [newReason, setNewReason] = useState('');

  const handleAdd = () => {
    const trimmed = newReason.trim();
    if (!trimmed || reasons.includes(trimmed)) return;
    onChange([...reasons, trimmed]);
    setNewReason('');
  };

  const handleRemove = (index) => {
    onChange(reasons.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div className="reasons-list">
      <div className="reasons-tags">
        {reasons.map((reason, i) => (
          <span key={i} className="reason-tag">
            {reason}
            <button
              className="reason-remove"
              onClick={() => handleRemove(i)}
              aria-label={`Remove reason: ${reason}`}
              title="Remove"
              type="button"
            >
              x
            </button>
          </span>
        ))}
        {reasons.length === 0 && (
          <span style={{ fontSize: 13, color: '#9ca3af', fontStyle: 'italic' }}>
            No reasons configured
          </span>
        )}
      </div>
      <div className="reason-add-row">
        <input
          type="text"
          value={newReason}
          onChange={e => setNewReason(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a reason..."
          maxLength={200}
        />
        <button
          className="reason-add-btn"
          onClick={handleAdd}
          disabled={!newReason.trim()}
          type="button"
        >
          Add
        </button>
      </div>
    </div>
  );
}

function PolicyCard({ preset, selected, onClick }) {
  const isSelected = selected === preset.key;
  return (
    <button
      type="button"
      className={`policy-card${isSelected ? ' selected' : ''}`}
      onClick={() => onClick(preset.key)}
      aria-pressed={isSelected}
      aria-label={`${preset.name} cancellation policy${preset.recommended ? ' (recommended)' : ''}`}
    >
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className={`card-icon ${preset.key}`}>
            {preset.iconLabel}
          </span>
          <span className="card-name">
            {preset.name}
            {preset.recommended && <span className="card-badge">Recommended</span>}
          </span>
        </div>
        <span className="card-check">
          <span className="card-check-inner" />
        </span>
      </div>
      <p className="card-desc">{preset.description}</p>
      <div className="card-details">
        {preset.tags.map(tag => (
          <span key={tag} className="card-detail-tag">{tag}</span>
        ))}
      </div>
    </button>
  );
}

function PolicySummary({ preset }) {
  const [expanded, setExpanded] = useState(false);
  const v = preset.values;
  if (!v) return null;

  return (
    <div className="policy-summary-expand">
      <button
        type="button"
        className="policy-summary-toggle"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className={`toggle-arrow${expanded ? ' expanded' : ''}`}>&#9654;</span>
        {expanded ? 'Hide details' : 'View details'}
      </button>
      {expanded && (
        <div className="policy-summary-body">
          <div className="summary-row">
            <span className="summary-label">Minimum notice</span>
            <span className="summary-value">{formatNoticeHours(v.min_notice_hours)}</span>
          </div>
          <div className="summary-row">
            <span className="summary-label">Max cancellations/month</span>
            <span className="summary-value">{v.max_cancellations_per_borrower === 0 ? 'Unlimited' : v.max_cancellations_per_borrower}</span>
          </div>
          <div className="summary-row">
            <span className="summary-label">Borrower self-cancel</span>
            <span className="summary-value">{v.allow_borrower_cancel ? 'Allowed' : 'Staff only'}</span>
          </div>
          <div className="summary-row">
            <span className="summary-label">Reason required</span>
            <span className="summary-value">{v.require_reason ? 'Yes' : 'No'}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

/**
 * CancellationPolicyStep - Step 7 of Smart Calendar guided setup.
 *
 * Props:
 *   onComplete   - (optional) called after successful save with the saved policy data
 *   initialData  - (optional) pre-loaded policy data to avoid duplicate fetch
 */
export default function CancellationPolicyStep({ onComplete, initialData }) {
  const [loading, setLoading] = useState(!initialData);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form state
  const [selectedPreset, setSelectedPreset] = useState('moderate');
  const [config, setConfig] = useState({
    min_notice_hours: 24,
    max_cancellations_per_borrower: 3,
    allow_borrower_cancel: true,
    require_reason: true,
    cancellation_reasons: [...DEFAULT_REASONS],
    late_cancel_message: DEFAULT_LATE_MESSAGE,
    // No-show fields
    noshow_detect_after_minutes: 15,
    noshow_send_followup_email: true,
    noshow_block_repeat: false,
    noshow_block_threshold: 3,
  });

  // Fetch existing policy on mount
  useEffect(() => {
    if (initialData) {
      const merged = { ...config, ...initialData };
      setConfig(merged);
      setSelectedPreset(detectPreset(merged));
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/v1/scheduler/cancellation-policy');
        if (!cancelled) {
          const merged = { ...config, ...data };
          setConfig(merged);
          setSelectedPreset(detectPreset(merged));
        }
      } catch (err) {
        // If 404 or no policy yet, use defaults -- that is fine
        if (!cancelled && !err.message.includes('404')) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update a single config field
  const updateConfig = useCallback((field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
    setSuccess('');
  }, []);

  // Handle preset selection
  const handlePresetSelect = useCallback((presetKey) => {
    setSelectedPreset(presetKey);
    setSuccess('');
    if (presetKey !== 'custom') {
      const presetValues = PRESET_POLICIES[presetKey].values;
      setConfig(prev => ({
        ...prev,
        ...presetValues,
      }));
    }
  }, []);

  // When custom config values change, re-check if they match a preset
  useEffect(() => {
    if (selectedPreset === 'custom') return;
    const detected = detectPreset(config);
    if (detected !== selectedPreset) {
      setSelectedPreset(detected);
    }
  }, [config.min_notice_hours, config.max_cancellations_per_borrower, config.allow_borrower_cancel, config.require_reason, selectedPreset, config]);

  // Save
  const handleSave = useCallback(async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = {
        min_notice_hours: config.min_notice_hours,
        max_cancellations_per_borrower: config.max_cancellations_per_borrower,
        allow_borrower_cancel: config.allow_borrower_cancel,
        require_reason: config.require_reason,
        cancellation_reasons: config.cancellation_reasons,
        late_cancel_message: config.late_cancel_message,
        noshow_detect_after_minutes: config.noshow_detect_after_minutes,
        noshow_send_followup_email: config.noshow_send_followup_email,
        noshow_block_repeat: config.noshow_block_repeat,
        noshow_block_threshold: config.noshow_block_threshold,
      };
      const data = await apiFetch('/api/v1/scheduler/cancellation-policy', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      setSuccess('Cancellation policy saved successfully');
      setTimeout(() => setSuccess(''), 4000);
      if (onComplete) onComplete(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [config, onComplete]);

  // Determine if custom config panel should show
  const showCustomPanel = selectedPreset === 'custom';

  if (loading) {
    return (
      <div className="cancel-policy-step">
        <div className="cancel-step-loading">Loading cancellation policy...</div>
      </div>
    );
  }

  return (
    <div className="cancel-policy-step">
      <h3>Cancellation &amp; No-Show Policy</h3>
      <p className="section-subtitle">
        Set rules for how borrowers can cancel appointments. Most mortgage professionals choose the Moderate policy.
      </p>

      {error && (
        <div className="cancel-step-error">
          <span>{error}</span>
          <button className="dismiss-btn" onClick={() => setError('')} type="button">X</button>
        </div>
      )}

      {success && (
        <div className="cancel-step-success">{success}</div>
      )}

      {/* ================================================================
          Section 1: Cancellation Rules — Preset Cards
          ================================================================ */}
      <div className="cancel-policy-section">
        <h4 className="section-title">Cancellation Rules</h4>
        <p className="section-description">
          Choose a policy preset or create a custom configuration.
        </p>

        <div className="policy-cards-grid">
          {PRESET_ORDER.map(key => (
            <PolicyCard
              key={key}
              preset={PRESET_POLICIES[key]}
              selected={selectedPreset}
              onClick={handlePresetSelect}
            />
          ))}
        </div>

        {/* Expandable summary for non-custom presets */}
        {selectedPreset !== 'custom' && (
          <PolicySummary preset={PRESET_POLICIES[selectedPreset]} />
        )}
      </div>

      {/* ================================================================
          Section 2: Custom Configuration
          ================================================================ */}
      {showCustomPanel && (
        <div className="cancel-policy-section">
          <h4 className="section-title">Custom Configuration</h4>
          <p className="section-description">
            Fine-tune your cancellation rules to match your workflow.
          </p>

          <div className="custom-config-panel" style={{ borderTop: 'none', paddingTop: 0 }}>
            {/* Minimum notice hours */}
            <div className="config-row">
              <label className="config-label">Minimum Notice Period</label>
              <div className="slider-row">
                <input
                  type="range"
                  min={0}
                  max={72}
                  step={1}
                  value={config.min_notice_hours}
                  onChange={e => updateConfig('min_notice_hours', parseInt(e.target.value, 10))}
                  aria-label="Minimum notice hours"
                />
                <span className="slider-value">{formatNoticeHours(config.min_notice_hours)}</span>
              </div>
              <p className="config-hint">
                Cancellations within this window are flagged as late cancellations.
              </p>
            </div>

            {/* Max cancellations per month */}
            <div className="config-row">
              <label className="config-label">Max Cancellations Per Borrower Per Month</label>
              <div className="max-cancel-row">
                {config.max_cancellations_per_borrower > 0 ? (
                  <>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={config.max_cancellations_per_borrower}
                      onChange={e => updateConfig('max_cancellations_per_borrower', Math.min(10, Math.max(1, parseInt(e.target.value, 10) || 1)))}
                      aria-label="Maximum cancellations per month"
                    />
                    <span className="unit-label">per month</span>
                    <button
                      type="button"
                      className="unlimited-toggle"
                      onClick={() => updateConfig('max_cancellations_per_borrower', 0)}
                    >
                      Set unlimited
                    </button>
                  </>
                ) : (
                  <>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#218D8D' }}>Unlimited</span>
                    <button
                      type="button"
                      className="unlimited-toggle"
                      onClick={() => updateConfig('max_cancellations_per_borrower', 3)}
                    >
                      Set a limit
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Allow borrower self-cancel */}
            <div className="config-row">
              <Toggle
                checked={config.allow_borrower_cancel}
                onChange={v => updateConfig('allow_borrower_cancel', v)}
                label="Allow borrower self-cancellation"
                hint="When disabled, only staff can cancel appointments."
              />
            </div>

            {/* Require cancellation reason */}
            <div className="config-row">
              <Toggle
                checked={config.require_reason}
                onChange={v => updateConfig('require_reason', v)}
                label="Require cancellation reason"
                hint="Borrowers must select a reason before cancelling."
              />
            </div>
          </div>
        </div>
      )}

      {/* ================================================================
          Section 3: Cancellation Reasons
          ================================================================ */}
      <div className="cancel-policy-section">
        <h4 className="section-title">Cancellation Reasons</h4>
        <p className="section-description">
          Pre-populated reasons shown in the cancellation dropdown. Borrowers select from this list when cancelling.
        </p>

        <ReasonsList
          reasons={config.cancellation_reasons || []}
          onChange={v => updateConfig('cancellation_reasons', v)}
        />
      </div>

      {/* ================================================================
          Section 4: Late Cancellation Message
          ================================================================ */}
      <div className="cancel-policy-section">
        <h4 className="section-title">Late Cancellation Message</h4>
        <p className="section-description">
          This message is shown to borrowers when they cancel within the minimum notice period.
        </p>

        <textarea
          className="late-cancel-textarea"
          value={config.late_cancel_message || ''}
          onChange={e => updateConfig('late_cancel_message', e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Message shown for late cancellations..."
          aria-label="Late cancellation message"
        />

        {config.late_cancel_message && (
          <div className="late-cancel-preview">
            <div className="preview-label">Borrower Preview</div>
            <div className="preview-box">
              <div className="preview-heading">
                <span aria-hidden="true">!</span>
                Late Cancellation
              </div>
              <div className="preview-text">{config.late_cancel_message}</div>
            </div>
          </div>
        )}
      </div>

      {/* ================================================================
          Section 5: No-Show Policy
          ================================================================ */}
      <div className="cancel-policy-section">
        <h4 className="section-title">No-Show Policy</h4>
        <p className="section-description">
          Configure how no-shows are detected and handled.
        </p>

        <div className="noshow-config">
          {/* Auto-detect no-shows */}
          <div className="config-row">
            <label className="config-label">Auto-Detect No-Shows</label>
            <div className="slider-row">
              <input
                type="range"
                min={5}
                max={30}
                step={5}
                value={config.noshow_detect_after_minutes}
                onChange={e => updateConfig('noshow_detect_after_minutes', parseInt(e.target.value, 10))}
                aria-label="Minutes after start to detect no-show"
              />
              <span className="slider-value">{config.noshow_detect_after_minutes} min</span>
            </div>
            <p className="config-hint">
              Mark as no-show if borrower has not joined after this many minutes past the scheduled start.
            </p>
          </div>

          {/* Send follow-up email */}
          <div className="config-row">
            <Toggle
              checked={config.noshow_send_followup_email}
              onChange={v => updateConfig('noshow_send_followup_email', v)}
              label="Send follow-up email after no-show"
              hint="Automatically email the borrower to reschedule after a missed appointment."
            />
          </div>

          {/* Block repeat no-shows */}
          <div className="config-row">
            <Toggle
              checked={config.noshow_block_repeat}
              onChange={v => updateConfig('noshow_block_repeat', v)}
              label="Block repeat no-shows from booking"
              hint="Prevent borrowers who repeatedly miss appointments from self-booking."
            />

            {config.noshow_block_repeat && (
              <div className="noshow-threshold-row" style={{ marginTop: 10, marginLeft: 56 }}>
                <span className="threshold-label">Block after</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={config.noshow_block_threshold}
                  onChange={e => updateConfig('noshow_block_threshold', Math.min(10, Math.max(1, parseInt(e.target.value, 10) || 1)))}
                  aria-label="No-show block threshold"
                />
                <span className="threshold-label">no-shows in 90 days</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ================================================================
          Save Button
          ================================================================ */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingBottom: 8 }}>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '10px 28px',
            borderRadius: 8,
            border: 'none',
            background: saving ? '#9ca3af' : '#218D8D',
            color: '#fff',
            cursor: saving ? 'wait' : 'pointer',
            fontSize: 15,
            fontWeight: 600,
            opacity: saving ? 0.7 : 1,
            transition: 'background 0.15s, opacity 0.15s',
          }}
        >
          {saving ? 'Saving...' : 'Save Cancellation Policy'}
        </button>
      </div>
    </div>
  );
}
