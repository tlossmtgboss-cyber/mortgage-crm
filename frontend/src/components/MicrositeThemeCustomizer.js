/**
 * MicrositeThemeCustomizer - Theme Customization Component
 *
 * Allows users to customize their selected theme's colors, fonts, and layout options.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './MicrositeThemeCustomizer.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

// Preset color palettes
const COLOR_PRESETS = [
  { name: 'Classic Blue', primary: '#2563eb', secondary: '#1e40af' },
  { name: 'Bold Red', primary: '#dc2626', secondary: '#1e3a5f' },
  { name: 'Modern Purple', primary: '#8b5cf6', secondary: '#ec4899' },
  { name: 'Forest Green', primary: '#059669', secondary: '#047857' },
  { name: 'Warm Orange', primary: '#ea580c', secondary: '#c2410c' },
  { name: 'Elegant Gold', primary: '#ca8a04', secondary: '#854d0e' },
  { name: 'Slate Gray', primary: '#475569', secondary: '#334155' },
  { name: 'Ocean Teal', primary: '#0891b2', secondary: '#0e7490' },
];

// Font options
const FONT_OPTIONS = [
  { value: 'inter', label: 'Inter', family: "'Inter', -apple-system, sans-serif" },
  { value: 'roboto', label: 'Roboto', family: "'Roboto', sans-serif" },
  { value: 'poppins', label: 'Poppins', family: "'Poppins', sans-serif" },
  { value: 'open-sans', label: 'Open Sans', family: "'Open Sans', sans-serif" },
  { value: 'lato', label: 'Lato', family: "'Lato', sans-serif" },
  { value: 'montserrat', label: 'Montserrat', family: "'Montserrat', sans-serif" },
  { value: 'source-sans', label: 'Source Sans Pro', family: "'Source Sans Pro', sans-serif" },
  { value: 'playfair', label: 'Playfair Display', family: "'Playfair Display', serif" },
];

const MicrositeThemeCustomizer = ({ theme, currentConfig, onConfigChange, onSave }) => {
  const [config, setConfig] = useState({
    primaryColor: '#2563eb',
    secondaryColor: '#1e40af',
    fontFamily: 'inter',
    ...currentConfig
  });
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [activeTab, setActiveTab] = useState('colors');

  // Initialize config from current settings
  useEffect(() => {
    if (currentConfig) {
      setConfig(prev => ({ ...prev, ...currentConfig }));
    }
  }, [currentConfig]);

  // Track changes
  useEffect(() => {
    const configString = JSON.stringify(config);
    const currentString = JSON.stringify(currentConfig || {});
    setHasChanges(configString !== currentString);
  }, [config, currentConfig]);

  // Update config
  const updateConfig = useCallback((key, value) => {
    setConfig(prev => {
      const updated = { ...prev, [key]: value };
      if (onConfigChange) {
        onConfigChange(updated);
      }
      return updated;
    });
  }, [onConfigChange]);

  // Apply preset
  const applyPreset = (preset) => {
    setConfig(prev => {
      const updated = {
        ...prev,
        primaryColor: preset.primary,
        secondaryColor: preset.secondary
      };
      if (onConfigChange) {
        onConfigChange(updated);
      }
      return updated;
    });
  };

  // Save configuration
  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          theme_config: config
        })
      });

      if (response.ok) {
        setHasChanges(false);
        if (onSave) {
          onSave(config);
        }
      } else {
        throw new Error('Failed to save configuration');
      }
    } catch (err) {
      console.error('Error saving config:', err);
      alert('Failed to save customization. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Reset to defaults
  const handleReset = () => {
    const defaults = theme?.defaultConfig || {
      primaryColor: '#2563eb',
      secondaryColor: '#1e40af',
      fontFamily: 'inter'
    };
    setConfig(defaults);
    if (onConfigChange) {
      onConfigChange(defaults);
    }
  };

  // Get layout options for current theme
  const layoutOptions = theme?.layoutOptions || {};

  return (
    <div className="theme-customizer">
      <div className="customizer-header">
        <h3>Customize Your Theme</h3>
        <p>Personalize colors, fonts, and layout to match your brand</p>
      </div>

      {/* Tabs */}
      <div className="customizer-tabs">
        <button
          className={`tab-btn ${activeTab === 'colors' ? 'active' : ''}`}
          onClick={() => setActiveTab('colors')}
        >
          Colors
        </button>
        <button
          className={`tab-btn ${activeTab === 'typography' ? 'active' : ''}`}
          onClick={() => setActiveTab('typography')}
        >
          Typography
        </button>
        {Object.keys(layoutOptions).length > 0 && (
          <button
            className={`tab-btn ${activeTab === 'layout' ? 'active' : ''}`}
            onClick={() => setActiveTab('layout')}
          >
            Layout
          </button>
        )}
      </div>

      {/* Colors Tab */}
      {activeTab === 'colors' && (
        <div className="customizer-section">
          {/* Color Presets */}
          <div className="preset-section">
            <label>Quick Presets</label>
            <div className="color-presets">
              {COLOR_PRESETS.map((preset, index) => (
                <button
                  key={index}
                  className={`preset-btn ${
                    config.primaryColor === preset.primary ? 'active' : ''
                  }`}
                  onClick={() => applyPreset(preset)}
                  title={preset.name}
                >
                  <span
                    className="preset-swatch"
                    style={{
                      background: `linear-gradient(135deg, ${preset.primary} 0%, ${preset.secondary} 100%)`
                    }}
                  />
                  <span className="preset-name">{preset.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Custom Colors */}
          <div className="color-pickers">
            <div className="color-field">
              <label>Primary Color</label>
              <div className="color-input-group">
                <input
                  type="color"
                  value={config.primaryColor}
                  onChange={(e) => updateConfig('primaryColor', e.target.value)}
                  className="color-picker"
                />
                <input
                  type="text"
                  value={config.primaryColor}
                  onChange={(e) => updateConfig('primaryColor', e.target.value)}
                  className="color-text"
                  placeholder="#2563eb"
                />
              </div>
              <span className="color-hint">Used for buttons, links, and accents</span>
            </div>

            <div className="color-field">
              <label>Secondary Color</label>
              <div className="color-input-group">
                <input
                  type="color"
                  value={config.secondaryColor}
                  onChange={(e) => updateConfig('secondaryColor', e.target.value)}
                  className="color-picker"
                />
                <input
                  type="text"
                  value={config.secondaryColor}
                  onChange={(e) => updateConfig('secondaryColor', e.target.value)}
                  className="color-text"
                  placeholder="#1e40af"
                />
              </div>
              <span className="color-hint">Used for backgrounds and highlights</span>
            </div>
          </div>

          {/* Color Preview */}
          <div className="color-preview">
            <label>Preview</label>
            <div
              className="preview-box"
              style={{
                background: `linear-gradient(135deg, ${config.primaryColor} 0%, ${config.secondaryColor} 100%)`
              }}
            >
              <span className="preview-text">Your Brand Colors</span>
              <button className="preview-btn">Sample Button</button>
            </div>
          </div>
        </div>
      )}

      {/* Typography Tab */}
      {activeTab === 'typography' && (
        <div className="customizer-section">
          <div className="font-selector">
            <label>Font Family</label>
            <div className="font-options">
              {FONT_OPTIONS.map((font) => (
                <button
                  key={font.value}
                  className={`font-option ${config.fontFamily === font.value ? 'active' : ''}`}
                  onClick={() => updateConfig('fontFamily', font.value)}
                  style={{ fontFamily: font.family }}
                >
                  <span className="font-sample">Aa</span>
                  <span className="font-name">{font.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Font Preview */}
          <div className="font-preview">
            <label>Preview</label>
            <div
              className="preview-text-box"
              style={{
                fontFamily: FONT_OPTIONS.find(f => f.value === config.fontFamily)?.family || 'Inter'
              }}
            >
              <h2>Your Trusted Mortgage Expert</h2>
              <p>
                With years of experience helping families achieve their homeownership dreams,
                I'm here to guide you through every step of the mortgage process.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Layout Tab */}
      {activeTab === 'layout' && Object.keys(layoutOptions).length > 0 && (
        <div className="customizer-section">
          {Object.entries(layoutOptions).map(([key, values]) => (
            <div key={key} className="layout-option">
              <label>
                {key
                  .replace(/([A-Z])/g, ' $1')
                  .replace(/^./, str => str.toUpperCase())
                  .trim()}
              </label>
              <div className="layout-choices">
                {values.map((value) => (
                  <button
                    key={value}
                    className={`layout-choice ${config[key] === value ? 'active' : ''}`}
                    onClick={() => updateConfig(key, value)}
                  >
                    {value.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>
            </div>
          ))}

          {/* Toggle Options */}
          {theme?.features?.includes('testimonials') && (
            <div className="toggle-option">
              <label>
                <input
                  type="checkbox"
                  checked={config.showTestimonials !== false}
                  onChange={(e) => updateConfig('showTestimonials', e.target.checked)}
                />
                <span className="toggle-label">Show Testimonials Section</span>
              </label>
            </div>
          )}

          {theme?.features?.includes('rate_calculator') && (
            <div className="toggle-option">
              <label>
                <input
                  type="checkbox"
                  checked={config.showRateCalculator !== false}
                  onChange={(e) => updateConfig('showRateCalculator', e.target.checked)}
                />
                <span className="toggle-label">Show Rate Calculator</span>
              </label>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="customizer-actions">
        <button
          className="reset-btn"
          onClick={handleReset}
          disabled={saving}
        >
          Reset to Defaults
        </button>
        <button
          className="save-btn"
          onClick={handleSave}
          disabled={saving || !hasChanges}
        >
          {saving ? 'Saving...' : hasChanges ? 'Save Changes' : 'Saved'}
        </button>
      </div>
    </div>
  );
};

export default MicrositeThemeCustomizer;
