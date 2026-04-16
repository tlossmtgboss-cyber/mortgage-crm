/**
 * State Recording Rules Admin Page
 *
 * Manages state-specific recording disclosure requirements.
 * - View all states with recording/consent rules
 * - Add/edit state disclosure scripts
 * - Track one-party vs all-party consent states
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './StateRecordingRules.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// All US states for reference
const US_STATES = [
  { code: 'AL', name: 'Alabama' }, { code: 'AK', name: 'Alaska' }, { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' }, { code: 'CA', name: 'California' }, { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' }, { code: 'DE', name: 'Delaware' }, { code: 'FL', name: 'Florida' },
  { code: 'GA', name: 'Georgia' }, { code: 'HI', name: 'Hawaii' }, { code: 'ID', name: 'Idaho' },
  { code: 'IL', name: 'Illinois' }, { code: 'IN', name: 'Indiana' }, { code: 'IA', name: 'Iowa' },
  { code: 'KS', name: 'Kansas' }, { code: 'KY', name: 'Kentucky' }, { code: 'LA', name: 'Louisiana' },
  { code: 'ME', name: 'Maine' }, { code: 'MD', name: 'Maryland' }, { code: 'MA', name: 'Massachusetts' },
  { code: 'MI', name: 'Michigan' }, { code: 'MN', name: 'Minnesota' }, { code: 'MS', name: 'Mississippi' },
  { code: 'MO', name: 'Missouri' }, { code: 'MT', name: 'Montana' }, { code: 'NE', name: 'Nebraska' },
  { code: 'NV', name: 'Nevada' }, { code: 'NH', name: 'New Hampshire' }, { code: 'NJ', name: 'New Jersey' },
  { code: 'NM', name: 'New Mexico' }, { code: 'NY', name: 'New York' }, { code: 'NC', name: 'North Carolina' },
  { code: 'ND', name: 'North Dakota' }, { code: 'OH', name: 'Ohio' }, { code: 'OK', name: 'Oklahoma' },
  { code: 'OR', name: 'Oregon' }, { code: 'PA', name: 'Pennsylvania' }, { code: 'RI', name: 'Rhode Island' },
  { code: 'SC', name: 'South Carolina' }, { code: 'SD', name: 'South Dakota' }, { code: 'TN', name: 'Tennessee' },
  { code: 'TX', name: 'Texas' }, { code: 'UT', name: 'Utah' }, { code: 'VT', name: 'Vermont' },
  { code: 'VA', name: 'Virginia' }, { code: 'WA', name: 'Washington' }, { code: 'WV', name: 'West Virginia' },
  { code: 'WI', name: 'Wisconsin' }, { code: 'WY', name: 'Wyoming' }, { code: 'DC', name: 'District of Columbia' }
];

const StateRecordingRules = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessSettings = isAdmin || hasAnyPermission(['settings.manage', 'admin.manage', 'system.admin']) || userRole === 'admin';
  const [loading, setLoading] = useState(true);
  const [rules, setRules] = useState([]);
  const [allPartyStates, setAllPartyStates] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  // Edit modal state
  const [showModal, setShowModal] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [formData, setFormData] = useState({
    state: '',
    recording_required: true,
    requires_verbal_ack: false,
    disclosure_script: '',
    consent_type: 'one-party',
    notes: ''
  });

  // Test lookup state
  const [testState, setTestState] = useState('');
  const [testResult, setTestResult] = useState(null);

  const getAuthHeaders = () => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const fetchRules = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [rulesRes, allPartyRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/state-recording-rules/`, { headers: getAuthHeaders() }),
        fetch(`${API_URL}/api/v1/state-recording-rules/all-party-states`, { headers: getAuthHeaders() })
      ]);

      if (rulesRes.ok) {
        const data = await rulesRes.json();
        setRules(data.rules || []);
      }

      if (allPartyRes.ok) {
        const data = await allPartyRes.json();
        setAllPartyStates(data.all_party_consent_states || []);
      }

    } catch (err) {
      console.error('Error fetching rules:', err);
      setError('Failed to load state recording rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRules();
  }, [fetchRules]);

  const handleTestLookup = async () => {
    if (!testState) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/state-recording-rules/by-state/${testState}`,
        { headers: getAuthHeaders() }
      );

      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      } else {
        setTestResult({ error: 'State not found' });
      }
    } catch (err) {
      setTestResult({ error: 'Failed to lookup state' });
    }
  };

  const handleOpenModal = (rule = null) => {
    if (rule) {
      setEditingRule(rule);
      setFormData({
        state: rule.state,
        recording_required: rule.recording_required,
        requires_verbal_ack: rule.requires_verbal_ack,
        disclosure_script: rule.disclosure_script,
        consent_type: rule.consent_type || 'one-party',
        notes: rule.notes || ''
      });
    } else {
      setEditingRule(null);
      setFormData({
        state: '',
        recording_required: true,
        requires_verbal_ack: false,
        disclosure_script: 'Just so you know, this call may be recorded for quality.',
        consent_type: 'one-party',
        notes: ''
      });
    }
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingRule(null);
  };

  const handleSaveRule = async () => {
    try {
      setError(null);

      const res = await fetch(`${API_URL}/api/v1/state-recording-rules/`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(formData)
      });

      if (res.ok) {
        setSuccess(`Rule for ${formData.state} saved successfully!`);
        setTimeout(() => setSuccess(null), 3000);
        handleCloseModal();
        fetchRules();
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to save rule');
      }
    } catch (err) {
      setError('Failed to save rule');
    }
  };

  const handleDeleteRule = async (stateCode) => {
    if (!window.confirm(`Are you sure you want to delete the rule for ${stateCode}?`)) {
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/state-recording-rules/${stateCode}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (res.ok) {
        setSuccess(`Rule for ${stateCode} deleted`);
        setTimeout(() => setSuccess(null), 3000);
        fetchRules();
      } else {
        setError('Failed to delete rule');
      }
    } catch (err) {
      setError('Failed to delete rule');
    }
  };

  const getStateName = (code) => {
    const state = US_STATES.find(s => s.code === code);
    return state ? state.name : code;
  };

  const getConsentBadge = (consentType, requiresAck) => {
    if (consentType === 'all-party' || requiresAck) {
      return <span className="badge badge-warning">All-Party Consent</span>;
    }
    return <span className="badge badge-success">One-Party Consent</span>;
  };

  if (loading) {
    return (
      <div className="state-recording-rules">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading State Recording Rules...</p>
        </div>
      </div>
    );
  }

  if (!canAccessSettings) {
    return (
      <div className="state-recording-rules">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access State Recording Rules.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="state-recording-rules">
      <div className="page-header">
        <div>
          <h1>State Recording Rules</h1>
          <p>Manage state-specific recording disclosure requirements and consent scripts</p>
        </div>
        <button className="btn btn-primary" onClick={() => handleOpenModal()}>
          + Add State Rule
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Tabs */}
      <div className="rules-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'all-rules' ? 'active' : ''}
          onClick={() => setActiveTab('all-rules')}
        >
          All Rules ({rules.length})
        </button>
        <button
          className={activeTab === 'all-party' ? 'active' : ''}
          onClick={() => setActiveTab('all-party')}
        >
          All-Party States ({allPartyStates.length})
        </button>
        <button
          className={activeTab === 'test' ? 'active' : ''}
          onClick={() => setActiveTab('test')}
        >
          Test Lookup
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="overview-tab">
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon">📋</div>
              <div className="stat-content">
                <div className="stat-value">{rules.length}</div>
                <div className="stat-label">Total Rules</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">⚠️</div>
              <div className="stat-content">
                <div className="stat-value">{allPartyStates.length}</div>
                <div className="stat-label">All-Party Consent States</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">✅</div>
              <div className="stat-content">
                <div className="stat-value">{rules.filter(r => r.consent_type === 'one-party').length}</div>
                <div className="stat-label">One-Party Consent States</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">🎙️</div>
              <div className="stat-content">
                <div className="stat-value">{rules.filter(r => r.requires_verbal_ack).length}</div>
                <div className="stat-label">Require Verbal Ack</div>
              </div>
            </div>
          </div>

          <div className="info-cards">
            <div className="info-card">
              <h3>One-Party Consent</h3>
              <p>In one-party consent states, only one party to the conversation needs to consent to the recording. Since your agent is a party, a simple disclosure is sufficient.</p>
              <div className="example-script">
                <strong>Example:</strong> "Just so you know, this call may be recorded for quality."
              </div>
            </div>
            <div className="info-card warning">
              <h3>All-Party Consent</h3>
              <p>In all-party consent states, <strong>all parties</strong> must consent to the recording. The agent must disclose recording and receive acknowledgment before proceeding.</p>
              <div className="example-script">
                <strong>Example:</strong> "This call is being recorded for quality and training purposes. Is that okay with you?"
              </div>
            </div>
          </div>
        </div>
      )}

      {/* All Rules Tab */}
      {activeTab === 'all-rules' && (
        <div className="rules-table-container">
          <table className="rules-table">
            <thead>
              <tr>
                <th>State</th>
                <th>Consent Type</th>
                <th>Verbal Ack</th>
                <th>Disclosure Script</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.state}>
                  <td>
                    <strong>{rule.state}</strong>
                    <span className="state-name">{getStateName(rule.state)}</span>
                  </td>
                  <td>{getConsentBadge(rule.consent_type, rule.requires_verbal_ack)}</td>
                  <td>
                    {rule.requires_verbal_ack ? (
                      <span className="ack-yes">Yes</span>
                    ) : (
                      <span className="ack-no">No</span>
                    )}
                  </td>
                  <td className="script-cell">
                    <div className="script-preview">{rule.disclosure_script}</div>
                  </td>
                  <td className="notes-cell">{rule.notes || '-'}</td>
                  <td>
                    <div className="action-buttons">
                      <button className="btn-icon" onClick={() => handleOpenModal(rule)} title="Edit">
                        ✏️
                      </button>
                      <button className="btn-icon btn-danger" onClick={() => handleDeleteRule(rule.state)} title="Delete">
                        🗑️
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr>
                  <td colSpan="6" className="empty-state">
                    No state rules configured yet. Click "Add State Rule" to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* All-Party States Tab */}
      {activeTab === 'all-party' && (
        <div className="all-party-tab">
          <div className="all-party-header">
            <h3>States Requiring All-Party Consent</h3>
            <p>These states require explicit consent from all parties before recording. Ensure your agent asks for acknowledgment.</p>
          </div>
          <div className="all-party-grid">
            {allPartyStates.map((state) => (
              <div key={state.state} className="all-party-card">
                <div className="state-code">{state.state}</div>
                <div className="state-name">{getStateName(state.state)}</div>
                <div className="state-script">{state.script}</div>
              </div>
            ))}
            {allPartyStates.length === 0 && (
              <div className="empty-state">No all-party consent states configured.</div>
            )}
          </div>
        </div>
      )}

      {/* Test Lookup Tab */}
      {activeTab === 'test' && (
        <div className="test-tab">
          <div className="test-card">
            <h3>Test State Lookup</h3>
            <p>Enter a state code to see what disclosure script and consent requirements apply.</p>
            <div className="test-input-group">
              <select
                value={testState}
                onChange={(e) => setTestState(e.target.value)}
                className="state-select"
              >
                <option value="">Select a state...</option>
                {US_STATES.map((state) => (
                  <option key={state.code} value={state.code}>
                    {state.code} - {state.name}
                  </option>
                ))}
              </select>
              <button className="btn btn-primary" onClick={handleTestLookup}>
                Lookup
              </button>
            </div>

            {testResult && !testResult.error && (
              <div className="test-result">
                <h4>Result for {testResult.state}</h4>
                <div className="result-grid">
                  <div className="result-item">
                    <label>Consent Type:</label>
                    <span>{getConsentBadge(testResult.consent_type, testResult.requires_verbal_ack)}</span>
                  </div>
                  <div className="result-item">
                    <label>Recording Required:</label>
                    <span>{testResult.recording_required ? 'Yes' : 'No'}</span>
                  </div>
                  <div className="result-item">
                    <label>Verbal Acknowledgment:</label>
                    <span>{testResult.requires_verbal_ack ? 'Required' : 'Not Required'}</span>
                  </div>
                </div>
                <div className="result-script">
                  <label>Disclosure Script:</label>
                  <div className="script-box">{testResult.script}</div>
                </div>
              </div>
            )}

            {testResult?.error && (
              <div className="test-error">{testResult.error}</div>
            )}
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingRule ? 'Edit State Rule' : 'Add State Rule'}</h2>
              <button className="modal-close" onClick={handleCloseModal}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>State</label>
                <select
                  value={formData.state}
                  onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                  disabled={!!editingRule}
                >
                  <option value="">Select a state...</option>
                  {US_STATES.map((state) => (
                    <option key={state.code} value={state.code}>
                      {state.code} - {state.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Consent Type</label>
                <select
                  value={formData.consent_type}
                  onChange={(e) => setFormData({ ...formData, consent_type: e.target.value })}
                >
                  <option value="one-party">One-Party Consent</option>
                  <option value="all-party">All-Party Consent</option>
                </select>
              </div>

              <div className="form-row">
                <div className="form-group checkbox-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={formData.recording_required}
                      onChange={(e) => setFormData({ ...formData, recording_required: e.target.checked })}
                    />
                    Recording Required
                  </label>
                </div>
                <div className="form-group checkbox-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={formData.requires_verbal_ack}
                      onChange={(e) => setFormData({ ...formData, requires_verbal_ack: e.target.checked })}
                    />
                    Requires Verbal Acknowledgment
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label>Disclosure Script</label>
                <textarea
                  value={formData.disclosure_script}
                  onChange={(e) => setFormData({ ...formData, disclosure_script: e.target.value })}
                  rows={4}
                  placeholder="Enter the disclosure script the agent should use..."
                />
              </div>

              <div className="form-group">
                <label>Notes (optional)</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  rows={2}
                  placeholder="Any additional notes about this state's requirements..."
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={handleCloseModal}>Cancel</button>
              <button className="btn btn-primary" onClick={handleSaveRule}>Save Rule</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StateRecordingRules;
