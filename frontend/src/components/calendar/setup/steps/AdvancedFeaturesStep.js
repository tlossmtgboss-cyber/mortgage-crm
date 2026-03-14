/**
 * AdvancedFeaturesStep - Step 9 of Smart Calendar guided setup
 *
 * Progressive disclosure of advanced features via toggle cards.
 * Each feature has an icon, title, description, toggle, and optional "Recommended" badge.
 * Displays a count of enabled features. Saves feature toggles to the API.
 *
 * Saves to: PUT /api/v1/scheduler/settings/features
 */

import React, { useState, useEffect, useCallback } from 'react';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './AdvancedFeaturesStep.css';

// ============================================================================
// Feature Definitions
// ============================================================================

const FEATURE_DEFINITIONS = [
  {
    key: 'ai_scheduling',
    icon: 'fa-brain',
    title: 'AI Scheduling',
    description: 'Let AI suggest optimal meeting times based on borrower preferences and LO availability patterns.',
    recommended: true,
    category: 'intelligence',
  },
  {
    key: 'smart_reminders',
    icon: 'fa-bell-exclamation',
    iconFallback: 'fa-bell',
    title: 'Smart Reminders',
    description: 'Automatic follow-up for no-shows with configurable retry sequences.',
    recommended: true,
    category: 'communication',
  },
  {
    key: 'ab_testing',
    icon: 'fa-flask',
    title: 'Booking Page A/B Testing',
    description: 'Test different booking page layouts to maximize conversion rates.',
    category: 'optimization',
  },
  {
    key: 'calendar_analytics',
    icon: 'fa-chart-line',
    title: 'Calendar Analytics',
    description: 'Track appointment metrics, no-show rates, and booking trends over time.',
    recommended: true,
    category: 'intelligence',
  },
  {
    key: 'waitlist',
    icon: 'fa-clock',
    title: 'Waitlist',
    description: 'Let borrowers join a waitlist when no slots are available and auto-notify when one opens.',
    category: 'booking',
  },
  {
    key: 'post_appointment_surveys',
    icon: 'fa-comment-dots',
    title: 'Post-Appointment Surveys',
    description: 'Collect feedback after meetings to improve service quality.',
    category: 'communication',
  },
  {
    key: 'calendar_labels',
    icon: 'fa-tags',
    title: 'Calendar Labels',
    description: 'Color-code appointments by type, loan stage, or custom categories.',
    category: 'organization',
  },
  {
    key: 'drag_and_drop',
    icon: 'fa-hand-pointer',
    title: 'Drag & Drop',
    description: 'Reschedule appointments by dragging them to a new time slot on the calendar.',
    category: 'productivity',
  },
  {
    key: 'keyboard_shortcuts',
    icon: 'fa-keyboard',
    title: 'Keyboard Shortcuts',
    description: 'Navigate the calendar, create appointments, and switch views with keyboard shortcuts.',
    category: 'productivity',
  },
  {
    key: 'dark_mode',
    icon: 'fa-moon',
    title: 'Dark Mode',
    description: 'Switch to a dark theme for reduced eye strain during evening work sessions.',
    category: 'appearance',
  },
];

// ============================================================================
// Sub-components
// ============================================================================

const FeatureCard = ({ feature, enabled, onToggle }) => (
  <div className={`afs-feature-card ${enabled ? 'afs-feature-card--enabled' : ''}`}>
    <div className="afs-feature-card__icon">
      <i className={`fas ${feature.iconFallback || feature.icon}`} aria-hidden="true" />
    </div>
    <div className="afs-feature-card__body">
      <div className="afs-feature-card__header">
        <span className="afs-feature-card__title">{feature.title}</span>
        {feature.recommended && (
          <span className="afs-feature-card__recommended">Recommended</span>
        )}
      </div>
      <p className="afs-feature-card__desc">{feature.description}</p>
    </div>
    <label className="afs-feature-toggle" aria-label={`Toggle ${feature.title}`}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={() => onToggle(feature.key)}
      />
      <span className="afs-toggle-track">
        <span className="afs-toggle-thumb" />
      </span>
    </label>
  </div>
);

const FeatureCounter = ({ enabled, total }) => {
  const pct = total > 0 ? Math.round((enabled / total) * 100) : 0;
  return (
    <div className="afs-counter">
      <div className="afs-counter__bar-bg">
        <div className="afs-counter__bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="afs-counter__text">
        <strong>{enabled}</strong> of {total} features enabled
      </span>
    </div>
  );
};

// ============================================================================
// Main component
// ============================================================================

const AdvancedFeaturesStep = ({ onComplete, onBack }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [features, setFeatures] = useState(() => {
    const initial = {};
    FEATURE_DEFINITIONS.forEach(f => {
      // Start with recommended features enabled by default
      initial[f.key] = !!f.recommended;
    });
    return initial;
  });

  // --------------------------------------------------------------------------
  // Load saved feature toggles
  // --------------------------------------------------------------------------

  const loadFeatures = useCallback(async () => {
    setLoading(true);
    try {
      const res = await calendarSettingsAPI.getFeatures
        ? await calendarSettingsAPI.getFeatures()
        : null;
      if (res?.data?.features) {
        setFeatures(prev => ({ ...prev, ...res.data.features }));
      }
    } catch (err) {
      // If endpoint doesn't exist yet, use defaults
      console.error('Failed to load feature settings:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFeatures();
  }, [loadFeatures]);

  // --------------------------------------------------------------------------
  // Toggle handler
  // --------------------------------------------------------------------------

  const handleToggle = useCallback((key) => {
    setFeatures(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const enableAll = useCallback(() => {
    const all = {};
    FEATURE_DEFINITIONS.forEach(f => { all[f.key] = true; });
    setFeatures(all);
  }, []);

  const enableRecommended = useCallback(() => {
    const rec = {};
    FEATURE_DEFINITIONS.forEach(f => { rec[f.key] = !!f.recommended; });
    setFeatures(rec);
  }, []);

  // --------------------------------------------------------------------------
  // Save
  // --------------------------------------------------------------------------

  const handleSave = async () => {
    setSaving(true);
    try {
      if (calendarSettingsAPI.updateFeatures) {
        await calendarSettingsAPI.updateFeatures({ features });
      }
      toast.success('Feature preferences saved');
      if (onComplete) onComplete({ features });
    } catch (err) {
      console.error('Failed to save feature settings:', err);
      toast.error('Failed to save feature preferences');
    } finally {
      setSaving(false);
    }
  };

  // --------------------------------------------------------------------------
  // Counts
  // --------------------------------------------------------------------------

  const enabledCount = Object.values(features).filter(Boolean).length;
  const totalCount = FEATURE_DEFINITIONS.length;

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="afs-loading">
        <div className="afs-spinner" />
        <span>Loading feature settings...</span>
      </div>
    );
  }

  return (
    <div className="afs-step">
      {/* Header */}
      <div className="afs-header">
        <div className="afs-step-badge">Step 9</div>
        <h2 className="afs-title">Advanced Features</h2>
        <p className="afs-subtitle">
          Enable the features that fit your workflow. You can change these anytime in Settings.
        </p>
      </div>

      {/* Counter + Quick Actions */}
      <div className="afs-toolbar">
        <FeatureCounter enabled={enabledCount} total={totalCount} />
        <div className="afs-toolbar-actions">
          <button
            type="button"
            className="afs-link-btn"
            onClick={enableRecommended}
          >
            Recommended only
          </button>
          <button
            type="button"
            className="afs-link-btn"
            onClick={enableAll}
          >
            Enable all
          </button>
        </div>
      </div>

      {/* Feature Cards */}
      <div className="afs-features-grid">
        {FEATURE_DEFINITIONS.map(feature => (
          <FeatureCard
            key={feature.key}
            feature={feature}
            enabled={!!features[feature.key]}
            onToggle={handleToggle}
          />
        ))}
      </div>

      {/* Summary */}
      <div className="afs-summary">
        <i className="fas fa-info-circle" aria-hidden="true" />
        <span>
          {enabledCount === 0
            ? 'No features enabled. You can always turn them on later from Settings.'
            : enabledCount === totalCount
              ? 'All features enabled. You have access to the full calendar experience.'
              : `${enabledCount} feature${enabledCount !== 1 ? 's' : ''} enabled. You can adjust these in Calendar Settings anytime.`
          }
        </span>
      </div>

      {/* Actions */}
      <div className="afs-actions">
        {onBack && (
          <button type="button" className="afs-btn afs-btn--secondary" onClick={onBack}>
            <i className="fas fa-arrow-left" aria-hidden="true" /> Back
          </button>
        )}
        <button
          type="button"
          className="afs-btn afs-btn--primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? (
            <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Saving...</>
          ) : (
            <>Finish Setup <i className="fas fa-check" aria-hidden="true" /></>
          )}
        </button>
      </div>
    </div>
  );
};

export default AdvancedFeaturesStep;
