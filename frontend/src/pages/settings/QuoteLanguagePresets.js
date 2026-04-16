/**
 * Quote Language Presets Editor
 *
 * Manages compliant language snippets for the AI voice agent.
 * Ensures agents never "freestyle" promises and stay compliant.
 *
 * Policies:
 * - range_only: When we can quote an indicative rate range
 * - ballpark: When we don't have enough detail to quote
 * - no_quote: When we cannot/should not quote numbers
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './QuoteLanguagePresets.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// Default presets structure
const DEFAULT_PRESETS = {
  version: "1.0.0",
  rules: {
    range_only: {
      description: "Use when borrower is eligible and we can provide an indicative rate range",
      opener: [],
      range_phrase: [],
      close: []
    },
    ballpark: {
      description: "Use when we don't have enough detail to quote even a range",
      opener: [],
      close: []
    },
    no_quote: {
      description: "Use when we cannot or should not quote any numbers",
      opener: [],
      close: []
    }
  },
  goal_overrides: {},
  segment_overrides: {},
  disclaimer_templates: {
    default: "",
    short: ""
  }
};

const QuoteLanguagePresets = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessSettings = isAdmin || hasAnyPermission(['settings.manage', 'admin.manage', 'system.admin']) || userRole === 'admin';
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [presets, setPresets] = useState(DEFAULT_PRESETS);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedPolicy, setSelectedPolicy] = useState('range_only');
  const [selectedGoal, setSelectedGoal] = useState('');
  const [selectedSegment, setSelectedSegment] = useState('');

  // Edit mode states
  const [editingPhrase, setEditingPhrase] = useState(null);
  const [newPhraseText, setNewPhraseText] = useState('');

  // Test tool state
  const [testParams, setTestParams] = useState({
    eligible: true,
    quote_policy: 'range_only',
    goal: 'rate_term_refi_review',
    segment: '',
    rate_range_text: '6.25% - 6.75%'
  });
  const [testResult, setTestResult] = useState(null);

  const getAuthHeaders = () => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const fetchPresets = useCallback(async () => {
    try {
      setLoading(true);
      // Fetch from static config file or API
      const res = await fetch(`${API_URL}/api/v1/quote-language/presets`, {
        headers: getAuthHeaders()
      });

      if (res.ok) {
        const data = await res.json();
        setPresets(data);
      } else {
        // If API not available, load from a reasonable default
        console.log('Using default presets');
      }
    } catch (err) {
      console.error('Error fetching presets:', err);
      // Keep defaults on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  const handleTestSelection = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quote-language/select`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(testParams)
      });

      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      } else {
        setTestResult({ error: 'Failed to test selection' });
      }
    } catch (err) {
      setTestResult({ error: 'Failed to test selection' });
    }
  };

  const handleAddPhrase = (policy, phraseType) => {
    if (!newPhraseText.trim()) return;

    setPresets(prev => {
      const updated = { ...prev };
      if (!updated.rules[policy][phraseType]) {
        updated.rules[policy][phraseType] = [];
      }
      updated.rules[policy][phraseType] = [
        ...updated.rules[policy][phraseType],
        newPhraseText.trim()
      ];
      return updated;
    });

    setNewPhraseText('');
    setEditingPhrase(null);
    setSuccess('Phrase added');
    setTimeout(() => setSuccess(null), 2000);
  };

  const handleRemovePhrase = (policy, phraseType, index) => {
    setPresets(prev => {
      const updated = { ...prev };
      updated.rules[policy][phraseType] = updated.rules[policy][phraseType].filter((_, i) => i !== index);
      return updated;
    });
    setSuccess('Phrase removed');
    setTimeout(() => setSuccess(null), 2000);
  };

  const handleUpdateDisclaimer = (key, value) => {
    setPresets(prev => ({
      ...prev,
      disclaimer_templates: {
        ...prev.disclaimer_templates,
        [key]: value
      }
    }));
  };

  const handleSavePresets = async () => {
    try {
      setSaving(true);
      setError(null);

      const res = await fetch(`${API_URL}/api/v1/quote-language/presets`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(presets)
      });

      if (res.ok) {
        setSuccess('Presets saved successfully!');
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError('Failed to save presets');
      }
    } catch (err) {
      setError('Failed to save presets');
    } finally {
      setSaving(false);
    }
  };

  const getPolicyLabel = (policy) => {
    const labels = {
      range_only: 'Range Only',
      ballpark: 'Ballpark',
      no_quote: 'No Quote'
    };
    return labels[policy] || policy;
  };

  const getPolicyDescription = (policy) => {
    return presets.rules[policy]?.description || '';
  };

  const getPhraseTypeLabel = (type) => {
    const labels = {
      opener: 'Opening Statement',
      range_phrase: 'Rate Range Phrase',
      close: 'Closing / CTA',
      value_prop: 'Value Proposition'
    };
    return labels[type] || type;
  };

  if (loading) {
    return (
      <div className="quote-language-presets">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading Quote Language Presets...</p>
        </div>
      </div>
    );
  }

  if (!canAccessSettings) {
    return (
      <div className="quote-language-presets">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Quote Language Presets.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="quote-language-presets">
      <div className="page-header">
        <div>
          <h1>Quote Language Presets</h1>
          <p>Manage compliant language snippets for the AI voice agent</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleSavePresets}
          disabled={saving}
        >
          {saving ? 'Saving...' : '💾 Save Changes'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Tabs */}
      <div className="presets-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'policies' ? 'active' : ''}
          onClick={() => setActiveTab('policies')}
        >
          Policy Buckets
        </button>
        <button
          className={activeTab === 'overrides' ? 'active' : ''}
          onClick={() => setActiveTab('overrides')}
        >
          Goal/Segment Overrides
        </button>
        <button
          className={activeTab === 'disclaimers' ? 'active' : ''}
          onClick={() => setActiveTab('disclaimers')}
        >
          Disclaimers
        </button>
        <button
          className={activeTab === 'test' ? 'active' : ''}
          onClick={() => setActiveTab('test')}
        >
          Test Tool
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="overview-tab">
          <div className="overview-grid">
            <div className="overview-card">
              <h3>📊 Policy Buckets</h3>
              <p>Three main buckets determine which language to use:</p>
              <ul>
                <li><strong>Range Only:</strong> Eligible borrower, can quote indicative range</li>
                <li><strong>Ballpark:</strong> Unknown eligibility, give general direction</li>
                <li><strong>No Quote:</strong> Cannot responsibly quote any numbers</li>
              </ul>
            </div>

            <div className="overview-card">
              <h3>🎯 Selection Logic</h3>
              <p>Policy bucket is determined by:</p>
              <div className="logic-flow">
                <div className="logic-step">
                  <code>eligible = true</code> + <code>quote_policy = range_only</code>
                  <span>→ Range Only</span>
                </div>
                <div className="logic-step">
                  <code>eligible = unknown</code>
                  <span>→ Ballpark</span>
                </div>
                <div className="logic-step">
                  <code>else</code>
                  <span>→ No Quote</span>
                </div>
              </div>
            </div>

            <div className="overview-card warning">
              <h3>⚠️ Compliance Notes</h3>
              <div className="compliance-section">
                <div className="never-say">
                  <h4>Never Say:</h4>
                  <ul>
                    <li>"I guarantee"</li>
                    <li>"You will definitely get"</li>
                    <li>"This is your rate"</li>
                    <li>"I promise"</li>
                    <li>"100% certain"</li>
                  </ul>
                </div>
                <div className="always-include">
                  <h4>Always Include:</h4>
                  <ul>
                    <li>"Subject to approval"</li>
                    <li>"Estimate/estimated/range"</li>
                    <li>"Final terms depend on review"</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <div className="stats-row">
            <div className="stat-item">
              <div className="stat-number">{presets.rules?.range_only?.opener?.length || 0}</div>
              <div className="stat-label">Range Openers</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{presets.rules?.ballpark?.opener?.length || 0}</div>
              <div className="stat-label">Ballpark Openers</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{presets.rules?.no_quote?.opener?.length || 0}</div>
              <div className="stat-label">No Quote Openers</div>
            </div>
            <div className="stat-item">
              <div className="stat-number">{Object.keys(presets.goal_overrides || {}).length}</div>
              <div className="stat-label">Goal Overrides</div>
            </div>
          </div>
        </div>
      )}

      {/* Policy Buckets Tab */}
      {activeTab === 'policies' && (
        <div className="policies-tab">
          <div className="policy-selector">
            {['range_only', 'ballpark', 'no_quote'].map(policy => (
              <button
                key={policy}
                className={`policy-btn ${selectedPolicy === policy ? 'active' : ''}`}
                onClick={() => setSelectedPolicy(policy)}
              >
                {getPolicyLabel(policy)}
              </button>
            ))}
          </div>

          <div className="policy-content">
            <div className="policy-header">
              <h3>{getPolicyLabel(selectedPolicy)}</h3>
              <p>{getPolicyDescription(selectedPolicy)}</p>
            </div>

            {/* Phrase Types */}
            {['opener', 'range_phrase', 'close'].map(phraseType => {
              const phrases = presets.rules[selectedPolicy]?.[phraseType] || [];
              if (phraseType === 'range_phrase' && selectedPolicy !== 'range_only') return null;

              return (
                <div key={phraseType} className="phrase-section">
                  <div className="phrase-header">
                    <h4>{getPhraseTypeLabel(phraseType)}</h4>
                    <span className="phrase-count">{phrases.length} phrases</span>
                  </div>

                  <div className="phrase-list">
                    {phrases.map((phrase, index) => (
                      <div key={index} className="phrase-item">
                        <div className="phrase-text">{phrase}</div>
                        <button
                          className="phrase-remove"
                          onClick={() => handleRemovePhrase(selectedPolicy, phraseType, index)}
                        >
                          ✕
                        </button>
                      </div>
                    ))}

                    {phrases.length === 0 && (
                      <div className="no-phrases">No phrases configured</div>
                    )}
                  </div>

                  {editingPhrase === `${selectedPolicy}-${phraseType}` ? (
                    <div className="add-phrase-form">
                      <textarea
                        value={newPhraseText}
                        onChange={(e) => setNewPhraseText(e.target.value)}
                        placeholder="Enter new phrase..."
                        rows={3}
                      />
                      <div className="form-actions">
                        <button
                          className="btn btn-secondary"
                          onClick={() => {
                            setEditingPhrase(null);
                            setNewPhraseText('');
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          className="btn btn-primary"
                          onClick={() => handleAddPhrase(selectedPolicy, phraseType)}
                        >
                          Add Phrase
                        </button>
                      </div>
                      <div className="placeholder-help">
                        <strong>Available placeholders:</strong> {'{rate_range_text}'}, {'{duration}'}
                      </div>
                    </div>
                  ) : (
                    <button
                      className="add-phrase-btn"
                      onClick={() => setEditingPhrase(`${selectedPolicy}-${phraseType}`)}
                    >
                      + Add Phrase
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Overrides Tab */}
      {activeTab === 'overrides' && (
        <div className="overrides-tab">
          <div className="overrides-section">
            <h3>Goal Overrides</h3>
            <p>Value propositions based on the call goal</p>

            <div className="override-list">
              {Object.entries(presets.goal_overrides || {}).map(([goal, config]) => (
                <div key={goal} className="override-card">
                  <div className="override-header">
                    <h4>{goal.replace(/_/g, ' ')}</h4>
                    <span className="override-type">Goal</span>
                  </div>
                  <p className="override-desc">{config.description}</p>
                  <div className="override-phrases">
                    <strong>Value Props:</strong>
                    <ul>
                      {(config.value_prop || []).map((vp, i) => (
                        <li key={i}>{vp}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="overrides-section">
            <h3>Segment Overrides</h3>
            <p>Value propositions based on borrower segment</p>

            <div className="override-list">
              {Object.entries(presets.segment_overrides || {}).map(([segment, config]) => (
                <div key={segment} className="override-card">
                  <div className="override-header">
                    <h4>{segment.replace(/_/g, ' ')}</h4>
                    <span className="override-type segment">Segment</span>
                  </div>
                  <p className="override-desc">{config.description}</p>
                  <div className="override-phrases">
                    <strong>Value Props:</strong>
                    <ul>
                      {(config.value_prop || []).map((vp, i) => (
                        <li key={i}>{vp}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Disclaimers Tab */}
      {activeTab === 'disclaimers' && (
        <div className="disclaimers-tab">
          <div className="disclaimer-card">
            <h3>Default Disclaimer</h3>
            <p>Used at the end of rate discussions</p>
            <textarea
              value={presets.disclaimer_templates?.default || ''}
              onChange={(e) => handleUpdateDisclaimer('default', e.target.value)}
              rows={4}
            />
          </div>

          <div className="disclaimer-card">
            <h3>Short Disclaimer</h3>
            <p>Abbreviated version for quick mentions</p>
            <textarea
              value={presets.disclaimer_templates?.short || ''}
              onChange={(e) => handleUpdateDisclaimer('short', e.target.value)}
              rows={2}
            />
          </div>

          <div className="disclaimer-card">
            <h3>Detailed Disclaimer</h3>
            <p>Full legal disclaimer for formal discussions</p>
            <textarea
              value={presets.disclaimer_templates?.detailed || ''}
              onChange={(e) => handleUpdateDisclaimer('detailed', e.target.value)}
              rows={5}
            />
          </div>

          {presets.disclaimer_templates?.state_specific && (
            <div className="state-disclaimers">
              <h3>State-Specific Disclaimers</h3>
              {Object.entries(presets.disclaimer_templates.state_specific).map(([state, text]) => (
                <div key={state} className="state-disclaimer">
                  <label>{state}</label>
                  <textarea
                    value={text}
                    onChange={(e) => {
                      setPresets(prev => ({
                        ...prev,
                        disclaimer_templates: {
                          ...prev.disclaimer_templates,
                          state_specific: {
                            ...prev.disclaimer_templates.state_specific,
                            [state]: e.target.value
                          }
                        }
                      }));
                    }}
                    rows={2}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Test Tool Tab */}
      {activeTab === 'test' && (
        <div className="test-tab">
          <div className="test-card">
            <h3>Test Language Selection</h3>
            <p>Simulate how language will be selected for different scenarios</p>

            <div className="test-form">
              <div className="form-row">
                <div className="form-group">
                  <label>Eligible</label>
                  <select
                    value={testParams.eligible === null ? 'null' : testParams.eligible.toString()}
                    onChange={(e) => setTestParams({
                      ...testParams,
                      eligible: e.target.value === 'null' ? null : e.target.value === 'true'
                    })}
                  >
                    <option value="true">True (Eligible)</option>
                    <option value="false">False (Not Eligible)</option>
                    <option value="null">Unknown</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Quote Policy</label>
                  <select
                    value={testParams.quote_policy}
                    onChange={(e) => setTestParams({ ...testParams, quote_policy: e.target.value })}
                  >
                    <option value="range_only">Range Only</option>
                    <option value="no_quote">No Quote</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Goal</label>
                  <select
                    value={testParams.goal}
                    onChange={(e) => setTestParams({ ...testParams, goal: e.target.value })}
                  >
                    <option value="">None</option>
                    <option value="annual_mortgage_review">Annual Mortgage Review</option>
                    <option value="rate_term_refi_review">Rate/Term Refi Review</option>
                    <option value="cash_out_planning">Cash-Out Planning</option>
                    <option value="purchase_preapproval">Purchase Pre-Approval</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Segment</label>
                  <select
                    value={testParams.segment}
                    onChange={(e) => setTestParams({ ...testParams, segment: e.target.value })}
                  >
                    <option value="">None</option>
                    <option value="arm_safety_review">ARM Safety Review</option>
                    <option value="equity_strategy_review">Equity Strategy Review</option>
                    <option value="mortgage_tune_up">Mortgage Tune-Up</option>
                    <option value="rate_watch">Rate Watch</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Rate Range Text</label>
                <input
                  type="text"
                  value={testParams.rate_range_text}
                  onChange={(e) => setTestParams({ ...testParams, rate_range_text: e.target.value })}
                  placeholder="e.g., 6.25% - 6.75%"
                />
              </div>

              <button className="btn btn-primary" onClick={handleTestSelection}>
                Test Selection
              </button>
            </div>

            {testResult && !testResult.error && (
              <div className="test-result">
                <h4>Selected Language</h4>

                <div className="result-section">
                  <label>Policy Bucket</label>
                  <span className="policy-badge">{testResult.policy_bucket}</span>
                </div>

                {testResult.approved_language?.opener && (
                  <div className="result-section">
                    <label>Opener</label>
                    <div className="result-text">{testResult.approved_language.opener}</div>
                  </div>
                )}

                {testResult.approved_language?.range_phrase && (
                  <div className="result-section">
                    <label>Range Phrase</label>
                    <div className="result-text">{testResult.approved_language.range_phrase}</div>
                  </div>
                )}

                {testResult.approved_language?.value_prop && (
                  <div className="result-section">
                    <label>Value Proposition</label>
                    <div className="result-text">{testResult.approved_language.value_prop}</div>
                  </div>
                )}

                {testResult.approved_language?.close && (
                  <div className="result-section">
                    <label>Close / CTA</label>
                    <div className="result-text">{testResult.approved_language.close}</div>
                  </div>
                )}

                {testResult.disclaimer && (
                  <div className="result-section">
                    <label>Disclaimer</label>
                    <div className="result-text disclaimer">{testResult.disclaimer}</div>
                  </div>
                )}
              </div>
            )}

            {testResult?.error && (
              <div className="test-error">{testResult.error}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default QuoteLanguagePresets;
