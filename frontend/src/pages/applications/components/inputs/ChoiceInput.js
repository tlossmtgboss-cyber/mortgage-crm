/**
 * ChoiceInput - Card-based single/multi select component
 * Used for single-choice and multi-choice question types
 */

import React from 'react';
import './ChoiceInput.css';

const ChoiceInput = ({
  options = [],
  value,
  onChange,
  multiple = false,
  columns = 2,
  disabled = false,
  error,
  className = '',
}) => {
  // Handle selection
  const handleSelect = (optionValue) => {
    if (disabled) return;

    if (multiple) {
      // Multi-select: toggle the option
      const currentValues = Array.isArray(value) ? value : [];
      const newValues = currentValues.includes(optionValue)
        ? currentValues.filter(v => v !== optionValue)
        : [...currentValues, optionValue];
      onChange(newValues);
    } else {
      // Single-select: set the value
      onChange(optionValue);
    }
  };

  // Check if an option is selected
  const isSelected = (optionValue) => {
    if (multiple) {
      return Array.isArray(value) && value.includes(optionValue);
    }
    return value === optionValue;
  };

  // Get icon component
  const renderIcon = (icon) => {
    if (!icon) return null;

    // Map icon names to emoji/icons
    const iconMap = {
      'user': '👤',
      'users': '👥',
      'home': '🏠',
      'building': '🏢',
      'buildings': '🏘️',
      'townhouse': '🏘️',
      'factory': '🏭',
      'medal': '🎖️',
      'shield': '🛡️',
      'briefcase': '💼',
      'store': '🏪',
      'document': '📄',
      'umbrella': '☂️',
      'pause': '⏸️',
      'dollar': '💵',
      'cash': '💰',
      'trending-down': '📉',
      'clock': '⏰',
      'user-minus': '👤➖',
      'x': '✕',
      'check': '✓',
      'calendar': '📅',
      'chart': '📊',
      'clipboard': '📋',
      'bank': '🏦',
    };

    return (
      <span className="choice-icon">
        {iconMap[icon] || icon}
      </span>
    );
  };

  return (
    <div
      className={`choice-input choice-input--cols-${columns} ${className} ${error ? 'has-error' : ''}`}
      role={multiple ? 'group' : 'radiogroup'}
    >
      <div className="choice-options">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`choice-option ${isSelected(option.value) ? 'selected' : ''} ${disabled ? 'disabled' : ''}`}
            onClick={() => handleSelect(option.value)}
            disabled={disabled}
            role={multiple ? 'checkbox' : 'radio'}
            aria-checked={isSelected(option.value)}
            aria-label={option.label}
          >
            <div className="choice-option-content">
              {option.icon && renderIcon(option.icon)}
              <span className="choice-label">{option.label}</span>
              {option.description && (
                <span className="choice-description">{option.description}</span>
              )}
            </div>
            <div className="choice-indicator">
              {isSelected(option.value) && (
                <span className="choice-checkmark">✓</span>
              )}
            </div>
          </button>
        ))}
      </div>

      {error && <div className="choice-error">{error}</div>}
    </div>
  );
};

export default ChoiceInput;
