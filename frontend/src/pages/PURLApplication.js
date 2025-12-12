/**
 * PURL Loan Application Form
 *
 * Multi-step loan application form for borrowers accessed via PURL portal.
 * Features:
 * - Auto-save as user types
 * - Progress tracking
 * - Field validation
 * - Step navigation
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import './PURLApplication.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Form steps configuration
const FORM_STEPS = [
  {
    id: 'personal',
    title: 'Personal Information',
    fields: ['borrower_first_name', 'borrower_last_name', 'borrower_email', 'borrower_phone', 'borrower_dob', 'ssn_last4']
  },
  {
    id: 'employment',
    title: 'Employment & Income',
    fields: ['employment_status', 'employer_name', 'job_title', 'years_employed', 'annual_income']
  },
  {
    id: 'loan',
    title: 'Loan Details',
    fields: ['loan_purpose', 'loan_amount', 'down_payment', 'loan_term']
  },
  {
    id: 'property',
    title: 'Property Information',
    fields: ['property_type', 'property_address', 'property_city', 'property_state', 'property_zip']
  },
  {
    id: 'review',
    title: 'Review & Submit',
    fields: []
  }
];

// Field configurations
const FIELD_CONFIG = {
  borrower_first_name: { label: 'First Name', type: 'text', required: true, placeholder: 'Enter your first name' },
  borrower_last_name: { label: 'Last Name', type: 'text', required: true, placeholder: 'Enter your last name' },
  borrower_email: { label: 'Email Address', type: 'email', required: true, placeholder: 'your.email@example.com' },
  borrower_phone: { label: 'Phone Number', type: 'tel', required: true, placeholder: '(555) 123-4567' },
  borrower_dob: { label: 'Date of Birth', type: 'date', required: false },
  ssn_last4: { label: 'Last 4 of SSN', type: 'text', required: false, maxLength: 4, pattern: '[0-9]{4}' },

  employment_status: {
    label: 'Employment Status',
    type: 'select',
    required: false,
    options: [
      { value: '', label: 'Select...' },
      { value: 'employed', label: 'Employed' },
      { value: 'self_employed', label: 'Self-Employed' },
      { value: 'retired', label: 'Retired' },
      { value: 'not_employed', label: 'Not Employed' }
    ]
  },
  employer_name: { label: 'Employer Name', type: 'text', required: false, placeholder: 'Company name' },
  job_title: { label: 'Job Title', type: 'text', required: false, placeholder: 'Your position' },
  years_employed: { label: 'Years at Job', type: 'number', required: false, min: 0, max: 50 },
  annual_income: { label: 'Annual Income', type: 'currency', required: false, placeholder: '75,000' },

  loan_purpose: {
    label: 'Loan Purpose',
    type: 'select',
    required: true,
    options: [
      { value: '', label: 'Select purpose...' },
      { value: 'purchase', label: 'Purchase a Home' },
      { value: 'refinance', label: 'Refinance' },
      { value: 'cash_out', label: 'Cash-Out Refinance' },
      { value: 'construction', label: 'Construction Loan' }
    ]
  },
  loan_amount: { label: 'Loan Amount', type: 'currency', required: true, placeholder: '350,000' },
  down_payment: { label: 'Down Payment', type: 'currency', required: false, placeholder: '70,000' },
  loan_term: {
    label: 'Loan Term',
    type: 'select',
    required: false,
    options: [
      { value: '', label: 'Select term...' },
      { value: '30', label: '30 Years' },
      { value: '20', label: '20 Years' },
      { value: '15', label: '15 Years' },
      { value: '10', label: '10 Years' }
    ]
  },

  property_type: {
    label: 'Property Type',
    type: 'select',
    required: false,
    options: [
      { value: '', label: 'Select type...' },
      { value: 'single_family', label: 'Single Family Home' },
      { value: 'condo', label: 'Condominium' },
      { value: 'townhouse', label: 'Townhouse' },
      { value: 'multi_family', label: 'Multi-Family (2-4 units)' },
      { value: 'manufactured', label: 'Manufactured Home' }
    ]
  },
  property_address: { label: 'Street Address', type: 'text', required: false, placeholder: '123 Main Street' },
  property_city: { label: 'City', type: 'text', required: false, placeholder: 'City' },
  property_state: { label: 'State', type: 'text', required: false, placeholder: 'State' },
  property_zip: { label: 'ZIP Code', type: 'text', required: false, placeholder: '12345', maxLength: 5 }
};

// Currency input component
const CurrencyInput = ({ value, onChange, placeholder, ...props }) => {
  const formatValue = (val) => {
    if (!val) return '';
    const num = parseFloat(val.toString().replace(/[^0-9.]/g, ''));
    if (isNaN(num)) return '';
    return num.toLocaleString('en-US');
  };

  const handleChange = (e) => {
    const rawValue = e.target.value.replace(/[^0-9.]/g, '');
    onChange(rawValue);
  };

  return (
    <div className="currency-input">
      <span className="currency-symbol">$</span>
      <input
        type="text"
        value={formatValue(value)}
        onChange={handleChange}
        placeholder={placeholder}
        {...props}
      />
    </div>
  );
};

// Form field component
const FormField = ({ name, value, onChange, error }) => {
  const config = FIELD_CONFIG[name];
  if (!config) return null;

  const handleChange = (e) => {
    onChange(name, e.target.value);
  };

  const inputProps = {
    id: name,
    name,
    value: value || '',
    onChange: handleChange,
    placeholder: config.placeholder,
    required: config.required,
    maxLength: config.maxLength,
    pattern: config.pattern,
    min: config.min,
    max: config.max
  };

  let inputElement;

  switch (config.type) {
    case 'select':
      inputElement = (
        <select {...inputProps}>
          {config.options.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      );
      break;
    case 'currency':
      inputElement = (
        <CurrencyInput
          value={value}
          onChange={(val) => onChange(name, val)}
          placeholder={config.placeholder}
        />
      );
      break;
    case 'textarea':
      inputElement = <textarea {...inputProps} rows={4} />;
      break;
    default:
      inputElement = <input type={config.type} {...inputProps} />;
  }

  return (
    <div className={`form-field ${error ? 'has-error' : ''}`}>
      <label htmlFor={name}>
        {config.label}
        {config.required && <span className="required">*</span>}
      </label>
      {inputElement}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
};

// Progress indicator component
const ProgressIndicator = ({ steps, currentStep, completeness }) => (
  <div className="progress-indicator">
    <div className="steps-progress">
      {steps.map((step, index) => (
        <div
          key={step.id}
          className={`step-dot ${index <= currentStep ? 'active' : ''} ${index < currentStep ? 'completed' : ''}`}
        >
          {index < currentStep ? '✓' : index + 1}
        </div>
      ))}
    </div>
    <div className="completeness-bar">
      <div className="bar-fill" style={{ width: `${completeness}%` }} />
    </div>
    <div className="completeness-text">{completeness}% Complete</div>
  </div>
);

// Review section component
const ReviewSection = ({ title, fields, data }) => (
  <div className="review-section">
    <h4>{title}</h4>
    <div className="review-grid">
      {fields.map(field => {
        const config = FIELD_CONFIG[field];
        let displayValue = data[field];

        // Format currency values
        if (config?.type === 'currency' && displayValue) {
          displayValue = `$${parseFloat(displayValue).toLocaleString('en-US')}`;
        }

        // Get label from select options
        if (config?.type === 'select' && displayValue) {
          const option = config.options.find(o => o.value === displayValue);
          displayValue = option?.label || displayValue;
        }

        return (
          <div key={field} className="review-item">
            <span className="review-label">{config?.label || field}</span>
            <span className="review-value">{displayValue || '—'}</span>
          </div>
        );
      })}
    </div>
  </div>
);

// Main application component
export default function PURLApplication() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Get token
  const getToken = () => {
    const urlParams = new URLSearchParams(location.search);
    const urlToken = urlParams.get('token');
    if (urlToken) {
      localStorage.setItem(`purl_token_${slug}`, urlToken);
      return urlToken;
    }
    return localStorage.getItem(`purl_token_${slug}`);
  };

  const [token] = useState(getToken);
  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [applicationId, setApplicationId] = useState(null);
  const [completeness, setCompleteness] = useState(0);
  const [error, setError] = useState(null);
  const [lastSaved, setLastSaved] = useState(null);

  // Debounce ref for auto-save
  const saveTimeoutRef = useRef(null);

  // API helper
  const fetchAPI = useCallback(async (endpoint, options = {}) => {
    const response = await fetch(`${API_BASE_URL}/api/purl/workspace/${slug}${endpoint}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      if (response.status === 401) {
        setError('Session expired. Please use your portal link again.');
        throw new Error('Unauthorized');
      }
      const data = await response.json();
      throw new Error(data.detail || 'Request failed');
    }

    return response.json();
  }, [slug, token]);

  // Load existing application
  const loadApplication = useCallback(async () => {
    if (!token) {
      setError('Please use your portal access link to view this page.');
      setLoading(false);
      return;
    }

    try {
      const data = await fetchAPI('/application');
      if (data.application) {
        setFormData(data.application.data || {});
        setApplicationId(data.application.id);
        setCompleteness(data.application.completeness_pct || 0);
      }
      setLoading(false);
    } catch (err) {
      console.error('Failed to load application:', err);
      setError(err.message);
      setLoading(false);
    }
  }, [token, fetchAPI]);

  // Initial load
  useEffect(() => {
    loadApplication();
  }, [loadApplication]);

  // Auto-save function
  const saveApplication = useCallback(async (data) => {
    setSaving(true);
    try {
      const result = await fetchAPI('/application', {
        method: 'POST',
        body: JSON.stringify(data)
      });

      setApplicationId(result.id);
      setCompleteness(result.completeness_pct);
      setLastSaved(new Date());

      if (result.validation_errors?.length > 0) {
        const newErrors = {};
        result.validation_errors.forEach(err => {
          const match = err.match(/Missing required field: (\w+)/);
          if (match) {
            newErrors[match[1]] = 'This field is required';
          }
        });
        // Don't show validation errors while typing
      }

    } catch (err) {
      console.error('Failed to save:', err);
    }
    setSaving(false);
  }, [fetchAPI]);

  // Handle field change with auto-save
  const handleFieldChange = useCallback((field, value) => {
    const newData = { ...formData, [field]: value };
    setFormData(newData);

    // Clear error for this field
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }

    // Debounced auto-save
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveApplication(newData);
    }, 1500);
  }, [formData, errors, saveApplication]);

  // Validate current step
  const validateStep = () => {
    const step = FORM_STEPS[currentStep];
    const newErrors = {};

    step.fields.forEach(field => {
      const config = FIELD_CONFIG[field];
      if (config?.required && !formData[field]) {
        newErrors[field] = 'This field is required';
      }

      // Email validation
      if (field === 'borrower_email' && formData[field]) {
        if (!formData[field].includes('@')) {
          newErrors[field] = 'Please enter a valid email address';
        }
      }

      // Phone validation
      if (field === 'borrower_phone' && formData[field]) {
        const digits = formData[field].replace(/\D/g, '');
        if (digits.length < 10) {
          newErrors[field] = 'Please enter a valid phone number';
        }
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Navigation handlers
  const handleNext = () => {
    if (currentStep === FORM_STEPS.length - 1) return;

    // Save current data immediately
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveApplication(formData);

    if (validateStep()) {
      setCurrentStep(currentStep + 1);
      window.scrollTo(0, 0);
    }
  };

  const handleBack = () => {
    if (currentStep === 0) return;
    setCurrentStep(currentStep - 1);
    window.scrollTo(0, 0);
  };

  // Submit application
  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    try {
      // Final save
      await saveApplication(formData);

      // Submit
      const result = await fetchAPI('/application/submit', {
        method: 'POST'
      });

      // Navigate to portal with success message
      navigate(`/portal/${slug}?submitted=true`, { replace: true });

    } catch (err) {
      console.error('Submit failed:', err);
      setError(err.message || 'Failed to submit application. Please check all required fields.');
      setSubmitting(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="purl-application loading">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading application...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !applicationId) {
    return (
      <div className="purl-application error">
        <div className="error-container">
          <div className="error-icon">⚠️</div>
          <h2>Access Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const currentStepConfig = FORM_STEPS[currentStep];
  const isLastStep = currentStep === FORM_STEPS.length - 1;

  return (
    <div className="purl-application">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <button className="back-to-portal" onClick={() => navigate(`/portal/${slug}`)}>
            ← Back to Portal
          </button>
          <h1>Loan Application</h1>
          <div className="save-status">
            {saving ? (
              <span className="saving">Saving...</span>
            ) : lastSaved ? (
              <span className="saved">✓ Saved</span>
            ) : null}
          </div>
        </div>
      </header>

      {/* Progress */}
      <div className="app-progress">
        <ProgressIndicator
          steps={FORM_STEPS}
          currentStep={currentStep}
          completeness={completeness}
        />
      </div>

      {/* Form */}
      <main className="app-main">
        <div className="form-container">
          <h2>{currentStepConfig.title}</h2>

          {error && (
            <div className="form-error">
              <span className="error-icon">⚠️</span>
              {error}
            </div>
          )}

          {!isLastStep ? (
            <div className="form-fields">
              {currentStepConfig.fields.map(field => (
                <FormField
                  key={field}
                  name={field}
                  value={formData[field]}
                  onChange={handleFieldChange}
                  error={errors[field]}
                />
              ))}
            </div>
          ) : (
            <div className="review-content">
              <p className="review-intro">
                Please review your information below. Click "Submit Application" when you're ready to proceed.
              </p>

              {FORM_STEPS.slice(0, -1).map(step => (
                <ReviewSection
                  key={step.id}
                  title={step.title}
                  fields={step.fields}
                  data={formData}
                />
              ))}

              <div className="consent-section">
                <label className="consent-label">
                  <input type="checkbox" required />
                  <span>
                    I certify that the information provided is true and accurate to the best of my knowledge.
                    I authorize the lender to verify this information.
                  </span>
                </label>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Navigation */}
      <footer className="app-footer">
        <div className="footer-content">
          <button
            className="btn btn-secondary"
            onClick={handleBack}
            disabled={currentStep === 0}
          >
            ← Back
          </button>

          <div className="step-indicator">
            Step {currentStep + 1} of {FORM_STEPS.length}
          </div>

          {!isLastStep ? (
            <button
              className="btn btn-primary"
              onClick={handleNext}
            >
              Continue →
            </button>
          ) : (
            <button
              className="btn btn-primary btn-submit"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? 'Submitting...' : 'Submit Application'}
            </button>
          )}
        </div>
      </footer>
    </div>
  );
}
