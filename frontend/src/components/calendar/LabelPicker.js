import React, { useState, useCallback, useRef, useEffect } from 'react';
import '../../styles/calendar-labels.css';

/**
 * LabelPicker - Inline dropdown/popover for assigning labels to appointments.
 *
 * Features:
 * - Small trigger button showing currently selected label dots
 * - Popover with all available labels as checkboxes
 * - Multi-select: an appointment can have multiple labels
 * - Click outside or Escape to close
 *
 * Props:
 *   labels           - Array of all available labels: [{ id, name, color, icon }]
 *   selectedLabelIds - Array of currently assigned label IDs: [id, ...]
 *   onToggleLabel    - Callback: (labelId, isNowSelected) => void
 *   disabled         - Boolean, disables the picker
 *   compact          - Boolean, shows a smaller trigger button
 */
const LabelPicker = React.memo(function LabelPicker({
  labels = [],
  selectedLabelIds = [],
  onToggleLabel,
  disabled = false,
  compact = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef(null);

  const selectedSet = React.useMemo(
    () => new Set(selectedLabelIds),
    [selectedLabelIds]
  );

  const selectedLabels = React.useMemo(
    () => labels.filter(l => selectedSet.has(l.id)),
    [labels, selectedSet]
  );

  const handleToggle = useCallback((labelId) => {
    if (disabled) return;
    const isCurrentlySelected = selectedSet.has(labelId);
    onToggleLabel(labelId, !isCurrentlySelected);
  }, [selectedSet, onToggleLabel, disabled]);

  const handleTriggerClick = useCallback((e) => {
    e.stopPropagation();
    if (!disabled) {
      setIsOpen(prev => !prev);
    }
  }, [disabled]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen]);

  return (
    <div className="label-picker-wrapper">
      <button
        type="button"
        className="label-picker-trigger"
        onClick={handleTriggerClick}
        disabled={disabled}
        title={selectedLabels.length > 0
          ? `Labels: ${selectedLabels.map(l => l.name).join(', ')}`
          : 'Add labels'
        }
        aria-label="Toggle label picker"
        aria-expanded={isOpen}
      >
        {selectedLabels.length > 0 ? (
          <span className="selected-labels">
            {selectedLabels.slice(0, 3).map(label => (
              <span
                key={label.id}
                className="label-swatch label-swatch--small"
                style={{ backgroundColor: label.color }}
              />
            ))}
            {selectedLabels.length > 3 && (
              <span style={{ fontSize: 10, color: '#64748b' }}>
                +{selectedLabels.length - 3}
              </span>
            )}
          </span>
        ) : (
          <>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
              <line x1="7" y1="7" x2="7.01" y2="7" />
            </svg>
            {!compact && <span>Labels</span>}
          </>
        )}
      </button>

      {isOpen && (
        <>
          <div className="label-picker-backdrop" onClick={handleClose} />
          <div className="label-picker-popover" ref={popoverRef} onClick={(e) => e.stopPropagation()}>
            <div className="label-picker-popover-title">Labels</div>
            {labels.length === 0 ? (
              <div className="label-picker-no-labels">
                No labels available. Create labels in Calendar Settings.
              </div>
            ) : (
              labels.map(label => {
                const isSelected = selectedSet.has(label.id);
                return (
                  <button
                    key={label.id}
                    type="button"
                    className={`label-picker-option${isSelected ? ' selected' : ''}`}
                    onClick={() => handleToggle(label.id)}
                    style={{ '--label-color': label.color }}
                  >
                    <span className="label-picker-checkbox">
                      <svg viewBox="0 0 12 12">
                        <polyline points="2 6 5 9 10 3" />
                      </svg>
                    </span>
                    <span
                      className="label-swatch"
                      style={{ backgroundColor: label.color }}
                    />
                    <span className="label-picker-name">{label.name}</span>
                    {label.icon && <span>{label.icon}</span>}
                  </button>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
});

export default LabelPicker;
