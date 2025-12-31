/**
 * IntakeQuestion - Renders a single intake question with appropriate input type
 */

import React from 'react';
import './IntakeQuestion.css';

function IntakeQuestion({ question, value, onChange, error, disabled }) {
  if (!question) return null;

  const {
    question_id,
    question_text,
    question_type = 'text',
    help_text,
    options = [],
    required = false,
    validation = {}
  } = question;

  // Render different input types
  const renderInput = () => {
    switch (question_type) {
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
            {question_type === 'currency' && (
              <span className="input-prefix">$</span>
            )}
            <input
              type="number"
              id={question_id}
              className={`intake-input ${question_type === 'currency' ? 'with-prefix' : ''}`}
              value={value || ''}
              onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
              placeholder={question_type === 'currency' ? '0.00' : '0'}
              disabled={disabled}
              min={validation.min}
              max={validation.max}
              step={question_type === 'currency' ? '0.01' : '1'}
            />
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
                  onClick={() => onChange(optValue)}
                  disabled={disabled}
                >
                  {optLabel}
                </button>
              );
            })}
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
              onClick={() => onChange(true)}
              disabled={disabled}
            >
              Yes
            </button>
            <button
              type="button"
              className={`intake-option ${value === false || value === 'no' ? 'selected' : ''}`}
              onClick={() => onChange(false)}
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
          {question_text}
          {required && <span className="required-indicator">*</span>}
        </label>
        {help_text && (
          <p className="question-help">{help_text}</p>
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
