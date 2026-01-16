import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import './PurchasePreQualForm.css';

// API Base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Field options
const CREDIT_SCORE_RANGES = [
  { value: '760+', label: '760+ (Excellent)' },
  { value: '720-759', label: '720-759 (Very Good)' },
  { value: '680-719', label: '680-719 (Good)' },
  { value: '640-679', label: '640-679 (Fair)' },
  { value: '620-639', label: '620-639 (Below Average)' },
  { value: 'below-620', label: 'Below 620' },
  { value: 'unknown', label: "I don't know" }
];

const DEROGATORY_EVENTS = [
  { value: 'none', label: 'None' },
  { value: 'bankruptcy', label: 'Bankruptcy' },
  { value: 'foreclosure', label: 'Foreclosure' },
  { value: 'short-sale', label: 'Short Sale' },
  { value: 'deed-in-lieu', label: 'Deed in Lieu' },
  { value: 'late-payments', label: 'Recent Late Payments (30+ days)' }
];

const EMPLOYMENT_TYPES = [
  { value: 'w2-employee', label: 'W2 Employee' },
  { value: 'self-employed', label: 'Self-Employed' },
  { value: 'business-owner', label: 'Business Owner' },
  { value: '1099-contractor', label: '1099 Contractor' },
  { value: 'retired', label: 'Retired' },
  { value: 'other', label: 'Other' }
];

const INCOME_RANGES = [
  { value: 'under-50k', label: 'Under $50,000' },
  { value: '50k-75k', label: '$50,000 - $75,000' },
  { value: '75k-100k', label: '$75,000 - $100,000' },
  { value: '100k-150k', label: '$100,000 - $150,000' },
  { value: '150k-200k', label: '$150,000 - $200,000' },
  { value: '200k-300k', label: '$200,000 - $300,000' },
  { value: '300k-plus', label: '$300,000+' }
];

const DOWN_PAYMENT_RANGES = [
  { value: '0-3', label: '0-3%' },
  { value: '3-5', label: '3-5%' },
  { value: '5-10', label: '5-10%' },
  { value: '10-20', label: '10-20%' },
  { value: '20-plus', label: '20% or more' }
];

const FUND_SOURCES = [
  { value: 'savings', label: 'Personal Savings' },
  { value: 'gift', label: 'Gift from Family' },
  { value: '401k', label: '401(k)/IRA' },
  { value: 'stock-sale', label: 'Stock/Investment Sale' },
  { value: 'home-sale', label: 'Home Sale Proceeds' },
  { value: 'other', label: 'Other' }
];

const TIMELINE_OPTIONS = [
  { value: 'asap', label: 'ASAP - Found a home' },
  { value: '30-days', label: 'Within 30 days' },
  { value: '60-days', label: '1-2 months' },
  { value: '90-days', label: '2-3 months' },
  { value: '6-months', label: '3-6 months' },
  { value: 'just-exploring', label: 'Just exploring options' }
];

const MARITAL_STATUS_OPTIONS = [
  { value: 'single', label: 'Single' },
  { value: 'married', label: 'Married' },
  { value: 'separated', label: 'Separated' },
  { value: 'divorced', label: 'Divorced' },
  { value: 'widowed', label: 'Widowed' }
];

function PurchasePreQualForm({ embedded = false, partnerId, realtorEmail, onSuccess }) {
  const [searchParams] = useSearchParams();
  const urlPartnerId = searchParams.get('partner_id') || partnerId;
  const urlRealtorEmail = searchParams.get('realtor_email') || realtorEmail;
  const urlSource = searchParams.get('source') || 'direct';

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [submissionResult, setSubmissionResult] = useState(null);

  // Calendar state
  const [showCalendar, setShowCalendar] = useState(false);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [loadingSlots, setLoadingSlots] = useState(false);

  // Form data
  const [formData, setFormData] = useState({
    // Buyer Identity
    firstName: '',
    lastName: '',
    mobilePhone: '',
    email: '',
    dateOfBirth: '',
    maritalStatus: '',

    // Property & Goals
    targetPurchasePrice: '',
    targetCity: '',
    desiredMonthlyPayment: '',
    timeline: '',

    // Credit Snapshot
    creditScoreRange: '',
    derogatoryEvents: [],

    // Employment & Income
    employmentType: '',
    employerName: '',
    yearsInLineOfWork: '',
    incomeRange: '',

    // Assets & Down Payment
    cashAvailable: '',
    downPaymentRange: '',
    fundSources: [],

    // Context
    additionalNotes: '',

    // Authorization
    consentGiven: false,

    // Hidden/tracking
    partnerId: urlPartnerId || '',
    realtorEmail: urlRealtorEmail || '',
    source: urlSource
  });

  // Handle input changes
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;

    if (type === 'checkbox' && name !== 'consentGiven') {
      // Handle multi-select checkboxes
      const fieldName = name.split('-')[0];
      setFormData(prev => ({
        ...prev,
        [fieldName]: checked
          ? [...(prev[fieldName] || []), value]
          : (prev[fieldName] || []).filter(v => v !== value)
      }));
    } else if (type === 'checkbox') {
      setFormData(prev => ({ ...prev, [name]: checked }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }
  };

  // Format phone number
  const formatPhone = (value) => {
    const phone = value.replace(/\D/g, '');
    if (phone.length < 4) return phone;
    if (phone.length < 7) return `(${phone.slice(0, 3)}) ${phone.slice(3)}`;
    return `(${phone.slice(0, 3)}) ${phone.slice(3, 6)}-${phone.slice(6, 10)}`;
  };

  const handlePhoneChange = (e) => {
    const formatted = formatPhone(e.target.value);
    setFormData(prev => ({ ...prev, mobilePhone: formatted }));
  };

  // Format currency
  const formatCurrency = (value) => {
    const num = value.replace(/\D/g, '');
    if (!num) return '';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(num);
  };

  const handleCurrencyChange = (e, fieldName) => {
    const raw = e.target.value.replace(/\D/g, '');
    setFormData(prev => ({ ...prev, [fieldName]: raw }));
  };

  // Fetch available calendar slots
  const fetchCalendarSlots = async () => {
    setLoadingSlots(true);
    try {
      const startDate = new Date();
      const endDate = new Date();
      endDate.setDate(endDate.getDate() + 14);

      const response = await fetch(`${API_BASE}/api/v1/scheduler/public/available-slots`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: startDate.toISOString().split('T')[0],
          end_date: endDate.toISOString().split('T')[0],
          duration_minutes: 30,
          appointment_type: 'pre-qualification-call'
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAvailableSlots(data.available_slots || []);
      }
    } catch (err) {
      console.error('Failed to fetch calendar slots:', err);
    } finally {
      setLoadingSlots(false);
    }
  };

  // Validate current step
  const validateStep = () => {
    switch (step) {
      case 1:
        return formData.firstName && formData.lastName && formData.mobilePhone && formData.email;
      case 2:
        return formData.targetPurchasePrice && formData.targetCity && formData.timeline;
      case 3:
        return formData.creditScoreRange;
      case 4:
        return formData.employmentType && formData.incomeRange;
      case 5:
        return formData.downPaymentRange;
      case 6:
        return formData.consentGiven;
      default:
        return true;
    }
  };

  // Handle form submission
  const handleSubmit = async () => {
    if (!formData.consentGiven) {
      setError('Please agree to the terms to continue.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/prequal/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          // Buyer info
          first_name: formData.firstName,
          last_name: formData.lastName,
          mobile_phone: formData.mobilePhone.replace(/\D/g, ''),
          email: formData.email,
          date_of_birth: formData.dateOfBirth,
          marital_status: formData.maritalStatus,

          // Property goals
          target_purchase_price: parseInt(formData.targetPurchasePrice) || 0,
          target_city: formData.targetCity,
          desired_monthly_payment: parseInt(formData.desiredMonthlyPayment) || 0,
          timeline: formData.timeline,

          // Credit
          credit_score_range: formData.creditScoreRange,
          derogatory_events: formData.derogatoryEvents,

          // Employment
          employment_type: formData.employmentType,
          employer_name: formData.employerName,
          years_in_line_of_work: parseInt(formData.yearsInLineOfWork) || 0,
          income_range: formData.incomeRange,

          // Assets
          cash_available: parseInt(formData.cashAvailable) || 0,
          down_payment_range: formData.downPaymentRange,
          fund_sources: formData.fundSources,

          // Notes
          additional_notes: formData.additionalNotes,

          // Calendar selection
          scheduled_appointment: selectedSlot,

          // Tracking
          partner_id: formData.partnerId,
          realtor_email: formData.realtorEmail,
          source: formData.source,

          // Consent
          consent_given: formData.consentGiven,
          consent_timestamp: new Date().toISOString()
        })
      });

      if (response.ok) {
        const result = await response.json();
        setSubmissionResult(result);
        setSubmitted(true);
        if (onSuccess) onSuccess(result);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to submit application. Please try again.');
      }
    } catch (err) {
      console.error('Submission error:', err);
      setError('Unable to submit application. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  // Progress indicator
  const totalSteps = 6;
  const progressPercentage = (step / totalSteps) * 100;

  // Success screen
  if (submitted) {
    return (
      <div className={`prequal-form ${embedded ? 'embedded' : ''}`}>
        <div className="prequal-success">
          <div className="success-icon">&#10003;</div>
          <h2>Thank You, {formData.firstName}!</h2>
          <p>Your pre-qualification application has been received.</p>

          {selectedSlot && (
            <div className="appointment-confirmation">
              <h3>Your Consultation is Scheduled</h3>
              <p className="appointment-time">
                {new Date(selectedSlot.start_time).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric'
                })} at {new Date(selectedSlot.start_time).toLocaleTimeString('en-US', {
                  hour: 'numeric',
                  minute: '2-digit'
                })}
              </p>
              <p className="appointment-note">
                You'll receive a confirmation email with meeting details shortly.
              </p>
            </div>
          )}

          {!selectedSlot && (
            <p className="next-steps">
              A mortgage specialist will contact you within 24 hours to discuss your options.
            </p>
          )}

          <div className="reference-number">
            Reference: {submissionResult?.reference_id || 'PQ-' + Date.now().toString(36).toUpperCase()}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`prequal-form ${embedded ? 'embedded' : ''}`}>
      {/* Header */}
      <div className="prequal-header">
        <h1>Purchase Pre-Qualification</h1>
        <p>Get pre-qualified in under 3 minutes</p>
      </div>

      {/* Progress Bar */}
      <div className="prequal-progress">
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progressPercentage}%` }} />
        </div>
        <div className="progress-steps">
          {['Identity', 'Property', 'Credit', 'Income', 'Assets', 'Review'].map((label, idx) => (
            <span
              key={idx}
              className={`progress-step ${step > idx ? 'completed' : ''} ${step === idx + 1 ? 'active' : ''}`}
            >
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="prequal-error">
          <span className="error-icon">!</span>
          {error}
        </div>
      )}

      {/* Form Steps */}
      <div className="prequal-content">
        {/* Step 1: Buyer Identity */}
        {step === 1 && (
          <div className="prequal-step">
            <h2>Tell Us About Yourself</h2>

            <div className="form-row">
              <div className="form-group">
                <label>First Name *</label>
                <input
                  type="text"
                  name="firstName"
                  value={formData.firstName}
                  onChange={handleChange}
                  placeholder="John"
                  required
                />
              </div>
              <div className="form-group">
                <label>Last Name *</label>
                <input
                  type="text"
                  name="lastName"
                  value={formData.lastName}
                  onChange={handleChange}
                  placeholder="Smith"
                  required
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Mobile Phone *</label>
                <input
                  type="tel"
                  name="mobilePhone"
                  value={formData.mobilePhone}
                  onChange={handlePhoneChange}
                  placeholder="(555) 123-4567"
                  required
                />
              </div>
              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="john@email.com"
                  required
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Date of Birth</label>
                <input
                  type="date"
                  name="dateOfBirth"
                  value={formData.dateOfBirth}
                  onChange={handleChange}
                />
              </div>
              <div className="form-group">
                <label>Marital Status</label>
                <select
                  name="maritalStatus"
                  value={formData.maritalStatus}
                  onChange={handleChange}
                >
                  <option value="">Select...</option>
                  {MARITAL_STATUS_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Property & Goals */}
        {step === 2 && (
          <div className="prequal-step">
            <h2>Your Home Purchase Goals</h2>

            <div className="form-row">
              <div className="form-group">
                <label>Target Purchase Price *</label>
                <input
                  type="text"
                  name="targetPurchasePrice"
                  value={formData.targetPurchasePrice ? formatCurrency(formData.targetPurchasePrice) : ''}
                  onChange={(e) => handleCurrencyChange(e, 'targetPurchasePrice')}
                  placeholder="$450,000"
                  required
                />
              </div>
              <div className="form-group">
                <label>Target City/Area *</label>
                <input
                  type="text"
                  name="targetCity"
                  value={formData.targetCity}
                  onChange={handleChange}
                  placeholder="Miami, FL"
                  required
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Desired Monthly Payment</label>
                <input
                  type="text"
                  name="desiredMonthlyPayment"
                  value={formData.desiredMonthlyPayment ? formatCurrency(formData.desiredMonthlyPayment) : ''}
                  onChange={(e) => handleCurrencyChange(e, 'desiredMonthlyPayment')}
                  placeholder="$2,500"
                />
              </div>
              <div className="form-group">
                <label>Purchase Timeline *</label>
                <select
                  name="timeline"
                  value={formData.timeline}
                  onChange={handleChange}
                  required
                >
                  <option value="">Select timeline...</option>
                  {TIMELINE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Credit Snapshot */}
        {step === 3 && (
          <div className="prequal-step">
            <h2>Credit Information</h2>

            <div className="form-group">
              <label>Estimated Credit Score Range *</label>
              <div className="radio-group">
                {CREDIT_SCORE_RANGES.map(opt => (
                  <label key={opt.value} className="radio-option">
                    <input
                      type="radio"
                      name="creditScoreRange"
                      value={opt.value}
                      checked={formData.creditScoreRange === opt.value}
                      onChange={handleChange}
                    />
                    <span className="radio-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Any Recent Credit Events? (Select all that apply)</label>
              <div className="checkbox-group">
                {DEROGATORY_EVENTS.map(opt => (
                  <label key={opt.value} className="checkbox-option">
                    <input
                      type="checkbox"
                      name="derogatoryEvents-check"
                      value={opt.value}
                      checked={formData.derogatoryEvents.includes(opt.value)}
                      onChange={handleChange}
                    />
                    <span className="checkbox-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Employment & Income */}
        {step === 4 && (
          <div className="prequal-step">
            <h2>Employment & Income</h2>

            <div className="form-group">
              <label>Employment Type *</label>
              <div className="radio-group">
                {EMPLOYMENT_TYPES.map(opt => (
                  <label key={opt.value} className="radio-option">
                    <input
                      type="radio"
                      name="employmentType"
                      value={opt.value}
                      checked={formData.employmentType === opt.value}
                      onChange={handleChange}
                    />
                    <span className="radio-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Employer Name</label>
                <input
                  type="text"
                  name="employerName"
                  value={formData.employerName}
                  onChange={handleChange}
                  placeholder="Company name"
                />
              </div>
              <div className="form-group">
                <label>Years in Line of Work</label>
                <input
                  type="number"
                  name="yearsInLineOfWork"
                  value={formData.yearsInLineOfWork}
                  onChange={handleChange}
                  placeholder="5"
                  min="0"
                  max="50"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Annual Household Income Range *</label>
              <div className="radio-group">
                {INCOME_RANGES.map(opt => (
                  <label key={opt.value} className="radio-option">
                    <input
                      type="radio"
                      name="incomeRange"
                      value={opt.value}
                      checked={formData.incomeRange === opt.value}
                      onChange={handleChange}
                    />
                    <span className="radio-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Step 5: Assets & Down Payment */}
        {step === 5 && (
          <div className="prequal-step">
            <h2>Assets & Down Payment</h2>

            <div className="form-row">
              <div className="form-group">
                <label>Approximate Cash/Savings Available</label>
                <input
                  type="text"
                  name="cashAvailable"
                  value={formData.cashAvailable ? formatCurrency(formData.cashAvailable) : ''}
                  onChange={(e) => handleCurrencyChange(e, 'cashAvailable')}
                  placeholder="$50,000"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Down Payment Range *</label>
              <div className="radio-group horizontal">
                {DOWN_PAYMENT_RANGES.map(opt => (
                  <label key={opt.value} className="radio-option">
                    <input
                      type="radio"
                      name="downPaymentRange"
                      value={opt.value}
                      checked={formData.downPaymentRange === opt.value}
                      onChange={handleChange}
                    />
                    <span className="radio-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Source of Funds (Select all that apply)</label>
              <div className="checkbox-group horizontal">
                {FUND_SOURCES.map(opt => (
                  <label key={opt.value} className="checkbox-option">
                    <input
                      type="checkbox"
                      name="fundSources-check"
                      value={opt.value}
                      checked={formData.fundSources.includes(opt.value)}
                      onChange={handleChange}
                    />
                    <span className="checkbox-label">{opt.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Additional Context (Optional)</label>
              <textarea
                name="additionalNotes"
                value={formData.additionalNotes}
                onChange={handleChange}
                placeholder="Anything else we should know about your situation?"
                rows="3"
              />
            </div>
          </div>
        )}

        {/* Step 6: Review & Submit */}
        {step === 6 && (
          <div className="prequal-step">
            <h2>Review & Schedule</h2>

            {/* Summary */}
            <div className="review-summary">
              <div className="summary-section">
                <h3>Your Information</h3>
                <p><strong>Name:</strong> {formData.firstName} {formData.lastName}</p>
                <p><strong>Phone:</strong> {formData.mobilePhone}</p>
                <p><strong>Email:</strong> {formData.email}</p>
              </div>

              <div className="summary-section">
                <h3>Purchase Goals</h3>
                <p><strong>Target Price:</strong> {formatCurrency(formData.targetPurchasePrice)}</p>
                <p><strong>Location:</strong> {formData.targetCity}</p>
                <p><strong>Timeline:</strong> {TIMELINE_OPTIONS.find(t => t.value === formData.timeline)?.label}</p>
              </div>

              <div className="summary-section">
                <h3>Financial Snapshot</h3>
                <p><strong>Credit Score:</strong> {CREDIT_SCORE_RANGES.find(c => c.value === formData.creditScoreRange)?.label}</p>
                <p><strong>Employment:</strong> {EMPLOYMENT_TYPES.find(e => e.value === formData.employmentType)?.label}</p>
                <p><strong>Income:</strong> {INCOME_RANGES.find(i => i.value === formData.incomeRange)?.label}</p>
                <p><strong>Down Payment:</strong> {DOWN_PAYMENT_RANGES.find(d => d.value === formData.downPaymentRange)?.label}</p>
              </div>
            </div>

            {/* Calendar Booking */}
            <div className="calendar-section">
              <h3>Schedule Your Consultation (Optional)</h3>
              <p>Book a time to speak with a mortgage specialist</p>

              {!showCalendar ? (
                <button
                  type="button"
                  className="btn-schedule"
                  onClick={() => {
                    setShowCalendar(true);
                    fetchCalendarSlots();
                  }}
                >
                  Choose a Time
                </button>
              ) : (
                <div className="calendar-picker">
                  {loadingSlots ? (
                    <div className="loading-slots">Loading available times...</div>
                  ) : availableSlots.length > 0 ? (
                    <div className="slots-grid">
                      {availableSlots.slice(0, 12).map((slot, idx) => (
                        <button
                          key={idx}
                          type="button"
                          className={`slot-btn ${selectedSlot === slot ? 'selected' : ''}`}
                          onClick={() => setSelectedSlot(slot)}
                        >
                          <span className="slot-date">
                            {new Date(slot.start_time).toLocaleDateString('en-US', {
                              weekday: 'short',
                              month: 'short',
                              day: 'numeric'
                            })}
                          </span>
                          <span className="slot-time">
                            {new Date(slot.start_time).toLocaleTimeString('en-US', {
                              hour: 'numeric',
                              minute: '2-digit'
                            })}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="no-slots">No available times found. We'll contact you to schedule.</p>
                  )}

                  {selectedSlot && (
                    <div className="selected-time">
                      Selected: {new Date(selectedSlot.start_time).toLocaleDateString('en-US', {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric'
                      })} at {new Date(selectedSlot.start_time).toLocaleTimeString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit'
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Consent */}
            <div className="consent-section">
              <label className="consent-checkbox">
                <input
                  type="checkbox"
                  name="consentGiven"
                  checked={formData.consentGiven}
                  onChange={handleChange}
                  required
                />
                <span className="consent-text">
                  I authorize the lender to pull my credit report and verify the information provided.
                  I understand this is a soft pull that will not affect my credit score.
                  I consent to receive calls, texts, and emails regarding my mortgage inquiry.
                </span>
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Navigation Buttons */}
      <div className="prequal-navigation">
        {step > 1 && (
          <button
            type="button"
            className="btn-back"
            onClick={() => setStep(step - 1)}
            disabled={loading}
          >
            Back
          </button>
        )}

        {step < totalSteps ? (
          <button
            type="button"
            className="btn-next"
            onClick={() => setStep(step + 1)}
            disabled={!validateStep()}
          >
            Continue
          </button>
        ) : (
          <button
            type="button"
            className="btn-submit"
            onClick={handleSubmit}
            disabled={loading || !formData.consentGiven}
          >
            {loading ? 'Submitting...' : 'Submit Application'}
          </button>
        )}
      </div>

      {/* Footer */}
      <div className="prequal-footer">
        <p>Your information is secure and encrypted</p>
        <div className="security-badges">
          <span className="badge">256-bit SSL</span>
          <span className="badge">Bank-Level Security</span>
        </div>
      </div>
    </div>
  );
}

export default PurchasePreQualForm;
