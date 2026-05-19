/**
 * FeatureManagement Component
 *
 * Admin interface for managing platform feature visibility.
 * Controls which features are available to users during account setup.
 */

import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import './FeatureManagement.css';

// Category metadata for grouping
const CATEGORY_META = {
  ai_tools: { label: 'AI Tools', icon: '🤖', color: '#B8924A' },
  communication: { label: 'Communication', icon: '💬', color: '#0ea5e9' },
  analytics: { label: 'Analytics', icon: '📊', color: '#2D7A52' },
  operations: { label: 'Operations', icon: '⚙️', color: '#f59e0b' },
  administration: { label: 'Administration', icon: '🛡️', color: '#B8924A' },
  integrations: { label: 'Integrations', icon: '🔌', color: '#ec4899' }
};

// Development status badges
const STATUS_BADGES = {
  development: { label: 'Development', color: '#ef4444', description: 'Hidden from all users' },
  beta: { label: 'BETA', color: '#f59e0b', description: 'Visible with beta badge' },
  stable: { label: 'Stable', color: '#2D7A52', description: 'Production ready' }
};

function FeatureManagement({ companyId = 1 }) {
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [showDevelopment, setShowDevelopment] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);

  const fetchFeatures = useCallback(async () => {
    try {
      setLoading(true);

      const response = await api.get(`/api/v1/features/company/${companyId}/access`);
      setFeatures(response.data.features || []);
      setSetupComplete(true);
      setError(null);
    } catch (err) {
      console.error('Error fetching features:', err);
      if (err.status === 404 || err.response?.status === 404) {
        // Tables might not exist yet - try to set them up
        setSetupComplete(false);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    fetchFeatures();
  }, [fetchFeatures]);

  const runSetup = async () => {
    try {
      setSaving(true);
      const response = await api.post('/api/v1/features/migrate/full-setup');
      setSuccessMessage(`Setup complete! ${response.data.features_seeded?.length || 0} features created.`);
      setTimeout(() => setSuccessMessage(null), 3000);
      fetchFeatures();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleFeatureAccess = async (featureKey, currentEnabled) => {
    try {
      setSaving(true);
      await api.put(`/api/v1/features/company/${companyId}/access/${featureKey}`, {
        is_enabled: !currentEnabled
      });

      // Update local state
      setFeatures(prev => prev.map(f =>
        f.feature_key === featureKey
          ? { ...f, access: { ...f.access, is_enabled: !currentEnabled } }
          : f
      ));
      setSuccessMessage(`Feature ${!currentEnabled ? 'enabled' : 'disabled'} successfully`);
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const bulkEnableAll = async (category = null) => {
    try {
      setSaving(true);

      const featuresToEnable = features
        .filter(f => !f.access?.is_enabled)
        .filter(f => f.development_status !== 'development')
        .filter(f => category === null || f.category === category)
        .map(f => f.feature_key);

      if (featuresToEnable.length === 0) {
        setSuccessMessage('All features are already enabled');
        setTimeout(() => setSuccessMessage(null), 2000);
        return;
      }

      await api.post(`/api/v1/features/company/${companyId}/access/bulk`, {
        feature_keys: featuresToEnable,
        is_enabled: true
      });

      fetchFeatures();
      setSuccessMessage(`${featuresToEnable.length} features enabled`);
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const bulkDisableAll = async (category = null) => {
    try {
      setSaving(true);

      const featuresToDisable = features
        .filter(f => f.access?.is_enabled)
        .filter(f => category === null || f.category === category)
        .map(f => f.feature_key);

      if (featuresToDisable.length === 0) {
        setSuccessMessage('All features are already disabled');
        setTimeout(() => setSuccessMessage(null), 2000);
        return;
      }

      await api.post(`/api/v1/features/company/${companyId}/access/bulk`, {
        feature_keys: featuresToDisable,
        is_enabled: false
      });

      fetchFeatures();
      setSuccessMessage(`${featuresToDisable.length} features disabled`);
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Group features by category
  const groupedFeatures = features.reduce((acc, feature) => {
    const cat = feature.category || 'operations';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(feature);
    return acc;
  }, {});

  // Filter by active category
  const displayFeatures = activeCategory === 'all'
    ? features
    : features.filter(f => f.category === activeCategory);

  // Filter out development features unless showDevelopment is true
  const filteredFeatures = showDevelopment
    ? displayFeatures
    : displayFeatures.filter(f => f.development_status !== 'development');

  // Stats
  const enabledCount = features.filter(f => f.access?.is_enabled).length;
  const totalAvailable = features.filter(f => f.development_status !== 'development').length;

  if (loading) {
    return (
      <div className="feature-management loading">
        <div className="spinner"></div>
        <p>Loading feature settings...</p>
      </div>
    );
  }

  if (!setupComplete) {
    return (
      <div className="feature-management setup-required">
        <div className="setup-card">
          <div className="setup-icon">🚀</div>
          <h2>Feature System Setup Required</h2>
          <p>The feature management system needs to be initialized. This will create the necessary database tables and seed the default features.</p>
          <button
            className="btn-setup"
            onClick={runSetup}
            disabled={saving}
          >
            {saving ? 'Setting up...' : 'Initialize Feature System'}
          </button>
          {error && <p className="error-text">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="feature-management">
      {/* Header */}
      <div className="fm-header">
        <div className="fm-header-content">
          <h1>Feature Management</h1>
          <p>Control which features are visible to users during account setup</p>
        </div>
        <div className="fm-header-stats">
          <div className="stat-box">
            <span className="stat-value">{enabledCount}</span>
            <span className="stat-label">Enabled</span>
          </div>
          <div className="stat-box">
            <span className="stat-value">{totalAvailable}</span>
            <span className="stat-label">Available</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="fm-message success">{successMessage}</div>
      )}
      {error && (
        <div className="fm-message error">{error}</div>
      )}

      {/* Controls */}
      <div className="fm-controls">
        <div className="fm-filters">
          <button
            className={`filter-btn ${activeCategory === 'all' ? 'active' : ''}`}
            onClick={() => setActiveCategory('all')}
          >
            All Categories
          </button>
          {Object.entries(CATEGORY_META).map(([key, meta]) => (
            <button
              key={key}
              className={`filter-btn ${activeCategory === key ? 'active' : ''}`}
              onClick={() => setActiveCategory(key)}
              style={{ '--cat-color': meta.color }}
            >
              <span className="filter-icon">{meta.icon}</span>
              {meta.label}
            </button>
          ))}
        </div>

        <div className="fm-actions">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showDevelopment}
              onChange={(e) => setShowDevelopment(e.target.checked)}
            />
            Show Development Features
          </label>
          <button
            className="btn-secondary"
            onClick={() => bulkEnableAll(activeCategory === 'all' ? null : activeCategory)}
            disabled={saving}
          >
            Enable All
          </button>
          <button
            className="btn-secondary danger"
            onClick={() => bulkDisableAll(activeCategory === 'all' ? null : activeCategory)}
            disabled={saving}
          >
            Disable All
          </button>
        </div>
      </div>

      {/* Features Grid */}
      <div className="fm-features-grid">
        {filteredFeatures.map(feature => (
          <div
            key={feature.feature_key}
            className={`feature-card ${feature.access?.is_enabled ? 'enabled' : 'disabled'} ${feature.development_status === 'development' ? 'development' : ''}`}
          >
            <div className="feature-card-header">
              <div className="feature-icon-wrap" style={{ backgroundColor: CATEGORY_META[feature.category]?.color || '#6b7280' }}>
                <span>{CATEGORY_META[feature.category]?.icon || '📦'}</span>
              </div>
              <div className="feature-status-badges">
                {feature.is_premium && (
                  <span className="badge premium">Premium</span>
                )}
                <span
                  className="badge status"
                  style={{ backgroundColor: STATUS_BADGES[feature.development_status]?.color }}
                  title={STATUS_BADGES[feature.development_status]?.description}
                >
                  {STATUS_BADGES[feature.development_status]?.label}
                </span>
              </div>
            </div>

            <div className="feature-card-body">
              <h3>{feature.feature_name}</h3>
              <p>{feature.description}</p>
              {feature.is_premium && feature.base_price > 0 && (
                <span className="feature-price">${feature.base_price}/mo</span>
              )}
            </div>

            <div className="feature-card-footer">
              <span className="category-tag" style={{ color: CATEGORY_META[feature.category]?.color }}>
                {CATEGORY_META[feature.category]?.label}
              </span>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={feature.access?.is_enabled || false}
                  onChange={() => toggleFeatureAccess(feature.feature_key, feature.access?.is_enabled)}
                  disabled={saving || feature.development_status === 'development'}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
          </div>
        ))}
      </div>

      {filteredFeatures.length === 0 && (
        <div className="fm-empty">
          <p>No features found in this category.</p>
        </div>
      )}
    </div>
  );
}

export default FeatureManagement;
