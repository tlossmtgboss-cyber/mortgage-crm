/**
 * Re-Engagement Config Manager
 *
 * Self-contained component for configuring AI prospect re-engagement.
 * Manages own state, loading, and API calls (same pattern as AppointmentTypesManager).
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from '../utils/toast';
import api from '../services/api';
import './ReengagementConfigManager.css';

const PREDEFINED_STAGES = [
  'Prospect',
  'Long-Term Nurture',
  'Attempted Contact',
  'New',
  'Credit Repair',
  'Pre-Qualified',
  'Rate Watch',
];

const DEFAULT_CONFIG = {
  enabled: false,
  stale_days: 30,
  daily_limit: 20,
  max_turns: 8,
  expiry_days: 7,
  initial_message_template: '',
  eligible_stages: ['Prospect', 'Long-Term Nurture', 'Attempted Contact', 'New', 'Credit Repair'],
};

function ReengagementConfigManager() {
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [newStageInput, setNewStageInput] = useState('');
  const [stageSelectValue, setStageSelectValue] = useState('');

  // Track the saved config to detect dirty state
  const savedConfigRef = useRef(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/v1/prospect-reengagement/config');
      const data = response.data?.data;
      if (data) {
        const loaded = {
          enabled: data.enabled ?? DEFAULT_CONFIG.enabled,
          stale_days: data.stale_days ?? DEFAULT_CONFIG.stale_days,
          daily_limit: data.daily_limit ?? DEFAULT_CONFIG.daily_limit,
          max_turns: data.max_turns ?? DEFAULT_CONFIG.max_turns,
          expiry_days: data.expiry_days ?? DEFAULT_CONFIG.expiry_days,
          initial_message_template: data.initial_message_template ?? DEFAULT_CONFIG.initial_message_template,
          eligible_stages: data.eligible_stages ?? DEFAULT_CONFIG.eligible_stages,
        };
        setConfig(loaded);
        savedConfigRef.current = JSON.stringify(loaded);
      }
    } catch (error) {
      toast.error('Failed to load re-engagement settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Dirty-state tracking
  useEffect(() => {
    if (savedConfigRef.current === null) return;
    const isDirty = JSON.stringify(config) !== savedConfigRef.current;
    setHasChanges(isDirty);
  }, [config]);

  const saveConfig = async () => {
    setSaving(true);
    try {
      await api.put('/api/v1/prospect-reengagement/config', config);
      toast.success('Re-engagement settings saved');
      savedConfigRef.current = JSON.stringify(config);
      setHasChanges(false);
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || 'Failed to save re-engagement settings');
    } finally {
      setSaving(false);
    }
  };

  const discardChanges = () => {
    if (savedConfigRef.current) {
      setConfig(JSON.parse(savedConfigRef.current));
      setHasChanges(false);
    }
  };

  const updateConfig = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const addEligibleStage = (stage) => {
    const trimmed = stage.trim();
    if (trimmed && !config.eligible_stages.includes(trimmed)) {
      setConfig(prev => ({
        ...prev,
        eligible_stages: [...prev.eligible_stages, trimmed],
      }));
    }
  };

  const removeEligibleStage = (stage) => {
    setConfig(prev => ({
      ...prev,
      eligible_stages: prev.eligible_stages.filter(s => s !== stage),
    }));
  };

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Loading re-engagement settings...</p>
      </div>
    );
  }

  return (
    <div className="reengagement-panel" role="region" aria-label="Re-Engagement Configuration">
      {/* Compliance Banner */}
      <div className="reengagement-compliance-banner">
        <i className="fas fa-shield-alt"></i>
        <div>
          <strong>SMS Compliance</strong>
          <p>
            Re-engagement messages are sent via SMS. The system automatically enforces TCPA calling
            hours (8 AM - 9 PM local time), checks opt-out lists, and verifies SMS consent before
            sending. Leads who reply STOP are automatically opted out. Ensure your message template
            is compliant with your organization's communication policies.
          </p>
        </div>
      </div>

      {/* Info Card */}
      <div className="reengagement-info-card">
        <i className="fas fa-info-circle"></i>
        <div>
          <strong>AI Prospect Re-Engagement</strong>
          <p>
            Automatically reaches out to stale leads based on the <em>Last Touched Date</em> on
            their client profile. Leads with no contact activity for the configured number of days
            become eligible for AI-driven outreach sequences.
          </p>
        </div>
      </div>

      {/* Enable/Disable Toggle */}
      <section className="settings-section reengagement-section">
        <div className="reengagement-toggle-row">
          <div className="reengagement-toggle-label">
            <h3>Enable Re-Engagement</h3>
            <p>When enabled, the AI will automatically initiate outreach to stale leads on a daily schedule.</p>
          </div>
          <label className="reengagement-toggle">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => updateConfig('enabled', e.target.checked)}
              aria-label="Enable or disable re-engagement"
            />
            <span className="reengagement-toggle-slider"></span>
          </label>
        </div>
      </section>

      {/* Timing & Limits */}
      <section className="settings-section reengagement-section">
        <h2>Timing & Limits</h2>

        <div className="form-row">
          <label htmlFor="re-stale_days">Stale Days Threshold</label>
          <input
            id="re-stale_days"
            type="number"
            min="7"
            max="365"
            value={config.stale_days}
            onChange={(e) => updateConfig('stale_days', parseInt(e.target.value) || 30)}
          />
          <span className="field-hint">Leads with no contact for this many days become eligible for re-engagement</span>
        </div>

        <div className="form-row">
          <label htmlFor="re-daily_limit">Daily Outreach Limit</label>
          <input
            id="re-daily_limit"
            type="number"
            min="1"
            max="100"
            value={config.daily_limit}
            onChange={(e) => updateConfig('daily_limit', parseInt(e.target.value) || 20)}
          />
          <span className="field-hint">Maximum re-engagement messages sent per day per organization</span>
        </div>

        <div className="form-row">
          <label htmlFor="re-max_turns">Max Conversation Turns</label>
          <input
            id="re-max_turns"
            type="number"
            min="2"
            max="20"
            value={config.max_turns}
            onChange={(e) => updateConfig('max_turns', parseInt(e.target.value) || 8)}
          />
          <span className="field-hint">Maximum back-and-forth messages in a re-engagement conversation</span>
        </div>

        <div className="form-row">
          <label htmlFor="re-expiry_days">Conversation Expiry (days)</label>
          <input
            id="re-expiry_days"
            type="number"
            min="1"
            max="30"
            value={config.expiry_days}
            onChange={(e) => updateConfig('expiry_days', parseInt(e.target.value) || 7)}
          />
          <span className="field-hint">Conversations expire after this many days with no reply from the lead</span>
        </div>
      </section>

      {/* Eligible Lead Stages */}
      <section className="settings-section reengagement-section">
        <h2>Eligible Lead Stages</h2>
        <p className="section-description">Only leads in these stages will be considered for re-engagement outreach.</p>

        <div className="stage-chips">
          {config.eligible_stages.map(stage => (
            <span key={stage} className="stage-chip">
              {stage}
              <button
                type="button"
                className="stage-chip-remove"
                onClick={() => removeEligibleStage(stage)}
                title={`Remove ${stage}`}
              >
                <i className="fas fa-times"></i>
              </button>
            </span>
          ))}
          {config.eligible_stages.length === 0 && (
            <span className="stage-chips-empty">No stages selected — re-engagement will not target any leads</span>
          )}
        </div>

        <div className="stage-add-row">
          <select
            className="stage-select"
            value={stageSelectValue}
            onChange={(e) => {
              if (e.target.value) {
                addEligibleStage(e.target.value);
              }
              setStageSelectValue('');
            }}
          >
            <option value="">Add a stage...</option>
            {PREDEFINED_STAGES
              .filter(s => !config.eligible_stages.includes(s))
              .map(s => (
                <option key={s} value={s}>{s}</option>
              ))
            }
          </select>
          <div className="stage-custom-add">
            <input
              type="text"
              placeholder="Custom stage name"
              value={newStageInput}
              onChange={(e) => setNewStageInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (newStageInput.trim()) {
                    addEligibleStage(newStageInput);
                    setNewStageInput('');
                  }
                }
              }}
            />
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                if (newStageInput.trim()) {
                  addEligibleStage(newStageInput);
                  setNewStageInput('');
                }
              }}
            >
              Add
            </button>
          </div>
        </div>
      </section>

      {/* Message Template */}
      <section className="settings-section reengagement-section">
        <h2>Initial Message Template</h2>
        <p className="section-description">The first message sent to re-engage a stale lead. Use merge fields to personalize.</p>

        <div className="form-row">
          <textarea
            className="template-textarea"
            rows="5"
            value={config.initial_message_template}
            onChange={(e) => updateConfig('initial_message_template', e.target.value)}
            aria-label="Initial message template"
            placeholder={`Hi {first_name}, this is {lo_first_name}. I wanted to check in — are you still exploring mortgage options? I'd love to help if you have any questions.`}
          />
          <div className="merge-fields-hint">
            <strong>Available merge fields:</strong> {'{first_name}'}, {'{lo_first_name}'}, {'{lo_last_name}'}
          </div>
        </div>
      </section>

      {/* Sticky Save Bar */}
      {hasChanges && (
        <div className="reengagement-save-bar-sticky">
          <div className="reengagement-save-bar-content">
            <span>You have unsaved changes</span>
            <div className="reengagement-save-bar-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={discardChanges}
                disabled={saving}
              >
                Discard
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={saveConfig}
                disabled={saving}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                ) : (
                  <><i className="fas fa-save"></i> Save Re-Engagement Settings</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default ReengagementConfigManager;
