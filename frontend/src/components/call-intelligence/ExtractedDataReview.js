/**
 * Extracted Data Review Component
 *
 * Side-by-side view of extracted call data and editable form fields.
 * Shows what was extracted from the call with ability to edit before creating application.
 */

import React from 'react';

const ExtractedDataReview = ({
  extractedData,
  formData,
  onUpdateField,
  completeness,
}) => {
  // Field groups for organized display
  const fieldGroups = [
    {
      title: 'Personal Information',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      ),
      fields: [
        { key: 'first_name', label: 'First Name', required: true },
        { key: 'last_name', label: 'Last Name', required: true },
        { key: 'email', label: 'Email', type: 'email', recommended: true },
        { key: 'phone', label: 'Phone', type: 'tel', required: true },
      ],
    },
    {
      title: 'Loan Details',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
          <line x1="1" y1="10" x2="23" y2="10" />
        </svg>
      ),
      fields: [
        { key: 'loan_purpose', label: 'Loan Purpose', recommended: true },
        { key: 'loan_amount', label: 'Loan Amount', type: 'currency', recommended: true },
        { key: 'property_type', label: 'Property Type' },
        { key: 'property_address', label: 'Property Address' },
        { key: 'estimated_value', label: 'Est. Property Value', type: 'currency' },
        { key: 'down_payment', label: 'Down Payment', type: 'currency' },
      ],
    },
    {
      title: 'Financial Information',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="1" x2="12" y2="23" />
          <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
        </svg>
      ),
      fields: [
        { key: 'annual_income', label: 'Annual Income', type: 'currency' },
        { key: 'employment_type', label: 'Employment Type' },
        { key: 'employer_name', label: 'Employer' },
        { key: 'credit_score_range', label: 'Credit Score Range' },
      ],
    },
    {
      title: 'Additional Details',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
      ),
      fields: [
        { key: 'timeline', label: 'Timeline' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ],
    },
  ];

  // Format currency for display
  const formatCurrency = (value) => {
    if (!value) return '';
    const num = parseFloat(String(value).replace(/[,$]/g, ''));
    if (isNaN(num)) return value;
    return num.toLocaleString();
  };

  // Check if field was extracted (has original value)
  const wasExtracted = (key) => {
    return extractedData[key] && extractedData[key].toString().trim() !== '';
  };

  // Render input based on type
  const renderInput = (field) => {
    const value = formData[field.key] || '';
    const extracted = wasExtracted(field.key);

    if (field.type === 'textarea') {
      return (
        <textarea
          value={value}
          onChange={(e) => onUpdateField(field.key, e.target.value)}
          placeholder={`Enter ${field.label.toLowerCase()}...`}
          rows={3}
        />
      );
    }

    if (field.type === 'currency') {
      return (
        <div className="currency-input">
          <span className="currency-symbol">$</span>
          <input
            type="text"
            value={formatCurrency(value)}
            onChange={(e) => onUpdateField(field.key, e.target.value)}
            placeholder="0"
          />
        </div>
      );
    }

    return (
      <input
        type={field.type || 'text'}
        value={value}
        onChange={(e) => onUpdateField(field.key, e.target.value)}
        placeholder={extracted ? '' : `Enter ${field.label.toLowerCase()}...`}
      />
    );
  };

  return (
    <div className="extracted-data-review">
      {/* Completeness Indicator */}
      <div className="completeness-bar">
        <div className="completeness-header">
          <span>Data Completeness</span>
          <span className={`completeness-value ${completeness >= 70 ? 'good' : completeness >= 50 ? 'ok' : 'low'}`}>
            {completeness}%
          </span>
        </div>
        <div className="completeness-track">
          <div
            className={`completeness-fill ${completeness >= 70 ? 'good' : completeness >= 50 ? 'ok' : 'low'}`}
            style={{ width: `${completeness}%` }}
          ></div>
        </div>
        <div className="completeness-hint">
          {completeness < 50 && 'Fill in required fields to continue'}
          {completeness >= 50 && completeness < 70 && 'Add more details for a complete profile'}
          {completeness >= 70 && 'Great! You have enough data to create an application'}
        </div>
      </div>

      {/* Legend */}
      <div className="field-legend">
        <span className="legend-item extracted">
          <span className="legend-dot"></span>
          Extracted from call
        </span>
        <span className="legend-item required">
          <span className="legend-dot"></span>
          Required
        </span>
        <span className="legend-item recommended">
          <span className="legend-dot"></span>
          Recommended
        </span>
      </div>

      {/* Field Groups */}
      <div className="field-groups">
        {fieldGroups.map((group) => (
          <div key={group.title} className="field-group">
            <div className="group-header">
              <span className="group-icon">{group.icon}</span>
              <h4>{group.title}</h4>
            </div>
            <div className="group-fields">
              {group.fields.map((field) => {
                const extracted = wasExtracted(field.key);
                const hasValue = formData[field.key] && formData[field.key].toString().trim() !== '';

                return (
                  <div
                    key={field.key}
                    className={`field-row ${extracted ? 'extracted' : ''} ${field.required ? 'required' : ''} ${field.recommended ? 'recommended' : ''}`}
                  >
                    <div className="field-label">
                      <span className="label-text">{field.label}</span>
                      {field.required && <span className="required-mark">*</span>}
                      {extracted && (
                        <span className="extracted-badge" title="Extracted from call">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </span>
                      )}
                    </div>
                    <div className="field-input">
                      {renderInput(field)}
                      {extracted && !hasValue && (
                        <button
                          className="restore-btn"
                          onClick={() => onUpdateField(field.key, extractedData[field.key])}
                          title="Restore extracted value"
                        >
                          Restore
                        </button>
                      )}
                    </div>
                    {extracted && extractedData[field.key] !== formData[field.key] && hasValue && (
                      <div className="field-original">
                        Original: {extractedData[field.key]}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ExtractedDataReview;
