/**
 * AppointmentTypesStep — Smart Calendar Guided Setup, Step 3
 *
 * Pre-built mortgage-specific appointment types that users toggle on/off.
 * Each type can be expanded for inline editing (name, duration, description,
 * color, meeting mode).  Users can also add custom types and reorder via
 * up/down buttons.
 *
 * Data shape matches calendarSettingsAPI.createAppointmentType / updateAppointmentType:
 *   { type_name, description, duration_minutes, color, location_type, is_public }
 *
 * Props:
 *   onStepComplete(types)  - called with the enabled types array when valid
 *   initialTypes           - optional array of existing types from API
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './AppointmentTypesStep.css';

// ============================================================================
// Constants
// ============================================================================

const MEETING_MODES = [
  { value: 'virtual', label: 'Video', icon: 'fa-video' },
  { value: 'phone', label: 'Phone', icon: 'fa-phone' },
  { value: 'in_person', label: 'In-Person', icon: 'fa-map-marker-alt' },
];

const DURATION_OPTIONS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '60 min' },
  { value: 90, label: '90 min' },
];

const COLOR_PALETTE = [
  '#3b82f6', // blue
  '#10b981', // green
  '#8b5cf6', // purple
  '#f59e0b', // orange
  '#14b8a6', // teal
  '#ef4444', // red
  '#6b7280', // gray
  '#218D8D', // brand teal
  '#ec4899', // pink
  '#6366f1', // indigo
];

const MEETING_MODE_ICONS = {
  virtual: 'fa-video',
  phone: 'fa-phone',
  in_person: 'fa-map-marker-alt',
};

/**
 * Pre-built mortgage appointment types.
 * `_prebuiltKey` is a stable identifier so we can tell pre-built from custom
 * even before they have a server-assigned id.
 */
const PREBUILT_TYPES = [
  {
    _prebuiltKey: 'initial_consultation',
    type_name: 'Initial Consultation',
    duration_minutes: 30,
    color: '#3b82f6',
    description: 'Meet new borrowers, discuss loan options',
    location_type: 'virtual',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'preapproval_review',
    type_name: 'Pre-Approval Review',
    duration_minutes: 45,
    color: '#10b981',
    description: 'Review documents, run pre-approval',
    location_type: 'virtual',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'application_walkthrough',
    type_name: 'Application Walkthrough',
    duration_minutes: 60,
    color: '#8b5cf6',
    description: 'Guide borrower through full application',
    location_type: 'virtual',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'document_collection',
    type_name: 'Document Collection',
    duration_minutes: 30,
    color: '#f59e0b',
    description: 'Collect outstanding docs',
    location_type: 'virtual',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'rate_lock_discussion',
    type_name: 'Rate Lock Discussion',
    duration_minutes: 15,
    color: '#14b8a6',
    description: 'Review rates and lock options',
    location_type: 'phone',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'closing_prep',
    type_name: 'Closing Prep',
    duration_minutes: 30,
    color: '#ef4444',
    description: 'Review CD, prepare for closing',
    location_type: 'virtual',
    is_public: true,
    enabled: true,
  },
  {
    _prebuiltKey: 'follow_up_call',
    type_name: 'Follow-Up Call',
    duration_minutes: 15,
    color: '#6b7280',
    description: 'Check-in with existing borrower',
    location_type: 'phone',
    is_public: true,
    enabled: false,
  },
];

// ============================================================================
// Helper
// ============================================================================

function durationLabel(minutes) {
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h} hr`;
  }
  return `${minutes} min`;
}

let _nextTempId = 1;
function tempId() {
  return `_tmp_${Date.now()}_${_nextTempId++}`;
}

// ============================================================================
// TypeCard sub-component
// ============================================================================

function TypeCard({
  type,
  index,
  totalCount,
  isEditing,
  onToggle,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  onMoveUp,
  onMoveDown,
}) {
  const [draft, setDraft] = useState(null);
  const nameRef = useRef(null);

  // When we enter edit mode, seed the draft from the type
  useEffect(() => {
    if (isEditing) {
      setDraft({
        type_name: type.type_name,
        description: type.description || '',
        duration_minutes: type.duration_minutes,
        color: type.color,
        location_type: type.location_type || 'virtual',
      });
      // Focus name field when editor opens
      setTimeout(() => nameRef.current?.focus(), 50);
    } else {
      setDraft(null);
    }
  }, [isEditing]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateDraft = useCallback((field, value) => {
    setDraft(prev => prev ? { ...prev, [field]: value } : prev);
  }, []);

  const handleSave = useCallback(() => {
    if (!draft || !draft.type_name.trim()) return;
    onSaveEdit(draft);
  }, [draft, onSaveEdit]);

  const modeIcon = MEETING_MODE_ICONS[type.location_type] || 'fa-video';
  const modeLabel = MEETING_MODES.find(m => m.value === type.location_type)?.label || 'Video';
  const isCustom = type._isCustom;
  const cardClasses = [
    'appt-type-card',
    !type.enabled ? 'disabled-card' : '',
    isEditing ? 'editing' : '',
    isCustom ? 'custom-card' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cardClasses}>
      <div className="card-color-bar" style={{ backgroundColor: type.color }} />
      <div className="card-body">
        {/* Summary row */}
        <div
          className="card-summary"
          onClick={() => {
            if (!isEditing) onEdit();
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              if (!isEditing) onEdit();
            }
          }}
          aria-expanded={isEditing}
          aria-label={`${type.type_name} - click to edit`}
        >
          <div className="card-info">
            <div className="card-name-row">
              <span className="card-name">{type.type_name}</span>
              {isCustom && <span className="card-custom-badge">Custom</span>}
            </div>
            {type.description && <p className="card-desc">{type.description}</p>}
            <div className="card-meta">
              <span className="meta-badge">
                <i className="fas fa-clock" /> {durationLabel(type.duration_minutes)}
              </span>
              <span className="meta-badge">
                <i className={`fas ${modeIcon}`} /> {modeLabel}
              </span>
            </div>
          </div>

          <div className="card-controls" onClick={(e) => e.stopPropagation()}>
            <button
              className="reorder-btn"
              onClick={onMoveUp}
              disabled={index === 0}
              aria-label="Move up"
              title="Move up"
              type="button"
            >
              <i className="fas fa-chevron-up" />
            </button>
            <button
              className="reorder-btn"
              onClick={onMoveDown}
              disabled={index === totalCount - 1}
              aria-label="Move down"
              title="Move down"
              type="button"
            >
              <i className="fas fa-chevron-down" />
            </button>
            <label className="type-toggle">
              <input
                type="checkbox"
                checked={type.enabled}
                onChange={() => onToggle()}
                aria-label={`${type.enabled ? 'Disable' : 'Enable'} ${type.type_name}`}
              />
              <span className="toggle-track" />
            </label>
          </div>
        </div>

        {/* Inline editor */}
        {isEditing && draft && (
          <div className="card-editor">
            <div className="editor-grid">
              <div className="editor-field">
                <label>Name</label>
                <input
                  ref={nameRef}
                  type="text"
                  value={draft.type_name}
                  onChange={(e) => updateDraft('type_name', e.target.value)}
                  placeholder="Appointment type name"
                  maxLength={100}
                />
              </div>

              <div className="editor-field">
                <label>Duration</label>
                <select
                  value={draft.duration_minutes}
                  onChange={(e) => updateDraft('duration_minutes', parseInt(e.target.value, 10))}
                >
                  {DURATION_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div className="editor-field full-width">
                <label>Description</label>
                <textarea
                  value={draft.description}
                  onChange={(e) => updateDraft('description', e.target.value)}
                  placeholder="Brief description borrowers will see"
                  rows={2}
                  maxLength={200}
                />
              </div>

              <div className="editor-field">
                <label>Color</label>
                <div className="color-options">
                  {COLOR_PALETTE.map(c => (
                    <button
                      key={c}
                      type="button"
                      className={`color-dot ${draft.color === c ? 'selected' : ''}`}
                      style={{ backgroundColor: c }}
                      onClick={() => updateDraft('color', c)}
                      aria-label={`Select color ${c}`}
                    />
                  ))}
                </div>
              </div>

              <div className="editor-field">
                <label>Meeting Mode</label>
                <div className="mode-options">
                  {MEETING_MODES.map(mode => (
                    <label
                      key={mode.value}
                      className={`mode-option ${draft.location_type === mode.value ? 'selected' : ''}`}
                    >
                      <input
                        type="radio"
                        name={`mode-${type._key || type.id}`}
                        value={mode.value}
                        checked={draft.location_type === mode.value}
                        onChange={() => updateDraft('location_type', mode.value)}
                      />
                      <i className={`fas ${mode.icon}`} />
                      {mode.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="editor-actions">
              <div className="editor-left-actions">
                {isCustom && (
                  <button
                    type="button"
                    className="editor-btn btn-danger"
                    onClick={onDelete}
                  >
                    <i className="fas fa-trash" /> Remove
                  </button>
                )}
              </div>
              <div className="editor-right-actions">
                <button
                  type="button"
                  className="editor-btn"
                  onClick={onCancelEdit}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="editor-btn btn-save"
                  onClick={handleSave}
                  disabled={!draft.type_name.trim()}
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Main component
// ============================================================================

export default function AppointmentTypesStep({ onStepComplete, initialTypes }) {
  const [types, setTypes] = useState(() => initTypes(initialTypes));
  const [editingKey, setEditingKey] = useState(null);
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState('');

  // Notify parent whenever the enabled set changes
  const enabledCount = types.filter(t => t.enabled).length;

  useEffect(() => {
    if (enabledCount > 0) {
      setValidationError('');
    }
  }, [enabledCount]);

  // ------------------------------------------------------------------
  // Initialize types: merge server data with pre-built defaults
  // ------------------------------------------------------------------
  function initTypes(existing) {
    if (existing && existing.length > 0) {
      // Map server types, preserving order and adding _key for React
      return existing.map(t => ({
        ...t,
        _key: t.id || tempId(),
        enabled: t.is_active !== undefined ? t.is_active : true,
        _isCustom: !PREBUILT_TYPES.some(
          pb => pb.type_name.toLowerCase() === (t.type_name || '').toLowerCase()
        ),
      }));
    }
    // No existing types: seed from pre-built defaults
    return PREBUILT_TYPES.map(pb => ({
      ...pb,
      _key: pb._prebuiltKey,
      _isCustom: false,
    }));
  }

  // ------------------------------------------------------------------
  // Toggle enabled/disabled
  // ------------------------------------------------------------------
  const handleToggle = useCallback((key) => {
    setTypes(prev => prev.map(t =>
      t._key === key ? { ...t, enabled: !t.enabled } : t
    ));
  }, []);

  // ------------------------------------------------------------------
  // Reorder
  // ------------------------------------------------------------------
  const handleMove = useCallback((index, direction) => {
    setTypes(prev => {
      const next = [...prev];
      const swapIdx = index + direction;
      if (swapIdx < 0 || swapIdx >= next.length) return prev;
      [next[index], next[swapIdx]] = [next[swapIdx], next[index]];
      return next;
    });
  }, []);

  // ------------------------------------------------------------------
  // Edit
  // ------------------------------------------------------------------
  const handleEdit = useCallback((key) => {
    setEditingKey(key);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingKey(null);
  }, []);

  const handleSaveEdit = useCallback((key, draft) => {
    setTypes(prev => prev.map(t =>
      t._key === key
        ? {
            ...t,
            type_name: draft.type_name,
            description: draft.description,
            duration_minutes: draft.duration_minutes,
            color: draft.color,
            location_type: draft.location_type,
          }
        : t
    ));
    setEditingKey(null);
  }, []);

  // ------------------------------------------------------------------
  // Add custom type
  // ------------------------------------------------------------------
  const handleAddCustom = useCallback(() => {
    const key = tempId();
    const newType = {
      _key: key,
      _isCustom: true,
      type_name: '',
      description: '',
      duration_minutes: 30,
      color: COLOR_PALETTE[types.length % COLOR_PALETTE.length],
      location_type: 'virtual',
      is_public: true,
      enabled: true,
    };
    setTypes(prev => [...prev, newType]);
    setEditingKey(key);
  }, [types.length]);

  // ------------------------------------------------------------------
  // Delete custom type
  // ------------------------------------------------------------------
  const handleDelete = useCallback((key) => {
    setTypes(prev => prev.filter(t => t._key !== key));
    if (editingKey === key) {
      setEditingKey(null);
    }
  }, [editingKey]);

  // ------------------------------------------------------------------
  // Save to API
  // ------------------------------------------------------------------
  const handleSaveAll = useCallback(async () => {
    const enabled = types.filter(t => t.enabled);
    if (enabled.length === 0) {
      setValidationError('At least one appointment type must be enabled.');
      return;
    }
    // Validate all enabled types have a name
    const nameless = enabled.find(t => !t.type_name.trim());
    if (nameless) {
      setValidationError('All enabled types must have a name.');
      setEditingKey(nameless._key);
      return;
    }

    setSaving(true);
    setValidationError('');

    try {
      // Save each type to API.  For types that already have a server id, update.
      // For new types, create.  Disabled pre-built types are skipped (not created).
      const savedTypes = [];

      for (const t of types) {
        const payload = {
          type_name: t.type_name,
          description: t.description || '',
          duration_minutes: t.duration_minutes,
          color: t.color,
          location_type: t.location_type || 'virtual',
          is_public: t.is_public !== false,
          is_active: t.enabled,
        };

        if (t.id) {
          // Existing type -- update
          await calendarSettingsAPI.updateAppointmentType(t.id, payload);
          savedTypes.push({ ...t, ...payload });
        } else if (t.enabled) {
          // New type, enabled -- create
          const created = await calendarSettingsAPI.createAppointmentType(payload);
          savedTypes.push({ ...t, ...(created?.data || created), id: (created?.data || created)?.id });
        }
        // Disabled new types are simply not persisted until user enables them
      }

      // Reorder: send the ordered list of ids for all saved types that have ids
      const orderedIds = savedTypes.filter(t => t.id).map(t => t.id);
      if (orderedIds.length > 1) {
        try {
          await calendarSettingsAPI.reorderAppointmentTypes(orderedIds);
        } catch (_reorderErr) {
          // Reorder is best-effort in setup flow
        }
      }

      toast.success(`${enabled.length} appointment type${enabled.length !== 1 ? 's' : ''} saved`);

      if (onStepComplete) {
        onStepComplete(savedTypes);
      }
    } catch (err) {
      console.error('Failed to save appointment types:', err);
      toast.error(err.message || 'Failed to save appointment types');
    } finally {
      setSaving(false);
    }
  }, [types, onStepComplete]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="appt-types-step">
      <div className="step-intro">
        <h2>Appointment Types</h2>
        <p>
          Choose which meeting types borrowers can book with you. We have
          pre-built the most common mortgage appointments -- just toggle the
          ones you need and customize if you like.
        </p>
      </div>

      {/* Live enabled count */}
      <div
        className={`enabled-count-banner ${enabledCount > 0 ? 'has-enabled' : 'none-enabled'}`}
        role="status"
        aria-live="polite"
      >
        <i className={`fas ${enabledCount > 0 ? 'fa-check-circle' : 'fa-exclamation-circle'}`} />
        <span>
          {enabledCount > 0
            ? `${enabledCount} type${enabledCount !== 1 ? 's' : ''} enabled \u2014 borrowers will see these on your booking page`
            : 'No types enabled \u2014 enable at least one for your booking page'}
        </span>
      </div>

      {/* Validation error */}
      {validationError && (
        <div className="validation-error" role="alert">
          <i className="fas fa-exclamation-triangle" />
          {validationError}
        </div>
      )}

      {/* Type cards */}
      <div className="type-card-list">
        {types.map((type, idx) => (
          <TypeCard
            key={type._key}
            type={type}
            index={idx}
            totalCount={types.length}
            isEditing={editingKey === type._key}
            onToggle={() => handleToggle(type._key)}
            onEdit={() => handleEdit(type._key)}
            onCancelEdit={handleCancelEdit}
            onSaveEdit={(draft) => handleSaveEdit(type._key, draft)}
            onDelete={() => handleDelete(type._key)}
            onMoveUp={() => handleMove(idx, -1)}
            onMoveDown={() => handleMove(idx, 1)}
          />
        ))}
      </div>

      {/* Add Custom */}
      <button
        type="button"
        className="add-custom-btn"
        onClick={handleAddCustom}
      >
        <i className="fas fa-plus" /> Add Custom Type
      </button>

      {/* Save / continue */}
      <button
        type="button"
        className="editor-btn btn-save"
        style={{ width: '100%', padding: '12px', fontSize: '15px' }}
        onClick={handleSaveAll}
        disabled={saving}
      >
        {saving ? 'Saving...' : `Save ${enabledCount} Appointment Type${enabledCount !== 1 ? 's' : ''} & Continue`}
      </button>
    </div>
  );
}
