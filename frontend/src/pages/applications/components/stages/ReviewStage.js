/**
 * ReviewStage - Final review before submission
 * Displays summary of all application data and document checklist
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { useApplication } from '../../contexts/ApplicationContext';
import { useDocumentChecklist, getCategoryLabel } from '../../hooks/useDocumentChecklist';
import { getStages } from '../../config/stageConfig';
import CreditAuthorizationBlock from './CreditAuthorizationBlock';
import EDisclosureBlock from './EDisclosureBlock';
import CalendarBookingStep from './CalendarBookingStep';
import './ReviewStage.css';

// Helper to format currency values
const formatCurrency = (value) => {
  if (!value) return '-';
  const num = parseFloat(String(value).replace(/[^0-9.-]/g, ''));
  if (isNaN(num)) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(num);
};

// Helper to format phone numbers
const formatPhone = (value) => {
  if (!value) return '-';
  const digits = String(value).replace(/\D/g, '');
  if (digits.length !== 10) return value;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
};

// Helper to mask SSN
const maskSSN = (value) => {
  if (!value) return '-';
  const digits = String(value).replace(/\D/g, '');
  if (digits.length < 4) return '***-**-****';
  return `***-**-${digits.slice(-4)}`;
};

// Helper to format address
const formatAddress = (address) => {
  if (!address) return '-';
  if (typeof address === 'string') return address;
  const { street, city, state, zip } = address;
  const parts = [street, city, state, zip].filter(Boolean);
  return parts.join(', ') || '-';
};

// Section summary card component
const SummarySection = ({ title, onEdit, children }) => {
  return (
    <div className="review-section">
      <div className="review-section-header">
        <h3 className="review-section-title">{title}</h3>
        {onEdit && (
          <button className="review-edit-btn" onClick={onEdit}>
            Edit
          </button>
        )}
      </div>
      <div className="review-section-content">
        {children}
      </div>
    </div>
  );
};

// Field display component
const SummaryField = ({ label, value, masked = false }) => {
  const displayValue = masked ? maskSSN(value) : value || '-';
  return (
    <div className="review-field">
      <span className="review-field-label">{label}</span>
      <span className="review-field-value">{displayValue}</span>
    </div>
  );
};

// Document checklist item
const DocumentItem = ({ document, checked, onToggle }) => {
  return (
    <label className="document-item">
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(document.id)}
        className="document-checkbox"
      />
      <div className="document-info">
        <span className="document-name">{document.name}</span>
        <span className="document-description">{document.description}</span>
        {document.required && <span className="document-required">Required</span>}
      </div>
    </label>
  );
};

// Main ReviewStage component
const ReviewStage = ({
  onSubmit,
  onNavigateToStage,
  isSubmitting = false,
  voiceReviewToken = null,
  showCalendar = false,
  orgSlug = null,
  loSlug = null,
  loName = null,
}) => {
  const { state, actions } = useApplication();
  const { formData, applicationType } = state;
  const {
    requiredDocuments,
    documentsByCategory,
    documentCounts,
  } = useDocumentChecklist();

  // Track which documents user has confirmed
  const [confirmedDocs, setConfirmedDocs] = useState({});
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [agreedToCredit, setAgreedToCredit] = useState(false);
  const [agreedToEConsent, setAgreedToEConsent] = useState(false);

  // Voice-review consent state
  const isVoiceReview = !!voiceReviewToken;
  const [creditAuthDone, setCreditAuthDone] = useState(false);
  const [eConsentDone, setEConsentDone] = useState(false);
  const [disclosureData, setDisclosureData] = useState(null);

  // Fetch consent status + disclosure texts for voice-review mode
  useEffect(() => {
    if (!isVoiceReview) return;

    const apiBase = process.env.REACT_APP_API_URL || '';

    // Fetch consent status
    fetch(`${apiBase}/api/v1/pos/consent/${voiceReviewToken}/status`)
      .then(r => r.json())
      .then(data => {
        if (data.credit_auth?.completed) setCreditAuthDone(true);
        if (data.e_consent?.completed) setEConsentDone(true);
      })
      .catch(() => {});

    // Fetch disclosure texts
    fetch(`${apiBase}/api/v1/pos/consent/${voiceReviewToken}/disclosures`)
      .then(r => r.json())
      .then(data => setDisclosureData(data))
      .catch(() => {});
  }, [isVoiceReview, voiceReviewToken]);

  // Get stages for navigation
  const stages = useMemo(
    () => getStages(applicationType),
    [applicationType]
  );

  // Toggle document confirmation
  const toggleDocument = useCallback((docId) => {
    setConfirmedDocs(prev => ({
      ...prev,
      [docId]: !prev[docId],
    }));
  }, []);

  // Check if all required documents are confirmed
  const allRequiredDocsConfirmed = useMemo(() => {
    const requiredDocs = requiredDocuments.filter(d => d.required);
    return requiredDocs.every(d => confirmedDocs[d.id]);
  }, [requiredDocuments, confirmedDocs]);

  // Check if ready to submit
  const canSubmit = useMemo(() => {
    if (isVoiceReview) {
      return agreedToTerms && creditAuthDone && eConsentDone;
    }
    return allRequiredDocsConfirmed && agreedToTerms && agreedToCredit && agreedToEConsent;
  }, [allRequiredDocsConfirmed, agreedToTerms, agreedToCredit, agreedToEConsent, isVoiceReview, creditAuthDone, eConsentDone]);

  // Handle stage navigation
  const handleEditStage = useCallback((stageId) => {
    if (onNavigateToStage) {
      onNavigateToStage(stageId);
    } else {
      actions.setStage(stageId);
    }
  }, [onNavigateToStage, actions]);

  // Handle submission
  const handleSubmit = useCallback(() => {
    if (canSubmit && onSubmit) {
      onSubmit();
    }
  }, [canSubmit, onSubmit]);

  return (
    <div className="review-stage">
      <div className="review-header">
        <h1 className="review-title">Review Your Application</h1>
        <p className="review-subtitle">
          Please review all information below and confirm your document checklist before submitting.
        </p>
      </div>

      <div className="review-content">
        {/* Application Summary */}
        <div className="review-summary">
          {/* Personal Information */}
          <SummarySection
            title="Personal Information"
            onEdit={() => handleEditStage('about_you')}
          >
            <div className="review-fields-grid">
              <SummaryField label="Full Name" value={`${formData.first_name || ''} ${formData.last_name || ''}`} />
              <SummaryField label="Email" value={formData.email} />
              <SummaryField label="Phone" value={formatPhone(formData.phone)} />
              <SummaryField label="Date of Birth" value={formData.date_of_birth} />
              <SummaryField label="SSN" value={formData.ssn} masked />
              <SummaryField label="Citizenship" value={formData.citizenship_status} />
            </div>
            {formData.current_address && (
              <SummaryField label="Current Address" value={formatAddress(formData.current_address)} />
            )}
          </SummarySection>

          {/* Co-Borrower Information (if applicable) */}
          {['2', '3', '4+'].includes(formData.borrower_count) && (
            <SummarySection
              title="Co-Borrower Information"
              onEdit={() => handleEditStage('about_you')}
            >
              <div className="review-fields-grid">
                <SummaryField
                  label="Co-Borrower Name"
                  value={`${formData.coborrower_first_name || ''} ${formData.coborrower_last_name || ''}`}
                />
                <SummaryField label="Co-Borrower Email" value={formData.coborrower_email} />
                <SummaryField label="Co-Borrower Phone" value={formatPhone(formData.coborrower_phone)} />
                <SummaryField label="Co-Borrower SSN" value={formData.coborrower_ssn} masked />
              </div>
            </SummarySection>
          )}

          {/* Property Information */}
          {applicationType === 'purchase' && (
            <SummarySection
              title="New Home Details"
              onEdit={() => handleEditStage('new_home')}
            >
              <div className="review-fields-grid">
                <SummaryField label="Property Type" value={formData.property_type} />
                <SummaryField label="Occupancy" value={formData.occupancy_type} />
                <SummaryField label="Purchase Price" value={formatCurrency(formData.purchase_price)} />
                <SummaryField label="Down Payment" value={formatCurrency(formData.down_payment)} />
              </div>
              {formData.property_address && (
                <SummaryField label="Property Address" value={formatAddress(formData.property_address)} />
              )}
            </SummarySection>
          )}

          {/* Current Mortgage (Refinance) */}
          {applicationType === 'refinance' && (
            <SummarySection
              title="Current Mortgage"
              onEdit={() => handleEditStage('current_mortgage')}
            >
              <div className="review-fields-grid">
                <SummaryField label="Refinance Goal" value={formData.refinance_purpose} />
                <SummaryField label="Current Balance" value={formatCurrency(formData.current_mortgage_balance)} />
                <SummaryField label="Current Rate" value={formData.current_interest_rate ? `${formData.current_interest_rate}%` : '-'} />
                <SummaryField label="Property Value" value={formatCurrency(formData.estimated_property_value)} />
              </div>
              {formData.property_address && (
                <SummaryField label="Property Address" value={formatAddress(formData.property_address)} />
              )}
            </SummarySection>
          )}

          {/* Income Information */}
          <SummarySection
            title="Income & Employment"
            onEdit={() => handleEditStage('income')}
          >
            <div className="review-fields-grid">
              <SummaryField label="Employment Type" value={formData.employment_type} />
              <SummaryField label="Employer" value={formData.employer_name} />
              <SummaryField label="Job Title" value={formData.job_title} />
              <SummaryField label="Monthly Income" value={formatCurrency(formData.monthly_income)} />
              <SummaryField label="Years at Job" value={formData.years_at_job ? `${formData.years_at_job} years` : '-'} />
            </div>
          </SummarySection>

          {/* Assets Information */}
          <SummarySection
            title="Assets"
            onEdit={() => handleEditStage('assets')}
          >
            <div className="review-fields-grid">
              <SummaryField label="Checking" value={formatCurrency(formData.checking_balance)} />
              <SummaryField label="Savings" value={formatCurrency(formData.savings_balance)} />
              <SummaryField label="Investments" value={formatCurrency(formData.investment_balance)} />
              <SummaryField label="Retirement" value={formatCurrency(formData.retirement_balance)} />
            </div>
            {formData.gift_funds === 'yes' && (
              <div className="review-notice">
                <span className="notice-icon">🎁</span>
                <span>Gift funds will be used for down payment</span>
              </div>
            )}
          </SummarySection>
        </div>
        {/* END .review-summary */}

        {/* Calendar Booking (optional) */}
        {showCalendar && orgSlug && (
          <CalendarBookingStep
            orgSlug={orgSlug}
            loSlug={loSlug}
            loName={loName}
          />
        )}

        {/* Document Checklist */}
        <div className="review-documents">
          <h2 className="documents-title">Document Checklist</h2>
          <p className="documents-subtitle">
            Confirm that you can provide the following documents. You'll upload them after submission.
          </p>

          <div className="documents-summary">
            <span className="docs-count">
              {Object.keys(confirmedDocs).filter(k => confirmedDocs[k]).length} of {documentCounts.required} required documents confirmed
            </span>
          </div>

          {Object.entries(documentsByCategory).map(([category, docs]) => (
            <div key={category} className="document-category">
              <h3 className="category-title">{getCategoryLabel(category)}</h3>
              <div className="document-list">
                {docs.map(doc => (
                  <DocumentItem
                    key={doc.id}
                    document={doc}
                    checked={confirmedDocs[doc.id] || false}
                    onToggle={toggleDocument}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Agreements & Authorizations */}
        <div className="review-agreements">
          <h2 className="agreements-title">Authorizations</h2>

          <label className="agreement-item">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="agreement-checkbox"
            />
            <div className="agreement-text">
              <strong>Terms and Conditions</strong>
              <p>
                I certify that all information provided in this application is true and complete
                to the best of my knowledge. I understand that false statements may result in
                criminal prosecution under federal and state laws.
              </p>
            </div>
          </label>

          {isVoiceReview ? (
            <>
              <CreditAuthorizationBlock
                applicationToken={voiceReviewToken}
                disclosureText={disclosureData?.credit_auth?.text}
                isAuthorized={creditAuthDone}
                onAuthorized={() => setCreditAuthDone(true)}
              />
              <EDisclosureBlock
                applicationToken={voiceReviewToken}
                disclosureData={disclosureData?.e_consent}
                isConsented={eConsentDone}
                onConsented={() => setEConsentDone(true)}
              />
            </>
          ) : (
            <>
              <label className="agreement-item">
                <input
                  type="checkbox"
                  checked={agreedToCredit}
                  onChange={(e) => setAgreedToCredit(e.target.checked)}
                  className="agreement-checkbox"
                />
                <div className="agreement-text">
                  <strong>Credit Authorization</strong>
                  <p>
                    I authorize the lender to obtain my credit report and verify my employment,
                    income, and assets as needed to process this loan application.
                  </p>
                </div>
              </label>

              <label className="agreement-item">
                <input
                  type="checkbox"
                  checked={agreedToEConsent}
                  onChange={(e) => setAgreedToEConsent(e.target.checked)}
                  className="agreement-checkbox"
                />
                <div className="agreement-text">
                  <strong>Electronic Consent</strong>
                  <p>
                    I consent to receive disclosures, notices, and communications electronically
                    at the email address provided in this application.
                  </p>
                </div>
              </label>
            </>
          )}
        </div>

        {/* Submit Button */}
        <div className="review-submit">
          {!canSubmit && (
            <div className="submit-requirements">
              {!isVoiceReview && !allRequiredDocsConfirmed && (
                <p className="requirement">Please confirm all required documents above</p>
              )}
              {!agreedToTerms && (
                <p className="requirement">Please agree to the Terms and Conditions</p>
              )}
              {isVoiceReview ? (
                <>
                  {!creditAuthDone && (
                    <p className="requirement">Please complete the credit authorization above</p>
                  )}
                  {!eConsentDone && (
                    <p className="requirement">Please complete the electronic disclosure consent above</p>
                  )}
                </>
              ) : (
                <>
                  {!agreedToCredit && (
                    <p className="requirement">Please authorize credit check</p>
                  )}
                  {!agreedToEConsent && (
                    <p className="requirement">Please provide electronic consent</p>
                  )}
                </>
              )}
            </div>
          )}

          <button
            className="submit-button"
            onClick={handleSubmit}
            disabled={!canSubmit || isSubmitting}
          >
            {isSubmitting ? 'Submitting...' : 'Submit Application'}
          </button>

          <p className="submit-note">
            After submission, you'll receive an email with instructions to upload your documents
            and next steps in the loan process.
          </p>
        </div>
      </div>
    </div>
  );
};

export default ReviewStage;
