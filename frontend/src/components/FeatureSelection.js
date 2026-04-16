/**
 * FeatureSelection Component
 *
 * User-facing component for selecting which features to enable during account setup.
 * Only shows features that have been made available by the admin.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './FeatureSelection.css';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Category display metadata
const CATEGORY_INFO = {
  ai_tools: { label: 'AI Tools', icon: '🤖', description: 'Intelligent automation and AI-powered assistance' },
  communication: { label: 'Communication', icon: '💬', description: 'Email, calling, and messaging tools' },
  analytics: { label: 'Analytics', icon: '📊', description: 'Data insights and reporting' },
  operations: { label: 'Operations', icon: '⚙️', description: 'Day-to-day workflow tools' },
  administration: { label: 'Administration', icon: '🛡️', description: 'User and system management' },
  integrations: { label: 'Integrations', icon: '🔌', description: 'Connect with external services' }
};

function FeatureSelection({ companyId = 1, selectedFeatures = [], onFeaturesChange, showPricing = true }) {
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedCategory, setExpandedCategory] = useState(null);

  // Fetch available features (only non-development ones that user can see)
  const fetchFeatures = useCallback(async () => {
    try {
      setLoading(true);
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      const response = await fetch(
        `${API_BASE}/api/v1/features/available`,
        { headers }
      );

      if (response.ok) {
        const data = await response.json();
        setFeatures(data);
      } else {
        throw new Error('Failed to load features');
      }
      setError(null);
    } catch (err) {
      console.error('Error fetching features:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFeatures();
  }, [fetchFeatures]);

  const toggleFeature = (featureKey) => {
    const newSelected = selectedFeatures.includes(featureKey)
      ? selectedFeatures.filter(k => k !== featureKey)
      : [...selectedFeatures, featureKey];

    if (onFeaturesChange) {
      onFeaturesChange(newSelected);
    }
  };

  const selectAllInCategory = (category) => {
    const categoryFeatureKeys = features
      .filter(f => f.category === category)
      .map(f => f.feature_key);

    const allSelected = categoryFeatureKeys.every(k => selectedFeatures.includes(k));

    let newSelected;
    if (allSelected) {
      // Deselect all in category
      newSelected = selectedFeatures.filter(k => !categoryFeatureKeys.includes(k));
    } else {
      // Select all in category
      newSelected = [...new Set([...selectedFeatures, ...categoryFeatureKeys])];
    }

    if (onFeaturesChange) {
      onFeaturesChange(newSelected);
    }
  };

  // Group features by category
  const groupedFeatures = features.reduce((acc, feature) => {
    const cat = feature.category || 'operations';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(feature);
    return acc;
  }, {});

  // Calculate total price
  const totalPrice = features
    .filter(f => selectedFeatures.includes(f.feature_key) && f.is_premium)
    .reduce((sum, f) => sum + (f.base_price || 0), 0);

  if (loading) {
    return (
      <div className="feature-selection loading">
        <div className="fs-spinner"></div>
        <p>Loading available features...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="feature-selection error">
        <p>Unable to load features: {error}</p>
        <button onClick={fetchFeatures}>Retry</button>
      </div>
    );
  }

  if (features.length === 0) {
    return (
      <div className="feature-selection empty">
        <div className="empty-icon">📦</div>
        <h3>No Features Available</h3>
        <p>Feature configuration has not been set up yet. Please contact your administrator.</p>
      </div>
    );
  }

  return (
    <div className="feature-selection">
      <div className="fs-header">
        <h2>Select Your Features</h2>
        <p>Choose the tools and features you want to enable for your account</p>
      </div>

      {/* Quick Stats */}
      <div className="fs-stats">
        <div className="fs-stat">
          <span className="fs-stat-value">{selectedFeatures.length}</span>
          <span className="fs-stat-label">Selected</span>
        </div>
        <div className="fs-stat">
          <span className="fs-stat-value">{features.length}</span>
          <span className="fs-stat-label">Available</span>
        </div>
        {showPricing && (
          <div className="fs-stat highlight">
            <span className="fs-stat-value">${totalPrice.toFixed(0)}</span>
            <span className="fs-stat-label">Monthly</span>
          </div>
        )}
      </div>

      {/* Categories */}
      <div className="fs-categories">
        {Object.entries(groupedFeatures).map(([category, categoryFeatures]) => {
          const catInfo = CATEGORY_INFO[category] || { label: category, icon: '📦', description: '' };
          const selectedInCategory = categoryFeatures.filter(f => selectedFeatures.includes(f.feature_key)).length;
          const isExpanded = expandedCategory === category || expandedCategory === null;

          return (
            <div key={category} className={`fs-category ${isExpanded ? 'expanded' : ''}`}>
              <div
                className="fs-category-header"
                onClick={() => setExpandedCategory(expandedCategory === category ? null : category)}
              >
                <div className="fs-category-info">
                  <span className="fs-category-icon">{catInfo.icon}</span>
                  <div>
                    <h3>{catInfo.label}</h3>
                    <p>{catInfo.description}</p>
                  </div>
                </div>
                <div className="fs-category-actions">
                  <span className="fs-category-count">
                    {selectedInCategory}/{categoryFeatures.length}
                  </span>
                  <button
                    className="fs-select-all-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      selectAllInCategory(category);
                    }}
                  >
                    {selectedInCategory === categoryFeatures.length ? 'Deselect All' : 'Select All'}
                  </button>
                  <span className="fs-expand-icon">{isExpanded ? '−' : '+'}</span>
                </div>
              </div>

              {isExpanded && (
                <div className="fs-category-features">
                  {categoryFeatures.map(feature => (
                    <div
                      key={feature.feature_key}
                      className={`fs-feature ${selectedFeatures.includes(feature.feature_key) ? 'selected' : ''}`}
                      onClick={() => toggleFeature(feature.feature_key)}
                    >
                      <div className="fs-feature-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedFeatures.includes(feature.feature_key)}
                          onChange={() => toggleFeature(feature.feature_key)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="fs-feature-content">
                        <div className="fs-feature-header">
                          <h4>{feature.feature_name}</h4>
                          <div className="fs-feature-badges">
                            {feature.development_status === 'beta' && (
                              <span className="fs-badge beta">BETA</span>
                            )}
                            {feature.is_premium && (
                              <span className="fs-badge premium">Premium</span>
                            )}
                          </div>
                        </div>
                        <p>{feature.description}</p>
                        {showPricing && feature.is_premium && feature.base_price > 0 && (
                          <span className="fs-feature-price">${feature.base_price}/mo</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Summary Footer */}
      <div className="fs-footer">
        <div className="fs-summary">
          <span className="fs-summary-label">Selected Features:</span>
          <div className="fs-selected-tags">
            {selectedFeatures.length === 0 ? (
              <span className="fs-no-selection">No features selected</span>
            ) : (
              selectedFeatures.slice(0, 5).map(key => {
                const feature = features.find(f => f.feature_key === key);
                return feature ? (
                  <span key={key} className="fs-selected-tag">
                    {feature.feature_name}
                    <button onClick={() => toggleFeature(key)}>×</button>
                  </span>
                ) : null;
              })
            )}
            {selectedFeatures.length > 5 && (
              <span className="fs-more-selected">+{selectedFeatures.length - 5} more</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default FeatureSelection;
