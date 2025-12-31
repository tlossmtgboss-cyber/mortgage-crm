/**
 * IntakeQuestion - Renders a single intake question with appropriate input type
 */

import React from 'react';
import './IntakeQuestion.css';

// Icon mappings for visual pickers
const OPTION_ICONS = {
  // Language icons
  'en-US': '🇺🇸',
  'es-US': '🇲🇽',
  // Property type icons
  'single_family': '🏠',
  'condo': '🏢',
  'townhouse': '🏘️',
  'multi_family': '🏗️',
  'manufactured': '🏭',
  // Loan purpose icons
  'purchase': '🏡',
  'refinance': '💰',
  'cash_out': '💵',
  'heloc': '🏦',
  // Occupancy icons
  'primary': '🏠',
  'second_home': '🏖️',
  'investment': '📈',
  // Yes/No
  'yes': '✓',
  'no': '✗',
  'true': '✓',
  'false': '✗',
};

function IntakeQuestion({ question, value, onChange, onAutoAdvance, error, disabled }) {
  if (!question) return null;

  // Map API response format to component format
  const {
    question_id,
    prompt,
    question_text,
    answer_types = [],
    ui = {},
    options = [],
    context = {},
    required = false,
    validation = {}
  } = question;

  // Determine question type from API format
  const getQuestionType = () => {
    // Check widget first
    if (ui.widget) {
      if (ui.widget === 'language_picker') return 'visual_select';
      if (ui.widget === 'property_type_picker') return 'visual_select';
      if (ui.widget === 'yes_no') return 'yes_no';
      if (ui.widget === 'date_picker') return 'date';
      if (ui.widget === 'currency_input') return 'currency';
    }

    // Check answer_types array
    if (answer_types.includes('single_select') && options.length > 0) {
      return options.length <= 6 ? 'visual_select' : 'select';
    }
    if (answer_types.includes('multi_select')) return 'multi_select';
    if (answer_types.includes('number')) return 'number';
    if (answer_types.includes('currency')) return 'currency';
    if (answer_types.includes('date')) return 'date';
    if (answer_types.includes('email')) return 'email';
    if (answer_types.includes('phone')) return 'phone';
    if (answer_types.includes('boolean') || answer_types.includes('yes_no')) return 'yes_no';

    return 'text';
  };

  const questionType = getQuestionType();
  const displayText = prompt || question_text || context.micro_why || 'Please answer this question';
  const helpText = question.help_text || ui.hint;

  // Render different input types
  const renderInput = () => {
    switch (questionType) {
      case 'visual_select':
        return (
          <div className="intake-visual-options">
            {options.map((opt) => {
              const optValue = typeof opt === 'object' ? opt.value : opt;
              const optLabel = typeof opt === 'object' ? opt.label : opt;
              const optIcon = typeof opt === 'object' ? opt.icon : null;
              const displayIcon = optIcon || OPTION_ICONS[optValue] || OPTION_ICONS[optValue.toLowerCase()];

              return (
                <button
                  key={optValue}
                  type="button"
                  className={`intake-visual-option ${value === optValue ? 'selected' : ''}`}
                  onClick={() => {
                    onChange(optValue);
                    // Auto-advance for single-select
                    if (onAutoAdvance) {
                      onAutoAdvance(optValue);
                    }
                  }}
                  disabled={disabled}
                >
                  {displayIcon && <span className="option-icon">{displayIcon}</span>}
                  <span className="option-label">{optLabel}</span>
                </button>
              );
            })}
          </div>
        );

      case 'select':
        return (
          <div className="intake-options">
            {options.map((opt) => {
              const optValue = typeof opt === 'object' ? opt.value : opt;
              const optLabel = typeof opt === 'object' ? opt.label : opt;

              return (
                <button
                  key={optValue}
                  type="button"
                  className={`intake-option ${value === optValue ? 'selected' : ''}`}
                  onClick={() => {
                    onChange(optValue);
                    // Auto-advance for single-select
                    if (onAutoAdvance) {
                      onAutoAdvance(optValue);
                    }
                  }}
                  disabled={disabled}
                >
                  {optLabel}
                </button>
              );
            })}
          </div>
        );

      case 'text':
        return (
          <textarea
            id={question_id}
            className="intake-input intake-textarea"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type your answer..."
            disabled={disabled}
            rows={3}
          />
        );

      case 'number':
      case 'currency':
        return (
          <div className="intake-input-wrapper">
            {questionType === 'currency' && (
              <span className="input-prefix">$</span>
            )}
            <input
              type="number"
              id={question_id}
              className={`intake-input ${questionType === 'currency' ? 'with-prefix' : ''}`}
              value={value || ''}
              onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
              placeholder={questionType === 'currency' ? '0.00' : '0'}
              disabled={disabled}
              min={validation.min}
              max={validation.max}
              step={questionType === 'currency' ? '0.01' : '1'}
            />
          </div>
        );

      case 'multi_select':
        return (
          <div className="intake-checkboxes">
            {options.map((opt) => {
              const optValue = typeof opt === 'object' ? opt.value : opt;
              const optLabel = typeof opt === 'object' ? opt.label : opt;
              const isChecked = Array.isArray(value) && value.includes(optValue);

              return (
                <label key={optValue} className="intake-checkbox">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => {
                      const newValue = Array.isArray(value) ? [...value] : [];
                      if (e.target.checked) {
                        newValue.push(optValue);
                      } else {
                        const idx = newValue.indexOf(optValue);
                        if (idx > -1) newValue.splice(idx, 1);
                      }
                      onChange(newValue);
                    }}
                    disabled={disabled}
                  />
                  <span className="checkbox-label">{optLabel}</span>
                </label>
              );
            })}
          </div>
        );

      case 'date':
        return (
          <input
            type="date"
            id={question_id}
            className="intake-input"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            min={validation.min}
            max={validation.max}
          />
        );

      case 'email':
        return (
          <input
            type="email"
            id={question_id}
            className="intake-input"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="email@example.com"
            disabled={disabled}
          />
        );

      case 'phone':
        return (
          <input
            type="tel"
            id={question_id}
            className="intake-input"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="(555) 555-5555"
            disabled={disabled}
          />
        );

      case 'yes_no':
      case 'boolean':
        return (
          <div className="intake-options intake-yes-no">
            <button
              type="button"
              className={`intake-option ${value === true || value === 'yes' ? 'selected' : ''}`}
              onClick={() => {
                onChange(true);
                if (onAutoAdvance) onAutoAdvance(true);
              }}
              disabled={disabled}
            >
              Yes
            </button>
            <button
              type="button"
              className={`intake-option ${value === false || value === 'no' ? 'selected' : ''}`}
              onClick={() => {
                onChange(false);
                if (onAutoAdvance) onAutoAdvance(false);
              }}
              disabled={disabled}
            >
              No
            </button>
          </div>
        );

      default:
        return (
          <input
            type="text"
            id={question_id}
            className="intake-input"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type your answer..."
            disabled={disabled}
          />
        );
    }
  };

  return (
    <div className="intake-question">
      <div className="question-header">
        <label htmlFor={question_id} className="question-text">
          {displayText}
          {required && <span className="required-indicator">*</span>}
        </label>
        {helpText && (
          <p className="question-help">{helpText}</p>
        )}
      </div>

      <div className="question-input">
        {renderInput()}
      </div>

      {error && (
        <div className="question-error">
          {error}
        </div>
      )}
    </div>
  );
}

export default IntakeQuestion;
