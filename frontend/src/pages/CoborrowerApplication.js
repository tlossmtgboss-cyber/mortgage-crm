import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { coborrowerAPI } from '../services/api';
import './BorrowerApplication.css';
import { toast } from '../utils/toast';

const CoborrowerApplication = () => {
  const { token } = useParams();
  const navigate = useNavigate();

  const [invitation, setInvitation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [formData, setFormData] = useState({
    personal_info: {
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      date_of_birth: '',
      ssn: '',
      marital_status: '',
      dependents: 0,
      citizenship_status: 'us_citizen',
      current_address: {
        street: '',
        city: '',
        state: '',
        zip: '',
        years_at_address: 0,
        months_at_address: 0,
        housing_type: 'rent'
      }
    },
    income: {
      employment_status: 'employed',
      employer_name: '',
      employer_phone: '',
      job_title: '',
      years_employed: 0,
      months_employed: 0,
      monthly_income: '',
      other_income: [],
      self_employed: false
    },
    assets: {
      checking_accounts: [],
      savings_accounts: [],
      investment_accounts: [],
      retirement_accounts: [],
      other_assets: []
    },
    liabilities: {
      credit_cards: [],
      auto_loans: [],
      student_loans: [],
      other_debts: []
    },
    declarations: {
      outstanding_judgments: false,
      bankruptcy: false,
      foreclosure: false,
      lawsuit: false,
      loan_default: false,
      alimony_child_support: false,
      down_payment_borrowed: false,
      comaker_on_note: false,
      us_citizen: true,
      permanent_resident: false,
      primary_residence: true
    },
    credit_auth: {
      authorized: false,
      authorized_at: null,
      ip_address: ''
    }
  });

  // Fetch invitation data
  useEffect(() => {
    const fetchInvitation = async () => {
      try {
        setLoading(true);
        const response = await coborrowerAPI.get(token);
        setInvitation(response);

        // Pre-fill email from invitation
        if (response.email) {
          setFormData(prev => ({
            ...prev,
            personal_info: {
              ...prev.personal_info,
              email: response.email,
              first_name: response.first_name || '',
              last_name: response.last_name || ''
            }
          }));
        }

        // Load existing data if any
        if (response.coborrower_data) {
          setFormData(prev => ({
            ...prev,
            ...response.coborrower_data
          }));
        }

        setError(null);
      } catch (err) {
        console.error('Error fetching invitation:', err);
        if (err.response?.status === 404) {
          setError('This invitation link is invalid or has expired.');
        } else if (err.response?.status === 410) {
          setError('This invitation has already been completed.');
        } else {
          setError('Unable to load the invitation. Please try again or contact the loan officer.');
        }
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      fetchInvitation();
    }
  }, [token]);

  // Auto-save handler
  const autoSave = useCallback(async () => {
    if (!invitation || invitation.status === 'completed') return;

    try {
      setSaving(true);
      await coborrowerAPI.save(token, formData);
    } catch (err) {
      console.error('Auto-save failed:', err);
    } finally {
      setSaving(false);
    }
  }, [token, formData, invitation]);

  // Debounced auto-save on blur
  const handleFieldBlur = () => {
    autoSave();
  };

  const handleInputChange = (section, field, value) => {
    setFormData(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value
      }
    }));
  };

  const handleNestedChange = (section, parent, field, value) => {
    setFormData(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [parent]: {
          ...prev[section][parent],
          [field]: value
        }
      }
    }));
  };

  // Handle credit authorization
  const handleCreditAuth = async () => {
    if (!formData.credit_auth.authorized) {
      toast.error('Please check the authorization box to proceed.');
      return;
    }

    try {
      setSaving(true);
      await coborrowerAPI.creditAuth(token, {
        signature: `${formData.personal_info.first_name} ${formData.personal_info.last_name}`,
        consent_text: 'I authorize the lender to obtain my credit report.',
        ip_address: '' // Will be captured server-side
      });

      setFormData(prev => ({
        ...prev,
        credit_auth: {
          ...prev.credit_auth,
          authorized_at: new Date().toISOString()
        }
      }));

      toast.success('Credit authorization captured successfully.');
    } catch (err) {
      console.error('Credit auth failed:', err);
      toast.error('Failed to capture credit authorization. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Submit co-borrower application
  const handleSubmit = async () => {
    // Validate required fields
    const { personal_info, income, declarations, credit_auth } = formData;

    if (!personal_info.first_name || !personal_info.last_name || !personal_info.email) {
      toast.success('Please complete all required personal information fields.');
      return;
    }

    if (!personal_info.ssn || !personal_info.date_of_birth) {
      toast.error('Please provide your Social Security Number and Date of Birth.');
      return;
    }

    if (!income.monthly_income) {
      toast.error('Please provide your monthly income information.');
      return;
    }

    if (!credit_auth.authorized || !credit_auth.authorized_at) {
      toast.success('Please complete the credit authorization before submitting.');
      return;
    }

    try {
      setSubmitting(true);
      await coborrowerAPI.submit(token);

      // Show success and redirect
      toast.success('Thank you! Your co-borrower information has been submitted successfully.');
      navigate(`/coborrower/${token}/submitted`);
    } catch (err) {
      console.error('Submit failed:', err);
      toast.error('Failed to submit. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="borrower-application">
        <div className="application-loading">
          <div className="loading-spinner"></div>
          <p>Loading your invitation...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="borrower-application">
        <div className="application-error">
          <div className="error-icon">⚠️</div>
          <h2>Unable to Load Invitation</h2>
          <p>{error}</p>
          <p className="error-help">
            If you believe this is an error, please contact the loan officer who sent you this invitation.
          </p>
        </div>
      </div>
    );
  }

  if (invitation?.status === 'completed') {
    return (
      <div className="borrower-application">
        <div className="application-submitted">
          <div className="submitted-icon">✅</div>
          <h2>Already Submitted</h2>
          <p>Your co-borrower information has already been submitted.</p>
          <p>If you need to make changes, please contact the loan officer.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="borrower-application coborrower-application">
      <div className="application-header">
        <h1>Co-Borrower Application</h1>
        <p className="header-subtitle">
          You've been invited to complete your information as a co-borrower on a mortgage application.
        </p>
        {invitation?.borrower_name && (
          <p className="primary-borrower-info">
            Primary Borrower: <strong>{invitation.borrower_name}</strong>
          </p>
        )}
        {saving && <span className="auto-save-indicator">Saving...</span>}
      </div>

      <div className="application-content single-step">
        {/* Personal Information */}
        <section className="form-section">
          <h2>Personal Information</h2>

          <div className="form-row">
            <div className="form-group">
              <label>First Name *</label>
              <input
                type="text"
                value={formData.personal_info.first_name}
                onChange={(e) => handleInputChange('personal_info', 'first_name', e.target.value)}
                onBlur={handleFieldBlur}
                required
              />
            </div>
            <div className="form-group">
              <label>Last Name *</label>
              <input
                type="text"
                value={formData.personal_info.last_name}
                onChange={(e) => handleInputChange('personal_info', 'last_name', e.target.value)}
                onBlur={handleFieldBlur}
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Email *</label>
              <input
                type="email"
                value={formData.personal_info.email}
                onChange={(e) => handleInputChange('personal_info', 'email', e.target.value)}
                onBlur={handleFieldBlur}
                required
              />
            </div>
            <div className="form-group">
              <label>Phone *</label>
              <input
                type="tel"
                value={formData.personal_info.phone}
                onChange={(e) => handleInputChange('personal_info', 'phone', e.target.value)}
                onBlur={handleFieldBlur}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Date of Birth *</label>
              <input
                type="date"
                value={formData.personal_info.date_of_birth}
                onChange={(e) => handleInputChange('personal_info', 'date_of_birth', e.target.value)}
                onBlur={handleFieldBlur}
                required
              />
            </div>
            <div className="form-group">
              <label>Social Security Number *</label>
              <input
                type="password"
                value={formData.personal_info.ssn}
                onChange={(e) => handleInputChange('personal_info', 'ssn', e.target.value)}
                onBlur={handleFieldBlur}
                placeholder="XXX-XX-XXXX"
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Marital Status</label>
              <select
                value={formData.personal_info.marital_status}
                onChange={(e) => handleInputChange('personal_info', 'marital_status', e.target.value)}
                onBlur={handleFieldBlur}
              >
                <option value="">Select...</option>
                <option value="single">Single</option>
                <option value="married">Married</option>
                <option value="separated">Separated</option>
                <option value="divorced">Divorced</option>
                <option value="widowed">Widowed</option>
              </select>
            </div>
            <div className="form-group">
              <label>Number of Dependents</label>
              <input
                type="number"
                min="0"
                value={formData.personal_info.dependents}
                onChange={(e) => handleInputChange('personal_info', 'dependents', parseInt(e.target.value) || 0)}
                onBlur={handleFieldBlur}
              />
            </div>
          </div>

          <h3>Current Address</h3>
          <div className="form-group">
            <label>Street Address</label>
            <input
              type="text"
              value={formData.personal_info.current_address.street}
              onChange={(e) => handleNestedChange('personal_info', 'current_address', 'street', e.target.value)}
              onBlur={handleFieldBlur}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>City</label>
              <input
                type="text"
                value={formData.personal_info.current_address.city}
                onChange={(e) => handleNestedChange('personal_info', 'current_address', 'city', e.target.value)}
                onBlur={handleFieldBlur}
              />
            </div>
            <div className="form-group">
              <label>State</label>
              <input
                type="text"
                value={formData.personal_info.current_address.state}
                onChange={(e) => handleNestedChange('personal_info', 'current_address', 'state', e.target.value)}
                onBlur={handleFieldBlur}
                maxLength="2"
              />
            </div>
            <div className="form-group">
              <label>ZIP Code</label>
              <input
                type="text"
                value={formData.personal_info.current_address.zip}
                onChange={(e) => handleNestedChange('personal_info', 'current_address', 'zip', e.target.value)}
                onBlur={handleFieldBlur}
                maxLength="10"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Years at Address</label>
              <input
                type="number"
                min="0"
                value={formData.personal_info.current_address.years_at_address}
                onChange={(e) => handleNestedChange('personal_info', 'current_address', 'years_at_address', parseInt(e.target.value) || 0)}
                onBlur={handleFieldBlur}
              />
            </div>
            <div className="form-group">
              <label>Housing Type</label>
              <select
                value={formData.personal_info.current_address.housing_type}
                onChange={(e) => handleNestedChange('personal_info', 'current_address', 'housing_type', e.target.value)}
                onBlur={handleFieldBlur}
              >
                <option value="rent">Rent</option>
                <option value="own">Own</option>
                <option value="living_rent_free">Living Rent Free</option>
              </select>
            </div>
          </div>
        </section>

        {/* Income Information */}
        <section className="form-section">
          <h2>Income Information</h2>

          <div className="form-group">
            <label>Employment Status</label>
            <select
              value={formData.income.employment_status}
              onChange={(e) => handleInputChange('income', 'employment_status', e.target.value)}
              onBlur={handleFieldBlur}
            >
              <option value="employed">Employed</option>
              <option value="self_employed">Self-Employed</option>
              <option value="retired">Retired</option>
              <option value="not_employed">Not Employed</option>
            </select>
          </div>

          {(formData.income.employment_status === 'employed' || formData.income.employment_status === 'self_employed') && (
            <>
              <div className="form-row">
                <div className="form-group">
                  <label>Employer Name</label>
                  <input
                    type="text"
                    value={formData.income.employer_name}
                    onChange={(e) => handleInputChange('income', 'employer_name', e.target.value)}
                    onBlur={handleFieldBlur}
                  />
                </div>
                <div className="form-group">
                  <label>Employer Phone</label>
                  <input
                    type="tel"
                    value={formData.income.employer_phone}
                    onChange={(e) => handleInputChange('income', 'employer_phone', e.target.value)}
                    onBlur={handleFieldBlur}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Job Title / Position</label>
                  <input
                    type="text"
                    value={formData.income.job_title}
                    onChange={(e) => handleInputChange('income', 'job_title', e.target.value)}
                    onBlur={handleFieldBlur}
                  />
                </div>
                <div className="form-group">
                  <label>Years Employed</label>
                  <input
                    type="number"
                    min="0"
                    value={formData.income.years_employed}
                    onChange={(e) => handleInputChange('income', 'years_employed', parseInt(e.target.value) || 0)}
                    onBlur={handleFieldBlur}
                  />
                </div>
              </div>
            </>
          )}

          <div className="form-group">
            <label>Gross Monthly Income *</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={formData.income.monthly_income}
              onChange={(e) => handleInputChange('income', 'monthly_income', e.target.value)}
              onBlur={handleFieldBlur}
              placeholder="Before taxes"
              required
            />
          </div>
        </section>

        {/* Declarations */}
        <section className="form-section">
          <h2>Declarations</h2>
          <p className="section-description">
            Please answer the following questions truthfully. Select "Yes" or "No" for each.
          </p>

          <div className="declarations-list">
            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.outstanding_judgments}
                  onChange={(e) => handleInputChange('declarations', 'outstanding_judgments', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Are there any outstanding judgments against you?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.bankruptcy}
                  onChange={(e) => handleInputChange('declarations', 'bankruptcy', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Have you declared bankruptcy within the past 7 years?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.foreclosure}
                  onChange={(e) => handleInputChange('declarations', 'foreclosure', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Have you had property foreclosed upon in the last 7 years?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.lawsuit}
                  onChange={(e) => handleInputChange('declarations', 'lawsuit', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Are you a party to a lawsuit?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.loan_default}
                  onChange={(e) => handleInputChange('declarations', 'loan_default', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Have you directly or indirectly been obligated on any loan which resulted in default?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.alimony_child_support}
                  onChange={(e) => handleInputChange('declarations', 'alimony_child_support', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Are you obligated to pay alimony, child support, or separate maintenance?
              </label>
            </div>

            <div className="declaration-item">
              <label>
                <input
                  type="checkbox"
                  checked={formData.declarations.us_citizen}
                  onChange={(e) => handleInputChange('declarations', 'us_citizen', e.target.checked)}
                  onBlur={handleFieldBlur}
                />
                Are you a U.S. citizen?
              </label>
            </div>

            {!formData.declarations.us_citizen && (
              <div className="declaration-item">
                <label>
                  <input
                    type="checkbox"
                    checked={formData.declarations.permanent_resident}
                    onChange={(e) => handleInputChange('declarations', 'permanent_resident', e.target.checked)}
                    onBlur={handleFieldBlur}
                  />
                  Are you a permanent resident alien?
                </label>
              </div>
            )}
          </div>
        </section>

        {/* Credit Authorization */}
        <section className="form-section credit-auth-section">
          <h2>Credit Authorization</h2>

          <div className="credit-auth-notice">
            <p>
              By authorizing below, you consent to allow the lender to obtain your credit report
              to evaluate your creditworthiness for this mortgage application.
            </p>
          </div>

          <div className="credit-auth-agreement">
            <p className="agreement-text">
              I, <strong>{formData.personal_info.first_name} {formData.personal_info.last_name}</strong>,
              hereby authorize the lender and its designated agents to obtain my credit report
              from one or more consumer reporting agencies. I understand that this authorization
              will be used to evaluate my application for credit.
            </p>
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={formData.credit_auth.authorized}
                onChange={(e) => handleInputChange('credit_auth', 'authorized', e.target.checked)}
              />
              I authorize the lender to obtain my credit report *
            </label>
          </div>

          {formData.credit_auth.authorized && !formData.credit_auth.authorized_at && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleCreditAuth}
              disabled={saving}
            >
              {saving ? 'Processing...' : 'Confirm Authorization'}
            </button>
          )}

          {formData.credit_auth.authorized_at && (
            <div className="credit-auth-confirmed">
              <span className="confirmed-icon">✓</span>
              Credit authorization captured on {new Date(formData.credit_auth.authorized_at).toLocaleDateString()}
            </div>
          )}
        </section>

        {/* Submit Section */}
        <section className="form-section submit-section">
          <div className="submit-notice">
            <p>
              By submitting this form, you certify that all information provided is true
              and complete to the best of your knowledge.
            </p>
          </div>

          <div className="submit-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={autoSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Progress'}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-submit"
              onClick={handleSubmit}
              disabled={submitting || !formData.credit_auth.authorized_at}
            >
              {submitting ? 'Submitting...' : 'Submit Application'}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

export default CoborrowerApplication;
