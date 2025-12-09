import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { publicApplicationAPI, prequalifyAPI } from '../services/api';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import AI1003Concierge from '../components/AI1003Concierge';
import './BorrowerApplication.css';

// Step components
const STEPS = [
  { id: 'personal_info', label: 'Personal Info', icon: '👤' },
  { id: 'coborrower', label: 'Co-Borrower', icon: '👥' },
  { id: 'property', label: 'Property', icon: '🏠' },
  { id: 'income', label: 'Income', icon: '💼' },
  { id: 'assets', label: 'Assets', icon: '💰' },
  { id: 'liabilities', label: 'Liabilities', icon: '📊' },
  { id: 'declarations', label: 'Declarations', icon: '📋' },
  { id: 'documents', label: 'Documents', icon: '📄' },
  { id: 'credit_auth', label: 'Credit Auth', icon: '✓' },
  { id: 'review', label: 'Review', icon: '🔍' },
];

export default function BorrowerApplication() {
  const { token } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [application, setApplication] = useState(null);
  const [currentStep, setCurrentStep] = useState('personal_info');
  const [stepData, setStepData] = useState({});
  const [saving, setSaving] = useState(false);
  const [prequalResult, setPrequalResult] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [useConversationMode, setUseConversationMode] = useState(false);
  const [showModeChoice, setShowModeChoice] = useState(true);

  // Load application data
  const loadApplication = useCallback(async () => {
    try {
      setLoading(true);
      const data = await publicApplicationAPI.get(token);
      setApplication(data);
      setCurrentStep(data.current_step || 'personal_info');
      setStepData(data.step_data || {});
      if (data.prequalification_data) {
        setPrequalResult(data.prequalification_data);
      }
    } catch (err) {
      if (err.response?.status === 410) {
        setError('This application link has expired. Please contact your loan officer for a new link.');
      } else if (err.response?.status === 404) {
        setError('Application not found. Please check your link or contact your loan officer.');
      } else {
        setError('Unable to load application. Please try again later.');
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadApplication();
  }, [loadApplication]);

  // Load documents when on documents step
  useEffect(() => {
    if (currentStep === 'documents' && token) {
      loadDocuments();
    }
  }, [currentStep, token]);

  const loadDocuments = async () => {
    try {
      const docs = await publicApplicationAPI.getDocuments(token);
      setDocuments(docs);
    } catch (err) {
      console.error('Error loading documents:', err);
    }
  };

  // Auto-save data
  const saveStepData = async (step, data, markCompleted = false) => {
    try {
      setSaving(true);
      await publicApplicationAPI.saveStep(token, step, data, markCompleted);
      setStepData(prev => ({ ...prev, [step]: data }));
    } catch (err) {
      console.error('Error saving step data:', err);
    } finally {
      setSaving(false);
    }
  };

  // Navigate to next step
  const goToNextStep = () => {
    const currentIndex = STEPS.findIndex(s => s.id === currentStep);
    if (currentIndex < STEPS.length - 1) {
      const nextStep = STEPS[currentIndex + 1].id;

      // Skip co-borrower step if no co-borrower
      if (nextStep === 'coborrower' && !application?.has_coborrower) {
        setCurrentStep(STEPS[currentIndex + 2].id);
      } else {
        setCurrentStep(nextStep);
      }
    }
  };

  // Navigate to previous step
  const goToPrevStep = () => {
    const currentIndex = STEPS.findIndex(s => s.id === currentStep);
    if (currentIndex > 0) {
      const prevStep = STEPS[currentIndex - 1].id;

      // Skip co-borrower step if no co-borrower
      if (prevStep === 'coborrower' && !application?.has_coborrower) {
        setCurrentStep(STEPS[currentIndex - 2].id);
      } else {
        setCurrentStep(prevStep);
      }
    }
  };

  // Complete current step and move to next
  const completeStep = async (data) => {
    await saveStepData(currentStep, data, true);
    goToNextStep();
  };

  // Calculate pre-qualification
  const calculatePrequal = async (data) => {
    try {
      const result = await publicApplicationAPI.prequalify(token, data);
      setPrequalResult(result);
      return result;
    } catch (err) {
      console.error('Error calculating pre-qualification:', err);
      throw err;
    }
  };

  // Handle document upload
  const handleDocumentUpload = async (file, category) => {
    try {
      setUploading(true);
      await publicApplicationAPI.uploadDocument(token, file, category);
      await loadDocuments();
    } catch (err) {
      console.error('Error uploading document:', err);
    } finally {
      setUploading(false);
    }
  };

  // Handle document delete
  const handleDocumentDelete = async (docId) => {
    try {
      await publicApplicationAPI.deleteDocument(token, docId);
      await loadDocuments();
    } catch (err) {
      console.error('Error deleting document:', err);
    }
  };

  // Capture credit authorization
  const captureCreditAuth = async (data) => {
    try {
      await publicApplicationAPI.captureCreditAuth(token, data);
      await loadApplication();
    } catch (err) {
      console.error('Error capturing credit auth:', err);
      throw err;
    }
  };

  // Submit application
  const submitApplication = async () => {
    try {
      setSaving(true);
      await publicApplicationAPI.submit(token);
      // Reload application to show submitted state
      await loadApplication();
    } catch (err) {
      console.error('Error submitting application:', err);
      throw err;
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="borrower-app-loading">
        <div className="loading-spinner"></div>
        <p>Loading your application...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="borrower-app-error">
        <div className="error-icon">⚠️</div>
        <h2>Unable to Load Application</h2>
        <p>{error}</p>
      </div>
    );
  }

  // Show submitted confirmation if application is already submitted
  if (application?.status === 'submitted' || application?.status === 'under_review') {
    return (
      <div className="borrower-app-submitted">
        <div className="submitted-content">
          <div className="submitted-icon">✅</div>
          <h1>Application Submitted!</h1>
          <p className="submitted-message">
            Thank you for completing your mortgage application. We have received your information
            and will be in touch shortly.
          </p>
          <div className="submitted-details">
            <p><strong>Application ID:</strong> {application.id}</p>
            {application.submitted_at && (
              <p><strong>Submitted:</strong> {new Date(application.submitted_at).toLocaleDateString()}</p>
            )}
            {application.lo_name && (
              <p><strong>Loan Officer:</strong> {application.lo_name}</p>
            )}
          </div>
          <div className="submitted-next-steps">
            <h3>What Happens Next?</h3>
            <ol>
              <li>Our team will review your application</li>
              <li>We may reach out if we need additional information</li>
              <li>You'll receive updates on your application status</li>
            </ol>
          </div>
          <p className="contact-info">
            Questions? Contact your loan officer or call us at the number provided.
          </p>
        </div>
      </div>
    );
  }

  const completedSteps = application?.completed_steps || [];
  const progress = application?.progress_percentage || 0;
  const borrowerName = `${application?.borrower_first_name || ''} ${application?.borrower_last_name || ''}`.trim();
  const apiBaseUrl = process.env.REACT_APP_API_URL || '';

  // Handle data extracted from AI Concierge
  const handleConciergeDataExtracted = (newData) => {
    setStepData(prev => ({ ...prev, ...newData }));
    saveStepData({ ...stepData, ...newData });
  };

  // Handle concierge completion
  const handleConciergeComplete = async (finalData) => {
    setStepData(prev => ({ ...prev, ...finalData }));
    await saveStepData({ ...stepData, ...finalData });
    // Switch to review step
    setCurrentStep('review');
    setUseConversationMode(false);
  };

  // Show mode choice for new applications
  if (showModeChoice && !application?.current_step) {
    return (
      <div className="borrower-application">
        <div className="mode-choice-container">
          <div className="mode-choice-content">
            <h1>Welcome to Your Mortgage Application</h1>
            <p className="mode-choice-subtitle">
              How would you like to complete your application?
            </p>

            <div className="mode-options">
              <div
                className="mode-option conversation"
                onClick={() => {
                  setUseConversationMode(true);
                  setShowModeChoice(false);
                }}
              >
                <div className="mode-icon">🤖</div>
                <h2>AI Concierge</h2>
                <p>Have a conversation with our AI assistant who will guide you through the application step by step.</p>
                <ul className="mode-features">
                  <li>Natural conversation</li>
                  <li>Voice input supported</li>
                  <li>Instant explanations</li>
                </ul>
                <button className="mode-select-btn">Start Conversation</button>
              </div>

              <div
                className="mode-option traditional"
                onClick={() => {
                  setUseConversationMode(false);
                  setShowModeChoice(false);
                }}
              >
                <div className="mode-icon">📝</div>
                <h2>Traditional Form</h2>
                <p>Fill out a structured form at your own pace with all fields visible upfront.</p>
                <ul className="mode-features">
                  <li>See all fields</li>
                  <li>Save and resume</li>
                  <li>Skip around sections</li>
                </ul>
                <button className="mode-select-btn secondary">Use Form</button>
              </div>
            </div>

            <p className="mode-switch-note">
              You can switch between modes at any time during the application.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Show AI Concierge mode
  if (useConversationMode) {
    return (
      <div className="borrower-application concierge-mode">
        <AI1003Concierge
          applicationToken={token}
          existingData={stepData}
          onDataExtracted={handleConciergeDataExtracted}
          onSwitchToForm={() => setUseConversationMode(false)}
          onComplete={handleConciergeComplete}
          borrowerName={borrowerName}
          apiBaseUrl={apiBaseUrl}
        />
      </div>
    );
  }

  return (
    <div className="borrower-application">
      {/* Header */}
      <header className="borrower-app-header">
        <div className="header-content">
          <div className="company-info">
            {application?.company_name && (
              <h1>{application.company_name}</h1>
            )}
            {application?.lo_name && (
              <p className="lo-info">Your Loan Officer: {application.lo_name}</p>
            )}
          </div>
          <div className="progress-info">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress}%` }}></div>
            </div>
            <span className="progress-text">{progress}% Complete</span>
          </div>
        </div>
      </header>

      <div className="borrower-app-container">
        {/* Sidebar with steps */}
        <aside className="step-sidebar">
          <h3>Application Steps</h3>
          <ul className="step-list">
            {STEPS.map((step, index) => {
              // Hide co-borrower step if no co-borrower
              if (step.id === 'coborrower' && !application?.has_coborrower) {
                return null;
              }

              const isCompleted = completedSteps.includes(step.id);
              const isCurrent = currentStep === step.id;
              const isAccessible = isCurrent || isCompleted || index <= STEPS.findIndex(s => s.id === currentStep);

              return (
                <li
                  key={step.id}
                  className={`step-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''} ${!isAccessible ? 'disabled' : ''}`}
                  onClick={() => isAccessible && setCurrentStep(step.id)}
                >
                  <span className="step-icon">
                    {isCompleted ? '✓' : step.icon}
                  </span>
                  <span className="step-label">{step.label}</span>
                </li>
              );
            })}
          </ul>
        </aside>

        {/* Main content */}
        <main className="step-content">
          {saving && (
            <div className="saving-indicator">
              <span>Saving...</span>
            </div>
          )}

          {currentStep === 'personal_info' && (
            <PersonalInfoStep
              data={stepData.personal_info || {}}
              application={application}
              onSave={(data) => saveStepData('personal_info', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'coborrower' && (
            <CoborrowerStep
              data={stepData.coborrower || {}}
              application={application}
              token={token}
              onSave={(data) => saveStepData('coborrower', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'property' && (
            <PropertyStep
              data={stepData.property || {}}
              onSave={(data) => saveStepData('property', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'income' && (
            <IncomeStep
              data={stepData.income || {}}
              onSave={(data) => saveStepData('income', data)}
              onComplete={completeStep}
              calculatePrequal={calculatePrequal}
              prequalResult={prequalResult}
            />
          )}

          {currentStep === 'assets' && (
            <AssetsStep
              data={stepData.assets || {}}
              onSave={(data) => saveStepData('assets', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'liabilities' && (
            <LiabilitiesStep
              data={stepData.liabilities || {}}
              onSave={(data) => saveStepData('liabilities', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'declarations' && (
            <DeclarationsStep
              data={stepData.declarations || {}}
              onSave={(data) => saveStepData('declarations', data)}
              onComplete={completeStep}
            />
          )}

          {currentStep === 'documents' && (
            <DocumentsStep
              documents={documents}
              uploading={uploading}
              onUpload={handleDocumentUpload}
              onDelete={handleDocumentDelete}
              onComplete={() => {
                saveStepData('documents', { uploaded: true }, true);
                goToNextStep();
              }}
            />
          )}

          {currentStep === 'credit_auth' && (
            <CreditAuthStep
              captured={application?.credit_auth_captured}
              onCapture={captureCreditAuth}
              onComplete={() => {
                saveStepData('credit_auth', { authorized: true }, true);
                goToNextStep();
              }}
            />
          )}

          {currentStep === 'review' && (
            <ReviewStep
              application={application}
              stepData={stepData}
              completedSteps={completedSteps}
              prequalResult={prequalResult}
              onSubmit={submitApplication}
              onEditStep={setCurrentStep}
            />
          )}

          {/* Navigation buttons */}
          <div className="step-navigation">
            {currentStep !== 'personal_info' && (
              <button className="btn-prev" onClick={goToPrevStep}>
                ← Previous
              </button>
            )}
            <div className="nav-spacer"></div>
          </div>
        </main>
      </div>
    </div>
  );
}

// Personal Information Step Component
function PersonalInfoStep({ data, application, onSave, onComplete }) {
  const [form, setForm] = useState({
    firstName: data.firstName || application?.borrower_first_name || '',
    lastName: data.lastName || application?.borrower_last_name || '',
    email: data.email || application?.borrower_email || '',
    phone: data.phone || application?.borrower_phone || '',
    dateOfBirth: data.dateOfBirth || '',
    ssn: data.ssn || '',
    maritalStatus: data.maritalStatus || '',
    dependents: data.dependents || '0',
    citizenship: data.citizenship || 'us_citizen',
    currentAddress: data.currentAddress || '',
    city: data.city || '',
    state: data.state || '',
    zip: data.zip || '',
    yearsAtAddress: data.yearsAtAddress || '',
    housingType: data.housingType || 'rent',
    monthlyRent: data.monthlyRent || '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  return (
    <div className="step-panel">
      <h2>Personal Information</h2>
      <p className="step-description">Please provide your personal details.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label>First Name *</label>
            <input
              type="text"
              name="firstName"
              value={form.firstName}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
          <div className="form-group">
            <label>Last Name *</label>
            <input
              type="text"
              name="lastName"
              value={form.lastName}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
          <div className="form-group">
            <label>Phone *</label>
            <input
              type="tel"
              name="phone"
              value={form.phone}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Date of Birth *</label>
            <input
              type="date"
              name="dateOfBirth"
              value={form.dateOfBirth}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
          <div className="form-group">
            <label>Social Security Number *</label>
            <input
              type="password"
              name="ssn"
              value={form.ssn}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="XXX-XX-XXXX"
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Marital Status</label>
            <select name="maritalStatus" value={form.maritalStatus} onChange={handleChange} onBlur={handleBlur}>
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
              name="dependents"
              value={form.dependents}
              onChange={handleChange}
              onBlur={handleBlur}
              min="0"
            />
          </div>
        </div>

        <div className="form-group">
          <label>Citizenship Status *</label>
          <select name="citizenship" value={form.citizenship} onChange={handleChange} onBlur={handleBlur} required>
            <option value="us_citizen">U.S. Citizen</option>
            <option value="permanent_resident">Permanent Resident</option>
            <option value="non_permanent_resident">Non-Permanent Resident</option>
          </select>
        </div>

        <h3>Current Address</h3>

        <div className="form-group">
          <label>Street Address *</label>
          <input
            type="text"
            name="currentAddress"
            value={form.currentAddress}
            onChange={handleChange}
            onBlur={handleBlur}
            required
          />
        </div>

        <div className="form-row form-row-3">
          <div className="form-group">
            <label>City *</label>
            <input
              type="text"
              name="city"
              value={form.city}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
          <div className="form-group">
            <label>State *</label>
            <input
              type="text"
              name="state"
              value={form.state}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
          <div className="form-group">
            <label>ZIP *</label>
            <input
              type="text"
              name="zip"
              value={form.zip}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Years at Address</label>
            <input
              type="number"
              name="yearsAtAddress"
              value={form.yearsAtAddress}
              onChange={handleChange}
              onBlur={handleBlur}
              min="0"
              step="0.5"
            />
          </div>
          <div className="form-group">
            <label>Housing Type *</label>
            <select name="housingType" value={form.housingType} onChange={handleChange} onBlur={handleBlur} required>
              <option value="rent">Rent</option>
              <option value="own">Own</option>
              <option value="living_rent_free">Living Rent Free</option>
            </select>
          </div>
          {form.housingType === 'rent' && (
            <div className="form-group">
              <label>Monthly Rent</label>
              <input
                type="number"
                name="monthlyRent"
                value={form.monthlyRent}
                onChange={handleChange}
                onBlur={handleBlur}
                min="0"
              />
            </div>
          )}
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Co-Borrower Step Component
function CoborrowerStep({ data, application, token, onSave, onComplete }) {
  const [hasCoborrower, setHasCoborrower] = useState(application?.has_coborrower || false);
  const [form, setForm] = useState({
    firstName: data.firstName || '',
    lastName: data.lastName || '',
    email: data.email || application?.coborrower_email || '',
    phone: data.phone || '',
    relationship: data.relationship || 'spouse',
  });
  const [inviteSent, setInviteSent] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleSendInvite = async () => {
    try {
      await publicApplicationAPI.createCoborrowerInvitation(token, {
        email: form.email,
        first_name: form.firstName,
        last_name: form.lastName,
        phone: form.phone,
        relationship_type: form.relationship,
        send_email: true,
      });
      setInviteSent(true);
    } catch (err) {
      console.error('Error sending invitation:', err);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete({ ...form, hasCoborrower });
  };

  if (!hasCoborrower) {
    return (
      <div className="step-panel">
        <h2>Co-Borrower Information</h2>
        <p className="step-description">Will anyone else be on this loan with you?</p>

        <div className="coborrower-choice">
          <button
            className="choice-btn"
            onClick={() => setHasCoborrower(true)}
          >
            Yes, add a co-borrower
          </button>
          <button
            className="choice-btn secondary"
            onClick={() => onComplete({ hasCoborrower: false })}
          >
            No, continue without
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-panel">
      <h2>Co-Borrower Information</h2>
      <p className="step-description">
        Enter your co-borrower's information. We'll send them an invitation to complete their section.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label>First Name *</label>
            <input
              type="text"
              name="firstName"
              value={form.firstName}
              onChange={handleChange}
              required
            />
          </div>
          <div className="form-group">
            <label>Last Name *</label>
            <input
              type="text"
              name="lastName"
              value={form.lastName}
              onChange={handleChange}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Email *</label>
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              required
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              name="phone"
              value={form.phone}
              onChange={handleChange}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Relationship</label>
          <select name="relationship" value={form.relationship} onChange={handleChange}>
            <option value="spouse">Spouse</option>
            <option value="partner">Partner</option>
            <option value="family_member">Family Member</option>
            <option value="other">Other</option>
          </select>
        </div>

        {!inviteSent ? (
          <button
            type="button"
            className="btn-secondary"
            onClick={handleSendInvite}
          >
            Send Invitation to Co-Borrower
          </button>
        ) : (
          <div className="invite-sent-message">
            ✓ Invitation sent to {form.email}
          </div>
        )}

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Property Step Component
function PropertyStep({ data, onSave, onComplete }) {
  const [form, setForm] = useState({
    loanPurpose: data.loanPurpose || 'purchase',
    propertyType: data.propertyType || 'single_family',
    occupancy: data.occupancy || 'primary',
    propertyAddress: data.propertyAddress || '',
    city: data.city || '',
    state: data.state || '',
    zip: data.zip || '',
    county: data.county || '',
    purchasePrice: data.purchasePrice || '',
    downPayment: data.downPayment || '',
    downPaymentType: data.downPaymentType || 'percentage',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  return (
    <div className="step-panel">
      <h2>Property Information</h2>
      <p className="step-description">Tell us about the property.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Loan Purpose *</label>
          <select name="loanPurpose" value={form.loanPurpose} onChange={handleChange} onBlur={handleBlur} required>
            <option value="purchase">Purchase</option>
            <option value="refinance">Refinance</option>
            <option value="cash_out_refinance">Cash-Out Refinance</option>
            <option value="construction">Construction</option>
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Property Type *</label>
            <select name="propertyType" value={form.propertyType} onChange={handleChange} onBlur={handleBlur} required>
              <option value="single_family">Single Family</option>
              <option value="condo">Condo</option>
              <option value="townhouse">Townhouse</option>
              <option value="multi_family">Multi-Family (2-4 units)</option>
              <option value="manufactured">Manufactured Home</option>
            </select>
          </div>
          <div className="form-group">
            <label>Occupancy *</label>
            <select name="occupancy" value={form.occupancy} onChange={handleChange} onBlur={handleBlur} required>
              <option value="primary">Primary Residence</option>
              <option value="secondary">Second Home</option>
              <option value="investment">Investment Property</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <AddressAutocomplete
            label="Property Address"
            value={form.propertyAddress}
            onChange={(value) => {
              setForm(prev => ({ ...prev, propertyAddress: value }));
            }}
            onAddressSelect={(addressData) => {
              setForm(prev => ({
                ...prev,
                propertyAddress: addressData.fullAddress || addressData.streetAddress || '',
                city: addressData.city || '',
                state: addressData.state || '',
                zip: addressData.zip || '',
                county: addressData.county || '',
              }));
              onSave({
                ...form,
                propertyAddress: addressData.fullAddress || addressData.streetAddress || '',
                city: addressData.city || '',
                state: addressData.state || '',
                zip: addressData.zip || '',
                county: addressData.county || '',
              });
            }}
            placeholder="Start typing address..."
            types={['address']}
          />
        </div>

        <div className="form-row form-row-3">
          <div className="form-group">
            <label>City</label>
            <input
              type="text"
              name="city"
              value={form.city}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="Auto-filled from address"
            />
          </div>
          <div className="form-group">
            <label>State</label>
            <input
              type="text"
              name="state"
              value={form.state}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="Auto-filled"
            />
          </div>
          <div className="form-group">
            <label>ZIP</label>
            <input
              type="text"
              name="zip"
              value={form.zip}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="Auto-filled"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Purchase Price *</label>
            <input
              type="number"
              name="purchasePrice"
              value={form.purchasePrice}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
              required
            />
          </div>
          <div className="form-group">
            <label>Down Payment *</label>
            <div className="input-with-toggle">
              <input
                type="number"
                name="downPayment"
                value={form.downPayment}
                onChange={handleChange}
                onBlur={handleBlur}
                required
              />
              <select
                name="downPaymentType"
                value={form.downPaymentType}
                onChange={handleChange}
                className="input-toggle"
              >
                <option value="percentage">%</option>
                <option value="amount">$</option>
              </select>
            </div>
          </div>
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Income Step Component
function IncomeStep({ data, onSave, onComplete, calculatePrequal, prequalResult }) {
  const [form, setForm] = useState({
    employmentType: data.employmentType || 'w2',
    employerName: data.employerName || '',
    employerAddress: data.employerAddress || '',
    employerCity: data.employerCity || '',
    employerState: data.employerState || '',
    employerPhone: data.employerPhone || '',
    jobTitle: data.jobTitle || '',
    yearsEmployed: data.yearsEmployed || '',
    monthsEmployed: data.monthsEmployed || '',
    annualIncome: data.annualIncome || '',
    monthlyBonus: data.monthlyBonus || '',
    monthlyCommission: data.monthlyCommission || '',
    otherIncome: data.otherIncome || '',
    otherIncomeSource: data.otherIncomeSource || '',
    creditScoreRange: data.creditScoreRange || '700-739',
  });
  const [calculating, setCalculating] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handlePrequal = async () => {
    setCalculating(true);
    try {
      // Get property data from saved step data
      await calculatePrequal({
        annual_income: parseFloat(form.annualIncome) || 0,
        monthly_debts: 0, // Will be updated in liabilities step
        credit_score_range: form.creditScoreRange,
        down_payment: 20,
        down_payment_type: 'percentage',
        loan_type: 'conventional',
        property_type: 'single_family',
        occupancy: 'primary',
      });
    } catch (err) {
      console.error('Error calculating pre-qualification:', err);
    } finally {
      setCalculating(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  return (
    <div className="step-panel">
      <h2>Income & Employment</h2>
      <p className="step-description">Tell us about your employment and income.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Employment Type *</label>
          <select name="employmentType" value={form.employmentType} onChange={handleChange} onBlur={handleBlur} required>
            <option value="w2">W-2 Employee</option>
            <option value="self_employed">Self-Employed</option>
            <option value="1099">1099 Contractor</option>
            <option value="retired">Retired</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <EmployerAutocomplete
              label="Employer Name"
              value={form.employerName}
              onChange={(value) => {
                setForm(prev => ({ ...prev, employerName: value }));
              }}
              onEmployerSelect={(employerData) => {
                setForm(prev => ({
                  ...prev,
                  employerName: employerData.name || '',
                  employerAddress: employerData.address || '',
                  employerCity: employerData.city || '',
                  employerState: employerData.state || '',
                  employerPhone: employerData.phone || '',
                }));
                onSave({
                  ...form,
                  employerName: employerData.name || '',
                  employerAddress: employerData.address || '',
                  employerCity: employerData.city || '',
                  employerState: employerData.state || '',
                  employerPhone: employerData.phone || '',
                });
              }}
              placeholder="Start typing employer name..."
              required
            />
          </div>
          <div className="form-group">
            <label>Job Title *</label>
            <input
              type="text"
              name="jobTitle"
              value={form.jobTitle}
              onChange={handleChange}
              onBlur={handleBlur}
              required
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Years at Job</label>
            <input
              type="number"
              name="yearsEmployed"
              value={form.yearsEmployed}
              onChange={handleChange}
              onBlur={handleBlur}
              min="0"
            />
          </div>
          <div className="form-group">
            <label>Months</label>
            <input
              type="number"
              name="monthsEmployed"
              value={form.monthsEmployed}
              onChange={handleChange}
              onBlur={handleBlur}
              min="0"
              max="11"
            />
          </div>
        </div>

        <div className="form-group">
          <label>Annual Base Income *</label>
          <input
            type="number"
            name="annualIncome"
            value={form.annualIncome}
            onChange={handleChange}
            onBlur={handleBlur}
            placeholder="$"
            required
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Monthly Bonus (avg)</label>
            <input
              type="number"
              name="monthlyBonus"
              value={form.monthlyBonus}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
          <div className="form-group">
            <label>Monthly Commission (avg)</label>
            <input
              type="number"
              name="monthlyCommission"
              value={form.monthlyCommission}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Other Monthly Income</label>
            <input
              type="number"
              name="otherIncome"
              value={form.otherIncome}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
          <div className="form-group">
            <label>Source of Other Income</label>
            <input
              type="text"
              name="otherIncomeSource"
              value={form.otherIncomeSource}
              onChange={handleChange}
              onBlur={handleBlur}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Estimated Credit Score *</label>
          <select name="creditScoreRange" value={form.creditScoreRange} onChange={handleChange} onBlur={handleBlur} required>
            <option value="760+">760+</option>
            <option value="740-759">740-759</option>
            <option value="720-739">720-739</option>
            <option value="700-719">700-719</option>
            <option value="680-699">680-699</option>
            <option value="660-679">660-679</option>
            <option value="640-659">640-659</option>
            <option value="620-639">620-639</option>
            <option value="<620">Below 620</option>
          </select>
        </div>

        {/* Pre-qualification calculator */}
        <div className="prequal-section">
          <button
            type="button"
            className="btn-prequal"
            onClick={handlePrequal}
            disabled={calculating}
          >
            {calculating ? 'Calculating...' : 'Calculate Pre-Qualification'}
          </button>

          {prequalResult && (
            <div className="prequal-result">
              <h4>Your Pre-Qualification Estimate</h4>
              <div className="prequal-amount">
                ${prequalResult.max_loan_amount?.toLocaleString()}
              </div>
              <p>Estimated Rate: {prequalResult.estimated_rate}%</p>
              <p>Est. Monthly Payment: ${prequalResult.estimated_monthly_payment?.toLocaleString()}</p>
              {prequalResult.warnings?.length > 0 && (
                <div className="prequal-warnings">
                  {prequalResult.warnings.map((w, i) => (
                    <p key={i} className="warning">{w}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Assets Step Component
function AssetsStep({ data, onSave, onComplete }) {
  const [form, setForm] = useState({
    checkingBalance: data.checkingBalance || '',
    savingsBalance: data.savingsBalance || '',
    investmentBalance: data.investmentBalance || '',
    retirementBalance: data.retirementBalance || '',
    otherAssets: data.otherAssets || '',
    giftFunds: data.giftFunds || '',
    giftSource: data.giftSource || '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  const totalAssets =
    (parseFloat(form.checkingBalance) || 0) +
    (parseFloat(form.savingsBalance) || 0) +
    (parseFloat(form.investmentBalance) || 0) +
    (parseFloat(form.retirementBalance) || 0) +
    (parseFloat(form.otherAssets) || 0) +
    (parseFloat(form.giftFunds) || 0);

  return (
    <div className="step-panel">
      <h2>Assets</h2>
      <p className="step-description">Tell us about your assets and savings.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label>Checking Account Balance</label>
            <input
              type="number"
              name="checkingBalance"
              value={form.checkingBalance}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
          <div className="form-group">
            <label>Savings Account Balance</label>
            <input
              type="number"
              name="savingsBalance"
              value={form.savingsBalance}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Investment Accounts</label>
            <input
              type="number"
              name="investmentBalance"
              value={form.investmentBalance}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
          <div className="form-group">
            <label>Retirement Accounts (401k, IRA)</label>
            <input
              type="number"
              name="retirementBalance"
              value={form.retirementBalance}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
        </div>

        <div className="form-group">
          <label>Other Assets</label>
          <input
            type="number"
            name="otherAssets"
            value={form.otherAssets}
            onChange={handleChange}
            onBlur={handleBlur}
            placeholder="$"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Gift Funds for Down Payment</label>
            <input
              type="number"
              name="giftFunds"
              value={form.giftFunds}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$"
            />
          </div>
          <div className="form-group">
            <label>Gift Source (if applicable)</label>
            <input
              type="text"
              name="giftSource"
              value={form.giftSource}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="e.g., Parents"
            />
          </div>
        </div>

        <div className="total-box">
          <span>Total Assets:</span>
          <strong>${totalAssets.toLocaleString()}</strong>
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Liabilities Step Component
function LiabilitiesStep({ data, onSave, onComplete }) {
  const [form, setForm] = useState({
    monthlyRent: data.monthlyRent || '',
    carPayment: data.carPayment || '',
    studentLoans: data.studentLoans || '',
    creditCards: data.creditCards || '',
    otherDebts: data.otherDebts || '',
    childSupport: data.childSupport || '',
    alimony: data.alimony || '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  const totalMonthlyDebts =
    (parseFloat(form.monthlyRent) || 0) +
    (parseFloat(form.carPayment) || 0) +
    (parseFloat(form.studentLoans) || 0) +
    (parseFloat(form.creditCards) || 0) +
    (parseFloat(form.otherDebts) || 0) +
    (parseFloat(form.childSupport) || 0) +
    (parseFloat(form.alimony) || 0);

  return (
    <div className="step-panel">
      <h2>Monthly Liabilities</h2>
      <p className="step-description">Tell us about your monthly debt obligations.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label>Current Rent/Mortgage Payment</label>
            <input
              type="number"
              name="monthlyRent"
              value={form.monthlyRent}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
          <div className="form-group">
            <label>Car Payment(s)</label>
            <input
              type="number"
              name="carPayment"
              value={form.carPayment}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Student Loan Payments</label>
            <input
              type="number"
              name="studentLoans"
              value={form.studentLoans}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
          <div className="form-group">
            <label>Credit Card Minimum Payments</label>
            <input
              type="number"
              name="creditCards"
              value={form.creditCards}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
        </div>

        <div className="form-group">
          <label>Other Monthly Debts</label>
          <input
            type="number"
            name="otherDebts"
            value={form.otherDebts}
            onChange={handleChange}
            onBlur={handleBlur}
            placeholder="$/month"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Child Support</label>
            <input
              type="number"
              name="childSupport"
              value={form.childSupport}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
          <div className="form-group">
            <label>Alimony</label>
            <input
              type="number"
              name="alimony"
              value={form.alimony}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="$/month"
            />
          </div>
        </div>

        <div className="total-box">
          <span>Total Monthly Debts:</span>
          <strong>${totalMonthlyDebts.toLocaleString()}/month</strong>
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Declarations Step Component
function DeclarationsStep({ data, onSave, onComplete }) {
  const [form, setForm] = useState({
    outstandingJudgments: data.outstandingJudgments || false,
    bankruptcy: data.bankruptcy || false,
    bankruptcyType: data.bankruptcyType || '',
    foreclosure: data.foreclosure || false,
    lawsuit: data.lawsuit || false,
    delinquentFederalDebt: data.delinquentFederalDebt || false,
    alimonyObligation: data.alimonyObligation || false,
    downPaymentBorrowed: data.downPaymentBorrowed || false,
    coMakerOnNote: data.coMakerOnNote || false,
    usCitizen: data.usCitizen || true,
    permanentResident: data.permanentResident || false,
    primaryResidence: data.primaryResidence || true,
    ownershipInterest: data.ownershipInterest || false,
  });

  const handleChange = (e) => {
    const { name, type, checked, value } = e.target;
    setForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleBlur = () => {
    onSave(form);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onComplete(form);
  };

  return (
    <div className="step-panel">
      <h2>Declarations</h2>
      <p className="step-description">Please answer the following questions truthfully.</p>

      <form onSubmit={handleSubmit}>
        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="outstandingJudgments"
              checked={form.outstandingJudgments}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Are there any outstanding judgments against you?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="bankruptcy"
              checked={form.bankruptcy}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Have you declared bankruptcy within the past 7 years?
          </label>
          {form.bankruptcy && (
            <div className="sub-field">
              <label>Type of Bankruptcy</label>
              <select
                name="bankruptcyType"
                value={form.bankruptcyType}
                onChange={handleChange}
                onBlur={handleBlur}
              >
                <option value="">Select...</option>
                <option value="chapter7">Chapter 7</option>
                <option value="chapter13">Chapter 13</option>
                <option value="chapter11">Chapter 11</option>
              </select>
            </div>
          )}
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="foreclosure"
              checked={form.foreclosure}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Have you had property foreclosed upon in the last 7 years?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="lawsuit"
              checked={form.lawsuit}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Are you a party to a lawsuit?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="delinquentFederalDebt"
              checked={form.delinquentFederalDebt}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Are you currently delinquent on any Federal debt?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="alimonyObligation"
              checked={form.alimonyObligation}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Are you obligated to pay alimony, child support, or separate maintenance?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="downPaymentBorrowed"
              checked={form.downPaymentBorrowed}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Is any part of the down payment borrowed?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="coMakerOnNote"
              checked={form.coMakerOnNote}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Are you a co-maker or endorser on a note?
          </label>
        </div>

        <h3>Residency</h3>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="primaryResidence"
              checked={form.primaryResidence}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Will you occupy the property as your primary residence?
          </label>
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              name="ownershipInterest"
              checked={form.ownershipInterest}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            Do you have an ownership interest in a property in the last 3 years?
          </label>
        </div>

        <button type="submit" className="btn-next">
          Continue →
        </button>
      </form>
    </div>
  );
}

// Documents Step Component
function DocumentsStep({ documents, uploading, onUpload, onDelete, onComplete }) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('income');

  const categories = [
    { id: 'income', label: 'Income Documents', description: 'Pay stubs, W-2s, tax returns' },
    { id: 'assets', label: 'Asset Statements', description: 'Bank statements, investment accounts' },
    { id: 'identity', label: 'ID Documents', description: "Driver's license, passport" },
    { id: 'property', label: 'Property Documents', description: 'Purchase contract, HOA docs' },
    { id: 'other', label: 'Other', description: 'Any other supporting documents' },
  ];

  const handleDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      await onUpload(file, selectedCategory);
    }
  };

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    for (const file of files) {
      await onUpload(file, selectedCategory);
    }
    e.target.value = '';
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="step-panel">
      <h2>Upload Documents</h2>
      <p className="step-description">
        Upload your supporting documents to speed up the approval process.
      </p>

      <div className="category-selector">
        <label>Document Category:</label>
        <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}>
          {categories.map(cat => (
            <option key={cat.id} value={cat.id}>{cat.label}</option>
          ))}
        </select>
        <span className="category-hint">
          {categories.find(c => c.id === selectedCategory)?.description}
        </span>
      </div>

      <div
        className={`upload-zone ${dragOver ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {uploading ? (
          <div className="upload-progress">
            <div className="spinner"></div>
            <p>Uploading...</p>
          </div>
        ) : (
          <>
            <div className="upload-icon">📄</div>
            <p>Drag and drop files here, or</p>
            <label className="upload-btn">
              Browse Files
              <input
                type="file"
                multiple
                onChange={handleFileSelect}
                accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                hidden
              />
            </label>
            <p className="upload-hint">PDF, JPG, PNG, DOC up to 10MB each</p>
          </>
        )}
      </div>

      {documents.length > 0 && (
        <div className="uploaded-documents">
          <h4>Uploaded Documents ({documents.length})</h4>
          <ul className="document-list">
            {documents.map(doc => (
              <li key={doc.id} className="document-item">
                <span className="doc-icon">📄</span>
                <div className="doc-info">
                  <span className="doc-name">{doc.filename}</span>
                  <span className="doc-meta">
                    {doc.category} • {formatFileSize(doc.file_size)}
                  </span>
                </div>
                {doc.is_verified && <span className="verified-badge">✓ Verified</span>}
                <button
                  className="delete-btn"
                  onClick={() => onDelete(doc.id)}
                  title="Delete document"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button type="button" className="btn-next" onClick={onComplete}>
        Continue →
      </button>
    </div>
  );
}

// Credit Authorization Step Component
function CreditAuthStep({ captured, onCapture, onComplete }) {
  const [form, setForm] = useState({
    ssnLast4: '',
    consentAgreed: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const consentText = `I hereby authorize the Lender and/or its agents to verify any and all information contained in my loan application by whatever means deemed appropriate, including but not limited to: verification of my employment, income, assets, credit history, and any other information relevant to the loan decision. I understand that this authorization allows the Lender to obtain a consumer credit report and/or other reports or investigations in connection with my application for credit.`;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await onCapture({
        ssn_last4: form.ssnLast4,
        consent_text: consentText,
        consent_agreed: form.consentAgreed,
      });
      onComplete();
    } catch (err) {
      setError('Failed to save authorization. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (captured) {
    return (
      <div className="step-panel">
        <h2>Credit Authorization</h2>
        <div className="auth-captured">
          <span className="check-icon">✓</span>
          <h3>Authorization Captured</h3>
          <p>Your credit authorization has been recorded.</p>
          <button type="button" className="btn-next" onClick={onComplete}>
            Continue →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-panel">
      <h2>Credit Authorization</h2>
      <p className="step-description">
        Please review and authorize us to check your credit.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="consent-box">
          <h4>Credit Authorization Agreement</h4>
          <p>{consentText}</p>
        </div>

        <div className="form-group">
          <label>Last 4 digits of SSN (for verification) *</label>
          <input
            type="text"
            value={form.ssnLast4}
            onChange={(e) => setForm({ ...form, ssnLast4: e.target.value.replace(/\D/g, '').slice(0, 4) })}
            placeholder="XXXX"
            maxLength="4"
            required
          />
        </div>

        <div className="declaration-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.consentAgreed}
              onChange={(e) => setForm({ ...form, consentAgreed: e.target.checked })}
              required
            />
            I have read and agree to the credit authorization above *
          </label>
        </div>

        {error && <div className="error-message">{error}</div>}

        <button
          type="submit"
          className="btn-next"
          disabled={!form.consentAgreed || form.ssnLast4.length !== 4 || submitting}
        >
          {submitting ? 'Saving...' : 'Authorize & Continue →'}
        </button>
      </form>
    </div>
  );
}

// Review Step Component
function ReviewStep({ application, stepData, completedSteps, prequalResult, onSubmit, onEditStep }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit application. Please try again.');
      setSubmitting(false);
    }
  };

  const personalInfo = stepData.personal_info || {};
  const property = stepData.property || {};
  const income = stepData.income || {};

  return (
    <div className="step-panel">
      <h2>Review Your Application</h2>
      <p className="step-description">
        Please review your information before submitting.
      </p>

      <div className="review-sections">
        {/* Personal Info */}
        <div className="review-section">
          <div className="section-header">
            <h4>Personal Information</h4>
            <button className="edit-btn" onClick={() => onEditStep('personal_info')}>Edit</button>
          </div>
          <div className="section-content">
            <p><strong>Name:</strong> {personalInfo.firstName} {personalInfo.lastName}</p>
            <p><strong>Email:</strong> {personalInfo.email}</p>
            <p><strong>Phone:</strong> {personalInfo.phone}</p>
            <p><strong>Address:</strong> {personalInfo.currentAddress}, {personalInfo.city}, {personalInfo.state} {personalInfo.zip}</p>
          </div>
        </div>

        {/* Property Info */}
        <div className="review-section">
          <div className="section-header">
            <h4>Property Information</h4>
            <button className="edit-btn" onClick={() => onEditStep('property')}>Edit</button>
          </div>
          <div className="section-content">
            <p><strong>Loan Purpose:</strong> {property.loanPurpose}</p>
            <p><strong>Property Type:</strong> {property.propertyType}</p>
            <p><strong>Purchase Price:</strong> ${parseFloat(property.purchasePrice || 0).toLocaleString()}</p>
            <p><strong>Down Payment:</strong> {property.downPayment}{property.downPaymentType === 'percentage' ? '%' : ''}</p>
          </div>
        </div>

        {/* Income Info */}
        <div className="review-section">
          <div className="section-header">
            <h4>Income & Employment</h4>
            <button className="edit-btn" onClick={() => onEditStep('income')}>Edit</button>
          </div>
          <div className="section-content">
            <p><strong>Employer:</strong> {income.employerName}</p>
            <p><strong>Annual Income:</strong> ${parseFloat(income.annualIncome || 0).toLocaleString()}</p>
            <p><strong>Credit Score Range:</strong> {income.creditScoreRange}</p>
          </div>
        </div>

        {/* Pre-qualification Result */}
        {prequalResult && (
          <div className="review-section prequal">
            <div className="section-header">
              <h4>Pre-Qualification Estimate</h4>
            </div>
            <div className="section-content">
              <p className="prequal-highlight">
                <strong>Estimated Loan Amount:</strong> ${prequalResult.max_loan_amount?.toLocaleString()}
              </p>
              <p><strong>Estimated Rate:</strong> {prequalResult.estimated_rate}%</p>
              <p><strong>Est. Monthly Payment:</strong> ${prequalResult.estimated_monthly_payment?.toLocaleString()}</p>
            </div>
          </div>
        )}

        {/* Completion Status */}
        <div className="completion-status">
          <h4>Completion Status</h4>
          <ul>
            {STEPS.map(step => {
              if (step.id === 'coborrower' && !application?.has_coborrower) return null;
              const isComplete = completedSteps.includes(step.id);
              return (
                <li key={step.id} className={isComplete ? 'complete' : 'incomplete'}>
                  {isComplete ? '✓' : '○'} {step.label}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {application?.has_coborrower && !application?.coborrower_completed && (
        <div className="warning-message">
          ⚠️ Your co-borrower has not completed their section yet. You can submit now and they can complete their section later.
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      <button
        type="button"
        className="btn-submit"
        onClick={handleSubmit}
        disabled={submitting}
      >
        {submitting ? 'Submitting...' : 'Submit Application'}
      </button>
    </div>
  );
}
