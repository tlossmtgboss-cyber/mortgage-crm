/**
 * MicrositeThemeSelector - Choose Layout Component
 *
 * Allows users to browse and select microsite themes from the marketplace.
 * Displays theme previews, features, and configuration options.
 */

import React, { useState, useEffect, useMemo } from 'react';
import './MicrositeThemeSelector.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

// Theme categories for filtering
const CATEGORIES = [
  { value: 'all', label: 'All Themes' },
  { value: 'professional', label: 'Professional' },
  { value: 'modern', label: 'Modern' },
  { value: 'bold', label: 'Bold' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'elegant', label: 'Elegant' },
];

// Feature icons mapping
const FEATURE_ICONS = {
  hero_image: '🖼️',
  hero_gradient: '🌈',
  contact_form: '📝',
  rate_calculator: '🧮',
  testimonials: '💬',
  about_section: '👤',
  credentials: '🏆',
};

const MicrositeThemeSelector = ({ onThemeSelect, currentThemeId }) => {
  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedTheme, setSelectedTheme] = useState(null);
  const [previewTheme, setPreviewTheme] = useState(null);
  const [microsite, setMicrosite] = useState(null);
  const [saving, setSaving] = useState(false);
  const [userSlug, setUserSlug] = useState(null);

  // Get auth headers
  const getAuthHeaders = () => ({
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Content-Type': 'application/json'
  });

  // Fetch available themes
  useEffect(() => {
    fetchThemes();
    fetchMicrosite();
    fetchUserSlug();
  }, []);

  const fetchThemes = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/public/themes`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setThemes(data.themes || []);
      } else {
        throw new Error('Failed to fetch themes');
      }
    } catch (err) {
      console.error('Error fetching themes:', err);
      setError('Failed to load themes');
    } finally {
      setLoading(false);
    }
  };

  const fetchMicrosite = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setMicrosite(data);
        if (data.themeId) {
          setSelectedTheme(data.themeId);
        }
      }
    } catch (err) {
      console.error('Error fetching microsite:', err);
    }
  };

  const fetchUserSlug = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/preview-url`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setUserSlug(data.slug);
      }
    } catch (err) {
      console.error('Error fetching user slug:', err);
    }
  };

  // Filter themes by category
  const filteredThemes = useMemo(() => {
    if (selectedCategory === 'all') {
      return themes;
    }
    return themes.filter(theme => theme.category === selectedCategory);
  }, [themes, selectedCategory]);

  // Save selected theme
  const handleSaveTheme = async (themeId) => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ theme_id: themeId })
      });

      if (response.ok) {
        const data = await response.json();
        setMicrosite(data);
        setSelectedTheme(themeId);
        if (onThemeSelect) {
          onThemeSelect(themeId);
        }
      } else {
        throw new Error('Failed to save theme');
      }
    } catch (err) {
      console.error('Error saving theme:', err);
      setError('Failed to save theme selection');
    } finally {
      setSaving(false);
    }
  };

  // Publish microsite
  const handlePublish = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite/publish`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        await fetchMicrosite();
      } else {
        const err = await response.json();
        setError(err.detail || 'Failed to publish');
      }
    } catch (err) {
      console.error('Error publishing:', err);
      setError('Failed to publish microsite');
    } finally {
      setSaving(false);
    }
  };

  // Preview theme
  const handlePreview = (theme) => {
    setPreviewTheme(theme);
  };

  // Close preview
  const closePreview = () => {
    setPreviewTheme(null);
  };

  if (loading) {
    return (
      <div className="theme-selector-loading">
        <div className="loading-spinner"></div>
        <p>Loading themes...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="theme-selector-error">
        <p>{error}</p>
        <button onClick={fetchThemes}>Retry</button>
      </div>
    );
  }

  return (
    <div className="theme-selector">
      {/* Header */}
      <div className="theme-selector-header">
        <div className="header-content">
          <h2>Choose Your Microsite Theme</h2>
          <p>Select a professional theme for your loan officer microsite</p>
        </div>
        <div className="header-actions">
          {userSlug && (
            <a
              href={`/lo/${userSlug}`}
              target="_blank"
              rel="noopener noreferrer"
              className="preview-link"
            >
              Preview Your Microsite
            </a>
          )}
          {microsite && !microsite.isPublished && selectedTheme && (
            <button
              className="publish-btn"
              onClick={handlePublish}
              disabled={saving}
            >
              {saving ? 'Publishing...' : 'Publish Microsite'}
            </button>
          )}
          {microsite && microsite.isPublished && (
            <span className="published-badge">Published</span>
          )}
        </div>
      </div>

      {/* Category Filter */}
      <div className="category-filter">
        {CATEGORIES.map(cat => (
          <button
            key={cat.value}
            className={`category-btn ${selectedCategory === cat.value ? 'active' : ''}`}
            onClick={() => setSelectedCategory(cat.value)}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Theme Grid */}
      <div className="theme-grid">
        {filteredThemes.map(theme => (
          <div
            key={theme.id}
            className={`theme-card ${selectedTheme === theme.id ? 'selected' : ''}`}
            onClick={() => handlePreview(theme)}
          >
            {/* Theme Thumbnail */}
            <div className="theme-thumbnail">
              {theme.thumbnailUrl ? (
                <img src={theme.thumbnailUrl} alt={theme.name} />
              ) : (
                <div className="placeholder-thumbnail">
                  <span className="theme-icon">
                    {theme.category === 'bold' ? '🔥' :
                     theme.category === 'professional' ? '💼' :
                     theme.category === 'modern' ? '✨' :
                     theme.category === 'minimal' ? '⚡' : '🎨'}
                  </span>
                </div>
              )}
              {selectedTheme === theme.id && (
                <div className="selected-overlay">
                  <span className="checkmark">✓</span>
                  <span>Current Theme</span>
                </div>
              )}
              {theme.isFeatured && (
                <span className="featured-badge">Featured</span>
              )}
            </div>

            {/* Theme Info */}
            <div className="theme-info">
              <h3>{theme.name}</h3>
              <p className="theme-description">{theme.description}</p>

              {/* Features */}
              <div className="theme-features">
                {(theme.features || []).slice(0, 4).map(feature => (
                  <span key={feature} className="feature-tag">
                    {FEATURE_ICONS[feature] || '📦'} {feature.replace(/_/g, ' ')}
                  </span>
                ))}
                {(theme.features || []).length > 4 && (
                  <span className="feature-tag more">+{theme.features.length - 4} more</span>
                )}
              </div>

              {/* Actions */}
              <div className="theme-actions">
                <button
                  className="preview-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handlePreview(theme);
                  }}
                >
                  Preview
                </button>
                <button
                  className={`select-btn ${selectedTheme === theme.id ? 'selected' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSaveTheme(theme.id);
                  }}
                  disabled={saving || selectedTheme === theme.id}
                >
                  {selectedTheme === theme.id ? 'Selected' : 'Select Theme'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* No themes found */}
      {filteredThemes.length === 0 && (
        <div className="no-themes">
          <p>No themes found in this category</p>
        </div>
      )}

      {/* Preview Modal */}
      {previewTheme && (
        <div className="theme-preview-modal" onClick={closePreview}>
          <div className="preview-content" onClick={(e) => e.stopPropagation()}>
            <button className="close-preview" onClick={closePreview}>×</button>

            <div className="preview-header">
              <h2>{previewTheme.name}</h2>
              <span className={`category-badge ${previewTheme.category}`}>
                {previewTheme.category}
              </span>
            </div>

            <div className="preview-body">
              {/* Preview Image */}
              <div className="preview-image-container">
                {previewTheme.previewUrl ? (
                  <img src={previewTheme.previewUrl} alt={previewTheme.name} />
                ) : previewTheme.thumbnailUrl ? (
                  <img src={previewTheme.thumbnailUrl} alt={previewTheme.name} />
                ) : (
                  <div className="preview-placeholder">
                    <span className="theme-icon large">
                      {previewTheme.category === 'bold' ? '🔥' :
                       previewTheme.category === 'professional' ? '💼' :
                       previewTheme.category === 'modern' ? '✨' :
                       previewTheme.category === 'minimal' ? '⚡' : '🎨'}
                    </span>
                    <p>Preview not available</p>
                  </div>
                )}
              </div>

              {/* Theme Details */}
              <div className="preview-details">
                <p className="description">{previewTheme.description}</p>

                <div className="detail-section">
                  <h4>Features</h4>
                  <div className="features-list">
                    {(previewTheme.features || []).map(feature => (
                      <div key={feature} className="feature-item">
                        <span className="icon">{FEATURE_ICONS[feature] || '📦'}</span>
                        <span className="label">{feature.replace(/_/g, ' ')}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {previewTheme.supportsCustomColors && (
                  <div className="detail-section">
                    <h4>Customization</h4>
                    <p>This theme supports custom colors to match your brand.</p>
                  </div>
                )}

                {Object.keys(previewTheme.layoutOptions || {}).length > 0 && (
                  <div className="detail-section">
                    <h4>Layout Options</h4>
                    <div className="layout-options">
                      {Object.entries(previewTheme.layoutOptions).map(([key, values]) => (
                        <div key={key} className="layout-option">
                          <span className="option-label">{key.replace(/([A-Z])/g, ' $1').trim()}:</span>
                          <span className="option-values">{values.join(', ')}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="preview-footer">
              <button className="cancel-btn" onClick={closePreview}>
                Cancel
              </button>
              <button
                className={`select-btn ${selectedTheme === previewTheme.id ? 'selected' : ''}`}
                onClick={() => {
                  handleSaveTheme(previewTheme.id);
                  closePreview();
                }}
                disabled={saving || selectedTheme === previewTheme.id}
              >
                {selectedTheme === previewTheme.id ? 'Currently Selected' : 'Select This Theme'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MicrositeThemeSelector;
