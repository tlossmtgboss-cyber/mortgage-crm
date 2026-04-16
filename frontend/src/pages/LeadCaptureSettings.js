import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { APIError } from '../utils/errorHandling';
import './LeadCaptureSettings.css';
import { getToken } from '../utils/tokenStore';

function LeadCaptureSettings() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('sources');
  const [settings, setSettings] = useState(null);
  const [originalSettings, setOriginalSettings] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [statistics, setStatistics] = useState(null);
  const [scoringFields, setScoringFields] = useState([]);
  const [assignableUsers, setAssignableUsers] = useState([]);

  // Test scoring state
  const [testLead, setTestLead] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [testingScore, setTestingScore] = useState(false);

  // Loading and error state (managed directly to avoid infinite loop)
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Track if initial load has happened
  const loadedRef = useRef(false);

  // Toast notification state
  const [toast, setToast] = useState({ show: false, type: '', message: '' });

  const showToast = (type, message) => {
    setToast({ show: true, type, message });
    setTimeout(() => setToast({ show: false, type: '', message: '' }), 5000);
  };

  // Load settings and reference data
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      const [settingsRes, statsRes, fieldsRes, usersRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/lead-capture-settings`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/lead-capture-settings/statistics`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/lead-capture-settings/scoring-fields`, { headers }),
        fetch(`${API_BASE_URL}/api/v1/lead-capture-settings/assignable-users`, { headers })
      ]);

      if (!settingsRes.ok) {
        const err = await settingsRes.json();
        throw new APIError(err.detail?.message || 'Failed to load settings', settingsRes.status, err.detail);
      }

      const settingsData = await settingsRes.json();
      setSettings(settingsData.data);
      setOriginalSettings(JSON.parse(JSON.stringify(settingsData.data)));

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStatistics(statsData.data);
      }

      if (fieldsRes.ok) {
        const fieldsData = await fieldsRes.json();
        setScoringFields(fieldsData.data?.fields || []);
      }

      if (usersRes.ok) {
        const usersData = await usersRes.json();
        setAssignableUsers(usersData.data?.users || []);
      }

    } catch (err) {
      console.error('Error loading lead capture settings:', err);
      setError(err);
      showToast('error', 'Failed to load lead capture settings');
    } finally {
      setLoading(false);
    }
  }, []);

  // Load data on mount only
  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadData();
    }
  }, [loadData]);

  // Check for changes
  useEffect(() => {
    if (settings && originalSettings) {
      setHasChanges(JSON.stringify(settings) !== JSON.stringify(originalSettings));
    }
  }, [settings, originalSettings]);

  // Field update handler
  const updateField = (path, value) => {
    setSettings(prev => {
      const newSettings = JSON.parse(JSON.stringify(prev));
      const parts = path.split('.');
      let current = newSettings;

      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]]) {
          current[parts[i]] = {};
        }
        current = current[parts[i]];
      }

      current[parts[parts.length - 1]] = value;
      return newSettings;
    });

    if (fieldErrors[path]) {
      setFieldErrors(prev => {
        const updated = { ...prev };
        delete updated[path];
        return updated;
      });
    }
  };

  // Lead source handlers
  const toggleSource = (sourceId) => {
    setSettings(prev => {
      const newSources = prev.lead_sources.map(s =>
        s.id === sourceId ? { ...s, enabled: !s.enabled } : s
      );
      return { ...prev, lead_sources: newSources };
    });
  };

  const updateSource = (sourceId, field, value) => {
    setSettings(prev => {
      const newSources = prev.lead_sources.map(s =>
        s.id === sourceId ? { ...s, [field]: value } : s
      );
      return { ...prev, lead_sources: newSources };
    });
  };

  // Lead stage handlers
  const updateStage = (stageId, field, value) => {
    setSettings(prev => {
      const newStages = prev.lead_stages.map(s =>
        s.id === stageId ? { ...s, [field]: value } : s
      );
      return { ...prev, lead_stages: newStages };
    });
  };

  const moveStage = (stageId, direction) => {
    setSettings(prev => {
      const stages = [...prev.lead_stages].sort((a, b) => a.order - b.order);
      const idx = stages.findIndex(s => s.id === stageId);
      if ((direction === -1 && idx === 0) || (direction === 1 && idx === stages.length - 1)) {
        return prev;
      }

      const newIdx = idx + direction;
      const temp = stages[idx].order;
      stages[idx].order = stages[newIdx].order;
      stages[newIdx].order = temp;

      return { ...prev, lead_stages: stages };
    });
  };

  // Scoring rule handlers
  const toggleRule = (ruleId) => {
    setSettings(prev => {
      const newRules = prev.scoring_rules.map(r =>
        r.id === ruleId ? { ...r, enabled: !r.enabled } : r
      );
      return { ...prev, scoring_rules: newRules };
    });
  };

  const updateRule = (ruleId, field, value) => {
    setSettings(prev => {
      const newRules = prev.scoring_rules.map(r =>
        r.id === ruleId ? { ...r, [field]: value } : r
      );
      return { ...prev, scoring_rules: newRules };
    });
  };

  // Test scoring
  const handleTestScoring = async () => {
    setTestingScore(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/lead-capture-settings/test-scoring`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(testLead)
      });

      if (response.ok) {
        const data = await response.json();
        setTestResult(data.data);
      }
    } catch (err) {
      console.error('Error testing scoring:', err);
    } finally {
      setTestingScore(false);
    }
  };

  // Validate form
  const validateForm = () => {
    const errors = {};

    // Validate sources
    const enabledSources = (settings.lead_sources || []).filter(s => s.enabled);
    if (enabledSources.length === 0) {
      errors['lead_sources'] = 'At least one lead source must be enabled';
    }

    // Validate stages
    const stages = settings.lead_stages || [];
    if (stages.length < 2) {
      errors['lead_stages'] = 'At least two stages required';
    }
    if (!stages.some(s => s.is_converted)) {
      errors['lead_stages'] = 'At least one converted stage required';
    }
    if (!stages.some(s => s.is_lost)) {
      errors['lead_stages'] = 'At least one lost stage required';
    }

    // Validate thresholds
    if (settings.warm_lead_threshold >= settings.hot_lead_threshold) {
      errors['warm_lead_threshold'] = 'Must be less than hot lead threshold';
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // Save settings
  const handleSave = async () => {
    if (!validateForm()) {
      showToast('error', 'Please fix the validation errors');
      return;
    }

    setSubmitting(true);

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/lead-capture-settings`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
      });

      if (!response.ok) {
        const err = await response.json();
        if (err.detail?.field) {
          setFieldErrors({ [err.detail.field]: err.detail.message });
        }
        throw new APIError(err.detail?.message || 'Failed to save settings', response.status, err.detail);
      }

      const data = await response.json();
      setSettings(data.data);
      setOriginalSettings(JSON.parse(JSON.stringify(data.data)));
      setHasChanges(false);
      showToast('success', 'Lead capture settings saved successfully');

    } catch (err) {
      console.error('Error saving settings:', err);
      showToast('error', err.message || 'Failed to save settings');
    } finally {
      setSubmitting(false);
    }
  };

  // Discard changes
  const handleDiscard = () => {
    setSettings(JSON.parse(JSON.stringify(originalSettings)));
    setFieldErrors({});
    setHasChanges(false);
  };

  // Reset to defaults
  const handleResetDefaults = async () => {
    if (!window.confirm('Reset all lead capture settings to defaults? This cannot be undone.')) {
      return;
    }

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/lead-capture-settings/reset-defaults`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error('Failed to reset settings');
      }

      const data = await response.json();
      setSettings(data.data);
      setOriginalSettings(JSON.parse(JSON.stringify(data.data)));
      setHasChanges(false);
      showToast('success', 'Settings reset to defaults');

    } catch (err) {
      console.error('Error resetting settings:', err);
      showToast('error', 'Failed to reset settings');
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="lead-capture-settings-page">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading lead capture settings...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="lead-capture-settings-page">
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h2>Unable to Load Settings</h2>
          <p>{error.message || 'An unexpected error occurred'}</p>
          <button className="btn-primary" onClick={loadData}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!settings) return null;

  return (
    <div className="lead-capture-settings-page">
      {/* Toast Notification */}
      {toast.show && (
        <div className={`toast-notification ${toast.type}`}>
          <i className={`fas ${toast.type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
          <span>{toast.message}</span>
          <button onClick={() => setToast({ show: false, type: '', message: '' })}>
            <i className="fas fa-times"></i>
          </button>
        </div>
      )}

      {/* Header */}
      <div className="settings-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/settings')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div>
            <h1>Lead Capture Settings</h1>
            <p className="subtitle">Configure lead sources, stages, scoring, and assignment</p>
          </div>
        </div>
        <button className="btn-secondary" onClick={handleResetDefaults}>
          <i className="fas fa-undo"></i> Reset Defaults
        </button>
      </div>

      {/* Statistics Banner */}
      {statistics && (
        <div className="stats-banner">
          <div className="stat-item">
            <span className="stat-value">{statistics.total_leads_30d}</span>
            <span className="stat-label">Leads (30 days)</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{statistics.conversion_rate}%</span>
            <span className="stat-label">Conversion Rate</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{statistics.avg_response_time_minutes} min</span>
            <span className="stat-label">Avg Response Time</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{statistics.avg_lead_score}</span>
            <span className="stat-label">Avg Lead Score</span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="settings-tabs">
        <button
          className={`tab-btn ${activeTab === 'sources' ? 'active' : ''}`}
          onClick={() => setActiveTab('sources')}
        >
          <i className="fas fa-broadcast-tower"></i> Lead Sources
        </button>
        <button
          className={`tab-btn ${activeTab === 'stages' ? 'active' : ''}`}
          onClick={() => setActiveTab('stages')}
        >
          <i className="fas fa-tasks"></i> Pipeline Stages
        </button>
        <button
          className={`tab-btn ${activeTab === 'scoring' ? 'active' : ''}`}
          onClick={() => setActiveTab('scoring')}
        >
          <i className="fas fa-star"></i> Lead Scoring
        </button>
        <button
          className={`tab-btn ${activeTab === 'assignment' ? 'active' : ''}`}
          onClick={() => setActiveTab('assignment')}
        >
          <i className="fas fa-user-plus"></i> Assignment
        </button>
        <button
          className={`tab-btn ${activeTab === 'followup' ? 'active' : ''}`}
          onClick={() => setActiveTab('followup')}
        >
          <i className="fas fa-bell"></i> Follow-up
        </button>
      </div>

      {/* Lead Sources Tab */}
      {activeTab === 'sources' && (
        <div className="settings-section">
          <h2>Lead Sources</h2>
          <p className="section-description">Configure where your leads come from and how they're tracked</p>

          {fieldErrors['lead_sources'] && (
            <div className="field-error-banner">{fieldErrors['lead_sources']}</div>
          )}

          <div className="sources-grid">
            {['online', 'referral', 'marketing', 'direct', 'other'].map(category => (
              <div key={category} className="source-category">
                <h4>{category.charAt(0).toUpperCase() + category.slice(1)}</h4>
                <div className="source-list">
                  {(settings.lead_sources || [])
                    .filter(s => s.category === category)
                    .map(source => (
                      <div key={source.id} className={`source-item ${source.enabled ? 'enabled' : 'disabled'}`}>
                        <div className="source-header">
                          <label className="source-toggle">
                            <input
                              type="checkbox"
                              checked={source.enabled}
                              onChange={() => toggleSource(source.id)}
                            />
                            <span className="source-name">{source.name}</span>
                          </label>
                          {source.tracking_code && (
                            <span className="source-code">{source.tracking_code}</span>
                          )}
                        </div>
                        {source.enabled && (
                          <div className="source-options">
                            <label className="option-toggle">
                              <input
                                type="checkbox"
                                checked={source.auto_assign}
                                onChange={(e) => updateSource(source.id, 'auto_assign', e.target.checked)}
                              />
                              <span>Auto-assign</span>
                            </label>
                            {source.cost_per_lead !== undefined && source.cost_per_lead !== null && (
                              <span className="source-cost">${source.cost_per_lead}/lead</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))
                  }
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pipeline Stages Tab */}
      {activeTab === 'stages' && (
        <div className="settings-section">
          <h2>Pipeline Stages</h2>
          <p className="section-description">Define the stages leads go through in your pipeline</p>

          {fieldErrors['lead_stages'] && (
            <div className="field-error-banner">{fieldErrors['lead_stages']}</div>
          )}

          <div className="stages-list">
            {(settings.lead_stages || [])
              .sort((a, b) => a.order - b.order)
              .map((stage, idx) => (
                <div key={stage.id} className="stage-item">
                  <div className="stage-order">
                    <button
                      className="order-btn"
                      onClick={() => moveStage(stage.id, -1)}
                      disabled={idx === 0}
                    >
                      <i className="fas fa-chevron-up"></i>
                    </button>
                    <span>{idx + 1}</span>
                    <button
                      className="order-btn"
                      onClick={() => moveStage(stage.id, 1)}
                      disabled={idx === settings.lead_stages.length - 1}
                    >
                      <i className="fas fa-chevron-down"></i>
                    </button>
                  </div>

                  <div className="stage-color">
                    <input
                      type="color"
                      value={stage.color}
                      onChange={(e) => updateStage(stage.id, 'color', e.target.value)}
                    />
                  </div>

                  <div className="stage-details">
                    <input
                      type="text"
                      value={stage.name}
                      onChange={(e) => updateStage(stage.id, 'name', e.target.value)}
                      className="stage-name-input"
                    />
                    <div className="stage-badges">
                      {stage.is_active && <span className="badge active">Active</span>}
                      {stage.is_converted && <span className="badge converted">Converted</span>}
                      {stage.is_lost && <span className="badge lost">Lost</span>}
                    </div>
                  </div>

                  <div className="stage-sla">
                    <label>SLA</label>
                    <input
                      type="number"
                      min="1"
                      max="720"
                      value={stage.sla_hours || ''}
                      onChange={(e) => updateStage(stage.id, 'sla_hours', e.target.value ? parseInt(e.target.value) : null)}
                      placeholder="hrs"
                    />
                  </div>

                  <div className="stage-flags">
                    <label title="Active stage (lead still being worked)">
                      <input
                        type="checkbox"
                        checked={stage.is_active}
                        onChange={(e) => {
                          updateStage(stage.id, 'is_active', e.target.checked);
                          if (e.target.checked) {
                            updateStage(stage.id, 'is_converted', false);
                            updateStage(stage.id, 'is_lost', false);
                          }
                        }}
                      />
                      Active
                    </label>
                    <label title="Converted to loan">
                      <input
                        type="checkbox"
                        checked={stage.is_converted}
                        onChange={(e) => {
                          updateStage(stage.id, 'is_converted', e.target.checked);
                          if (e.target.checked) {
                            updateStage(stage.id, 'is_active', false);
                            updateStage(stage.id, 'is_lost', false);
                          }
                        }}
                      />
                      Converted
                    </label>
                    <label title="Lost/Dead lead">
                      <input
                        type="checkbox"
                        checked={stage.is_lost}
                        onChange={(e) => {
                          updateStage(stage.id, 'is_lost', e.target.checked);
                          if (e.target.checked) {
                            updateStage(stage.id, 'is_active', false);
                            updateStage(stage.id, 'is_converted', false);
                          }
                        }}
                      />
                      Lost
                    </label>
                  </div>
                </div>
              ))
            }
          </div>
        </div>
      )}

      {/* Lead Scoring Tab */}
      {activeTab === 'scoring' && (
        <div className="settings-section">
          <h2>Lead Scoring</h2>
          <p className="section-description">Configure how leads are scored and prioritized</p>

          <label className="toggle-option featured">
            <input
              type="checkbox"
              checked={settings.scoring_enabled}
              onChange={(e) => updateField('scoring_enabled', e.target.checked)}
            />
            <div className="toggle-content">
              <span className="toggle-label">Enable Lead Scoring</span>
              <span className="toggle-hint">Automatically score leads based on their attributes</span>
            </div>
          </label>

          {settings.scoring_enabled && (
            <>
              <div className="form-row two-col" style={{ marginTop: '24px' }}>
                <div className="form-group">
                  <label>Hot Lead Threshold</label>
                  <div className="threshold-input">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={settings.hot_lead_threshold}
                      onChange={(e) => updateField('hot_lead_threshold', parseInt(e.target.value))}
                    />
                    <span className="threshold-value hot">{settings.hot_lead_threshold}+</span>
                  </div>
                  <span className="field-hint">Leads scoring above this are marked "hot"</span>
                </div>

                <div className="form-group">
                  <label>Warm Lead Threshold</label>
                  <div className="threshold-input">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={settings.warm_lead_threshold}
                      onChange={(e) => updateField('warm_lead_threshold', parseInt(e.target.value))}
                      className={fieldErrors['warm_lead_threshold'] ? 'has-error' : ''}
                    />
                    <span className="threshold-value warm">{settings.warm_lead_threshold}+</span>
                  </div>
                  {fieldErrors['warm_lead_threshold'] && (
                    <span className="field-error">{fieldErrors['warm_lead_threshold']}</span>
                  )}
                  <span className="field-hint">Leads scoring above this are marked "warm"</span>
                </div>
              </div>

              <div className="divider"></div>

              <h3>Scoring Rules</h3>
              <div className="scoring-rules">
                {(settings.scoring_rules || []).map(rule => (
                  <div key={rule.id} className={`scoring-rule ${rule.enabled ? 'enabled' : 'disabled'}`}>
                    <label className="rule-toggle">
                      <input
                        type="checkbox"
                        checked={rule.enabled}
                        onChange={() => toggleRule(rule.id)}
                      />
                    </label>
                    <div className="rule-details">
                      <span className="rule-name">{rule.name}</span>
                      <span className="rule-condition">
                        {rule.field} {rule.operator} {rule.value || ''}
                      </span>
                    </div>
                    <div className="rule-points">
                      <input
                        type="number"
                        min="-100"
                        max="100"
                        value={rule.points}
                        onChange={(e) => updateRule(rule.id, 'points', parseInt(e.target.value))}
                        disabled={!rule.enabled}
                      />
                      <span>pts</span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="divider"></div>

              <h3>Test Scoring</h3>
              <p className="section-description">Test how a sample lead would be scored</p>

              <div className="test-scoring-form">
                <div className="test-inputs">
                  <div className="form-group">
                    <label>Email</label>
                    <input
                      type="email"
                      value={testLead.email || ''}
                      onChange={(e) => setTestLead({ ...testLead, email: e.target.value })}
                      placeholder="test@example.com"
                    />
                  </div>
                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      value={testLead.phone || ''}
                      onChange={(e) => setTestLead({ ...testLead, phone: e.target.value })}
                      placeholder="555-123-4567"
                    />
                  </div>
                  <div className="form-group">
                    <label>Loan Amount</label>
                    <input
                      type="number"
                      value={testLead.loan_amount || ''}
                      onChange={(e) => setTestLead({ ...testLead, loan_amount: e.target.value })}
                      placeholder="500000"
                    />
                  </div>
                  <div className="form-group">
                    <label>Loan Purpose</label>
                    <select
                      value={testLead.loan_purpose || ''}
                      onChange={(e) => setTestLead({ ...testLead, loan_purpose: e.target.value })}
                    >
                      <option value="">Select...</option>
                      <option value="purchase">Purchase</option>
                      <option value="refinance">Refinance</option>
                      <option value="cash_out">Cash Out</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Credit Score Range</label>
                    <select
                      value={testLead.credit_score_range || ''}
                      onChange={(e) => setTestLead({ ...testLead, credit_score_range: e.target.value })}
                    >
                      <option value="">Select...</option>
                      <option value="760+">760+</option>
                      <option value="720-759">720-759</option>
                      <option value="700+">700+</option>
                      <option value="680-719">680-719</option>
                      <option value="620-679">620-679</option>
                      <option value="below_620">Below 620</option>
                    </select>
                  </div>
                </div>

                <button
                  className="btn-secondary"
                  onClick={handleTestScoring}
                  disabled={testingScore}
                >
                  {testingScore ? 'Testing...' : 'Test Score'}
                </button>

                {testResult && (
                  <div className={`test-result ${testResult.grade}`}>
                    <div className="result-score">
                      <span className="score-value">{testResult.total_score}</span>
                      <span className="score-label">points</span>
                    </div>
                    <div className="result-grade">
                      <span className={`grade-badge ${testResult.grade}`}>
                        {testResult.grade.toUpperCase()}
                      </span>
                    </div>
                    <div className="result-rules">
                      <h5>Applied Rules:</h5>
                      <ul>
                        {testResult.applied_rules.map((rule, i) => (
                          <li key={i}>
                            {rule.rule_name}: <strong>+{rule.points}</strong>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Assignment Tab */}
      {activeTab === 'assignment' && (
        <div className="settings-section">
          <h2>Lead Assignment</h2>
          <p className="section-description">Configure how leads are assigned to team members</p>

          <div className="form-group">
            <label>Assignment Method</label>
            <div className="assignment-methods">
              {[
                { id: 'round_robin', name: 'Round Robin', desc: 'Distribute leads evenly across team' },
                { id: 'weighted', name: 'Weighted', desc: 'Assign based on capacity weights' },
                { id: 'geographic', name: 'Geographic', desc: 'Assign based on lead location' },
                { id: 'manual', name: 'Manual', desc: 'All leads require manual assignment' }
              ].map(method => (
                <label key={method.id} className={`method-option ${settings.assignment?.method === method.id ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="assignment_method"
                    value={method.id}
                    checked={settings.assignment?.method === method.id}
                    onChange={(e) => updateField('assignment.method', e.target.value)}
                  />
                  <div className="method-content">
                    <span className="method-name">{method.name}</span>
                    <span className="method-desc">{method.desc}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {settings.assignment?.method === 'round_robin' && (
            <div className="form-group">
              <label>Round Robin Users</label>
              <div className="user-selection">
                {assignableUsers.map(user => (
                  <label key={user.id} className="user-option">
                    <input
                      type="checkbox"
                      checked={(settings.assignment?.round_robin_users || []).includes(user.id)}
                      onChange={(e) => {
                        const users = settings.assignment?.round_robin_users || [];
                        if (e.target.checked) {
                          updateField('assignment.round_robin_users', [...users, user.id]);
                        } else {
                          updateField('assignment.round_robin_users', users.filter(id => id !== user.id));
                        }
                      }}
                    />
                    <span className="user-name">{user.name}</span>
                    <span className="user-load">{user.current_leads} leads</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="divider"></div>

          <h3>Capacity Settings</h3>

          <div className="toggle-options">
            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.assignment?.respect_capacity}
                onChange={(e) => updateField('assignment.respect_capacity', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Respect User Capacity</span>
                <span className="toggle-hint">Skip users who have reached their daily lead limit</span>
              </div>
            </label>

            <label className="toggle-option">
              <input
                type="checkbox"
                checked={settings.assignment?.business_hours_only}
                onChange={(e) => updateField('assignment.business_hours_only', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Business Hours Only</span>
                <span className="toggle-hint">Only auto-assign during business hours</span>
              </div>
            </label>
          </div>

          <div className="form-group" style={{ maxWidth: '250px', marginTop: '16px' }}>
            <label>Max Daily Leads Per User</label>
            <input
              type="number"
              min="1"
              max="500"
              value={settings.assignment?.max_daily_leads || 50}
              onChange={(e) => updateField('assignment.max_daily_leads', parseInt(e.target.value))}
            />
          </div>

          <div className="divider"></div>

          <h3>Deduplication</h3>

          <label className="toggle-option">
            <input
              type="checkbox"
              checked={settings.deduplication?.enabled}
              onChange={(e) => updateField('deduplication.enabled', e.target.checked)}
            />
            <div className="toggle-content">
              <span className="toggle-label">Enable Deduplication</span>
              <span className="toggle-hint">Detect and handle duplicate leads</span>
            </div>
          </label>

          {settings.deduplication?.enabled && (
            <div className="form-row two-col" style={{ marginTop: '16px' }}>
              <div className="form-group">
                <label>Match Window (Days)</label>
                <input
                  type="number"
                  min="1"
                  max="365"
                  value={settings.deduplication?.match_window_days || 30}
                  onChange={(e) => updateField('deduplication.match_window_days', parseInt(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label>Action on Duplicate</label>
                <select
                  value={settings.deduplication?.action_on_duplicate || 'merge'}
                  onChange={(e) => updateField('deduplication.action_on_duplicate', e.target.value)}
                >
                  <option value="merge">Merge with existing</option>
                  <option value="update">Update existing</option>
                  <option value="reject">Reject duplicate</option>
                  <option value="create_task">Create review task</option>
                </select>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Follow-up Tab */}
      {activeTab === 'followup' && (
        <div className="settings-section">
          <h2>Follow-up & Notifications</h2>
          <p className="section-description">Configure automatic follow-up and notification settings</p>

          <div className="notification-group">
            <h3>Lead Notifications</h3>

            <div className="toggle-options">
              <label className="toggle-option">
                <input
                  type="checkbox"
                  checked={settings.notify_on_new_lead}
                  onChange={(e) => updateField('notify_on_new_lead', e.target.checked)}
                />
                <div className="toggle-content">
                  <span className="toggle-label">Notify on New Lead</span>
                  <span className="toggle-hint">Send notification when a new lead is captured</span>
                </div>
              </label>

              <label className="toggle-option">
                <input
                  type="checkbox"
                  checked={settings.notify_on_hot_lead}
                  onChange={(e) => updateField('notify_on_hot_lead', e.target.checked)}
                />
                <div className="toggle-content">
                  <span className="toggle-label">Notify on Hot Lead</span>
                  <span className="toggle-hint">Send priority notification for high-scoring leads</span>
                </div>
              </label>
            </div>

            <div className="form-group" style={{ marginTop: '16px' }}>
              <label>Notification Channels</label>
              <div className="channel-options">
                {['email', 'sms', 'push'].map(channel => (
                  <label key={channel} className="channel-option">
                    <input
                      type="checkbox"
                      checked={(settings.instant_notification_channels || []).includes(channel)}
                      onChange={(e) => {
                        const channels = settings.instant_notification_channels || [];
                        if (e.target.checked) {
                          updateField('instant_notification_channels', [...channels, channel]);
                        } else {
                          updateField('instant_notification_channels', channels.filter(c => c !== channel));
                        }
                      }}
                    />
                    <span>{channel.charAt(0).toUpperCase() + channel.slice(1)}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="divider"></div>

          <div className="notification-group">
            <h3>Automatic Follow-up</h3>

            <label className="toggle-option featured">
              <input
                type="checkbox"
                checked={settings.auto_followup_enabled}
                onChange={(e) => updateField('auto_followup_enabled', e.target.checked)}
              />
              <div className="toggle-content">
                <span className="toggle-label">Enable Automatic Follow-up</span>
                <span className="toggle-hint">Automatically send follow-up messages to new leads</span>
              </div>
            </label>

            {settings.auto_followup_enabled && (
              <div className="form-row two-col" style={{ marginTop: '16px' }}>
                <div className="form-group">
                  <label>Initial Follow-up (Minutes)</label>
                  <input
                    type="number"
                    min="1"
                    max="1440"
                    value={settings.initial_followup_minutes || 15}
                    onChange={(e) => updateField('initial_followup_minutes', parseInt(e.target.value))}
                  />
                  <span className="field-hint">Time before first automated contact</span>
                </div>

                <div className="form-group">
                  <label>Follow-up Reminder (Hours)</label>
                  <input
                    type="number"
                    min="1"
                    max="168"
                    value={settings.followup_reminder_hours || 24}
                    onChange={(e) => updateField('followup_reminder_hours', parseInt(e.target.value))}
                  />
                  <span className="field-hint">Reminder if no response received</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sticky Save Bar */}
      {hasChanges && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button className="btn-secondary" onClick={handleDiscard} disabled={submitting}>
                Discard
              </button>
              <button className="btn-primary" onClick={handleSave} disabled={submitting}>
                {submitting ? (
                  <>
                    <span className="spinner-sm"></span> Saving...
                  </>
                ) : (
                  <>
                    <i className="fas fa-check"></i> Save Changes
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LeadCaptureSettings;
