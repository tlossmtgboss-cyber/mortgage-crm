import React, { useState, useEffect } from 'react';
import './ApplicationSummaryReview.css';
import { toast } from '../utils/toast';

/**
 * ApplicationSummaryReview - AI-powered summary review before submission
 *
 * Features:
 * - Comprehensive view of all application data
 * - Inline editing capability
 * - AI-generated suggestions for completeness
 * - Validation warnings
 * - Required field highlighting
 */

const SECTIONS = [
  {
    id: 'personal',
    title: 'Personal Information',
    icon: '👤',
    fields: [
      { key: 'firstName', label: 'First Name', required: true },
      { key: 'lastName', label: 'Last Name', required: true },
      { key: 'middleName', label: 'Middle Name' },
      { key: 'suffix', label: 'Suffix' },
      { key: 'email', label: 'Email Address', required: true, type: 'email' },
      { key: 'phone', label: 'Phone Number', required: true, type: 'tel' },
      { key: 'dateOfBirth', label: 'Date of Birth', type: 'date' },
      { key: 'ssn', label: 'Social Security Number', type: 'ssn', sensitive: true },
      { key: 'maritalStatus', label: 'Marital Status' },
      { key: 'citizenshipStatus', label: 'Citizenship Status' },
      { key: 'dependentsCount', label: 'Number of Dependents', type: 'number' },
    ],
  },
  {
    id: 'property',
    title: 'Property Information',
    icon: '🏠',
    fields: [
      { key: 'loanPurpose', label: 'Loan Purpose', required: true },
      { key: 'propertyType', label: 'Property Type', required: true },
      { key: 'occupancy', label: 'Occupancy Type', required: true },
      { key: 'propertyAddress', label: 'Property Address' },
      { key: 'city', label: 'City' },
      { key: 'state', label: 'State' },
      { key: 'zip', label: 'ZIP Code' },
      { key: 'county', label: 'County' },
      { key: 'purchasePrice', label: 'Purchase Price', type: 'currency', required: true },
      { key: 'downPayment', label: 'Down Payment', type: 'currency' },
    ],
  },
  {
    id: 'income',
    title: 'Income & Employment',
    icon: '💼',
    fields: [
      { key: 'employmentType', label: 'Employment Type', required: true },
      { key: 'employerName', label: 'Employer Name', required: true },
      { key: 'employerAddress', label: 'Employer Address' },
      { key: 'employerPhone', label: 'Employer Phone', type: 'tel' },
      { key: 'jobTitle', label: 'Job Title', required: true },
      { key: 'yearsEmployed', label: 'Years at Job', type: 'number' },
      { key: 'monthsEmployed', label: 'Months at Job', type: 'number' },
      { key: 'annualIncome', label: 'Annual Income', type: 'currency', required: true },
      { key: 'monthlyBonus', label: 'Monthly Bonus (avg)', type: 'currency' },
      { key: 'monthlyCommission', label: 'Monthly Commission (avg)', type: 'currency' },
      { key: 'otherIncome', label: 'Other Monthly Income', type: 'currency' },
      { key: 'otherIncomeSource', label: 'Other Income Source' },
      { key: 'creditScoreRange', label: 'Estimated Credit Score' },
    ],
  },
  {
    id: 'assets',
    title: 'Assets',
    icon: '💰',
    fields: [
      { key: 'checkingBalance', label: 'Checking Accounts', type: 'currency' },
      { key: 'savingsBalance', label: 'Savings Accounts', type: 'currency' },
      { key: 'investmentValue', label: 'Investments', type: 'currency' },
      { key: 'retirementValue', label: 'Retirement Accounts', type: 'currency' },
      { key: 'otherAssets', label: 'Other Assets', type: 'currency' },
      { key: 'giftFunds', label: 'Gift Funds', type: 'currency' },
      { key: 'giftSource', label: 'Gift Source' },
    ],
  },
  {
    id: 'liabilities',
    title: 'Liabilities',
    icon: '📊',
    fields: [
      { key: 'monthlyRentMortgage', label: 'Monthly Rent/Mortgage', type: 'currency' },
      { key: 'carPayment', label: 'Auto Loans', type: 'currency' },
      { key: 'studentLoans', label: 'Student Loans', type: 'currency' },
      { key: 'creditCardPayments', label: 'Credit Card Payments', type: 'currency' },
      { key: 'childSupport', label: 'Child Support/Alimony', type: 'currency' },
      { key: 'otherDebts', label: 'Other Debts', type: 'currency' },
    ],
  },
  {
    id: 'declarations',
    title: 'Declarations',
    icon: '📋',
    fields: [
      { key: 'isUsCitizen', label: 'US Citizen', type: 'boolean' },
      { key: 'permanentResident', label: 'Permanent Resident', type: 'boolean' },
      { key: 'hasBankruptcy', label: 'Bankruptcy in last 7 years', type: 'boolean' },
      { key: 'hasForeclosure', label: 'Foreclosure in last 7 years', type: 'boolean' },
      { key: 'hasLawsuit', label: 'Party to lawsuit', type: 'boolean' },
      { key: 'hasDelinquentDebt', label: 'Delinquent federal debt', type: 'boolean' },
      { key: 'willOccupyProperty', label: 'Will occupy property', type: 'boolean' },
    ],
  },
];

const ApplicationSummaryReview = ({
  data = {},
  onDataChange,
  onSubmit,
  onBack,
  isSubmitting = false,
  validationErrors = {},
  aiSuggestions = [],
}) => {
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [expandedSections, setExpandedSections] = useState(
    SECTIONS.reduce((acc, s) => ({ ...acc, [s.id]: true }), {})
  );
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Calculate completion stats
  const getCompletionStats = () => {
    let totalRequired = 0;
    let filledRequired = 0;
    let totalFields = 0;
    let filledFields = 0;

    SECTIONS.forEach(section => {
      section.fields.forEach(field => {
        totalFields++;
        if (data[field.key]) filledFields++;
        if (field.required) {
          totalRequired++;
          if (data[field.key]) filledRequired++;
        }
      });
    });

    return {
      totalRequired,
      filledRequired,
      totalFields,
      filledFields,
      requiredComplete: filledRequired === totalRequired,
      overallPercentage: Math.round((filledFields / totalFields) * 100),
    };
  };

  const stats = getCompletionStats();

  // Format value for display
  const formatValue = (value, type, sensitive = false) => {
    if (value === null || value === undefined || value === '') {
      return <span className="empty-value">Not provided</span>;
    }

    if (sensitive) {
      return '•••••' + String(value).slice(-4);
    }

    switch (type) {
      case 'currency':
        return new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: 0,
        }).format(value);
      case 'boolean':
        return value ? 'Yes' : 'No';
      case 'date':
        return new Date(value).toLocaleDateString();
      case 'tel':
        return formatPhone(value);
      default:
        return formatLabel(String(value));
    }
  };

  const formatPhone = (phone) => {
    const cleaned = String(phone).replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    return phone;
  };

  const formatLabel = (value) => {
    // Convert snake_case to Title Case
    return value
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  };

  // Handle field edit
  const startEditing = (fieldKey, currentValue) => {
    setEditingField(fieldKey);
    setEditValue(currentValue || '');
  };

  const saveEdit = (fieldKey) => {
    if (onDataChange) {
      onDataChange({ ...data, [fieldKey]: editValue });
    }
    setEditingField(null);
    setEditValue('');
  };

  const cancelEdit = () => {
    setEditingField(null);
    setEditValue('');
  };

  // Toggle section expand/collapse
  const toggleSection = (sectionId) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }));
  };

  // Get validation status for field
  const getFieldStatus = (fieldKey, required) => {
    if (validationErrors[fieldKey]) {
      return 'error';
    }
    if (required && !data[fieldKey]) {
      return 'missing';
    }
    if (data[fieldKey]) {
      return 'complete';
    }
    return 'empty';
  };

  // Handle submit
  const handleSubmit = () => {
    if (!stats.requiredComplete) {
      toast.success('Please complete all required fields before submitting.');
      return;
    }
    setShowConfirmation(true);
  };

  const confirmSubmit = () => {
    setShowConfirmation(false);
    if (onSubmit) {
      onSubmit();
    }
  };

  return (
    <div className="summary-review">
      {/* Header */}
      <div className="summary-header">
        <h1>Review Your Application</h1>
        <p>Please review all information carefully before submitting. Click any field to edit.</p>
      </div>

      {/* Progress Stats */}
      <div className="completion-stats">
        <div className="stat-card">
          <div className="stat-value">{stats.overallPercentage}%</div>
          <div className="stat-label">Complete</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.filledRequired}/{stats.totalRequired}</div>
          <div className="stat-label">Required Fields</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.filledFields}</div>
          <div className="stat-label">Fields Filled</div>
        </div>
        {!stats.requiredComplete && (
          <div className="stat-warning">
            <span className="warning-icon">⚠️</span>
            {stats.totalRequired - stats.filledRequired} required field(s) missing
          </div>
        )}
      </div>

      {/* AI Suggestions */}
      {aiSuggestions.length > 0 && (
        <div className="ai-suggestions">
          <div className="suggestions-header">
            <span className="ai-icon">🤖</span>
            <h3>AI Suggestions</h3>
          </div>
          <ul className="suggestions-list">
            {aiSuggestions.map((suggestion, index) => (
              <li key={index} className={`suggestion ${suggestion.type}`}>
                <span className="suggestion-icon">
                  {suggestion.type === 'warning' ? '⚠️' : suggestion.type === 'error' ? '❌' : '💡'}
                </span>
                <span className="suggestion-text">{suggestion.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Sections */}
      <div className="summary-sections">
        {SECTIONS.map(section => (
          <div key={section.id} className="summary-section">
            <div
              className="section-header"
              onClick={() => toggleSection(section.id)}
            >
              <span className="section-icon">{section.icon}</span>
              <h2>{section.title}</h2>
              <span className="section-status">
                {section.fields.filter(f => data[f.key]).length}/{section.fields.length}
              </span>
              <span className={`expand-icon ${expandedSections[section.id] ? 'expanded' : ''}`}>
                ▼
              </span>
            </div>

            {expandedSections[section.id] && (
              <div className="section-fields">
                {section.fields.map(field => {
                  const status = getFieldStatus(field.key, field.required);
                  const isEditing = editingField === field.key;

                  return (
                    <div
                      key={field.key}
                      className={`field-row ${status} ${isEditing ? 'editing' : ''}`}
                    >
                      <div className="field-label">
                        {field.label}
                        {field.required && <span className="required">*</span>}
                      </div>

                      {isEditing ? (
                        <div className="field-edit">
                          {field.type === 'boolean' ? (
                            <select
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value === 'true')}
                              autoFocus
                            >
                              <option value="">Select...</option>
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </select>
                          ) : (
                            <input
                              type={field.type === 'currency' || field.type === 'number' ? 'number' : 'text'}
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveEdit(field.key);
                                if (e.key === 'Escape') cancelEdit();
                              }}
                            />
                          )}
                          <div className="edit-actions">
                            <button className="save-btn" onClick={() => saveEdit(field.key)}>
                              ✓
                            </button>
                            <button className="cancel-btn" onClick={cancelEdit}>
                              ✕
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div
                          className="field-value"
                          onClick={() => startEditing(field.key, data[field.key])}
                        >
                          {formatValue(data[field.key], field.type, field.sensitive)}
                          <span className="edit-icon">✏️</span>
                        </div>
                      )}

                      {validationErrors[field.key] && (
                        <div className="field-error">{validationErrors[field.key]}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="summary-actions">
        <button className="back-btn" onClick={onBack} disabled={isSubmitting}>
          ← Back
        </button>
        <button
          className="submit-btn"
          onClick={handleSubmit}
          disabled={isSubmitting || !stats.requiredComplete}
        >
          {isSubmitting ? 'Submitting...' : 'Submit Application'}
        </button>
      </div>

      {/* Confirmation Modal */}
      {showConfirmation && (
        <div className="confirmation-overlay">
          <div className="confirmation-modal">
            <h2>Confirm Submission</h2>
            <p>
              Please confirm that all information is accurate. By submitting, you certify that:
            </p>
            <ul>
              <li>All information provided is true and accurate</li>
              <li>You authorize us to verify the information</li>
              <li>You agree to our terms and conditions</li>
            </ul>
            <div className="confirmation-actions">
              <button
                className="cancel-btn"
                onClick={() => setShowConfirmation(false)}
              >
                Review Again
              </button>
              <button
                className="confirm-btn"
                onClick={confirmSubmit}
              >
                Confirm & Submit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApplicationSummaryReview;
