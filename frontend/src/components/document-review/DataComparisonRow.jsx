/**
 * DataComparisonRow
 *
 * Single field comparison row showing extracted vs existing value.
 * Allows user to choose action: keep current, use extracted, or ignore.
 */

import React from 'react';
import './DataComparisonRow.css';

const DataComparisonRow = ({
  fieldName,
  label,
  extractedValue,
  currentValue,
  confidence,
  provenance,
  selectedAction,
  onActionSelect,
  isConflict,
  isNew,
}) => {
  const formatValue = (value) => {
    if (value === null || value === undefined || value === '') {
      return <span className="empty-value">—</span>;
    }
    if (typeof value === 'number') {
      // Format currency if it looks like money
      if (fieldName.toLowerCase().includes('amount') ||
          fieldName.toLowerCase().includes('income') ||
          fieldName.toLowerCase().includes('pay') ||
          fieldName.toLowerCase().includes('balance')) {
        return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      }
      return value.toLocaleString();
    }
    if (typeof value === 'boolean') {
      return value ? 'Yes' : 'No';
    }
    return String(value);
  };

  const getConfidenceClass = (conf) => {
    if (!conf) return '';
    if (conf >= 80) return 'high';
    if (conf >= 60) return 'medium';
    return 'low';
  };

  const getStatusClass = () => {
    if (isConflict) return 'conflict';
    if (isNew) return 'new';
    return 'match';
  };

  const hasExtractedValue = extractedValue !== null && extractedValue !== undefined && extractedValue !== '';
  const hasCurrentValue = currentValue !== null && currentValue !== undefined && currentValue !== '';

  return (
    <div className={`comparison-row ${getStatusClass()} ${selectedAction ? `action-${selectedAction}` : ''}`}>
      {/* Field Label */}
      <div className="row-label">
        <span className="label-text">{label}</span>
        {confidence && (
          <span
            className={`confidence-indicator ${getConfidenceClass(confidence)}`}
            title={`${confidence}% confidence`}
          >
            {confidence}%
          </span>
        )}
      </div>

      {/* Values Comparison */}
      <div className="row-values">
        {/* Current Value */}
        <div className={`value-cell current ${selectedAction === 'keep' ? 'selected' : ''}`}>
          <span className="value-label">Current</span>
          <span className="value-content">{formatValue(currentValue)}</span>
        </div>

        {/* Arrow/Indicator */}
        <div className="value-indicator">
          {isConflict && <span className="conflict-icon">≠</span>}
          {isNew && <span className="new-icon">+</span>}
          {!isConflict && !isNew && hasExtractedValue && hasCurrentValue && (
            <span className="match-icon">✓</span>
          )}
        </div>

        {/* Extracted Value */}
        <div className={`value-cell extracted ${selectedAction === 'replace' || selectedAction === 'add' ? 'selected' : ''}`}>
          <span className="value-label">Extracted</span>
          <span className="value-content">{formatValue(extractedValue)}</span>
          {provenance && (
            <span className="provenance" title={provenance}>
              📄
            </span>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="row-actions">
        {isConflict && (
          <>
            <button
              type="button"
              className={`action-btn keep ${selectedAction === 'keep' ? 'active' : ''}`}
              onClick={() => onActionSelect(fieldName, 'keep')}
              title="Keep current value"
            >
              Keep
            </button>
            <button
              type="button"
              className={`action-btn replace ${selectedAction === 'replace' ? 'active' : ''}`}
              onClick={() => onActionSelect(fieldName, 'replace')}
              title="Replace with extracted value"
            >
              Replace
            </button>
          </>
        )}

        {isNew && (
          <>
            <button
              type="button"
              className={`action-btn add ${selectedAction === 'add' ? 'active' : ''}`}
              onClick={() => onActionSelect(fieldName, 'add')}
              title="Add extracted value"
            >
              Add
            </button>
            <button
              type="button"
              className={`action-btn ignore ${selectedAction === 'ignore' ? 'active' : ''}`}
              onClick={() => onActionSelect(fieldName, 'ignore')}
              title="Ignore this field"
            >
              Ignore
            </button>
          </>
        )}

        {!isConflict && !isNew && hasExtractedValue && hasCurrentValue && (
          <span className="match-label">Match</span>
        )}
      </div>
    </div>
  );
};

export default DataComparisonRow;
