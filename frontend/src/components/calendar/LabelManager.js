import React, { useState, useCallback, useRef } from 'react';
import '../../styles/calendar-labels.css';

/**
 * Default preset colors for the color picker.
 */
const PRESET_COLORS = [
  '#4A90D9',  // Blue
  '#27AE60',  // Green
  '#8E44AD',  // Purple
  '#E67E22',  // Orange
  '#16A085',  // Teal
  '#E74C3C',  // Red
  '#F1C40F',  // Yellow
  '#34495E',  // Dark Gray
];

/**
 * LabelManager - Admin interface for managing calendar labels.
 *
 * Features:
 * - List of labels with color swatch, name, optional icon, edit/delete buttons
 * - Create new label: name input + color picker (8 preset colors + custom hex)
 * - Drag to reorder
 *
 * Props:
 *   labels          - Array of label objects: { id, name, color, icon, is_default, sort_order }
 *   onCreateLabel   - Callback: (labelData) => void
 *   onUpdateLabel   - Callback: (labelId, labelData) => void
 *   onDeleteLabel   - Callback: (labelId) => void
 *   onReorderLabels - Callback: (orderedIds) => void
 *   loading         - Boolean, shows loading state
 */
const LabelManager = React.memo(function LabelManager({
  labels = [],
  onCreateLabel,
  onUpdateLabel,
  onDeleteLabel,
  onReorderLabels,
  loading = false,
}) {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formName, setFormName] = useState('');
  const [formColor, setFormColor] = useState(PRESET_COLORS[0]);
  const [formIcon, setFormIcon] = useState('');
  const [customHex, setCustomHex] = useState('');

  // Drag state
  const [dragIndex, setDragIndex] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const dragItemRef = useRef(null);

  const resetForm = useCallback(() => {
    setFormName('');
    setFormColor(PRESET_COLORS[0]);
    setFormIcon('');
    setCustomHex('');
    setEditingId(null);
    setShowForm(false);
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmedName = formName.trim();
    if (!trimmedName) return;

    const labelData = {
      name: trimmedName,
      color: formColor,
      icon: formIcon.trim() || null,
    };

    if (editingId) {
      onUpdateLabel(editingId, labelData);
    } else {
      onCreateLabel(labelData);
    }

    resetForm();
  }, [formName, formColor, formIcon, editingId, onCreateLabel, onUpdateLabel, resetForm]);

  const handleEdit = useCallback((label) => {
    setEditingId(label.id);
    setFormName(label.name);
    setFormColor(label.color);
    setFormIcon(label.icon || '');
    setCustomHex(PRESET_COLORS.includes(label.color) ? '' : label.color);
    setShowForm(true);
  }, []);

  const handleDelete = useCallback((labelId) => {
    if (window.confirm('Delete this label? It will be removed from all appointments.')) {
      onDeleteLabel(labelId);
    }
  }, [onDeleteLabel]);

  const handleColorSelect = useCallback((color) => {
    setFormColor(color);
    setCustomHex('');
  }, []);

  const handleCustomHexChange = useCallback((value) => {
    setCustomHex(value);
    // Apply if it looks like a valid hex color
    if (/^#[0-9A-Fa-f]{6}$/.test(value) || /^#[0-9A-Fa-f]{3}$/.test(value)) {
      setFormColor(value);
    }
  }, []);

  // Drag and drop handlers
  const handleDragStart = useCallback((e, index) => {
    setDragIndex(index);
    dragItemRef.current = index;
    e.dataTransfer.effectAllowed = 'move';
    // Use a timeout so the dragging class applies after the drag image is captured
    setTimeout(() => {
      const el = document.querySelector(`[data-label-index="${index}"]`);
      if (el) el.classList.add('dragging');
    }, 0);
  }, []);

  const handleDragOver = useCallback((e, index) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (dragIndex !== null && dragOverIndex !== null && dragIndex !== dragOverIndex) {
      const reordered = [...labels];
      const [removed] = reordered.splice(dragIndex, 1);
      reordered.splice(dragOverIndex, 0, removed);
      onReorderLabels(reordered.map(l => l.id));
    }
    setDragIndex(null);
    setDragOverIndex(null);
    // Remove dragging class from all items
    document.querySelectorAll('.label-manager-item.dragging').forEach(el => {
      el.classList.remove('dragging');
    });
  }, [dragIndex, dragOverIndex, labels, onReorderLabels]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === 'Escape') {
      resetForm();
    }
  }, [handleSubmit, resetForm]);

  return (
    <div className="label-manager">
      <div className="label-manager-header">
        <h3>Calendar Labels</h3>
        {!showForm && (
          <button
            className="btn-add-appointment"
            onClick={() => {
              resetForm();
              setShowForm(true);
            }}
            title="Add new label"
          >
            + New Label
          </button>
        )}
      </div>

      {loading ? (
        <div className="label-manager-empty">Loading labels...</div>
      ) : labels.length === 0 && !showForm ? (
        <div className="label-manager-empty">
          No labels yet. Create one to start color-coding your appointments.
        </div>
      ) : (
        <div className="label-manager-list">
          {labels.map((label, index) => (
            <div
              key={label.id}
              className={`label-manager-item${dragOverIndex === index ? ' drag-over' : ''}`}
              data-label-index={index}
              draggable
              onDragStart={(e) => handleDragStart(e, index)}
              onDragOver={(e) => handleDragOver(e, index)}
              onDragEnd={handleDragEnd}
            >
              <div className="label-manager-drag-handle" aria-hidden="true">
                <span /><span /><span />
              </div>
              <div
                className="label-swatch label-swatch--large"
                style={{ backgroundColor: label.color }}
                aria-hidden="true"
              />
              {label.icon && (
                <span className="label-manager-icon">{label.icon}</span>
              )}
              <span className="label-manager-name">{label.name}</span>
              <div className="label-manager-actions">
                <button onClick={() => handleEdit(label)} title="Edit label">
                  Edit
                </button>
                <button
                  className="delete"
                  onClick={() => handleDelete(label.id)}
                  title="Delete label"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="label-form" onKeyDown={handleKeyDown}>
          <div className="label-form-row">
            <div className="label-form-field">
              <label htmlFor="label-name-input">Name</label>
              <input
                id="label-name-input"
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Pre-Approval"
                maxLength={50}
                autoFocus
              />
            </div>
            <div className="label-form-field" style={{ maxWidth: 80 }}>
              <label htmlFor="label-icon-input">Icon</label>
              <input
                id="label-icon-input"
                type="text"
                value={formIcon}
                onChange={(e) => setFormIcon(e.target.value)}
                placeholder="optional"
                maxLength={4}
              />
            </div>
          </div>

          <div className="label-color-picker">
            <label>Color</label>
            <div className="label-color-presets">
              {PRESET_COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  className={`label-color-preset${formColor === color ? ' selected' : ''}`}
                  style={{ backgroundColor: color }}
                  onClick={() => handleColorSelect(color)}
                  title={color}
                  aria-label={`Select color ${color}`}
                />
              ))}
            </div>
            <div className="label-color-custom">
              <span style={{ fontSize: 12, color: '#64748b' }}>Custom:</span>
              <input
                type="text"
                value={customHex}
                onChange={(e) => handleCustomHexChange(e.target.value)}
                placeholder="#RRGGBB"
                maxLength={7}
              />
              {customHex && /^#[0-9A-Fa-f]{3,6}$/.test(customHex) && (
                <div
                  className="label-swatch"
                  style={{ backgroundColor: customHex }}
                  aria-hidden="true"
                />
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
            <span style={{ fontSize: 12, color: '#64748b' }}>Preview:</span>
            <div
              className="label-swatch label-swatch--large"
              style={{ backgroundColor: formColor }}
              aria-hidden="true"
            />
            <span style={{ fontSize: 13, fontWeight: 500 }}>
              {formName.trim() || 'Label Name'}
            </span>
          </div>

          <div className="label-form-actions">
            <button type="button" onClick={resetForm}>Cancel</button>
            <button
              type="button"
              className="btn-primary"
              onClick={handleSubmit}
              disabled={!formName.trim()}
            >
              {editingId ? 'Save Changes' : 'Create Label'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
});

export default LabelManager;
