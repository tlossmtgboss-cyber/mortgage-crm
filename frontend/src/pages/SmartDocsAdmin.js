import React, { useState, useEffect, useCallback } from 'react';
import docReviewApi from '../services/docReviewApi';
import docSecurityApi from '../services/docSecurityApi';
import { toast } from '../utils/toast';
import './SmartDocsAdmin.css';

const TABS = [
  { key: 'auto-review', label: 'Auto-Review Settings' },
  { key: 'retention', label: 'Retention Policies' },
];

// ---------------------------------------------------------------------------
// Auto-Review Settings Tab
// ---------------------------------------------------------------------------
function AutoReviewTab({ autoReview, setAutoReview, onSave }) {
  if (!autoReview) {
    return <div className="sd-admin__empty">No auto-review settings available.</div>;
  }

  function handleChange(e) {
    const { name, type, value, checked } = e.target;
    setAutoReview(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : Number(value),
    }));
  }

  return (
    <div className="sd-admin__card">
      <h3 className="sd-admin__card-title">Auto-Review Configuration</h3>
      <div className="sd-admin__form">
        <div className="sd-admin__field">
          <label htmlFor="ar-enabled" className="sd-admin__label">Enable Auto-Review</label>
          <input
            id="ar-enabled"
            name="enabled"
            type="checkbox"
            className="sd-admin__checkbox"
            checked={!!autoReview.enabled}
            onChange={handleChange}
          />
        </div>
        <div className="sd-admin__field">
          <label htmlFor="ar-confidence" className="sd-admin__label">Confidence Threshold</label>
          <input
            id="ar-confidence"
            name="confidence_threshold"
            type="number"
            className="sd-admin__number-input"
            min={50}
            max={100}
            value={autoReview.confidence_threshold ?? 80}
            onChange={handleChange}
          />
        </div>
        <div className="sd-admin__field">
          <label htmlFor="ar-quality" className="sd-admin__label">Quality Threshold</label>
          <input
            id="ar-quality"
            name="quality_threshold"
            type="number"
            className="sd-admin__number-input"
            min={50}
            max={100}
            value={autoReview.quality_threshold ?? 75}
            onChange={handleChange}
          />
        </div>
        <div className="sd-admin__field">
          <label htmlFor="ar-max-approvals" className="sd-admin__label">Max Auto-Approvals per Day</label>
          <input
            id="ar-max-approvals"
            name="max_auto_approvals_per_day"
            type="number"
            className="sd-admin__number-input"
            min={0}
            max={1000}
            value={autoReview.max_auto_approvals_per_day ?? 50}
            onChange={handleChange}
          />
        </div>
      </div>
      <div className="sd-admin__form-actions">
        <button className="sd-admin__btn sd-admin__btn--primary" onClick={onSave}>
          Save Settings
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retention Policies Tab
// ---------------------------------------------------------------------------
function RetentionPoliciesTab({ policies, onAdd }) {
  return (
    <div>
      <div className="sd-admin__section-header">
        <h3 className="sd-admin__section-title">Retention Policies</h3>
        <button className="sd-admin__btn sd-admin__btn--primary" onClick={onAdd}>
          Add Policy
        </button>
      </div>
      {(!policies || policies.length === 0) ? (
        <div className="sd-admin__empty">No retention policies configured.</div>
      ) : (
        <div className="sd-admin__table-container">
          <table className="sd-admin__table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Document Type</th>
                <th>Retention (days)</th>
                <th>Action</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((policy, idx) => {
                const isActive =
                  policy.is_active !== false && policy.status !== 'inactive';
                return (
                  <tr key={policy.id || idx}>
                    <td>{policy.policy_name || policy.name || '—'}</td>
                    <td>{policy.doc_type || policy.document_type || '—'}</td>
                    <td>{policy.retention_days != null ? policy.retention_days : '—'}</td>
                    <td>{policy.action || policy.retention_action || '—'}</td>
                    <td>
                      <span
                        className="sd-admin__badge"
                        style={
                          isActive
                            ? { background: '#dcfce7', color: '#15803d' }
                            : { background: '#f1f5f9', color: '#64748b' }
                        }
                      >
                        {isActive ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------
export default function SmartDocsAdmin() {
  const [activeTab, setActiveTab] = useState('auto-review');
  const [autoReview, setAutoReview] = useState(null);
  const [retentionPolicies, setRetentionPolicies] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [reviewRes, retentionRes] = await Promise.allSettled([
        docReviewApi.getAutoReviewSettings(),
        docSecurityApi.getRetentionPolicies(),
      ]);

      if (reviewRes.status === 'fulfilled') {
        setAutoReview(reviewRes.value);
      } else {
        toast.error('Failed to load auto-review settings');
      }

      if (retentionRes.status === 'fulfilled') {
        const data = retentionRes.value;
        setRetentionPolicies(Array.isArray(data) ? data : data.policies || []);
      } else {
        toast.error('Failed to load retention policies');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleSaveAutoReview() {
    if (!autoReview) return;
    try {
      await docReviewApi.updateAutoReviewSettings(autoReview);
      toast.success('Auto-review settings saved');
    } catch (err) {
      toast.error(err.message || 'Failed to save settings');
    }
  }

  async function handleAddPolicy() {
    const name = window.prompt('Enter policy name:');
    if (!name || !name.trim()) return;
    try {
      await docSecurityApi.createRetentionPolicy({
        policy_name: name.trim(),
        retention_days: 2555,
        action: 'archive',
        is_active: true,
      });
      toast.success('Retention policy created');
      // Reload table
      const data = await docSecurityApi.getRetentionPolicies();
      setRetentionPolicies(Array.isArray(data) ? data : data.policies || []);
    } catch (err) {
      toast.error(err.message || 'Failed to create policy');
    }
  }

  return (
    <div className="sd-admin">
      <div className="sd-admin__header">
        <h1 className="sd-admin__title">Admin Configuration</h1>
        <p className="sd-admin__subtitle">
          Manage auto-review thresholds and document retention policies
        </p>
      </div>

      <div className="sd-admin__tabs">
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`sd-admin__tab${activeTab === tab.key ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="sd-admin__content">
        {loading ? (
          <div className="sd-admin__loading">Loading configuration...</div>
        ) : (
          <>
            {activeTab === 'auto-review' && (
              <AutoReviewTab
                autoReview={autoReview}
                setAutoReview={setAutoReview}
                onSave={handleSaveAutoReview}
              />
            )}
            {activeTab === 'retention' && (
              <RetentionPoliciesTab
                policies={retentionPolicies}
                onAdd={handleAddPolicy}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
