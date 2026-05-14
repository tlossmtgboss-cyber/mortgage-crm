import React, { useState, useEffect } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import { API_BASE } from './shared/constants';

const MorningBriefingSettings = () => {
  const defaultSections = { pipeline: true, at_risk: true, stale_leads: true, appointments: true, conditions: true, yesterday: true };
  const defaultThresholds = { at_risk_days: 10, stale_lead_days: 7, stale_lead_high_score_days: 3, lock_expiring_days: 3, max_at_risk_items: 10, max_stale_lead_items: 10 };
  const [prefs, setPrefs] = useState({
    briefing_enabled: true, briefing_hour: 7, timezone: '',
    sections: { ...defaultSections }, thresholds: { ...defaultThresholds }, ai_tone: 'balanced',
  });
  const [savedPrefs, setSavedPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const fetchPrefs = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/briefing/preferences`, {
          headers: getAuthHeaders(),
        });
        if (res.ok) {
          const data = await res.json();
          const merged = {
            ...data,
            sections: { ...defaultSections, ...(data.sections || {}) },
            thresholds: { ...defaultThresholds, ...(data.thresholds || {}) },
            ai_tone: data.ai_tone || 'balanced',
          };
          setPrefs(merged);
          setSavedPrefs(JSON.stringify(merged));
        }
      } catch (err) { console.error('Failed to fetch briefing preferences', err); }
      finally { setLoading(false); }
    };
    fetchPrefs();
  }, []);

  const isDirty = savedPrefs !== null && JSON.stringify(prefs) !== savedPrefs;

  const savePrefs = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/briefing/preferences`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          briefing_enabled: prefs.briefing_enabled,
          briefing_hour: prefs.briefing_hour,
          sections: prefs.sections,
          thresholds: prefs.thresholds,
          ai_tone: prefs.ai_tone,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const merged = {
          ...data,
          sections: { ...defaultSections, ...(data.sections || {}) },
          thresholds: { ...defaultThresholds, ...(data.thresholds || {}) },
          ai_tone: data.ai_tone || 'balanced',
        };
        setPrefs(merged);
        setSavedPrefs(JSON.stringify(merged));
        setMessage({ type: 'success', text: 'Briefing preferences saved' });
      } else {
        setMessage({ type: 'error', text: 'Failed to save preferences' });
      }
    } catch (err) { setMessage({ type: 'error', text: 'Failed to save preferences' }); }
    finally { setSaving(false); }
  };

  const generateNow = async () => {
    setGenerating(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/briefing/generate-now?force=true`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setMessage({ type: 'success', text: 'Briefing generation started — check your Dashboard in a minute' });
      } else {
        const data = await res.json().catch(() => ({}));
        setMessage({ type: 'error', text: data?.detail || 'Failed to generate briefing' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to generate briefing' });
    }
    finally { setGenerating(false); }
  };

  const updateSection = (key, val) => setPrefs(p => ({ ...p, sections: { ...p.sections, [key]: val } }));
  const updateThreshold = (key, val) => {
    const num = parseInt(val);
    if (!isNaN(num) && num >= 1) setPrefs(p => ({ ...p, thresholds: { ...p.thresholds, [key]: num } }));
  };

  if (loading) return <div className="settings-section"><h3>Morning Briefing</h3><p>Loading...</p></div>;

  const hourOptions = [];
  for (let h = 5; h <= 11; h++) {
    hourOptions.push(<option key={h} value={h}>{`${h}:00 AM`}</option>);
  }

  const sectionLabels = {
    pipeline: 'Pipeline snapshot',
    at_risk: 'At-risk loans',
    stale_leads: 'Stale leads',
    appointments: "Today's appointments",
    conditions: 'Pending conditions',
    yesterday: "Yesterday's activity",
  };

  const thresholdLabels = {
    at_risk_days: { label: 'Days without movement to flag', suffix: 'days' },
    stale_lead_days: { label: 'Days silent to flag lead', suffix: 'days' },
    stale_lead_high_score_days: { label: 'Days silent for high-score leads', suffix: 'days' },
    lock_expiring_days: { label: 'Lock expiring within', suffix: 'days' },
    max_at_risk_items: { label: 'Max at-risk items shown', suffix: '' },
    max_stale_lead_items: { label: 'Max stale leads shown', suffix: '' },
  };

  const disabled = !prefs.briefing_enabled;

  return (
    <div className="settings-section">
      <h3>Morning Briefing</h3>
      <p className="settings-description">Get a daily AI-powered briefing of your pipeline, priorities, and appointments delivered to your email and Dashboard.</p>

      <div className="settings-row">
        <label className="settings-toggle">
          <input type="checkbox" checked={prefs.briefing_enabled} onChange={(e) => setPrefs({ ...prefs, briefing_enabled: e.target.checked })} />
          <span>Enable daily briefing</span>
        </label>
      </div>

      <div className="settings-row">
        <label>Delivery time</label>
        <select value={prefs.briefing_hour} onChange={(e) => setPrefs({ ...prefs, briefing_hour: parseInt(e.target.value) })} disabled={disabled}>
          {hourOptions}
        </select>
        {prefs.timezone && <span className="settings-hint">in your timezone: {prefs.timezone}</span>}
      </div>

      <div className="settings-row">
        <label>AI narrative style</label>
        <div className="settings-radio-group">
          {['concise', 'balanced', 'detailed'].map(tone => (
            <label key={tone} className="settings-radio">
              <input type="radio" name="ai_tone" value={tone} checked={prefs.ai_tone === tone} onChange={() => setPrefs({ ...prefs, ai_tone: tone })} disabled={disabled} />
              <span style={{ textTransform: 'capitalize' }}>{tone}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="settings-subsection">
        <h4>Sections</h4>
        <p className="settings-hint">Choose which sections appear in your briefing.</p>
        <div className="settings-checkboxes">
          {Object.entries(sectionLabels).map(([key, label]) => (
            <label key={key} className="settings-toggle">
              <input type="checkbox" checked={prefs.sections[key] !== false} onChange={(e) => updateSection(key, e.target.checked)} disabled={disabled} />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="settings-subsection">
        <h4>Thresholds</h4>
        <p className="settings-hint">Customize when items are flagged in your briefing.</p>
        <div className="settings-thresholds">
          {Object.entries(thresholdLabels).map(([key, { label, suffix }]) => (
            <div key={key} className="settings-row settings-threshold-row">
              <label>{label}</label>
              <div className="settings-threshold-input">
                <input type="number" min="1" max="60" value={prefs.thresholds[key] || ''} onChange={(e) => updateThreshold(key, e.target.value)} disabled={disabled} style={{ width: 60, textAlign: 'center' }} />
                {suffix && <span className="settings-hint">{suffix}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-row settings-actions">
        <button onClick={savePrefs} disabled={saving || !isDirty} className="btn btn-primary">
          {saving ? 'Saving...' : isDirty ? 'Save Preferences' : 'Saved'}
        </button>
        <button onClick={generateNow} disabled={generating || !prefs.briefing_enabled || isDirty} className="btn btn-secondary" title={isDirty ? 'Save preferences first' : ''}>
          {generating ? 'Generating...' : 'Generate Now'}
        </button>
      </div>

      {message && (
        <div className={`settings-message ${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  );
};

export default MorningBriefingSettings;
