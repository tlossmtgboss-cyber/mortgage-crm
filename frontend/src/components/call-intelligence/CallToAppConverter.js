/**
 * Call to Application Converter Component
 *
 * Modal for converting call data into a loan application.
 * Features:
 * - Extract borrower data from call artifacts
 * - Side-by-side view of extracted data and form fields
 * - Edit extracted values before creating
 * - Create lead or loan with pre-filled data
 */

import React, { useState, useMemo } from 'react';
import { toast } from '../../utils/toast';
import { leadsAPI, loansAPI, callMonitoringAPI } from '../../services/api';
import ExtractedDataReview from './ExtractedDataReview';

const CallToAppConverter = ({
  session,
  reviewData,
  onClose,
  onSuccess,
}) => {
  const [step, setStep] = useState(1); // 1: Review, 2: Create
  const [createType, setCreateType] = useState('lead'); // 'lead' or 'loan'
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Extract data from artifacts
  const extractedData = useMemo(() => {
    const data = {
      // Personal info
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      // Loan info
      loan_purpose: '',
      loan_amount: '',
      property_type: '',
      property_address: '',
      estimated_value: '',
      down_payment: '',
      // Financial info
      annual_income: '',
      employment_type: '',
      employer_name: '',
      credit_score_range: '',
      // Additional
      timeline: '',
      notes: '',
    };

    // Extract from session metadata
    if (session.metadata) {
      data.first_name = session.metadata.caller_name?.split(' ')[0] || '';
      data.last_name = session.metadata.caller_name?.split(' ').slice(1).join(' ') || '';
      data.phone = session.metadata.phone || '';
      data.email = session.metadata.email || '';
      data.loan_purpose = session.metadata.loan_purpose || '';
      data.loan_amount = session.metadata.loan_amount || '';
    }

    // Extract from intake_field artifacts
    const intakeFields = reviewData?.artifacts?.filter(
      a => a.artifact_type === 'intake_field'
    ) || [];

    intakeFields.forEach(artifact => {
      const fieldData = artifact.structured_data || {};
      const fieldName = fieldData.field_name?.toLowerCase().replace(/\s+/g, '_');
      const value = fieldData.value;

      if (!value) return;

      // Map common field names
      const fieldMap = {
        'first_name': 'first_name',
        'last_name': 'last_name',
        'email': 'email',
        'phone': 'phone',
        'loan_amount': 'loan_amount',
        'loan_purpose': 'loan_purpose',
        'property_type': 'property_type',
        'property_address': 'property_address',
        'estimated_value': 'estimated_value',
        'down_payment': 'down_payment',
        'annual_income': 'annual_income',
        'employment_type': 'employment_type',
        'employer': 'employer_name',
        'employer_name': 'employer_name',
        'credit_score': 'credit_score_range',
        'credit_score_range': 'credit_score_range',
        'timeline': 'timeline',
      };

      if (fieldMap[fieldName]) {
        data[fieldMap[fieldName]] = value;
      }
    });

    // Extract from summary artifact
    const summary = reviewData?.artifacts?.find(
      a => a.artifact_type === 'summary'
    )?.structured_data;

    if (summary) {
      if (summary.loan_details) {
        data.loan_purpose = data.loan_purpose || summary.loan_details.purpose;
        data.loan_amount = data.loan_amount || summary.loan_details.amount;
        data.property_type = data.property_type || summary.loan_details.property_type;
      }
      if (summary.borrower_profile) {
        data.employment_type = data.employment_type || summary.borrower_profile.employment;
        data.credit_score_range = data.credit_score_range || summary.borrower_profile.credit_range;
      }
    }

    return data;
  }, [session, reviewData]);

  // Editable form data
  const [formData, setFormData] = useState(extractedData);

  // Update form field
  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Calculate completeness
  const requiredFields = ['first_name', 'last_name', 'phone'];
  const recommendedFields = ['email', 'loan_purpose', 'loan_amount'];
  const filledRequired = requiredFields.filter(f => formData[f]).length;
  const filledRecommended = recommendedFields.filter(f => formData[f]).length;
  const completeness = Math.round(
    ((filledRequired / requiredFields.length) * 70 +
      (filledRecommended / recommendedFields.length) * 30)
  );

  // Handle create
  const handleCreate = async () => {
    // Validate required fields
    if (!formData.first_name || !formData.last_name) {
      toast.error('First and last name are required');
      return;
    }
    if (!formData.phone && !formData.email) {
      toast.error('Phone or email is required');
      return;
    }

    setIsSubmitting(true);
    try {
      if (createType === 'lead') {
        // Create lead
        await leadsAPI.create({
          first_name: formData.first_name,
          last_name: formData.last_name,
          email: formData.email,
          phone: formData.phone,
          source: 'call_conversion',
          status: 'new',
          loan_purpose: formData.loan_purpose,
          loan_amount: formData.loan_amount ? parseFloat(formData.loan_amount.replace(/[,$]/g, '')) : null,
          property_type: formData.property_type,
          notes: `Converted from call on ${new Date(session.started_at).toLocaleDateString()}. ${formData.notes || ''}`,
          metadata: {
            call_session_id: session.id,
            extracted_data: formData,
          },
        });
        toast.success('Lead created successfully');
      } else {
        // Create loan
        await loansAPI.create({
          borrower_first_name: formData.first_name,
          borrower_last_name: formData.last_name,
          borrower_email: formData.email,
          borrower_phone: formData.phone,
          loan_purpose: formData.loan_purpose,
          loan_amount: formData.loan_amount ? parseFloat(formData.loan_amount.replace(/[,$]/g, '')) : null,
          property_type: formData.property_type,
          property_address: formData.property_address,
          estimated_value: formData.estimated_value ? parseFloat(formData.estimated_value.replace(/[,$]/g, '')) : null,
          status: 'lead',
          source: 'call_conversion',
          notes: `Converted from call on ${new Date(session.started_at).toLocaleDateString()}. ${formData.notes || ''}`,
        });
        toast.success('Loan application created successfully');
      }

      // Update session with conversion status
      try {
        await callMonitoringAPI.updateSession(session.id, {
          metadata: {
            ...session.metadata,
            converted_to: createType,
            converted_at: new Date().toISOString(),
          },
        });
      } catch (e) {
        console.warn('Could not update session metadata:', e);
      }

      onSuccess();
    } catch (error) {
      console.error('Error creating application:', error);
      toast.error(`Failed to create ${createType}: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="converter-modal-overlay" onClick={onClose}>
      <div className="converter-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="converter-header">
          <div className="converter-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
            <h2>Convert to Application</h2>
          </div>
          <button className="converter-close" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Progress Steps */}
        <div className="converter-steps">
          <div className={`step ${step >= 1 ? 'active' : ''}`}>
            <span className="step-number">1</span>
            <span className="step-label">Review Data</span>
          </div>
          <div className="step-line"></div>
          <div className={`step ${step >= 2 ? 'active' : ''}`}>
            <span className="step-number">2</span>
            <span className="step-label">Create Application</span>
          </div>
        </div>

        {/* Content */}
        <div className="converter-content">
          {step === 1 && (
            <ExtractedDataReview
              extractedData={extractedData}
              formData={formData}
              onUpdateField={updateField}
              completeness={completeness}
            />
          )}

          {step === 2 && (
            <div className="converter-create">
              <div className="create-type-selector">
                <h3>What would you like to create?</h3>
                <div className="type-options">
                  <label className={`type-option ${createType === 'lead' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="createType"
                      value="lead"
                      checked={createType === 'lead'}
                      onChange={() => setCreateType('lead')}
                    />
                    <div className="type-content">
                      <div className="type-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                          <circle cx="12" cy="7" r="4" />
                        </svg>
                      </div>
                      <div className="type-label">Create Lead</div>
                      <div className="type-desc">Add to pipeline for nurturing</div>
                    </div>
                  </label>
                  <label className={`type-option ${createType === 'loan' ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name="createType"
                      value="loan"
                      checked={createType === 'loan'}
                      onChange={() => setCreateType('loan')}
                    />
                    <div className="type-content">
                      <div className="type-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                        </svg>
                      </div>
                      <div className="type-label">Create Loan</div>
                      <div className="type-desc">Start full application</div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Summary Preview */}
              <div className="create-summary">
                <h4>Summary</h4>
                <div className="summary-grid">
                  <div className="summary-item">
                    <span className="summary-label">Name</span>
                    <span className="summary-value">
                      {formData.first_name} {formData.last_name}
                    </span>
                  </div>
                  <div className="summary-item">
                    <span className="summary-label">Contact</span>
                    <span className="summary-value">
                      {formData.phone || formData.email || 'N/A'}
                    </span>
                  </div>
                  {formData.loan_purpose && (
                    <div className="summary-item">
                      <span className="summary-label">Purpose</span>
                      <span className="summary-value">{formData.loan_purpose}</span>
                    </div>
                  )}
                  {formData.loan_amount && (
                    <div className="summary-item">
                      <span className="summary-label">Amount</span>
                      <span className="summary-value">${Number(formData.loan_amount.replace(/[,$]/g, '')).toLocaleString()}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="converter-footer">
          {step === 1 ? (
            <>
              <button className="converter-btn secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                className="converter-btn primary"
                onClick={() => setStep(2)}
                disabled={completeness < 50}
              >
                Continue
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            </>
          ) : (
            <>
              <button
                className="converter-btn secondary"
                onClick={() => setStep(1)}
                disabled={isSubmitting}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
                Back
              </button>
              <button
                className="converter-btn primary"
                onClick={handleCreate}
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <span className="spinner-small"></span>
                    Creating...
                  </>
                ) : (
                  <>
                    Create {createType === 'lead' ? 'Lead' : 'Loan Application'}
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default CallToAppConverter;
